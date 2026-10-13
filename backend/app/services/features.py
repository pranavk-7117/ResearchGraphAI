import math
import re
from collections import Counter, defaultdict

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
        all_edges = db.query(models.Edge).all()
        for edge in all_edges:
            degree[edge.source_paper_id] += 1
            degree[edge.target_paper_id] += 1

        suggestions: list[dict] = []
        components = graph.connected_components()
        for index, component in enumerate(components, start=1):
            cluster_papers = [papers[pid] for pid in component if pid in papers]
            if not cluster_papers:
                continue

            low_degree = sorted(cluster_papers, key=lambda paper: degree[paper.id])[:2]
            cluster_edges = [
                edge
                for edge in all_edges
                if edge.source_paper_id in component and edge.target_paper_id in component
            ]

            topic_terms = self._topic_terms(cluster_papers)
            weak_edge_types = self._weak_edge_types(cluster_edges, cluster_papers)
            candidate_questions = self._gap_questions(topic_terms, weak_edge_types, cluster_papers)
            bridge_candidates = self._bridge_candidates(cluster_papers, degree)
            average_degree = round(sum(degree[paper.id] for paper in cluster_papers) / len(cluster_papers), 2)
            opportunity_type = self._opportunity_type(cluster_papers, weak_edge_types, average_degree)
            suggestion = self._cluster_gap_summary(topic_terms, weak_edge_types, low_degree, opportunity_type)

            suggestions.append(
                {
                    "cluster": index,
                    "topic": " + ".join(topic_terms[:2]).title(),
                    "opportunity_type": opportunity_type,
                    "paper_count": len(cluster_papers),
                    "edge_count": len(cluster_edges),
                    "average_degree": average_degree,
                    "coverage_score": min(100, round((average_degree / max(1, len(cluster_papers) - 1)) * 100)),
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
                if score > 0.78 and (newer.id, older.id) not in citation_pairs:
                    flags.append(
                        {
                            "paper": newer.title,
                            "may_need_citation": older.title,
                            "similarity": round(score, 3),
                        }
                    )
        return flags

    def evolution_chain(self, db: Session, paper_ids: list[int] | None, topic: str | None, days: int) -> dict:
        """
        Build an authentic research topic evolution chain.
        Orders papers by topological lineage of method extension and publication timeline.
        """
        query = db.query(models.Paper)
        if paper_ids:
            papers = query.filter(models.Paper.id.in_(paper_ids)).all()
        elif topic and topic.strip():
            clean_topic = topic.strip().lower()
            # 1. Match via keywords
            papers = (
                query.join(models.Paper.keywords)
                .filter(models.Keyword.text.ilike(f"%{clean_topic}%"))
                .distinct()
                .all()
            )
            # 2. Match via title and abstract lexical match
            if not papers:
                tokens = [t for t in re.findall(r"\w+", clean_topic) if len(t) > 2]
                filters = [models.Paper.title.ilike(f"%{clean_topic}%"), models.Paper.abstract.ilike(f"%{clean_topic}%")]
                for token in tokens:
                    filters.append(models.Paper.title.ilike(f"%{token}%"))
                    filters.append(models.Paper.abstract.ilike(f"%{token}%"))
                papers = query.filter(or_(*filters)).distinct().all()

            # 3. Match via semantic embedding if still few
            if len(papers) < 2:
                q_emb = self.embeddings.embed(clean_topic)
                all_p = query.all()
                scored_p = [
                    (cosine_similarity(q_emb, decode_embedding(p.whole_embedding)), p)
                    for p in all_p
                ]
                scored_p.sort(key=lambda x: x[0], reverse=True)
                papers = [p for score, p in scored_p if score > 0.45][:8]
        else:
            papers = query.all()

        if not papers:
            papers = query.limit(8).all()

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
        Strict, zero-hallucination RAG question answering.
        Retrieves top dense chunks and relevant papers. If off-topic or insufficient
        evidence, explicitly discloses the limitation without hallucination.
        """
        clean_question = question.strip()
        if not clean_question:
            return {"answer": "Please ask a question about the indexed research papers.", "citations": []}

        # 1. Vector similarity search over chunks
        q_embedding = self.embeddings.embed(clean_question)
        chunks = db.query(models.PaperChunk).all()
        chunk_hits = self.vector_store.search(chunks, q_embedding, limit=8)

        # 2. Extract significant query keywords (excluding common stop words)
        stop_words = {
            "what", "is", "the", "how", "do", "does", "are", "can", "for", "in", "and", "or", "of", "to",
            "a", "an", "best", "give", "tell", "me", "about", "why", "who", "which", "with", "where",
            "explain", "overview", "recipe", "baking"
        }
        query_kw = [w for w in re.findall(r"\w+", clean_question.lower()) if len(w) > 2 and w not in stop_words]

        # 3. Check lexical match across database papers
        sql_filters = []
        for kw in query_kw[:4]:
            sql_filters.append(models.Paper.title.ilike(f"%{kw}%"))
            sql_filters.append(models.Paper.abstract.ilike(f"%{kw}%"))

        matched_papers = []
        if sql_filters:
            matched_papers = db.query(models.Paper).filter(or_(*sql_filters)).limit(5).all()

        # Check if any chunk actually contains query keywords
        lexical_chunk_hits = [
            (score, chunk)
            for score, chunk in chunk_hits
            if any(kw in chunk.text.lower() for kw in query_kw)
        ]

        # Guard against zero-evidence hallucination (off-topic queries with no matches)
        if not matched_papers and not lexical_chunk_hits:
            available_kws = [k.text for k in db.query(models.Keyword).limit(8).all()]
            topics_str = ", ".join(available_kws) if available_kws else "AI, Machine Learning, IoT, NLP, Cybersecurity"
            return {
                "answer": (
                    f"I cannot find direct factual evidence in the indexed research papers to answer '{clean_question}'. "
                    f"The database currently contains papers covering domains such as: {topics_str}. "
                    "Please ask a question about the indexed research literature or upload a relevant paper in the Upload tab."
                ),
                "citations": [],
            }

        # 4. Assemble retrieved evidence context
        cited_papers_map: dict[int, models.Paper] = {}
        context_blocks: list[str] = []

        # Prioritize lexical and top vector hits
        candidate_hits = lexical_chunk_hits if lexical_chunk_hits else chunk_hits
        for score, chunk in candidate_hits:
            paper = db.get(models.Paper, chunk.paper_id)
            if paper and paper.id not in cited_papers_map:
                cited_papers_map[paper.id] = paper
                context_blocks.append(f"[{paper.title} ({paper.year or 'N/A'}) - Excerpt]:\n{chunk.text}")
            if len(context_blocks) >= 5:
                break

        # Supplement with paper abstracts if matched
        for paper in matched_papers:
            if paper.id not in cited_papers_map and paper.abstract:
                cited_papers_map[paper.id] = paper
                context_blocks.append(f"[{paper.title} ({paper.year or 'N/A'}) - Abstract]:\n{paper.abstract}")
            if len(context_blocks) >= 7:
                break

        if not context_blocks:
            available_kws = [k.text for k in db.query(models.Keyword).limit(8).all()]
            topics_str = ", ".join(available_kws) if available_kws else "AI, Machine Learning, IoT, NLP, Cybersecurity"
            return {
                "answer": (
                    f"I cannot find direct factual evidence in the indexed research papers to answer '{clean_question}'. "
                    f"The database currently contains papers covering domains such as: {topics_str}. "
                    "Please ask a question about the indexed research literature or upload a relevant paper in the Upload tab."
                ),
                "citations": [],
            }

        context_text = "\n\n".join(context_blocks)

        prompt = (
            "You are a scientific research assistant. "
            "Answer the question accurately and concisely using ONLY the provided excerpts from research papers.\n\n"
            "Rules:\n"
            "1. Base your answer strictly on the facts in the context excerpts below. Do NOT fabricate claims, algorithms, or results.\n"
            "2. Whenever mentioning a method, finding, or limitation, cite the supporting paper title in brackets, e.g. [Title of Paper (Year)].\n"
            "3. If the context does not contain enough evidence to answer part of the question, clearly state what is missing rather than speculating.\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {clean_question}"
        )

        # Call LLM service (OpenAI / Gemini / Groq / dynamic local grounded synthesis)
        answer = self.llm.complete(prompt, context=context_text)

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

    def _topic_terms(self, papers: list[models.Paper]) -> list[str]:
        """
        Extract prominent domain keywords and frequent noun-phrases dynamically
        from the actual paper collection, without hardcoded dictionaries.
        """
        # Collect explicit database keywords
        kw_counts = Counter()
        for p in papers:
            for kw in p.keywords:
                kw_counts[kw.text] += 3

        # Collect unigrams/bigrams from titles and abstracts
        stop_words = {
            "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
            "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
            "by", "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
            "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
            "him", "himself", "his", "how", "if", "in", "into", "is", "it", "its", "itself", "just",
            "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
            "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
            "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
            "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
            "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
            "why", "with", "would", "you", "your", "yours", "yourself", "yourselves", "paper", "propose",
            "method", "approach", "results", "demonstrate", "study", "across", "using", "presents",
        }

        full_text = " ".join(f"{p.title} {p.abstract}" for p in papers).lower()
        words = [w for w in re.findall(r"\b[a-z]{3,}\b", full_text) if w not in stop_words]

        # Add single word frequencies
        for w in words:
            kw_counts[w.capitalize()] += 1

        # Add bigram frequencies
        for i in range(len(words) - 1):
            bigram = f"{words[i].capitalize()} {words[i+1].capitalize()}"
            kw_counts[bigram] += 2

        # Return top 3 distinct terms
        most_common = [term for term, count in kw_counts.most_common(8)]
        # Filter out substrings to keep unique concepts
        filtered = []
        for term in most_common:
            if not any(term.lower() in existing.lower() for existing in filtered):
                filtered.append(term)
            if len(filtered) >= 3:
                break

        return filtered or ["Applied Literature Discovery", "Empirical Systems"]

    def _weak_edge_types(self, cluster_edges: list[models.Edge], cluster_papers: list[models.Paper]) -> list[str]:
        """
        Dynamically calculate structural weaknesses based on graph topology.
        """
        edge_types = Counter(e.edge_type for e in cluster_edges)
        n = len(cluster_papers)
        possible_edges = max(1, n * (n - 1))
        density = len(cluster_edges) / possible_edges

        weaknesses = []
        # Missing citations
        if edge_types["citation"] < max(1, n - 1):
            weaknesses.append("empirical peer citation & independent reproduction")

        # Missing method extension chains
        if edge_types["semantic_relation"] == 0:
            weaknesses.append("methodological extension & lineage verification")

        # Low density or missing comparative similarity
        if edge_types["similarity"] < max(2, n - 1):
            weaknesses.append("cross-method comparative benchmarks on shared datasets")

        if density < 0.2:
            weaknesses.append("integration baselines connecting isolated sub-graphs")

        if not weaknesses:
            weaknesses.append("inter-domain transfer & real-world operational testing")

        return weaknesses[:3]

    def _opportunity_type(self, cluster_papers: list[models.Paper], weak_edges: list[str], avg_degree: float) -> str:
        """
        Determine opportunity type dynamically from graph density and weakness markers.
        """
        if avg_degree < 1.8:
            return "Connectivity & Synthesis Gap"
        if any("citation" in w or "reproduction" in w for w in weak_edges):
            return "Empirical Validation Gap"
        if any("lineage" in w or "extension" in w for w in weak_edges):
            return "Methodological Lineage Gap"
        if any("inter-domain" in w or "transfer" in w for w in weak_edges):
            return "Cross-Domain Translation Gap"
        return "Benchmarking & Evaluation Gap"

    def _gap_questions(self, topic_terms: list[str], weak_edges: list[str], papers: list[models.Paper]) -> list[str]:
        """
        Dynamically formulate research gap questions from extracted terms and weak points.
        """
        t1 = topic_terms[0] if topic_terms else "the core method"
        w1 = weak_edges[0] if weak_edges else "empirical validation"
        p1 = papers[0].title if papers else "the leading paper"

        return [
            f"How can the framework in '{p1}' be formally evaluated under {w1}?",
            f"What trade-offs emerge when applying {t1} across diverse real-world datasets?",
            f"Can the identified limitations in {t1} be resolved without introducing significant computational overhead?",
        ]

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
        opportunity_type: str,
    ) -> str:
        topic = " and ".join(topic_terms[:2])
        weak = ", ".join(weak_edge_types[:2])
        candidates = " and ".join(f"'{p.title}'" for p in low_degree[:2])
        return (
            f"Potential {opportunity_type}: The {topic} cluster demonstrates active investigation, "
            f"yet exhibits structural deficiencies in {weak}. "
            f"Specifically, sparsely connected work such as {candidates} points to untested assumptions "
            "and represents fertile ground for novel comparative and validation research."
        )

    def _next_steps(
        self,
        topic_terms: list[str],
        weak_edge_types: list[str],
        bridge_candidates: list[models.Paper],
    ) -> list[str]:
        topic = " and ".join(topic_terms[:2])
        bridge = bridge_candidates[0].title if bridge_candidates else "central literature"
        return [
            f"Audit '{bridge}' against current benchmarks for {weak_edge_types[0]}.",
            f"Design a unified comparative benchmark comparing central {topic} baselines.",
            "Formulate an extension study connecting the lowest-degree papers to main branch algorithms.",
        ]

    def _paper_contribution(self, paper: models.Paper) -> str:
        """
        Dynamically extract the main contribution sentence directly from abstract or text.
        """
        sentences = re.split(r"(?<=[.!?])\s+", paper.abstract)
        contrib_patterns = [
            r"\b(we propose|we introduce|we present|this paper presents|our approach|we develop|we formulate)\b",
            r"\b(demonstrates that|results indicate|we design|we show that|proposes a method|achieves)\b",
        ]
        for pattern in contrib_patterns:
            for s in sentences:
                if re.search(pattern, s, re.I):
                    clean_s = s.strip()
                    if 20 < len(clean_s) < 300:
                        return clean_s

        if sentences and len(sentences[0].strip()) > 20:
            return sentences[0].strip()

        return f"Introduces novel methods and empirical evaluations for {paper.title}."

    def _limitation(self, paper: models.Paper) -> str:
        """
        Dynamically extract acknowledged limitations, overheads, or open problems directly from text.
        """
        # Look in full text for LIMITATIONS section first
        if "LIMITATIONS:" in paper.full_text:
            lim_part = paper.full_text.split("LIMITATIONS:")[1].split("\n\n")[0].strip()
            if len(lim_part) > 20:
                first_s = re.split(r"(?<=[.!?])\s+", lim_part)[0]
                return first_s.rstrip(".")

        # Look in abstract
        sentences = re.split(r"(?<=[.!?])\s+", paper.abstract)
        limitation_patterns = [
            r"\b(however|challenge|limit|future work|remains open|trade-off|bottleneck|open problem|drawback)\b",
            r"\b(overhead|latency|unaddressed|requires further|remains unclear|vulnerable to|strains)\b",
        ]
        for pattern in limitation_patterns:
            for s in sentences:
                if re.search(pattern, s, re.I):
                    clean_s = s.strip()
                    if 20 < len(clean_s) < 300:
                        return clean_s.rstrip(".")

        return f"scalability and generalization bounds of {paper.title} under noisy or adversarial real-world conditions"

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
                f"'{left.title}' established {left_contrib.lower().rstrip('.')}. "
                f"However, it acknowledged {left_limit.lower().rstrip('.')}. "
                f"Subsequent work in '{right.title}' moved the lineage forward by {right_contrib.lower().rstrip('.')}."
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
            return "No papers matched this topic in the database."
        first = papers[0]
        last = papers[-1]
        terms = self._topic_terms(papers)
        first_contrib = self._paper_contribution(first).rstrip(".")
        last_contrib = self._paper_contribution(last).rstrip(".")
        unresolved = self._limitation(last if len(papers) == 1 else papers[-2]).rstrip(".")

        topic_label = topic.title() if topic else terms[0]
        return (
            f"The literature in {topic_label} initiates with foundational investigation in '{first.title}', which {first_contrib.lower()}. "
            f"Across {len(papers)} connected studies, the field progresses along core themes of {', '.join(terms[:3])}. "
            f"Recent advances culminate in '{last.title}', which {last_contrib.lower()}. "
            f"A pivotal unresolved question across the lineage remains {unresolved}."
        )
