from typing import Any
from pydantic import BaseModel


class PaperOut(BaseModel):
    id: int
    title: str
    authors: str
    abstract: str
    year: int | None
    source_type: str

    class Config:
        from_attributes = True


class PaperUpdate(BaseModel):
    title: str
    authors: str = ""
    abstract: str = ""
    year: int | None = None
    source_type: str = "user_uploaded"


class EdgeOut(BaseModel):
    id: int
    source_paper_id: int
    target_paper_id: int
    edge_type: str
    relation_label: str | None
    confidence: float

    class Config:
        from_attributes = True


class GraphOut(BaseModel):
    papers: list[PaperOut]
    edges: list[EdgeOut]


class UploadOut(BaseModel):
    paper: PaperOut
    citation_edges: int
    similarity_edges: int
    saved_path: str


class RelatedRequest(BaseModel):
    paper_id: int
    hops: int = 2
    mode: str = "bfs"


class ExplainRequest(BaseModel):
    source_id: int
    target_id: int


class ChatRequest(BaseModel):
    question: str


class ChainRequest(BaseModel):
    paper_ids: list[int] | None = None
    topic: str | None = None
    days: int = 5


class SQLQueryRequest(BaseModel):
    query: str


class SQLQueryResponse(BaseModel):
    query: str
    execution_time_ms: float
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
