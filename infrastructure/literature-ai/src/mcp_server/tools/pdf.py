"""PDF acquisition and management tools for MCP server."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from mcp.types import TextContent, Tool

from config.settings import settings, DATA_DIR


# PDF storage configuration
PDF_STORAGE_PATH = Path(os.getenv("PDF_STORAGE_PATH", str(DATA_DIR / "pdfs")))


def get_api_url() -> str:
    """Get the literature database API URL."""
    url = settings.litdb.api_url.rstrip("/")
    if not url.endswith("/api/v1"):
        url = f"{url}/api/v1"
    return url


async def list_tools() -> list[Tool]:
    """List PDF management tools."""
    return [
        Tool(
            name="acquire_paper_pdf",
            description="Download PDF for a paper using open access sources or UW proxy",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to acquire PDF for",
                    },
                    "use_proxy": {
                        "type": "boolean",
                        "description": "Use UW EZProxy for institutional access (requires cookies)",
                        "default": False,
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_pdf_status",
            description="Get PDF status for papers - which have PDFs downloaded, which need PDFs",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["all", "has_pdf", "needs_pdf"],
                        "description": "Filter papers by PDF status",
                        "default": "all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to return",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="find_duplicates",
            description="Find duplicate papers by file hash or title similarity",
            inputSchema={
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["hash", "title"],
                        "description": "Detection method: 'hash' (exact file match) or 'title' (similar titles)",
                        "default": "title",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Similarity threshold for title matching (0.0-1.0)",
                        "default": 0.85,
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a PDF tool."""
    api_url = get_api_url()

    if name == "acquire_paper_pdf":
        return await _acquire_paper_pdf(api_url, arguments)
    elif name == "get_pdf_status":
        return await _get_pdf_status(api_url, arguments)
    elif name == "find_duplicates":
        return await _find_duplicates(api_url, arguments)
    else:
        return [TextContent(type="text", text=f"Unknown PDF tool: {name}")]


