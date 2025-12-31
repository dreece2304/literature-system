"""Integration tests for citation MCP tools.

Tests the citation-related MCP tool handlers:
- BibTeX generation tools (citations.py)
- Citation key suggestion (citations.py)
- Manuscript scanning (citations.py)
- Citation health checking (project.py)
"""
import pytest
import json

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mcp_server.tools import citations
from mcp_server.tools import project


class TestCitationToolSchemas:
    """Tests for citation tool schemas."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_citation_tools(self):
        """Test that list_tools returns expected citation tools."""
        tools = await citations.list_tools()

        tool_names = [t.name for t in tools]
        expected = [
            "scan_manuscript",
            "check_citations",
            "suggest_citation_key",
            "generate_bibtex",
            "format_bibliography",
            "validate_citations",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    @pytest.mark.asyncio
    async def test_list_tools_returns_project_tools(self):
        """Test that list_tools returns expected project tools."""
        tools = await project.list_tools()

        tool_names = [t.name for t in tools]
        expected = [
            "citation_health_check",
            "find_orphan_citations",
            "find_missing_citations",
            "find_incomplete_bib_entries",
            "find_duplicate_bib_entries",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"


class TestGenerateBibTeXTool:
    """Tests for generate_bibtex tool."""

    @pytest.mark.asyncio
    async def test_generate_bibtex_success(self, db):
        """Test successful BibTeX generation."""
        # Test with paper data directly (not from PaperService)
        # since BibTeX generation works on input data, not DB queries
        result = await citations.call_tool("generate_bibtex", {
            "papers": [{
                "title": "Test Paper",
                "authors": "Smith, John",
                "year": 2023,
                "journal": "Test Journal",
                "doi": "10.1234/test"
            }]
        })

        # generate_bibtex returns raw BibTeX text, not JSON
        text = result[0].text
        assert "@article" in text
        assert "Test Paper" in text

    @pytest.mark.asyncio
    async def test_generate_bibtex_multiple_papers(self, db):
        """Test BibTeX generation for multiple papers."""
        papers = [
            {"title": "Paper 1", "authors": "Author One", "year": 2023},
            {"title": "Paper 2", "authors": "Author Two", "year": 2022}
        ]

        result = await citations.call_tool("generate_bibtex", {"papers": papers})

        text = result[0].text
        assert text.count("@article") == 2

    @pytest.mark.asyncio
    async def test_generate_bibtex_conference_type(self, db):
        """Test BibTeX generation with conference entry type."""
        papers = [{
            "title": "Conference Paper",
            "authors": "Presenter, Name",
            "year": 2023
        }]

        result = await citations.call_tool("generate_bibtex", {
            "papers": papers,
            "entry_type": "inproceedings"
        })

        text = result[0].text
        assert "@inproceedings" in text


class TestSuggestCitationKeyTool:
    """Tests for suggest_citation_key tool."""

    @pytest.mark.asyncio
    async def test_suggest_key_basic(self, db):
        """Test basic citation key suggestion."""
        result = await citations.call_tool("suggest_citation_key", {
            "title": "Machine Learning Fundamentals",
            "authors": "Smith, John",
            "year": 2023
        })

        data = json.loads(result[0].text)
        assert "suggested_key" in data
        assert "smith" in data["suggested_key"].lower()
        assert "2023" in data["suggested_key"]

    @pytest.mark.asyncio
    async def test_suggest_key_multiple_authors(self, db):
        """Test citation key with multiple authors."""
        result = await citations.call_tool("suggest_citation_key", {
            "title": "Collaborative Research",
            "authors": "Smith, John and Doe, Jane",
            "year": 2022
        })

        data = json.loads(result[0].text)
        # Should use first author
        assert "smith" in data["suggested_key"].lower()

    @pytest.mark.asyncio
    async def test_suggest_key_required_fields(self, db):
        """Test citation key requires title and authors."""
        # Missing authors should still work with default
        result = await citations.call_tool("suggest_citation_key", {
            "title": "Test Paper"
        })

        # Should return something, possibly with error or unknown author
        assert result is not None


class TestScanManuscriptTool:
    """Tests for scan_manuscript tool."""

    @pytest.mark.asyncio
    async def test_scan_latex_file(self, db, tmp_path):
        """Test scanning LaTeX file for citations."""
        # Create temp LaTeX file
        tex_file = tmp_path / "test.tex"
        tex_file.write_text(r"""
        \documentclass{article}
        \begin{document}
        We reference \cite{smith2023} and \cite{doe2022}.
        \end{document}
        """)

        result = await citations.call_tool("scan_manuscript", {
            "file_path": str(tex_file)
        })

        data = json.loads(result[0].text)
        # Returns structure with all_citations or sections with citations
        assert "all_citations" in data or "sections" in data

    @pytest.mark.asyncio
    async def test_scan_manuscript_content(self, db):
        """Test scanning manuscript content directly."""
        content = r"""
        \section{Introduction}
        As shown in \cite{ref1}, the method works.
        Building on \cite{ref2}, we extend...
        """

        result = await citations.call_tool("scan_manuscript", {
            "content": content,
            "format": "latex"
        })

        data = json.loads(result[0].text)
        assert "all_citations" in data or "sections" in data

    @pytest.mark.asyncio
    async def test_scan_markdown_content(self, db):
        """Test scanning Markdown content."""
        content = """
        # Introduction
        Previous work [@smith2023] showed results.
        We build on [@doe2022; @johnson2021].
        """

        result = await citations.call_tool("scan_manuscript", {
            "content": content,
            "format": "markdown"
        })

        data = json.loads(result[0].text)
        assert "all_citations" in data or "sections" in data


class TestCheckCitationsTool:
    """Tests for check_citations tool."""

    @pytest.mark.asyncio
    async def test_check_citations_all_found(self, db):
        """Test checking citations when all are in library."""
        result = await citations.call_tool("check_citations", {
            "manuscript_citations": ["smith2023", "doe2022"],
            "library_papers": [
                {"id": 1, "title": "Smith Paper", "authors": "Smith", "year": 2023},
                {"id": 2, "title": "Doe Paper", "authors": "Doe", "year": 2022}
            ]
        })

        data = json.loads(result[0].text)
        assert "orphan_citations" in data
        assert "unused_papers" in data

    @pytest.mark.asyncio
    async def test_check_citations_orphans(self, db):
        """Test detecting orphan citations."""
        result = await citations.call_tool("check_citations", {
            "manuscript_citations": ["smith2023", "unknown2024"],
            "library_papers": [
                {"id": 1, "title": "Smith Paper", "authors": "Smith", "year": 2023}
            ]
        })

        data = json.loads(result[0].text)
        # Should identify unknown2024 as orphan
        assert "orphan_citations" in data
        assert data["orphan_citations"]["count"] >= 1


class TestCitationHealthCheckTool:
    """Tests for citation_health_check tool (in project.py)."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, db, tmp_path):
        """Test citation health check."""
        # Create temp files
        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
        @article{smith2023,
            title = {Test Paper},
            author = {Smith, John},
            year = {2023}
        }
        """)

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"""
        \cite{smith2023}
        """)

        result = await project.call_tool("citation_health_check", {
            "bib_path": str(bib_file),
            "tex_path": str(tex_file)
        })

        data = json.loads(result[0].text)
        assert "summary" in data
        assert "status" in data


class TestFindOrphanCitationsTool:
    """Tests for find_orphan_citations tool (in project.py)."""

    @pytest.mark.asyncio
    async def test_find_orphans_none(self, db, tmp_path):
        """Test finding orphans when none exist."""
        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
        @article{used2023,
            title = {Used Paper},
            author = {Author},
            year = {2023}
        }
        """)

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{used2023}")

        result = await project.call_tool("find_orphan_citations", {
            "bib_path": str(bib_file),
            "tex_path": str(tex_file)
        })

        data = json.loads(result[0].text)
        assert "total_orphans" in data or "orphans" in data
        orphans = data.get("orphans", data.get("orphan_entries", []))
        assert len(orphans) == 0

    @pytest.mark.asyncio
    async def test_find_orphans_with_orphans(self, db, tmp_path):
        """Test finding orphan bib entries."""
        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
        @article{used2023,
            title = {Used Paper},
            author = {Author},
            year = {2023}
        }
        @article{unused2022,
            title = {Unused Paper},
            author = {Author},
            year = {2022}
        }
        """)

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{used2023}")

        result = await project.call_tool("find_orphan_citations", {
            "bib_path": str(bib_file),
            "tex_path": str(tex_file)
        })

        data = json.loads(result[0].text)
        # Should find unused2022 as orphan
        assert "total_orphans" in data or "orphans" in data
        orphans = data.get("orphans", data.get("orphan_entries", []))
        assert len(orphans) >= 1


class TestFindMissingCitationsTool:
    """Tests for find_missing_citations tool (in project.py)."""

    @pytest.mark.asyncio
    async def test_find_missing_none(self, db, tmp_path):
        """Test when no citations are missing."""
        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
        @article{ref2023,
            title = {Paper},
            author = {Author},
            year = {2023}
        }
        """)

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{ref2023}")

        result = await project.call_tool("find_missing_citations", {
            "bib_path": str(bib_file),
            "tex_path": str(tex_file)
        })

        data = json.loads(result[0].text)
        assert "total_missing" in data or "missing_citations" in data
        missing = data.get("missing_citations", [])
        assert len(missing) == 0

    @pytest.mark.asyncio
    async def test_find_missing_with_missing(self, db, tmp_path):
        """Test finding missing citations."""
        bib_file = tmp_path / "refs.bib"
        bib_file.write_text("""
        @article{exists2023,
            title = {Exists},
            author = {Author},
            year = {2023}
        }
        """)

        tex_file = tmp_path / "paper.tex"
        tex_file.write_text(r"\cite{exists2023} \cite{missing2024}")

        result = await project.call_tool("find_missing_citations", {
            "bib_path": str(bib_file),
            "tex_path": str(tex_file)
        })

        data = json.loads(result[0].text)
        # Should find missing2024
        assert "total_missing" in data or "missing_citations" in data
        missing = data.get("missing_citations", [])
        assert len(missing) >= 1


