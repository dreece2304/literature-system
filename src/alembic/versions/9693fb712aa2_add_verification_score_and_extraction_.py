"""add verification_score and extraction_checkpoint

Revision ID: 9693fb712aa2
Revises: b3c4d5e6f7a8
Create Date: 2026-07-25 20:30:52.842966

Adds:
    paper_contents.verification_score (indexed) - composite verification score, 0-1
    extraction_metadata.extraction_checkpoint - ChunkProcessingState snapshot for crash recovery

Note: autogenerate also detected unrelated pre-existing schema drift (FTS5 shadow
tables, index-naming differences on paper_references, a unique-constraint rename
on paper_citations, and a redundant nullable/autoincrement alter on
paper_references.id). That noise has been stripped; this migration contains only
the two intended column additions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9693fb712aa2'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add verification_score and extraction_checkpoint columns."""
    op.add_column('extraction_metadata', sa.Column('extraction_checkpoint', sa.JSON(), nullable=True))
    op.add_column('paper_contents', sa.Column('verification_score', sa.Float(), nullable=True))
    op.create_index(op.f('ix_paper_contents_verification_score'), 'paper_contents', ['verification_score'], unique=False)


def downgrade() -> None:
    """Remove verification_score and extraction_checkpoint columns."""
    op.drop_index(op.f('ix_paper_contents_verification_score'), table_name='paper_contents')
    op.drop_column('paper_contents', 'verification_score')
    op.drop_column('extraction_metadata', 'extraction_checkpoint')
