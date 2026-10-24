"""
Document Storage Service for ResearchGraphAI.

Supports Supabase Storage bucket integration with a fallback to secure local storage.
Validates file headers, computes SHA-256 hashes, prevents client-controlled file paths,
and manages document cleanup.
"""

import hashlib
import os
from pathlib import Path
from typing import BinaryIO
import httpx
from fastapi import HTTPException, status

BACKEND_DIR = Path(__file__).resolve().parents[1]
LOCAL_STORAGE_DIR = BACKEND_DIR / "storage" / "documents"
LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class StorageService:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = os.getenv("STORAGE_BUCKET", "research-papers")
        self.use_supabase = bool(self.supabase_url and self.service_key)

    def validate_pdf(self, content: bytes) -> None:
        """Validate PDF magic bytes and size."""
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file provided",
            )
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB",
            )
        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file format. File must be a valid PDF document with %PDF- header",
            )

    def save_document(self, content: bytes, project_id: int | None = None) -> tuple[str, str, int]:
        """
        Validates and saves a PDF document.
        Returns: (storage_path, sha256_hash, file_size_bytes)
        """
        self.validate_pdf(content)
        sha256_hash = hashlib.sha256(content).hexdigest()
        filename = f"{sha256_hash}.pdf"
        storage_rel_path = f"projects/{project_id or 'global'}/{filename}"

        if self.use_supabase:
            url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_rel_path}"
            headers = {
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/pdf",
                "x-upsert": "true",
            }
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, headers=headers, content=content)
                    if resp.status_code not in (200, 201):
                        # Fallback to local if bucket not configured or error
                        local_path = LOCAL_STORAGE_DIR / filename
                        local_path.write_bytes(content)
                        return str(local_path), sha256_hash, len(content)
                return storage_rel_path, sha256_hash, len(content)
            except Exception:
                local_path = LOCAL_STORAGE_DIR / filename
                local_path.write_bytes(content)
                return str(local_path), sha256_hash, len(content)
        else:
            local_path = LOCAL_STORAGE_DIR / filename
            local_path.write_bytes(content)
            return str(local_path), sha256_hash, len(content)

    def get_document_bytes(self, storage_path: str) -> bytes:
        """Retrieve stored document bytes."""
        # Check local path first
        path_obj = Path(storage_path)
        if path_obj.exists() and path_obj.is_file():
            return path_obj.read_bytes()

        if self.use_supabase and not path_obj.is_absolute():
            url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path}"
            headers = {"Authorization": f"Bearer {self.service_key}"}
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.content

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored document file not found",
        )

    def delete_document(self, storage_path: str) -> None:
        """Delete document from storage."""
        path_obj = Path(storage_path)
        if path_obj.exists() and path_obj.is_file():
            try:
                path_obj.unlink()
            except OSError:
                pass

        if self.use_supabase and not path_obj.is_absolute():
            url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path}"
            headers = {"Authorization": f"Bearer {self.service_key}"}
            try:
                with httpx.Client(timeout=10.0) as client:
                    client.delete(url, headers=headers)
            except Exception:
                pass


storage_service = StorageService()
