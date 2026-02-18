"""add_needs_chunking_status

Revision ID: 6a8c7b18a684
Revises: 1aa6b5d4e79d
Create Date: 2026-01-06

Adds the new 'needs_chunking' enrichment status and migrates existing data.

New workflow:
    PENDING → NEEDS_PDF → NEEDS_CHUNKING → NEEDS_EXTRACTION → COMPLETE

Data migration:
    - Papers with PDF but no chunks → needs_chunking
    - Papers marked needs_extraction without PDF → needs_pdf
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6a8c7b18a684'
down_revision: Union[str, Sequence[str], None] = '1aa6b5d4e79d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add needs_chunking status and fix existing data.

    Migrates papers to correct status based on their actual state:
    - Has PDF, no chunks → needs_chunking
    - No PDF but marked needs_extraction → needs_pdf
    """
    # Papers with PDF but not chunked (chunking_status = 'none' or NULL)
    # should be needs_chunking, not complete or needs_extraction
    op.execute("""
        UPDATE papers
        SET enrichment_status = 'needs_chunking'
        WHERE file_path IS NOT NULL
          AND enrichment_status IN ('complete', 'needs_extraction')
          AND id NOT IN (
              SELECT paper_id FROM extraction_metadata
              WHERE chunking_status = 'complete'
          )
    """)

    # Papers without PDF but marked needs_extraction should be needs_pdf
    op.execute("""
        UPDATE papers
        SET enrichment_status = 'needs_pdf'
        WHERE file_path IS NULL
          AND enrichment_status = 'needs_extraction'
    """)


def downgrade() -> None:
    """Revert needs_chunking status to needs_extraction."""
    op.execute("""
        UPDATE papers
        SET enrichment_status = 'needs_extraction'
        WHERE enrichment_status = 'needs_chunking'
    """)
