"""
PostgreSQL Relational & Analytical Queries for ResearchGraphAI (T15 DBMS Additions).

Provides:
- View-backed project summary stats (`v_project_paper_stats`) eliminating N+1 counts
- Materialized view field growth queries (`mv_field_growth`) and write-path refresh
- Recursive CTE (`WITH RECURSIVE`) citation ancestor traversal with cycle guard
- Window function (`RANK() OVER`) cluster representative ranking
"""

from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session


def list_user_project_stats(db: Session, user_id: str) -> dict[int, dict[str, Any]]:
    """Fetch per-project aggregate stats from `v_project_paper_stats` in one query."""
    rows = db.execute(
        text(
            """
            SELECT project_id, corpus_version, total_papers, selected_papers,
                   processed_papers, avg_citation_count, min_year, max_year
            FROM v_project_paper_stats
            WHERE user_id = :uid
            """
        ),
        {"uid": user_id},
    ).mappings().all()
    return {
        int(r["project_id"]): {
            "project_id": int(r["project_id"]),
            "corpus_version": int(r["corpus_version"] or 1),
            "total_papers": int(r["total_papers"] or 0),
            "selected_papers": int(r["selected_papers"] or 0),
            "processed_papers": int(r["processed_papers"] or 0),
            "avg_citation_count": float(r["avg_citation_count"] or 0.0),
            "min_year": r["min_year"],
            "max_year": r["max_year"],
        }
        for r in rows
    }


def get_project_stats_from_view(db: Session, project_id: int) -> dict[str, Any]:
    """Read `v_project_paper_stats` and `mv_field_growth` for a single project (read-only)."""
    row = db.execute(
        text(
            """
            SELECT project_id, corpus_version, total_papers, selected_papers,
                   processed_papers, avg_citation_count, min_year, max_year
            FROM v_project_paper_stats
            WHERE project_id = :pid
            """
        ),
        {"pid": project_id},
    ).mappings().first()

    growth_rows = db.execute(
        text(
            """
            SELECT year, paper_count, total_citations
            FROM mv_field_growth
            WHERE project_id = :pid
            ORDER BY year ASC
            """
        ),
        {"pid": project_id},
    ).mappings().all()

    base = (
        {
            "project_id": int(row["project_id"]),
            "corpus_version": int(row["corpus_version"] or 1),
            "total_papers": int(row["total_papers"] or 0),
            "selected_papers": int(row["selected_papers"] or 0),
            "processed_papers": int(row["processed_papers"] or 0),
            "avg_citation_count": float(row["avg_citation_count"] or 0.0),
            "min_year": row["min_year"],
            "max_year": row["max_year"],
        }
        if row
        else {
            "project_id": project_id,
            "corpus_version": 1,
            "total_papers": 0,
            "selected_papers": 0,
            "processed_papers": 0,
            "avg_citation_count": 0.0,
            "min_year": None,
            "max_year": None,
        }
    )
    base["field_growth"] = [
        {
            "year": int(g["year"]),
            "paper_count": int(g["paper_count"]),
            "total_citations": int(g["total_citations"]),
        }
        for g in growth_rows
    ]
    return base


def refresh_field_growth_mv(db: Session) -> None:
    """Refresh materialized view `mv_field_growth` (write-side only)."""
    db.execute(text("REFRESH MATERIALIZED VIEW mv_field_growth;"))
    db.commit()


def get_citation_ancestors_recursive(
    db: Session,
    project_id: int,
    paper_id: int,
    max_depth: int = 6,
) -> list[dict[str, Any]]:
    """
    Traverse citation ancestors (papers cited directly or transitively by `paper_id`)
    via PostgreSQL `WITH RECURSIVE` CTE with explicit array-path cycle detection.
    """
    rows = db.execute(
        text(
            """
            WITH RECURSIVE ancestors AS (
                SELECT
                    r.target_id AS paper_id,
                    1 AS depth,
                    ARRAY[r.source_id, r.target_id] AS path
                FROM paper_relations r
                WHERE r.project_id = :pid
                  AND r.relation_type = 'cites'
                  AND r.source_id = :paper_id

                UNION ALL

                SELECT
                    r.target_id AS paper_id,
                    a.depth + 1 AS depth,
                    a.path || r.target_id AS path
                FROM paper_relations r
                JOIN ancestors a ON r.source_id = a.paper_id
                WHERE r.project_id = :pid
                  AND r.relation_type = 'cites'
                  AND a.depth < :max_depth
                  AND NOT (r.target_id = ANY(a.path))
            ),
            dedup AS (
                SELECT paper_id, MIN(depth) AS min_depth
                FROM ancestors
                GROUP BY paper_id
            )
            SELECT d.paper_id, d.min_depth AS depth, p.title, p.year, p.doi
            FROM dedup d
            JOIN papers p ON p.id = d.paper_id
            ORDER BY d.min_depth ASC, p.year ASC NULLS LAST, d.paper_id ASC;
            """
        ),
        {"pid": project_id, "paper_id": paper_id, "max_depth": max_depth},
    ).mappings().all()

    return [
        {
            "paper_id": int(r["paper_id"]),
            "depth": int(r["depth"]),
            "title": r["title"],
            "year": r["year"],
            "doi": r["doi"],
        }
        for r in rows
    ]


def get_cluster_representatives_window(
    db: Session,
    project_id: int,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Rank representative papers per cluster using `RANK() OVER (PARTITION BY cluster_id ...)`."""
    rows = db.execute(
        text(
            """
            WITH ranked AS (
                SELECT
                    rc.id AS cluster_id,
                    rc.label AS cluster_label,
                    p.id AS paper_id,
                    p.title,
                    p.year,
                    COALESCE(p.citation_count, 0) AS citation_count,
                    RANK() OVER (
                        PARTITION BY cm.cluster_id
                        ORDER BY COALESCE(p.citation_count, 0) DESC, p.id ASC
                    ) AS cluster_rank
                FROM cluster_members cm
                JOIN research_clusters rc ON rc.id = cm.cluster_id
                JOIN papers p ON p.id = cm.paper_id
                WHERE rc.project_id = :pid
            )
            SELECT cluster_id, cluster_label, paper_id, title, year, citation_count, cluster_rank
            FROM ranked
            WHERE cluster_rank <= :top_n
            ORDER BY cluster_id ASC, cluster_rank ASC;
            """
        ),
        {"pid": project_id, "top_n": top_n},
    ).mappings().all()

    return [
        {
            "cluster_id": int(r["cluster_id"]),
            "cluster_label": r["cluster_label"],
            "paper_id": int(r["paper_id"]),
            "title": r["title"],
            "year": r["year"],
            "citation_count": int(r["citation_count"]),
            "cluster_rank": int(r["cluster_rank"]),
        }
        for r in rows
    ]
