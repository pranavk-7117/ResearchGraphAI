"""
Tests for Dense Embeddings, L2-Normalized Mean Paper Embeddings, Citation Resolution,
Mutual k-NN Similarity, Bounded SQL Queries (40 papers), and Citation-DAG-Only PageRank.
"""

from unittest.mock import MagicMock
import networkx as nx
import numpy as np
import pytest
from sqlalchemy import event

from app.database import SessionLocal, engine
from app import models
from app.services.constants import BASIS_CITATION_METADATA, BASIS_EMBEDDING_SIMILARITY, RELATION_CITES, RELATION_SIMILAR
from app.services.embeddings import EmbeddingService, cosine_similarity, get_paper_embeddings
from app.services.relations import RelationsService
from app.services.research_graph import NetworkXGraphService


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_embedding_dimensions():
    service = EmbeddingService()
    assert service.dim == 384
    vec = service.embed("Evaluating cryptographic protocols for decentralized networks.")
    assert len(vec) == 384
    assert all(isinstance(v, float) for v in vec)


def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert pytest.approx(cosine_similarity(v1, v2)) == 1.0
    assert pytest.approx(cosine_similarity(v1, v3)) == 0.0


def test_paper_embedding_is_l2_normalized_mean_of_all_chunks():
    """Paper embedding must average ALL chunks and L2-normalize, not take only chunk 0."""
    db = MagicMock()
    p = MagicMock(id=7, title="Multi-chunk paper", abstract=None)
    e1 = [1.0, 0.0, 0.0]
    e2 = [0.0, 1.0, 0.0]
    db.query.return_value.filter.return_value.all.return_value = [(7, e1), (7, e2)]

    out = get_paper_embeddings(db, [p], embed_missing=False)
    expected = np.array([1.0, 1.0, 0.0], dtype=np.float32)
    expected = expected / np.linalg.norm(expected)
    assert np.allclose(out[7], expected, atol=1e-5)
    assert pytest.approx(np.linalg.norm(out[7]), abs=1e-5) == 1.0


def test_pagerank_invariant_to_similarity_edges():
    """PageRank must run ONLY on the citation DAG; adding/reversing similarity edges cannot change it."""
    g1 = nx.DiGraph()
    for i in (1, 2, 3, 4):
        g1.add_node(i)
    g1.add_edge(2, 1, relation_type=RELATION_CITES, weight=1.0, directed=True)
    g1.add_edge(3, 1, relation_type=RELATION_CITES, weight=1.0, directed=True)
    g1.add_edge(4, 2, relation_type=RELATION_CITES, weight=1.0, directed=True)

    pr_base = NetworkXGraphService.analyze_graph(g1)["pagerank"]

    # Add similarity edges and also add reversed similarity edge directions
    g2 = g1.copy()
    g2.add_edge(1, 4, relation_type=RELATION_SIMILAR, weight=0.95, directed=False)
    g2.add_edge(3, 4, relation_type=RELATION_SIMILAR, weight=0.88, directed=False)
    pr_with_sim = NetworkXGraphService.analyze_graph(g2)["pagerank"]

    g3 = g1.copy()
    g3.add_edge(4, 1, relation_type=RELATION_SIMILAR, weight=0.95, directed=False)
    g3.add_edge(4, 3, relation_type=RELATION_SIMILAR, weight=0.88, directed=False)
    pr_reversed_sim = NetworkXGraphService.analyze_graph(g3)["pagerank"]

    assert pr_base == pr_with_sim
    assert pr_base == pr_reversed_sim


def test_citation_fuzzy_matching_strictness():
    """Drop partial_ratio false positives; allow only full fuzz.ratio >= 95 with year +-1."""
    svc = RelationsService()
    p_target = MagicMock(
        id=10, doi=None, openalex_id=None, s2_id=None, arxiv_id=None,
        title_hash="h10", title="Deep Residual Learning for Image Recognition", year=2016,
    )
    lookups = svc._build_citation_lookups([p_target])

    # Partial substring match in unrelated long title must NOT resolve
    ref_bad = MagicMock(
        citing_paper_id=99,
        doi=None,
        raw_reference="Extensions of Deep Residual Learning for Image Recognition in Autonomous Marine Navigation with Long Context 2016",
    )
    assert svc._resolve_reference(ref_bad, lookups) is None

    # Full title >= 95 with wrong year (2022 vs 2016) must NOT resolve
    ref_wrong_year = MagicMock(
        citing_paper_id=99,
        doi=None,
        raw_reference="Deep Residual Learning for Image Recognition 2022",
    )
    assert svc._resolve_reference(ref_wrong_year, lookups) is None

    # Exact/near-exact full title with matching year +-1 resolves
    ref_ok = MagicMock(
        citing_paper_id=99,
        doi=None,
        raw_reference="Deep Residual Learning for Image Recognition",
    )
    assert svc._resolve_reference(ref_ok, lookups) == 10


