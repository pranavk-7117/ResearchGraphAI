from app import models
from app.database import SessionLocal, init_db
from app.services.embeddings import EmbeddingService, encode_embedding


THEMES = [
    {
        "slug": "retrieval",
        "keyword": "retrieval",
        "titles": [
            "Latent Semantic Indexing for Information Retrieval",
            "Probabilistic Ranking for Scholarly Search",
            "Learning to Rank Research Articles with Citation Signals",
            "Dense Passage Retrieval for Open-Domain Questions",
            "Hybrid Sparse-Dense Retrieval for Scientific Corpora",
            "Query Expansion with Domain Terminology Graphs",
            "Evaluating Neural Retrieval in Literature Discovery",
            "Robust Retrieval Pipelines for Research Assistants",
        ],
        "abstract": "studies retrieval models for finding relevant scientific papers using lexical signals, dense embeddings, citations, and query reformulation.",
    },
    {
        "slug": "rag",
        "keyword": "rag",
        "titles": [
            "Retrieval-Augmented Generation for Knowledge-Intensive NLP",
            "Grounded Answer Generation over Research Collections",
            "Citation-Aware RAG for Scientific Question Answering",
            "Chunk Selection Strategies for Literature Review Assistants",
            "Faithfulness Checks for Retrieval-Augmented Research Tools",
            "RAG with Structured Evidence Graphs",
            "Context Window Allocation for Multi-Paper Questions",
            "Auditable RAG Answers with Paper-Level Citations",
        ],
        "abstract": "combines retrieved scientific evidence with language generation while emphasizing citations, faithfulness, and transparent answer provenance.",
    },
    {
        "slug": "knowledge-graph",
        "keyword": "knowledge graph",
        "titles": [
            "PageRank and Citation-Aware Research Discovery",
            "Knowledge Graph Construction from Scholarly Metadata",
            "Entity Linking for Scientific Concepts and Methods",
            "Citation Graphs Meet Retrieval-Augmented Assistants",
            "Semantic Relation Extraction between Research Papers",
            "Graph-Based Exploration of Research Communities",
            "Temporal Knowledge Graphs for Topic Evolution",
            "Interactive Scholarly Graph Interfaces",
        ],
        "abstract": "uses citation links, semantic relations, concepts, and temporal structure to organize scientific literature as an explorable knowledge graph.",
    },
    {
        "slug": "gap-analysis",
        "keyword": "gap suggestions",
        "titles": [
            "Finding Research Gaps with Connected Components",
            "Low-Degree Nodes as Signals for Underexplored Topics",
            "Cluster Summaries for Literature Gap Suggestions",
            "Unaddressed Evaluation Settings in Applied AI Papers",
            "Human-in-the-Loop Validation of Gap Recommendations",
            "Contradiction Mining for Open Scientific Questions",
            "From Evidence Clusters to Research Hypotheses",
            "Cautious Gap Suggestion Interfaces for Researchers",
        ],
        "abstract": "identifies possible research gaps using graph clusters, sparse connections, missing evaluations, contradictions, and cautious human-readable suggestions.",
    },
    {
        "slug": "evolution",
        "keyword": "evolution chain",
        "titles": [
            "Modeling Scientific Topic Evolution with Citation Chains",
            "Topological Ordering of Method Extension Graphs",
            "Reading Plans from Research Lineage Graphs",
            "Explaining Method Progression across Paper Collections",
            "Timeline Summaries for Literature Review Generation",
            "Detecting Cycles in Claims of Method Extension",
            "Narrative Literature Reviews from Structured Chains",
            "Pedagogical Sequencing of Foundational Papers",
        ],
        "abstract": "models how research topics evolve through method extensions, limitations, fixes, timelines, reading plans, and structured literature reviews.",
    },
    {
        "slug": "recommendation",
        "keyword": "recommendation",
        "titles": [
            "Graph Neural Networks for Scholarly Recommendation",
            "Personalized Paper Recommendation with User Reading Histories",
            "Cold-Start Scientific Recommendation with Abstract Embeddings",
            "Diversity-Aware Recommendation for Literature Exploration",
            "Serendipity Metrics for Research Discovery Systems",
            "Citation-Enhanced Recommendations for Early Researchers",
            "Interactive Feedback Loops in Paper Recommenders",
            "Benchmarking Scholarly Recommendation Systems",
        ],
        "abstract": "recommends papers using graph neural networks, reading histories, abstracts, citation context, diversity, feedback, and benchmarking protocols.",
    },
    {
        "slug": "summarization",
        "keyword": "summarization",
        "titles": [
            "Scientific Paper Summarization with Section-Aware Encoders",
            "Multi-Document Summaries for Literature Surveys",
            "Extractive Summaries of Methods and Contributions",
            "Abstractive Summaries Grounded in Citation Context",
            "Comparative Summaries across Related Papers",
            "Claim-Centric Summarization for Research Assistants",
            "Evaluation Rubrics for Scientific Summaries",
            "Controllable Literature Review Paragraph Generation",
        ],
        "abstract": "summarizes scientific papers and paper clusters using section structure, claims, comparisons, citation context, and controllable review generation.",
    },
    {
        "slug": "metadata",
        "keyword": "metadata extraction",
        "titles": [
            "PDF Metadata Extraction for Scholarly Archives",
            "Title and Author Detection from Academic PDFs",
            "Reference Parsing in Noisy Research Documents",
            "Semantic Scholar Matching with Fuzzy Title Search",
            "Deduplicating Uploaded and Indexed Papers",
            "Metadata Quality Checks for Research Databases",
            "Recovering Abstracts from Heterogeneous PDF Layouts",
            "Practical Ingestion Pipelines for Literature Tools",
        ],
        "abstract": "extracts and cleans metadata from PDFs, including titles, authors, abstracts, references, duplicate detection, and indexed-paper matching.",
    },
    {
        "slug": "evaluation",
        "keyword": "evaluation",
        "titles": [
            "Evaluating Research Assistants for Factual Grounding",
            "Citation Precision Metrics for Literature QA",
            "User Studies of Graph-Based Literature Exploration",
            "Stress Tests for Missing Citation Detection",
            "Measuring Coverage in Literature Review Generators",
            "Benchmark Datasets for Scientific RAG Systems",
            "Error Taxonomies for Research Paper Chatbots",
            "Reproducibility Protocols for Literature AI Tools",
        ],
        "abstract": "evaluates literature AI systems through grounding, citation precision, user studies, coverage, benchmark datasets, error taxonomies, and reproducibility.",
    },
    {
        "slug": "interface",
        "keyword": "interface",
        "titles": [
            "Visual Analytics for Research Paper Collections",
            "Node-Link Interfaces for Scholarly Knowledge Graphs",
            "Progressive Disclosure in Literature Exploration Tools",
            "Design Patterns for AI-Assisted Research Workflows",
            "Explainable Graph Interactions for Research Discovery",
            "Reading Planner Interfaces for Complex Topics",
            "Trust Calibration in AI Literature Review Tools",
            "Workspace Design for Research Graph AI Systems",
        ],
        "abstract": "designs interactive interfaces for graph exploration, progressive disclosure, explainable AI workflows, reading plans, and researcher trust.",
    },
]


