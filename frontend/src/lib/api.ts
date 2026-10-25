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
};

export type GraphEdge = {
  id: number;
  source: number;
  target: number;
  relation_type: "cites" | "similar" | string;
  basis: "citation_metadata" | "embedding_similarity" | string;
  score: number;
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
  representative_paper_ids: number[];
  year_distribution: Record<string, number>;
  member_count: number;
  members: ClusterMember[];
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
    top_external_matches?: Array<{ title: string; year: number | null; doi?: string }>;
    disclaimer?: string;
  };
  user_feedback: string | null;
  created_at: string;
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

const BASE_URL = import.meta.env.VITE_API_URL || "/api";

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
