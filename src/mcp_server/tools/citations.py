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
        # Consolidated manuscript tool
        Tool(
            name="manuscript_tools",
            description="Manuscript analysis. Actions: scan (parse structure), check (citations vs library)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["scan", "check"],
                        "description": "Action: scan (parse manuscript), check (compare citations to library)",
                        "default": "scan",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "For scan: path to .tex/.md file",
                    },
                    "content": {
                        "type": "string",
                        "description": "For scan: manuscript content (if no file_path)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["latex", "markdown"],
                        "description": "For scan: document format",
                        "default": "latex",
                    },
                    "manuscript_citations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For check: citation keys from manuscript",
                    },
                    "library_papers": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "For check: papers from library",
                    },
                },
            },
        ),
        # Consolidated citation formatting tool
        Tool(
            name="format_citation",
            description="Citation formatting. Actions: bibtex, suggest_key, validate, bibliography",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["bibtex", "suggest_key", "validate", "bibliography"],
                        "description": "Action: bibtex (generate entries), suggest_key (generate key), validate (check data), bibliography (format list)",
                        "default": "bibtex",
                    },
                    "papers": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "For bibtex/validate/bibliography: papers to process",
                    },
                    "title": {
                        "type": "string",
                        "description": "For suggest_key: paper title",
                    },
                    "authors": {
                        "type": "string",
                        "description": "For suggest_key: author names",
                    },
                    "year": {
                        "type": "integer",
                        "description": "For suggest_key: publication year",
                    },
                    "entry_type": {
                        "type": "string",
                        "enum": ["article", "inproceedings", "book", "misc"],
                        "description": "For bibtex: entry type",
                        "default": "article",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["apa", "mla", "chicago", "bibtex"],
                        "description": "For bibliography: citation style",
                        "default": "apa",
                    },
                    "sort": {
                        "type": "boolean",
                        "description": "For bibliography: sort by author",
                        "default": True,
                    },
                },
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


def _do_scan_manuscript(arguments: dict[str, Any], parser: ManuscriptParser) -> list[TextContent]:
    """Scan manuscript for structure and citations."""
    if arguments.get("file_path"):
        file_path = Path(arguments["file_path"])
        if not file_path.exists():
            return [TextContent(type="text", text=f"File not found: {file_path}")]
        structure = parser.parse_file(file_path)
    elif arguments.get("content"):
        content = arguments["content"]
        fmt = arguments.get("format", "latex")
        if fmt == "latex":
            structure = parser.parse_latex(content)
        else:
            structure = parser.parse_markdown(content)
    else:
        return [TextContent(type="text", text="Please provide either file_path or content.")]

    if not structure:
        return [TextContent(type="text", text="Failed to parse manuscript.")]

    result = {
        "title": structure.title,
        "abstract_preview": (
            structure.abstract[:300] + "..." if len(structure.abstract) > 300 else structure.abstract
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


def _do_check_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Check manuscript citations vs library."""
    manuscript_citations = set(arguments["manuscript_citations"])
    library_papers = arguments.get("library_papers", [])

    library_keys = {}
    for paper in library_papers:
        authors = paper.get("authors", "Unknown")
        if isinstance(authors, list):
            authors = ", ".join(authors)
        key = _generate_citation_key(paper.get("title", ""), authors, paper.get("year"))
        library_keys[key] = paper

    library_key_set = set(library_keys.keys())
    orphan_citations = manuscript_citations - library_key_set
    unused_papers = library_key_set - manuscript_citations
    matched = manuscript_citations & library_key_set

    result = {
        "total_manuscript_citations": len(manuscript_citations),
        "total_library_papers": len(library_papers),
        "matched_citations": len(matched),
        "orphan_citations": {
            "count": len(orphan_citations),
            "keys": list(orphan_citations),
            "message": "Citations in manuscript but not in library" if orphan_citations else "All citations found",
        },
        "unused_papers": {
            "count": len(unused_papers),
            "keys": list(unused_papers)[:20],
            "message": "Papers in library but not cited" if unused_papers else "All papers cited",
        },
    }
    return [TextContent(type="text", text=serialize(result))]


def _do_suggest_key(arguments: dict[str, Any]) -> list[TextContent]:
    """Suggest a citation key."""
    key = _generate_citation_key(
        arguments.get("title", ""),
        arguments.get("authors", "Unknown"),
        arguments.get("year"),
    )
    result = {
        "suggested_key": key,
        "format": "firstauthorYEARfirstword",
        "example_usage": f"\\cite{{{key}}}",
    }
    return [TextContent(type="text", text=serialize(result))]


def _do_generate_bibtex(arguments: dict[str, Any]) -> list[TextContent]:
    """Generate BibTeX entries."""
    papers = arguments["papers"]
    entry_type = arguments.get("entry_type", "article")
    bibtex_entries = [_to_bibtex(paper, entry_type) for paper in papers]
    return [TextContent(type="text", text="\n\n".join(bibtex_entries))]


def _do_format_bibliography(arguments: dict[str, Any]) -> list[TextContent]:
    """Format bibliography in various styles."""
    papers = arguments["papers"]
    style = arguments.get("style", "apa")
    sort = arguments.get("sort", True)

    if sort:
        papers = sorted(papers, key=lambda p: str(p.get("authors", "")).lower())

    formatters = {"apa": _format_apa, "mla": _format_mla, "chicago": _format_chicago, "bibtex": _to_bibtex}
    formatter = formatters.get(style, _format_apa)
    formatted = [formatter(paper) for paper in papers]
    return [TextContent(type="text", text="\n\n".join(formatted))]


def _do_validate_citations(arguments: dict[str, Any]) -> list[TextContent]:
    """Validate citation data."""
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
        "papers_with_warnings": sum(1 for r in results if r["warnings"]),
        "details": results,
    }
    return [TextContent(type="text", text=serialize(summary))]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a citation tool."""
    parser = ManuscriptParser()

    try:
        # Consolidated manuscript_tools
        if name == "manuscript_tools":
            action = arguments.get("action", "scan")
            if action == "scan":
                return _do_scan_manuscript(arguments, parser)
            elif action == "check":
                return _do_check_citations(arguments)
            else:
                return [TextContent(type="text", text=serialize({"error": f"Unknown action: {action}"}))]

        # Consolidated format_citation
        if name == "format_citation":
            action = arguments.get("action", "bibtex")
            if action == "bibtex":
                return _do_generate_bibtex(arguments)
            elif action == "suggest_key":
                return _do_suggest_key(arguments)
            elif action == "validate":
                return _do_validate_citations(arguments)
            elif action == "bibliography":
                return _do_format_bibliography(arguments)
            else:
                return [TextContent(type="text", text=serialize({"error": f"Unknown action: {action}"}))]

        return [TextContent(type="text", text=f"Unknown citation tool: {name}")]

    except Exception as e:
        logger.error(f"Citation tool error: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]
