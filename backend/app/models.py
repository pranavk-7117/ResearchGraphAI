from datetime import datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    expanded_queries: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    papers: Mapped[list["Paper"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    edges: Mapped[list["Edge"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    facts: Mapped[list["PaperFact"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    chat_history: Mapped[list["ChatHistory"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class PaperKeyword(Base):
    __tablename__ = "paper_keywords"
    __table_args__ = (UniqueConstraint("paper_id", "keyword_id"),)

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        Index(
            "ix_papers_whole_embedding_hnsw",
            "whole_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"whole_embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    authors: Mapped[str] = mapped_column(Text, default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="user_uploaded")
    full_text: Mapped[str] = mapped_column(Text, default="")
    whole_embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)

    # Extended paper attributes
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tldr: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_user_paper: Mapped[bool] = mapped_column(Boolean, default=False)

    workspace: Mapped["Workspace | None"] = relationship(back_populates="papers")
    keywords: Mapped[list["Keyword"]] = relationship(
        secondary="paper_keywords", back_populates="papers"
    )
    chunks: Mapped[list["PaperChunk"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    facts: Mapped[list["PaperFact"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    papers: Mapped[list[Paper]] = relationship(
        secondary="paper_keywords", back_populates="keywords"
    )


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    source_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    target_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    edge_type: Mapped[str] = mapped_column(String(40), index=True)
    relation_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    workspace: Mapped["Workspace | None"] = relationship(back_populates="edges")


class PaperChunk(Base):
    __tablename__ = "paper_chunks"
    __table_args__ = (
        Index(
            "ix_paper_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)

    paper: Mapped["Paper"] = relationship(back_populates="chunks")


class PaperFact(Base):
    __tablename__ = "paper_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    task: Mapped[str] = mapped_column(String(255), default="")
    method: Mapped[str] = mapped_column(String(255), default="")
    dataset: Mapped[str] = mapped_column(String(255), default="")
    population: Mapped[str] = mapped_column(String(255), default="")
    metric: Mapped[str] = mapped_column(String(255), default="")
    result_summary: Mapped[str] = mapped_column(Text, default="")
    limitation: Mapped[str] = mapped_column(Text, default="")
    future_work: Mapped[str] = mapped_column(Text, default="")
    evidence_sentence: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    paper: Mapped["Paper"] = relationship(back_populates="facts")
    workspace: Mapped["Workspace | None"] = relationship(back_populates="facts")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(50), default="discovery")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workspace: Mapped["Workspace | None"] = relationship(back_populates="jobs")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    cited_paper_ids: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    workspace: Mapped["Workspace | None"] = relationship(back_populates="chat_history")
