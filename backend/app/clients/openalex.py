"""
OpenAlex academic source client with bounded retries, polite pool mailto, and abstract reconstruction.
"""

import os
import time
from typing import Any
import httpx

from app.clients.base import AcademicSourceClient, RawCandidatePaper


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index or not isinstance(inverted_index, dict):
        return None
    pos_word: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            pos_word.append((pos, word))
    pos_word.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pos_word) if pos_word else None


class OpenAlexClient(AcademicSourceClient):
    BASE_URL = "https://api.openalex.org/works"

    def __init__(self):
        self.mailto = os.getenv("OPENALEX_MAILTO", "research@researchgraphai.com")

    def search(
        self,
        query: str,
        limit: int = 25,
        year_min: int | None = None,
        year_max: int | None = None,
        oa_only: bool = False,
    ) -> list[RawCandidatePaper]:
        params: dict[str, Any] = {
            "search": query,
            "per-page": min(limit, 50),
            "mailto": self.mailto,
        }

        filters = []
        if oa_only:
            filters.append("is_oa:true")
        if year_min and year_max:
            filters.append(f"publication_year:{year_min}-{year_max}")
        elif year_min:
            filters.append(f"publication_year:>{year_min - 1}")
        elif year_max:
            filters.append(f"publication_year:<{year_max + 1}")

        if filters:
            params["filter"] = ",".join(filters)

        retries = 3
        backoff = 1.0
        data: dict[str, Any] = {}

        for attempt in range(retries):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.get(self.BASE_URL, params=params)
                    if resp.status_code == 429:
                        retry_after = float(resp.headers.get("Retry-After", backoff))
                        time.sleep(retry_after)
                        backoff *= 2
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
            except Exception as e:
                if attempt == retries - 1:
                    return []
                time.sleep(backoff)
                backoff *= 2

        results: list[RawCandidatePaper] = []
        for item in data.get("results", []):
            title = (item.get("title") or "").strip()
            if not title:
                continue

            abstract = reconstruct_abstract(item.get("abstract_inverted_index"))
            doi_raw = item.get("doi")
            doi = doi_raw.replace("https://doi.org/", "").strip() if doi_raw else None
            
            authors = []
            for authorship in item.get("authorships", []):
                author_obj = authorship.get("author", {})
                name = author_obj.get("display_name")
                if name:
                    authors.append({"name": name})

            open_access = item.get("open_access", {})
            oa_status = open_access.get("oa_status")
            oa_pdf_url = open_access.get("oa_url")
            
            primary_loc = item.get("primary_location") or {}
            source_obj = primary_loc.get("source") or {}
            venue = source_obj.get("display_name")
            pdf_url = primary_loc.get("pdf_url") or oa_pdf_url

            citation_count = int(item.get("cited_by_count") or 0)
            raw_refs = [str(r) for r in item.get("referenced_works", [])]

            results.append(
                RawCandidatePaper(
                    source="openalex",
                    external_id=str(item.get("id") or ""),
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    year=item.get("publication_year"),
                    date=item.get("publication_date"),
                    venue=venue,
                    doi=doi,
                    url=item.get("doi") or item.get("id"),
                    oa_status=oa_status,
                    oa_pdf_url=pdf_url,
                    license=primary_loc.get("license"),
                    citation_count=citation_count,
                    raw_references=raw_refs,
                    metadata_only=abstract is None,
                )
            )

        return results
