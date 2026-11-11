"""t5_gap_statement_hash_unique

Revision ID: c3d4e5f60703
Revises: b2c3d4e5f602
Create Date: 2026-11-11 11:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60703"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add statement_hash on research_gaps with unique constraint on (project_id, corpus_version, statement_hash)."""
    op.add_column("research_gaps", sa.Column("statement_hash", sa.String(length=64), nullable=True))
    op.execute(
        "UPDATE research_gaps "
        "SET statement_hash = encode(sha256(convert_to(lower(trim(gap_statement)), 'UTF8')), 'hex') "
        "WHERE statement_hash IS NULL;"
    )
    # Delete pre-existing duplicates before creating unique constraint (keep highest strength / lowest id)
    op.execute(
        """
        DELETE FROM research_gaps a
        USING research_gaps b
        WHERE a.project_id = b.project_id
          AND a.corpus_version = b.corpus_version
          AND a.statement_hash = b.statement_hash
          AND (a.evidence_strength < b.evidence_strength OR (a.evidence_strength = b.evidence_strength AND a.id > b.id));
        """
    )
    op.alter_column("research_gaps", "statement_hash", existing_type=sa.String(length=64), nullable=False)
    op.create_unique_constraint(
        "uq_research_gaps_proj_ver_hash",
        "research_gaps",
        ["project_id", "corpus_version", "statement_hash"],
    )


def downgrade() -> None:
    """Drop unique constraint and statement_hash column from research_gaps."""
    op.drop_constraint("uq_research_gaps_proj_ver_hash", "research_gaps", type_="unique")
    op.drop_column("research_gaps", "statement_hash")
