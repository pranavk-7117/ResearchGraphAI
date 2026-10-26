"""
Paper Relations and Citation Resolution Service for ResearchGraphAI.

Builds and resolves relations:
- Citation edges: from explicit reference metadata / parsed reference lists.
- Semantic similarity edges: from pgvector dense embeddings (clearly labelled as inferred).
- Method/Dataset similarity: from structured paper facts.
"""

from typing import Any
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app import models
from app.services.embeddings import cosine_similarity


class RelationsService:
    def build_project_relations(
        self,
        db: Session,
        project_id: int,
        similarity_threshold: float = 0.52,
    ) -> list[models.PaperRelation]:
        """
        Derive both metadata citation edges and inferred semantic relations
        across papers in a research project.
        """
        # Get all papers in this project
        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        if not paper_ids:
            return []

        papers = (
            db.query(models.Paper)
            .filter(models.Paper.id.in_(paper_ids))
            .all()
        )
        paper_map = {p.id: p for p in papers}

        created_relations: list[models.PaperRelation] = []

        # 1. Resolve Citation Metadata Edges
        # Check references for each paper
        refs = (
            db.query(models.PaperReference)
            .filter(models.PaperReference.citing_paper_id.in_(paper_ids))
            .all()
        )

        for ref in refs:
            target_paper_id = None

            # Direct DOI match
            if ref.doi:
                for p in papers:
                    if p.doi and p.doi.lower() == ref.doi.lower() and p.id != ref.citing_paper_id:
                        target_paper_id = p.id
                        break

            # Raw reference matching (OpenAlex ID, S2 ID, arXiv ID, DOI, or Title)
            if not target_paper_id and ref.raw_reference:
                ref_text_lower = ref.raw_reference.lower()
                for p in papers:
                    if p.id == ref.citing_paper_id:
                        continue
                    # Check OpenAlex ID
                    if p.openalex_id:
                        oa_short = p.openalex_id.split("/")[-1].lower()
                        if oa_short in ref_text_lower:
                            target_paper_id = p.id
                            break
                    # Check S2 ID
                    if p.s2_id and p.s2_id.lower() in ref_text_lower:
                        target_paper_id = p.id
                        break
                    # Check Arxiv ID
                    if p.arxiv_id and p.arxiv_id.lower() in ref_text_lower:
                        target_paper_id = p.id
                        break
                    # Check DOI inside raw reference
                    if p.doi and p.doi.lower() in ref_text_lower:
                        target_paper_id = p.id
                        break
                    # Check Title substring or fuzzy match
                    title_clean = p.title.lower()
                    if len(title_clean) > 15 and title_clean in ref_text_lower:
                        target_paper_id = p.id
                        break
                    elif fuzz.partial_ratio(title_clean, ref_text_lower) > 90:
                        target_paper_id = p.id
                        break

            if target_paper_id:
                ref.cited_paper_id = target_paper_id
                ref.resolved = True

                # Check if relation already exists
                existing = (
                    db.query(models.PaperRelation)
                    .filter(
                        models.PaperRelation.project_id == project_id,
                        models.PaperRelation.source_id == ref.citing_paper_id,
                        models.PaperRelation.target_id == target_paper_id,
                        models.PaperRelation.relation_type == "cites",
                    )
                    .first()
                )
                if not existing:
                    rel = models.PaperRelation(
                        project_id=project_id,
                        source_id=ref.citing_paper_id,
                        target_id=target_paper_id,
                        relation_type="cites",
                        basis="citation_metadata",
                        score=1.0,
                    )
                    db.add(rel)
                    created_relations.append(rel)

        # 2. Derive Semantic Similarity Edges (Inferred)
        # Fetch embeddings from chunks or compute average
        paper_embeddings: dict[int, list[float]] = {}
        for p in papers:
            # Check chunks
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
                paper_embeddings[p.id] = list(emb)

        # Pairwise comparison
        paper_id_list = list(paper_embeddings.keys())
        sim_scores_per_paper: dict[int, list[tuple[float, int]]] = {pid: [] for pid in paper_id_list}
        pairwise_sims: list[tuple[float, int, int]] = []

        for i in range(len(paper_id_list)):
            for j in range(i + 1, len(paper_id_list)):
                id_a = paper_id_list[i]
                id_b = paper_id_list[j]
                sim = cosine_similarity(paper_embeddings[id_a], paper_embeddings[id_b])
                pairwise_sims.append((sim, id_a, id_b))
                sim_scores_per_paper[id_a].append((sim, id_b))
                sim_scores_per_paper[id_b].append((sim, id_a))

        # 1. Connect all pairs meeting similarity threshold
        connected_pairs: set[tuple[int, int]] = set()
        for sim, id_a, id_b in pairwise_sims:
            if sim >= similarity_threshold:
                connected_pairs.add((min(id_a, id_b), max(id_a, id_b)))

        # 2. Ensure every paper has at least top 2 peers connected if similarity >= 0.38
        for pid, peer_sims in sim_scores_per_paper.items():
            peer_sims.sort(key=lambda x: x[0], reverse=True)
            for sim, peer_id in peer_sims[:2]:
                if sim >= 0.38:
                    connected_pairs.add((min(pid, peer_id), max(pid, peer_id)))

        for id_a, id_b in connected_pairs:
            # Check if already connected by citation
            existing_cite = (
                db.query(models.PaperRelation)
                .filter(
                    models.PaperRelation.project_id == project_id,
                    models.PaperRelation.source_id.in_([id_a, id_b]),
                    models.PaperRelation.target_id.in_([id_a, id_b]),
                    models.PaperRelation.relation_type == "cites",
                )
                .first()
            )
            if existing_cite:
                continue

            existing_sim = (
                db.query(models.PaperRelation)
                .filter(
                    models.PaperRelation.project_id == project_id,
                    models.PaperRelation.source_id == id_a,
                    models.PaperRelation.target_id == id_b,
                    models.PaperRelation.relation_type == "similar",
                )
                .first()
            )
            if not existing_sim:
                sim_val = cosine_similarity(paper_embeddings[id_a], paper_embeddings[id_b])
                rel = models.PaperRelation(
                    project_id=project_id,
                    source_id=id_a,
                    target_id=id_b,
                    relation_type="similar",
                    basis="embedding_similarity",
                    score=round(float(sim_val), 4),
                )
                db.add(rel)
                created_relations.append(rel)

        db.commit()
        return created_relations
