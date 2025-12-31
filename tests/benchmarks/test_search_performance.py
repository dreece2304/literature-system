"""Performance benchmarks for search operations.

Tests measure:
- Keyword search scaling with paper count
- Semantic search performance
- Search with various filters
"""
import pytest
import time
from typing import Callable

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class Timer:
    """Simple context manager for timing operations."""

    def __init__(self):
        self.elapsed = 0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.start


def measure_time(func: Callable, iterations: int = 1) -> float:
    """Measure average execution time over multiple iterations."""
    total = 0
    for _ in range(iterations):
        with Timer() as t:
            func()
        total += t.elapsed
    return total / iterations


@pytest.mark.slow
class TestKeywordSearchScaling:
    """Benchmark keyword search performance at different scales."""

    @pytest.fixture
    def populated_db(self, db):
        """Create database with varying number of papers."""
        from services import PaperService

        def _populate(count: int):
            for i in range(count):
                PaperService.create(
                    title=f"Test Paper {i} about machine learning",
                    abstract=f"This paper discusses neural networks and deep learning applications in materials science. Paper index {i}.",
                    year=2020 + (i % 4),
                    authors=[f"Author {i % 10}", f"Author {(i + 1) % 10}"],
                    tags=[f"tag{i % 5}"]
                )

        return _populate

    def test_keyword_search_10_papers(self, db, populated_db):
        """Benchmark keyword search with 10 papers."""
        from services import SearchService

        populated_db(10)

        avg_time = measure_time(
            lambda: SearchService.keyword_search("machine learning", limit=10),
            iterations=5
        )

        print(f"\nKeyword search (10 papers): {avg_time*1000:.2f}ms")
        assert avg_time < 1.0  # Should complete in under 1 second

    def test_keyword_search_50_papers(self, db, populated_db):
        """Benchmark keyword search with 50 papers."""
        from services import SearchService

        populated_db(50)

        avg_time = measure_time(
            lambda: SearchService.keyword_search("neural networks", limit=10),
            iterations=5
        )

        print(f"\nKeyword search (50 papers): {avg_time*1000:.2f}ms")
        assert avg_time < 2.0

    def test_keyword_search_100_papers(self, db, populated_db):
        """Benchmark keyword search with 100 papers."""
        from services import SearchService

        populated_db(100)

        avg_time = measure_time(
            lambda: SearchService.keyword_search("materials science", limit=10),
            iterations=5
        )

        print(f"\nKeyword search (100 papers): {avg_time*1000:.2f}ms")
        assert avg_time < 3.0

    def test_keyword_search_with_year_filter(self, db, populated_db):
        """Benchmark keyword search with year filter."""
        from services import SearchService

        populated_db(100)

        avg_time = measure_time(
            lambda: SearchService.keyword_search("deep learning", year_min=2022, limit=10),
            iterations=5
        )

        print(f"\nKeyword search with year filter (100 papers): {avg_time*1000:.2f}ms")
        assert avg_time < 3.0


@pytest.mark.slow
class TestAuthorSearchPerformance:
    """Benchmark author search performance."""

    @pytest.fixture
    def populated_author_db(self, db):
        """Create database with papers by various authors."""
        from services import PaperService

        for i in range(50):
            PaperService.create(
                title=f"Paper by Author {i % 10}",
                authors=[f"Author {i % 10}", f"Coauthor {i % 20}"]
            )

    def test_author_search_performance(self, db, populated_author_db):
        """Benchmark author search."""
        from services import SearchService

        avg_time = measure_time(
            lambda: SearchService.search_by_author("Author 5"),
            iterations=5
        )

        print(f"\nAuthor search (50 papers): {avg_time*1000:.2f}ms")
        assert avg_time < 2.0

    def test_partial_author_search_performance(self, db, populated_author_db):
        """Benchmark partial author name search."""
        from services import SearchService

        avg_time = measure_time(
            lambda: SearchService.search_by_author("Author"),
            iterations=5
        )

        print(f"\nPartial author search: {avg_time*1000:.2f}ms")
        assert avg_time < 2.0


@pytest.mark.slow
class TestTagSearchPerformance:
    """Benchmark tag search performance."""

    @pytest.fixture
    def populated_tag_db(self, db):
        """Create database with papers having various tags."""
        from services import PaperService

        for i in range(50):
            PaperService.create(
                title=f"Tagged Paper {i}",
                tags=[f"tag-{i % 5}", f"category-{i % 3}"]
            )

    def test_tag_search_performance(self, db, populated_tag_db):
        """Benchmark tag search."""
        from services import SearchService

        avg_time = measure_time(
            lambda: SearchService.search_by_tag("tag-2"),
            iterations=5
        )

        print(f"\nTag search (50 papers): {avg_time*1000:.2f}ms")
        assert avg_time < 2.0


@pytest.mark.slow
class TestSearchResultFormat:
    """Benchmark search result formatting overhead."""

    @pytest.fixture
    def search_db(self, db):
        """Create database with papers for result formatting tests."""
        from services import PaperService

        for i in range(20):
            PaperService.create(
                title=f"Format Test Paper {i}",
                abstract="A" * 500,  # Long abstract
                authors=[f"Author {j}" for j in range(5)],
                tags=[f"tag{k}" for k in range(3)],
                year=2023,
                doi=f"10.1234/test{i}"
            )

    def test_search_result_formatting(self, db, search_db):
        """Benchmark search with full result formatting."""
        from services import SearchService

        avg_time = measure_time(
            lambda: SearchService.keyword_search("Format Test", limit=20),
            iterations=5
        )

        print(f"\nSearch with full result formatting: {avg_time*1000:.2f}ms")
        assert avg_time < 3.0
