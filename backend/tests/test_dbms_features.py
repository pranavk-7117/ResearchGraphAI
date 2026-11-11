"""
Live PostgreSQL DBMS Tests for T15: Views, Materialized Views, Triggers, WITH RECURSIVE, Window RANK().
"""

import uuid
from sqlalchemy import text

from app import models
from app.database import SessionLocal
from app.dsa.graph import Graph as DSAGraph, bfs
from app.services.dbms_queries import (
    get_citation_ancestors_recursive,
    get_cluster_representatives_window,
    get_project_stats_from_view,
    refresh_field_growth_mv,
)


def test_dbms_trigger_views_recursive_cte_and_window_rank():
    """Exercise live Supabase PostgreSQL trigger, views, MV, WITH RECURSIVE vs BFS, and RANK() OVER."""
    db = SessionLocal()
    tag = f"dbms_test_{uuid.uuid4().hex[:8]}"
    profile = models.Profile(id=tag, email=f"{tag}@example.com", full_name="DBMS Test")
    db.add(profile)
    db.flush()
    project = models.ResearchProject(user_id=tag, topic=f"DBMS Test {tag}")
    db.add(project)
    db.flush()
    initial_version = project.corpus_version

    # Create 4 papers: P4 -> P3 -> P2 -> P1 (and P4 -> P2)
    papers = [
        models.Paper(title=f"{tag}_P1", title_hash=f"{tag}_h1", year=2018, citation_count=120),
        models.Paper(title=f"{tag}_P2", title_hash=f"{tag}_h2", year=2020, citation_count=80),
        models.Paper(title=f"{tag}_P3", title_hash=f"{tag}_h3", year=2022, citation_count=15),
        models.Paper(title=f"{tag}_P4", title_hash=f"{tag}_h4", year=2024, citation_count=5),
    ]
    for p in papers:
        db.add(p)
    db.flush()

    try:
        # 1. Trigger test: inserting into project_papers bumps corpus_version
        for idx, p in enumerate(papers):
            db.add(models.ProjectPaper(
                project_id=project.id,
                paper_id=p.id,
                selected=(idx < 2),
                processing_status="completed" if idx == 0 else "discovered",
            ))
        db.commit()
        db.refresh(project)
        assert project.corpus_version >= initial_version + 4

        # 2. View + Materialized View test
        refresh_field_growth_mv(db)
        stats = get_project_stats_from_view(db, project.id)
        assert stats["total_papers"] == 4
        assert stats["selected_papers"] == 2
        assert stats["processed_papers"] == 1
        assert abs(stats["avg_citation_count"] - 55.0) < 0.01
        assert stats["min_year"] == 2018
        assert stats["max_year"] == 2024
        assert len(stats["field_growth"]) == 4

        # 3. WITH RECURSIVE vs hand-built DSA BFS oracle (P4 cites P3, P3 cites P2, P2 cites P1, P4 cites P2)
        p1, p2, p3, p4 = papers
        edges = [(p4.id, p3.id), (p3.id, p2.id), (p2.id, p1.id), (p4.id, p2.id)]
        for src, tgt in edges:
            db.add(models.PaperRelation(
                project_id=project.id,
                source_id=src,
                target_id=tgt,
                relation_type="cites",
                basis="citation_metadata",
                directed=True,
                score=1.0,
            ))
        db.commit()

        cte_rows = get_citation_ancestors_recursive(db, project.id, p4.id, max_depth=6)
        cte_depths = {r["paper_id"]: r["depth"] for r in cte_rows}

        dsa_g = DSAGraph(directed=True)
        for p in papers:
            dsa_g.add_node(p.id)
        for src, tgt in edges:
            dsa_g.add_edge(src, tgt)
        bfs_nodes = bfs(dsa_g, p4.id)
        assert set(cte_depths.keys()) == set(bfs_nodes[1:])
        assert cte_depths == {p3.id: 1, p2.id: 1, p1.id: 2}

        # 4. Window RANK() OVER (PARTITION BY cluster_id ORDER BY citation_count DESC)
        cluster = models.ResearchCluster(project_id=project.id, algorithm="leiden", label=f"{tag}_Cluster")
        db.add(cluster)
        db.flush()
        for p in papers:
            db.add(models.ClusterMember(cluster_id=cluster.id, paper_id=p.id))
        db.commit()

        reps = get_cluster_representatives_window(db, project.id, top_n=2)
        assert len(reps) == 2
        assert reps[0]["paper_id"] == p1.id and reps[0]["cluster_rank"] == 1
        assert reps[1]["paper_id"] == p2.id and reps[1]["cluster_rank"] == 2

        # 5. Trigger DELETE test
        ver_before_del = project.corpus_version
        db.query(models.ProjectPaper).filter(
            models.ProjectPaper.project_id == project.id,
            models.ProjectPaper.paper_id == p4.id,
        ).delete()
        db.commit()
        db.refresh(project)
        assert project.corpus_version == ver_before_del + 1
    finally:
        db.rollback()
        db.query(models.ResearchProject).filter(models.ResearchProject.id == project.id).delete()
        db.query(models.Profile).filter(models.Profile.id == tag).delete()
        db.query(models.Paper).filter(models.Paper.title_hash.like(f"{tag}_%")).delete(synchronize_session=False)
        db.commit()
        db.close()
