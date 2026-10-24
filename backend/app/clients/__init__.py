from app.clients.base import AcademicSourceClient, RawCandidatePaper
from app.clients.openalex import OpenAlexClient
from app.clients.semantic_scholar import SemanticScholarClient
from app.clients.arxiv import ArxivClient

__all__ = [
    "AcademicSourceClient",
    "RawCandidatePaper",
    "OpenAlexClient",
    "SemanticScholarClient",
    "ArxivClient",
]
