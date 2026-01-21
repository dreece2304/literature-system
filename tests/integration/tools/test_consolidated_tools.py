"""Tests for consolidated MCP tools.

Tests the new consolidated tool structure:
- extraction.py: extract_paper, get_extraction_status, manage_pdf_processing, etc.
- project.py: manage_bibtex, citation_health_check, scan_citations, manage_project
- citations.py: manuscript_tools, format_citation
- pdf.py: acquire_pdf, manage_pdf, find_duplicates
- validation.py: get_validation_status, validate_papers
"""
from __future__ import annotations

import json
import pytest


class TestExtractionTools:
    """Tests for consolidated extraction tools."""

    @pytest.mark.asyncio
    async def test_extract_paper_lists_consolidated_tools(self, db):
        """Verify extraction module lists 8 consolidated tools."""
        from mcp_server.tools import extraction

        tools = await extraction.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 8
        assert "extract_paper" in tool_names
        assert "get_extraction_status" in tool_names
        assert "manage_pdf_processing" in tool_names
        assert "manage_references" in tool_names
        assert "verify_extraction" in tool_names

    @pytest.mark.asyncio
    async def test_extract_paper_tier_parameter(self, db):
        """Test extract_paper with tier parameter."""
        from mcp_server.tools import extraction

        # Test that tool accepts tier parameter in schema
        tools = await extraction.list_tools()
        extract_tool = next(t for t in tools if t.name == "extract_paper")

        schema = extract_tool.inputSchema
        assert "tier" in schema["properties"]
        assert schema["properties"]["tier"]["enum"] == ["quick", "deep"]

    @pytest.mark.asyncio
    async def test_get_extraction_status_view_parameter(self, db):
        """Test get_extraction_status with view parameter."""
        from mcp_server.tools import extraction

        tools = await extraction.list_tools()
        status_tool = next(t for t in tools if t.name == "get_extraction_status")

        schema = status_tool.inputSchema
        assert "view" in schema["properties"]
        assert set(schema["properties"]["view"]["enum"]) == {"status", "llm", "queue", "reextraction"}

    @pytest.mark.asyncio
    async def test_manage_pdf_processing_action_parameter(self, db):
        """Test manage_pdf_processing with action parameter."""
        from mcp_server.tools import extraction

        tools = await extraction.list_tools()
        pdf_tool = next(t for t in tools if t.name == "manage_pdf_processing")

        schema = pdf_tool.inputSchema
        assert "action" in schema["properties"]

    @pytest.mark.asyncio
    async def test_legacy_tool_names_not_exposed(self, db):
        """Verify legacy tool names are not in the tool list."""
        from mcp_server.tools import extraction

        tools = await extraction.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list
        assert "extract_paper_quick" not in tool_names
        assert "extract_paper_deep" not in tool_names
        assert "get_llm_status" not in tool_names
        assert "get_extraction_queue" not in tool_names


class TestProjectTools:
    """Tests for consolidated project tools."""

    @pytest.mark.asyncio
    async def test_project_lists_consolidated_tools(self, db):
        """Verify project module lists 4 consolidated tools."""
        from mcp_server.tools import project

        tools = await project.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 4
        assert "manage_bibtex" in tool_names
        assert "citation_health_check" in tool_names
        assert "scan_citations" in tool_names
        assert "manage_project" in tool_names

    @pytest.mark.asyncio
    async def test_manage_bibtex_action_parameter(self, db):
        """Test manage_bibtex with action parameter."""
        from mcp_server.tools import project

        tools = await project.list_tools()
        bibtex_tool = next(t for t in tools if t.name == "manage_bibtex")

        schema = bibtex_tool.inputSchema
        assert "action" in schema["properties"]
        assert set(schema["properties"]["action"]["enum"]) == {"parse", "link", "import", "export", "sync"}

    @pytest.mark.asyncio
    async def test_citation_health_check_check_parameter(self, db):
        """Test citation_health_check with check parameter."""
        from mcp_server.tools import project

        tools = await project.list_tools()
        health_tool = next(t for t in tools if t.name == "citation_health_check")

        schema = health_tool.inputSchema
        assert "check" in schema["properties"]
        assert set(schema["properties"]["check"]["enum"]) == {"all", "orphans", "missing", "incomplete", "duplicates"}

    @pytest.mark.asyncio
    async def test_legacy_project_tools_not_exposed(self, db):
        """Verify legacy project tool names are not in the tool list."""
        from mcp_server.tools import project

        tools = await project.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list
        assert "parse_bib_file" not in tool_names
        assert "link_bib_to_database" not in tool_names
        assert "find_orphan_citations" not in tool_names


