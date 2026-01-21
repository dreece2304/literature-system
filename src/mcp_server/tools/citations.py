"""
Citation Tools for MCP Server.

These tools provide citation management capabilities including
manuscript scanning, citation checking, and BibTeX generation.

Tools in this module work with paper data passed directly as arguments,
not with database queries. For database-backed citation operations,
see the project.py module.
"""

import re
import sys
from typing import Any
from pathlib import Path

from mcp.types import Tool, TextContent
from loguru import logger

# Add src directory to path for imports
_litai_src = Path(__file__).parent.parent.parent
if str(_litai_src) not in sys.path:
    sys.path.insert(0, str(_litai_src))

from literature_core import serialize
from context.parser import ManuscriptParser


async def list_tools() -> list[Tool]:
    """List citation management tools."""
    return [
        Tool(
            name="scan_manuscript",
            description="Scan LaTeX/Markdown for citations, sections, structure",
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
            description="Check manuscript citations vs library (orphans, unused)",
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
            description="Generate BibTeX key (format: firstauthorYEARfirstword)",
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


# ============================================================================
# Helper Functions
# ============================================================================


def _generate_citation_key(title: str, authors: str, year: int | None = None) -> str:
    """Generate a BibTeX citation key from paper metadata.

    Format: firstauthorYEARfirstword
    Example: smith2023machine

    Args:
        title: Paper title
        authors: Author names (comma or 'and' separated)
        year: Publication year

    Returns:
        Citation key string
    """
    # Extract first author's last name
    first_author = "unknown"
    if authors:
        # Handle "Smith, John" or "John Smith" or "Smith, J. and Doe, J."
        authors_clean = authors.replace(" and ", ", ").replace(";", ",")
        first_author_part = authors_clean.split(",")[0].strip()
        # If "Smith, John" format, use Smith
        # If "John Smith" format, use last word
        words = first_author_part.split()
        if len(words) > 0:
            first_author = words[-1] if len(words) > 1 else words[0]
        first_author = re.sub(r'[^a-zA-Z]', '', first_author).lower()

    # Extract first meaningful word from title
    title_word = ""
    if title:
        # Skip common articles
        skip_words = {"a", "an", "the", "on", "of", "for", "in", "to"}
        for word in title.split():
            clean = re.sub(r'[^a-zA-Z]', '', word).lower()
            if clean and clean not in skip_words:
                title_word = clean
                break

    year_str = str(year) if year else ""

    return f"{first_author}{year_str}{title_word}"


def _to_bibtex(
    paper: dict[str, Any],
    entry_type: str = "article",
    key: str | None = None
) -> str:
    """Generate BibTeX entry for a paper.

    Args:
        paper: Paper dict with title, authors, year, etc.
        entry_type: BibTeX entry type (article, inproceedings, etc.)
        key: Citation key (generated if not provided)

    Returns:
        BibTeX entry string
    """
    # Normalize authors format
    authors = paper.get("authors", "Unknown")
    if isinstance(authors, list):
        authors = " and ".join(authors)

    # Generate key if not provided
    if not key:
        key = _generate_citation_key(
            paper.get("title", ""),
            authors,
            paper.get("year"),
        )

    fields = []
    if paper.get("title"):
        fields.append(f'  title = {{{paper["title"]}}}')
    if authors:
        fields.append(f'  author = {{{authors}}}')
    if paper.get("year"):
        fields.append(f'  year = {{{paper["year"]}}}')
    if paper.get("journal"):
        fields.append(f'  journal = {{{paper["journal"]}}}')
    if paper.get("venue"):
        fields.append(f'  booktitle = {{{paper["venue"]}}}')
    if paper.get("volume"):
        fields.append(f'  volume = {{{paper["volume"]}}}')
    if paper.get("number"):
        fields.append(f'  number = {{{paper["number"]}}}')
    if paper.get("pages"):
        fields.append(f'  pages = {{{paper["pages"]}}}')
    if paper.get("doi"):
        fields.append(f'  doi = {{{paper["doi"]}}}')
    if paper.get("url"):
        fields.append(f'  url = {{{paper["url"]}}}')

    return f"@{entry_type}{{{key},\n" + ",\n".join(fields) + "\n}"


def _format_apa(paper: dict[str, Any]) -> str:
    """Format paper in APA style."""
    authors = paper.get("authors", "Unknown")
    if isinstance(authors, list):
        authors = ", ".join(authors)
    year = paper.get("year", "n.d.")
    title = paper.get("title", "Untitled")
    journal = paper.get("journal", "")

    citation = f"{authors} ({year}). {title}."
    if journal:
        citation += f" {journal}."
    if paper.get("doi"):
        citation += f" https://doi.org/{paper['doi']}"

    return citation


def _format_mla(paper: dict[str, Any]) -> str:
    """Format paper in MLA style."""
    authors = paper.get("authors", "Unknown")
    if isinstance(authors, list):
        authors = ", ".join(authors)
    title = paper.get("title", "Untitled")
    journal = paper.get("journal", "")
    year = paper.get("year", "")

    citation = f'{authors}. "{title}."'
    if journal:
        citation += f" {journal},"
    if year:
        citation += f" {year}."

    return citation


def _format_chicago(paper: dict[str, Any]) -> str:
    """Format paper in Chicago style."""
    authors = paper.get("authors", "Unknown")
    if isinstance(authors, list):
        authors = ", ".join(authors)
    title = paper.get("title", "Untitled")
    journal = paper.get("journal", "")
    year = paper.get("year", "")

    citation = f'{authors}. "{title}."'
    if journal:
        citation += f" {journal}"
    if year:
        citation += f" ({year})."

    return citation


def _validate_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Validate a paper's citation data.

    Returns:
        Dict with valid (bool), errors (list), warnings (list)
    """
    errors = []
    warnings = []

    # Required fields
    if not paper.get("title"):
        errors.append("Missing title")
    if not paper.get("authors"):
        errors.append("Missing authors")

    # Recommended fields
    if not paper.get("year"):
        warnings.append("Missing year")
    if not paper.get("doi") and not paper.get("url"):
        warnings.append("No DOI or URL")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ============================================================================
# Tool Implementation
# ============================================================================


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a citation tool."""
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
            return [TextContent(type="text", text=serialize(result))]

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

                key = _generate_citation_key(
                    paper.get("title", ""),
                    authors,
                    paper.get("year"),
                )
                library_keys[key] = paper

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
            return [TextContent(type="text", text=serialize(result))]

        elif name == "suggest_citation_key":
            authors = arguments.get("authors", "Unknown")
            title = arguments.get("title", "")
            year = arguments.get("year")

            key = _generate_citation_key(title, authors, year)

            result = {
                "suggested_key": key,
                "format": "firstauthorYEARfirstword",
                "example_usage": f"\\cite{{{key}}}",
            }
            return [TextContent(type="text", text=serialize(result))]

        elif name == "generate_bibtex":
            papers = arguments["papers"]
            entry_type = arguments.get("entry_type", "article")

            bibtex_entries = []
            for paper in papers:
                bibtex_entries.append(_to_bibtex(paper, entry_type))

            return [TextContent(
                type="text",
                text="\n\n".join(bibtex_entries),
            )]

        elif name == "format_bibliography":
            papers = arguments["papers"]
            style = arguments.get("style", "apa")
            sort = arguments.get("sort", True)

            # Sort by author if requested
            if sort:
                papers = sorted(
                    papers,
                    key=lambda p: str(p.get("authors", "")).lower()
                )

            # Format each paper
            formatted = []
            for paper in papers:
                if style == "apa":
                    formatted.append(_format_apa(paper))
                elif style == "mla":
                    formatted.append(_format_mla(paper))
                elif style == "chicago":
                    formatted.append(_format_chicago(paper))
                elif style == "bibtex":
                    formatted.append(_to_bibtex(paper))
                else:
                    formatted.append(_format_apa(paper))  # Default to APA

            return [TextContent(type="text", text="\n\n".join(formatted))]

        elif name == "validate_citations":
            papers = arguments["papers"]

            results = []
            for paper in papers:
                validation = _validate_paper(paper)
                results.append({
                    "title": str(paper.get("title", "Unknown"))[:50],
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
            return [TextContent(type="text", text=serialize(summary))]

        else:
            return [TextContent(type="text", text=f"Unknown citation tool: {name}")]

    except Exception as e:
        logger.error(f"Citation tool error: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]