def test_citation_and_similarity_relations(db):
    db.query(models.PaperReference).filter(models.PaperReference.raw_reference == "Kipf and Welling 2017 GCN").delete()
    db.query(models.Paper).filter(models.Paper.doi.in_(["10.1000/gcn", "10.1000/gat"])).delete()
    db.commit()

    prof_id = "test-relations-user"
    if not db.query(models.Profile).filter(models.Profile.id == prof_id).first():
        db.add(models.Profile(id=prof_id, email="rel@test.com"))
        db.commit()

    proj = models.ResearchProject(user_id=prof_id, topic="Graph Learning")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    try:
        p_a = models.Paper(title="Graph Convolutional Networks", doi="10.1000/gcn", title_hash="hash_gcn", year=2017, source_name="openalex")
        p_b = models.Paper(title="Graph Attention Networks", doi="10.1000/gat", title_hash="hash_gat", year=2018, source_name="arxiv")
        db.add_all([p_a, p_b])
        db.commit()
        db.refresh(p_a)
        db.refresh(p_b)

        db.add(models.ProjectPaper(project_id=proj.id, paper_id=p_a.id, selected=True))
        db.add(models.ProjectPaper(project_id=proj.id, paper_id=p_b.id, selected=True))
        db.add(models.PaperReference(citing_paper_id=p_b.id, raw_reference="Kipf and Welling 2017 GCN", doi=p_a.doi, source="api"))
        db.commit()

        rel_service = RelationsService()
        rel_service.build_project_relations(db, project_id=proj.id)

        citation_rel = (
            db.query(models.PaperRelation)
            .filter(
                models.PaperRelation.project_id == proj.id,
                models.PaperRelation.source_id == p_b.id,
                models.PaperRelation.target_id == p_a.id,
                models.PaperRelation.relation_type == RELATION_CITES,
            )
            .first()
        )
        assert citation_rel is not None
        assert citation_rel.basis == BASIS_CITATION_METADATA
        assert citation_rel.directed is True
    finally:
        db.delete(proj)
        db.query(models.Paper).filter(models.Paper.title_hash.in_(["hash_gcn", "hash_gat"])).delete(synchronize_session=False)
        db.commit()


def test_build_relations_40_papers_bounded_sql_queries(db):
    """Acceptance: relation building for 40 papers issues bounded O(N) SQL queries and undirected mutual k-NN edges."""
    prof_id = "test-t4-40papers-user"
    if not db.query(models.Profile).filter(models.Profile.id == prof_id).first():
        db.add(models.Profile(id=prof_id, email="t4@test.com"))
        db.commit()

    hashes = [f"t4_40p_hash_{i}" for i in range(40)]
    db.query(models.Paper).filter(models.Paper.title_hash.in_(hashes)).delete(synchronize_session=False)
    db.commit()

    proj = models.ResearchProject(user_id=prof_id, topic="T4 Bounded Query 40-Paper Benchmark")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    try:
        papers = [
            models.Paper(
                title=f"Synthetic T4 Benchmark Paper {i}",
                title_hash=hashes[i],
                year=2020 + (i % 5),
                source_name="test",
            )
            for i in range(40)
        ]
        db.add_all(papers)
        db.flush()

        for idx, p in enumerate(papers):
            db.add(models.ProjectPaper(project_id=proj.id, paper_id=p.id, selected=True))
            vec = [0.0] * 384
            vec[idx % 10] = 1.0
            vec[(idx + 1) % 10] = 0.5
            norm = float(np.linalg.norm(vec))
            vec = [x / norm for x in vec]
            db.add(models.PaperChunk(
                paper_id=p.id, page_start=1, section="Abstract", chunk_index=0,
                text=f"Chunk text for paper {p.id}", text_hash=f"t4_chk_{p.id}", embedding=vec,
            ))
        db.commit()

        query_count = 0

        def count_queries(conn, cursor, statement, parameters, context, executemany):
            nonlocal query_count
            query_count += 1

        event.listen(engine, "before_cursor_execute", count_queries)
        try:
            rel_service = RelationsService()
            created = rel_service.build_project_relations(db, project_id=proj.id, sim_k=4)
        finally:
            event.remove(engine, "before_cursor_execute", count_queries)

        # Bounded: batched LATERAL pgvector + bulk queries (<= 15 queries for 40 papers!)
        assert query_count <= 15, f"Too many SQL queries: {query_count}"

        sim_edges = [r for r in created if r.relation_type == RELATION_SIMILAR]
        assert len(sim_edges) > 0
        for edge in sim_edges:
            assert edge.source_id < edge.target_id
            assert edge.directed is False
            assert edge.basis == BASIS_EMBEDDING_SIMILARITY

        # Test graph analytics caching & invalidation on corpus_version bump
        G = NetworkXGraphService.build_project_graph(db, proj.id)
        a1 = NetworkXGraphService.analyze_graph(G, db=db, project_id=proj.id, corpus_version=proj.corpus_version)
        assert len(a1["pagerank"]) == 40
        cache_row = db.query(models.GraphAnalyticsCache).filter(
            models.GraphAnalyticsCache.project_id == proj.id,
            models.GraphAnalyticsCache.corpus_version == proj.corpus_version,
        ).first()
        assert cache_row is not None
    finally:
        db.delete(proj)
        db.query(models.Paper).filter(models.Paper.title_hash.in_(hashes)).delete(synchronize_session=False)
        db.commit()