AUTHORS = [
    "Avery Chen",
    "Mira Patel",
    "Samir Rao",
    "Lena Ortiz",
    "Noah Williams",
    "Hana Kim",
    "Iris Morgan",
    "Theo Becker",
]


def build_sample_papers() -> list[tuple[str, str, str, int, list[str]]]:
    papers = []
    for theme_index, theme in enumerate(THEMES):
        for paper_index, title in enumerate(theme["titles"]):
            year = 1990 + theme_index * 2 + paper_index * 4
            authors = ", ".join(
                [
                    AUTHORS[(theme_index + paper_index) % len(AUTHORS)],
                    AUTHORS[(theme_index + paper_index + 3) % len(AUTHORS)],
                ]
            )
            abstract = (
                f"This paper {theme['abstract']} It contributes to {theme['keyword']} research "
                f"by comparing prior work, describing limitations, and outlining future research directions."
            )
            papers.append((title, authors, abstract, min(year, 2026), [theme["keyword"], theme["slug"]]))
    return papers


def add_keyword(keyword_cache: dict[str, models.Keyword], text: str) -> models.Keyword:
    keyword = keyword_cache.get(text)
    if keyword is None:
        keyword = models.Keyword(text=text)
        keyword_cache[text] = keyword
    return keyword


def add_edge(db, source: int, target: int, edge_type: str, label: str, confidence: float) -> None:
    db.add(
        models.Edge(
            source_paper_id=source,
            target_paper_id=target,
            edge_type=edge_type,
            relation_label=label,
            confidence=confidence,
        )
    )