class TestCitationTools:
    """Tests for consolidated citation tools."""

    @pytest.mark.asyncio
    async def test_citations_lists_consolidated_tools(self, db):
        """Verify citations module lists 2 consolidated tools."""
        from mcp_server.tools import citations

        tools = await citations.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 2
        assert "manuscript_tools" in tool_names
        assert "format_citation" in tool_names

    @pytest.mark.asyncio
    async def test_manuscript_tools_action_parameter(self, db):
        """Test manuscript_tools with action parameter."""
        from mcp_server.tools import citations

        tools = await citations.list_tools()
        manuscript_tool = next(t for t in tools if t.name == "manuscript_tools")

        schema = manuscript_tool.inputSchema
        assert "action" in schema["properties"]
        assert set(schema["properties"]["action"]["enum"]) == {"scan", "check"}

    @pytest.mark.asyncio
    async def test_format_citation_action_parameter(self, db):
        """Test format_citation with action parameter."""
        from mcp_server.tools import citations

        tools = await citations.list_tools()
        format_tool = next(t for t in tools if t.name == "format_citation")

        schema = format_tool.inputSchema
        assert "action" in schema["properties"]
        assert set(schema["properties"]["action"]["enum"]) == {"bibtex", "suggest_key", "validate", "bibliography"}

    @pytest.mark.asyncio
    async def test_legacy_citation_tools_not_exposed(self, db):
        """Verify legacy citation tool names are not in the tool list."""
        from mcp_server.tools import citations

        tools = await citations.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list
        assert "scan_manuscript" not in tool_names
        assert "check_citations" not in tool_names
        assert "generate_bibtex" not in tool_names


class TestPDFTools:
    """Tests for consolidated PDF tools."""

    @pytest.mark.asyncio
    async def test_pdf_lists_consolidated_tools(self, db):
        """Verify pdf module lists 3 consolidated tools."""
        from mcp_server.tools import pdf

        tools = await pdf.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 3
        assert "acquire_pdf" in tool_names
        assert "manage_pdf" in tool_names
        assert "find_duplicates" in tool_names

    @pytest.mark.asyncio
    async def test_acquire_pdf_method_parameter(self, db):
        """Test acquire_pdf with method parameter."""
        from mcp_server.tools import pdf

        tools = await pdf.list_tools()
        acquire_tool = next(t for t in tools if t.name == "acquire_pdf")

        schema = acquire_tool.inputSchema
        assert "method" in schema["properties"]
        assert set(schema["properties"]["method"]["enum"]) == {"open_access", "browser_queue"}

    @pytest.mark.asyncio
    async def test_manage_pdf_action_parameter(self, db):
        """Test manage_pdf with action parameter."""
        from mcp_server.tools import pdf

        tools = await pdf.list_tools()
        manage_tool = next(t for t in tools if t.name == "manage_pdf")

        schema = manage_tool.inputSchema
        assert "action" in schema["properties"]
        assert set(schema["properties"]["action"]["enum"]) == {"status", "queue_status", "process", "clear"}

    @pytest.mark.asyncio
    async def test_browser_pdf_module_returns_empty(self, db):
        """Verify browser_pdf module returns no tools (consolidated into pdf.py)."""
        from mcp_server.tools import browser_pdf

        tools = await browser_pdf.list_tools()
        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_legacy_pdf_tools_not_exposed(self, db):
        """Verify legacy PDF tool names are not in the tool list."""
        from mcp_server.tools import pdf

        tools = await pdf.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list
        assert "acquire_paper_pdf" not in tool_names
        assert "get_pdf_status" not in tool_names
        assert "queue_pdf_download" not in tool_names


class TestValidationTools:
    """Tests for consolidated validation tools."""

    @pytest.mark.asyncio
    async def test_validation_lists_consolidated_tools(self, db):
        """Verify validation module lists 2 consolidated tools."""
        from mcp_server.tools import validation

        tools = await validation.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 2
        assert "get_validation_status" in tool_names
        assert "validate_papers" in tool_names

    @pytest.mark.asyncio
    async def test_validate_papers_action_parameter(self, db):
        """Test validate_papers with action parameter."""
        from mcp_server.tools import validation

        tools = await validation.list_tools()
        validate_tool = next(t for t in tools if t.name == "validate_papers")

        schema = validate_tool.inputSchema
        assert "action" in schema["properties"]
        assert set(schema["properties"]["action"]["enum"]) == {"validate", "queue", "reset"}

    @pytest.mark.asyncio
    async def test_legacy_validation_tools_not_exposed(self, db):
        """Verify legacy validation tool names are not in the tool list."""
        from mcp_server.tools import validation

        tools = await validation.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list
        assert "validate_paper" not in tool_names
        assert "validate_papers_batch" not in tool_names
        assert "get_validation_queue" not in tool_names


