"""
Pydantic Request and Response Schemas for ResearchGraphAI.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# ==============================================================================
# Health
# ==============================================================================

class HealthOut(BaseModel):
    ok: bool
    database_connected: bool
    pgvector_installed: bool
    pgvector_version: str | None = None
    engine: str


# ==============================================================================
# Projects
# ==============================================================================

class ProjectCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    filters: dict[str, Any] = Field(default_factory=dict)


class ProjectOut(BaseModel):
    id: int
    user_id: str
    topic: str
    status: str
    filters: dict[str, Any]
    corpus_version: int
    paper_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==============================================================================
# Papers & Candidates
# ==============================================================================

class PaperAuthor(BaseModel):
    name: str


class PaperOut(BaseModel):
    id: int
    doi: str | None = None
    title: str
    abstract: str | None = None
    authors: list[dict[str, Any]] = []
    year: int | None = None
    date: str | None = None
    venue: str | None = None
    url: str | None = None
    oa_status: str | None = None
    oa_pdf_url: str | None = None
    citation_count: int = 0
    source_name: str
    abstract_only: bool = True
    selected: bool = False
    processing_status: str = "discovered"
    relevance_score: float = 0.0
    score_components: dict[str, Any] = {}

    class Config:
        from_attributes = True


class CandidateSelectionRequest(BaseModel):
    paper_ids: list[int] = Field(default_factory=list)
    select_all: bool = False


# ==============================================================================
# Jobs
# ==============================================================================

class JobOut(BaseModel):
    id: str
    project_id: int | None = None
    type: str
    status: str
    stage: str
    progress: float
    warnings: list[str] = []
    errors: list[str] = []
    per_paper_results: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==============================================================================
# Graph & Relations
# ==============================================================================

class GraphNode(BaseModel):
    id: int
    title: str
    year: int | None = None
    citation_count: int = 0
    abstract_only: bool = True
    cluster_id: int | None = None
    authors_str: str = ""
    abstract: str | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    pagerank: float = 0.0


class GraphEdge(BaseModel):
    id: int
    source: int
    target: int
    relation_type: str  # cites | similar
    basis: str  # citation_metadata | embedding_similarity
    score: float


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int
    total_edges: int


# ==============================================================================
# Clusters
# ==============================================================================

class ClusterMemberOut(BaseModel):
    paper_id: int
    title: str
    year: int | None = None
    membership_score: float


class ClusterOut(BaseModel):
    id: int
    label: str
    representative_paper_ids: list[int]
    year_distribution: dict[str, int]
    member_count: int
    members: list[ClusterMemberOut] = []


# ==============================================================================
# Evolution
# ==============================================================================

class EvolutionTransitionOut(BaseModel):
    id: int
    from_paper_id: int
    from_paper_title: str
    from_paper_year: int | None = None
    to_paper_id: int
    to_paper_title: str
    to_paper_year: int | None = None
    kind: str
    explanation: str
    basis: str


class EvolutionOut(BaseModel):
    citation_timeline: list[dict[str, Any]]
    method_progression: list[dict[str, Any]]
    finding_dynamics: list[dict[str, Any]]


# ==============================================================================
# Gaps
# ==============================================================================

class GapOut(BaseModel):
    id: int
    gap_statement: str
    why_it_matters: str
    gap_type: str
    supporting_evidence: list[dict[str, Any]]
    counter_evidence: list[dict[str, Any]]
    corpus_cannot_establish: str
    suggested_research_question: str
    suggested_validation: str
    score_components: dict[str, Any]
    evidence_strength: float
    external_verification: dict[str, Any]
    user_feedback: str | None = None
    created_at: datetime


class GapFeedbackRequest(BaseModel):
    feedback: str  # relevant | not_relevant | already_addressed | needs_evidence | saved


# ==============================================================================
# Literature Review
# ==============================================================================

class LiteratureReviewOut(BaseModel):
    id: int
    corpus_version: int
    sections: list[dict[str, Any]]
    verification_status: str
    created_at: datetime


# ==============================================================================
# Chat
# ==============================================================================

class ChatRequest(BaseModel):
    question: str = Field(min_length=2)
    session_id: str | None = None
    paper_id_filter: int | None = None


class ChatCitation(BaseModel):
    ref: str
    paper_id: int
    title: str
    authors: list[dict[str, Any]] = []
    doi: str | None = None
    page: int | None = None
    section: str | None = None
    quote: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[ChatCitation] = []
    retrieved_count: int = 0


# ==============================================================================
# Uploaded Paper Analysis
# ==============================================================================

class PaperAnalysisOut(BaseModel):
    id: int
    paper_title: str
    report: dict[str, Any]
    evidence_rows: list[dict[str, Any]]
    created_at: datetime
