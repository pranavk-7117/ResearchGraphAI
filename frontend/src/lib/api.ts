/**
 * ResearchGraphAI Frontend API Client
 * Clean, type-safe integration with FastAPI backend on Supabase.
 */

export type Project = {
  id: number;
  user_id: string;
  topic: string;
  status: string;
  filters: Record<string, any>;
  corpus_version: number;
  paper_count: number;
  created_at: string;
  updated_at: string;
};

export type Paper = {
  id: number;
  doi: string | null;
  title: string;
  abstract: string | null;
  authors: Array<{ name: string }>;
  year: number | null;
  date: string | null;
  venue: string | null;
  url: string | null;
  oa_status: string | null;
  oa_pdf_url: string | null;
  citation_count: number;
  source_name: string;
  abstract_only: boolean;
  selected: boolean;
  processing_status: string;
  relevance_score: number;
  score_components: {
    total_score?: number;
    semantic_relevance?: number;
    recency_score?: number;
    citation_influence?: number;
    open_access_score?: number;
    ranking_mode?: string;
    weights?: Record<string, number>;
  };
};

export type Job = {
  id: string;
  project_id: number | null;
  type: string;
  status: string;
  stage: string;
  progress: number;
  warnings: string[];
  errors: string[];
  per_paper_results: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type GraphNode = {
  id: number;
  title: string;
  year: number | null;
  citation_count: number;
  abstract_only: boolean;
  cluster_id: number | null;
  authors_str: string;
  abstract?: string | null;
  venue?: string | null;
  doi?: string | null;
  url?: string | null;
  pagerank?: number;
  betweenness?: number;
  k_core?: number;
  burt_constraint?: number | null;
};

export type GraphEdge = {
  id: number;
  source: number;
  target: number;
  relation_type: "cites" | "similar" | "coupling" | string;
  layer?: "citation" | "coupling" | "semantic" | string;
  basis: "citation_metadata" | "embedding_similarity" | "bibliographic_coupling" | string;
  score: number;
  directed?: boolean;
  shared_references?: string[];
};

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
};

export type ClusterMember = {
  paper_id: number;
  title: string;
  year: number | null;
  membership_score: number;
};

export type Cluster = {
  id: number;
  label: string;
  algorithm?: string | null;
  params?: {
    modularity?: number | null;
    silhouette?: number | null;
    silhouette_agglomerative?: number | null;
    nmi?: number | null;
    resolution?: number;
    seed?: number;
    fallback?: string | null;
  };
  representative_paper_ids: number[];
  year_distribution: Record<string, number>;
  member_count: number;
  members: ClusterMember[];
};

export type StreamPaperItem = {
  id: number;
  title: string;
  year: number | null;
  authors_str?: string | null;
  abstract?: string | null;
  venue?: string | null;
  pub_type?: string | null;
  citation_count: number;
  doi?: string | null;
  url?: string | null;
  topic_tag?: string | null;
  key_contribution?: string | null;
  gaps_solved?: string[];
  new_aspects?: string[];
};

export type EvolutionPhase = {
  phase_num: number;
  start_year: number;
  end_year: number;
  title: string;
  description?: string | null;
  paper_count: number;
  icon?: string;
  dominant_theme?: string | null;
  papers?: StreamPaperItem[];
};

export type EvolutionTransitionItem = {
  phase_from?: number;
  phase_to?: number;
  badge?: string;
  year_range: string;
  title: string;
  description?: string | null;
  key_changes: string[];
  paper_count: number;
  kind?: string;
  papers?: StreamPaperItem[];
};

export type EvolutionFocusTrend = {
  years: number[];
  series: Array<{
    name: string;
    color: string;
    data: number[];
  }>;
};

export type AnnualMilestone = {
  year: number;
  paper_count: number;
  top_theme?: string | null;
  milestone_title: string;
  papers: StreamPaperItem[];
};

export type EvolutionData = {
  citation_timeline: Array<{
    from_paper: { id: number; title: string; year: number | null };
    to_paper: { id: number; title: string; year: number | null };
    kind: string;
    explanation: string;
    basis: string;
  }>;
  method_progression: Array<{
    from_paper: { id: number; title: string; year: number | null; method?: string; dataset?: string };
    to_paper: { id: number; title: string; year: number | null; method?: string; dataset?: string };
    kind: string;
    explanation: string;
    basis: string;
  }>;
  finding_dynamics: Array<{
    from_paper: { id: number; title: string; year: number | null };
    to_paper: { id: number; title: string; year: number | null };
    kind: string;
    explanation: string;
    basis: string;
  }>;
  phases?: EvolutionPhase[];
  transitions?: EvolutionTransitionItem[];
  focus_trends?: EvolutionFocusTrend;
  key_insights?: string[];
  time_range?: { min_year: number; max_year: number };
  total_papers?: number;
  paper_stream?: StreamPaperItem[];
  annual_milestones?: AnnualMilestone[];
  citation_backbone?: {
    global_path: Array<{ id: number; title: string; year: number | null }>;
    global_edges: Array<{
      from_paper: { id: number; title: string; year: number | null };
      to_paper: { id: number; title: string; year: number | null };
      spc: number;
    }>;
    total_spc: number;
    total_paths: number;
    key_route_paths: Array<Array<{ id: number; title: string; year: number | null }>>;
    key_route_edges: Array<{
      from_paper: { id: number; title: string; year: number | null };
      to_paper: { id: number; title: string; year: number | null };
      spc: number;
    }>;
    edge_count: number;
    min_citations: number;
    is_sparse: boolean;
    intent_pruning_status: string;
    pruned_edges_count: number;
    message: string;
  };
};

