"""add_claim_citations_table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-01-21

Adds claim_citations table for tracking claims in papers with their
cited references. Enables:
- Finding source papers for specific claims
- Building citation chains (A cites B cites C)
- Verifying if cited papers support claims
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create claim_citations table for tracking claims with their cited references."""
    op.create_table(
        'claim_citations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('paper_id', sa.Integer(), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('claim_text', sa.Text(), nullable=False),
        sa.Column('citation_numbers', sa.JSON()),  # [17, 23]
        sa.Column('section', sa.String(50)),  # introduction, methods, etc.
        sa.Column('chunk_index', sa.Integer()),  # Which chunk this came from
        sa.Column('claim_type', sa.String(50)),  # fact, method, comparison, limitation
        sa.Column('reference_ids', sa.JSON()),  # Links to paper_references
        sa.Column('matched_paper_ids', sa.JSON()),  # Links to papers in library
        sa.Column('match_statuses', sa.JSON()),  # Status for each citation
        sa.Column('importance', sa.String(20)),  # high, medium, low
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Indexes for efficient queries
    op.create_index('ix_claim_citations_paper_id', 'claim_citations', ['paper_id'])
    op.create_index('ix_claim_citations_section', 'claim_citations', ['section'])
    op.create_index('ix_claim_citations_claim_type', 'claim_citations', ['claim_type'])


def downgrade() -> None:
    """Drop claim_citations table."""
    op.drop_index('ix_claim_citations_claim_type', 'claim_citations')
    op.drop_index('ix_claim_citations_section', 'claim_citations')
    op.drop_index('ix_claim_citations_paper_id', 'claim_citations')
    op.drop_table('claim_citations')
