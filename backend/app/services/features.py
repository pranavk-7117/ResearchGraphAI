from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import cosine_similarity, decode_embedding
from app.services.embeddings import EmbeddingService
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
        return [by_id[paper_id] for paper_id in ids if paper_id in by_id]

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
        edge_type_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for edge in db.query(models.Edge).all():
            degree[edge.source_paper_id] += 1
            degree[edge.target_paper_id] += 1
            edge_type_counts[edge.source_paper_id][edge.edge_type] += 1
            edge_type_counts[edge.target_paper_id][edge.edge_type] += 1
        suggestions: list[dict] = []
        for index, component in enumerate(graph.connected_components(), start=1):
            cluster_papers = [papers[paper_id] for paper_id in component if paper_id in papers]
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
                if score > 0.9 and (newer.id, older.id) not in citation_pairs:
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
        ordered = [by_id[paper_id] for paper_id in ordered_ids if paper_id in by_id]
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
        sql_hits = db.query(models.Paper).filter(
            or_(models.Paper.title.ilike(f"%{question}%"), models.Paper.abstract.ilike(f"%{question}%"))
        ).limit(5).all()
        topic_aliases = self._topic_aliases(self._question_focus(question.lower(), []))
        topic_hits = (
            db.query(models.Paper)
            .join(models.Paper.keywords)
            .filter(models.Keyword.text.in_(topic_aliases))
            .limit(5)
            .all()
        )
        q_embedding = self.embeddings.embed(question)
        chunks = db.query(models.PaperChunk).all()
        chunk_hits = self.vector_store.search(chunks, q_embedding, limit=5)
        cited_ids = {paper.id for paper in sql_hits}
        cited_ids.update(paper.id for paper in topic_hits)
        cited_ids.update(chunk.paper_id for _, chunk in chunk_hits[:5])
        papers = {paper.id: paper for paper in db.query(models.Paper).filter(models.Paper.id.in_(cited_ids)).all()}
        ranked_papers = self._rank_papers_for_question(question, list(papers.values()))
        answer = self._local_rag_answer(question, ranked_papers, chunk_hits)
        db.add(
            models.ChatHistory(
                question=question,
                answer=answer,
                cited_paper_ids=",".join(str(paper.id) for paper in ranked_papers),
            )
        )
        db.commit()
        return {"answer": answer, "citations": [paper.title for paper in ranked_papers]}

    def _reading_plan(self, papers: list[models.Paper], days: int) -> list[dict]:
        days = max(days, 1)
        plan = [{"day": day, "papers": []} for day in range(1, days + 1)]
        for index, paper in enumerate(papers):
            plan[index % days]["papers"].append(paper.title)
        return plan

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

    def _paper_contribution(self, paper: models.Paper) -> str:
        text = f"{paper.title} {paper.abstract}".lower()
        title = paper.title.lower()
        specific = self._specific_contribution(title)
        if specific:
            return specific
        if "citation-aware research discovery" in title:
            return "Uses citation links to surface influential and connected papers."
        if "latent semantic indexing" in title:
            return "Introduces semantic matching beyond exact keyword overlap."
        if "probabilistic ranking" in title:
            return "Frames scholarly search as ranked evidence under uncertainty."
        if "learning to rank" in title:
            return "Uses citation signals to improve result ordering."
        if "dense passage" in title:
            return "Uses embeddings to retrieve answer-bearing paper passages."
        if "hybrid sparse-dense" in title:
            return "Combines keyword and embedding retrieval for stronger coverage."
        if "query expansion" in title:
            return "Expands user queries with domain terminology and graph context."
        if "evaluating neural retrieval" in title:
            return "Adds evaluation pressure around retrieval quality in literature discovery."
        if "robust retrieval pipelines" in title:
            return "Turns retrieval methods into repeatable assistant-ready pipelines."
        if "retrieval-augmented generation" in title or "rag" in title or "generation" in title:
            return "Connects retrieved evidence to grounded answer generation."
        if "citation graph" in title or "knowledge graph" in text or "graph" in title:
            return "Adds structure through citations, semantic relations, or graph exploration."
        if "ranking" in text:
            return "Improves how relevant papers are ordered for exploration."
        if "retrieval" in text:
            return "Improves how relevant papers or passages are found."
        if "gap" in text:
            return "Turns sparse or weakly connected literature regions into research opportunities."
        if "summar" in text:
            return "Condenses multiple papers into review-ready claims and comparisons."
        if "metadata" in text or "pdf" in text:
            return "Improves ingestion quality and paper metadata reliability."
        if "recommend" in text:
            return "Suggests useful papers through user, citation, or embedding signals."
        return "Adds a focused piece to the research workflow."

    def _evolution_step(self, left: models.Paper, right: models.Paper) -> dict:
        return {
            "from": left.title,
            "to": right.title,
            "solved": self._paper_contribution(left),
            "left_open": self._limitation(left),
            "next_fixed": self._paper_contribution(right),
            "note": (
                f"{left.title} established {self._paper_contribution(left).lower()} "
                f"It left open {self._limitation(left).lower()} "
                f"{right.title} moves the chain forward by {self._paper_contribution(right).lower()}"
            ),
        }

    def _limitation(self, paper: models.Paper) -> str:
        text = f"{paper.title} {paper.abstract}".lower()
        title = paper.title.lower()
        specific = self._specific_limitation(title)
        if specific:
            return specific
        if "citation-aware research discovery" in title:
            return "whether citation networks overrepresent older or already popular work."
        if "latent semantic indexing" in title:
            return "whether semantic similarity alone captures domain-specific research intent."
        if "probabilistic ranking" in title:
            return "whether ranking assumptions hold for citation-heavy scientific search."
        if "learning to rank" in title:
            return "whether citation-based ranking overlooks new or under-cited papers."
        if "dense passage" in title:
            return "whether dense retrieval remains reliable for long, technical papers."
        if "hybrid sparse-dense" in title:
            return "how to balance lexical precision with semantic recall."
        if "query expansion" in title:
            return "whether expanded queries introduce noise or topic drift."
        if "evaluating neural retrieval" in title:
            return "which benchmarks reflect real literature discovery tasks."
        if "robust retrieval pipelines" in title:
            return "how the pipeline behaves under messy uploads and changing collections."
        if "retrieval-augmented generation" in title or "rag" in title or "generation" in text:
            return "how to prove answers stay faithful when evidence is incomplete."
        if "citation graph" in title or "knowledge graph" in text or "graph" in title:
            return "how graph structure remains readable and useful at larger scale."
        if "retrieval" in text:
            return "whether retrieval quality holds across domains, queries, and real users."
        if "gap" in text:
            return "how to validate suggested gaps without overstating uncertainty."
        if "summar" in text:
            return "how to preserve claim-level nuance across many papers."
        if "metadata" in text or "pdf" in text:
            return "how robust the pipeline is to noisy PDFs and inconsistent formats."
        if "recommend" in text:
            return "how to balance relevance, diversity, and cold-start behavior."
        return "how the method generalizes beyond its immediate setting."

    def _specific_contribution(self, title: str) -> str | None:
        rules = [
            ("retrieval-augmented generation", "Connects retrieved evidence to grounded answer generation."),
            ("grounded answer generation", "Generates answers directly from retrieved research evidence."),
            ("citation-aware rag", "Attaches citation evidence to generated scientific answers."),
            ("chunk selection", "Chooses the most useful paper passages before answer generation."),
            ("faithfulness checks", "Checks whether generated research answers stay supported by sources."),
            ("rag with structured evidence", "Organizes retrieved evidence as a graph before generation."),
            ("context window allocation", "Budgets limited context across multiple relevant papers."),
            ("auditable rag", "Makes generated answers traceable to paper-level citations."),
            ("knowledge graph construction", "Builds structured paper-concept networks from scholarly metadata."),
            ("entity linking", "Connects paper text to canonical scientific concepts and methods."),
            ("semantic relation extraction", "Labels relationships between papers beyond simple similarity."),
            ("graph-based exploration", "Turns research communities into navigable graph neighborhoods."),
            ("temporal knowledge graphs", "Adds time-aware structure for tracking topic evolution."),
            ("interactive scholarly graph", "Makes graph exploration usable through interactive visual controls."),
            ("visual analytics", "Uses visual summaries to help researchers inspect large paper collections."),
            ("node-link interfaces", "Presents scholarly relationships as readable node-link diagrams."),
            ("progressive disclosure", "Reveals graph detail gradually to reduce interface overload."),
            ("design patterns", "Organizes AI-assisted research workflows into reusable interface patterns."),
            ("explainable graph interactions", "Explains why papers are connected inside the graph UI."),
            ("reading planner interfaces", "Transforms complex paper sets into scheduled reading paths."),
            ("trust calibration", "Helps users judge when AI literature tools are reliable."),
            ("workspace design", "Combines graph, retrieval, and review tools into one research workspace."),
            ("finding research gaps", "Uses connected components to identify underexplored literature regions."),
            ("low-degree nodes", "Treats sparse graph connectivity as a signal for possible gaps."),
            ("cluster summaries", "Summarizes paper clusters to expose missing evaluation angles."),
            ("unaddressed evaluation", "Highlights evaluation settings that applied AI papers leave uncovered."),
            ("human-in-the-loop", "Adds researcher validation to gap recommendation workflows."),
            ("contradiction mining", "Finds conflicting claims that can become open research questions."),
            ("evidence clusters", "Turns related evidence groups into concrete research hypotheses."),
            ("cautious gap", "Frames gap suggestions as uncertain leads rather than definitive claims."),
            ("evaluating research assistants", "Tests research assistants for factual grounding."),
            ("citation precision", "Measures whether generated answers cite the right papers."),
            ("user studies", "Evaluates graph exploration with real researcher behavior."),
            ("stress tests", "Challenges missing citation detection under difficult cases."),
            ("coverage", "Measures whether literature review generators cover the topic adequately."),
            ("benchmark datasets", "Creates shared datasets for evaluating scientific RAG systems."),
            ("error taxonomies", "Categorizes common failures in research paper chatbots."),
            ("reproducibility", "Defines protocols that make literature AI tools easier to reproduce."),
            ("topic evolution", "Models how scientific topics change through citation chains."),
            ("topological ordering", "Orders method-extension graphs into readable lineage chains."),
            ("research lineage", "Turns lineage graphs into practical reading plans."),
            ("method progression", "Explains how one paper addresses limits left by another."),
            ("timeline summaries", "Converts paper sequences into concise timeline summaries."),
            ("detecting cycles", "Detects circular claims inside method-extension chains."),
            ("narrative literature", "Generates review narratives from structured paper chains."),
            ("pedagogical sequencing", "Orders foundational papers for easier learning."),
            ("scientific paper summarization", "Summarizes papers using section-aware document structure."),
            ("multi-document summaries", "Synthesizes multiple papers into survey-style summaries."),
            ("extractive summaries", "Pulls methods and contributions directly from paper text."),
            ("abstractive summaries", "Generates citation-grounded summaries in new wording."),
            ("comparative summaries", "Compares related papers across methods and findings."),
            ("claim-centric", "Centers summaries around claims, evidence, and limitations."),
            ("evaluation rubrics", "Defines criteria for judging scientific summaries."),
            ("controllable literature", "Lets users steer literature review paragraph generation."),
            ("graph neural networks", "Applies graph neural networks to paper recommendation."),
            ("personalized paper recommendation", "Uses reading histories for personalized suggestions."),
            ("cold-start", "Recommends papers when user history is sparse."),
            ("diversity-aware", "Balances relevance with diversity in exploration."),
            ("serendipity", "Measures whether recommendations surface useful surprises."),
            ("citation-enhanced", "Uses citation context to improve recommendations."),
            ("interactive feedback", "Learns recommendations from user feedback loops."),
            ("benchmarking scholarly", "Compares recommendation systems under shared benchmarks."),
            ("pdf metadata", "Extracts metadata from scholarly PDFs."),
            ("title and author", "Detects titles and authors in academic PDF layouts."),
            ("reference parsing", "Parses noisy reference sections from research documents."),
            ("semantic scholar matching", "Matches uploaded papers to indexed records with fuzzy search."),
            ("deduplicating", "Merges duplicate uploaded and indexed paper records."),
            ("metadata quality", "Checks metadata reliability before indexing."),
            ("recovering abstracts", "Recovers abstracts from heterogeneous PDF layouts."),
            ("ingestion pipelines", "Builds practical ingestion pipelines for literature tools."),
        ]
        for needle, value in rules:
            if needle in title:
                return value
        return None

    def _specific_limitation(self, title: str) -> str | None:
        rules = [
            ("retrieval-augmented generation", "how to prove answers stay faithful when evidence is incomplete."),
            ("grounded answer generation", "how to handle evidence conflicts without inventing unsupported claims."),
            ("citation-aware rag", "whether citation links are precise enough for claim-level verification."),
            ("chunk selection", "how to pick passages when relevant evidence is scattered across papers."),
            ("faithfulness checks", "which faithfulness errors matter most to researchers."),
            ("rag with structured evidence", "whether graph-structured evidence improves answers without adding complexity."),
            ("context window allocation", "how to allocate context fairly across long or competing papers."),
            ("auditable rag", "how much citation detail users need before answers become hard to read."),
            ("knowledge graph construction", "whether extracted graph facts remain accurate across noisy metadata sources."),
            ("entity linking", "how to resolve ambiguous concepts across disciplines."),
            ("semantic relation extraction", "whether relation labels are consistent enough for downstream reasoning."),
            ("graph-based exploration", "how to prevent large communities from becoming visually overwhelming."),
            ("temporal knowledge graphs", "whether time-aware edges capture conceptual change rather than only publication order."),
            ("interactive scholarly graph", "how well users understand graph controls during real review work."),
            ("visual analytics", "which visual encodings actually improve research decisions."),
            ("node-link interfaces", "how node-link diagrams scale beyond small paper sets."),
            ("progressive disclosure", "which details should be hidden or revealed at each step."),
            ("design patterns", "whether patterns generalize across research domains and user skill levels."),
            ("explainable graph interactions", "how to explain connections without oversimplifying evidence."),
            ("reading planner interfaces", "how to adapt plans when users skip or reorder papers."),
            ("trust calibration", "how to prevent users from overtrusting polished AI outputs."),
            ("workspace design", "how to keep multiple research tools coherent in one workflow."),
            ("finding research gaps", "how to validate that a sparse region is truly a gap."),
            ("low-degree nodes", "whether low degree reflects novelty, missing data, or irrelevance."),
            ("cluster summaries", "how to avoid hiding minority findings inside one cluster summary."),
            ("unaddressed evaluation", "which missing evaluations matter most for practical deployment."),
            ("human-in-the-loop", "how much review effort researchers will tolerate."),
            ("contradiction mining", "how to distinguish true contradictions from different assumptions."),
            ("evidence clusters", "how to rank hypotheses by feasibility and importance."),
            ("cautious gap", "how to communicate uncertainty without weakening usefulness."),
            ("evaluating research assistants", "which tasks best reflect real research work."),
            ("citation precision", "how to evaluate citations when multiple papers support a claim."),
            ("user studies", "whether lab behavior transfers to long-term literature workflows."),
            ("stress tests", "which failure modes are most common in real collections."),
            ("coverage", "how to measure coverage when topic boundaries are fuzzy."),
            ("benchmark datasets", "whether benchmarks stay current as research topics evolve."),
            ("error taxonomies", "how to turn error categories into actionable fixes."),
            ("reproducibility", "how to reproduce results when APIs, models, and corpora change."),
            ("topic evolution", "whether citation chains capture intellectual influence."),
            ("topological ordering", "how to handle cycles and contested extension claims."),
            ("research lineage", "how to personalize reading plans for different backgrounds."),
            ("method progression", "how to verify that a later paper truly fixes an earlier limitation."),
            ("timeline summaries", "how to preserve nuance in a compressed timeline."),
            ("detecting cycles", "which edge should be dropped when a cycle is ambiguous."),
            ("narrative literature", "how to avoid making a chain sound more certain than it is."),
            ("pedagogical sequencing", "how to balance historical order with learning difficulty."),
            ("scientific paper summarization", "how to keep section-level summaries faithful."),
            ("multi-document summaries", "how to avoid blending incompatible findings."),
            ("extractive summaries", "which extracted sentences best represent the paper."),
            ("abstractive summaries", "how to prevent generated summaries from adding unsupported claims."),
            ("comparative summaries", "which comparison axes matter across related papers."),
            ("claim-centric", "how to link each claim back to evidence."),
            ("evaluation rubrics", "whether rubrics predict usefulness for researchers."),
            ("controllable literature", "how much control users need without making the tool complex."),
            ("graph neural networks", "how recommendations work for new topics with sparse graph data."),
            ("personalized paper recommendation", "how to protect privacy and avoid filter bubbles."),
            ("cold-start", "how to recommend well before preferences are known."),
            ("diversity-aware", "how much diversity to trade for immediate relevance."),
            ("serendipity", "how to measure useful surprise rather than randomness."),
            ("citation-enhanced", "whether citation context disadvantages newer papers."),
            ("interactive feedback", "how quickly feedback should change recommendations."),
            ("benchmarking scholarly", "which benchmark metrics reflect researcher satisfaction."),
            ("pdf metadata", "how to handle inconsistent publisher formats."),
            ("title and author", "how to detect metadata in unusual PDF layouts."),
            ("reference parsing", "how to recover references from noisy or incomplete sections."),
            ("semantic scholar matching", "how to avoid false matches for similar titles."),
            ("deduplicating", "how to merge duplicates without losing provenance."),
            ("metadata quality", "which metadata errors most damage search and graph quality."),
            ("recovering abstracts", "how to distinguish abstracts from introductions or summaries."),
            ("ingestion pipelines", "how to keep ingestion robust without heavy infrastructure."),
        ]
        for needle, value in rules:
            if needle in title:
                return value
        return None

    def _literature_review(self, papers: list[models.Paper], topic: str | None) -> str:
        if not papers:
            return "No papers matched this topic."
        first = papers[0]
        last = papers[-1]
        terms = self._topic_terms(papers)
        first_contribution = self._paper_contribution(first).rstrip(".").lower()
        last_contribution = self._paper_contribution(last).rstrip(".").lower()
        unresolved = self._limitation(last if len(papers) == 1 else papers[-2]).rstrip(".")
        return (
            f"The {topic or 'selected'} literature begins with {first.title}, which {first_contribution}. "
            f"Across {len(papers)} papers, the chain develops themes around {', '.join(terms[:3])}. "
            f"It ends with {last.title}, shifting the focus toward {last_contribution}. "
            f"The main unresolved thread is {unresolved}."
        )

    def _local_rag_answer(
        self,
        question: str,
        cited_papers: list[models.Paper],
        chunk_hits: list[tuple[float, models.PaperChunk]],
    ) -> str:
        q = question.lower()
        if not cited_papers:
            return "I could not find matching papers in the collection for that question."
        cited_papers = self._rank_papers_for_question(question, cited_papers)
        terms = self._topic_terms(cited_papers)
        top_titles = [paper.title for paper in cited_papers[:3]]
        evidence_line = f"Evidence I used: {', '.join(top_titles)}."
        focus = self._question_focus(q, terms)

        if self._asks_definition(q) and ("knowledge graph" in q or "graph" in q):
            relation_examples = ", ".join(self._paper_contribution(paper).rstrip(".").lower() for paper in cited_papers[:3])
            return (
                "A knowledge graph in this app is a map of papers, concepts, and relationships. Papers become nodes; citation, similarity, and method-extension links become edges. "
                f"For the retrieved graph papers, the useful jobs are: {relation_examples}. "
                "That lets the interface explain why papers are connected instead of only listing search results. "
                f"{evidence_line}"
            )
        if self._asks_definition(q) and ("rag" in q or "retrieval" in q):
            return (
                "Retrieval is the search layer that finds relevant papers or chunks. RAG adds a generation layer that writes an answer from those retrieved sources and keeps citations attached. "
                f"In this collection, the retrieved work emphasizes {', '.join(self._paper_contribution(p).rstrip('.').lower() for p in cited_papers[:3])}. "
                f"{evidence_line}"
            )
        if "missing citation" in q or "citation detection" in q or ("citation" in q and ("work" in q or "detect" in q or "missing" in q)):
            return (
                "Missing citation detection is a review signal, not a final verdict. The app compares newer papers against older papers using semantic similarity, then checks whether a citation edge already exists. "
                "If the content is close, the newer paper is later in time, and no citation link is present, it becomes a candidate for human inspection. "
                "The important open issue is precision: similar papers can share background without requiring a citation. "
                f"{evidence_line}"
            )
        if "evolution" in q or "timeline" in q or "reading" in q or "chain" in q:
            ordered = sorted(cited_papers[:5], key=lambda paper: (paper.year or 9999, paper.title))
            transitions = []
            for left, right in zip(ordered, ordered[1:]):
                transitions.append(
                    f"{left.year}: {left.title} opened {self._limitation(left).rstrip('.').lower()}; "
                    f"{right.title} then {self._advance_phrase(right)}"
                )
            if transitions:
                return (
                    f"The {focus} evolution is best read as a sequence of problems being made more usable. "
                    + " ".join(transitions[:3])
                    + f" {evidence_line}"
                )
            return (
                f"The {focus} evolution should be read from foundational papers toward newer work that adds evaluation, interface support, or workflow integration. "
                f"{evidence_line}"
            )
        if "gap" in q or "underexplored" in q or "open question" in q:
            weak = self._weak_edge_types([], terms)
            candidates = ", ".join(paper.title for paper in cited_papers[:2])
            return (
                f"For {focus}, the gap is not simply that papers are missing; it is that the cluster needs stronger evidence around {', '.join(weak[:2])}. "
                f"I would inspect {candidates} first because retrieved papers like these can reveal weak links between methods, evaluation, and deployment claims. "
                f"{evidence_line}"
            )
        if "compare" in q or "difference" in q or "versus" in q or " vs " in q:
            first = cited_papers[0]
            second = cited_papers[1] if len(cited_papers) > 1 else cited_papers[0]
            return (
                f"{first.title} mainly {self._paper_contribution(first).rstrip('.').lower()}, while {second.title} mainly {self._paper_contribution(second).rstrip('.').lower()}. "
                f"The practical difference is that the first paper anchors one part of {focus}, while the second pushes a different part of the workflow or evaluation story. "
                f"{evidence_line}"
            )
        if "recommend" in q or "suggest" in q:
            return (
                f"The recommendation thread for {focus} combines graph position, user feedback, citation context, and embedding similarity. "
                f"The tradeoff is that papers can be relevant but repetitive, so good recommendations also need diversity and cold-start checks. "
                f"{evidence_line}"
            )
        if "metadata" in q or "pdf" in q or "ingestion" in q:
            return (
                "The metadata pipeline turns messy uploaded PDFs into usable records: title, authors, abstract, references, chunks, and embeddings. "
                "Its main risk is that one bad extraction can damage search, citation checks, and graph links downstream. "
                f"{evidence_line}"
            )
        return (
            f"This question is mainly about {focus}. "
            f"The strongest retrieved evidence says to focus on {self._paper_contribution(cited_papers[0]).rstrip('.').lower()}, while also checking {self._limitation(cited_papers[0]).rstrip('.').lower()}. "
            f"{evidence_line}"
        )

    def _advance_phrase(self, paper: models.Paper) -> str:
        contribution = self._paper_contribution(paper).rstrip(".").lower()
        if contribution.startswith(("adds ", "uses ", "builds ", "connects ", "turns ", "orders ", "models ")):
            return contribution
        return f"adds {contribution}"

    def _rank_papers_for_question(self, question: str, papers: list[models.Paper]) -> list[models.Paper]:
        q = question.lower()

        def score(paper: models.Paper) -> tuple[int, int, str]:
            text = f"{paper.title} {paper.abstract}".lower()
            matches = sum(1 for token in q.replace("?", " ").replace(".", " ").split() if len(token) > 3 and token in text)
            exact = 2 if paper.title.lower() in q else 0
            return (matches + exact, -(paper.year or 9999), paper.title)

        return sorted(papers, key=score, reverse=True)

    def _asks_definition(self, question: str) -> bool:
        starts = ("what is", "what are", "define", "explain what", "tell me what")
        return question.strip().startswith(starts)

    def _question_focus(self, question: str, fallback_terms: list[str]) -> str:
        focus_rules = [
            ("knowledge graph interface", ["knowledge graph", "interface"]),
            ("knowledge graph", ["knowledge graph", "graph"]),
            ("missing citation detection", ["missing citation", "citation detection"]),
            ("gap analysis", ["gap", "underexplored", "open question"]),
            ("evolution chain", ["evolution", "timeline", "reading", "chain"]),
            ("metadata extraction", ["metadata", "pdf", "ingestion"]),
            ("paper recommendation", ["recommend", "suggest"]),
            ("retrieval augmented generation", ["rag", "generation"]),
            ("retrieval", ["retrieval", "search"]),
            ("summarization", ["summary", "summarization", "summarize"]),
            ("evaluation", ["evaluation", "benchmark", "metric"]),
        ]
        for label, needles in focus_rules:
            if any(needle in question for needle in needles):
                return label
        return " and ".join(fallback_terms[:2])

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