export type Gap = {
  id: number;
  gap_statement: string;
  why_it_matters: string;
  gap_type: string;
  supporting_evidence: Array<{
    paper_title?: string;
    quote?: string;
    page?: number;
    limitation_observed?: string;
  }>;
  counter_evidence: Array<{
    paper_title?: string;
    quote?: string;
    page?: number;
  }>;
  corpus_cannot_establish: string;
  suggested_research_question: string;
  suggested_validation: string;
  score_components: {
    formula?: string;
    evidence_quality?: number;
    supporting_papers_count?: number;
    counter_evidence_count?: number;
    calculated_strength?: number;
  };
  evidence_strength: number;
  external_verification: {
    searched_terms?: string;
    external_papers_found?: number;
    likely_addressed?: boolean;
    top_external_matches?: Array<{ title: string; year: number | null; doi?: string }>;
    disclaimer?: string;
  };
  matrix_cell?: {
    method: string;
    task: string;
    count: number;
    row_support: number;
    col_support: number;
    expected: number;
    pmi: number;
    hypergeom_p: number;
  } | null;
  status?: string;
  user_feedback: string | null;
  created_at: string;
};

export type GapMatrixCell = {
  method: string;
  task: string;
  count: number;
  row_support: number;
  col_support: number;
  expected: number;
  pmi: number;
  hypergeom_p: number;
  is_candidate_void: boolean;
  papers: Array<{ paper_id: number; title: string }>;
};

export type GapMatrixData = {
  methods: string[];
  tasks: string[];
  cells: GapMatrixCell[];
  candidates: GapMatrixCell[];
  total_papers: number;
  min_support: number;
};

export type LiteratureReview = {
  id: number;
  corpus_version: number;
  sections: Array<{
    title: string;
    content: string;
    cited_paper_ids: number[];
  }>;
  verification_status: string;
  created_at: string;
};

export type ChatCitation = {
  ref: string;
  paper_id: number;
  title: string;
  authors: Array<{ name: string }>;
  doi: string | null;
  page: number | null;
  section: string | null;
  quote: string;
};

export type ChatResponse = {
  session_id: string;
  answer: string;
  citations: ChatCitation[];
  retrieved_count: number;
};

export type CompletenessData = {
  project_id: number;
  total_observed: number;
  venn_breakdown: {
    singles: Record<string, number>;
    pairwise: Record<string, number>;
    triple: Record<string, number>;
    union_size: number;
  };
  best_pair: {
    sources: [string, string];
    n1: number;
    n2: number;
    overlap_m: number;
  } | null;
  lincoln_petersen_estimate: number | null;
  chapman_estimate: number | null;
  ci_95: [number, number] | null;
  estimated_coverage_pct: number | null;
  estimate_available: boolean;
  is_lower_bound: boolean;
  method: string;
  disclaimer: string;
};

export type ProjectStats = {
  project_id: number;
  corpus_version: number;
  total_papers: number;
  selected_papers: number;
  processed_papers: number;
  avg_citation_count: number;
  min_year: number | null;
  max_year: number | null;
  field_growth: Array<{ year: number; paper_count: number; total_citations: number }>;
};

export type PaperAnalysis = {
  id: number;
  paper_title: string;
  report: {
    overview?: string;
    problem?: string;
    claimed_contributions?: string[];
    methodology?: string;
    datasets_and_benchmarks?: string;
    findings?: string;
    limitations?: string;
    gap_alignment?: { status: string; explanation: string };
    semantic_distance_label?: string;
    novelty_overlap_analysis?: string;
    candidate_uncited_comparisons?: string[];
    suggested_improvements?: string[];
  };
  evidence_rows: Array<Record<string, any>>;
  created_at: string;
};

function getBaseUrl(): string {
  const envUrl = (import.meta.env.VITE_API_URL || "").trim();
  if (!envUrl) return "/api";
  const stripped = envUrl.replace(/\/+$/, "");
  return stripped.endsWith("/api") ? stripped : `${stripped}/api`;
}

