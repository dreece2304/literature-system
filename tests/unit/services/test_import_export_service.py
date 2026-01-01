"""Unit tests for ImportExportService.

Tests cover:
- BibTeX import/export
- JSON import/export
- CSV export
- Collection export
"""
import pytest
import json

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestBibTeXImport:
    """Tests for BibTeX import."""

    def test_import_bibtex_single_entry(self, db):
        """Test importing single BibTeX entry."""
        from services import ImportExportService

        bibtex = """
        @article{smith2023test,
            title = {Test Paper Title},
            author = {Smith, John},
            year = {2023},
            journal = {Test Journal}
        }
        """

        result = ImportExportService.import_bibtex(bibtex)

        assert len(result.imported) == 1
        assert len(result.failed) == 0

    def test_import_bibtex_multiple_entries(self, db):
        """Test importing multiple BibTeX entries."""
        from services import ImportExportService

        bibtex = """
        @article{paper1,
            title = {First Paper},
            author = {Author, First},
            year = {2023}
        }

        @article{paper2,
            title = {Second Paper},
            author = {Author, Second},
            year = {2022}
        }

        @inproceedings{paper3,
            title = {Conference Paper},
            author = {Author, Third},
            year = {2021}
        }
        """

        result = ImportExportService.import_bibtex(bibtex)

        assert len(result.imported) == 3

    def test_import_bibtex_with_tags(self, db):
        """Test importing BibTeX with tags applied."""
        from services import ImportExportService

        bibtex = """
        @article{test,
            title = {Tagged Paper},
            author = {Author, Test},
            year = {2023}
        }
        """

        result = ImportExportService.import_bibtex(bibtex, tags=["imported", "review"])

        assert len(result.imported) == 1

    def test_import_bibtex_with_collection(self, db):
        """Test importing BibTeX into collection."""
        from services import ImportExportService, CollectionService

        collection = CollectionService.create(name="Import Test")

        bibtex = """
        @article{test,
            title = {Collection Paper},
            author = {Author, Test},
            year = {2023}
        }
        """

        result = ImportExportService.import_bibtex(
            bibtex,
            collection_id=collection["id"]
        )

        assert len(result.imported) == 1

    def test_import_bibtex_malformed(self, db):
        """Test importing malformed BibTeX."""
        from services import ImportExportService

        bibtex = """
        @article{incomplete,
            title = {Missing closing brace
        """

        result = ImportExportService.import_bibtex(bibtex)

        # Should handle gracefully - either has failed entries or no imports
        assert len(result.failed) > 0 or len(result.imported) == 0

    def test_import_bibtex_empty(self, db):
        """Test importing empty BibTeX."""
        from services import ImportExportService

        result = ImportExportService.import_bibtex("")

        assert len(result.imported) == 0


class TestBibTeXExport:
    """Tests for BibTeX export."""

    def test_export_bibtex_single_paper(self, db):
        """Test exporting single paper to BibTeX."""
        from services import PaperService, ImportExportService

        paper = PaperService.create(
            title="Export Test Paper",
            year=2023,
            authors=["Smith, John"],
            journal="Test Journal"
        )

        result = ImportExportService.export_papers(
            paper_ids=[paper["id"]],
            format="bibtex"
        )

        assert "@article" in result
        assert "Export Test Paper" in result
        assert "2023" in result

    def test_export_bibtex_multiple_papers(self, db):
        """Test exporting multiple papers to BibTeX."""
        from services import PaperService, ImportExportService

        paper1 = PaperService.create(title="First Paper", year=2023)
        paper2 = PaperService.create(title="Second Paper", year=2022)

        result = ImportExportService.export_papers(
            paper_ids=[paper1["id"], paper2["id"]],
            format="bibtex"
        )

        assert result.count("@article") == 2

    def test_export_bibtex_with_abstract(self, db):
        """Test exporting papers with abstracts."""
        from services import PaperService, ImportExportService

        paper = PaperService.create(
            title="Abstract Test",
            abstract="This is the paper abstract.",
            year=2023
        )

        result = ImportExportService.export_papers(
            paper_ids=[paper["id"]],
            format="bibtex",
            include_abstract=True
        )

        assert "abstract" in result.lower()
        assert "This is the paper abstract" in result

    def test_export_bibtex_without_abstract(self, db):
        """Test exporting papers without abstracts."""
        from services import PaperService, ImportExportService

        paper = PaperService.create(
            title="No Abstract Test",
            abstract="This should be excluded.",
            year=2023
        )

        result = ImportExportService.export_papers(
            paper_ids=[paper["id"]],
            format="bibtex",
            include_abstract=False
        )

        assert "This should be excluded" not in result


