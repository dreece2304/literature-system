"""Unit tests for CitationService.

Tests the actual service layer methods. MCP tool functionality
is tested in tests/integration/tools/test_citation_tools.py.

CitationService provides:
- BibTeX parsing and file handling
- TeX citation scanning
- Citation health checking (orphans, missing, duplicates)
- Database linking and export
- Project configuration
"""
import pytest
from pathlib import Path
import tempfile

import sys

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestBibTeXParsing:
    """Tests for CitationService.parse_bibtex()."""

    def test_parse_bibtex_single_entry(self):
        """Test parsing a single BibTeX entry."""
        from services.citation_service import CitationService

        bibtex = """
@article{smith2023,
    title = {Machine Learning for Science},
    author = {Smith, John and Doe, Jane},
    journal = {Nature},
    year = {2023},
    doi = {10.1038/example}
}
"""
        result = CitationService.parse_bibtex(bibtex)

        assert len(result) == 1
        entry = result[0]
        assert entry.key == "smith2023"
        assert entry.type == "article"
        # BibEntry stores fields in 'fields' dict
        assert "Machine Learning" in entry.fields.get("title", "")

    def test_parse_bibtex_multiple_entries(self):
        """Test parsing multiple BibTeX entries."""
        from services.citation_service import CitationService

        bibtex = """
@article{paper1,
    title = {First Paper},
    author = {Author One},
    year = {2023}
}
@inproceedings{paper2,
    title = {Second Paper},
    author = {Author Two},
    booktitle = {Conference},
    year = {2024}
}
"""
        result = CitationService.parse_bibtex(bibtex)

        assert len(result) == 2
        keys = [e.key for e in result]
        assert "paper1" in keys
        assert "paper2" in keys

    def test_parse_bibtex_empty(self):
        """Test parsing empty content."""
        from services.citation_service import CitationService

        result = CitationService.parse_bibtex("")

        assert result == []

    def test_parse_bibtex_malformed(self):
        """Test parsing malformed BibTeX handles gracefully."""
        from services.citation_service import CitationService

        bibtex = """
@article{incomplete,
    title = {Missing closing brace
"""
        # Should not raise, may return empty or partial
        result = CitationService.parse_bibtex(bibtex)
        assert isinstance(result, list)


class TestBibFileParsing:
    """Tests for CitationService.parse_bib_file()."""

    def test_parse_bib_file(self, tmp_path):
        """Test parsing a .bib file."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "test.bib"
        bib_file.write_text("""
@article{test2023,
    title = {Test Paper},
    author = {Test Author},
    year = {2023}
}
""")
        result = CitationService.parse_bib_file(str(bib_file))

        assert len(result) == 1
        assert result[0].key == "test2023"

    def test_parse_bib_file_not_found(self):
        """Test parsing non-existent file raises ValidationError."""
        from services.citation_service import CitationService
        from literature_core import ValidationError

        with pytest.raises(ValidationError):
            CitationService.parse_bib_file("/nonexistent/path.bib")


class TestTexCitationScanning:
    """Tests for CitationService.scan_tex_citations().

    Returns CitationScanResult dataclass with:
    - files_scanned: int
    - total_citations: int
    - unique_keys: int
    - citations_by_key: dict
    """

    def test_scan_tex_citations(self, tmp_path):
        """Test scanning a TeX file for citations."""
        from services.citation_service import CitationService

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"""
\documentclass{article}
\begin{document}
This paper builds on \cite{smith2023} and \cite{jones2024}.
We also reference \citep{brown2022, green2021}.
\end{document}
""")
        result = CitationService.scan_tex_citations(str(tex_file))

        # Result is CitationScanResult dataclass
        assert result.total_citations > 0
        assert result.unique_keys > 0
        assert "smith2023" in result.citations_by_key
        assert "jones2024" in result.citations_by_key

    def test_scan_tex_citations_no_citations(self, tmp_path):
        """Test scanning TeX file with no citations."""
        from services.citation_service import CitationService

        tex_file = tmp_path / "empty.tex"
        tex_file.write_text(r"""
\documentclass{article}
\begin{document}
No citations here.
\end{document}
""")
        result = CitationService.scan_tex_citations(str(tex_file))

        assert result.total_citations == 0
        assert result.unique_keys == 0


class TestCitationLocationTracking:
    """Tests for CitationService.get_citation_locations()."""

    def test_get_citation_locations(self, tmp_path):
        """Test finding all locations of a citation key."""
        from services.citation_service import CitationService

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"""
Line 1: First citation \cite{target}.
Line 2: Some text.
Line 3: Second use \cite{target}.
Line 4: Different cite \cite{other}.
""")
        result = CitationService.get_citation_locations(str(tex_file), "target")

        assert len(result) == 2  # Found in two places


class TestHealthCheck:
    """Tests for CitationService.check_health()."""

    def test_check_health_clean(self, tmp_path):
        """Test health check with matching bib and tex files."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