const BASE_URL = getBaseUrl();

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("rg_auth_token");
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errorDetail = `Request failed with status ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  if (res.status === 204) {
    return null as T;
  }

  return res.json();
}

export const api = {
  // Projects
  projects: {
    list: () => request<Project[]>("/projects"),
    create: (topic: string, filters: Record<string, any> = {}) =>
      request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ topic, filters }),
      }),
    get: (id: number) => request<Project>(`/projects/${id}`),
    stats: (id: number) => request<ProjectStats>(`/projects/${id}/stats`),
    delete: (id: number) =>
      request<void>(`/projects/${id}`, {
        method: "DELETE",
      }),
  },

  // Discovery
  discovery: {
    trigger: (
      projectId: number,
      params: { limit?: number; ranking_mode?: string; year_min?: number; year_max?: number; oa_only?: boolean } = {}
    ) => {
      const sp = new URLSearchParams();
      if (params.limit) sp.set("limit", String(params.limit));
      if (params.ranking_mode) sp.set("ranking_mode", params.ranking_mode);
      if (params.year_min) sp.set("year_min", String(params.year_min));
      if (params.year_max) sp.set("year_max", String(params.year_max));
      if (params.oa_only !== undefined) sp.set("oa_only", String(params.oa_only));
      return request<Job>(`/projects/${projectId}/discover?${sp.toString()}`, { method: "POST" });
    },
    getCandidates: (projectId: number) => request<Paper[]>(`/projects/${projectId}/candidates`),
    completeness: (projectId: number) => request<CompletenessData>(`/projects/${projectId}/completeness`),
    selectCandidates: (projectId: number, paperIds: number[], selectAll = false) =>
      request<{ ok: boolean; selected_count: number }>(`/projects/${projectId}/select-candidates`, {
        method: "POST",
        body: JSON.stringify({ paper_ids: paperIds, select_all: selectAll }),
      }),
    triggerProcessing: (projectId: number) =>
      request<Job>(`/projects/${projectId}/process`, { method: "POST" }),
  },

  // Papers & Graph
  papers: {
    list: (projectId: number) => request<Paper[]>(`/projects/${projectId}/papers`),
  },
  graph: {
    get: (projectId: number) => request<GraphData>(`/projects/${projectId}/graph`),
    autocomplete: (projectId: number, q: string, limit = 8) =>
      request<{ query: string; results: Array<{ text: string; payload: { type: string; paper_id: number; title: string; year: number | null } }> }>(
        `/projects/${projectId}/autocomplete?q=${encodeURIComponent(q)}&limit=${limit}`
      ),
    readingPath: (projectId: number, paperId: number, n = 10, maxHops = 3) =>
      request<{
        project_id: number;
        target_paper_id: number;
        target_title: string;
        steps: Array<{ paper_id: number; step: number; hop_distance: number; pagerank: number; title: string | null; year: number | null; doi: string | null }>;
      }>(`/projects/${projectId}/reading-path?paper_id=${paperId}&n=${n}&max_hops=${maxHops}`),
  },

  // Clusters, Evolution & Gaps
  clusters: {
    get: (projectId: number) => request<Cluster[]>(`/projects/${projectId}/clusters`),
  },
  evolution: {
    get: (projectId: number) => request<EvolutionData>(`/projects/${projectId}/evolution`),
  },
  gaps: {
    get: (projectId: number) => request<Gap[]>(`/projects/${projectId}/gaps`),
    matrix: (projectId: number) => request<GapMatrixData>(`/projects/${projectId}/gap-matrix`),
    detect: (projectId: number) =>
      request<Job>(`/projects/${projectId}/gaps/detect`, { method: "POST" }),
    feedback: (gapId: number, feedback: string) =>
      request<{ ok: boolean; feedback: string }>(`/gaps/${gapId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ feedback }),
      }),
  },

  // Review & BibTeX
  review: {
    get: (projectId: number) =>
      request<LiteratureReview>(`/projects/${projectId}/literature-review`),
    generate: (projectId: number) =>
      request<LiteratureReview>(`/projects/${projectId}/literature-review`, { method: "POST" }),
    bibtex: (projectId: number) => request<{ bibtex: string }>(`/projects/${projectId}/bibtex`),
  },

  // Chat
  chat: {
    send: (projectId: number, question: string, sessionId?: string, paperIdFilter?: number) =>
      request<ChatResponse>(`/projects/${projectId}/chat`, {
        method: "POST",
        body: JSON.stringify({
          question,
          session_id: sessionId,
          paper_id_filter: paperIdFilter,
        }),
      }),
  },

  // Upload & Compare
  upload: {
    compare: (projectId: number, file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return request<PaperAnalysis>(`/projects/${projectId}/upload`, {
        method: "POST",
        body: formData,
      });
    },
    listAnalyses: (projectId: number) => request<PaperAnalysis[]>(`/projects/${projectId}/analyses`),
  },

  // Jobs
  jobs: {
    get: (jobId: string) => request<Job>(`/jobs/${jobId}`),
  },

  // Health
  health: () => request<{ ok: boolean; database_connected: boolean; pgvector_installed: boolean }>("/health"),
};
