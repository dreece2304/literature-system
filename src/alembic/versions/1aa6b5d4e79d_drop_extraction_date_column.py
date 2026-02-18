"""drop_extraction_date_column

Revision ID: 1aa6b5d4e79d
Revises: 3190e4a915cb
Create Date: 2026-01-06

Drop legacy extraction_date column from paper_contents.
Data has been migrated to quick_extraction_date and deep_extraction_date.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1aa6b5d4e79d'
down_revision: Union[str, Sequence[str], None] = '3190e4a915cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy extraction_date column."""
    op.drop_column('paper_contents', 'extraction_date')


def downgrade() -> None:
    """Restore extraction_date column."""
    op.add_column(
        'paper_contents',
        sa.Column('extraction_date', sa.DateTime(), nullable=True)
    )
    # Restore data from quick/deep columns
    op.execute(
        "UPDATE paper_contents "
        "SET extraction_date = COALESCE(deep_extraction_date, quick_extraction_date)"
    )
