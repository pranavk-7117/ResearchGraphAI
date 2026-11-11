"""t1_hybrid_fts_gin

Revision ID: a1b2c3d4e501
Revises: 5d4d80a9f2aa
Create Date: 2026-11-11 11:25:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e501"
down_revision: Union[str, Sequence[str], None] = "5d4d80a9f2aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add generated tsvector column on paper_chunks and GIN indexes for hybrid FTS."""
    op.execute(
        "ALTER TABLE paper_chunks ADD COLUMN IF NOT EXISTS text_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text, ''))) STORED;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_paper_chunks_text_tsv_gin "
        "ON paper_chunks USING gin (text_tsv);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_papers_title_abstract_tsv_gin "
        "ON papers USING gin (to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(abstract, '')));"
    )


def downgrade() -> None:
    """Drop FTS GIN indexes and generated tsvector column."""
    op.execute("DROP INDEX IF EXISTS ix_papers_title_abstract_tsv_gin;")
    op.execute("DROP INDEX IF EXISTS ix_paper_chunks_text_tsv_gin;")
    op.execute("ALTER TABLE paper_chunks DROP COLUMN IF EXISTS text_tsv;")
