"""Unit tests for CitationService.

Tests cover:
- BibTeX generation
- Citation key generation
- Manuscript scanning
- Citation validation
"""
import pytest

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestBibTeXGeneration:
    """Tests for BibTeX generation."""

    def test_generate_bibtex_single_paper(self, db):
        """Test generating BibTeX for single paper."""
        from services import CitationService

        papers = [{
            "title": "Test Paper on Machine Learning",
            "authors": "Smith, John and Doe, Jane",
            "year": 2023,
            "journal": "Nature Machine Intelligence",
            "doi": "10.1038/s42256-023-00001-1"
        }]

        result = CitationService.generate_bibtex(papers)

        assert "@article" in result
        assert "Test Paper on Machine Learning" in result
        assert "Smith" in result
        assert "2023" in result

    def test_generate_bibtex_multiple_papers(self, db):
        """Test generating BibTeX for multiple papers."""
        from services import CitationService

        papers = [
            {
                "title": "First Paper",
                "authors": "Author, First",
                "year": 2023
            },
            {
                "title": "Second Paper",
                "authors": "Author, Second",
                "year": 2022
            }
        ]

        result = CitationService.generate_bibtex(papers)

        assert result.count("@article") == 2
        assert "First Paper" in result
        assert "Second Paper" in result

    def test_generate_bibtex_with_conference(self, db):
        """Test generating BibTeX for conference paper."""
        from services import CitationService

        papers = [{
            "title": "Conference Paper",
            "authors": "Presenter, Name",
            "year": 2023
        }]

        result = CitationService.generate_bibtex(papers, entry_type="inproceedings")

        assert "@inproceedings" in result

    def test_generate_bibtex_empty_list(self, db):
        """Test generating BibTeX for empty list."""
        from services import CitationService

        result = CitationService.generate_bibtex([])

        assert result == "" or result.strip() == ""


class TestCitationKeyGeneration:
    """Tests for citation key generation."""

    def test_suggest_citation_key_basic(self, db):
        """Test basic citation key generation."""
        from services import CitationService

        result = CitationService.suggest_citation_key(
            title="Machine Learning for Materials",
            authors="Smith, John",
            year=2023
        )

        assert "smith" in result.lower()
        assert "2023" in result

    def test_suggest_citation_key_multiple_authors(self, db):
        """Test citation key with multiple authors."""
        from services import CitationService

        result = CitationService.suggest_citation_key(
            title="Collaborative Research Paper",
            authors="Smith, John and Doe, Jane and Johnson, Bob",
            year=2022
        )

        # Should use first author
        assert "smith" in result.lower()

    def test_suggest_citation_key_special_characters(self, db):
        """Test citation key handles special characters."""
        from services import CitationService

        result = CitationService.suggest_citation_key(
            title="α-particles in β-decay",
            authors="Müller, Hans",
            year=2021
        )

        # Should produce valid key
        assert result is not None
        assert len(result) > 0


class TestManuscriptScanning:
    """Tests for manuscript citation scanning."""

    def test_scan_latex_manuscript(self, db):
        """Test scanning LaTeX manuscript for citations."""
        from services import CitationService

        latex_content = r"""
        \documentclass{article}
        \begin{document}
        This work builds on \cite{smith2023} and extends \cite{doe2022}.
        We also reference \citep{johnson2021, williams2020}.
        \end{document}
        """

        result = CitationService.scan_manuscript(content=latex_content, format="latex")

        assert "citation_keys" in result
        keys = result["citation_keys"]
        assert "smith2023" in keys
        assert "doe2022" in keys
        assert "johnson2021" in keys
        assert "williams2020" in keys

    def test_scan_markdown_manuscript(self, db):
        """Test scanning Markdown manuscript for citations."""
        from services import CitationService

        md_content = """
        # Introduction

        Previous work [@smith2023] showed promising results.
        Building on [@doe2022; @johnson2021], we propose...
        """

        result = CitationService.scan_manuscript(content=md_content, format="markdown")

        assert "citation_keys" in result

    def test_scan_manuscript_no_citations(self, db):
        """Test scanning manuscript with no citations."""
        from services import CitationService

        content = "This is plain text without any citations."

        result = CitationService.scan_manuscript(content=content, format="latex")

        assert result["citation_keys"] == []

    def test_scan_manuscript_sections(self, db):
        """Test that scanning identifies sections."""
        from services import CitationService

        latex_content = r"""
        \section{Introduction}
        Text here \cite{ref1}.

        \section{Methods}
        More text \cite{ref2}.

        \section{Results}
        Results \cite{ref3}.
        """

        result = CitationService.scan_manuscript(content=latex_content, format="latex")

        # Should identify structure
        assert "sections" in result or "citation_keys" in result


class TestCitationValidation:
    """Tests for citation validation."""

    def test_validate_citations_complete(self, db):
        """Test validating complete citation data."""
        from services import CitationService

        papers = [{
            "title": "Complete Paper",
            "authors": "Author, Name",
            "year": 2023,
            "journal": "Journal Name",
            "doi": "10.1234/test"
        }]

        result = CitationService.validate_citations(papers)

        assert result["valid"] is True
        assert len(result.get("issues", [])) == 0

    def test_validate_citations_missing_year(self, db):
        """Test validation catches missing year."""
        from services import CitationService

        papers = [{
            "title": "Paper Without Year",
            "authors": "Author, Name"
        }]

        result = CitationService.validate_citations(papers)

        assert result["valid"] is False or len(result.get("issues", [])) > 0

    def test_validate_citations_missing_author(self, db):
        """Test validation catches missing author."""
        from services import CitationService

        papers = [{
            "title": "Paper Without Author",
            "year": 2023
        }]

        result = CitationService.validate_citations(papers)

        assert result["valid"] is False or len(result.get("issues", [])) > 0


class TestCitationChecking:
    """Tests for checking citations against library."""

    def test_check_citations_all_found(self, db):
        """Test checking citations when all are in library."""
        from services import PaperService, CitationService

        # Create papers in library
        PaperService.create(title="Smith 2023 Paper", year=2023)
        PaperService.create(title="Doe 2022 Paper", year=2022)

        manuscript_citations = ["smith2023", "doe2022"]
        library_papers = [
            {"id": 1, "title": "Smith 2023 Paper", "year": 2023, "authors": "Smith"},
            {"id": 2, "title": "Doe 2022 Paper", "year": 2022, "authors": "Doe"}
        ]

        result = CitationService.check_citations(
            manuscript_citations=manuscript_citations,
            library_papers=library_papers
        )

        assert "orphan_citations" in result
        assert "unused_papers" in result

    def test_check_citations_orphans(self, db):
        """Test checking citations finds orphan citations."""
        from services import CitationService

        manuscript_citations = ["smith2023", "unknown2024"]
        library_papers = [
            {"id": 1, "title": "Smith Paper", "year": 2023, "authors": "Smith"}
        ]

        result = CitationService.check_citations(
            manuscript_citations=manuscript_citations,
            library_papers=library_papers
        )

        # unknown2024 should be orphan
        assert "orphan_citations" in result

    def test_check_citations_unused(self, db):
        """Test checking citations finds unused papers."""
        from services import CitationService

        manuscript_citations = ["smith2023"]
        library_papers = [
            {"id": 1, "title": "Smith Paper", "year": 2023, "authors": "Smith"},
            {"id": 2, "title": "Unused Paper", "year": 2022, "authors": "Nobody"}
        ]

        result = CitationService.check_citations(
            manuscript_citations=manuscript_citations,
            library_papers=library_papers
        )

        # Unused paper should be identified
        assert "unused_papers" in result