class TestSearchTools:
    """Tests for search tools after redundant removal."""

    @pytest.mark.asyncio
    async def test_search_redundant_tools_removed(self, db):
        """Verify search_by_author and search_by_tag removed."""
        from mcp_server.tools import search

        tools = await search.list_tools()
        tool_names = [t.name for t in tools]

        # These were redundant with list_papers(author=X) and list_papers(tag=X)
        assert "search_by_author" not in tool_names
        assert "search_by_tag" not in tool_names
        assert len(tools) == 2
        assert "search" in tool_names
        assert "get_search_status" in tool_names


class TestNotesTools:
    """Tests for notes tools after redundant removal."""

    @pytest.mark.asyncio
    async def test_notes_redundant_tools_removed(self, db):
        """Verify get_paper_notes removed (use list_notes with paper_id)."""
        from mcp_server.tools import notes

        tools = await notes.list_tools()
        tool_names = [t.name for t in tools]

        # get_paper_notes was redundant with list_notes(paper_id=X)
        assert "get_paper_notes" not in tool_names
        assert len(tools) == 6
        assert "list_notes" in tool_names


class TestPapersTools:
    """Tests for papers tools."""

    @pytest.mark.asyncio
    async def test_papers_does_not_have_extraction_queue(self, db):
        """Verify get_extraction_queue was removed from papers.py."""
        from mcp_server.tools import papers

        tools = await papers.list_tools()
        tool_names = [t.name for t in tools]

        # get_extraction_queue moved to extraction.py
        assert "get_extraction_queue" not in tool_names
        assert len(tools) == 9


class TestCitationNetworkTools:
    """Tests for consolidated citation network tools."""

    @pytest.mark.asyncio
    async def test_citation_network_lists_consolidated_tools(self, db):
        """Verify citation_network module lists 6 tools (was 7)."""
        from mcp_server.tools import citation_network

        tools = await citation_network.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 6
        assert "get_citations" in tool_names
        assert "find_common_references" in tool_names
        assert "build_citation_graph" in tool_names
        assert "import_references_from_paper" in tool_names
        assert "get_local_citations" in tool_names
        assert "link_papers_citation" in tool_names

    @pytest.mark.asyncio
    async def test_get_citations_direction_parameter(self, db):
        """Test get_citations with direction parameter."""
        from mcp_server.tools import citation_network

        tools = await citation_network.list_tools()
        citations_tool = next(t for t in tools if t.name == "get_citations")

        schema = citations_tool.inputSchema
        assert "direction" in schema["properties"]
        assert set(schema["properties"]["direction"]["enum"]) == {"incoming", "outgoing"}
        assert "direction" in schema.get("required", [])

    @pytest.mark.asyncio
    async def test_legacy_citation_network_tools_not_exposed(self, db):
        """Verify legacy citation network tool names are not in the tool list."""
        from mcp_server.tools import citation_network

        tools = await citation_network.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list (consolidated into get_citations)
        assert "get_paper_citations" not in tool_names
        assert "get_paper_references" not in tool_names


class TestImportExportTools:
    """Tests for consolidated import/export tools."""

    @pytest.mark.asyncio
    async def test_import_export_lists_consolidated_tools(self, db):
        """Verify import_export module lists 3 tools (was 6)."""
        from mcp_server.tools import import_export

        tools = await import_export.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 3
        assert "import_paper" in tool_names
        assert "export" in tool_names
        assert "get_enrichment_queue" in tool_names

    @pytest.mark.asyncio
    async def test_import_paper_source_parameter(self, db):
        """Test import_paper with source parameter."""
        from mcp_server.tools import import_export

        tools = await import_export.list_tools()
        import_tool = next(t for t in tools if t.name == "import_paper")

        schema = import_tool.inputSchema
        assert "source" in schema["properties"]
        assert set(schema["properties"]["source"]["enum"]) == {"wizard", "bibtex", "external"}

    @pytest.mark.asyncio
    async def test_export_source_parameter(self, db):
        """Test export with source parameter."""
        from mcp_server.tools import import_export

        tools = await import_export.list_tools()
        export_tool = next(t for t in tools if t.name == "export")

        schema = export_tool.inputSchema
        assert "source" in schema["properties"]
        assert set(schema["properties"]["source"]["enum"]) == {"papers", "collection"}

    @pytest.mark.asyncio
    async def test_legacy_import_export_tools_not_exposed(self, db):
        """Verify legacy import/export tool names are not in the tool list."""
        from mcp_server.tools import import_export

        tools = await import_export.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list (consolidated)
        assert "import_bibtex" not in tool_names
        assert "import_from_external" not in tool_names
        assert "import_paper_wizard" not in tool_names
        assert "export_papers" not in tool_names
        assert "export_collection" not in tool_names


