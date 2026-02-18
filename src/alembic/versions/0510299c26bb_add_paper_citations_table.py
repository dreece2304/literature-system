"""add_paper_citations_table

Revision ID: 0510299c26bb
Revises: fe8f5f99913b
Create Date: 2026-01-06 18:49:53.274816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0510299c26bb'
down_revision: Union[str, Sequence[str], None] = 'fe8f5f99913b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create paper_citations table for tracking citation relationships."""
    op.create_table(
        'paper_citations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('citing_paper_id', sa.Integer(), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cited_paper_id', sa.Integer(), sa.ForeignKey('papers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),  # 'openalex', 'semantic_scholar', 'pdf', 'manual'
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        # Unique constraint defined at table creation for SQLite compatibility
        sa.UniqueConstraint('citing_paper_id', 'cited_paper_id', name='uq_paper_citations_pair'),
    )

    # Indexes for efficient queries
    op.create_index('ix_paper_citations_citing', 'paper_citations', ['citing_paper_id'])
    op.create_index('ix_paper_citations_cited', 'paper_citations', ['cited_paper_id'])


def downgrade() -> None:
    """Drop paper_citations table."""
    op.drop_index('ix_paper_citations_cited', 'paper_citations')
    op.drop_index('ix_paper_citations_citing', 'paper_citations')
    op.drop_table('paper_citations')
