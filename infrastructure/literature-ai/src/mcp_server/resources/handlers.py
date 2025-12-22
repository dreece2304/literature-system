"""
Resource handlers for MCP Server.

Resources enable @ mention syntax in Claude Code for quick access
to literature data like recent papers, unread papers, and projects.
"""

import json
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.types import Resource
from loguru import logger

from config.settings import settings


def get_api_url() -> str:
    """Get the literature-database API URL."""
    base = settings.litdb.api_url.rstrip('/')
    if not base.endswith('/api/v1'):
        base = f"{base}/api/v1"
    return base


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
            description="Recently added papers (last 7 days)",
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
    api_url = get_api_url()
    parsed = urlparse(uri)

    if parsed.scheme != "literature":
        return json.dumps({"error": f"Unknown scheme: {parsed.scheme}"})

    resource_name = parsed.netloc or parsed.path.lstrip("/")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if resource_name == "recent":
                return await _get_recent_papers(client, api_url)

            elif resource_name == "unread":
                return await _get_papers_by_status(client, api_url, "unread")

            elif resource_name == "reading":
                return await _get_papers_by_status(client, api_url, "reading")

            elif resource_name == "favorites":
                return await _get_favorite_papers(client, api_url)

            elif resource_name == "extraction-queue":
                return await _get_extraction_queue(client, api_url)

            elif resource_name == "stats":
                return await _get_library_stats(client, api_url)

            elif resource_name.startswith("paper/"):
                paper_id = resource_name.split("/")[1]
                return await _get_paper_detail(client, api_url, paper_id)

            elif resource_name.startswith("tag/"):
                tag_name = resource_name.split("/")[1]
                return await _get_papers_by_tag(client, api_url, tag_name)

            elif resource_name.startswith("author/"):
                author_name = resource_name.split("/")[1]
                return await _get_papers_by_author(client, api_url, author_name)

            else:
                return json.dumps({"error": f"Unknown resource: {resource_name}"})

        except httpx.HTTPStatusError as e:
            logger.error(f"API error reading resource: {e}")
            return json.dumps({
                "error": f"API Error: {e.response.status_code}",
                "detail": e.response.text[:200],
            })
        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            return json.dumps({"error": str(e)})


async def _get_recent_papers(
    client: httpx.AsyncClient, api_url: str
) -> str:
    """Get recently added papers."""
    response = await client.get(
        f"{api_url}/papers",
        params={"limit": 20, "sort": "-created_at"},
    )
    response.raise_for_status()
    data = response.json()

    papers = data.get("items", data) if isinstance(data, dict) else data

    result = {
        "title": "Recent Papers",
        "description": "Papers added in the last 7 days",
        "count": len(papers),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
                "read_status": p.get("read_status"),
            }
            for p in papers
        ],
    }
    return json.dumps(result, indent=2)


async def _get_papers_by_status(
    client: httpx.AsyncClient, api_url: str, status: str
) -> str:
    """Get papers by read status."""
    response = await client.get(
        f"{api_url}/papers",
        params={"read_status": status, "limit": 50},
    )
    response.raise_for_status()
    data = response.json()

    papers = data.get("items", data) if isinstance(data, dict) else data

    status_labels = {
        "unread": "Unread Papers",
        "reading": "Currently Reading",
        "read": "Read Papers",
    }

    result = {
        "title": status_labels.get(status, f"Papers ({status})"),
        "count": len(papers),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
                "rating": p.get("rating"),
            }
            for p in papers
        ],
    }
    return json.dumps(result, indent=2)


async def _get_favorite_papers(
    client: httpx.AsyncClient, api_url: str
) -> str:
    """Get highly rated papers."""
    response = await client.get(
        f"{api_url}/papers",
        params={"limit": 100},
    )
    response.raise_for_status()
    data = response.json()

    papers = data.get("items", data) if isinstance(data, dict) else data

    # Filter for rating >= 4
    favorites = [p for p in papers if (p.get("rating") or 0) >= 4]

    result = {
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
    return json.dumps(result, indent=2)


async def _get_extraction_queue(
    client: httpx.AsyncClient, api_url: str
) -> str:
    """Get papers needing AI extraction."""
    try:
        response = await client.get(
            f"{api_url}/extraction/queue",
            params={"limit": 30},
        )
        response.raise_for_status()
        data = response.json()

        papers = data.get("papers", data) if isinstance(data, dict) else data

        result = {
            "title": "Extraction Queue",
            "description": "Papers needing AI summarization and analysis",
            "count": len(papers),
            "papers": [
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "has_abstract": bool(p.get("abstract")),
                    "has_full_text": bool(p.get("full_text")),
                    "priority": (
                        "high" if p.get("full_text")
                        else "medium" if p.get("abstract")
                        else "low"
                    ),
                }
                for p in papers
            ],
        }
        return json.dumps(result, indent=2)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return json.dumps({
                "title": "Extraction Queue",
                "description": "Endpoint not available",
                "count": 0,
                "papers": [],
                "note": "The extraction queue endpoint may not be configured",
            })
        raise


async def _get_library_stats(
    client: httpx.AsyncClient, api_url: str
) -> str:
    """Get library statistics overview."""
    response = await client.get(
        f"{api_url}/papers",
        params={"limit": 1000},
    )
    response.raise_for_status()
    data = response.json()

    papers = data.get("items", data) if isinstance(data, dict) else data

    # Calculate statistics
    total = len(papers)
    by_status = {"unread": 0, "reading": 0, "read": 0}
    by_year = {}
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

    result = {
        "title": "Library Statistics",
        "total_papers": total,
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
    return json.dumps(result, indent=2)


async def _get_paper_detail(
    client: httpx.AsyncClient, api_url: str, paper_id: str
) -> str:
    """Get detailed paper information."""
    response = await client.get(f"{api_url}/papers/{paper_id}")
    response.raise_for_status()
    paper = response.json()

    result = {
        "id": paper["id"],
        "title": paper["title"],
        "authors": _format_authors(paper.get("authors", [])),
        "year": paper.get("year"),
        "abstract": paper.get("abstract"),
        "doi": paper.get("doi"),
        "arxiv_id": paper.get("arxiv_id"),
        "read_status": paper.get("read_status"),
        "rating": paper.get("rating"),
        "tags": [
            t.get("name", t) if isinstance(t, dict) else t
            for t in paper.get("tags", [])
        ],
    }
    return json.dumps(result, indent=2)


async def _get_papers_by_tag(
    client: httpx.AsyncClient, api_url: str, tag_name: str
) -> str:
    """Get papers with a specific tag."""
    response = await client.get(
        f"{api_url}/papers",
        params={"tag": tag_name, "limit": 50},
    )
    response.raise_for_status()
    data = response.json()

    papers = data.get("items", data) if isinstance(data, dict) else data

    result = {
        "title": f"Papers tagged: {tag_name}",
        "count": len(papers),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
            }
            for p in papers
        ],
    }
    return json.dumps(result, indent=2)


async def _get_papers_by_author(
    client: httpx.AsyncClient, api_url: str, author_name: str
) -> str:
    """Get papers by a specific author."""
    response = await client.get(
        f"{api_url}/papers",
        params={"author": author_name, "limit": 50},
    )
    response.raise_for_status()
    data = response.json()

    papers = data.get("items", data) if isinstance(data, dict) else data

    result = {
        "title": f"Papers by: {author_name}",
        "count": len(papers),
        "papers": [
            {
                "id": p["id"],
                "title": p["title"],
                "year": p.get("year"),
                "authors": _format_authors(p.get("authors", [])),
            }
            for p in papers
        ],
    }
    return json.dumps(result, indent=2)


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
