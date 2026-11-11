"""t11_project_paper_sources

Revision ID: d4e5f6070804
Revises: c3d4e5f60703
Create Date: 2026-11-11 12:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4e5f6070804"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add sources JSONB array on project_papers to track multi-source capture overlap."""
    op.add_column(
        "project_papers",
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE project_papers pp
        SET sources = CASE
            WHEN p.source_name IS NOT NULL AND length(trim(p.source_name)) > 0
                THEN jsonb_build_array(lower(p.source_name))
            ELSE '[]'::jsonb
        END
        FROM papers p
        WHERE pp.paper_id = p.id
          AND pp.sources = '[]'::jsonb;
        """
    )


def downgrade() -> None:
    """Drop sources column from project_papers."""
    op.drop_column("project_papers", "sources")
