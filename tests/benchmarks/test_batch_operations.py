"""Performance benchmarks for batch operations.

Tests measure:
- Batch paper creation
- Batch updates
- Batch deletes
- Import/export performance
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
class TestBatchPaperCreation:
    """Benchmark batch paper creation."""

    def test_create_10_papers(self, db):
        """Benchmark creating 10 papers."""
        from services import PaperService

        def create_papers():
            for i in range(10):
                PaperService.create(
                    title=f"Batch Paper {i}",
                    abstract="Test abstract",
                    year=2023,
                    authors=["Author A", "Author B"],
                    tags=["tag1", "tag2"]
                )

        avg_time = measure_time(create_papers, iterations=3)

        print(f"\nCreate 10 papers: {avg_time*1000:.2f}ms")
        assert avg_time < 5.0

    def test_create_50_papers(self, db):
        """Benchmark creating 50 papers."""
        from services import PaperService

        def create_papers():
            for i in range(50):
                PaperService.create(
                    title=f"Batch Paper {i}",
                    year=2023
                )

        avg_time = measure_time(create_papers, iterations=2)

        print(f"\nCreate 50 papers: {avg_time*1000:.2f}ms")
        assert avg_time < 10.0

    def test_create_papers_with_full_metadata(self, db):
        """Benchmark creating papers with full metadata."""
        from services import PaperService

        def create_papers():
            for i in range(20):
                PaperService.create(
                    title=f"Full Metadata Paper {i}",
                    abstract="A" * 500,
                    year=2023,
                    doi=f"10.1234/batch{i}",
                    authors=[f"Author {j}" for j in range(5)],
                    tags=[f"tag{k}" for k in range(3)],
                    journal="Test Journal"
                )

        avg_time = measure_time(create_papers, iterations=2)

        print(f"\nCreate 20 full-metadata papers: {avg_time*1000:.2f}ms")
        assert avg_time < 10.0


@pytest.mark.slow
class TestBatchPaperUpdates:
    """Benchmark batch paper updates."""

    @pytest.fixture
    def papers_to_update(self, db):
        """Create papers for update testing."""
        from services import PaperService

        papers = []
        for i in range(50):
            paper = PaperService.create(title=f"Update Test {i}")
            papers.append(paper)
        return papers

    def test_batch_update_tags(self, db, papers_to_update):
        """Benchmark batch tag update."""
        from services import PaperService

        paper_ids = [p["id"] for p in papers_to_update]

        with Timer() as t:
            PaperService.batch_update(
                paper_ids=paper_ids,
                tags_to_add=["batch-tag-1", "batch-tag-2"]
            )

        print(f"\nBatch tag update (50 papers): {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 5.0

    def test_batch_update_status(self, db, papers_to_update):
        """Benchmark batch status update."""
        from services import PaperService

        paper_ids = [p["id"] for p in papers_to_update]

        with Timer() as t:
            PaperService.batch_update(
                paper_ids=paper_ids,
                read_status="read"
            )

        print(f"\nBatch status update (50 papers): {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 5.0

    def test_batch_update_rating(self, db, papers_to_update):
        """Benchmark batch rating update."""
        from services import PaperService

        paper_ids = [p["id"] for p in papers_to_update]

        with Timer() as t:
            PaperService.batch_update(
                paper_ids=paper_ids,
                rating=4
            )

        print(f"\nBatch rating update (50 papers): {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 5.0


@pytest.mark.slow
class TestBatchPaperDeletion:
    """Benchmark batch paper deletion."""

    def test_batch_delete_20_papers(self, db):
        """Benchmark deleting 20 papers."""
        from services import PaperService

        # Create papers
        papers = []
        for i in range(20):
            paper = PaperService.create(title=f"Delete Test {i}")
            papers.append(paper)

        paper_ids = [p["id"] for p in papers]

        with Timer() as t:
            PaperService.batch_delete(paper_ids)

        print(f"\nBatch delete (20 papers): {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 3.0

    def test_batch_delete_papers_with_notes(self, db):
        """Benchmark deleting papers with notes (cascade)."""
        from services import PaperService, NoteService

        # Create papers with notes
        paper_ids = []
        for i in range(10):
            paper = PaperService.create(title=f"Paper with Notes {i}")
            for j in range(3):
                NoteService.create(paper_id=paper["id"], content=f"Note {j}")
            paper_ids.append(paper["id"])

        with Timer() as t:
            PaperService.batch_delete(paper_ids)

        print(f"\nBatch delete with cascade (10 papers, 30 notes): {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 5.0


@pytest.mark.slow
class TestCollectionOperations:
    """Benchmark collection operations."""

    @pytest.fixture
    def papers_for_collection(self, db):
        """Create papers for collection testing."""
        from services import PaperService

        papers = []
        for i in range(30):
            paper = PaperService.create(title=f"Collection Paper {i}")
            papers.append(paper)
        return papers

    def test_add_papers_to_collection(self, db, papers_for_collection):
        """Benchmark adding papers to collection."""
        from services import CollectionService

        collection = CollectionService.create(name="Performance Test")
        paper_ids = [p["id"] for p in papers_for_collection]

        with Timer() as t:
            CollectionService.add_papers(collection["id"], paper_ids)

        print(f"\nAdd 30 papers to collection: {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 3.0

    def test_remove_papers_from_collection(self, db, papers_for_collection):
        """Benchmark removing papers from collection."""
        from services import CollectionService

        collection = CollectionService.create(name="Performance Test")
        paper_ids = [p["id"] for p in papers_for_collection]
        CollectionService.add_papers(collection["id"], paper_ids)

        with Timer() as t:
            CollectionService.remove_papers(collection["id"], paper_ids[:15])

        print(f"\nRemove 15 papers from collection: {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 3.0


@pytest.mark.slow
class TestImportExportPerformance:
    """Benchmark import/export operations."""

    @pytest.fixture
    def export_papers(self, db):
        """Create papers for export testing."""
        from services import PaperService

        papers = []
        for i in range(30):
            paper = PaperService.create(
                title=f"Export Paper {i}",
                abstract="Test abstract " * 20,
                year=2023,
                authors=["Author A", "Author B"],
                doi=f"10.1234/export{i}"
            )
            papers.append(paper)
        return papers

    def test_export_bibtex(self, db, export_papers):
        """Benchmark BibTeX export."""
        from services import ImportExportService

        paper_ids = [p["id"] for p in export_papers]

        with Timer() as t:
            ImportExportService.export_papers(
                paper_ids=paper_ids,
                format="bibtex",
                include_abstract=True
            )

        print(f"\nExport 30 papers to BibTeX: {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 3.0

    def test_export_json(self, db, export_papers):
        """Benchmark JSON export."""
        from services import ImportExportService

        paper_ids = [p["id"] for p in export_papers]

        with Timer() as t:
            ImportExportService.export_papers(
                paper_ids=paper_ids,
                format="json",
                include_abstract=True
            )

        print(f"\nExport 30 papers to JSON: {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 3.0

    def test_import_bibtex(self, db):
        """Benchmark BibTeX import."""
        from services import ImportExportService

        # Generate BibTeX content
        bibtex_entries = []
        for i in range(20):
            entry = f"""
