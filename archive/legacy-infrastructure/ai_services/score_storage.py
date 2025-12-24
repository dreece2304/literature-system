"""
Score storage service for persisting paper triage scores.

Provides SQLite-backed storage for paper scores with context-aware filtering.
Scores are tied to research contexts to support multiple projects.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from loguru import logger

from config.settings import DATA_DIR


@dataclass
class StoredScore:
    """Stored paper score with metadata."""

    paper_id: str
    context_id: str  # Research context identifier (e.g., "project-name" or "default")
    score: int  # 0-10
    justification: str
    dimensions: Dict[str, float]  # Scoring dimensions as JSON
    key_takeaways: List[str]
    action: str  # must_read, should_read, skim, skip
    research_interests: List[str]  # Interests used for scoring
    scored_at: str  # ISO timestamp

    # Paper metadata (cached for quick retrieval)
    title: str
    authors: str
    year: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class ScoreStorage:
    """
    SQLite-backed storage for paper scores.

    Features:
    - Context-aware scoring (same paper can have different scores per context)
    - Fast retrieval of top-scored papers
    - Score history tracking
    - Automatic cleanup of old scores
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize score storage.

        Args:
            db_path: Path to SQLite database (default: data/scores.db)
        """
        self.db_path = db_path or DATA_DIR / "scores.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()
        logger.info(f"ScoreStorage initialized: {self.db_path}")

    def _init_database(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create scores table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                context_id TEXT NOT NULL,
                score INTEGER NOT NULL,
                justification TEXT,
                dimensions TEXT,  -- JSON
                key_takeaways TEXT,  -- JSON
                action TEXT,
                research_interests TEXT,  -- JSON
                scored_at TEXT NOT NULL,

                -- Cached paper metadata
                title TEXT NOT NULL,
                authors TEXT NOT NULL,
                year INTEGER,

                -- Ensure one score per paper per context (latest wins)
                UNIQUE(paper_id, context_id)
            )
        """)

        # Create indices for fast retrieval
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_context_score
            ON paper_scores(context_id, score DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_context
            ON paper_scores(paper_id, context_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scored_at
            ON paper_scores(scored_at DESC)
        """)

        conn.commit()
        conn.close()

        logger.info("Database schema initialized")

    def store_score(
        self,
        paper_id: str,
        score: int,
        justification: str,
        dimensions: Dict[str, float],
        key_takeaways: List[str],
        action: str,
        research_interests: List[str],
        title: str,
        authors: str,
        year: Optional[int] = None,
        context_id: str = "default",
    ) -> StoredScore:
        """
        Store or update a paper score.

        Args:
            paper_id: Paper identifier
            score: Score (0-10)
            justification: Scoring justification
            dimensions: Scoring dimensions
            key_takeaways: Key takeaways
            action: Recommended action
            research_interests: Research interests used
            title: Paper title
            authors: Paper authors
            year: Publication year
            context_id: Research context identifier

        Returns:
            StoredScore object
        """
        scored_at = datetime.utcnow().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO paper_scores
                (paper_id, context_id, score, justification, dimensions,
                 key_takeaways, action, research_interests, scored_at,
                 title, authors, year)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                paper_id,
                context_id,
                score,
                justification,
                json.dumps(dimensions),
                json.dumps(key_takeaways),
                action,
                json.dumps(research_interests),
                scored_at,
                title,
                authors,
                year,
            ))

            conn.commit()
            logger.info(f"Stored score for paper {paper_id} (context: {context_id}, score: {score})")

            return StoredScore(
                paper_id=paper_id,
                context_id=context_id,
                score=score,
                justification=justification,
                dimensions=dimensions,
                key_takeaways=key_takeaways,
                action=action,
                research_interests=research_interests,
                scored_at=scored_at,
                title=title,
                authors=authors,
                year=year,
            )

        finally:
            conn.close()

    def get_score(
        self,
        paper_id: str,
        context_id: str = "default"
    ) -> Optional[StoredScore]:
        """
        Retrieve score for a paper in a specific context.

        Args:
            paper_id: Paper identifier
            context_id: Research context identifier

        Returns:
            StoredScore or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM paper_scores
                WHERE paper_id = ? AND context_id = ?
            """, (paper_id, context_id))

            row = cursor.fetchone()

            if row:
                return self._row_to_stored_score(row)

            return None

        finally:
            conn.close()

    def get_top_papers(
        self,
        context_id: str = "default",
        min_score: int = 7,
        limit: int = 10,
    ) -> List[StoredScore]:
        """
        Get top-scored papers for a context.

        Args:
            context_id: Research context identifier
            min_score: Minimum score threshold
            limit: Maximum number of papers to return

        Returns:
            List of StoredScore objects, sorted by score descending
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM paper_scores
                WHERE context_id = ? AND score >= ?
                ORDER BY score DESC, scored_at DESC
                LIMIT ?
            """, (context_id, min_score, limit))

            rows = cursor.fetchall()

            return [self._row_to_stored_score(row) for row in rows]

        finally:
            conn.close()

    def get_all_scores(
        self,
        context_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[StoredScore]:
        """
        Get all scores, optionally filtered by context.

        Args:
            context_id: Optional context filter
            limit: Maximum number of scores to return

        Returns:
            List of StoredScore objects, sorted by score descending
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if context_id:
                cursor.execute("""
                    SELECT * FROM paper_scores
                    WHERE context_id = ?
                    ORDER BY score DESC, scored_at DESC
                    LIMIT ?
                """, (context_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM paper_scores
                    ORDER BY score DESC, scored_at DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()

            return [self._row_to_stored_score(row) for row in rows]

        finally:
            conn.close()

    def delete_score(
        self,
        paper_id: str,
        context_id: str = "default"
    ) -> bool:
        """
        Delete a score.

        Args:
            paper_id: Paper identifier
            context_id: Research context identifier

        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                DELETE FROM paper_scores
                WHERE paper_id = ? AND context_id = ?
            """, (paper_id, context_id))

            deleted = cursor.rowcount > 0
            conn.commit()

            if deleted:
                logger.info(f"Deleted score for paper {paper_id} (context: {context_id})")

            return deleted

        finally:
            conn.close()

    def get_contexts(self) -> List[Dict[str, Any]]:
        """
        Get all research contexts with score counts.

        Returns:
            List of context info dicts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    context_id,
                    COUNT(*) as paper_count,
                    AVG(score) as avg_score,
                    MAX(scored_at) as last_scored_at
                FROM paper_scores
                GROUP BY context_id
                ORDER BY last_scored_at DESC
            """)

            rows = cursor.fetchall()

            return [
                {
                    "context_id": row[0],
                    "paper_count": row[1],
                    "avg_score": round(row[2], 2),
                    "last_scored_at": row[3],
                }
                for row in rows
            ]

        finally:
            conn.close()

    def get_stats(self, context_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about stored scores.

        Args:
            context_id: Optional context filter

        Returns:
            Statistics dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if context_id:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_scores,
                        AVG(score) as avg_score,
                        MIN(score) as min_score,
                        MAX(score) as max_score,
                        SUM(CASE WHEN action = 'must_read' THEN 1 ELSE 0 END) as must_read_count,
                        SUM(CASE WHEN action = 'should_read' THEN 1 ELSE 0 END) as should_read_count,
                        SUM(CASE WHEN action = 'skim' THEN 1 ELSE 0 END) as skim_count,
                        SUM(CASE WHEN action = 'skip' THEN 1 ELSE 0 END) as skip_count
                    FROM paper_scores
                    WHERE context_id = ?
                """, (context_id,))
            else:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_scores,
                        AVG(score) as avg_score,
                        MIN(score) as min_score,
                        MAX(score) as max_score,
                        SUM(CASE WHEN action = 'must_read' THEN 1 ELSE 0 END) as must_read_count,
                        SUM(CASE WHEN action = 'should_read' THEN 1 ELSE 0 END) as should_read_count,
                        SUM(CASE WHEN action = 'skim' THEN 1 ELSE 0 END) as skim_count,
                        SUM(CASE WHEN action = 'skip' THEN 1 ELSE 0 END) as skip_count
                    FROM paper_scores
                """)

            row = cursor.fetchone()

            return {
                "total_scores": row[0] or 0,
                "avg_score": round(row[1], 2) if row[1] else 0.0,
                "min_score": row[2] or 0,
                "max_score": row[3] or 0,
                "action_counts": {
                    "must_read": row[4] or 0,
                    "should_read": row[5] or 0,
                    "skim": row[6] or 0,
                    "skip": row[7] or 0,
                },
                "context_id": context_id,
            }

        finally:
            conn.close()

    def _row_to_stored_score(self, row: sqlite3.Row) -> StoredScore:
        """Convert database row to StoredScore object."""
        return StoredScore(
            paper_id=row["paper_id"],
            context_id=row["context_id"],
            score=row["score"],
            justification=row["justification"],
            dimensions=json.loads(row["dimensions"]),
            key_takeaways=json.loads(row["key_takeaways"]),
            action=row["action"],
            research_interests=json.loads(row["research_interests"]),
            scored_at=row["scored_at"],
            title=row["title"],
            authors=row["authors"],
            year=row["year"],
        )


# Singleton instance
_score_storage: Optional[ScoreStorage] = None


def get_score_storage() -> ScoreStorage:
    """Get or create score storage singleton."""
    global _score_storage
    if _score_storage is None:
        _score_storage = ScoreStorage()
    return _score_storage
