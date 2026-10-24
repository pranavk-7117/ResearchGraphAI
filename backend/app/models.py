"""
SQLAlchemy ORM models for ResearchGraphAI.

Structured around global deduplicated paper records, user-scoped research projects,
evidence-grounded fact extraction, real citation and semantic relations,
hierarchical clusters, research gaps, evolution chains, literature reviews,
RAG chat sessions, and durable background jobs.
"""

from datetime import datetime, timezone
from typing import Any
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# Auth & Projects
# ==============================================================================

class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Supabase auth user UUID
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    projects: Mapped[list["ResearchProject"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ResearchProject(Base):
    __tablename__ = "research_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(500), index=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="active")
    corpus_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["Profile"] = relationship(back_populates="projects")
    project_papers: Mapped[list["ProjectPaper"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    relations: Mapped[list["PaperRelation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    clusters: Mapped[list["ResearchCluster"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    gaps: Mapped[list["ResearchGap"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    evolution_transitions: Mapped[list["EvolutionTransition"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    literature_reviews: Mapped[list["LiteratureReview"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["PaperAnalysis"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["ResearchJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


# ==============================================================================
# Global Papers & Storage
# ==============================================================================

class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("doi", name="uq_papers_doi"),
        Index("ix_papers_title_hash", "title_hash"),
        Index("ix_papers_openalex_id", "openalex_id"),
        Index("ix_papers_s2_id", "s2_id"),
        Index("ix_papers_arxiv_id", "arxiv_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    openalex_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    s2_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title_hash: Mapped[str] = mapped_column(String(64), index=True)
    
    title: Mapped[str] = mapped_column(Text, index=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    oa_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    oa_pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Provenance
    source_name: Mapped[str] = mapped_column(String(50), default="unknown")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # Relationships
    project_entries: Mapped[list["ProjectPaper"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    documents: Mapped[list["PaperDocument"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    chunks: Mapped[list["PaperChunk"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    facts: Mapped[list["PaperFact"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    cited_by: Mapped[list["PaperReference"]] = relationship(
        foreign_keys="PaperReference.cited_paper_id", back_populates="cited_paper"
    )
    references: Mapped[list["PaperReference"]] = relationship(
        foreign_keys="PaperReference.citing_paper_id", back_populates="citing_paper", cascade="all, delete-orphan"
    )


class ProjectPaper(Base):
    __tablename__ = "project_papers"
    __table_args__ = (
        UniqueConstraint("project_id", "paper_id", name="uq_project_papers_project_paper"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_components: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_status: Mapped[str] = mapped_column(String(50), default="discovered")
    abstract_only: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["ResearchProject"] = relationship(back_populates="project_papers")
    paper: Mapped["Paper"] = relationship(back_populates="project_entries")


class PaperDocument(Base):
    __tablename__ = "paper_documents"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_paper_documents_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    storage_path: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(50), default="discovered")  # discovered | uploaded
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    paper: Mapped["Paper | None"] = relationship(back_populates="documents")


class PaperChunk(Base):
    __tablename__ = "paper_chunks"
    __table_args__ = (
        UniqueConstraint("paper_id", "text_hash", "embedding_model", name="uq_paper_chunks_idempotent"),
        Index(
            "ix_paper_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), default="all-MiniLM-L6-v2")
    embedding_version: Mapped[str] = mapped_column(String(50), default="1.0")

    paper: Mapped["Paper"] = relationship(back_populates="chunks")


# ==============================================================================
# References, Citations & Relations
# ==============================================================================

class PaperReference(Base):
    __tablename__ = "paper_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    citing_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    cited_paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, index=True)
    raw_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), default="api")  # api | parsed_reference_list
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    citing_paper: Mapped["Paper"] = relationship(foreign_keys=[citing_paper_id], back_populates="references")
    cited_paper: Mapped["Paper | None"] = relationship(foreign_keys=[cited_paper_id], back_populates="cited_by")


class PaperRelation(Base):
    __tablename__ = "paper_relations"
    __table_args__ = (
        UniqueConstraint("project_id", "source_id", "target_id", "relation_type", name="uq_paper_relations_edge"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(50), index=True)
    # cites | similar | same_dataset | same_method | extends | conflicts
    basis: Mapped[str] = mapped_column(String(50))
    # citation_metadata | extracted_text | embedding_similarity | llm_inference
    score: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_chunk_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    method_version: Mapped[str] = mapped_column(String(50), default="1.0")

    project: Mapped["ResearchProject"] = relationship(back_populates="relations")
    source_paper: Mapped["Paper"] = relationship(foreign_keys=[source_id])
    target_paper: Mapped["Paper"] = relationship(foreign_keys=[target_id])


# ==============================================================================
# Structured Facts & Intelligence
# ==============================================================================

class PaperFact(Base):
    __tablename__ = "paper_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Extracted fields
    research_question: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    problem: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    method: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    algorithm_or_model: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    dataset: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    limitations: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    future_work: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    claimed_contributions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    extraction_model: Mapped[str] = mapped_column(String(100), default="groq")
    abstract_only: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    paper: Mapped["Paper"] = relationship(back_populates="facts")


class ResearchCluster(Base):
    __tablename__ = "research_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    algorithm: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    version: Mapped[str] = mapped_column(String(50), default="1.0")
    label: Mapped[str] = mapped_column(String(255))
    label_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    representative_paper_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    year_distribution: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["ResearchProject"] = relationship(back_populates="clusters")
    members: Mapped[list["ClusterMember"]] = relationship(back_populates="cluster", cascade="all, delete-orphan")


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    __table_args__ = (
        UniqueConstraint("cluster_id", "paper_id", name="uq_cluster_members"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("research_clusters.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    membership_score: Mapped[float] = mapped_column(Float, default=1.0)

    cluster: Mapped["ResearchCluster"] = relationship(back_populates="members")
    paper: Mapped["Paper"] = relationship()


class ResearchGap(Base):
    __tablename__ = "research_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    corpus_version: Mapped[int] = mapped_column(Integer, default=1)
    gap_statement: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    gap_type: Mapped[str] = mapped_column(String(100))
    
    supporting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    counter_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    corpus_cannot_establish: Mapped[str] = mapped_column(Text)
    suggested_research_question: Mapped[str] = mapped_column(Text)
    suggested_validation: Mapped[str] = mapped_column(Text)
    
    score_components: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    formula_version: Mapped[str] = mapped_column(String(50), default="1.0")
    evidence_strength: Mapped[float] = mapped_column(Float, default=0.0)
    external_verification: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="candidate")
    user_feedback: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # relevant | not_relevant | already_addressed | needs_evidence | saved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["ResearchProject"] = relationship(back_populates="gaps")


class EvolutionTransition(Base):
    __tablename__ = "evolution_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    from_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    to_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    # citation | method_change | dataset_change | finding_confirms | finding_contradicts | inferred
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    basis: Mapped[str] = mapped_column(String(50))
    # citation_metadata | extracted_text | llm_inference
    corpus_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["ResearchProject"] = relationship(back_populates="evolution_transitions")
    from_paper: Mapped["Paper"] = relationship(foreign_keys=[from_paper_id])
    to_paper: Mapped["Paper"] = relationship(foreign_keys=[to_paper_id])


class LiteratureReview(Base):
    __tablename__ = "literature_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    corpus_version: Mapped[int] = mapped_column(Integer, default=1)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    verification_status: Mapped[str] = mapped_column(String(50), default="unverified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["ResearchProject"] = relationship(back_populates="literature_reviews")


class PaperAnalysis(Base):
    __tablename__ = "paper_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    uploaded_document_id: Mapped[int | None] = mapped_column(ForeignKey("paper_documents.id", ondelete="SET NULL"), nullable=True)
    paper_title: Mapped[str] = mapped_column(String(500))
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    corpus_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["ResearchProject"] = relationship(back_populates="analyses")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="Research Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped["ResearchProject"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # [{paper_id, title, page, section, quote}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(50))
    # discovery | download | extraction | embedding | analysis
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # pending | discovering | downloading | extracting | embedding | analysing | completed | completed_with_warnings | failed | cancelled
    stage: Mapped[str] = mapped_column(String(100), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    per_paper_results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    errors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    project: Mapped["ResearchProject | None"] = relationship(back_populates="jobs")
