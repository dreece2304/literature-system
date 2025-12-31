"""Real integration tests for External API MCP tools.

These tests actually hit the external APIs (CrossRef, OpenAlex, Semantic Scholar, arXiv).
They require network access and may be slower than mocked tests.

Run with: pytest tests/integration/tools/test_external_tools_real.py -v
Skip in CI with: pytest -m "not real_api"
"""
import pytest
import json

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from mcp_server.tools import external


# Mark all tests in this module as real_api tests
pytestmark = [
    pytest.mark.real_api,
    pytest.mark.asyncio,
]


class TestLookupPaperMetadataReal:
    """Real API tests for lookup_paper_metadata tool."""

    async def test_lookup_by_doi_real(self, db):
        """Test looking up a real paper by DOI."""
        # Use a well-known paper DOI (Attention Is All You Need)
        result = await external.call_tool("lookup_paper_metadata", {
            "doi": "10.48550/arXiv.1706.03762"
        })

        output = result[0].text
        # Should find metadata
        assert len(output) > 20
        # May contain paper info or no metadata message
        print(f"DOI lookup result: {output[:500]}")

    async def test_lookup_by_title_real(self, db):
        """Test looking up paper by title (famous paper)."""
        result = await external.call_tool("lookup_paper_metadata", {
            "title": "Attention Is All You Need"
        })

        output = result[0].text
        assert len(output) > 20
        # Should find the paper or return no metadata message
        print(f"Title lookup result: {output[:500]}")

    async def test_lookup_ald_paper_real(self, db):
        """Test looking up an ALD paper by title."""
        result = await external.call_tool("lookup_paper_metadata", {
            "title": "Atomic layer deposition overview and applications"
        })

        output = result[0].text
        assert len(output) > 10
        print(f"ALD paper lookup: {output[:500]}")


class TestSearchExternalPapersReal:
    """Real API tests for search_external_papers tool."""

    async def test_search_crossref_real(self, db):
        """Test searching CrossRef for real papers."""
        result = await external.call_tool("search_external_papers", {
            "query": "atomic layer deposition thin films",
            "sources": ["crossref"],
            "limit": 3
        })

        data = json.loads(result[0].text)
        print(f"CrossRef search result: {json.dumps(data, indent=2)[:1000]}")

        assert "crossref" in data
        # CrossRef should return results for this common topic
        assert len(data["crossref"]) > 0
        # Check result structure
        if data["crossref"]:
            paper = data["crossref"][0]
            assert "title" in paper

    async def test_search_openalex_real(self, db):
        """Test searching OpenAlex for real papers."""
        result = await external.call_tool("search_external_papers", {
            "query": "machine learning materials science",
            "sources": ["openalex"],
            "limit": 3
        })

        data = json.loads(result[0].text)
        print(f"OpenAlex search result: {json.dumps(data, indent=2)[:1000]}")

        assert "openalex" in data
        assert len(data["openalex"]) > 0

    async def test_search_semantic_scholar_real(self, db):
        """Test searching Semantic Scholar for real papers."""
        result = await external.call_tool("search_external_papers", {
            "query": "transformer neural network attention",
            "sources": ["semantic_scholar"],
            "limit": 3
        })

        data = json.loads(result[0].text)
        print(f"Semantic Scholar search: {json.dumps(data, indent=2)[:1000]}")

        assert "semantic_scholar" in data
        # Semantic Scholar should find papers about transformers
        assert len(data["semantic_scholar"]) > 0

    async def test_search_arxiv_real(self, db):
        """Test searching arXiv for real papers."""
        result = await external.call_tool("search_external_papers", {
            "query": "large language models",
            "sources": ["arxiv"],
            "limit": 3
        })

        data = json.loads(result[0].text)
        print(f"arXiv search result: {json.dumps(data, indent=2)[:1000]}")

        assert "arxiv" in data
        # arXiv has lots of LLM papers
        assert len(data["arxiv"]) > 0
        # Check for arxiv-specific fields
        if data["arxiv"]:
            paper = data["arxiv"][0]
            assert "arxiv_id" in paper or "pdf_url" in paper

    async def test_search_all_sources_real(self, db):
        """Test searching all sources for a broad topic."""
        result = await external.call_tool("search_external_papers", {
            "query": "deep learning",
            "limit": 2
        })

        data = json.loads(result[0].text)
        print(f"All sources search: {json.dumps(data, indent=2)[:1500]}")

        # Should have results from multiple sources
        assert isinstance(data, dict)
        sources_with_results = [k for k, v in data.items() if v]
        assert len(sources_with_results) >= 1


