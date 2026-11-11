"""t15_dbms_views_trigger

Revision ID: f60708091006
Revises: e5f607080905
Create Date: 2026-11-11 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f60708091006"
down_revision: Union[str, Sequence[str], None] = "e5f607080905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create project stats view, field growth materialized view, and corpus_version trigger."""
    op.execute(
        """
        CREATE OR REPLACE VIEW v_project_paper_stats AS
        SELECT
            rp.id AS project_id,
            rp.user_id,
            rp.topic,
            rp.corpus_version,
            COUNT(pp.id) AS total_papers,
            COUNT(pp.id) FILTER (WHERE pp.selected = TRUE) AS selected_papers,
            COUNT(pp.id) FILTER (WHERE pp.processing_status = 'completed') AS processed_papers,
            COALESCE(ROUND(AVG(p.citation_count)::numeric, 2), 0) AS avg_citation_count,
            MIN(p.year) AS min_year,
            MAX(p.year) AS max_year
        FROM research_projects rp
        LEFT JOIN project_papers pp ON pp.project_id = rp.id
        LEFT JOIN papers p ON p.id = pp.paper_id
        GROUP BY rp.id, rp.user_id, rp.topic, rp.corpus_version;
        """
    )

    op.execute(
        """
        CREATE MATERIALIZED VIEW mv_field_growth AS
        SELECT
            pp.project_id,
            p.year,
            COUNT(DISTINCT pp.paper_id) AS paper_count,
            SUM(COALESCE(p.citation_count, 0)) AS total_citations
        FROM project_papers pp
        JOIN papers p ON p.id = pp.paper_id
        WHERE p.year IS NOT NULL
        GROUP BY pp.project_id, p.year
        ORDER BY pp.project_id, p.year;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_mv_field_growth_proj_year ON mv_field_growth (project_id, year);"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_bump_project_corpus_version()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE research_projects
                SET corpus_version = corpus_version + 1,
                    updated_at = NOW()
                WHERE id = NEW.project_id;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE research_projects
                SET corpus_version = corpus_version + 1,
                    updated_at = NOW()
                WHERE id = OLD.project_id;
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_project_papers_bump_corpus_version
        AFTER INSERT OR DELETE ON project_papers
        FOR EACH ROW
        EXECUTE FUNCTION fn_bump_project_corpus_version();
        """
    )


def downgrade() -> None:
    """Drop corpus_version trigger/function, materialized view, and stats view."""
    op.execute("DROP TRIGGER IF EXISTS trg_project_papers_bump_corpus_version ON project_papers;")
    op.execute("DROP FUNCTION IF EXISTS fn_bump_project_corpus_version();")
    op.execute("DROP INDEX IF EXISTS ix_mv_field_growth_proj_year;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_field_growth;")
    op.execute("DROP VIEW IF EXISTS v_project_paper_stats;")
