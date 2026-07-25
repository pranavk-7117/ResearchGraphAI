from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaperKeyword(Base):
    __tablename__ = "paper_keywords"
    __table_args__ = (UniqueConstraint("paper_id", "keyword_id"),)

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    authors: Mapped[str] = mapped_column(Text, default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="user_uploaded")
    full_text: Mapped[str] = mapped_column(Text, default="")
    whole_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)

    keywords: Mapped[list["Keyword"]] = relationship(
        secondary="paper_keywords", back_populates="papers"
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
    source_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    target_paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    edge_type: Mapped[str] = mapped_column(String(40), index=True)
    relation_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class PaperChunk(Base):
    __tablename__ = "paper_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(Text)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    cited_paper_ids: Mapped[str] = mapped_column(Text, default="")
