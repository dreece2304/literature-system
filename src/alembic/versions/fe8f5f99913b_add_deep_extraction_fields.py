"""add_deep_extraction_fields

Revision ID: fe8f5f99913b
Revises: 6a8c7b18a684
Create Date: 2026-01-06

Schema v2.1: Separate quick and deep extraction fields.

Quick extraction (from abstract) persists in:
    paper_type, topics, one_sentence_summary

Deep extraction (from PDF) stores its own versions in:
    deep_paper_type, deep_topics, deep_one_sentence_summary

Plus verification field to compare quick vs deep results.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe8f5f99913b'
down_revision: Union[str, Sequence[str], None] = '6a8c7b18a684'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add deep extraction fields to paper_contents."""
    # Deep tier versions of quick fields
    op.add_column(
        'paper_contents',
        sa.Column('deep_paper_type', sa.String(50), nullable=True)
    )
    op.add_column(
        'paper_contents',
        sa.Column('deep_topics', sa.JSON(), nullable=True)
    )
    op.add_column(
        'paper_contents',
        sa.Column('deep_one_sentence_summary', sa.Text(), nullable=True)
    )

    # Separate model tracking for deep extraction
    op.add_column(
        'paper_contents',
        sa.Column('deep_extractor_model', sa.String(100), nullable=True)
    )

    # Verification field for comparing quick vs deep
    op.add_column(
        'paper_contents',
        sa.Column('verification', sa.JSON(), nullable=True)
    )

    # Update schema version to 2.1
    op.execute(
        "UPDATE paper_contents SET schema_version = '2.1' WHERE schema_version = '2.0'"
    )


def downgrade() -> None:
    """Remove deep extraction fields."""
    op.drop_column('paper_contents', 'verification')
    op.drop_column('paper_contents', 'deep_extractor_model')
    op.drop_column('paper_contents', 'deep_one_sentence_summary')
    op.drop_column('paper_contents', 'deep_topics')
    op.drop_column('paper_contents', 'deep_paper_type')

    # Revert schema version
    op.execute(
        "UPDATE paper_contents SET schema_version = '2.0' WHERE schema_version = '2.1'"
    )
