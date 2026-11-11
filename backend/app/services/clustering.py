"""
Corpus Clustering & Community Detection Service for ResearchGraphAI.

Supports:
1. Leiden community detection on the weighted combined graph (igraph + leidenalg,
   with logged fallback to NetworkX louvain_communities / greedy_modularity_communities)
   guaranteeing connected communities and deterministic output with a fixed seed.
2. Embedding-based Agglomerative Clustering with automatic k selection via
   cosine silhouette score over k in [2, min(8, n - 1)].

Stores modularity (community), silhouette (agglomerative), and NMI agreement
between both partitions in ResearchCluster.params.
"""

from collections import Counter
import logging
import os
from typing import Any
import networkx as nx
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import normalized_mutual_info_score, silhouette_score
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import get_paper_embeddings
from app.services.llm import LLMService

logger = logging.getLogger(__name__)


def _ensure_connected_communities(
    nx_graph: nx.Graph, communities: list[set[Any]]
) -> list[list[Any]]:
    """Split any community that is disconnected in nx_graph into connected subgraphs."""
    connected: list[list[Any]] = []
    for comm in communities:
        if not comm:
            continue
        sub = nx_graph.subgraph(comm)
        for comp in nx.connected_components(sub):
            connected.append(sorted(comp))
    # Sort deterministically by min node ID
    connected.sort(key=lambda c: c[0])
    return connected


def run_community_partition(
    nx_graph: nx.Graph,
    resolution: float = 1.0,
    seed: int = 42,
) -> tuple[list[list[Any]], dict[str, Any]]:
    """
    Partition `nx_graph` using Leiden (igraph + leidenalg) or logged NetworkX fallback.
    Guarantees every returned community induces a connected subgraph and is deterministic for `seed`.
    """
    if nx_graph.number_of_nodes() == 0:
        return [], {"algo_name": "Leiden", "modularity": 0.0, "fallback": None}

    if nx_graph.number_of_edges() == 0:
        comms = [[n] for n in sorted(nx_graph.nodes())]
        return comms, {"algo_name": "Leiden", "modularity": 0.0, "fallback": "no_edges_singletons"}

    fallback_note: str | None = None
    algo_name = "Leiden"
    raw_comms: list[set[Any]] = []

    try:
        import igraph as ig
        import leidenalg

        nodes_sorted = sorted(nx_graph.nodes())
        idx_map = {n: i for i, n in enumerate(nodes_sorted)}
        ig_g = ig.Graph(n=len(nodes_sorted), directed=False)
        edges = []
        weights = []
        for u, v, data in nx_graph.edges(data=True):
            if u != v:
                edges.append((idx_map[u], idx_map[v]))
                weights.append(max(0.01, float(data.get("weight", 1.0))))
        ig_g.add_edges(edges)
        ig_g.es["weight"] = weights

        part = leidenalg.find_partition(
            ig_g,
            leidenalg.RBConfigurationVertexPartition,
            weights="weight",
            resolution_parameter=resolution,
            seed=seed,
        )
        raw_comms = [{nodes_sorted[idx] for idx in group} for group in part]
    except Exception as exc:
        fallback_note = f"igraph/leidenalg unavailable ({exc}); "
        if hasattr(nx.community, "louvain_communities"):
            fallback_note += "used networkx.community.louvain_communities"
            algo_name = "LouvainFallback"
            logger.warning(fallback_note)
            raw_comms = [
                set(c)
                for c in nx.community.louvain_communities(
                    nx_graph, weight="weight", resolution=resolution, seed=seed
                )
            ]
        else:
            fallback_note += "used networkx.community.greedy_modularity_communities"
            algo_name = "GreedyModularityFallback"
            logger.warning(fallback_note)
            raw_comms = [
                set(c)
                for c in nx.algorithms.community.greedy_modularity_communities(
                    nx_graph, weight="weight"
                )
            ]

    comms = _ensure_connected_communities(nx_graph, raw_comms)
    mod_val = round(
        float(nx.algorithms.community.modularity(nx_graph, [set(c) for c in comms], weight="weight")),
        4,
    )
    return comms, {
        "algo_name": algo_name,
        "modularity": mod_val,
        "resolution": resolution,
        "seed": seed,
        "fallback": fallback_note,
    }


