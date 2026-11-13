"""r3_facts_check_constraints

Revision ID: h8i9j0110808
Revises: g7h8i9j01107
Create Date: 2026-11-14 02:55:00.000000

Adds database CHECK constraints on paper_facts for status, source_scope, and paper_kind.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h8i9j0110808"
down_revision: Union[str, None] = "g7h8i9j01107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Clean up any invalid legacy status/source_scope/paper_kind values before enforcing
    op.execute("""
        UPDATE paper_facts
        SET status = 'pending'
        WHERE status NOT IN ('extracted', 'not_stated', 'source_limited', 'failed', 'pending');
    """)
    op.execute("""
        UPDATE paper_facts
        SET source_scope = 'abstract_only'
        WHERE source_scope NOT IN ('abstract_only', 'full_text_pdf', 'full_text_html', 'metadata_only', 'abstract_fallback');
    """)
    op.execute("""
        UPDATE paper_facts
        SET paper_kind = 'unknown'
        WHERE paper_kind NOT IN ('survey', 'empirical', 'system', 'theory', 'unknown');
    """)

    # 2. Add CHECK constraints
    op.create_check_constraint(
        constraint_name="ck_paper_facts_status",
        table_name="paper_facts",
        condition="status IN ('extracted', 'not_stated', 'source_limited', 'failed', 'pending')",
    )
    op.create_check_constraint(
        constraint_name="ck_paper_facts_source_scope",
        table_name="paper_facts",
        condition="source_scope IN ('abstract_only', 'full_text_pdf', 'full_text_html', 'metadata_only', 'abstract_fallback')",
    )
    op.create_check_constraint(
        constraint_name="ck_paper_facts_paper_kind",
        table_name="paper_facts",
        condition="paper_kind IN ('survey', 'empirical', 'system', 'theory', 'unknown')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_paper_facts_paper_kind", "paper_facts", type_="check")
    op.drop_constraint("ck_paper_facts_source_scope", "paper_facts", type_="check")
    op.drop_constraint("ck_paper_facts_status", "paper_facts", type_="check")