def seed_database(reset: bool = True) -> None:
    init_db()
    db = SessionLocal()
    embeddings = EmbeddingService()
    sample_papers = build_sample_papers()
    try:
        if reset:
            db.query(models.ChatHistory).delete()
            db.query(models.PaperChunk).delete()
            db.query(models.Edge).delete()
            db.query(models.PaperKeyword).delete()
            db.query(models.Keyword).delete()
            db.query(models.Paper).delete()
            db.commit()

        keyword_cache: dict[str, models.Keyword] = {}
        paper_ids: list[int] = []
        theme_paper_ids: list[list[int]] = []

        for theme_index, theme in enumerate(THEMES):
            ids_for_theme: list[int] = []
            for title, authors, abstract, year, keywords in sample_papers[
                theme_index * 8 : theme_index * 8 + 8
            ]:
                body = (
                    f"{title}\n\nAbstract\n{abstract}\n\n"
                    f"Methods\nThe work studies {theme['keyword']} in research paper management systems.\n\n"
                    "References\n"
                )
                paper = models.Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    source_type="indexed",
                    full_text=body,
                    whole_embedding=encode_embedding(embeddings.embed(f"{title}\n{abstract}")),
                )
                for keyword_text in sorted(set(keywords)):
                    paper.keywords.append(add_keyword(keyword_cache, keyword_text))
                db.add(paper)
                db.flush()
                paper_ids.append(paper.id)
                ids_for_theme.append(paper.id)
                chunks = [
                    f"{title}. {abstract}",
                    f"This chunk discusses {theme['keyword']}, limitations, evidence, citations, and future work.",
                ]
                for chunk_index, chunk_text in enumerate(chunks):
                    db.add(
                        models.PaperChunk(
                            paper_id=paper.id,
                            chunk_index=chunk_index,
                            text=chunk_text,
                            embedding=encode_embedding(embeddings.embed(chunk_text)),
                        )
                    )
            theme_paper_ids.append(ids_for_theme)

        for ids in theme_paper_ids:
            for index in range(len(ids) - 1):
                add_edge(db, ids[index], ids[index + 1], "semantic_relation", "extends", 0.82 + index * 0.015)
                add_edge(db, ids[index + 1], ids[index], "citation", "cites", 0.88 + index * 0.01)
            for index in range(len(ids) - 2):
                add_edge(db, ids[index], ids[index + 2], "similarity", "similar", 0.78 + index * 0.012)
                add_edge(db, ids[index + 2], ids[index], "similarity", "similar", 0.78 + index * 0.012)
            add_edge(db, ids[0], ids[4], "semantic_relation", "extends", 0.74)
            add_edge(db, ids[6], ids[2], "citation", "cites", 0.9)

        # Keep the corpus intentionally split into five demo clusters:
        # retrieval+RAG, knowledge-graph+interface, gaps+evaluation,
        # evolution+summarization, and recommendation+metadata.
        cross_theme_pairs = [
            (0, 1),
            (2, 9),
            (3, 8),
            (4, 6),
            (5, 7),
        ]
        for left_theme, right_theme in cross_theme_pairs:
            left = theme_paper_ids[left_theme]
            right = theme_paper_ids[right_theme]
            add_edge(db, left[3], right[3], "similarity", "similar", 0.83)
            add_edge(db, right[3], left[3], "similarity", "similar", 0.83)
            add_edge(db, left[5], right[1], "citation", "cites", 0.86)
            add_edge(db, left[6], right[6], "semantic_relation", "applies_method_from", 0.77)

        db.commit()
        print(f"Seeded {len(paper_ids)} papers and {db.query(models.Edge).count()} edges.")
    finally:
        db.close()


def seed_if_empty() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(models.Paper).count() == 0:
            db.close()
            seed_database(reset=False)
    finally:
        if db.is_active:
            db.close()


def main() -> None:
    seed_database(reset=True)


if __name__ == "__main__":
    main()
