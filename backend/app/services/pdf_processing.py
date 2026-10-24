"""
PDF Processing, Extraction, and Chunking Service for ResearchGraphAI.

Extracts page-by-page text, detects sections, flags OCR-needed/empty extractions,
produces section-aware chunks with provenance, and extracts references.
"""

import hashlib
import os
import re
from typing import Any
import fitz  # PyMuPDF
from pydantic import BaseModel

from app.services.llm import LLMService


class ExtractedChunk(BaseModel):
    chunk_index: int
    page_start: int
    page_end: int
    section: str | None
    text: str
    text_hash: str


class PDFExtractionResult(BaseModel):
    title: str | None = None
    authors: list[dict[str, str]] = []
    abstract: str | None = None
    year: int | None = None
    doi: str | None = None
    total_pages: int = 0
    total_bytes: int = 0
    chunks: list[ExtractedChunk] = []
    raw_references: list[str] = []
    is_ocr_needed: bool = False
    is_empty: bool = False
    full_text_available: bool = False


class PDFProcessingService:
    def __init__(self):
        self.llm = LLMService()

    def process_pdf_bytes(
        self,
        pdf_bytes: bytes,
        known_title: str | None = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
    ) -> PDFExtractionResult:
        """
        Process PDF document bytes:
        - Validates format
        - Extracts text per page
        - Detects sections and references
        - Produces section-aware chunks
        """
        if not pdf_bytes or len(pdf_bytes) < 10:
            return PDFExtractionResult(is_empty=True, total_bytes=len(pdf_bytes))

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise RuntimeError(f"Corrupt or encrypted PDF could not be opened: {e}") from e

        total_pages = len(doc)
        total_bytes = len(pdf_bytes)

        if total_pages == 0:
            doc.close()
            return PDFExtractionResult(is_empty=True, total_pages=0, total_bytes=total_bytes)

        pages_text: list[tuple[int, str]] = []  # (page_num, text)
        total_extracted_chars = 0

        for page_idx in range(total_pages):
            page = doc[page_idx]
            text = page.get_text("text") or ""
            clean_text = " ".join(text.split())
            total_extracted_chars += len(clean_text)
            pages_text.append((page_idx + 1, clean_text))

        # Check for scanned / image-only PDFs
        if total_extracted_chars < 200:
            doc.close()
            return PDFExtractionResult(
                total_pages=total_pages,
                total_bytes=total_bytes,
                is_ocr_needed=True,
                is_empty=total_extracted_chars == 0,
                full_text_available=False,
            )

        # 1. Extract metadata from PDF or first pages
        extracted_title = known_title
        extracted_abstract = None
        extracted_doi = None
        extracted_year = None
        extracted_authors: list[dict[str, str]] = []

        first_page_text = pages_text[0][1] if pages_text else ""
        second_page_text = pages_text[1][1] if len(pages_text) > 1 else ""
        intro_text = f"{first_page_text}\n{second_page_text}"

        # DOI regex lookup
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", intro_text)
        if doi_match:
            extracted_doi = doi_match.group(0).rstrip(".,;")

        # Year regex lookup
        year_matches = re.findall(r"\b(20\d{2}|19\d{2})\b", intro_text)
        if year_matches:
            plausible_years = [int(y) for y in year_matches if 1980 <= int(y) <= 2030]
            if plausible_years:
                extracted_year = plausible_years[0]

        # Abstract lookup
        abstract_match = re.search(r"\babstract\b[:\s]*(.+?)(?=\b(introduction|keywords|1\.\s*introduction)\b|\Z)", intro_text, re.I | re.S)
        if abstract_match:
            extracted_abstract = abstract_match.group(1).strip()[:2000]

        # If title is unknown, extract using metadata or LLM/heuristics
        if not extracted_title or len(extracted_title) < 5:
            pdf_meta_title = doc.metadata.get("title", "")
            if pdf_meta_title and len(pdf_meta_title.strip()) > 6 and not pdf_meta_title.lower().endswith(".pdf"):
                extracted_title = pdf_meta_title.strip()
            elif self.llm.is_available():
                prompt = (
                    "Extract the exact academic paper title and authors from the following beginning text of a research paper. "
                    "Output in JSON with keys 'title' and 'authors' (list of strings):\n\n"
                    f"{intro_text[:1800]}"
                )
                try:
                    res = self.llm.complete(prompt)
                    # Simple JSON extract
                    json_match = re.search(r"\{.*\}", res, re.S)
                    if json_match:
                        import json
                        meta = json.loads(json_match.group(0))
                        extracted_title = meta.get("title", extracted_title)
                        for a in meta.get("authors", []):
                            extracted_authors.append({"name": str(a)})
                except Exception:
                    pass

        # Fallback title if still empty: first meaningful header line
        if not extracted_title:
            lines = [line.strip() for line in first_page_text.splitlines() if len(line.strip()) > 8]
            extracted_title = lines[0] if lines else "Untitled Document"

        # 2. Extract References section
        raw_references = self._extract_references(pages_text)

        # 3. Section-aware Chunking
        chunks = self._chunk_pages(pages_text, chunk_size=chunk_size, overlap=chunk_overlap)

        doc.close()

        return PDFExtractionResult(
            title=extracted_title,
            authors=extracted_authors,
            abstract=extracted_abstract,
            year=extracted_year,
            doi=extracted_doi,
            total_pages=total_pages,
            total_bytes=total_bytes,
            chunks=chunks,
            raw_references=raw_references,
            is_ocr_needed=False,
            is_empty=False,
            full_text_available=len(chunks) > 0,
        )

    def _extract_references(self, pages_text: list[tuple[int, str]]) -> list[str]:
        """Extract reference list entries from the end of the paper."""
        full_text = "\n".join(t for _, t in pages_text)
        # Search for references section
        ref_header = re.search(r"\n\s*(references|bibliography)\s*\n", full_text, re.I)
        if not ref_header:
            return []

        ref_body = full_text[ref_header.end():]
        # Split by bracket numbers [1], [2] or numbers 1., 2.
        raw_items = re.split(r"\n\s*(?:\[\d+\]|\d+\.)\s+", ref_body)
        cleaned_refs = []
        for item in raw_items:
            clean = " ".join(item.split()).strip()
            if len(clean) > 20 and not clean.startswith("http"):
                cleaned_refs.append(clean[:400])
        return cleaned_refs[:60]

    def _chunk_pages(
        self,
        pages_text: list[tuple[int, str]],
        chunk_size: int = 1000,
        overlap: int = 150,
    ) -> list[ExtractedChunk]:
        """Produce section-aware chunks that preserve page_start, page_end, and section."""
        chunks: list[ExtractedChunk] = []
        chunk_idx = 0

        current_section = "Introduction"
        current_text = ""
        page_start = 1
        page_end = 1

        section_pattern = re.compile(
            r"\b(abstract|introduction|related work|background|methodology|methods|experiments|results|discussion|conclusion|limitations)\b",
            re.I,
        )

        for page_num, text in pages_text:
            if not text:
                continue

            # Check if section header appears in text
            sec_match = section_pattern.search(text)
            if sec_match:
                current_section = sec_match.group(1).title()

            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                sentence_clean = sentence.strip()
                if not sentence_clean:
                    continue

                if len(current_text) + len(sentence_clean) > chunk_size and len(current_text) > 300:
                    text_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
                    chunks.append(
                        ExtractedChunk(
                            chunk_index=chunk_idx,
                            page_start=page_start,
                            page_end=page_num,
                            section=current_section,
                            text=current_text,
                            text_hash=text_hash,
                        )
                    )
                    chunk_idx += 1
                    # Retain overlap from end of current_text
                    current_text = current_text[-overlap:] + " " + sentence_clean
                    page_start = page_num
                else:
                    if not current_text:
                        page_start = page_num
                    current_text = f"{current_text} {sentence_clean}".strip()
                    page_end = page_num

        if current_text and len(current_text) > 50:
            text_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
            chunks.append(
                ExtractedChunk(
                    chunk_index=chunk_idx,
                    page_start=page_start,
                    page_end=page_end,
                    section=current_section,
                    text=current_text,
                    text_hash=text_hash,
                )
            )

        return chunks
