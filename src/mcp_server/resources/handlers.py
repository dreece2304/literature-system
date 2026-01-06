"""
Resource handlers for MCP Server.

Resources enable @ mention syntax in Claude Code for quick access
to literature data like recent papers, unread papers, and projects.

REFACTORED: Uses services directly instead of HTTP API calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.types import Resource
from loguru import logger

# Add src directory to path for imports
# handlers.py is at src/mcp_server/resources/handlers.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from services import PaperService, SearchService


async def list_resources() -> list[Resource]:
    """
    List available resources for @ mentions.

    These resources provide quick access to paper collections
    via @literature://resource-name syntax in Claude Code.
    """
    return [
        Resource(
            uri="literature://recent",
            name="Recent Papers",
            description="Recently added papers (last 20)",
            mimeType="application/json",
        ),
        Resource(
            uri="literature://unread",
            name="Unread Papers",
            description="Papers marked as unread",
            mimeType="application/json",
        ),
        Resource(
            uri="literature://reading",
            name="Currently Reading",
            description="Papers currently being read",
            mimeType="application/json",
        ),
        Resource(
            uri="literature://favorites",
            name="Favorite Papers",
            description="Papers with rating 4 or higher",
            mimeType="application/json",
        ),
        Resource(
            uri="literature://extraction-queue",
            name="Extraction Queue",
            description="Papers needing AI extraction (missing summaries)",
            mimeType="application/json",
        ),
        Resource(
            uri="literature://stats",
            name="Library Statistics",
            description="Overview statistics of your literature library",
            mimeType="application/json",
        ),
    ]


async def read_resource(uri: str) -> str:
    """
    Read resource content by URI.

    Args:
        uri: Resource URI (e.g., literature://recent)

    Returns:
        JSON string with resource content
    """
    parsed = urlparse(uri)

    if parsed.scheme != "literature":
        return json.dumps({"error": f"Unknown scheme: {parsed.scheme}"})

    resource_name = parsed.netloc or parsed.path.lstrip("/")

    try:
        if resource_name == "recent":
            return _get_recent_papers()

        elif resource_name == "unread":
            return _get_papers_by_status("unread")

        elif resource_name == "reading":
            return _get_papers_by_status("reading")

        elif resource_name == "favorites":
            return _get_favorite_papers()

        elif resource_name == "extraction-queue":
            return _get_extraction_queue()

        elif resource_name == "stats":
            return _get_library_stats()

        elif resource_name.startswith("paper/"):
            paper_id = resource_name.split("/")[1]
            return _get_paper_detail(int(paper_id))

        elif resource_name.startswith("tag/"):
            tag_name = resource_name.split("/")[1]
            return _get_papers_by_tag(tag_name)

        elif resource_name.startswith("author/"):
            author_name = resource_name.split("/")[1]
            return _get_papers_by_author(author_name)

        else:
            return json.dumps({"error": f"Unknown resource: {resource_name}"})

    except Exception as e:
        logger.error(f"Error reading resource {uri}: {e}")
        return json.dumps({"error": str(e)})


def _get_recent_papers() -> str:
    """Get recently added papers."""
    result = PaperService.list(limit=20)

    papers_data = {
        "title": "Recent Papers",
        "description": "Recently added papers",
        "count": len(result.papers),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
                "read_status": p.get("read_status"),
            }
            for p in result.papers
        ],
    }
    return json.dumps(papers_data, indent=2)


def _get_papers_by_status(status: str) -> str:
    """Get papers by read status."""
    result = PaperService.list(read_status=status, limit=50)

    status_labels = {
        "unread": "Unread Papers",
        "reading": "Currently Reading",
        "read": "Read Papers",
    }

    papers_data = {
        "title": status_labels.get(status, f"Papers ({status})"),
        "count": len(result.papers),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
                "rating": p.get("rating"),
            }
            for p in result.papers
        ],
    }
    return json.dumps(papers_data, indent=2)


def _get_favorite_papers() -> str:
    """Get highly rated papers."""
    # Get papers and filter by rating >= 4
    result = PaperService.list(limit=100)
    favorites = [p for p in result.papers if (p.get("rating") or 0) >= 4]

    papers_data = {
        "title": "Favorite Papers",
        "description": "Papers rated 4 stars or higher",
        "count": len(favorites),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
                "rating": p.get("rating"),
            }
            for p in favorites
        ],
    }
    return json.dumps(papers_data, indent=2)


def _get_extraction_queue() -> str:
    """Get papers needing AI extraction."""
    result = PaperService.get_extraction_queue(limit=30)

    papers_data = {
        "title": "Extraction Queue",
        "description": "Papers needing AI summarization and analysis",
        "count": len(result.papers),
        "papers": [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "has_abstract": p.get("has_abstract", False),
                "has_full_text": p.get("has_full_text", False),
                "priority": p.get("priority", "low"),
            }
            for p in result.papers
        ],
    }
    return json.dumps(papers_data, indent=2)


def _get_library_stats() -> str:
    """Get library statistics overview."""
    # Get all papers (up to 1000) for stats calculation
    result = PaperService.list(limit=1000)
    papers = result.papers

    # Calculate statistics
    total = len(papers)
    by_status = {"unread": 0, "reading": 0, "read": 0}
    by_year: dict[int, int] = {}
    with_abstract = 0
    with_doi = 0
    rated_papers = 0
    total_rating = 0

    for p in papers:
        status = p.get("read_status", "unread")
        if status in by_status:
            by_status[status] += 1

        year = p.get("year")
        if year:
            by_year[year] = by_year.get(year, 0) + 1

        if p.get("abstract"):
            with_abstract += 1

        if p.get("doi"):
            with_doi += 1

        if p.get("rating"):
            rated_papers += 1
            total_rating += p["rating"]

    # Sort years
    sorted_years = sorted(by_year.items(), key=lambda x: x[0], reverse=True)

    stats = {
        "title": "Library Statistics",
        "total_papers": result.total,  # Use actual total from service
        "by_read_status": by_status,
        "completeness": {
            "with_abstract": with_abstract,
            "with_doi": with_doi,
            "abstract_percentage": round(with_abstract / total * 100, 1) if total else 0,
            "doi_percentage": round(with_doi / total * 100, 1) if total else 0,
        },
        "ratings": {
            "rated_papers": rated_papers,
            "average_rating": (
                round(total_rating / rated_papers, 2) if rated_papers else None
            ),
        },
        "papers_by_year": dict(sorted_years[:10]),
    }
    return json.dumps(stats, indent=2)


def _get_paper_detail(paper_id: int) -> str:
    """Get detailed paper information."""
    paper = PaperService.get(paper_id)

    if not paper:
        return json.dumps({"error": f"Paper {paper_id} not found"})

    paper_data = {
        "id": paper["id"],
        "title": paper["title"],
        "authors": _format_authors(paper.get("authors", [])),
        "year": paper.get("year"),
        "abstract": paper.get("abstract"),
        "doi": paper.get("doi"),
        "arxiv_id": paper.get("arxiv_id"),
        "read_status": paper.get("read_status"),
        "rating": paper.get("rating"),
        "tags": paper.get("tags", []),
    }
    return json.dumps(paper_data, indent=2)


def _get_papers_by_tag(tag_name: str) -> str:
    """Get papers with a specific tag."""
    result = SearchService.search_by_tag(tag_name, limit=50)

    papers_data = {
        "title": f"Papers tagged: {tag_name}",
        "count": len(result.results),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
            }
            for p in result.results
        ],
    }
    return json.dumps(papers_data, indent=2)


def _get_papers_by_author(author_name: str) -> str:
    """Get papers by a specific author."""
    result = SearchService.search_by_author(author_name, limit=50)

    papers_data = {
        "title": f"Papers by: {author_name}",
        "count": len(result.results),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
            }
            for p in result.results
        ],
    }
    return json.dumps(papers_data, indent=2)


def _format_authors(authors: list[Any]) -> str:
    """Format author list to string."""
    if not authors:
        return "Unknown"

    author_names = []
    for a in authors:
        if isinstance(a, dict):
            author_names.append(a.get("name", str(a)))
        else:
            author_names.append(str(a))

    return ", ".join(author_names)
