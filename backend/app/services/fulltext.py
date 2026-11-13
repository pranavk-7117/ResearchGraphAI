"""
Multi-source Full-Text PDF Resolution Cascade for ResearchGraphAI.

Cascade sources:
1. Stored oa_pdf_url (OpenAlex / Semantic Scholar)
2. OpenAlex locations array / alternate PDFs
3. Semantic Scholar openAccessPdf
4. Direct arXiv PDF (from arXiv ID or arXiv DOI: 10.48550/arXiv.XXXXX)
5. Unpaywall REST API (best_oa_location.url_for_pdf)
6. HTML Landing page meta tags (citation_pdf_url)
7. Europe PMC REST API (fullTextXML / PDF)

Configuration:
- 20-second timeout per source.
- 2 retries with exponential backoff on 429 or 5xx.
- 25 MB max download cap.
- Returns (pdf_bytes, fulltext_note).
"""

import logging
import re
import time
from typing import Any
import httpx

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 25 * 1024 * 1024  # 25 MB
DEFAULT_TIMEOUT = 20.0  # 20 seconds


class FullTextResolver:
    def __init__(self, email: str = "pranav@researchgraphai.com"):
        self.email = email
        self.headers = {
            "User-Agent": f"ResearchGraphAI/2.0 (mailto:{self.email})",
            "Accept": "application/pdf,application/json,text/html,*/*",
        }

    def _http_get_with_retry(
        self,
        client: httpx.Client,
        url: str,
        retries: int = 2,
        backoff_sec: float = 1.0,
    ) -> httpx.Response | None:
        """Execute GET with up to 2 retries on 429 or 5xx."""
        for attempt in range(retries + 1):
            try:
                resp = client.get(url)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(backoff_sec * (2 ** attempt))
                    continue
                return resp
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < retries:
                    time.sleep(backoff_sec * (2 ** attempt))
                    continue
                return None
            except Exception:
                return None
        return None

    def _validate_pdf_bytes(self, content: bytes | None) -> bytes | None:
        if not content or len(content) < 500:
            return None
        if len(content) > MAX_PDF_BYTES:
            logger.warning("PDF exceeded 25MB cap (%d bytes); skipping", len(content))
            return None
        # Must start with %PDF- header
        if content.startswith(b"%PDF-"):
            return content
        # Sometimes an HTML wrapper or leading whitespace appears
        idx = content.find(b"%PDF-")
        if 0 < idx < 256:
            return content[idx:]
        return None

    def fetch_full_text(
        self,
        paper_dict: dict[str, Any],
        stored_oa_url: str | None = None,
    ) -> tuple[bytes | None, str]:
        """
        Cascade through open-access sources to fetch genuine PDF content.
        Returns (pdf_bytes, fulltext_note).
        """
        doi = (paper_dict.get("doi") or "").strip()
        title = (paper_dict.get("title") or "").strip()
        arxiv_id = self._extract_arxiv_id(doi, paper_dict.get("url") or "")

        with httpx.Client(
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            # 1. Stored oa_pdf_url
            candidate_url = stored_oa_url or paper_dict.get("oa_pdf_url")
            if candidate_url and candidate_url.strip():
                resp = self._http_get_with_retry(client, candidate_url.strip())
                if resp and resp.status_code == 200:
                    pdf = self._validate_pdf_bytes(resp.content)
                    if pdf:
                        return pdf, "downloaded_oa_pdf"

            # 2. arXiv Direct PDF
            if arxiv_id:
                arxiv_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                resp = self._http_get_with_retry(client, arxiv_url)
                if resp and resp.status_code == 200:
                    pdf = self._validate_pdf_bytes(resp.content)
                    if pdf:
                        return pdf, "arxiv_direct"

            # 3. Semantic Scholar openAccessPdf lookup
            if doi:
                s2_pdf = self._fetch_semantic_scholar_pdf(client, doi)
                if s2_pdf:
                    return s2_pdf, "semantic_scholar_oa"

            # 4. Unpaywall API
            if doi:
                unpaywall_pdf = self._fetch_unpaywall_pdf(client, doi)
                if unpaywall_pdf:
                    return unpaywall_pdf, "unpaywall"

            # 5. Europe PMC
            if doi:
                epmc_pdf = self._fetch_europe_pmc_pdf(client, doi)
                if epmc_pdf:
                    return epmc_pdf, "europe_pmc"

            # 6. HTML Landing page meta tag extraction (citation_pdf_url)
            landing_url = paper_dict.get("original_url") or paper_dict.get("url") or (f"https://doi.org/{doi}" if doi else None)
            if landing_url:
                meta_pdf = self._fetch_landing_page_meta_pdf(client, landing_url)
                if meta_pdf:
                    return meta_pdf, "landing_meta"

        # If cascade fails to locate open access PDF
        note = "abstract_only_paywalled" if doi else "abstract_only_no_source"
        return None, note

    def _extract_arxiv_id(self, doi: str, url: str) -> str | None:
        """Extract arXiv ID from DOI or URL if present."""
        # 10.48550/arXiv.2301.00001
        m_doi = re.search(r"10\.48550/arXiv\.([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", doi, re.I)
        if m_doi:
            return m_doi.group(1)
        # https://arxiv.org/abs/2301.00001
        m_url = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", url, re.I)
        if m_url:
            return m_url.group(1)
        return None

    def _fetch_semantic_scholar_pdf(self, client: httpx.Client, doi: str) -> bytes | None:
        try:
            api_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf"
            resp = self._http_get_with_retry(client, api_url)
            if resp and resp.status_code == 200:
                data = resp.json()
                oa_info = data.get("openAccessPdf")
                if oa_info and isinstance(oa_info, dict) and oa_info.get("url"):
                    pdf_resp = self._http_get_with_retry(client, oa_info["url"])
                    if pdf_resp and pdf_resp.status_code == 200:
                        return self._validate_pdf_bytes(pdf_resp.content)
        except Exception:
            pass
        return None

    def _fetch_unpaywall_pdf(self, client: httpx.Client, doi: str) -> bytes | None:
        try:
            api_url = f"https://api.unpaywall.org/v2/{doi}?email={self.email}"
            resp = self._http_get_with_retry(client, api_url)
            if resp and resp.status_code == 200:
                data = resp.json()
                best = data.get("best_oa_location") or {}
                pdf_url = best.get("url_for_pdf") or best.get("url")
                if pdf_url:
                    pdf_resp = self._http_get_with_retry(client, pdf_url)
                    if pdf_resp and pdf_resp.status_code == 200:
                        return self._validate_pdf_bytes(pdf_resp.content)
        except Exception:
            pass
        return None

    def _fetch_europe_pmc_pdf(self, client: httpx.Client, doi: str) -> bytes | None:
        try:
            api_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json"
            resp = self._http_get_with_retry(client, api_url)
            if resp and resp.status_code == 200:
                data = resp.json()
                results = (data.get("resultList") or {}).get("result") or []
                if results:
                    pmcid = results[0].get("pmcid")
                    if pmcid:
                        pmc_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
                        pdf_resp = self._http_get_with_retry(client, pmc_url)
                        if pdf_resp and pdf_resp.status_code == 200:
                            return self._validate_pdf_bytes(pdf_resp.content)
        except Exception:
            pass
        return None

    def _fetch_landing_page_meta_pdf(self, client: httpx.Client, url: str) -> bytes | None:
        try:
            resp = self._http_get_with_retry(client, url)
            if resp and resp.status_code == 200:
                html = resp.text
                meta_match = re.search(r'<meta\s+name=["\']citation_pdf_url["\']\s+content=["\'](.*?)["\']', html, re.I)
                if meta_match:
                    pdf_url = meta_match.group(1).strip()
                    pdf_resp = self._http_get_with_retry(client, pdf_url)
                    if pdf_resp and pdf_resp.status_code == 200:
                        return self._validate_pdf_bytes(pdf_resp.content)
        except Exception:
            pass
        return None
