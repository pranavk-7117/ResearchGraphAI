"""
Tests for PDF Parsing, Page/Section Preservation, OCR Detection, and Storage.
"""

import pytest
from fastapi import HTTPException
import pymupdf

from app.services.pdf_processing import PDFProcessingService
from app.storage import StorageService


def test_pdf_validation_empty_and_corrupt():
    service = StorageService()
    # Empty file
    with pytest.raises(HTTPException) as exc_info:
        service.validate_pdf(b"")
    assert exc_info.value.status_code == 400

    # Non-PDF
    with pytest.raises(HTTPException) as exc_info:
        service.validate_pdf(b"NOT_A_PDF_FILE_HEADER")
    assert exc_info.value.status_code == 400


def test_pdf_ocr_needed_detection():
    # Create a 1-page blank PDF with no text
    doc = pymupdf.open()
    doc.new_page()
    blank_bytes = doc.tobytes()
    doc.close()

    parser = PDFProcessingService()
    res = parser.process_pdf_bytes(blank_bytes)
    assert res.is_ocr_needed is True
    assert res.full_text_available is False


def test_pdf_page_and_section_preservation():
    # Create a multi-page PDF with sections and text
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Abstract\nThis study investigates zero-knowledge proof scalability in distributed systems.")
    p1.insert_text((50, 150), "1. Introduction\nDecentralized verification requires sub-linear cryptographic proofs.")

    p2 = doc.new_page()
    p2.insert_text((50, 72), "2. Methodology\nWe deploy recursive SNARKs across heterogeneous server clusters.")
    p2.insert_text((50, 150), "3. Results\nEmpirical benchmarks show an 8.4x reduction in verification latency.")

    pdf_bytes = doc.tobytes()
    doc.close()

    parser = PDFProcessingService()
    res = parser.process_pdf_bytes(pdf_bytes, known_title="Scalable Zero-Knowledge Verification")

    assert res.total_pages == 2
    assert res.is_ocr_needed is False
    assert res.full_text_available is True
    assert len(res.chunks) > 0

    # Verify chunk structure has page and section preservation
    first_chunk = res.chunks[0]
    assert first_chunk.page_start in (1, 2)
    assert first_chunk.section is not None
    assert len(first_chunk.text_hash) == 64


def test_storage_service_save_and_retrieve():
    storage = StorageService()
    # Create dummy PDF bytes
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 72), "Storage verification document content.")
    content = doc.tobytes()
    doc.close()

    path, sha256_hash, file_size = storage.save_document(content, project_id=999)
    assert len(sha256_hash) == 64
    assert file_size == len(content)

    retrieved = storage.get_document_bytes(path)
    assert retrieved == content

    # Clean up
    storage.delete_document(path)
