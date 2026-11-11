"""
NetworkX-Powered Graph Intelligence Service for ResearchGraphAI.

Enforces strict separation of edge semantics:
- PageRank centrality is computed ONLY on the directed citation DAG (relation_type == 'cites').
  Similarity / coupling edges never enter PageRank.
- Graph analytics are cached per (project_id, corpus_version) in graph_analytics_cache.
"""

from typing import Any
import networkx as nx
from sqlalchemy.orm import Session

from app import models
from app.dsa.graph import Graph as DSAGraph
from app.dsa.shortest_path import dijkstra
from app.services.constants import RELATION_CITES


class NetworkXGraphService:
    @staticmethod
    def build_project_graph(db: Session, project_id: int) -> nx.DiGraph:
        """Construct a NetworkX DiGraph from stored paper relations."""
        G = nx.DiGraph()

        project_papers = (
            db.query(models.ProjectPaper, models.Paper)
            .join(models.Paper, models.ProjectPaper.paper_id == models.Paper.id)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )

        for pp, paper in project_papers:
            G.add_node(
                paper.id,
                title=paper.title,
                year=paper.year,
                citation_count=paper.citation_count,
                abstract_only=pp.abstract_only,
            )

        relations = (
            db.query(models.PaperRelation)
            .filter(models.PaperRelation.project_id == project_id)
            .all()
        )

        for rel in relations:
            directed = bool(getattr(rel, "directed", rel.relation_type == RELATION_CITES))
            G.add_edge(
                rel.source_id,
                rel.target_id,
                id=rel.id,
                relation_type=rel.relation_type,
                basis=rel.basis,
                weight=rel.score,
                directed=directed,
            )

        return G

    @staticmethod
    def build_citation_dag(G: nx.DiGraph) -> nx.DiGraph:
        """Extract ONLY directed citation edges (citing -> cited) onto all graph nodes."""
        dag = nx.DiGraph()
        dag.add_nodes_from(G.nodes(data=True))
        for u, v, data in G.edges(data=True):
            if data.get("relation_type") == RELATION_CITES:
                dag.add_edge(u, v, **data)
        return dag

    @staticmethod
    def analyze_graph(
        G: nx.DiGraph,
        db: Session | None = None,
        project_id: int | None = None,
        corpus_version: int | None = None,
    ) -> dict[str, Any]:
        """
        Compute structural graph analytics with optional (project_id, corpus_version) DB caching.
        PageRank runs strictly on the citation DAG only.
        """
        if db is not None and project_id is not None and corpus_version is not None:
            cached = (
                db.query(models.GraphAnalyticsCache)
                .filter(
                    models.GraphAnalyticsCache.project_id == project_id,
                    models.GraphAnalyticsCache.corpus_version == corpus_version,
                )
                .first()
            )
            if cached and cached.analytics:
                # Normalize JSON string keys back to int node IDs
                raw_pr = cached.analytics.get("pagerank", {})
                cached_out = dict(cached.analytics)
                cached_out["pagerank"] = {int(k): float(v) for k, v in raw_pr.items()}
                return cached_out

        if len(G.nodes) == 0:
            return {
                "total_nodes": 0,
                "total_edges": 0,
                "pagerank": {},
                "connected_components": [],
                "density": 0.0,
            }

        citation_dag = NetworkXGraphService.build_citation_dag(G)
        try:
            pagerank = nx.pagerank(citation_dag, weight="weight")
            pagerank = {int(k): round(float(v), 6) for k, v in pagerank.items()}
        except Exception:
            pagerank = {int(n): round(1.0 / len(G.nodes), 6) for n in G.nodes}

        components = [
            list(comp)
            for comp in nx.weakly_connected_components(G)
        ]

        analytics = {
            "total_nodes": len(G.nodes),
            "total_edges": len(G.edges),
            "citation_edges": len(citation_dag.edges),
            "pagerank": pagerank,
            "connected_components": components,
            "density": round(float(nx.density(G)), 4),
        }

        if db is not None and project_id is not None and corpus_version is not None:
            try:
                existing = (
                    db.query(models.GraphAnalyticsCache)
                    .filter(
                        models.GraphAnalyticsCache.project_id == project_id,
                        models.GraphAnalyticsCache.corpus_version == corpus_version,
                    )
                    .first()
                )
                serializable = dict(analytics)
                serializable["pagerank"] = {str(k): v for k, v in pagerank.items()}
                if existing:
                    existing.analytics = serializable
                else:
                    db.add(models.GraphAnalyticsCache(
                        project_id=project_id,
                        corpus_version=corpus_version,
                        analytics=serializable,
                    ))
                db.commit()
            except Exception:
                db.rollback()

        return analytics

    @staticmethod
    def explain_path(G: nx.DiGraph, source_id: int, target_id: int) -> dict[str, Any] | None:
        """Find and explain the lowest-cost path between two papers using hand-built Dijkstra."""
        if not G.has_node(source_id) or not G.has_node(target_id):
            return None

        # Build hand-built weighted traversal graph (citation cost=0.1, similarity cost=1-score)
        dsa_graph = DSAGraph(directed=True)
        for nid, attrs in G.nodes(data=True):
            dsa_graph.add_node(nid, **attrs)
        for u, v, data in G.edges(data=True):
            dsa_graph.add_edge(u, v, **data)
            if not data.get("directed", True):
                dsa_graph.add_edge(v, u, **data)

        result = dijkstra(dsa_graph, source_id, target_id, use_semantic_cost=True)
        if result is None:
            return None
        total_cost, path_nodes = result

        path_edges = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            data = dsa_graph.get_edge_data(u, v) or {}
            path_edges.append({
                "from": u,
                "to": v,
                "relation_type": data.get("relation_type", "connected"),
                "basis": data.get("basis", "inference"),
                "weight": data.get("weight", 1.0),
            })

        return {
            "path_nodes": path_nodes,
            "hops": len(path_nodes) - 1,
            "total_cost": round(float(total_cost), 4),
            "edges": path_edges,
            "explanation": f"Connected across {len(path_nodes) - 1} step(s) (Dijkstra cost {round(float(total_cost), 3)}).",
        }
