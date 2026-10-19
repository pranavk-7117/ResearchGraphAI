export type Workspace = {
  id: number;
  topic: string;
  status: string;
  expanded_queries: string;
  created_at: string;
  paper_count: number;
};

export type WorkspaceCreate = {
  topic: string;
  max_papers?: number;
};

export type Job = {
  id: string;
  workspace_id: number | null;
  type: string;
  status: string;
  progress: number;
  message: string;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type Paper = {
  id: number;
  workspace_id: number | null;
  title: string;
  authors: string;
  abstract: string;
  year: number | null;
  source_type: string;
  doi: string | null;
  citation_count: number;
  venue: string | null;
  url: string | null;
  pdf_url: string | null;
  tldr: string | null;
  is_user_paper: boolean;
};

export type Edge = {
  id: number;
  workspace_id: number | null;
  source_paper_id: number;
  target_paper_id: number;
  edge_type: string;
  relation_label: string | null;
  confidence: number;
};

export type PaperUpdate = Pick<Paper, "title" | "authors" | "abstract" | "year" | "source_type"> & {
  doi?: string | null;
  venue?: string | null;
};

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

export type TopicItem = {
  topic: string;
  count: number;
};

export type SamplePaperItem = {
  filename: string;
  title: string;
  size_bytes: number;
  relative_path: string;
  absolute_path: string;
};

export type SampleDomainItem = {
  domain_name: string;
  folder_name: string;
  paper_count: number;
  papers: SamplePaperItem[];
};

export type SamplePapersResponse = {
  domains: SampleDomainItem[];
  total_papers: number;
  directory: string;
};

export type GapSuggestion = {
  cluster: number;
  topic: string;
  opportunity_type: string;
  paper_count: number;
  edge_count: number;
  average_degree: number;
  coverage_score: number;
  weak_edge_types: string[];
  candidate_papers: string[];
  bridge_candidates: string[];
  research_questions: string[];
  next_steps: string[];
  suggestion: string;
};

export type GapsResponse = {
  gap_suggestions: GapSuggestion[];
  missing_citations: { paper: string; may_need_citation: string; similarity: number }[];
};

export type EvolutionResponse = {
  papers: { id: number; title: string; year: number | null; authors: string; abstract: string; contribution: string }[];
  steps: { from: string; to: string; solved: string; left_open: string; next_fixed: string; note: string }[];
  reading_plan: { day: number; papers: string[] }[];
  literature_review: string;
};

export type CompareResponse = {
  user_paper: {
    id: number;
    title: string;
    authors: string;
    year: number | null;
    abstract: string;
    contribution: string;
    limitation: string;
  };
  novelty_score: number;
  novelty_formula: string;
  avg_similarity_to_corpus: number;
  nearest_neighbours_count: number;
  suggested_citations: {
    title: string;
    authors: string;
    year: number | null;
    similarity_score: number;
    reason: string;
  }[];
  comparisons: {
    neighbour_title: string;
    neighbour_year: number | null;
    neighbour_authors: string;
    similarity_score: number;
    neighbour_contribution: string;
    neighbour_limitation: string;
    user_contribution: string;
    user_limitation: string;
  }[];
  critique: string;
  scope_note: string;
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
  // Workspaces
  workspaces: () => request<Workspace[]>("/workspaces"),
  createWorkspace: (payload: WorkspaceCreate) =>
    request<Workspace>("/workspaces", { method: "POST", body: JSON.stringify(payload) }),
  getWorkspace: (id: number) => request<Workspace>(`/workspaces/${id}`),
  deleteWorkspace: (id: number) =>
    request<{ ok: boolean; deleted_workspace_id: number }>(`/workspaces/${id}`, { method: "DELETE" }),
  discoverPapers: (workspaceId: number, maxPapers = 25) =>
    request<{ job_id: string; workspace_id: number }>(`/workspaces/${workspaceId}/discover`, {
      method: "POST",
      body: JSON.stringify({ max_papers: maxPapers }),
    }),
  uploadMyPaper: (workspaceId: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ paper: Paper; citation_edges: number; similarity_edges: number; saved_path: string; workspace_id: number }>(
      `/workspaces/${workspaceId}/my-paper`,
      { method: "POST", body }
    );
  },
  compareMyPaper: (workspaceId: number) =>
    request<CompareResponse>(`/workspaces/${workspaceId}/compare`),

  // Jobs
  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),

  // Papers
  papers: (workspaceId?: number) =>
    request<Paper[]>(workspaceId != null ? `/papers?workspace_id=${workspaceId}` : "/papers"),
  updatePaper: (paperId: number, payload: PaperUpdate) =>
    request<Paper>(`/papers/${paperId}`, { method: "PUT", body: JSON.stringify(payload) }),
  deletePaper: (paperId: number) =>
    request<{ ok: boolean; deleted_paper_id: number }>(`/papers/${paperId}`, { method: "DELETE" }),

  // Graph
  graph: (workspaceId?: number) =>
    request<{ papers: Paper[]; edges: Edge[]; workspace_id: number | null }>(
      workspaceId != null ? `/graph?workspace_id=${workspaceId}` : "/graph"
    ),

  // Upload
  upload: (file: File, workspaceId?: number) => {
    const body = new FormData();
    body.append("file", file);
    if (workspaceId != null) body.append("workspace_id", String(workspaceId));
    return request<{ paper: Paper; citation_edges: number; similarity_edges: number; saved_path: string; workspace_id: number | null }>(
      "/upload",
      { method: "POST", body }
    );
  },

  explain: (source_id: number, target_id: number, workspace_id?: number) =>
    request<{ path: any[]; explanation: string }>("/explain", {
      method: "POST",
      body: JSON.stringify({ source_id, target_id, workspace_id }),
    }),
  related: (paper_id: number, hops: number, mode: "bfs" | "dfs", workspace_id?: number) =>
    request<Paper[]>("/related", {
      method: "POST",
      body: JSON.stringify({ paper_id, hops, mode, workspace_id }),
    }),

  gaps: (workspaceId?: number) =>
    request<GapsResponse>(workspaceId != null ? `/gaps?workspace_id=${workspaceId}` : "/gaps"),

  evolution: (topic: string, days: number, workspace_id?: number) =>
    request<EvolutionResponse>("/evolution", {
      method: "POST",
      body: JSON.stringify({ topic, days, workspace_id }),
    }),

  chat: (question: string, workspace_id?: number) =>
    request<{ answer: string; citations: string[] }>("/chat", {
      method: "POST",
      body: JSON.stringify({ question, workspace_id }),
    }),

  topics: () => request<TopicItem[]>("/topics"),
  samplePapers: () => request<SamplePapersResponse>("/sample-papers"),
  dbStatus: () => request<DBStatus>("/db/status"),
  dbQuery: (query: string) =>
    request<SQLQueryResult>("/db/query", { method: "POST", body: JSON.stringify({ query }) }),
};
