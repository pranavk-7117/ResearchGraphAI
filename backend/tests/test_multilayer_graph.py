"""
Tests for T8: Multi-layer Graph (citation, coupling Jaccard, semantic),
structural metrics (betweenness, k-core, Burt's constraint), and API layer labels.
"""

from unittest.mock import MagicMock
import networkx as nx
import pytest

from app import models
from app.api.routes import get_project_graph
from app.auth import AuthenticatedUser
from app.services.constants import (
    BASIS_BIBLIOGRAPHIC_COUPLING,
    BASIS_CITATION_METADATA,
    BASIS_EMBEDDING_SIMILARITY,
    RELATION_CITES,
    RELATION_COUPLING,
    RELATION_SIMILAR,
)
from app.services.relations import canonical_reference_key, compute_bibliographic_coupling_pairs
from app.services.research_graph import NetworkXGraphService


def test_bibliographic_coupling_jaccard_hand_computed():
    """
    Fixture:
      P1 refs: {doi:a, doi:b, doi:c}
      P2 refs: {doi:b, doi:c, doi:d}
      P3 refs: {doi:e}
    Expected: only (1, 2) with Jaccard = 2 / 4 = 0.5 and shared_count = 2.
    """
    r1_a = MagicMock(cited_paper_id=None, doi="10.1/A", raw_reference=None)
    r1_b = MagicMock(cited_paper_id=None, doi="10.1/B", raw_reference=None)
    r1_c = MagicMock(cited_paper_id=None, doi="10.1/C", raw_reference=None)
    r2_b = MagicMock(cited_paper_id=None, doi="10.1/b", raw_reference=None)  # case-insensitive
    r2_c = MagicMock(cited_paper_id=None, doi="10.1/C", raw_reference=None)
    r2_d = MagicMock(cited_paper_id=None, doi="10.1/D", raw_reference=None)
    r3_e = MagicMock(cited_paper_id=None, doi="10.1/E", raw_reference=None)

    refs_by_paper = {
        1: {canonical_reference_key(r) for r in (r1_a, r1_b, r1_c)},
        2: {canonical_reference_key(r) for r in (r2_b, r2_c, r2_d)},
        3: {canonical_reference_key(r) for r in (r3_e,)},
    }
    edges = compute_bibliographic_coupling_pairs(refs_by_paper)
    assert len(edges) == 1
    u, v, jacc, shared = edges[0]
    assert (u, v) == (1, 2)
    assert jacc == 0.5
    assert shared == 2


def test_graph_structural_metrics_and_api_layers():
    """Verify betweenness, k-core, Burt's constraint and API layer names."""
    g = nx.DiGraph()
    for pid in (1, 2, 3, 4):
        g.add_node(pid, title=f"P{pid}", year=2020 + pid, citation_count=pid * 5, abstract_only=False)
    # 1-2-3-4 line via coupling/citation so 2 and 3 are bridges
    g.add_edge(2, 1, relation_type=RELATION_CITES, basis=BASIS_CITATION_METADATA, weight=1.0, directed=True)
    g.add_edge(2, 3, relation_type=RELATION_COUPLING, basis=BASIS_BIBLIOGRAPHIC_COUPLING, weight=0.5, directed=False)
    g.add_edge(3, 4, relation_type=RELATION_SIMILAR, basis=BASIS_EMBEDDING_SIMILARITY, weight=0.8, directed=False)

    analytics = NetworkXGraphService.analyze_graph(g)
    assert analytics["betweenness"][2] > analytics["betweenness"][1]
    assert analytics["betweenness"][3] > analytics["betweenness"][4]
    assert analytics["k_core"][1] == 1
    assert isinstance(analytics["burt_constraint"][2], float)

    # Verify routes.get_project_graph populates layer and shared_references
    db = MagicMock()
    proj = MagicMock(id=7, user_id="u1", corpus_version=1)
    p1 = MagicMock(id=1, title="P1", year=2021, citation_count=5, authors=[], abstract=None, venue=None, doi=None, original_url=None)
    p2 = MagicMock(id=2, title="P2", year=2022, citation_count=10, authors=[], abstract=None, venue=None, doi=None, original_url=None)
    pp1 = MagicMock(abstract_only=False)
    pp2 = MagicMock(abstract_only=False)

    rel_c = MagicMock(id=10, source_id=2, target_id=1, relation_type=RELATION_CITES, basis=BASIS_CITATION_METADATA, score=1.0, directed=True)
    rel_cp = MagicMock(id=11, source_id=1, target_id=2, relation_type=RELATION_COUPLING, basis=BASIS_BIBLIOGRAPHIC_COUPLING, score=0.5, directed=False)
    rel_s = MagicMock(id=12, source_id=1, target_id=2, relation_type=RELATION_SIMILAR, basis=BASIS_EMBEDDING_SIMILARITY, score=0.77, directed=False)

    ref_1 = MagicMock(citing_paper_id=1, cited_paper_id=None, doi="10.1/shared", raw_reference=None)
    ref_2 = MagicMock(citing_paper_id=2, cited_paper_id=None, doi="10.1/shared", raw_reference=None)

    def q_side_effect(model_or_tuple, *args):
        q = MagicMock()
        if model_or_tuple is models.ResearchProject:
            q.filter.return_value.first.return_value = proj
        elif model_or_tuple is models.ClusterMember:
            q.join.return_value.filter.return_value.all.return_value = []
        elif model_or_tuple is models.GraphAnalyticsCache:
            q.filter.return_value.first.return_value = None
        elif model_or_tuple is models.PaperRelation:
            q.filter.return_value.all.return_value = [rel_c, rel_cp, rel_s]
        elif model_or_tuple is models.PaperReference:
            q.filter.return_value.all.return_value = [ref_1, ref_2]
        else:
            q.join.return_value.filter.return_value.all.return_value = [(pp1, p1), (pp2, p2)]
        return q

    db.query.side_effect = q_side_effect
    out = get_project_graph(project_id=7, user=AuthenticatedUser(id="u1"), db=db)
    layers = {e.relation_type: e.layer for e in out.edges}
    assert layers == {RELATION_CITES: "citation", RELATION_COUPLING: "coupling", RELATION_SIMILAR: "semantic"}
    coupling_edge = next(e for e in out.edges if e.layer == "coupling")
    assert coupling_edge.shared_references == ["10.1/shared"]
    assert coupling_edge.score == 0.5
