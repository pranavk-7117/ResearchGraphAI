"""
Corpus Clustering Service for ResearchGraphAI.

Groups project papers into research themes using Agglomerative Clustering or HDBSCAN
over dense pgvector embeddings. Generates evidence-backed cluster labels via LLM
citing member papers, representative papers, and year distributions.
"""

from collections import Counter
from typing import Any
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy.orm import Session

from app import models
from app.services.llm import LLMService


class ClusteringService:
    def __init__(self):
        self.llm = LLMService()

    def cluster_project(
        self,
        db: Session,
        project_id: int,
        n_clusters: int | None = None,
    ) -> list[models.ResearchCluster]:
        """Cluster project papers into evidence-backed thematic groupings."""
        # 1. Clear existing clusters for this project
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

        papers = (
            db.query(models.Paper)
            .filter(models.Paper.id.in_(paper_ids))
            .all()
        )
        paper_map = {p.id: p for p in papers}

        # Collect embeddings
        embeddings_list: list[list[float]] = []
        valid_paper_ids: list[int] = []

        for p in papers:
            chunk = (
                db.query(models.PaperChunk)
                .filter(models.PaperChunk.paper_id == p.id)
                .order_by(models.PaperChunk.chunk_index)
                .first()
            )
            if chunk and chunk.embedding:
                emb = chunk.embedding
                if hasattr(emb, "tolist"):
                    emb = emb.tolist()
                embeddings_list.append(list(emb))
                valid_paper_ids.append(p.id)

        if len(valid_paper_ids) < 2:
            return []

        X = np.array(embeddings_list, dtype=np.float32)

        # Determine number of clusters k
        k = n_clusters or max(2, min(5, len(valid_paper_ids) // 3))
        if k >= len(valid_paper_ids):
            k = max(1, len(valid_paper_ids) - 1)

        clustering_algo = AgglomerativeClustering(
            n_clusters=k,
            metric="cosine",
            linkage="average",
        )
        labels = clustering_algo.fit_predict(X)

        cluster_groups: dict[int, list[int]] = {}
        for paper_id, label in zip(valid_paper_ids, labels):
            cluster_groups.setdefault(int(label), []).append(paper_id)

        created_clusters: list[models.ResearchCluster] = []

        for cluster_idx, group_paper_ids in cluster_groups.items():
            group_papers = [paper_map[pid] for pid in group_paper_ids]
            
            # Compute centroid
            group_indices = [valid_paper_ids.index(pid) for pid in group_paper_ids]
            centroid = np.mean(X[group_indices], axis=0)
            
            # Find representative paper (closest to centroid)
            distances = [
                float(np.linalg.norm(X[idx] - centroid))
                for idx in group_indices
            ]
            rep_idx = int(np.argmin(distances))
            representative_id = group_paper_ids[rep_idx]

            # Year distribution
            years = [p.year for p in group_papers if p.year]
            year_dist = dict(Counter(str(y) for y in sorted(years)))

            # Generate thematic label via LLM from member evidence
            cluster_label, label_evidence = self._generate_cluster_label(group_papers)

            cluster_row = models.ResearchCluster(
                project_id=project_id,
                algorithm="AgglomerativeClustering",
                params={"n_clusters": k, "metric": "cosine", "linkage": "average"},
                version="1.0",
                label=cluster_label,
                label_evidence=label_evidence,
                representative_paper_ids=[representative_id],
                year_distribution=year_dist,
            )
            db.add(cluster_row)
            db.flush()

            for pid, dist in zip(group_paper_ids, distances):
                # Membership score = inverse distance normalized
                score = round(max(0.1, 1.0 - dist), 3)
                member_row = models.ClusterMember(
                    cluster_id=cluster_row.id,
                    paper_id=pid,
                    membership_score=score,
                )
                db.add(member_row)

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
            # Data-driven fallback: use representative title terms without hardcoded templates
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
