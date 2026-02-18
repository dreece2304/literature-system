"""add_missing_indexes

Revision ID: a2b3c4d5e6f7
Revises: 0510299c26bb
Create Date: 2026-01-21

Adds ~20 indexes declared in models.py that were missing from the production database.
These indexes improve query performance for:
- Association table joins (paper_authors, paper_tags, paper_collections)
- Common paper filters (year, read_status, rating, date_added, validation_status)
- Entity lookups (authors.name, collections.name, collections.parent_id)
- Note filtering (paper_id, note_type)
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = '0510299c26bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing indexes to improve query performance."""
    # Association tables - critical for JOINs
    op.create_index('ix_paper_authors_paper_id', 'paper_authors', ['paper_id'])
    op.create_index('ix_paper_authors_author_id', 'paper_authors', ['author_id'])
    op.create_index('ix_paper_authors_both', 'paper_authors', ['paper_id', 'author_id'])

    op.create_index('ix_paper_tags_paper_id', 'paper_tags', ['paper_id'])
    op.create_index('ix_paper_tags_tag_id', 'paper_tags', ['tag_id'])

    op.create_index('ix_paper_collections_paper_id', 'paper_collections', ['paper_id'])
    op.create_index('ix_paper_collections_collection_id', 'paper_collections', ['collection_id'])

    # Papers - common filter columns
    op.create_index('ix_papers_year', 'papers', ['year'])
    op.create_index('ix_papers_date_added', 'papers', ['date_added'])
    op.create_index('ix_papers_rating', 'papers', ['rating'])
    op.create_index('ix_papers_read_status', 'papers', ['read_status'])
    op.create_index('ix_papers_validation_status', 'papers', ['validation_status'])
    op.create_index('ix_papers_year_status', 'papers', ['year', 'read_status'])
    op.create_index('ix_papers_citation_key', 'papers', ['citation_key'], unique=True)

    # Authors - name lookups
    op.create_index('ix_authors_name', 'authors', ['name'])

    # Collections - hierarchy queries
    op.create_index('ix_collections_name', 'collections', ['name'])
    op.create_index('ix_collections_parent_id', 'collections', ['parent_id'])

    # Notes - filtering by paper and type
    op.create_index('ix_notes_paper_id', 'notes', ['paper_id'])
    op.create_index('ix_notes_note_type', 'notes', ['note_type'])
    op.create_index('ix_notes_paper_type', 'notes', ['paper_id', 'note_type'])


def downgrade() -> None:
    """Remove the indexes added in this migration."""
    # Notes
    op.drop_index('ix_notes_paper_type', 'notes')
    op.drop_index('ix_notes_note_type', 'notes')
    op.drop_index('ix_notes_paper_id', 'notes')

    # Collections
    op.drop_index('ix_collections_parent_id', 'collections')
    op.drop_index('ix_collections_name', 'collections')

    # Authors
    op.drop_index('ix_authors_name', 'authors')

    # Papers
    op.drop_index('ix_papers_citation_key', 'papers')
    op.drop_index('ix_papers_year_status', 'papers')
    op.drop_index('ix_papers_validation_status', 'papers')
    op.drop_index('ix_papers_read_status', 'papers')
    op.drop_index('ix_papers_rating', 'papers')
    op.drop_index('ix_papers_date_added', 'papers')
    op.drop_index('ix_papers_year', 'papers')

    # Association tables
    op.drop_index('ix_paper_collections_collection_id', 'paper_collections')
    op.drop_index('ix_paper_collections_paper_id', 'paper_collections')
    op.drop_index('ix_paper_tags_tag_id', 'paper_tags')
    op.drop_index('ix_paper_tags_paper_id', 'paper_tags')
    op.drop_index('ix_paper_authors_both', 'paper_authors')
    op.drop_index('ix_paper_authors_author_id', 'paper_authors')
    op.drop_index('ix_paper_authors_paper_id', 'paper_authors')
