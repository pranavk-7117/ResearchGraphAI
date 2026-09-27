import re
from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import EmbeddingService, cosine_similarity, decode_embedding
from app.services.llm import LLMService
from app.services.research_graph import ResearchGraph
from app.services.vector_store import VectorStore


def build_graph(db: Session) -> ResearchGraph:
    graph = ResearchGraph()
    for paper in db.query(models.Paper).all():
        graph.add_paper(paper.id)
    for edge in db.query(models.Edge).all():
        graph.add_edge(
            edge.source_paper_id,
            edge.target_paper_id,
            edge.edge_type,
            edge.relation_label,
            edge.confidence,
        )
    return graph


class FeatureService:
    def __init__(self) -> None:
        self.llm = LLMService()
        self.embeddings = EmbeddingService()
        self.vector_store = VectorStore()

    def related_papers(self, db: Session, paper_id: int, hops: int, mode: str) -> list[models.Paper]:
        graph = build_graph(db)
        ids = graph.dfs(paper_id)[1:] if mode == "dfs" else graph.bfs(paper_id, hops)
        if not ids:
            return []
        papers = db.query(models.Paper).filter(models.Paper.id.in_(ids)).all()
        by_id = {paper.id: paper for paper in papers}
        return [by_id[pid] for pid in ids if pid in by_id]

    def explain_connection(self, db: Session, source_id: int, target_id: int) -> dict:
        graph = build_graph(db)
        path = graph.shortest_path(source_id, target_id)
        papers = {paper.id: paper for paper in db.query(models.Paper).all()}
        path_rows = [
            {
                "from": edge.source_id,
                "to": edge.target_id,
                "from_title": papers[edge.source_id].title,
                "to_title": papers[edge.target_id].title,
                "edge_type": edge.edge_type,
                "label": edge.relation_label,
                "confidence": edge.confidence,
            }
            for edge in path
            if edge.source_id in papers and edge.target_id in papers
        ]
        sentence = self.llm.complete("Turn this path into one sentence.", str(path_rows)) if path_rows else ""
        return {"path": path_rows, "explanation": sentence}

    def gap_suggestions(self, db: Session) -> list[dict]:
        graph = build_graph(db)
        papers = {paper.id: paper for paper in db.query(models.Paper).all()}
        degree: dict[int, int] = defaultdict(int)
        for edge in db.query(models.Edge).all():
            degree[edge.source_paper_id] += 1
            degree[edge.target_paper_id] += 1

        suggestions: list[dict] = []
        for index, component in enumerate(graph.connected_components(), start=1):
            cluster_papers = [papers[pid] for pid in component if pid in papers]
            if not cluster_papers:
                continue
            low_degree = sorted(cluster_papers, key=lambda paper: degree[paper.id])[:2]
            cluster_edges = [
                edge
                for edge in db.query(models.Edge).all()
                if edge.source_paper_id in component and edge.target_paper_id in component
            ]
            topic_terms = self._topic_terms(cluster_papers)
            weak_edge_types = self._weak_edge_types(cluster_edges, topic_terms)
            candidate_questions = self._gap_questions(topic_terms, weak_edge_types)
            bridge_candidates = self._bridge_candidates(cluster_papers, degree)
            suggestion = self._cluster_gap_summary(topic_terms, weak_edge_types, low_degree)
            average_degree = round(sum(degree[paper.id] for paper in cluster_papers) / len(cluster_papers), 2)
            opportunity_type = self._opportunity_type(topic_terms)
            suggestions.append(
                {
                    "cluster": index,
                    "topic": " + ".join(topic_terms[:2]).title(),
                    "opportunity_type": opportunity_type,
                    "paper_count": len(cluster_papers),
                    "edge_count": len(cluster_edges),
                    "average_degree": average_degree,
                    "coverage_score": min(100, round((average_degree / 10) * 100)),
                    "weak_edge_types": weak_edge_types,
                    "candidate_papers": [paper.title for paper in low_degree],
                    "bridge_candidates": [paper.title for paper in bridge_candidates],
                    "research_questions": candidate_questions,
                    "next_steps": self._next_steps(topic_terms, weak_edge_types, bridge_candidates),
                    "suggestion": suggestion,
                }
            )
        return suggestions

    def missing_citations(self, db: Session) -> list[dict]:
        papers = db.query(models.Paper).all()
        citation_pairs = {
            (edge.source_paper_id, edge.target_paper_id)
            for edge in db.query(models.Edge).filter(models.Edge.edge_type == "citation")
        }
        flags = []
        for newer in papers:
            for older in papers:
                if newer.id == older.id or not newer.year or not older.year or newer.year <= older.year:
                    continue
                score = cosine_similarity(
                    decode_embedding(newer.whole_embedding), decode_embedding(older.whole_embedding)
                )
                if score > 0.88 and (newer.id, older.id) not in citation_pairs:
                    flags.append(
                        {
                            "paper": newer.title,
                            "may_need_citation": older.title,
                            "similarity": round(score, 3),
                        }
                    )
        return flags

    def evolution_chain(self, db: Session, paper_ids: list[int] | None, topic: str | None, days: int) -> dict:
        query = db.query(models.Paper)
        if paper_ids:
            papers = query.filter(models.Paper.id.in_(paper_ids)).all()
        elif topic:
            topic_aliases = self._topic_aliases(topic)
            papers = (
                query.join(models.Paper.keywords)
                .filter(models.Keyword.text.in_(topic_aliases))
                .distinct()
                .all()
            )
            if not papers:
                papers = query.filter(
                    or_(models.Paper.title.ilike(f"%{topic}%"), models.Paper.abstract.ilike(f"%{topic}%"))
                ).all()
        else:
            papers = query.all()

        graph = build_graph(db)
        ordered_ids = graph.topo_sort_extends_chain([paper.id for paper in papers])
        by_id = {paper.id: paper for paper in papers}
        ordered = [by_id[pid] for pid in ordered_ids if pid in by_id]
        if not ordered:
            ordered = sorted(papers, key=lambda paper: (paper.year or 9999, paper.title))
        else:
            ordered = sorted(ordered, key=lambda paper: (paper.year or 9999, paper.title))

        steps = []
        for left, right in zip(ordered, ordered[1:]):
            steps.append(self._evolution_step(left, right))
        reading_plan = self._reading_plan(ordered, days)
        review = self._literature_review(ordered, topic)
        return {
            "papers": [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "year": paper.year,
                    "authors": paper.authors,
                    "abstract": paper.abstract,
                    "contribution": self._paper_contribution(paper),
                }
                for paper in ordered
            ],
            "steps": steps,
            "reading_plan": reading_plan,
            "literature_review": review,
        }

    def rag_chat(self, db: Session, question: str) -> dict:
        """
        Grounded, anti-hallucination RAG question answering.
        Combines semantic chunk retrieval, title/abstract lexical matching,
        and LLM completion strictly constrained to retrieved evidence.
        """
        clean_question = question.strip()
        if not clean_question:
            return {"answer": "Please ask a question about the research papers.", "citations": []}

        # 1. Vector similarity search over chunks
        q_embedding = self.embeddings.embed(clean_question)
        chunks = db.query(models.PaperChunk).all()
        chunk_hits = self.vector_store.search(chunks, q_embedding, limit=8)

        # 2. Keyword/SQL match over paper titles and abstracts
        keywords = [w for w in re.findall(r"\w+", clean_question.lower()) if len(w) > 3]
        sql_filters = []
        for kw in keywords[:3]:
            sql_filters.append(models.Paper.title.ilike(f"%{kw}%"))
            sql_filters.append(models.Paper.abstract.ilike(f"%{kw}%"))

        matched_papers = []
        if sql_filters:
            matched_papers = db.query(models.Paper).filter(or_(*sql_filters)).limit(6).all()

        # 3. Assemble retrieved evidence context
        cited_papers_map: dict[int, models.Paper] = {}
        context_blocks: list[str] = []

        # Add top relevant chunks (filter out low similarity)
        for score, chunk in chunk_hits:
            if score < 0.15 and len(context_blocks) >= 2:
                continue
            paper = db.get(models.Paper, chunk.paper_id)
            if paper:
                cited_papers_map[paper.id] = paper
                context_blocks.append(f"[{paper.title} (Year: {paper.year or 'N/A'}) - Passage]:\n{chunk.text}")
            if len(context_blocks) >= 5:
                break

        # Supplement with paper abstracts
        for paper in matched_papers:
            if paper.id not in cited_papers_map and paper.abstract:
                cited_papers_map[paper.id] = paper
                context_blocks.append(f"[{paper.title} (Year: {paper.year or 'N/A'}) - Abstract]:\n{paper.abstract}")
            if len(context_blocks) >= 7:
                break

        # Guard against zero-evidence hallucination
        if not context_blocks:
            return {
                "answer": (
                    f"No directly relevant research papers or excerpts were found in the database to answer '{clean_question}'. "
                    "Try querying topics indexed in the database (such as retrieval, RAG, knowledge graphs, gap analysis, or evolution) "
                    "or upload new PDFs in the Upload tab."
                ),
                "citations": [],
            }

        context_text = "\n\n".join(context_blocks)

        prompt = (
            "You are an academic research assistant for a literature discovery system. "
            "Answer the question accurately using ONLY the research evidence provided in the context below.\n\n"
            "Rules:\n"
            "1. Answer strictly based on what is stated in the context. Do NOT invent claims, methods, datasets, or citations.\n"
            "2. Whenever mentioning a finding, method, or conclusion, cite the paper in brackets, e.g. [Title of Paper].\n"
            "3. If the context does not contain enough information to fully answer the question, state what is known and clarify what is missing.\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {clean_question}"
        )

        # Call LLM service (OpenAI / Gemini / Groq / dynamic local grounded synthesis)
        answer = self.llm.complete(prompt, context=context_text)

        # Record conversation in chat history
        cited_paper_titles = [paper.title for paper in cited_papers_map.values()]
        db.add(
            models.ChatHistory(
                question=clean_question,
                answer=answer,
                cited_paper_ids=",".join(str(pid) for pid in cited_papers_map.keys()),
            )
        )
        db.commit()

        return {"answer": answer, "citations": cited_paper_titles}

    def _paper_contribution(self, paper: models.Paper) -> str:
        """Dynamically extract paper contribution from abstract or title without hardcoded dictionaries."""
        text = f"{paper.title}. {paper.abstract}".strip()
        sentences = re.split(r"(?<=[.!?])\s+", paper.abstract)

        # Look for explicit contribution sentence in abstract
        contrib_patterns = [
            r"\b(we propose|we introduce|we present|in this paper we|this work presents|our approach|we develop)\b",
            r"\b(demonstrates that|results indicate|we design|we show that|proposes a method)\b",
        ]
        for pattern in contrib_patterns:
            for s in sentences:
                if re.search(pattern, s, re.I):
                    clean_s = s.strip()
                    if 15 < len(clean_s) < 300:
                        return clean_s

        if sentences and len(sentences[0].strip()) > 15:
            return sentences[0].strip()

        return f"Establishes methodologies and findings regarding {paper.title.lower()}."

    def _limitation(self, paper: models.Paper) -> str:
        """Dynamically extract limitations or open questions without hardcoded dictionaries."""
        sentences = re.split(r"(?<=[.!?])\s+", paper.abstract)
        limitation_patterns = [
            r"\b(however|challenge|limit|future work|remains open|trade-off|bottleneck|open problem)\b",
            r"\b(unaddressed|requires further|remains unclear|evaluating under)\b",
        ]
        for pattern in limitation_patterns:
            for s in sentences:
                if re.search(pattern, s, re.I):
                    clean_s = s.strip()
                    if 15 < len(clean_s) < 300:
                        return clean_s.rstrip(".")

        return f"how the findings of '{paper.title}' generalize across diverse real-world benchmarks and edge conditions"

    def _evolution_step(self, left: models.Paper, right: models.Paper) -> dict:
        left_contrib = self._paper_contribution(left)
        left_limit = self._limitation(left)
        right_contrib = self._paper_contribution(right)
        return {
            "from": left.title,
            "to": right.title,
            "solved": left_contrib,
            "left_open": left_limit,
            "next_fixed": right_contrib,
            "note": (
                f"{left.title} addressed {left_contrib.lower().rstrip('.')}. "
                f"It left open {left_limit.lower().rstrip('.')}. "
                f"{right.title} moves the chain forward by {right_contrib.lower().rstrip('.')}."
            ),
        }

    def _reading_plan(self, papers: list[models.Paper], days: int) -> list[dict]:
        days = max(days, 1)
        plan = [{"day": day, "papers": []} for day in range(1, days + 1)]
        for index, paper in enumerate(papers):
            plan[index % days]["papers"].append(paper.title)
        return plan

    def _literature_review(self, papers: list[models.Paper], topic: str | None) -> str:
        if not papers:
            return "No papers matched this topic."
        first = papers[0]
        last = papers[-1]
        terms = self._topic_terms(papers)
        first_contribution = self._paper_contribution(first).rstrip(".")
        last_contribution = self._paper_contribution(last).rstrip(".")
        unresolved = self._limitation(last if len(papers) == 1 else papers[-2]).rstrip(".")
        return (
            f"The {topic or 'selected'} literature begins with {first.title}, which {first_contribution}. "
            f"Across {len(papers)} papers, the lineage develops core themes around {', '.join(terms[:3])}. "
            f"It progresses toward {last.title}, which {last_contribution}. "
            f"A central unresolved question is {unresolved}."
        )

    def _topic_aliases(self, topic: str) -> list[str]:
        normalized = topic.strip().lower()
        aliases = {
            "retrieval": ["retrieval"],
            "search": ["retrieval"],
            "rag": ["rag"],
            "generation": ["rag"],
            "retrieval augmented generation": ["rag"],
            "knowledge graph": ["knowledge graph", "knowledge-graph"],
            "knowledge graph interface": ["knowledge graph", "knowledge-graph", "interface"],
            "graph": ["knowledge graph", "knowledge-graph"],
            "gap": ["gap suggestions", "gap-analysis"],
            "gaps": ["gap suggestions", "gap-analysis"],
            "gap analysis": ["gap suggestions", "gap-analysis"],
            "evolution": ["evolution chain", "evolution"],
            "evolution chain": ["evolution chain", "evolution"],
            "timeline": ["evolution chain", "evolution"],
            "recommendation": ["recommendation"],
            "recommendations": ["recommendation"],
            "paper recommendation": ["recommendation"],
            "summarization": ["summarization"],
            "summary": ["summarization"],
            "metadata": ["metadata extraction", "metadata"],
            "metadata extraction": ["metadata extraction", "metadata"],
            "evaluation": ["evaluation"],
            "missing citation detection": ["evaluation"],
            "interface": ["interface"],
            "ui": ["interface"],
        }
        return aliases.get(normalized, [normalized])

    def _topic_terms(self, papers: list[models.Paper]) -> list[str]:
        terms = [
            "retrieval",
            "rag",
            "knowledge graph",
            "interface",
            "gap",
            "evaluation",
            "evolution",
            "summarization",
            "recommendation",
            "metadata",
            "citation",
            "reading plan",
        ]
        text = " ".join(f"{paper.title} {paper.abstract}" for paper in papers).lower()
        scored = sorted(
            [(text.count(term), term) for term in terms if text.count(term) > 0],
            reverse=True,
        )
        return [term for _, term in scored[:4]] or ["literature discovery"]

    def _weak_edge_types(self, edges: list[models.Edge], topic_terms: list[str]) -> list[str]:
        counts = defaultdict(int)
        for edge in edges:
            counts[edge.edge_type] += 1
        weak = []
        if counts["citation"] < 10:
            weak.append("citation evidence")
        if counts["similarity"] < 10:
            weak.append("comparative evaluation")
        if counts["semantic_relation"] < 10:
            weak.append("method lineage")
        if weak:
            return weak
        topic = " ".join(topic_terms[:2])
        if "retrieval" in topic or "rag" in topic:
            return ["live user studies", "domain-shift benchmarks", "latency and cost reporting"]
        if "knowledge graph" in topic or "interface" in topic:
            return ["usability evidence", "graph readability at scale", "longitudinal researcher workflows"]
        if "gap" in topic or "evaluation" in topic:
            return ["human validation", "false-positive analysis", "replication protocols"]
        if "evolution" in topic or "summarization" in topic:
            return ["timeline evaluation", "claim-level factuality", "pedagogical sequencing evidence"]
        if "metadata" in topic or "recommendation" in topic:
            return ["cold-start evaluation", "metadata error robustness", "diversity and fairness checks"]
        return ["cross-dataset validation"]

    def _bridge_candidates(self, papers: list[models.Paper], degree: dict[int, int]) -> list[models.Paper]:
        if len(papers) <= 2:
            return papers
        sorted_by_degree = sorted(papers, key=lambda paper: degree[paper.id])
        return [sorted_by_degree[0], sorted_by_degree[-1]]

    def _cluster_gap_summary(
        self,
        topic_terms: list[str],
        weak_edge_types: list[str],
        low_degree: list[models.Paper],
    ) -> str:
        topic = " and ".join(topic_terms[:2])
        weak = ", ".join(weak_edge_types[:2])
        candidates = " and ".join(paper.title for paper in low_degree[:2])
        return (
            f"Potential gap: this {topic} cluster has enough related work to show a theme, "
            f"but weak coverage around {weak}. The sparsely connected papers, {candidates}, "
            "look like good starting points for checking whether the cluster needs stronger comparative studies, "
            "replication evidence, or clearer links between methods and deployment settings."
        )

    def _gap_questions(self, topic_terms: list[str], weak_edge_types: list[str]) -> list[str]:
        topic = " and ".join(topic_terms[:2])
        return [
            f"Which assumptions in {topic} papers have not been tested across datasets or user groups?",
            f"Can stronger {weak_edge_types[0]} links change which papers are considered central?",
            f"What evaluation would connect the low-degree papers to the cluster's dominant methods?",
        ]

    def _opportunity_type(self, topic_terms: list[str]) -> str:
        topic = " ".join(topic_terms[:2])
        if "retrieval" in topic or "rag" in topic:
            return "Evaluation gap"
        if "knowledge graph" in topic or "interface" in topic:
            return "Interaction gap"
        if "gap" in topic or "evaluation" in topic:
            return "Validation gap"
        if "evolution" in topic or "summarization" in topic:
            return "Narrative gap"
        if "metadata" in topic or "recommendation" in topic:
            return "Robustness gap"
        return "Evidence gap"

    def _next_steps(
        self,
        topic_terms: list[str],
        weak_edge_types: list[str],
        bridge_candidates: list[models.Paper],
    ) -> list[str]:
        topic = " and ".join(topic_terms[:2])
        bridge = bridge_candidates[0].title if bridge_candidates else "the most central paper"
        return [
            f"Audit papers around {bridge} for missing baselines and evaluation settings.",
            f"Create a comparison table for {topic} covering {', '.join(weak_edge_types[:2])}.",
            "Add one targeted paper or experiment that connects the low-degree papers to the cluster core.",
        ]