class TestDiscoveryTools:
    """Tests for consolidated discovery tools."""

    @pytest.mark.asyncio
    async def test_discovery_lists_consolidated_tools(self, db):
        """Verify discovery module lists 4 tools (was 8)."""
        from mcp_server.tools import discovery

        tools = await discovery.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 4
        assert "semantic_find" in tool_names
        assert "manage_embeddings" in tool_names
        assert "get_reading_queue" in tool_names
        assert "suggest_paper_tags" in tool_names

    @pytest.mark.asyncio
    async def test_semantic_find_input_type_parameter(self, db):
        """Test semantic_find with input_type parameter."""
        from mcp_server.tools import discovery

        tools = await discovery.list_tools()
        find_tool = next(t for t in tools if t.name == "semantic_find")

        schema = find_tool.inputSchema
        assert "input_type" in schema["properties"]
        assert set(schema["properties"]["input_type"]["enum"]) == {"paper", "text", "citation"}
        assert "input_type" in schema.get("required", [])

    @pytest.mark.asyncio
    async def test_manage_embeddings_action_parameter(self, db):
        """Test manage_embeddings with action parameter."""
        from mcp_server.tools import discovery

        tools = await discovery.list_tools()
        embed_tool = next(t for t in tools if t.name == "manage_embeddings")

        schema = embed_tool.inputSchema
        assert "action" in schema["properties"]
        assert set(schema["properties"]["action"]["enum"]) == {"status", "process", "embed"}

    @pytest.mark.asyncio
    async def test_legacy_discovery_tools_not_exposed(self, db):
        """Verify legacy discovery tool names are not in the tool list."""
        from mcp_server.tools import discovery

        tools = await discovery.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list (consolidated)
        assert "find_similar_papers" not in tool_names
        assert "find_papers_like_text" not in tool_names
        assert "suggest_citations_for_text" not in tool_names
        assert "get_embedding_status" not in tool_names
        assert "process_embedding_queue" not in tool_names
        assert "embed_paper" not in tool_names


class TestZoteroTools:
    """Tests for consolidated Zotero tools."""

    @pytest.mark.asyncio
    async def test_zotero_lists_consolidated_tools(self, db):
        """Verify zotero module lists 2 tools (was 6)."""
        from mcp_server.tools import zotero

        tools = await zotero.list_tools()
        tool_names = [t.name for t in tools]

        assert len(tools) == 2
        assert "zotero_sync" in tool_names
        assert "zotero_status" in tool_names

    @pytest.mark.asyncio
    async def test_zotero_sync_direction_parameter(self, db):
        """Test zotero_sync with direction parameter."""
        from mcp_server.tools import zotero

        tools = await zotero.list_tools()
        sync_tool = next(t for t in tools if t.name == "zotero_sync")

        schema = sync_tool.inputSchema
        assert "direction" in schema["properties"]
        assert set(schema["properties"]["direction"]["enum"]) == {"pull", "push", "push_paper", "push_pdf"}
        assert "direction" in schema.get("required", [])

    @pytest.mark.asyncio
    async def test_zotero_status_check_connection_parameter(self, db):
        """Test zotero_status with check_connection parameter."""
        from mcp_server.tools import zotero

        tools = await zotero.list_tools()
        status_tool = next(t for t in tools if t.name == "zotero_status")

        schema = status_tool.inputSchema
        assert "check_connection" in schema["properties"]
        assert schema["properties"]["check_connection"]["type"] == "boolean"

    @pytest.mark.asyncio
    async def test_legacy_zotero_tools_not_exposed(self, db):
        """Verify legacy zotero tool names are not in the tool list."""
        from mcp_server.tools import zotero

        tools = await zotero.list_tools()
        tool_names = [t.name for t in tools]

        # These should NOT be in the list (consolidated)
        assert "sync_from_zotero" not in tool_names
        assert "sync_to_zotero" not in tool_names
        assert "push_paper_to_zotero" not in tool_names
        assert "push_pdf_to_zotero" not in tool_names
        assert "get_zotero_sync_status" not in tool_names
        assert "check_zotero_connection" not in tool_names


class TestTotalToolCount:
    """Tests for overall tool count."""

    @pytest.mark.asyncio
    async def test_total_tool_count(self, db):
        """Verify total tool count after Phase 5 consolidation."""
        from mcp_server.tools import (
            papers, search, extraction, discovery, citation_network,
            citations, collections, notes, pdf, browser_pdf,
            import_export, project, validation, zotero
        )

        modules = [
            papers, search, extraction, discovery, citation_network,
            citations, collections, notes, pdf, browser_pdf,
            import_export, project, validation, zotero
        ]

        total = 0
        for mod in modules:
            tools = await mod.list_tools()
            total += len(tools)

        # Phase 5 consolidation target: 71 → ~63 (after import/export, discovery, citation consolidations)
        # Remaining: zotero (6 → 2) will bring to ~59
        assert total <= 70, f"Total tools ({total}) exceeds target of 70"
        assert total >= 55, f"Total tools ({total}) unexpectedly low"
