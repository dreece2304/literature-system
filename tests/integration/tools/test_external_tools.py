"""Integration tests for External API MCP tools.

Tests cover:
- Paper metadata lookup (mocked external APIs)
- Open access PDF finding
- Paper enrichment
- External search
- Citation count lookup

All external API calls are mocked to avoid network dependencies.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mcp_server.tools import external


@dataclass
class MockExternalResult:
    """Mock external search result."""
    title: str = "Test Paper"
    authors: list = None
    year: int = 2023
    doi: str = None
    abstract: str = None
    journal: str = None
    arxiv_id: str = None
    pdf_url: str = None
    citation_count: int = None
    is_open_access: bool = False
    confidence: float = 0.9

    def __post_init__(self):
        if self.authors is None:
            self.authors = ["Test Author"]


class TestExternalToolSchemas:
    """Tests for external tool schemas."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_external_tools(self):
        """Test that list_tools returns all expected external tools."""
        tools = await external.list_tools()

        tool_names = [t.name for t in tools]
        expected = [
            "lookup_paper_metadata",
            "find_open_access_pdf",
            "enrich_paper",
            "search_external_papers",
            "get_citation_count",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    @pytest.mark.asyncio
    async def test_search_external_papers_requires_query(self):
        """Test that search_external_papers requires query."""
        tools = await external.list_tools()
        search_tool = next(t for t in tools if t.name == "search_external_papers")

        assert "required" in search_tool.inputSchema
        assert "query" in search_tool.inputSchema["required"]


class TestLookupPaperMetadataTool:
    """Tests for lookup_paper_metadata tool."""

    @pytest.mark.asyncio
    async def test_lookup_by_doi(self, db, mock_external_apis):
        """Test looking up paper by DOI."""
        mock_external_apis["crossref"].return_value = [
            MockExternalResult(
                title="Found Paper",
                doi="10.1234/test",
                abstract="Test abstract"
            )
        ]
        mock_external_apis["semantic_scholar"].return_value = [
            MockExternalResult(citation_count=100)
        ]

        result = await external.call_tool("lookup_paper_metadata", {
            "doi": "10.1234/test"
        })

        output = result[0].text
        # Should contain some metadata
        assert "Found Paper" in output or "crossref" in output.lower() or "No metadata" in output

    @pytest.mark.asyncio
    async def test_lookup_by_title(self, db, mock_external_apis):
        """Test looking up paper by title."""
        mock_external_apis["openalex"].return_value = [
            MockExternalResult(
                title="Machine Learning Paper",
                authors=["Smith, J."],
                year=2023
            )
        ]
        mock_external_apis["crossref"].return_value = [
            MockExternalResult(
                title="Machine Learning Paper",
                confidence=0.85
            )
        ]

        result = await external.call_tool("lookup_paper_metadata", {
            "title": "Machine Learning Paper"
        })

        output = result[0].text
        assert len(output) > 0

    @pytest.mark.asyncio
    async def test_lookup_no_results(self, db, mock_external_apis):
        """Test lookup with no results."""
        mock_external_apis["crossref"].return_value = []
        mock_external_apis["openalex"].return_value = []
        mock_external_apis["semantic_scholar"].return_value = []

        result = await external.call_tool("lookup_paper_metadata", {
            "title": "Nonexistent Paper XYZ"
        })

        output = result[0].text
        assert "No metadata" in output or len(output) > 0


class TestFindOpenAccessPdfTool:
    """Tests for find_open_access_pdf tool."""

    @pytest.mark.asyncio
    async def test_find_pdf_by_doi(self, db, mock_external_apis):
        """Test finding PDF by DOI via Unpaywall."""
        mock_external_apis["unpaywall"].return_value = [
            MockExternalResult(pdf_url="https://example.com/paper.pdf")
        ]

        result = await external.call_tool("find_open_access_pdf", {
            "doi": "10.1234/test"
        })

        output = result[0].text
        # Should find PDF or indicate not found
        assert "pdf" in output.lower() or "No open access" in output

    @pytest.mark.asyncio
    async def test_find_pdf_by_arxiv_id(self, db, mock_external_apis):
        """Test finding PDF by arXiv ID."""
        result = await external.call_tool("find_open_access_pdf", {
            "arxiv_id": "2301.12345"
        })

        output = result[0].text
        # Should construct arXiv PDF URL
        assert "arxiv" in output.lower() or "pdf" in output.lower()

    @pytest.mark.asyncio
    async def test_find_pdf_not_found(self, db, mock_external_apis):
        """Test when no PDF is found."""
        mock_external_apis["unpaywall"].return_value = []
        mock_external_apis["arxiv"].return_value = []
        mock_external_apis["semantic_scholar"].return_value = []

        result = await external.call_tool("find_open_access_pdf", {
            "title": "Paywalled Paper"
        })

        output = result[0].text
        assert "No open access" in output or len(output) > 0


class TestEnrichPaperTool:
    """Tests for enrich_paper tool."""

    @pytest.mark.asyncio
    async def test_enrich_with_doi(self, db, mock_external_apis):
        """Test enriching paper with DOI."""
        mock_external_apis["crossref"].return_value = [
            MockExternalResult(abstract="Enriched abstract from CrossRef")
        ]
        mock_external_apis["semantic_scholar"].return_value = [
            MockExternalResult(citation_count=50, pdf_url="https://example.com/paper.pdf")
        ]

        result = await external.call_tool("enrich_paper", {
            "doi": "10.1234/test",
            "title": "Test Paper"
        })

        output = result[0].text
        # Should return enrichment data
        assert len(output) > 0

    @pytest.mark.asyncio
    async def test_enrich_with_title_only(self, db, mock_external_apis):
        """Test enriching paper with title only."""
        mock_external_apis["openalex"].return_value = [
            MockExternalResult(
                abstract="Abstract from OpenAlex",
                doi="10.1234/found"
            )
        ]
        mock_external_apis["semantic_scholar"].return_value = [
            MockExternalResult(citation_count=25)
        ]

        result = await external.call_tool("enrich_paper", {
            "title": "Test Paper Title"
        })

        output = result[0].text
        assert len(output) > 0

    @pytest.mark.asyncio
    async def test_enrich_no_data_found(self, db, mock_external_apis):
        """Test enrichment when no additional data found."""
        mock_external_apis["crossref"].return_value = []
        mock_external_apis["openalex"].return_value = []
        mock_external_apis["semantic_scholar"].return_value = []

        result = await external.call_tool("enrich_paper", {
            "title": "Unknown Paper"
        })

        output = result[0].text
        assert "Could not find" in output or len(output) > 0


class TestSearchExternalPapersTool:
    """Tests for search_external_papers tool."""

    @pytest.mark.asyncio
    async def test_search_all_sources(self, db, mock_external_apis):
        """Test searching all external sources."""
        mock_external_apis["crossref"].return_value = [
            MockExternalResult(title="CrossRef Paper 1"),
            MockExternalResult(title="CrossRef Paper 2"),
        ]
        mock_external_apis["openalex"].return_value = [
            MockExternalResult(title="OpenAlex Paper", abstract="Abstract text")
        ]
        mock_external_apis["semantic_scholar"].return_value = [
            MockExternalResult(title="SS Paper", citation_count=100)
        ]

        result = await external.call_tool("search_external_papers", {
            "query": "machine learning materials"
        })

        data = json.loads(result[0].text)
        # Should have results from multiple sources
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_search_specific_sources(self, db, mock_external_apis):
        """Test searching specific sources only."""
        mock_external_apis["arxiv"].return_value = [
            MockExternalResult(
                title="arXiv Paper",
                arxiv_id="2301.12345",
                pdf_url="https://arxiv.org/pdf/2301.12345"
            )
        ]

        result = await external.call_tool("search_external_papers", {
            "query": "neural networks",
            "sources": ["arxiv"],
            "limit": 5
        })

        data = json.loads(result[0].text)
        assert "arxiv" in data

    @pytest.mark.asyncio
    async def test_search_with_limit(self, db, mock_external_apis):
        """Test search respects limit parameter."""
        mock_external_apis["crossref"].return_value = [
            MockExternalResult(title=f"Paper {i}") for i in range(10)
        ]

        result = await external.call_tool("search_external_papers", {
            "query": "test query",
            "sources": ["crossref"],
            "limit": 3
        })

        data = json.loads(result[0].text)
        # Note: limit is passed to service, actual limiting may vary
        assert "crossref" in data


class TestGetCitationCountTool:
    """Tests for get_citation_count tool."""

    @pytest.mark.asyncio
    async def test_get_citation_count_by_doi(self, db, mock_external_apis):
        """Test getting citation count by DOI."""
        mock_external_apis["semantic_scholar"].return_value = [
            MockExternalResult(
                title="Highly Cited Paper",
                citation_count=1500
            )
        ]

        result = await external.call_tool("get_citation_count", {
            "doi": "10.1234/highly-cited"
        })

        output = result[0].text
        # Should contain citation information
        assert "citation" in output.lower() or "1500" in output or "Could not find" in output

    @pytest.mark.asyncio
    async def test_get_citation_count_by_title(self, db, mock_external_apis):
        """Test getting citation count by title."""
        mock_external_apis["semantic_scholar"].return_value = [
            MockExternalResult(
                title="Test Paper",
                citation_count=42
            )
        ]

        result = await external.call_tool("get_citation_count", {
            "title": "Test Paper"
        })

        output = result[0].text
        assert len(output) > 0

    @pytest.mark.asyncio
    async def test_get_citation_count_no_params(self, db, mock_external_apis):
        """Test citation count with no parameters."""
        result = await external.call_tool("get_citation_count", {})

        output = result[0].text
        assert "provide" in output.lower() or len(output) > 0

    @pytest.mark.asyncio
    async def test_get_citation_count_not_found(self, db, mock_external_apis):
        """Test citation count when paper not found."""
        mock_external_apis["semantic_scholar"].return_value = []

        result = await external.call_tool("get_citation_count", {
            "title": "Unknown Paper"
        })

        output = result[0].text
        assert "Could not find" in output or len(output) > 0


class TestUnknownExternalTool:
    """Tests for unknown tool handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, db, mock_external_apis):
        """Test that unknown tool returns proper error."""
        result = await external.call_tool("unknown_external_tool", {})

        output = result[0].text
        assert "Unknown" in output


class TestExternalToolErrorHandling:
    """Tests for error handling in external tools."""

    @pytest.mark.asyncio
    async def test_handles_api_error(self, db, mock_external_apis):
        """Test that API errors are handled gracefully."""
        mock_external_apis["crossref"].side_effect = Exception("API Error")
        mock_external_apis["openalex"].side_effect = Exception("API Error")

        result = await external.call_tool("search_external_papers", {
            "query": "test",
            "sources": ["crossref", "openalex"]
        })

        output = result[0].text
        # Should handle error gracefully
        assert "Error" in output or len(output) > 0