@article{smith2023,
    title = {Test},
    author = {Smith},
    year = {2023}
}
""")
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{smith2023}")

        result = CitationService.check_health(str(bib_file), str(tex_file))

        assert hasattr(result, 'orphan_entries')
        assert hasattr(result, 'missing_citations')
        assert result.missing_citations == []  # All citations have bib entries

    def test_check_health_missing_citations(self, tmp_path):
        """Test health check finds missing bib entries."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("")  # Empty bib file

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{missing2023}")

        result = CitationService.check_health(str(bib_file), str(tex_file))

        assert "missing2023" in result.missing_citations

    def test_check_health_orphan_entries(self, tmp_path):
        """Test health check finds unused bib entries."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
@article{used2023,
    title = {Used},
    author = {A},
    year = {2023}
}
@article{unused2023,
    title = {Unused},
    author = {B},
    year = {2023}
}
""")
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{used2023}")

        result = CitationService.check_health(str(bib_file), str(tex_file))

        assert "unused2023" in result.orphan_entries


class TestOrphanDetection:
    """Tests for CitationService.find_orphan_entries().

    Returns list of dicts with keys like: {'key': '...', 'title': '...', 'year': '...'}
    """

    def test_find_orphan_entries(self, tmp_path):
        """Test finding bib entries not cited in tex."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
@article{cited,
    title = {Cited},
    author = {A},
    year = {2023}
}
@article{orphan,
    title = {Orphan},
    author = {B},
    year = {2023}
}
""")
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{cited}")

        result = CitationService.find_orphan_entries(str(bib_file), str(tex_file))

        # Result is list of dicts with 'key' field
        orphan_keys = [e["key"] for e in result]
        assert "orphan" in orphan_keys
        assert "cited" not in orphan_keys


class TestMissingCitations:
    """Tests for CitationService.find_missing_citations()."""

    def test_find_missing_citations(self, tmp_path):
        """Test finding citations without bib entries."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
@article{exists,
    title = {Exists},
    author = {A},
    year = {2023}
}
""")
        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{exists} and \cite{missing}")

        result = CitationService.find_missing_citations(str(bib_file), str(tex_file))

        assert "missing" in result
        assert "exists" not in result


class TestIncompleteEntries:
    """Tests for CitationService.find_incomplete_entries()."""

    def test_find_incomplete_entries(self, tmp_path):
        """Test finding bib entries missing required fields."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
@article{complete,
    title = {Complete Entry},
    author = {Author Name},
    year = {2023}
}
@article{notitle,
    author = {No Title},
    year = {2023}
}
@article{noauthor,
    title = {No Author},
    year = {2023}
}
""")
        result = CitationService.find_incomplete_entries(str(bib_file))

        incomplete_keys = [e["key"] for e in result]
        assert "complete" not in incomplete_keys
        # At least one of these should be flagged
        assert len(incomplete_keys) > 0


class TestDuplicateDetection:
    """Tests for CitationService.find_duplicate_entries()."""

    def test_find_duplicate_entries_by_doi(self, tmp_path):
        """Test finding duplicates by DOI."""
        from services.citation_service import CitationService

        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
@article{entry1,
    title = {First Entry},
    author = {A},
    doi = {10.1234/same}
}
@article{entry2,
    title = {Second Entry},
    author = {B},
    doi = {10.1234/same}
}
""")
        result = CitationService.find_duplicate_entries(str(bib_file))

        # Should find the duplicate DOI pair
        assert len(result) > 0


class TestDatabaseExport:
    """Tests for CitationService.export_to_bib().

    Signature: export_to_bib(paper_ids=None, tag=None, output_path=None, limit=...)
    """

    def test_export_to_bib(self, db, tmp_path):
        """Test exporting papers from database to BibTeX."""
        from services import PaperService
        from services.citation_service import CitationService

        # Create test paper
        paper = PaperService.create(
            title="Test Export Paper",
            authors=["John Doe", "Jane Smith"],
            year=2024,
            doi="10.1234/export"
        )

        output_path = tmp_path / "export.bib"
        # Export specific paper by ID
        result = CitationService.export_to_bib(
            paper_ids=[paper["id"]],
            output_path=str(output_path)
        )

        assert output_path.exists()
        content = output_path.read_text()
        assert "@" in content  # Contains BibTeX entries


class TestProjectConfig:
    """Tests for project configuration methods."""

    def test_get_project_config_no_config(self, tmp_path):
        """Test getting config when none exists."""
        from services.citation_service import CitationService

        result = CitationService.get_project_config(str(tmp_path))

        # Should return empty or default config
        assert result is not None

    def test_set_and_get_project_config(self, tmp_path):
        """Test setting and retrieving project config."""
        from services.citation_service import CitationService

        bib_files = ["refs.bib", "extra.bib"]
        tex_paths = ["manuscript/", "appendix/"]

        CitationService.set_project_config(
            str(tmp_path),
            bib_files=bib_files,
            tex_paths=tex_paths
        )

        result = CitationService.get_project_config(str(tmp_path))

        assert result.bib_files == bib_files
        assert result.tex_paths == tex_paths
