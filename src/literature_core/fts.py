"""SQLite FTS5 full-text search infrastructure.

Provides BM25-ranked full-text search over papers using SQLite's FTS5 extension.
Uses a content-less table that references the papers table to save space.
"""
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .database import get_engine

logger = logging.getLogger(__name__)


@dataclass
class FTSResult:
    """Result from FTS5 search."""
    paper_id: int
    bm25_score: float
    title_snippet: str | None = None
    abstract_snippet: str | None = None


@dataclass
class FTSStatus:
    """Status of the FTS5 index."""
    is_available: bool
    indexed_count: int
    papers_count: int
    needs_rebuild: bool
    last_error: str | None = None


# SQL statements for FTS5 v2 setup (title + abstract only, no full_text)
# Full-text content search is handled by semantic search via ChromaDB chunks
FTS5_CREATE_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    title,
    abstract,
    content='papers',
    content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);
"""

# Triggers to keep FTS in sync with papers table
FTS5_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS papers_fts_insert AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts(rowid, title, abstract)
    VALUES (new.id, new.title, new.abstract);
END;
"""

FTS5_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS papers_fts_delete AFTER DELETE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
    VALUES ('delete', old.id, old.title, old.abstract);
END;
"""

FTS5_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS papers_fts_update AFTER UPDATE ON papers BEGIN
    INSERT INTO papers_fts(papers_fts, rowid, title, abstract)
    VALUES ('delete', old.id, old.title, old.abstract);
    INSERT INTO papers_fts(rowid, title, abstract)
    VALUES (new.id, new.title, new.abstract);
END;
"""

# Legacy v1 SQL statements (with full_text) for migration purposes
FTS5_V1_CREATE_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    title,
    abstract,
    full_text,
    content='papers',
    content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);