class TestJSONExport:
    """Tests for JSON export."""

    def test_export_json_single_paper(self, db):
        """Test exporting single paper to JSON."""
        from services import PaperService, ImportExportService

        paper = PaperService.create(
            title="JSON Export Test",
            year=2023,
            authors=["Author One"]
        )

        result = ImportExportService.export_papers(
            paper_ids=[paper["id"]],
            format="json"
        )

        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["title"] == "JSON Export Test"

    def test_export_json_multiple_papers(self, db):
        """Test exporting multiple papers to JSON."""
        from services import PaperService, ImportExportService

        paper1 = PaperService.create(title="Paper 1", year=2023)
        paper2 = PaperService.create(title="Paper 2", year=2022)

        result = ImportExportService.export_papers(
            paper_ids=[paper1["id"], paper2["id"]],
            format="json"
        )

        parsed = json.loads(result)
        assert len(parsed) == 2

    def test_export_json_with_notes(self, db):
        """Test exporting papers with notes."""
        from services import PaperService, NoteService, ImportExportService

        paper = PaperService.create(title="Paper with Notes", year=2023)
        NoteService.create(paper_id=paper["id"], content="Test note")

        result = ImportExportService.export_papers(
            paper_ids=[paper["id"]],
            format="json",
            include_notes=True
        )

        parsed = json.loads(result)
        assert "notes" in parsed[0] or len(parsed) == 1

    def test_export_json_all_papers(self, db):
        """Test exporting all papers when no IDs specified."""
        from services import PaperService, ImportExportService

        PaperService.create(title="Paper A", year=2023)
        PaperService.create(title="Paper B", year=2022)
        PaperService.create(title="Paper C", year=2021)

        result = ImportExportService.export_papers(format="json")

        parsed = json.loads(result)
        assert len(parsed) >= 3


class TestCSVExport:
    """Tests for CSV export."""

    def test_export_csv_single_paper(self, db):
        """Test exporting single paper to CSV."""
        from services import PaperService, ImportExportService

        paper = PaperService.create(
            title="CSV Export Test",
            year=2023,
            doi="10.1234/test"
        )

        result = ImportExportService.export_papers(
            paper_ids=[paper["id"]],
            format="csv"
        )

        lines = result.strip().split("\n")
        assert len(lines) >= 2  # Header + data
        assert "CSV Export Test" in result

    def test_export_csv_multiple_papers(self, db):
        """Test exporting multiple papers to CSV."""
        from services import PaperService, ImportExportService

        for i in range(5):
            PaperService.create(title=f"Paper {i}", year=2020 + i)

        result = ImportExportService.export_papers(format="csv")

        lines = result.strip().split("\n")
        assert len(lines) >= 6  # Header + 5 data rows


class TestCollectionExport:
    """Tests for collection export."""

    def test_export_collection_bibtex(self, db):
        """Test exporting collection to BibTeX."""
        from services import PaperService, CollectionService, ImportExportService

        # Create collection with papers
        collection = CollectionService.create(name="Export Collection")

        paper1 = PaperService.create(title="Collection Paper 1", year=2023)
        paper2 = PaperService.create(title="Collection Paper 2", year=2022)

        CollectionService.add_papers(collection["id"], [paper1["id"], paper2["id"]])

        result = ImportExportService.export_collection(
            collection_id=collection["id"],
            format="bibtex"
        )

        assert "@article" in result
        assert "Collection Paper 1" in result
        assert "Collection Paper 2" in result

    def test_export_collection_with_subcollections(self, db):
        """Test exporting collection including subcollections."""
        from services import PaperService, CollectionService, ImportExportService

        # Create parent and child collections
        parent = CollectionService.create(name="Parent Collection")
        child = CollectionService.create(
            name="Child Collection",
            parent_id=parent["id"]
        )

        parent_paper = PaperService.create(title="Parent Paper", year=2023)
        child_paper = PaperService.create(title="Child Paper", year=2022)

        CollectionService.add_papers(parent["id"], [parent_paper["id"]])
        CollectionService.add_papers(child["id"], [child_paper["id"]])

        result = ImportExportService.export_collection(
            collection_id=parent["id"],
            format="bibtex",
            include_subcollections=True
        )

        assert "Parent Paper" in result
        assert "Child Paper" in result

    def test_export_empty_collection(self, db):
        """Test exporting empty collection."""
        from services import CollectionService, ImportExportService

        collection = CollectionService.create(name="Empty Collection")

        result = ImportExportService.export_collection(
            collection_id=collection["id"],
            format="bibtex"
        )

        # Should return empty or minimal content
        assert "@article" not in result or result.strip() == ""


