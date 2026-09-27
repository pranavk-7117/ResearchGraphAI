import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import (
    cosine_similarity,
    decode_embedding,
    encode_embedding,
)
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService


@dataclass
class IngestedPaper:
    paper: models.Paper
    citation_edges: int
    similarity_edges: int
    saved_path: str = ""


class PDFIngestionService:
    def __init__(self) -> None:
        self.embeddings = EmbeddingService()
        self.llm = LLMService()

    def ingest_pdf(
        self, db: Session, file_bytes: bytes, original_filename: str = "paper.pdf"
    ) -> IngestedPaper:
        import fitz

        # 1. Save the uploaded research paper into the user's Downloads directory
        saved_file_path = self._save_to_downloads(file_bytes, original_filename)

        # 2. Extract text and metadata
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = "\n".join(page.get_text() for page in doc)
        first_page = doc[0] if doc.page_count else None
        page_one_text = first_page.get_text() if first_page else ""
        title = self._extract_title(first_page, page_one_text)
        metadata = self._semantic_scholar_lookup(title) or self._fallback_metadata(
            page_one_text, full_text, title
        )
        whole_embedding = self.embeddings.embed(f"{metadata['title']}\n{metadata['abstract']}")
        paper = models.Paper(
            title=metadata["title"],
            authors=metadata["authors"],
            abstract=metadata["abstract"],
            year=metadata["year"],
            source_type=metadata["source_type"],
            full_text=full_text,
            whole_embedding=encode_embedding(whole_embedding),
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)
        self._store_chunks(db, paper.id, full_text)
        citation_count = self._link_references(db, paper.id, full_text)
        similarity_count = self._link_similar_papers(db, paper, whole_embedding)
        db.commit()
        return IngestedPaper(paper, citation_count, similarity_count, saved_file_path)

    def _save_to_downloads(self, file_bytes: bytes, original_filename: str) -> str:
        """Store the uploaded research paper PDF in the user's Downloads folder."""
        # Check environment override or default to OS user Downloads directory
        downloads_dir = Path(os.getenv("DOWNLOADS_DIR", str(Path.home() / "Downloads")))
        downloads_dir.mkdir(parents=True, exist_ok=True)

        clean_name = re.sub(r'[\\/*?:"<>|]', "", original_filename).strip()
        if not clean_name:
            clean_name = "uploaded_paper.pdf"
        if not clean_name.lower().endswith(".pdf"):
            clean_name += ".pdf"

        target_file = downloads_dir / clean_name
        stem = target_file.stem
        ext = target_file.suffix
        counter = 1
        while target_file.exists():
            target_file = downloads_dir / f"{stem}_{counter}{ext}"
            counter += 1

        target_file.write_bytes(file_bytes)
        return str(target_file.resolve())

    def _extract_title(self, page, page_one_text: str) -> str:
        if not page:
            return "Untitled paper"
        candidates: list[tuple[float, str]] = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = " ".join(span.get("text", "").strip() for span in spans).strip()
                if len(text) > 8:
                    candidates.append((max(span.get("size", 0) for span in spans), text))
        if candidates:
            return sorted(candidates, reverse=True)[0][1][:500]
        return page_one_text.splitlines()[0][:500] if page_one_text else "Untitled paper"

    def _semantic_scholar_lookup(self, title: str) -> dict | None:
        try:
            response = httpx.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": title, "limit": 1, "fields": "title,abstract,year,authors"},
                timeout=8,
            )
            response.raise_for_status()
            rows = response.json().get("data", [])
            if not rows:
                return None
            row = rows[0]
            if fuzz.token_set_ratio(title, row.get("title", "")) < 82:
                return None
            return {
                "title": row.get("title") or title,
                "authors": ", ".join(author["name"] for author in row.get("authors", [])),
                "abstract": row.get("abstract") or "",
                "year": row.get("year"),
                "source_type": "indexed",
            }
        except Exception:
            return None

    def _fallback_metadata(self, page_one_text: str, full_text: str, title: str) -> dict:
        authors = self.llm.complete("Extract author names only.", page_one_text[:2500])
        year_text = self.llm.complete("Guess publication year as a number, or blank.", page_one_text[:2500])
        year_match = re.search(r"(19|20)\d{2}", year_text)
        return {
            "title": title,
            "authors": authors.strip() or "Unknown",
            "abstract": self._extract_abstract(full_text),
            "year": int(year_match.group(0)) if year_match else None,
            "source_type": "user_uploaded",
        }

    def _extract_abstract(self, text: str) -> str:
        match = re.search(
            r"abstract\s*(.+?)(?:\n\s*(?:introduction|1\.|keywords|background)\b)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s+", " ", match.group(1)).strip()[:3000] if match else ""

    def _store_chunks(self, db: Session, paper_id: int, text: str) -> None:
        words = text.split()
        for index in range(0, len(words), 250):
            chunk = " ".join(words[index : index + 250])
            if not chunk:
                continue
            db.add(
                models.PaperChunk(
                    paper_id=paper_id,
                    chunk_index=index // 250,
                    text=chunk,
                    embedding=encode_embedding(self.embeddings.embed(chunk)),
                )
            )

    def _link_references(self, db: Session, paper_id: int, text: str) -> int:
        reference_text = self._reference_section(text)
        if not reference_text:
            return 0
        known = db.query(models.Paper).filter(models.Paper.id != paper_id).all()
        count = 0
        for line in reference_text.splitlines():
            if len(line.strip()) < 20:
                continue
            best = max(known, key=lambda paper: fuzz.token_set_ratio(line, paper.title), default=None)
            if best and fuzz.token_set_ratio(line, best.title) > 86:
                db.add(
                    models.Edge(
                        source_paper_id=paper_id,
                        target_paper_id=best.id,
                        edge_type="citation",
                        relation_label="cites",
                        confidence=0.95,
                    )
                )
                count += 1
        return count

    def _reference_section(self, text: str) -> str:
        match = re.search(r"\n\s*(references|bibliography)\s*\n(.+)$", text, re.IGNORECASE | re.DOTALL)
        return match.group(2) if match else ""

    def _link_similar_papers(
        self, db: Session, paper: models.Paper, embedding: list[float], threshold: float = 0.75
    ) -> int:
        others = db.query(models.Paper).filter(models.Paper.id != paper.id).all()
        count = 0
        for other in others:
            score = cosine_similarity(embedding, decode_embedding(other.whole_embedding))
            if score > threshold:
                db.add(
                    models.Edge(
                        source_paper_id=paper.id,
                        target_paper_id=other.id,
                        edge_type="similarity",
                        relation_label="similar",
                        confidence=round(score, 3),
                    )
                )
                db.add(
                    models.Edge(
                        source_paper_id=other.id,
                        target_paper_id=paper.id,
                        edge_type="similarity",
                        relation_label="similar",
                        confidence=round(score, 3),
                    )
                )
                count += 2
        return count