async def _acquire_paper_pdf(api_url: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Download PDF for a specific paper."""
    paper_id = arguments["paper_id"]
    use_proxy = arguments.get("use_proxy", False)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Get paper details
            response = await client.get(f"{api_url}/papers/{paper_id}")
            response.raise_for_status()
            paper = response.json()

            # Check if already has PDF
            if paper.get("file_path"):
                file_path = Path(paper["file_path"])
                if file_path.exists():
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "status": "already_exists",
                            "paper_id": paper_id,
                            "file_path": str(file_path),
                            "word_count": paper.get("word_count", 0),
                        }, indent=2),
                    )]

            doi = paper.get("doi")
            arxiv_id = paper.get("arxiv_id")

            if not doi and not arxiv_id:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "paper_id": paper_id,
                        "message": "Paper has no DOI or arXiv ID - cannot acquire PDF",
                    }, indent=2),
                )]

            # Try to find and download PDF
            from src.services.external_search import ExternalSearchService
            service = ExternalSearchService()

            pdf_url = await _find_pdf_url(service, paper)
            if not pdf_url and use_proxy and doi:
                pdf_url = _get_publisher_pdf_url_via_proxy(doi)

            if not pdf_url:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "not_found",
                        "paper_id": paper_id,
                        "message": "No open access PDF found. Try use_proxy=true for institutional access.",
                    }, indent=2),
                )]

            # Generate filename and download
            filename = _generate_filename(paper)
            file_path = PDF_STORAGE_PATH / filename
            PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

            success = await _download_pdf(pdf_url, file_path)
            if not success:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "download_failed",
                        "paper_id": paper_id,
                        "pdf_url": pdf_url,
                        "message": "Failed to download PDF",
                    }, indent=2),
                )]

            # Extract text and compute hash
            full_text, word_count = _extract_text_from_pdf(file_path)
            file_hash = _compute_file_hash(file_path)

            # Update paper in database
            updates = _prepare_paper_update(paper, {
                "file_path": str(file_path),
                "file_hash": file_hash,
                "word_count": word_count,
            })
            if full_text:
                updates["full_text"] = full_text

            update_response = await client.put(
                f"{api_url}/papers/{paper_id}",
                json=updates,
            )
            update_response.raise_for_status()

            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "success",
                    "paper_id": paper_id,
                    "file_path": str(file_path),
                    "word_count": word_count,
                    "pdf_url": pdf_url,
                }, indent=2),
            )]

        except httpx.HTTPStatusError as e:
            logger.error(f"API error: {e.response.status_code} - {e.response.text}")
            return [TextContent(
                type="text",
                text=f"API Error: {e.response.status_code} - {e.response.text[:500]}",
            )]
        except Exception as e:
            logger.error(f"Error acquiring PDF: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _get_pdf_status(api_url: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Get PDF status for papers."""
    filter_type = arguments.get("filter", "all")
    limit = min(arguments.get("limit", 50), 200)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Fetch all papers (paginated)
            papers = []
            offset = 0
            batch_size = 100

            while len(papers) < limit:
                response = await client.get(
                    f"{api_url}/papers",
                    params={"offset": offset, "limit": batch_size},
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("items", data) if isinstance(data, dict) else data
                if not items:
                    break

                papers.extend(items)
                offset += batch_size

                if isinstance(data, dict) and offset >= data.get("total", 0):
                    break

            # Categorize papers
            has_pdf = []
            needs_pdf = []
            no_identifier = []

            for p in papers:
                file_path = p.get("file_path")
                doi = p.get("doi")
                arxiv_id = p.get("arxiv_id")

                paper_info = {
                    "id": p["id"],
                    "title": p["title"][:80] + "..." if len(p.get("title", "")) > 80 else p.get("title"),
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                }

                if file_path:
                    paper_info["file_path"] = file_path
                    paper_info["word_count"] = p.get("word_count", 0)
                    has_pdf.append(paper_info)
                elif doi or arxiv_id:
                    needs_pdf.append(paper_info)
                else:
                    no_identifier.append(paper_info)

            # Apply filter
            if filter_type == "has_pdf":
                result_papers = has_pdf[:limit]
            elif filter_type == "needs_pdf":
                result_papers = needs_pdf[:limit]
            else:
                result_papers = (has_pdf + needs_pdf + no_identifier)[:limit]

            result = {
                "summary": {
                    "total_papers": len(papers),
                    "has_pdf": len(has_pdf),
                    "needs_pdf": len(needs_pdf),
                    "no_identifier": len(no_identifier),
                },
                "filter": filter_type,
                "papers": result_papers,
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        except httpx.HTTPStatusError as e:
            logger.error(f"API error: {e.response.status_code}")
            return [TextContent(type="text", text=f"API Error: {e.response.status_code}")]
        except Exception as e:
            logger.error(f"Error getting PDF status: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _find_duplicates(api_url: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Find duplicate papers."""
    method = arguments.get("method", "title")
    threshold = arguments.get("threshold", 0.85)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Fetch all papers
            papers = []
            offset = 0
            batch_size = 100

            while True:
                response = await client.get(
                    f"{api_url}/papers",
                    params={"offset": offset, "limit": batch_size},
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("items", data) if isinstance(data, dict) else data
                if not items:
                    break

                papers.extend(items)
                offset += batch_size

                if isinstance(data, dict) and offset >= data.get("total", 0):
                    break

            duplicates = []

            if method == "hash":
                # Group by file_hash
                hash_groups: dict[str, list] = {}
                for p in papers:
                    file_hash = p.get("file_hash")
                    if file_hash:
                        if file_hash not in hash_groups:
                            hash_groups[file_hash] = []
                        hash_groups[file_hash].append({
                            "id": p["id"],
                            "title": p["title"],
                            "file_path": p.get("file_path"),
                        })

                for file_hash, group in hash_groups.items():
                    if len(group) > 1:
                        duplicates.append({
                            "type": "hash_match",
                            "file_hash": file_hash,
                            "papers": group,
                        })

            else:  # title similarity
                from difflib import SequenceMatcher

                # Compare all pairs
                checked = set()
                for i, p1 in enumerate(papers):
                    for j, p2 in enumerate(papers[i + 1:], i + 1):
                        pair_key = (min(p1["id"], p2["id"]), max(p1["id"], p2["id"]))
                        if pair_key in checked:
                            continue
                        checked.add(pair_key)

                        title1 = p1.get("title", "").lower().strip()
                        title2 = p2.get("title", "").lower().strip()

                        if not title1 or not title2:
                            continue

                        similarity = SequenceMatcher(None, title1, title2).ratio()
                        if similarity >= threshold:
                            duplicates.append({
                                "type": "title_similarity",
                                "similarity": round(similarity, 3),
                                "papers": [
                                    {"id": p1["id"], "title": p1["title"]},
                                    {"id": p2["id"], "title": p2["title"]},
                                ],
                            })

            result = {
                "method": method,
                "threshold": threshold if method == "title" else None,
                "total_papers": len(papers),
                "duplicate_groups": len(duplicates),
                "duplicates": duplicates[:50],  # Limit output
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        except Exception as e:
            logger.error(f"Error finding duplicates: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]


# Helper functions (refactored from acquire_pdfs.py)

async def _find_pdf_url(service, paper: dict) -> str | None:
    """Try to find a PDF URL for a paper using various sources."""
    doi = paper.get("doi")
    title = paper.get("title", "")
    arxiv_id = paper.get("arxiv_id")

    # Strategy 1: Unpaywall (most reliable for OA)
    if doi:
        pdf_url = await service.find_pdf_url(doi)
        if pdf_url:
            return pdf_url

    # Strategy 2: Springer Open Access
    if doi:
        pdf_url = await service.search_springer_openaccess_by_doi(doi)
        if pdf_url:
            return pdf_url

    # Strategy 3: Semantic Scholar
    if title:
        results = await service._search_semantic_scholar_query(title, limit=1)
        if results and results[0].pdf_url:
            if service._title_similarity(title, results[0].title) > 0.8:
                return results[0].pdf_url

    # Strategy 4: arXiv (predictable URLs)
    if arxiv_id:
        clean_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
        return f"https://arxiv.org/pdf/{clean_id}.pdf"

    return None


def _get_publisher_pdf_url_via_proxy(doi: str) -> str | None:
    """Get PDF URL through UW EZProxy."""
    from urllib.parse import urlparse, urlunparse

    UW_EZPROXY_PREFIX = "offcampus.lib.washington.edu"

    # Common publisher patterns
    publishers = {
        "10.1016": "https://www.sciencedirect.com/science/article/pii/",  # Elsevier needs PII
        "10.1021": f"https://pubs.acs.org/doi/pdf/{doi}",
        "10.1002": f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",
        "10.1038": f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf",
        "10.1007": f"https://link.springer.com/content/pdf/{doi}.pdf",
    }

    for prefix, url_template in publishers.items():
        if doi.startswith(prefix):
            parsed = urlparse(url_template)
            proxied_host = f"{parsed.netloc}.{UW_EZPROXY_PREFIX}"
            return urlunparse(parsed._replace(netloc=proxied_host))

    return None


async def _download_pdf(url: str, output_path: Path) -> bool:
    """Download a PDF from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        headers=headers,
    ) as client:
        try:
            response = await client.get(url)

            if response.status_code in (401, 403):
                logger.debug(f"Access denied (HTTP {response.status_code})")
                return False

            if response.status_code != 200:
                logger.warning(f"Failed to download PDF: HTTP {response.status_code}")
                return False

            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
                if "html" in content_type.lower():
                    logger.debug("Got HTML instead of PDF")
                    return False
                logger.warning(f"Not a PDF: {content_type}")
                return False

            content = response.content
            if not content.startswith(b"%PDF"):
                logger.warning("Downloaded file is not a valid PDF")
                return False

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(content)
            return True

        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return False


def _extract_text_from_pdf(file_path: Path) -> tuple[str, int]:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed")
        return "", 0

    full_text = []

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)

        combined = "\n\n".join(full_text)
        word_count = len(combined.split())
        return combined, word_count

    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return "", 0


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _generate_filename(paper: dict) -> str:
    """Generate a unique filename for a paper's PDF."""
    paper_id = paper.get("id", "unknown")
    doi = paper.get("doi", "")
    arxiv_id = paper.get("arxiv_id", "")

    if doi:
        base = doi.replace("/", "_").replace(":", "_")
    elif arxiv_id:
        base = f"arxiv_{arxiv_id}"
    else:
        base = f"paper_{paper_id}"

    return f"{base}.pdf"


def _prepare_paper_update(current: dict, updates: dict) -> dict:
    """Prepare paper data for API update."""
    paper_data = dict(current)

    # Convert authors/tags if they're objects
    if "authors" in paper_data and paper_data["authors"]:
        if isinstance(paper_data["authors"][0], dict):
            paper_data["authors"] = [
                a.get("name", "") for a in paper_data["authors"] if a.get("name")
            ]
    if "tags" in paper_data and paper_data["tags"]:
        if isinstance(paper_data["tags"][0], dict):
            paper_data["tags"] = [
                t.get("name", "") for t in paper_data["tags"] if t.get("name")
            ]

    paper_data.pop("collections", None)
    paper_data.update(updates)

    return paper_data