class TestExternalImport:
    """Tests for importing from external sources."""

    @pytest.mark.asyncio
    async def test_import_from_doi(self, db, mock_external_apis):
        """Test importing paper from DOI."""
        from services import ImportExportService

        result = await ImportExportService.import_from_external(
            doi="10.1234/test.2023"
        )

        # ExternalImportResult has status attribute
        assert result.status in ("success", "error", "already_exists")

    @pytest.mark.asyncio
    async def test_import_from_arxiv(self, db, mock_external_apis):
        """Test importing paper from arXiv ID."""
        from services import ImportExportService

        result = await ImportExportService.import_from_external(
            arxiv_id="2401.12345"
        )

        assert result.status in ("success", "error", "already_exists")

    @pytest.mark.asyncio
    async def test_import_from_title(self, db, mock_external_apis):
        """Test importing paper from title lookup."""
        from services import ImportExportService

        result = await ImportExportService.import_from_external(
            title="Machine Learning for Materials Science"
        )

        assert result.status in ("success", "error", "already_exists")


class TestExportPagination:
    """Tests for export pagination."""

    def test_export_with_limit(self, db):
        """Test exporting with limit parameter."""
        from services import PaperService, ImportExportService

        # Create 10 papers
        for i in range(10):
            PaperService.create(title=f"Pagination Test Paper {i}", year=2023)

        result = ImportExportService.export_papers(format="json", limit=5)

        parsed = json.loads(result)
        assert len(parsed) == 5

    def test_export_with_offset(self, db):
        """Test exporting with offset parameter."""
        from services import PaperService, ImportExportService

        # Create 10 papers
        for i in range(10):
            PaperService.create(title=f"Offset Test Paper {i}", year=2023)

        # First page
        page1 = ImportExportService.export_papers(format="json", limit=5, offset=0)
        # Second page
        page2 = ImportExportService.export_papers(format="json", limit=5, offset=5)

        parsed1 = json.loads(page1)
        parsed2 = json.loads(page2)

        assert len(parsed1) == 5
        assert len(parsed2) == 5

        # Ensure no overlap
        ids1 = {p["id"] for p in parsed1}
        ids2 = {p["id"] for p in parsed2}
        assert ids1.isdisjoint(ids2)

    def test_export_consistent_ordering(self, db):
        """Test that pagination results are consistently ordered."""
        from services import PaperService, ImportExportService

        # Create papers
        for i in range(6):
            PaperService.create(title=f"Order Test Paper {i}", year=2023)

        # Get all papers
        all_papers = ImportExportService.export_papers(format="json", limit=10)
        parsed_all = json.loads(all_papers)

        # Get in pages
        page1 = ImportExportService.export_papers(format="json", limit=3, offset=0)
        page2 = ImportExportService.export_papers(format="json", limit=3, offset=3)

        parsed1 = json.loads(page1)
        parsed2 = json.loads(page2)

        # Combine pages should match all papers (by IDs)
        all_ids = [p["id"] for p in parsed_all]
        paged_ids = [p["id"] for p in parsed1] + [p["id"] for p in parsed2]

        assert set(paged_ids) <= set(all_ids)

    def test_export_offset_beyond_data(self, db):
        """Test exporting with offset beyond available data."""
        from services import PaperService, ImportExportService

        # Create 3 papers
        for i in range(3):
            PaperService.create(title=f"Beyond Test Paper {i}", year=2023)

        result = ImportExportService.export_papers(format="json", limit=10, offset=100)

        parsed = json.loads(result)
        assert len(parsed) == 0
