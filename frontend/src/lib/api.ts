export type Paper = {
  id: number;
  title: string;
  authors: string;
  abstract: string;
  year: number | null;
  source_type: string;
};

export type Edge = {
  id: number;
  source_paper_id: number;
  target_paper_id: number;
  edge_type: string;
  relation_label: string | null;
  confidence: number;
};

export type PaperUpdate = Pick<Paper, "title" | "authors" | "abstract" | "year" | "source_type">;

export type DBColumn = {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
};

export type DBForeignKey = {
  constrained_columns: string[];
  referred_table: string;
  referred_columns: string[];
};

export type DBTableInfo = {
  table_name: string;
  row_count: number;
  columns: DBColumn[];
  foreign_keys: DBForeignKey[];
};

export type DBStatus = {
  engine: string;
  is_sqlite: boolean;
  database_url_masked: string;
  total_tables: number;
  total_records: number;
  tables: DBTableInfo[];
  pool_status: any;
};

export type SQLQueryResult = {
  query: string;
  execution_time_ms: number;
  columns: string[];
  rows: Record<string, string | null>[];
  row_count: number;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export const api = {
  papers: () => request<Paper[]>("/papers"),
  updatePaper: (paperId: number, payload: PaperUpdate) =>
    request<Paper>(`/papers/${paperId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deletePaper: (paperId: number) =>
    request<{ ok: boolean; deleted_paper_id: number }>(`/papers/${paperId}`, {
      method: "DELETE",
    }),
  graph: () => request<{ papers: Paper[]; edges: Edge[] }>("/graph"),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ paper: Paper; citation_edges: number; similarity_edges: number; saved_path: string }>("/upload", {
      method: "POST",
      body,
    });
  },
  explain: (source_id: number, target_id: number) =>
    request<{ path: any[]; explanation: string }>("/explain", {
      method: "POST",
      body: JSON.stringify({ source_id, target_id }),
    }),
  related: (paper_id: number, hops: number, mode: "bfs" | "dfs") =>
    request<Paper[]>("/related", {
      method: "POST",
      body: JSON.stringify({ paper_id, hops, mode }),
    }),
  gaps: () =>
    request<{
      gap_suggestions: { cluster: number; paper_count: number; candidate_papers: string[]; suggestion: string }[];
      missing_citations: { paper: string; may_need_citation: string; similarity: number }[];
    }>("/gaps"),
  evolution: (topic: string, days: number) =>
    request<{
      papers: { id: number; title: string; year: number | null; authors: string; abstract: string; contribution: string }[];
      steps: { from: string; to: string; solved: string; left_open: string; next_fixed: string; note: string }[];
      reading_plan: { day: number; papers: string[] }[];
      literature_review: string;
    }>("/evolution", { method: "POST", body: JSON.stringify({ topic, days }) }),
  chat: (question: string) =>
    request<{ answer: string; citations: string[] }>("/chat", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  dbStatus: () => request<DBStatus>("/db/status"),
  dbQuery: (query: string) =>
    request<SQLQueryResult>("/db/query", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
};
