"""
arXiv academic source client using Atom XML query feed.
"""

import time
import xml.etree.ElementTree as ET
from typing import Any
import httpx

from app.clients.base import AcademicSourceClient, RawCandidatePaper

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivClient(AcademicSourceClient):
    BASE_URL = "https://export.arxiv.org/api/query"

    def search(
        self,
        query: str,
        limit: int = 25,
        year_min: int | None = None,
        year_max: int | None = None,
        oa_only: bool = False,
    ) -> list[RawCandidatePaper]:
        clean_query = query.replace('"', "").strip()
        search_query = f"all:{clean_query}"

        params: dict[str, Any] = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(limit, 50),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        retries = 3
        backoff = 1.0
        xml_content = ""

        for attempt in range(retries):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.get(self.BASE_URL, params=params)
                    if resp.status_code == 429:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    resp.raise_for_status()
                    xml_content = resp.text
                    break
            except Exception:
                if attempt == retries - 1:
                    return []
                time.sleep(backoff)
                backoff *= 2

        if not xml_content:
            return []

        results: list[RawCandidatePaper] = []
        try:
            root = ET.fromstring(xml_content)
            for entry in root.findall("atom:entry", ATOM_NS):
                title_elem = entry.find("atom:title", ATOM_NS)
                if title_elem is None or not title_elem.text:
                    continue
                title = " ".join(title_elem.text.split())

                summary_elem = entry.find("atom:summary", ATOM_NS)
                abstract = " ".join(summary_elem.text.split()) if summary_elem is not None and summary_elem.text else None

                id_elem = entry.find("atom:id", ATOM_NS)
                raw_id = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
                arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

                published_elem = entry.find("atom:published", ATOM_NS)
                date_str = published_elem.text.strip() if published_elem is not None and published_elem.text else None
                year = int(date_str[:4]) if date_str and len(date_str) >= 4 and date_str[:4].isdigit() else None

                if year_min and year and year < year_min:
                    continue
                if year_max and year and year > year_max:
                    continue

                authors = []
                for author_elem in entry.findall("atom:author", ATOM_NS):
                    name_elem = author_elem.find("atom:name", ATOM_NS)
                    if name_elem is not None and name_elem.text:
                        authors.append({"name": name_elem.text.strip()})

                # PDF link
                pdf_url = None
                for link in entry.findall("atom:link", ATOM_NS):
                    if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                        pdf_url = link.get("href")
                        break
                if not pdf_url and arxiv_id:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

                results.append(
                    RawCandidatePaper(
                        source="arxiv",
                        external_id=arxiv_id,
                        title=title,
                        abstract=abstract,
                        authors=authors,
                        year=year,
                        date=date_str,
                        venue="arXiv",
                        doi=None,
                        url=raw_id or f"https://arxiv.org/abs/{arxiv_id}",
                        oa_status="gold",
                        oa_pdf_url=pdf_url,
                        license="arXiv.org perpetual non-exclusive license",
                        citation_count=0,
                        raw_references=[],
                        metadata_only=abstract is None,
                    )
                )
        except Exception:
            return []

        return results
