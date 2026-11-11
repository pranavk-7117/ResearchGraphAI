"""t12_gap_matrix_cell

Revision ID: e5f607080905
Revises: d4e5f6070804
Create Date: 2026-11-11 12:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e5f607080905"
down_revision: Union[str, Sequence[str], None] = "d4e5f6070804"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable matrix_cell JSONB column on research_gaps for bipartite Method x Task voids."""
    op.add_column(
        "research_gaps",
        sa.Column("matrix_cell", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Remove matrix_cell column from research_gaps."""
    op.drop_column("research_gaps", "matrix_cell")
