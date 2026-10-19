from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class WorkspaceCreate(BaseModel):
    topic: str
    max_papers: int = 25


class DiscoverRequest(BaseModel):
    max_papers: int = 25


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    status: str
    expanded_queries: str = "[]"
    created_at: datetime
    paper_count: int = 0


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int | None = None
    title: str
    authors: str = ""
    abstract: str = ""
    year: int | None = None
    source_type: str = "user_uploaded"
    doi: str | None = None
    external_id: str | None = None
    citation_count: int = 0
    venue: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    tldr: str | None = None
    is_user_paper: bool = False


class PaperUpdate(BaseModel):
    title: str
    authors: str = ""
    abstract: str = ""
    year: int | None = None
    source_type: str = "user_uploaded"
    doi: str | None = None
    venue: str | None = None


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int | None = None
    source_paper_id: int
    target_paper_id: int
    edge_type: str
    relation_label: str | None = None
    confidence: float = 1.0


class GraphOut(BaseModel):
    papers: list[PaperOut]
    edges: list[EdgeOut]
    workspace_id: int | None = None


class PaperFactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_id: int
    workspace_id: int | None = None
    task: str = ""
    method: str = ""
    dataset: str = ""
    population: str = ""
    metric: str = ""
    result_summary: str = ""
    limitation: str = ""
    future_work: str = ""
    evidence_sentence: str = ""
    confidence: float = 1.0


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: int | None = None
    type: str
    status: str
    progress: float
    message: str = ""
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class UploadOut(BaseModel):
    paper: PaperOut
    citation_edges: int
    similarity_edges: int
    saved_path: str
    workspace_id: int | None = None


class RelatedRequest(BaseModel):
    paper_id: int
    hops: int = 2
    mode: str = "bfs"
    workspace_id: int | None = None


class ExplainRequest(BaseModel):
    source_id: int
    target_id: int
    workspace_id: int | None = None


class ChatRequest(BaseModel):
    question: str
    workspace_id: int | None = None


class ChainRequest(BaseModel):
    paper_ids: list[int] | None = None
    topic: str | None = None
    days: int = 5
    workspace_id: int | None = None


class SQLQueryRequest(BaseModel):
    query: str


class SQLQueryResponse(BaseModel):
    query: str
    execution_time_ms: float
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
