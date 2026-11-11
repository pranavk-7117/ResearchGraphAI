"""
Paper Relations and Citation Resolution Service for ResearchGraphAI.

Builds and resolves relations cleanly without O(N^2) Python loops or N+1 queries:
- Citation edges: O(R) resolution via in-memory lookup dicts + strict title fuzz.ratio >= 95 & year +-1.
- Semantic similarity edges: Mutual k-NN (config SIM_K, default 4) via pgvector cosine distance (<=>)
  over L2-normalized mean paper chunk embeddings, stored once as undirected (source_id < target_id, directed=False).
"""

import os
import re
from typing import Any
from rapidfuzz import fuzz
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app import models
from app.dsa.heap import top_k
from app.services.constants import (
    BASIS_BIBLIOGRAPHIC_COUPLING,
    BASIS_CITATION_METADATA,
    BASIS_EMBEDDING_SIMILARITY,
    RELATION_CITES,
    RELATION_COUPLING,
    RELATION_SIMILAR,
)
from app.services.embeddings import cosine_similarity, get_paper_embeddings

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.IGNORECASE)
_OA_RE = re.compile(r"\b(W\d{6,})\b", re.IGNORECASE)
_ARXIV_RE = re.compile(r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _normalize_title_simple(title: str | None) -> str:
    if not title:
        return ""
    return " ".join(re.sub(r"[^\w\s]", " ", title).lower().split())


def canonical_reference_key(ref: models.PaperReference) -> str | None:
    """Canonical hashable identifier for a PaperReference row used in bibliographic coupling."""
    if ref.cited_paper_id is not None:
        return f"pid:{ref.cited_paper_id}"
    if ref.doi and ref.doi.strip():
        return f"doi:{ref.doi.strip().lower()}"
    if ref.raw_reference and ref.raw_reference.strip():
        clean = " ".join(ref.raw_reference.strip().lower().split())
        return f"raw:{clean[:180]}"
    return None


def compute_bibliographic_coupling_pairs(
    refs_by_paper: dict[int, set[str]],
) -> list[tuple[int, int, float, int]]:
    """
    Compute undirected bibliographic coupling edges (u < v) with Jaccard similarity
    over reference sets: |R_u & R_v| / |R_u | R_v|.
    Returns list of (u, v, jaccard_score, shared_count).
    """
    pids = sorted(pid for pid, rset in refs_by_paper.items() if rset)
    # Inverted index from ref_key -> list of citing paper_ids to skip zero-overlap pairs
    inv: dict[str, list[int]] = {}
    for pid in pids:
        for rkey in refs_by_paper[pid]:
            inv.setdefault(rkey, []).append(pid)

    candidate_pairs: set[tuple[int, int]] = set()
    for plist in inv.values():
        if len(plist) < 2:
            continue
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                u, v = plist[i], plist[j]
                candidate_pairs.add((u, v) if u < v else (v, u))

    edges: list[tuple[int, int, float, int]] = []
    for u, v in sorted(candidate_pairs):
        ru = refs_by_paper[u]
        rv = refs_by_paper[v]
        shared = len(ru & rv)
        if shared == 0:
            continue
        union_len = len(ru | rv)
        jaccard = shared / union_len if union_len > 0 else 0.0
        edges.append((u, v, round(float(jaccard), 4), shared))
    return edges


class RelationsService:
    def _build_citation_lookups(self, papers: list[models.Paper]) -> dict[str, Any]:
        """Build O(1) lookup indices across all candidate papers in the project."""
        doi_map: dict[str, int] = {}
        oa_map: dict[str, int] = {}
        s2_map: dict[str, int] = {}
        arxiv_map: dict[str, int] = {}
        title_hash_map: dict[str, int] = {}
        norm_title_map: dict[str, int] = {}
        year_map: dict[int, int | None] = {}
        title_list: list[tuple[int, str, int | None]] = []

        for p in papers:
            year_map[p.id] = p.year
            if p.doi:
                doi_map[p.doi.strip().lower()] = p.id
            if p.openalex_id:
                oa_full = p.openalex_id.strip().lower()
                oa_short = oa_full.split("/")[-1]
                oa_map[oa_full] = p.id
                oa_map[oa_short] = p.id
            if p.s2_id:
                s2_map[p.s2_id.strip().lower()] = p.id
            if p.arxiv_id:
                arxiv_map[p.arxiv_id.strip().lower()] = p.id
            if p.title_hash:
                title_hash_map[p.title_hash] = p.id
            nt = _normalize_title_simple(p.title)
            if nt:
                norm_title_map[nt] = p.id
                title_list.append((p.id, nt, p.year))

        return {
            "doi": doi_map,
            "oa": oa_map,
            "s2": s2_map,
            "arxiv": arxiv_map,
            "title_hash": title_hash_map,
            "norm_title": norm_title_map,
            "years": year_map,
            "titles": title_list,
        }

    def _resolve_reference(self, ref: models.PaperReference, lookups: dict[str, Any]) -> int | None:
        """Resolve a single PaperReference in O(1) via identifier dicts, with strict fuzzy title fallback."""
        citing_id = ref.citing_paper_id

        if ref.doi:
            tid = lookups["doi"].get(ref.doi.strip().lower())
            if tid and tid != citing_id:
                return tid

        raw = (ref.raw_reference or "").strip()
        if not raw:
            return None

        # Extract identifiers in O(1) lookup
        for m in _DOI_RE.findall(raw):
            tid = lookups["doi"].get(m.lower().rstrip("."))
            if tid and tid != citing_id:
                return tid

        for m in _OA_RE.findall(raw):
            tid = lookups["oa"].get(m.lower())
            if tid and tid != citing_id:
                return tid

        for m in _ARXIV_RE.findall(raw):
            tid = lookups["arxiv"].get(m.lower())
            if tid and tid != citing_id:
                return tid

        raw_lower = raw.lower()
        for s2_id, tid in lookups["s2"].items():
            if tid != citing_id and s2_id in raw_lower:
                return tid

        norm_raw = _normalize_title_simple(raw)
        if norm_raw in lookups["norm_title"]:
            tid = lookups["norm_title"][norm_raw]
            if tid != citing_id:
                return tid

        # Strict full-title fuzzy match: fuzz.ratio >= 95 and equal year +-1 (no partial_ratio)
        year_matches = _YEAR_RE.findall(raw)
        ref_year = int(year_matches[-1]) if year_matches else None
        if len(norm_raw) >= 12:
            for tid, cand_title, cand_year in lookups["titles"]:
                if tid == citing_id:
                    continue
                if ref_year is not None and cand_year is not None and abs(ref_year - cand_year) > 1:
                    continue
                if fuzz.ratio(cand_title, norm_raw) >= 95:
                    return tid

        return None

    def _pgvector_all_top_k_neighbors(
        self,
        db: Session,
        paper_ids: list[int],
        sim_k: int,
    ) -> dict[int, dict[int, float]]:
        """Query top-K nearest neighbors for every paper in a single pgvector LATERAL SQL query."""
        sql = text("""
            WITH paper_embs AS (
                SELECT paper_id, AVG(embedding) AS mean_emb
                FROM paper_chunks
                WHERE paper_id IN :paper_ids
                GROUP BY paper_id
            )
            SELECT
                a.paper_id AS source_id,
                n.neighbor_id,
                n.sim
            FROM paper_embs a
            CROSS JOIN LATERAL (
                SELECT
                    b.paper_id AS neighbor_id,
                    1 - (b.mean_emb <=> a.mean_emb) AS sim
                FROM paper_embs b
                WHERE b.paper_id != a.paper_id
                ORDER BY b.mean_emb <=> a.mean_emb ASC
                LIMIT :k
            ) n;
        """).bindparams(bindparam("paper_ids", expanding=True))
        rows = db.execute(sql, {"paper_ids": paper_ids, "k": sim_k}).fetchall()
        out: dict[int, dict[int, float]] = {}
        for r in rows:
            out.setdefault(int(r.source_id), {})[int(r.neighbor_id)] = float(r.sim)
        return out

    def build_project_relations(
        self,
        db: Session,
        project_id: int,
        sim_k: int | None = None,
    ) -> list[models.PaperRelation]:
        """
        Derive citation metadata edges and mutual k-NN semantic similarity edges
        across papers in a research project using bounded SQL queries.
        """
        k_val = int(sim_k if sim_k is not None else os.getenv("SIM_K", "4"))

        project_papers = (
            db.query(models.ProjectPaper)
            .filter(models.ProjectPaper.project_id == project_id)
            .all()
        )
        paper_ids = [p.paper_id for p in project_papers]
        if not paper_ids:
            return []

        papers = db.query(models.Paper).filter(models.Paper.id.in_(paper_ids)).all()
        refs = (
            db.query(models.PaperReference)
            .filter(models.PaperReference.citing_paper_id.in_(paper_ids))
            .all()
        )
        existing_rels = (
            db.query(models.PaperRelation)
            .filter(models.PaperRelation.project_id == project_id)
            .all()
        )
        existing_keys = {
            (r.source_id, r.target_id, r.relation_type) for r in existing_rels
        }

        created_relations: list[models.PaperRelation] = []

        # 1. Resolve Citation Metadata Edges in O(R)
        lookups = self._build_citation_lookups(papers)
        for ref in refs:
            target_paper_id = self._resolve_reference(ref, lookups)
            if not target_paper_id:
                continue
            ref.cited_paper_id = target_paper_id
            ref.resolved = True
            key = (ref.citing_paper_id, target_paper_id, RELATION_CITES)
            if key not in existing_keys:
                existing_keys.add(key)
                rel = models.PaperRelation(
                    project_id=project_id,
                    source_id=ref.citing_paper_id,
                    target_id=target_paper_id,
                    relation_type=RELATION_CITES,
                    basis=BASIS_CITATION_METADATA,
                    score=1.0,
                    directed=True,
                )
                db.add(rel)
                created_relations.append(rel)

        # 2. Paper Embeddings (L2-normalized mean of all chunks, fallback abstract)
        paper_embeddings = get_paper_embeddings(db, papers, embed_missing=True)

        # 3. Mutual k-NN via single batched pgvector LATERAL query
        top_k_map: dict[int, dict[int, float]] = {}
        try:
            top_k_map = self._pgvector_all_top_k_neighbors(db, paper_ids, k_val)
        except Exception:
            db.rollback()
            top_k_map = {}

        pids_with_emb = list(paper_embeddings.keys())
        for pid in pids_with_emb:
            if pid not in top_k_map and len(pids_with_emb) > 1:
                scored = [
                    (other_id, cosine_similarity(paper_embeddings[pid], paper_embeddings[other_id]))
                    for other_id in pids_with_emb
                    if other_id != pid
                ]
                top_k_map[pid] = {
                    nid: sim for nid, sim in top_k(scored, k_val, key=lambda x: x[1], reverse=True)
                }

        # Mutual k-NN: edge (a, b) with a < b exists iff b in top_k(a) AND a in top_k(b)
        mutual_pairs: dict[tuple[int, int], float] = {}
        for u, u_neighbors in top_k_map.items():
            for v, sim_uv in u_neighbors.items():
                if u in top_k_map.get(v, {}):
                    a, b = (u, v) if u < v else (v, u)
                    if (a, b) not in mutual_pairs:
                        mutual_pairs[(a, b)] = sim_uv

        for (id_a, id_b), sim_val in mutual_pairs.items():
            key = (id_a, id_b, RELATION_SIMILAR)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            rel = models.PaperRelation(
                project_id=project_id,
                source_id=id_a,
                target_id=id_b,
                relation_type=RELATION_SIMILAR,
                basis=BASIS_EMBEDDING_SIMILARITY,
                score=round(float(sim_val), 4),
                directed=False,
            )
            db.add(rel)
            created_relations.append(rel)

        # 4. Bibliographic Coupling Layer (Jaccard similarity over paper_references, no extra API calls)
        refs_by_paper: dict[int, set[str]] = {}
        for ref in refs:
            rkey = canonical_reference_key(ref)
            if rkey:
                refs_by_paper.setdefault(ref.citing_paper_id, set()).add(rkey)

        for id_a, id_b, jaccard, _shared in compute_bibliographic_coupling_pairs(refs_by_paper):
            key = (id_a, id_b, RELATION_COUPLING)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            rel = models.PaperRelation(
                project_id=project_id,
                source_id=id_a,
                target_id=id_b,
                relation_type=RELATION_COUPLING,
                basis=BASIS_BIBLIOGRAPHIC_COUPLING,
                score=jaccard,
                directed=False,
            )
            db.add(rel)
            created_relations.append(rel)

        db.commit()
        return created_relations
