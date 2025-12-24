#!/usr/bin/env python
"""
Health check script for the literature management system.

Verifies database, services, embeddings, and search functionality.

Usage:
    python -m src.scripts.health_check
"""
import sys
from pathlib import Path

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = Path(__file__).parent.parent  # src/

# Add src/ to path so modules are importable
sys.path.insert(0, str(SRC_DIR))

from loguru import logger  # noqa: E402


def check_database() -> tuple[bool, str]:
    """Check database connection and paper count."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper

        with get_session() as session:
            count = session.query(Paper).count()
        return True, f"Database OK: {count} papers"
    except Exception as e:
        return False, f"Database FAILED: {e}"


def check_services() -> tuple[bool, str]:
    """Check that PaperService works."""
    try:
        from services.paper_service import PaperService

        result = PaperService.list(limit=3)
        return True, f"PaperService OK: retrieved {len(result.papers)} papers"
    except Exception as e:
        return False, f"PaperService FAILED: {e}"


def check_embeddings() -> tuple[bool, str]:
    """Check embeddings/vector store."""
    try:
        # Now that embeddings is in src/, import directly
        from embeddings.vectorstore import VectorStore

        vs = VectorStore()
        stats = vs.get_stats()
        chunk_count = stats.get("chunk_count", 0)
        return True, f"Embeddings OK: {chunk_count} chunks indexed"
    except Exception as e:
        return False, f"Embeddings FAILED: {e}"


def check_keyword_search() -> tuple[bool, str]:
    """Check keyword search functionality."""
    try:
        from services.search_service import SearchService

        results = SearchService.keyword_search("ALD", limit=3)
        return True, f"Keyword Search OK: {results.count} results for 'ALD'"
    except Exception as e:
        return False, f"Keyword Search FAILED: {e}"


def check_semantic_search() -> tuple[bool, str]:
    """Check semantic search functionality."""
    try:
        import asyncio
        from services.search_service import SearchService

        async def run_search():
            return await SearchService.semantic_search("thin film deposition", limit=3)

        results = asyncio.run(run_search())
        return True, f"Semantic Search OK: {results.count} results for 'thin film deposition'"
    except Exception as e:
        return False, f"Semantic Search FAILED: {e}"


def main():
    """Run all health checks."""
    logger.info("=" * 60)
    logger.info("LITERATURE SYSTEM HEALTH CHECK")
    logger.info("=" * 60)

    checks = [
        ("Database", check_database),
        ("Services", check_services),
        ("Embeddings", check_embeddings),
        ("Keyword Search", check_keyword_search),
        ("Semantic Search", check_semantic_search),
    ]

    all_passed = True
    results = []

    for name, check_fn in checks:
        try:
            passed, message = check_fn()
            status = "PASS" if passed else "FAIL"
            results.append((name, status, message))
            if not passed:
                all_passed = False
        except Exception as e:
            results.append((name, "ERROR", str(e)))
            all_passed = False

    # Print results
    logger.info("")
    for name, status, message in results:
        if status == "PASS":
            logger.success(f"[{status}] {name}: {message}")
        elif status == "FAIL":
            logger.error(f"[{status}] {name}: {message}")
        else:
            logger.warning(f"[{status}] {name}: {message}")

    logger.info("")
    logger.info("=" * 60)
    if all_passed:
        logger.success("ALL CHECKS PASSED")
        return 0
    else:
        logger.error("SOME CHECKS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