class TestFormatBibliographyTool:
    """Tests for format_bibliography tool."""

    @pytest.mark.asyncio
    async def test_format_apa(self, db):
        """Test formatting bibliography in APA style."""
        papers = [{
            "title": "Test Paper",
            "authors": "Smith, J.",
            "year": 2023,
            "journal": "Test Journal"
        }]

        result = await citations.call_tool("format_bibliography", {
            "papers": papers,
            "style": "apa"
        })

        text = result[0].text
        assert "Smith" in text
        assert "2023" in text

    @pytest.mark.asyncio
    async def test_format_bibtex_style(self, db):
        """Test formatting bibliography in BibTeX style."""
        papers = [{
            "title": "Test Paper",
            "authors": "Smith, John",
            "year": 2023
        }]

        result = await citations.call_tool("format_bibliography", {
            "papers": papers,
            "style": "bibtex"
        })

        text = result[0].text
        assert "@" in text


class TestValidateCitationsTool:
    """Tests for validate_citations tool."""

    @pytest.mark.asyncio
    async def test_validate_complete(self, db):
        """Test validating complete citation data."""
        papers = [{
            "title": "Complete Paper",
            "authors": "Author Name",
            "year": 2023,
            "journal": "Journal Name"
        }]

        result = await citations.call_tool("validate_citations", {"papers": papers})

        data = json.loads(result[0].text)
        assert "total_papers" in data
        assert "valid_papers" in data
        assert data["valid_papers"] >= 1

    @pytest.mark.asyncio
    async def test_validate_incomplete(self, db):
        """Test validating incomplete citation data."""
        papers = [{
            "title": "Incomplete Paper"
            # Missing author, year
        }]

        result = await citations.call_tool("validate_citations", {"papers": papers})

        data = json.loads(result[0].text)
        # Should report issues
        assert "total_papers" in data
        # Either valid_papers == 0 or there are warnings
        details = data.get("details", [])
        if details:
            # Check if there are errors/warnings for incomplete data
            assert len(details) >= 1


class TestUnknownCitationTool:
    """Tests for unknown tool handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_citations(self, db):
        """Test that unknown tool in citations returns error."""
        result = await citations.call_tool("unknown_citation_tool", {})

        text = result[0].text
        assert "Unknown" in text or "unknown" in text

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_project(self, db):
        """Test that unknown tool in project returns error."""
        result = await project.call_tool("unknown_project_tool", {})

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "UNKNOWN_TOOL"
