"""
Citation Tools for MCP Server.

These tools provide citation management capabilities including
manuscript scanning, citation checking, and BibTeX generation.
"""

import json
from typing import Any
from pathlib import Path

from mcp.types import Tool, TextContent
from loguru import logger

from src.services.citation_service import CitationService, Citation
from src.context.parser import ManuscriptParser


async def list_tools() -> list[Tool]:
    """List citation management tools."""
    return [
        Tool(
            name="scan_manuscript",
            description=(
                "Scan a LaTeX or Markdown manuscript to extract citations, "
                "sections, and document structure. Returns all \\cite{} keys found."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the manuscript file (.tex, .md)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Manuscript content (if file_path not provided)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["latex", "markdown"],
                        "description": "Document format (required if using content)",
                        "default": "latex",
                    },
                },
            },
        ),
        Tool(
            name="check_citations",
            description=(
                "Check citations in a manuscript against papers in the library. "
                "Reports orphan citations (not in library) and unused papers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "manuscript_citations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of citation keys from manuscript",
                    },
                    "library_papers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "title": {"type": "string"},
                                "authors": {"type": "string"},
                                "year": {"type": "integer"},
                            },
                        },
                        "description": "Papers from the literature library",
                    },
                },
                "required": ["manuscript_citations"],
            },
        ),
        Tool(
            name="suggest_citation_key",
            description=(
                "Generate a BibTeX citation key for a paper. "
                "Uses format: firstauthorYEARfirstword"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Paper title",
                    },
                    "authors": {
                        "type": "string",
                        "description": "Author names (comma or 'and' separated)",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Publication year",
                    },
                },
                "required": ["title", "authors"],
            },
        ),
        Tool(
            name="generate_bibtex",
            description="Generate BibTeX entries for papers",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "authors": {"type": "string"},
                                "year": {"type": "integer"},
                                "doi": {"type": "string"},
                                "journal": {"type": "string"},
                                "volume": {"type": "string"},
                                "pages": {"type": "string"},
                            },
                            "required": ["title", "authors"],
                        },
                        "description": "Papers to generate BibTeX for",
                    },
                    "entry_type": {
                        "type": "string",
                        "enum": ["article", "inproceedings", "book", "misc"],
                        "description": "BibTeX entry type",
                        "default": "article",
                    },
                },
                "required": ["papers"],
            },
        ),
        Tool(
            name="format_bibliography",
            description="Generate formatted bibliography in various styles",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                        },
                        "description": "Papers to include in bibliography",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["apa", "mla", "chicago", "bibtex"],
                        "description": "Citation style",
                        "default": "apa",
                    },
                    "sort": {
                        "type": "boolean",
                        "description": "Sort alphabetically by author",
                        "default": True,
                    },
                },
                "required": ["papers"],
            },
        ),
        Tool(
            name="validate_citations",
            description="Validate citation data for completeness",
            inputSchema={
                "type": "object",
                "properties": {
                    "papers": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Papers to validate",
                    },
                },
                "required": ["papers"],
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a citation tool."""
    citation_service = CitationService()
    parser = ManuscriptParser()

    try:
        if name == "scan_manuscript":
            # Parse manuscript from file or content
            if arguments.get("file_path"):
                file_path = Path(arguments["file_path"])
                if not file_path.exists():
                    return [TextContent(
                        type="text",
                        text=f"File not found: {file_path}",
                    )]
                structure = parser.parse_file(file_path)
            elif arguments.get("content"):
                content = arguments["content"]
                fmt = arguments.get("format", "latex")
                if fmt == "latex":
                    structure = parser.parse_latex(content)
                else:
                    structure = parser.parse_markdown(content)
            else:
                return [TextContent(
                    type="text",
                    text="Please provide either file_path or content.",
                )]

            if not structure:
                return [TextContent(
                    type="text",
                    text="Failed to parse manuscript.",
                )]

            result = {
                "title": structure.title,
                "abstract_preview": (
                    structure.abstract[:300] + "..."
                    if len(structure.abstract) > 300
                    else structure.abstract
                ),
                "document_type": structure.document_type,
                "total_words": structure.total_words,
                "sections": [
                    {
                        "level": s.level,
                        "title": s.title,
                        "word_count": s.word_count,
                        "citations": s.citations,
                        "line_range": f"{s.start_line}-{s.end_line}",
                    }
                    for s in structure.sections
                ],
                "all_citations": structure.all_citations,
                "citation_count": len(structure.all_citations),
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "check_citations":
            manuscript_citations = set(arguments["manuscript_citations"])
            library_papers = arguments.get("library_papers", [])

            # Generate citation keys for library papers
            library_keys = {}
            for paper in library_papers:
                # Handle authors format
                authors = paper.get("authors", "Unknown")
                if isinstance(authors, list):
                    authors = ", ".join(authors)

                citation = citation_service.create_citation({
                    "id": paper.get("id"),
                    "title": paper.get("title", ""),
                    "authors": authors,
                    "year": paper.get("year"),
                })
                library_keys[citation.cite_key] = paper

            library_key_set = set(library_keys.keys())

            # Find orphan citations (in manuscript but not in library)
            orphan_citations = manuscript_citations - library_key_set

            # Find unused papers (in library but not cited)
            unused_papers = library_key_set - manuscript_citations

            # Find matched citations
            matched = manuscript_citations & library_key_set

            result = {
                "total_manuscript_citations": len(manuscript_citations),
                "total_library_papers": len(library_papers),
                "matched_citations": len(matched),
                "orphan_citations": {
                    "count": len(orphan_citations),
                    "keys": list(orphan_citations),
                    "message": (
                        "These citations are in your manuscript but not in your library"
                        if orphan_citations else "All citations found in library"
                    ),
                },
                "unused_papers": {
                    "count": len(unused_papers),
                    "keys": list(unused_papers)[:20],  # Limit output
                    "message": (
                        "These papers are in your library but not cited"
                        if unused_papers else "All library papers are cited"
                    ),
                },
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "suggest_citation_key":
            # Handle authors format
            authors = arguments.get("authors", "Unknown")
            if isinstance(authors, list):
                authors = ", ".join(authors)

            citation = Citation(
                paper_id="temp",
                title=arguments.get("title", ""),
                authors=authors,
                year=arguments.get("year"),
            )

            result = {
                "suggested_key": citation.cite_key,
                "format": "firstauthorYEARfirstword",
                "example_usage": f"\\cite{{{citation.cite_key}}}",
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "generate_bibtex":
            papers = arguments["papers"]
            entry_type = arguments.get("entry_type", "article")

            bibtex_entries = []
            for paper in papers:
                # Handle authors format
                authors = paper.get("authors", "Unknown")
                if isinstance(authors, list):
                    authors = " and ".join(authors)

                citation = Citation(
                    paper_id=str(paper.get("id", "temp")),
                    title=paper.get("title", ""),
                    authors=authors,
                    year=paper.get("year"),
                    venue=paper.get("journal") or paper.get("venue"),
                    doi=paper.get("doi"),
                    url=paper.get("url"),
                    volume=paper.get("volume"),
                    number=paper.get("number"),
                    pages=paper.get("pages"),
                )
                bibtex_entries.append(citation.to_bibtex(entry_type))

            return [TextContent(
                type="text",
                text="\n\n".join(bibtex_entries),
            )]

        elif name == "format_bibliography":
            papers = arguments["papers"]
            style = arguments.get("style", "apa")
            sort = arguments.get("sort", True)

            # Normalize paper data
            normalized_papers = []
            for paper in papers:
                authors = paper.get("authors", "Unknown")
                if isinstance(authors, list):
                    authors = ", ".join(authors)
                normalized_papers.append({
                    **paper,
                    "authors": authors,
                })

            bibliography = citation_service.generate_bibliography(
                normalized_papers,
                style=style,
                sort=sort,
            )

            return [TextContent(type="text", text=bibliography)]

        elif name == "validate_citations":
            papers = arguments["papers"]

            results = []
            for paper in papers:
                validation = citation_service.validate_citation(paper)
                results.append({
                    "title": paper.get("title", "Unknown")[:50],
                    "valid": validation["valid"],
                    "errors": validation["errors"],
                    "warnings": validation["warnings"],
                })

            summary = {
                "total_papers": len(papers),
                "valid_papers": sum(1 for r in results if r["valid"]),
                "papers_with_warnings": sum(
                    1 for r in results if r["warnings"]
                ),
                "details": results,
            }
            return [TextContent(type="text", text=json.dumps(summary, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown citation tool: {name}")]

    except Exception as e:
        logger.error(f"Citation tool error: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]
