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
  graph: () => request<{ papers: Paper[]; edges: Edge[] }>("/graph"),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{ paper: Paper; citation_edges: number; similarity_edges: number }>("/upload", {
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
};