"""


def create_fts_tables(engine: Engine | None = None) -> bool:
    """Create FTS5 virtual table and sync triggers.

    Args:
        engine: SQLAlchemy engine (uses default if not provided)

    Returns:
        True if successful, False otherwise
    """
    if engine is None:
        engine = get_engine()

    try:
        with engine.connect() as conn:
            # Create FTS5 table
            conn.execute(text(FTS5_CREATE_TABLE))

            # Create sync triggers
            conn.execute(text(FTS5_TRIGGER_INSERT))
            conn.execute(text(FTS5_TRIGGER_DELETE))
            conn.execute(text(FTS5_TRIGGER_UPDATE))

            conn.commit()

        logger.info("FTS5 tables and triggers created successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to create FTS5 tables: {e}")
        return False


def is_fts_available(engine: Engine | None = None) -> bool:
    """Check if FTS5 table exists and is functional."""
    if engine is None:
        engine = get_engine()

    try:
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_fts'"
            ))
            return result.fetchone() is not None
    except Exception:
        return False


def get_fts_status(engine: Engine | None = None) -> FTSStatus:
    """Get status of the FTS5 index."""
    if engine is None:
        engine = get_engine()

    try:
        with engine.connect() as conn:
            # Check if FTS table exists
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='papers_fts'"
            ))
            if result.fetchone() is None:
                return FTSStatus(
                    is_available=False,
                    indexed_count=0,
                    papers_count=0,
                    needs_rebuild=True,
                    last_error="FTS5 table does not exist"
                )

            # Count indexed documents
            fts_count = conn.execute(text(
                "SELECT COUNT(*) FROM papers_fts"
            )).scalar() or 0

            # Count total papers
            papers_count = conn.execute(text(
                "SELECT COUNT(*) FROM papers"
            )).scalar() or 0

            needs_rebuild = fts_count != papers_count

            return FTSStatus(
                is_available=True,
                indexed_count=fts_count,
                papers_count=papers_count,
                needs_rebuild=needs_rebuild
            )

    except Exception as e:
        return FTSStatus(
            is_available=False,
            indexed_count=0,
            papers_count=0,
            needs_rebuild=True,
            last_error=str(e)
        )


def rebuild_fts_index(engine: Engine | None = None, batch_size: int = 100) -> dict[str, Any]:
    """Rebuild the FTS5 index from scratch.

    Args:
        engine: SQLAlchemy engine
        batch_size: Number of papers to process at once

    Returns:
        Dict with rebuild statistics
    """
    if engine is None:
        engine = get_engine()

    stats = {
        "success": False,
        "papers_indexed": 0,
        "errors": []
    }

    try:
        with engine.connect() as conn:
            # Drop existing FTS data
            try:
                conn.execute(text("DELETE FROM papers_fts"))
            except Exception:
                pass  # Table might not exist

            # Ensure FTS table exists
            conn.execute(text(FTS5_CREATE_TABLE))

            # Get total count
            total = conn.execute(text("SELECT COUNT(*) FROM papers")).scalar() or 0

            # Populate in batches (v2: title + abstract only)
            offset = 0
            while offset < total:
                conn.execute(text("""
                    INSERT INTO papers_fts(rowid, title, abstract)
                    SELECT id, title, abstract
                    FROM papers
                    ORDER BY id
                    LIMIT :limit OFFSET :offset
                """), {"limit": batch_size, "offset": offset})

                offset += batch_size
                stats["papers_indexed"] = min(offset, total)

            conn.commit()

            stats["success"] = True
            stats["papers_indexed"] = total
            logger.info(f"FTS5 index rebuilt: {total} papers indexed")

    except Exception as e:
        stats["errors"].append(str(e))
        logger.error(f"Failed to rebuild FTS index: {e}")

    return stats


def search_fts(
    query: str,
    limit: int = 20,
    year_min: int | None = None,
    year_max: int | None = None,
    include_snippets: bool = False,
    engine: Engine | None = None,
    use_or_for_multiword: bool = True,
) -> list[FTSResult]:
    """Search papers using FTS5 with BM25 ranking.

    Args:
        query: Search query (supports FTS5 syntax: AND, OR, NOT, phrases, prefix*)
        limit: Maximum results to return
        year_min: Minimum publication year filter
        year_max: Maximum publication year filter
        include_snippets: Whether to include highlighted snippets
        engine: SQLAlchemy engine (uses default if not provided)
        use_or_for_multiword: If True, convert multi-word queries to OR logic
                              (e.g., "EUV lithography" -> "EUV OR lithography")
                              This improves recall for discovery searches.
                              Set False for strict AND matching.

    Returns:
        List of FTSResult with paper_id and bm25_score
    """
    if not query or not query.strip():
        return []

    safe_query = query.strip()

    # Convert multi-word queries to OR logic for better recall
    # Only if query doesn't already contain FTS5 operators
    if use_or_for_multiword:
        fts5_operators = ["AND", "OR", "NOT", "NEAR", '"', "*", "(", ")"]
        has_operators = (
            any(op in safe_query.upper() for op in fts5_operators[:4])
            or any(op in safe_query for op in fts5_operators[4:])
        )

        if not has_operators:
            # Split on whitespace and join with OR for multi-word queries
            words = safe_query.split()
            if len(words) > 1:
                # Use OR to match ANY word (better recall)
                safe_query = " OR ".join(words)
                logger.debug(f"Converted multi-word query to OR: {safe_query}")

    if engine is None:
        engine = get_engine()

    try:
        with engine.connect() as conn:
            # Check if FTS is available
            if not is_fts_available(engine):
                logger.warning("FTS5 not available, returning empty results")
                return []

            # Build the query with year filters
            year_filter = ""
            params: dict[str, Any] = {"query": safe_query, "limit": limit}

            if year_min is not None or year_max is not None:
                conditions = []
                if year_min is not None:
                    conditions.append("p.year >= :year_min")
                    params["year_min"] = year_min
                if year_max is not None:
                    conditions.append("p.year <= :year_max")
                    params["year_max"] = year_max
                year_filter = "AND " + " AND ".join(conditions)

            # FTS5 search with BM25 ranking
            # bm25() returns negative scores (more negative = better match)
            # We negate it so higher = better for consistency
            # v2 weights: title=10.0, abstract=5.0 (no full_text)
            if include_snippets:
                sql = f"""
                    SELECT
                        fts.rowid as paper_id,
                        -bm25(papers_fts, 10.0, 5.0) as bm25_score,
                        snippet(papers_fts, 0, '<mark>', '</mark>', '...', 32) as title_snippet,
                        snippet(papers_fts, 1, '<mark>', '</mark>', '...', 64) as abstract_snippet
                    FROM papers_fts fts
                    JOIN papers p ON p.id = fts.rowid
                    WHERE papers_fts MATCH :query
                    {year_filter}
                    ORDER BY bm25_score DESC
                    LIMIT :limit
                """
            else:
                sql = f"""
                    SELECT
                        fts.rowid as paper_id,
                        -bm25(papers_fts, 10.0, 5.0) as bm25_score
                    FROM papers_fts fts
                    JOIN papers p ON p.id = fts.rowid
                    WHERE papers_fts MATCH :query
                    {year_filter}
                    ORDER BY bm25_score DESC
                    LIMIT :limit
                """

            result = conn.execute(text(sql), params)

            results = []
            for row in result:
                if include_snippets:
                    results.append(FTSResult(
                        paper_id=row.paper_id,
                        bm25_score=row.bm25_score,
                        title_snippet=row.title_snippet,
                        abstract_snippet=row.abstract_snippet,
                    ))
                else:
                    results.append(FTSResult(
                        paper_id=row.paper_id,
                        bm25_score=row.bm25_score,
                    ))

            return results

    except Exception as e:
        logger.error(f"FTS5 search failed: {e}")
        return []


def search_fts_phrase(
    phrase: str,
    limit: int = 20,
    engine: Engine | None = None,
) -> list[FTSResult]:
    """Search for an exact phrase in papers.

    Args:
        phrase: Exact phrase to search for
        limit: Maximum results
        engine: SQLAlchemy engine (uses default if not provided)

    Returns:
        List of matching papers
    """
    # Wrap in quotes for phrase search
    query = f'"{phrase}"'
    return search_fts(query, limit=limit, engine=engine)


def search_fts_any_term(
    terms: list[str],
    limit: int = 20,
    engine: Engine | None = None,
) -> list[FTSResult]:
    """Search for papers containing any of the given terms (OR).

    Args:
        terms: List of search terms
        limit: Maximum results
        engine: SQLAlchemy engine (uses default if not provided)

    Returns:
        List of matching papers
    """
    query = " OR ".join(terms)
    return search_fts(query, limit=limit, engine=engine)


def search_fts_all_terms(
    terms: list[str],
    limit: int = 20,
    engine: Engine | None = None,
) -> list[FTSResult]:
    """Search for papers containing all of the given terms (AND).

    Args:
        terms: List of search terms
        limit: Maximum results
        engine: SQLAlchemy engine (uses default if not provided)

    Returns:
        List of matching papers
    """
    query = " AND ".join(terms)
    return search_fts(query, limit=limit, engine=engine)


def optimize_fts_index(engine: Engine | None = None) -> bool:
    """Optimize the FTS5 index for better query performance.

    Should be run periodically after many updates.
    """
    if engine is None:
        engine = get_engine()

    try:
        with engine.connect() as conn:
            # FTS5 optimize command
            conn.execute(text("INSERT INTO papers_fts(papers_fts) VALUES('optimize')"))
            conn.commit()
            logger.info("FTS5 index optimized")
            return True
    except Exception as e:
        logger.error(f"Failed to optimize FTS index: {e}")
        return False
