"""Integration tests for Citation Network MCP tools.

Tests for get_paper_citations, get_paper_references, find_common_references,
and build_citation_graph tools.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestGetPaperCitations:
    """Tests for get_paper_citations tool."""

    @pytest.mark.asyncio
    async def test_get_paper_citations_by_doi(self, db, mock_external_apis):
        """Test getting citations by DOI."""
        from mcp_server.tools import citation_network
        from services.external_search import PaperResult

        # Mock the external API response
        mock_citations = [
            PaperResult(
                title="Citing Paper 1",
                authors=["Author A"],
                year=2023,
                doi="10.1234/cite1",
                journal="Journal A",
                abstract="This paper cites the original",
                source="semantic_scholar",
                confidence=1.0,
                citation_count=10,
            ),
            PaperResult(
                title="Citing Paper 2",
                authors=["Author B"],
                year=2024,
                doi="10.1234/cite2",
                journal="Journal B",
                abstract="Another citing paper",
                source="semantic_scholar",
                confidence=1.0,
                citation_count=5,
            ),
        ]

        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_citations = AsyncMock(return_value=mock_citations)

            result = await citation_network.call_tool("get_paper_citations", {
                "doi": "10.1234/original",
                "limit": 10
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            assert data["data"]["citation_count"] == 2
            assert len(data["data"]["citations"]) == 2
            assert data["data"]["citations"][0]["title"] == "Citing Paper 1"

    @pytest.mark.asyncio
    async def test_get_paper_citations_by_paper_id(self, db, mock_external_apis):
        """Test getting citations using database paper ID."""
        from mcp_server.tools import citation_network
        from services import PaperService
        from services.external_search import PaperResult

        # Create a paper in the database
        paper = PaperService.create(
            title="Original Paper",
            doi="10.1234/original"
        )

        mock_citations = [
            PaperResult(
                title="Citing Paper",
                authors=["Author A"],
                year=2023,
                doi="10.1234/cite1",
                journal="Test Journal",
                source="semantic_scholar",
                confidence=1.0,
            ),
        ]

        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_citations = AsyncMock(return_value=mock_citations)

            result = await citation_network.call_tool("get_paper_citations", {
                "paper_id": paper["id"],
                "limit": 10
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            assert data["data"]["source_doi"] == "10.1234/original"

    @pytest.mark.asyncio
    async def test_get_paper_citations_paper_not_found(self, db):
        """Test getting citations for non-existent paper."""
        from mcp_server.tools import citation_network

        result = await citation_network.call_tool("get_paper_citations", {
            "paper_id": 99999
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "PAPER_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_paper_citations_no_identifier(self, db):
        """Test getting citations without any identifier."""
        from mcp_server.tools import citation_network

        result = await citation_network.call_tool("get_paper_citations", {
            "limit": 10
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "INVALID_INPUT"


class TestGetPaperReferences:
    """Tests for get_paper_references tool."""

    @pytest.mark.asyncio
    async def test_get_paper_references_by_doi(self, db, mock_external_apis):
        """Test getting references by DOI."""
        from mcp_server.tools import citation_network
        from services.external_search import PaperResult

        mock_refs = [
            PaperResult(
                title="Referenced Paper 1",
                authors=["Author X"],
                year=2020,
                doi="10.1234/ref1",
                journal="Reference Journal",
                source="semantic_scholar",
                confidence=1.0,
            ),
        ]

        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_references = AsyncMock(return_value=mock_refs)

            result = await citation_network.call_tool("get_paper_references", {
                "doi": "10.1234/original",
                "limit": 10
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            assert data["data"]["reference_count"] == 1
            assert data["data"]["references"][0]["title"] == "Referenced Paper 1"

    @pytest.mark.asyncio
    async def test_get_paper_references_by_title(self, db, mock_external_apis):
        """Test getting references by title."""
        from mcp_server.tools import citation_network
        from services.external_search import PaperResult

        mock_refs = [
            PaperResult(
                title="Old Paper",
                authors=["Classic Author"],
                year=1995,
                doi=None,
                journal="Classic Journal",
                source="semantic_scholar",
                confidence=1.0,
            ),
        ]

        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_references = AsyncMock(return_value=mock_refs)

            result = await citation_network.call_tool("get_paper_references", {
                "title": "Modern Paper About Something",
                "limit": 10
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            assert data["data"]["source_title"] == "Modern Paper About Something"


class TestFindCommonReferences:
    """Tests for find_common_references tool."""

    @pytest.mark.asyncio
    async def test_find_common_references_success(self, db, mock_external_apis):
        """Test finding papers with common references."""
        from mcp_server.tools import citation_network
        from services import PaperService
        from services.external_search import PaperResult

        # Create source paper
        source = PaperService.create(
            title="Source Paper",
            doi="10.1234/source"
        )

        # Create another paper that might share references
        other = PaperService.create(
            title="Related Paper",
            doi="10.1234/related"
        )

        # Mock references
        source_refs = [
            PaperResult(
                title="Shared Ref 1",
                authors=["A"],
                year=2020,
                doi="10.1234/shared1",
                journal="Shared Journal",
                source="semantic_scholar",
                confidence=1.0,
            ),
            PaperResult(
                title="Shared Ref 2",
                authors=["B"],
                year=2019,
                doi="10.1234/shared2",
                journal="Shared Journal",
                source="semantic_scholar",
                confidence=1.0,
            ),
        ]

        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_references = AsyncMock(return_value=source_refs)

            result = await citation_network.call_tool("find_common_references", {
                "paper_id": source["id"],
                "min_shared": 1
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            assert "source_reference_count" in data["data"]

    @pytest.mark.asyncio
    async def test_find_common_references_paper_not_found(self, db):
        """Test with non-existent paper."""
        from mcp_server.tools import citation_network

        result = await citation_network.call_tool("find_common_references", {
            "paper_id": 99999
        })

        data = json.loads(result[0].text)
        assert data["success"] is False
        assert data["code"] == "PAPER_NOT_FOUND"


class TestBuildCitationGraph:
    """Tests for build_citation_graph tool."""

    @pytest.mark.asyncio
    async def test_build_citation_graph_basic(self, db, mock_external_apis):
        """Test building a basic citation graph."""
        from mcp_server.tools import citation_network
        from services import PaperService
        from services.external_search import PaperResult

        # Create papers
        paper1 = PaperService.create(
            title="Paper 1",
            doi="10.1234/p1"
        )
        paper2 = PaperService.create(
            title="Paper 2",
            doi="10.1234/p2"
        )

        # Mock empty citations/references for simplicity
        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_citations = AsyncMock(return_value=[])
            mock_instance.get_paper_references = AsyncMock(return_value=[])

            result = await citation_network.call_tool("build_citation_graph", {
                "paper_ids": [paper1["id"], paper2["id"]]
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            assert data["data"]["node_count"] >= 2  # At least our library papers
            assert "nodes" in data["data"]
            assert "edges" in data["data"]

    @pytest.mark.asyncio
    async def test_build_citation_graph_with_citations(self, db, mock_external_apis):
        """Test building graph with actual citations."""
        from mcp_server.tools import citation_network
        from services import PaperService
        from services.external_search import PaperResult

        # Create paper
        paper = PaperService.create(
            title="Main Paper",
            doi="10.1234/main"
        )

        # Mock a citing paper that's also in library
        citing_paper = PaperService.create(
            title="Citing Paper In Library",
            doi="10.1234/citing"
        )

        mock_citations = [
            PaperResult(
                title="Citing Paper In Library",
                authors=["A"],
                year=2023,
                doi="10.1234/citing",
                journal="Test Journal",
                source="semantic_scholar",
                confidence=1.0,
            ),
        ]

        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_citations = AsyncMock(return_value=mock_citations)
            mock_instance.get_paper_references = AsyncMock(return_value=[])

            result = await citation_network.call_tool("build_citation_graph", {
                "paper_ids": [paper["id"]]
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            # Should have at least the main paper and the citing paper
            assert data["data"]["node_count"] >= 1

    @pytest.mark.asyncio
    async def test_build_citation_graph_include_external(self, db, mock_external_apis):
        """Test building graph including external papers."""
        from mcp_server.tools import citation_network
        from services import PaperService
        from services.external_search import PaperResult

        paper = PaperService.create(
            title="Main Paper",
            doi="10.1234/main"
        )

        mock_citations = [
            PaperResult(
                title="External Citing Paper",
                authors=["External Author"],
                year=2023,
                doi="10.1234/external",
                journal="External Journal",
                source="semantic_scholar",
                confidence=1.0,
            ),
        ]

        with patch.object(
            citation_network, 'ExternalSearchService'
        ) as MockService:
            mock_instance = MockService.return_value
            mock_instance.get_paper_citations = AsyncMock(return_value=mock_citations)
            mock_instance.get_paper_references = AsyncMock(return_value=[])

            result = await citation_network.call_tool("build_citation_graph", {
                "paper_ids": [paper["id"]],
                "include_external": True
            })

            data = json.loads(result[0].text)
            assert data["success"] is True
            # Should include external nodes
            node_types = [n["type"] for n in data["data"]["nodes"]]
            assert "library" in node_types


class TestToolSchemas:
    """Tests for tool schema definitions."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_citation_network_tools(self, db):
        """Test that all citation network tools are listed."""
        from mcp_server.tools import citation_network

        tools = await citation_network.list_tools()
        tool_names = [t.name for t in tools]

        assert "get_paper_citations" in tool_names
        assert "get_paper_references" in tool_names
        assert "find_common_references" in tool_names
        assert "build_citation_graph" in tool_names

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, db):
        """Test that unknown tools return error."""
        from mcp_server.tools import citation_network

        result = await citation_network.call_tool("unknown_tool", {})
        data = json.loads(result[0].text)

        assert data["success"] is False
        assert data["code"] == "UNKNOWN_TOOL"
