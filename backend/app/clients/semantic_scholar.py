"""
Semantic Scholar academic source client with rate limiting and exponential backoff.
"""

import os
import time
from typing import Any
import httpx

from app.clients.base import AcademicSourceClient, RawCandidatePaper


class SemanticScholarClient(AcademicSourceClient):
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self):
        self.api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

    def search(
        self,
        query: str,
        limit: int = 25,
        year_min: int | None = None,
        year_max: int | None = None,
        oa_only: bool = False,
    ) -> list[RawCandidatePaper]:
        fields = (
            "paperId,externalIds,title,abstract,venue,year,publicationDate,"
            "authors,openAccessPdf,citationCount,references"
        )
        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 50),
            "fields": fields,
        }

        if year_min and year_max:
            params["year"] = f"{year_min}-{year_max}"
        elif year_min:
            params["year"] = f"{year_min}-"
        elif year_max:
            params["year"] = f"-{year_max}"

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        retries = 3
        backoff = 1.0
        data: dict[str, Any] = {}

        for attempt in range(retries):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.get(self.BASE_URL, params=params, headers=headers)
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("Retry-After", backoff))
                        time.sleep(retry_after)
                        backoff *= 2
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
            except Exception:
                if attempt == retries - 1:
                    return []
                time.sleep(backoff)
                backoff *= 2

        results: list[RawCandidatePaper] = []
        for item in data.get("data", []):
            title = (item.get("title") or "").strip()
            if not title:
                continue

            external_ids = item.get("externalIds") or {}
            doi = external_ids.get("DOI")
            s2_id = item.get("paperId")

            authors = [{"name": a.get("name", "")} for a in item.get("authors", []) if a.get("name")]
            oa_obj = item.get("openAccessPdf") or {}
            oa_pdf_url = oa_obj.get("url")

            if oa_only and not oa_pdf_url:
                continue

            raw_refs = [
                r.get("paperId") or r.get("title")
                for r in (item.get("references") or [])
                if isinstance(r, dict) and (r.get("paperId") or r.get("title"))
            ]

            citation_count = int(item.get("citationCount") or 0)
            abstract = item.get("abstract")

            results.append(
                RawCandidatePaper(
                    source="semantic_scholar",
                    external_id=str(s2_id or ""),
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    year=item.get("year"),
                    date=item.get("publicationDate"),
                    venue=item.get("venue"),
                    doi=doi,
                    url=f"https://www.semanticscholar.org/paper/{s2_id}" if s2_id else None,
                    oa_status="gold" if oa_pdf_url else None,
                    oa_pdf_url=oa_pdf_url,
                    license=None,
                    citation_count=citation_count,
                    raw_references=raw_refs,
                    metadata_only=abstract is None,
                )
            )

        return results
