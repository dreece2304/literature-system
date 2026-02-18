"""drop_paper_full_text_column

Revision ID: fc458fc0c8ad
Revises: a1f82a6d225a
Create Date: 2026-01-05 14:34:05.864038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc458fc0c8ad'
down_revision: Union[str, Sequence[str], None] = 'a1f82a6d225a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the deprecated full_text column from papers table.

    Full text content is now stored in the paper_chunks table.
    This migration removes the redundant column that was used before
    the chunked storage approach was implemented.
    """
    # SQLite requires batch operations for ALTER TABLE DROP COLUMN
    # This handles the table recreation automatically
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('full_text')


def downgrade() -> None:
    """Re-add the full_text column (will be empty).

    Note: This cannot restore the original data.
    Use paper_chunks table for full text content.
    """
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(sa.Column('full_text', sa.Text(), nullable=True))
