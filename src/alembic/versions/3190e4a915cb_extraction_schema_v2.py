"""extraction_schema_v2

Revision ID: 3190e4a915cb
Revises: 42754b808c18
Create Date: 2026-01-06

Schema changes for two-tier extraction system (v2.0):
- PaperContent: Add quick/deep extraction dates, normalize extraction_depth
- ProjectRelevance: Add relevance scoring and deep extraction tracking fields
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3190e4a915cb'
down_revision: Union[str, Sequence[str], None] = '42754b808c18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade to extraction schema v2.0.

    PaperContent changes:
    - Add quick_extraction_date and deep_extraction_date columns
    - Migrate existing extraction_date based on extraction_depth
    - Normalize extraction_depth values to lowercase

    ProjectRelevance changes:
    - Rename overall_relevance → relevance_level
    - Add matched_topics, deep_extract_decision, decision_reason, scored_at
    """
    # =================================================================
    # PaperContent: Add new date columns
    # =================================================================
    op.add_column(
        'paper_contents',
        sa.Column('quick_extraction_date', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'paper_contents',
        sa.Column('deep_extraction_date', sa.DateTime(), nullable=True)
    )

    # Migrate existing extraction_date to appropriate column
    # ABSTRACT_ONLY → quick_extraction_date
    op.execute(
        "UPDATE paper_contents "
        "SET quick_extraction_date = extraction_date "
        "WHERE extraction_depth = 'ABSTRACT_ONLY'"
    )

    # COMPREHENSIVE → deep_extraction_date
    op.execute(
        "UPDATE paper_contents "
        "SET deep_extraction_date = extraction_date "
        "WHERE extraction_depth = 'COMPREHENSIVE'"
    )

    # Normalize extraction_depth to lowercase
    op.execute(
        "UPDATE paper_contents "
        "SET extraction_depth = 'abstract_only' "
        "WHERE extraction_depth = 'ABSTRACT_ONLY'"
    )
    op.execute(
        "UPDATE paper_contents "
        "SET extraction_depth = 'comprehensive' "
        "WHERE extraction_depth = 'COMPREHENSIVE'"
    )

    # =================================================================
    # ProjectRelevance: Add new columns and rename
    # =================================================================
    # Add new columns
    op.add_column(
        'project_relevances',
        sa.Column('matched_topics', sa.JSON(), nullable=True)
    )
    op.add_column(
        'project_relevances',
        sa.Column('deep_extract_decision', sa.String(20), nullable=True)
    )
    op.add_column(
        'project_relevances',
        sa.Column('decision_reason', sa.String(200), nullable=True)
    )
    op.add_column(
        'project_relevances',
        sa.Column('scored_at', sa.DateTime(), nullable=True)
    )

    # Rename overall_relevance → relevance_level
    # SQLite doesn't support RENAME COLUMN directly in older versions,
    # but Alembic's batch mode handles this
    with op.batch_alter_table('project_relevances') as batch_op:
        batch_op.alter_column(
            'overall_relevance',
            new_column_name='relevance_level'
        )


def downgrade() -> None:
    """Revert extraction schema v2.0 changes."""
    # =================================================================
    # ProjectRelevance: Remove columns and rename back
    # =================================================================
    with op.batch_alter_table('project_relevances') as batch_op:
        batch_op.alter_column(
            'relevance_level',
            new_column_name='overall_relevance'
        )

    op.drop_column('project_relevances', 'scored_at')
    op.drop_column('project_relevances', 'decision_reason')
    op.drop_column('project_relevances', 'deep_extract_decision')
    op.drop_column('project_relevances', 'matched_topics')

    # =================================================================
    # PaperContent: Revert extraction_depth and remove date columns
    # =================================================================
    # Revert extraction_depth to uppercase
    op.execute(
        "UPDATE paper_contents "
        "SET extraction_depth = 'ABSTRACT_ONLY' "
        "WHERE extraction_depth = 'abstract_only'"
    )
    op.execute(
        "UPDATE paper_contents "
        "SET extraction_depth = 'COMPREHENSIVE' "
        "WHERE extraction_depth = 'comprehensive'"
    )

    # Restore extraction_date from the appropriate column
    op.execute(
        "UPDATE paper_contents "
        "SET extraction_date = quick_extraction_date "
        "WHERE extraction_depth = 'ABSTRACT_ONLY' AND extraction_date IS NULL"
    )
    op.execute(
        "UPDATE paper_contents "
        "SET extraction_date = deep_extraction_date "
        "WHERE extraction_depth = 'COMPREHENSIVE' AND extraction_date IS NULL"
    )

    op.drop_column('paper_contents', 'deep_extraction_date')
    op.drop_column('paper_contents', 'quick_extraction_date')