def run_agglomerative_silhouette(
    X: np.ndarray,
    paper_ids: list[int],
    n_clusters: int | None = None,
) -> tuple[dict[int, list[int]], dict[str, Any]]:
    """
    Cluster embedding matrix X using AgglomerativeClustering, picking k in [2, min(8, n-1)]
    via cosine silhouette score when n_clusters is None.
    """
    n = len(paper_ids)
    if n < 2:
        return {0: list(paper_ids)}, {"n_clusters": n, "silhouette": 0.0}

    best_k = n_clusters
    best_labels = None
    best_sil = -1.0

    if best_k is None:
        max_k = min(8, n - 1)
        if max_k < 2:
            best_k = 2 if n >= 2 else 1
        else:
            for cand_k in range(2, max_k + 1):
                algo = AgglomerativeClustering(n_clusters=cand_k, metric="cosine", linkage="average")
                labels = algo.fit_predict(X)
                if len(set(labels)) < 2 or len(set(labels)) >= n:
                    continue
                try:
                    sil = float(silhouette_score(X, labels, metric="cosine"))
                except Exception:
                    sil = -1.0
                if sil > best_sil:
                    best_sil = sil
                    best_k = cand_k
                    best_labels = labels

    if best_labels is None:
        k = max(1, min(best_k or 2, n))
        if k == 1 or n < 2:
            best_labels = np.zeros(n, dtype=int)
            best_sil = 0.0
        else:
            algo = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
            best_labels = algo.fit_predict(X)
            if 2 <= len(set(best_labels)) < n:
                try:
                    best_sil = float(silhouette_score(X, best_labels, metric="cosine"))
                except Exception:
                    best_sil = 0.0
            else:
                best_sil = 0.0

    groups: dict[int, list[int]] = {}
    for pid, lbl in zip(paper_ids, best_labels):
        groups.setdefault(int(lbl), []).append(pid)

    return groups, {
        "n_clusters": len(groups),
        "silhouette": round(float(best_sil), 4) if best_sil > -1.0 else 0.0,
        "metric": "cosine",
        "linkage": "average",
    }


def compute_partition_nmi(
    part_a: list[list[int]],
    part_b: list[list[int]],
) -> float | None:
    """Compute Normalized Mutual Information (NMI) between two partitions over common nodes."""
    map_a = {pid: idx for idx, grp in enumerate(part_a) for pid in grp}
    map_b = {pid: idx for idx, grp in enumerate(part_b) for pid in grp}
    common = sorted(set(map_a.keys()) & set(map_b.keys()))
    if len(common) < 2:
        return None
    labels_a = [map_a[pid] for pid in common]
    labels_b = [map_b[pid] for pid in common]
    return round(float(normalized_mutual_info_score(labels_a, labels_b)), 4)