@article{{paper{i},
    title = {{Import Performance Test Paper {i}}},
    author = {{Author, Test}},
    year = {{2023}},
    journal = {{Test Journal}}
}}
"""
            bibtex_entries.append(entry)

        bibtex_content = "\n".join(bibtex_entries)

        with Timer() as t:
            ImportExportService.import_bibtex(bibtex_content)

        print(f"\nImport 20 BibTeX entries: {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 5.0


@pytest.mark.slow
class TestDatabaseQueryPerformance:
    """Benchmark raw database query performance."""

    @pytest.fixture
    def large_dataset(self, db):
        """Create large dataset for query testing."""
        from services import PaperService

        for i in range(100):
            PaperService.create(
                title=f"Query Test Paper {i}",
                year=2020 + (i % 4),
                authors=[f"Author {i % 10}"],
                tags=[f"tag{i % 5}"]
            )

    def test_list_all_papers(self, db, large_dataset):
        """Benchmark listing all papers."""
        from services import PaperService

        with Timer() as t:
            PaperService.list(limit=100)

        print(f"\nList 100 papers: {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 3.0

    def test_list_with_filters(self, db, large_dataset):
        """Benchmark listing with multiple filters."""
        from services import PaperService

        with Timer() as t:
            PaperService.list(year=2023, tag="tag2", limit=50)

        print(f"\nList with filters: {t.elapsed*1000:.2f}ms")
        assert t.elapsed < 3.0

    def test_paginated_listing(self, db, large_dataset):
        """Benchmark paginated listing."""
        from services import PaperService

        total_time = 0
        for offset in range(0, 100, 20):
            with Timer() as t:
                PaperService.list(limit=20, offset=offset)
            total_time += t.elapsed

        print(f"\nPaginated listing (5 pages): {total_time*1000:.2f}ms")
        assert total_time < 5.0
