"""
Corpus Clustering & Community Detection Service for ResearchGraphAI.

Supports:
1. Leiden community detection on the weighted combined graph (igraph + leidenalg,
   with logged fallback to NetworkX louvain_communities / greedy_modularity_communities)
   guaranteeing connected communities and deterministic output with a fixed seed.
2. Embedding-based Agglomerative Clustering with automatic k selection via
   cosine silhouette score over k in [2, min(8, n // 3)].
3. Minimum cluster size enforcement (MIN_CLUSTER_SIZE = 3): merges any small cluster
   (< 3 papers) into the most similar large cluster via centroid cosine similarity.
4. Class-based TF-IDF (c-TF-IDF) keyword labels generated from titles and abstracts
   (e.g., 'Gait Analysis · Pressure Sensor · Diabetic Foot').

Stores modularity (community), silhouette (agglomerative), and NMI agreement
between both partitions in ResearchCluster.params.
"""

from collections import Counter
import logging
import math
import os
import re
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

MIN_CLUSTER_SIZE = 3

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an", "and",
    "any", "approach", "approaches", "are", "as", "at", "based", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "method", "methods", "model", "models", "more", "most", "my", "myself", "no",
    "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours",
    "ourselves", "out", "over", "own", "paper", "papers", "performance", "present",
    "presented", "propose", "proposed", "research", "result", "results", "same", "she",
    "should", "show", "shows", "so", "some", "study", "studies", "such", "system", "systems",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "use", "used",
    "uses", "using", "very", "was", "we", "were", "what", "when", "where", "which",
    "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
    "yourselves"
}


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
    Cluster embedding matrix X using AgglomerativeClustering, picking k in [2, min(8, n // 3)]
    via cosine silhouette score when n_clusters is None.
    """
    n = len(paper_ids)
    if n < 2:
        return {0: list(paper_ids)}, {"n_clusters": n, "silhouette": 0.0}

    best_k = n_clusters
    best_labels = None
    best_sil = -1.0

    if best_k is None:
        max_k = min(8, max(2, n // 3))
        max_k = min(max_k, n - 1)
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


def merge_small_clusters(
    groups: list[list[int]],
    X: np.ndarray | None,
    valid_paper_ids: list[int],
    min_size: int = MIN_CLUSTER_SIZE,
    nx_graph: nx.Graph | None = None,
) -> list[list[int]]:
    """
    Enforce min_size for all clusters.
    If total papers < min_size, returns a single cluster with all papers.
    Otherwise, merges any cluster with < min_size papers into the most similar
    large cluster (via cosine similarity of paper to cluster centroid, or graph adjacency).
    """
    all_pids = [pid for g in groups for pid in g]
    if len(all_pids) <= min_size:
        return [all_pids] if all_pids else []

    pid_to_idx = {pid: i for i, pid in enumerate(valid_paper_ids)} if valid_paper_ids else {}

    large_groups = [list(g) for g in groups if len(g) >= min_size]
    small_groups = [list(g) for g in groups if len(g) < min_size]

    if not small_groups:
        return large_groups

    if not large_groups:
        # All groups were small, but total papers >= min_size: combine and partition into valid sizes
        combined: list[int] = []
        for g in small_groups:
            combined.extend(g)
        chunks: list[list[int]] = []
        cur: list[int] = []
        for pid in combined:
            cur.append(pid)
            if len(cur) >= min_size and (len(combined) - len(cur) >= min_size or len(combined) - len(cur) == 0):
                chunks.append(cur)
                cur = []
        if cur:
            if chunks:
                chunks[-1].extend(cur)
            else:
                chunks.append(cur)
        return chunks

    # Merge each small group into the best large group
    for sm in small_groups:
        for pid in sm:
            best_idx = 0
            best_score = -1e9
            for idx, lg in enumerate(large_groups):
                # 1. Cosine similarity to centroid if embeddings available
                if X is not None and pid in pid_to_idx:
                    lg_indices = [pid_to_idx[p] for p in lg if p in pid_to_idx]
                    if lg_indices:
                        centroid = np.mean(X[lg_indices], axis=0)
                        c_norm = np.linalg.norm(centroid)
                        if c_norm > 1e-6:
                            centroid = centroid / c_norm
                        score = float(np.dot(X[pid_to_idx[pid]], centroid))
                    else:
                        score = 0.0
                # 2. Graph adjacency fallback
                elif nx_graph is not None and nx_graph.has_node(pid):
                    score = sum(
                        float(nx_graph[pid][other].get("weight", 1.0))
                        for other in lg
                        if nx_graph.has_edge(pid, other)
                    )
                else:
                    score = -len(lg)

                if score > best_score:
                    best_score = score
                    best_idx = idx

            large_groups[best_idx].append(pid)

    return large_groups


def compute_ctfidf_labels(
    clusters_papers: list[list[models.Paper]],
) -> list[tuple[str, dict[str, Any]]]:
    """
    Generate distinguishing cluster labels using class-based TF-IDF (c-TF-IDF)
    over member titles and abstracts.
    """
    num_clusters = len(clusters_papers)
    if num_clusters == 0:
        return []

    # Tokenize each cluster into unigrams and bigrams
    cluster_term_counts: list[Counter] = []
    for papers in clusters_papers:
        c_counter: Counter = Counter()
        for p in papers:
            text = f"{p.title or ''} {p.abstract or ''}".lower()
            tokens = [t for t in re.findall(r"[a-z0-9]+", text) if len(t) >= 3 and t not in STOP_WORDS]
            for t in tokens:
                c_counter[t] += 1
            # Bigrams
            for i in range(len(tokens) - 1):
                w1, w2 = tokens[i], tokens[i + 1]
                bigram = f"{w1} {w2}"
                c_counter[bigram] += 2  # Boost bigrams slightly for descriptive phrases
        cluster_term_counts.append(c_counter)

    # Document/cluster frequency DF(t)
    df_counts: Counter = Counter()
    for c_counter in cluster_term_counts:
        for t in c_counter:
            df_counts[t] += 1

    labels: list[tuple[str, dict[str, Any]]] = []

    for idx, c_counter in enumerate(cluster_term_counts):
        total_words = max(1, sum(c_counter.values()))
        scores: list[tuple[str, float]] = []

        for term, count in c_counter.items():
            tf = count / total_words
            idf = math.log(1.0 + (num_clusters / max(1, df_counts[term])))
            score = tf * idf
            scores.append((term, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        selected_terms: list[tuple[str, float]] = []
        selected_words: set[str] = set()

        for term, sc in scores:
            parts = term.split()
            if any(p in selected_words for p in parts) and len(selected_terms) > 0:
                continue
            selected_terms.append((term, sc))
            for p in parts:
                selected_words.add(p)
            if len(selected_terms) >= 3:
                break

        if not selected_terms:
            papers = clusters_papers[idx]
            fallback_title = papers[0].title[:30] if papers else "Cluster"
            labels.append((f"Cluster: {fallback_title}", {"source": "fallback_empty"}))
            continue

        formatted_label = " · ".join(
            " ".join(w.capitalize() for w in t.split()) for t, _ in selected_terms
        )
        labels.append((
            formatted_label,
            {
                "source": "c_tf_idf",
                "top_terms": [{"term": t, "score": round(sc, 4)} for t, sc in selected_terms],
            },
        ))

    return labels


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

        # Build weighted combined undirected graph: weight = 0.5 * citation + 0.5 * similarity
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
            is_citation = (rel.relation_type == "cites")
            score = float(rel.score or (1.0 if is_citation else 0.5))
            w = 0.5 * (1.0 if is_citation else 0.0) + 0.5 * score
            w = max(0.01, w)
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

        # K5: Enforce MIN_CLUSTER_SIZE = 3 by merging small clusters into most similar cluster
        selected_groups = merge_small_clusters(
            selected_groups,
            X=X,
            valid_paper_ids=valid_paper_ids,
            min_size=MIN_CLUSTER_SIZE,
            nx_graph=nx_graph,
        )

        # Build group paper lists
        group_papers_list = [
            [paper_map[pid] for pid in group_paper_ids if pid in paper_map]
            for group_paper_ids in selected_groups
        ]
        group_papers_list = [gp for gp in group_papers_list if gp]

        # K5: Compute descriptive c-TF-IDF keyword labels
        ctfidf_labels = compute_ctfidf_labels(group_papers_list)

        created_clusters: list[models.ResearchCluster] = []
        for grp_idx, group_papers in enumerate(group_papers_list):
            group_paper_ids = [p.id for p in group_papers]
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

            cluster_label, label_evidence = (
                ctfidf_labels[grp_idx]
                if grp_idx < len(ctfidf_labels)
                else (f"Cluster {grp_idx + 1}", {"source": "default"})
            )

            cluster_row = models.ResearchCluster(
                project_id=project_id,
                algorithm=stored_algo,
                params={**params_payload, "min_cluster_size": MIN_CLUSTER_SIZE, "merged_k": len(group_papers_list)},
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