class TestFindOpenAccessPdfReal:
    """Real API tests for find_open_access_pdf tool."""

    async def test_find_arxiv_pdf_real(self, db):
        """Test finding PDF for an arXiv paper."""
        result = await external.call_tool("find_open_access_pdf", {
            "arxiv_id": "1706.03762"
        })

        output = result[0].text
        print(f"arXiv PDF result: {output}")

        # Should construct arXiv PDF URL
        assert "arxiv" in output.lower()
        assert "pdf" in output.lower()

    async def test_find_pdf_by_doi_real(self, db):
        """Test finding PDF via DOI using Unpaywall."""
        # Use DOI of an open access paper
        result = await external.call_tool("find_open_access_pdf", {
            "doi": "10.1038/s41586-021-03819-2"  # AlphaFold paper (Nature)
        })

        output = result[0].text
        print(f"DOI PDF result: {output}")

        # May find PDF or indicate not found
        assert len(output) > 10

    async def test_find_pdf_by_title_real(self, db):
        """Test finding PDF by searching title."""
        result = await external.call_tool("find_open_access_pdf", {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers"
        })

        output = result[0].text
        print(f"Title PDF result: {output}")

        # Should attempt to find PDF
        assert len(output) > 10


class TestGetCitationCountReal:
    """Real API tests for get_citation_count tool."""

    async def test_get_citation_count_famous_paper(self, db):
        """Test getting citation count for a famous paper."""
        result = await external.call_tool("get_citation_count", {
            "title": "Deep Residual Learning for Image Recognition"
        })

        output = result[0].text
        print(f"Citation count result: {output}")

        # ResNet paper has thousands of citations
        if "citation_count" in output:
            data = json.loads(output)
            assert data["citation_count"] > 1000

    async def test_get_citation_count_by_doi(self, db):
        """Test getting citation count by DOI."""
        result = await external.call_tool("get_citation_count", {
            "doi": "10.48550/arXiv.1706.03762"
        })

        output = result[0].text
        print(f"DOI citation count: {output}")

        # Should return some result
        assert len(output) > 10


class TestEnrichPaperReal:
    """Real API tests for enrich_paper tool."""

    async def test_enrich_with_title_real(self, db):
        """Test enriching paper data with just a title."""
        result = await external.call_tool("enrich_paper", {
            "title": "ImageNet Classification with Deep Convolutional Neural Networks"
        })

        output = result[0].text
        print(f"Enrichment result: {output}")

        # Should find enrichment data for AlexNet paper
        assert len(output) > 20
        # Should have found abstract or citation count
        if "Could not find" not in output:
            data = json.loads(output)
            assert "abstract" in data or "citation_count" in data

    async def test_enrich_with_doi_real(self, db):
        """Test enriching paper data with DOI."""
        result = await external.call_tool("enrich_paper", {
            "doi": "10.1038/nature14539",  # Deep learning review (Nature)
            "title": "Deep learning"
        })

        output = result[0].text
        print(f"DOI enrichment result: {output}")

        assert len(output) > 10


class TestExternalToolRobustness:
    """Tests for error handling and edge cases with real APIs."""

    async def test_search_nonsense_query(self, db):
        """Test searching with nonsense query."""
        result = await external.call_tool("search_external_papers", {
            "query": "xyzzy123nonsense456gibberish",
            "sources": ["crossref"],
            "limit": 3
        })

        data = json.loads(result[0].text)
        # Should return empty or minimal results, not error
        assert "crossref" in data
        # Results should be empty or very few
        assert len(data["crossref"]) <= 3

    async def test_lookup_invalid_doi(self, db):
        """Test looking up invalid DOI."""
        result = await external.call_tool("lookup_paper_metadata", {
            "doi": "10.invalid/not-a-real-doi"
        })

        output = result[0].text
        # Should handle gracefully
        assert len(output) > 0
        print(f"Invalid DOI result: {output}")

    async def test_empty_search(self, db):
        """Test search with empty/minimal query."""
        result = await external.call_tool("search_external_papers", {
            "query": "a",
            "sources": ["arxiv"],
            "limit": 1
        })

        # Should not crash
        output = result[0].text
        assert len(output) > 0
