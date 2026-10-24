"""
Abstract base class and data structures for academic source clients.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawCandidatePaper:
    source: str
    external_id: str
    title: str
    abstract: str | None = None
    authors: list[dict[str, str]] = field(default_factory=list)
    year: int | None = None
    date: str | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    oa_status: str | None = None
    oa_pdf_url: str | None = None
    license: str | None = None
    citation_count: int = 0
    raw_references: list[str] = field(default_factory=list)
    metadata_only: bool = False


class AcademicSourceClient(ABC):
    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 25,
        year_min: int | None = None,
        year_max: int | None = None,
        oa_only: bool = False,
    ) -> list[RawCandidatePaper]:
        """Search the academic source and return normalized candidate records."""
        pass
