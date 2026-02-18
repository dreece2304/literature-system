"""update_enrichment_status_values

Revision ID: 42754b808c18
Revises: fc458fc0c8ad
Create Date: 2026-01-05 14:37:53.767144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42754b808c18'
down_revision: Union[str, Sequence[str], None] = 'fc458fc0c8ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate legacy enrichment_status values to new values.

    Changes:
    - needs_abstract → needs_extraction
    - needs_chunks → needs_extraction

    The new workflow simplifies status to:
    - pending: Just added, needs triage
    - needs_pdf: Has metadata, waiting for PDF
    - needs_extraction: Has PDF/chunks, queued for AI extraction
    - needs_review: Auto-process found issue, needs human decision
    - complete: Fully processed
    - failed: Unrecoverable error
    """
    # Migrate needs_abstract to needs_extraction
    op.execute(
        "UPDATE papers SET enrichment_status = 'needs_extraction' "
        "WHERE enrichment_status = 'needs_abstract'"
    )

    # Migrate needs_chunks to needs_extraction
    op.execute(
        "UPDATE papers SET enrichment_status = 'needs_extraction' "
        "WHERE enrichment_status = 'needs_chunks'"
    )


def downgrade() -> None:
    """Revert enrichment_status changes.

    Note: This is a lossy operation - we can't distinguish between
    papers that were needs_abstract vs needs_chunks.
    Both are reverted to needs_abstract.
    """
    op.execute(
        "UPDATE papers SET enrichment_status = 'needs_abstract' "
        "WHERE enrichment_status = 'needs_extraction'"
    )
