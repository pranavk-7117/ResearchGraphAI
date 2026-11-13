"""r3_facts_schema_and_lists

Revision ID: g7h8i9j01107
Revises: f60708091006
Create Date: 2026-11-14 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "g7h8i9j01107"
down_revision: Union[str, Sequence[str], None] = "f60708091006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add explicit extraction states, paper kind, open challenges, and fulltext notes."""
    op.add_column("paper_facts", sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"))
    op.create_index("ix_paper_facts_status", "paper_facts", ["status"])
    op.add_column("paper_facts", sa.Column("source_scope", sa.String(length=50), nullable=False, server_default="abstract_only"))
    op.add_column("paper_facts", sa.Column("paper_kind", sa.String(length=50), nullable=False, server_default="unknown"))
    op.add_column("paper_facts", sa.Column("error_reason", sa.Text(), nullable=True))
    op.add_column("paper_facts", sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("paper_facts", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("paper_facts", sa.Column("open_challenges", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.add_column("project_papers", sa.Column("fulltext_note", sa.String(length=100), nullable=True))

    # Backfill extraction status based on existing evidence
    op.execute(
        """
        UPDATE paper_facts
        SET status = 'extracted'
        WHERE claimed_contributions IS NOT NULL
          AND (limitations IS NOT NULL OR future_work IS NOT NULL);
        """
    )
    op.execute(
        """
        UPDATE paper_facts
        SET status = 'source_limited'
        WHERE claimed_contributions IS NOT NULL
          AND status = 'pending';
        """
    )


def downgrade() -> None:
    """Reversibly remove Round 3 facts columns and fulltext note."""
    op.drop_column("project_papers", "fulltext_note")
    op.drop_column("paper_facts", "open_challenges")
    op.drop_column("paper_facts", "last_attempt_at")
    op.drop_column("paper_facts", "attempts")
    op.drop_column("paper_facts", "error_reason")
    op.drop_column("paper_facts", "paper_kind")
    op.drop_column("paper_facts", "source_scope")
    op.drop_index("ix_paper_facts_status", table_name="paper_facts")
    op.drop_column("paper_facts", "status")