class ClusteringService:
    def __init__(self):
        self.llm = LLMService()

    def cluster_project(
        self,
        db: Session,
        project_id: int,
        n_clusters: int | None = None,
        algorithm: str = "leiden",
        resolution: float | None = None,
        seed: int = 42,
    ) -> list[models.ResearchCluster]:
        """Cluster project papers using Leiden (default) or embedding-Agglomerative, recording modularity/silhouette & NMI."""
        res_val = float(resolution if resolution is not None else os.getenv("LEIDEN_RESOLUTION", "1.0"))

        db.query(models.ResearchCluster).filter(
            models.ResearchCluster.project_id == project_id
        ).delete()
        db.commit()

        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        if len(paper_ids) < 2:
            return []

        papers = db.query(models.Paper).filter(models.Paper.id.in_(paper_ids)).all()
        paper_map = {p.id: p for p in papers}

        # L2-normalized mean paper embeddings in one query
        paper_embs = get_paper_embeddings(db, papers, embed_missing=False)
        valid_paper_ids = [p.id for p in papers if p.id in paper_embs]
        pid_to_idx = {pid: idx for idx, pid in enumerate(valid_paper_ids)}
        X = np.array([paper_embs[pid] for pid in valid_paper_ids], dtype=np.float32) if valid_paper_ids else None

        # Build weighted combined undirected graph from PaperRelations
        nx_graph = nx.Graph()
        for pid in paper_ids:
            nx_graph.add_node(pid)
        relations = (
            db.query(models.PaperRelation)
            .filter(models.PaperRelation.project_id == project_id)
            .all()
        )
        for rel in relations:
            if rel.source_id == rel.target_id or rel.source_id not in paper_map or rel.target_id not in paper_map:
                continue
            w = max(0.01, float(rel.score or 1.0))
            if nx_graph.has_edge(rel.source_id, rel.target_id):
                nx_graph[rel.source_id][rel.target_id]["weight"] = max(
                    nx_graph[rel.source_id][rel.target_id]["weight"], w
                )
            else:
                nx_graph.add_edge(rel.source_id, rel.target_id, weight=w)

        # Compute both partitions for NMI comparison
        leiden_groups, leiden_meta = run_community_partition(nx_graph, resolution=res_val, seed=seed)
        agg_groups_dict, agg_meta = (
            run_agglomerative_silhouette(X, valid_paper_ids, n_clusters=n_clusters)
            if X is not None and len(valid_paper_ids) >= 2
            else ({}, {"n_clusters": 0, "silhouette": 0.0})
        )
        agg_groups = list(agg_groups_dict.values())
        nmi = compute_partition_nmi(leiden_groups, agg_groups)

        use_agg = algorithm.lower().strip() == "agglomerative" or (
            nx_graph.number_of_edges() == 0 and len(agg_groups) > 0
        )

        if use_agg and agg_groups:
            selected_groups = agg_groups
            stored_algo = "AgglomerativeClustering"
            params_payload = {
                **agg_meta,
                "leiden_modularity": leiden_meta.get("modularity"),
                "nmi": nmi,
                "seed": seed,
            }
        else:
            selected_groups = leiden_groups
            stored_algo = leiden_meta.get("algo_name", "Leiden")
            params_payload = {
                "n_clusters": len(selected_groups),
                "modularity": leiden_meta.get("modularity"),
                "silhouette_agglomerative": agg_meta.get("silhouette"),
                "nmi": nmi,
                "resolution": res_val,
                "seed": seed,
                "fallback": leiden_meta.get("fallback"),
            }

        created_clusters: list[models.ResearchCluster] = []
        for group_paper_ids in selected_groups:
            group_papers = [paper_map[pid] for pid in group_paper_ids if pid in paper_map]
            if not group_papers:
                continue

            # Representative paper: closest to centroid if embeddings exist, else highest citations
            group_indices = [pid_to_idx[pid] for pid in group_paper_ids if pid in pid_to_idx]
            if X is not None and group_indices:
                centroid = np.mean(X[group_indices], axis=0)
                idx_distances = {
                    valid_paper_ids[idx]: float(np.linalg.norm(X[idx] - centroid))
                    for idx in group_indices
                }
                rep_id = min(idx_distances.keys(), key=lambda pid: idx_distances[pid])
            else:
                idx_distances = {}
                rep_id = max(group_papers, key=lambda p: p.citation_count or 0).id

            years = [p.year for p in group_papers if p.year]
            year_dist = dict(Counter(str(y) for y in sorted(years)))
            cluster_label, label_evidence = self._generate_cluster_label(group_papers)

            cluster_row = models.ResearchCluster(
                project_id=project_id,
                algorithm=stored_algo,
                params=params_payload,
                version="2.0",
                label=cluster_label,
                label_evidence=label_evidence,
                representative_paper_ids=[rep_id],
                year_distribution=year_dist,
            )
            db.add(cluster_row)
            db.flush()

            for pid in group_paper_ids:
                dist = idx_distances.get(pid, 0.25)
                score = round(max(0.1, 1.0 - dist), 3)
                db.add(models.ClusterMember(
                    cluster_id=cluster_row.id,
                    paper_id=pid,
                    membership_score=score,
                ))

            created_clusters.append(cluster_row)

        db.commit()
        return created_clusters

    def _generate_cluster_label(self, papers: list[models.Paper]) -> tuple[str, dict[str, Any]]:
        """Synthesize a descriptive cluster theme from member titles and abstracts."""
        paper_summaries = [
            f"- '{p.title}' ({p.year or 'n.d.'}): {(p.abstract or '')[:200]}"
            for p in papers[:6]
        ]
        context = "\n".join(paper_summaries)

        if not self.llm.is_available():
            return f"Cluster: {papers[0].title[:40]}...", {"source": "data_centroid", "papers": [p.title for p in papers[:3]]}

        prompt = (
            "Analyze the following group of related research papers. Synthesize a concise, "
            "academically precise thematic label (3 to 6 words) that captures the common method, "
            "problem, or objective of this cluster. Do not include quotes or numbering.\n\n"
            f"Papers:\n{context}"
        )
        try:
            label = self.llm.complete(prompt).strip().strip('"').strip("'")
            return label, {"source": "llm_synthesis", "papers": [p.title for p in papers[:3]]}
        except Exception:
            return f"Thematic Group: {papers[0].title[:35]}", {"source": "fallback"}
