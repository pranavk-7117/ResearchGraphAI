"""t4_directed_and_graph_cache

Revision ID: b2c3d4e5f602
Revises: a1b2c3d4e501
Create Date: 2026-11-11 11:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f602"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e501"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add directed flag to paper_relations and graph_analytics_cache table."""
    op.add_column(
        "paper_relations",
        sa.Column("directed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute("UPDATE paper_relations SET directed = false WHERE relation_type = 'similar';")

    op.create_table(
        "graph_analytics_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("corpus_version", sa.Integer(), nullable=False),
        sa.Column("analytics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "corpus_version", name="uq_graph_analytics_cache_proj_ver"),
    )
    op.create_index(op.f("ix_graph_analytics_cache_project_id"), "graph_analytics_cache", ["project_id"], unique=False)


def downgrade() -> None:
    """Remove graph_analytics_cache table and directed column."""
    op.drop_index(op.f("ix_graph_analytics_cache_project_id"), table_name="graph_analytics_cache")
    op.drop_table("graph_analytics_cache")
    op.drop_column("paper_relations", "directed")
