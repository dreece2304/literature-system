"""Browser-based PDF acquisition tools for MCP server.

These tools work with the Windows-side Playwright PDF fetcher to download
PDFs that require VPN/institutional access.

Architecture:
    MCP Server (WSL) <--queue.json--> PDF Fetcher (Windows) --> downloads/
                     <--status.json--

MIGRATED: HTTP calls replaced with direct SQLAlchemy queries.
"""

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from mcp.types import TextContent, Tool

from config.ai_settings import DATA_DIR

# Add src directory to path for literature_core imports
# browser_pdf.py is at src/mcp_server/tools/browser_pdf.py, so parent.parent.parent = src/
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import get_session, Paper


# Paths for Windows-side fetcher (accessible from WSL via /mnt/c/)
WINDOWS_USER = os.getenv("WINDOWS_USER", "dreec")
FETCHER_BASE = Path(f"/mnt/c/Users/{WINDOWS_USER}/literature-ai")
QUEUE_FILE = FETCHER_BASE / "queue.json"
STATUS_FILE = FETCHER_BASE / "status.json"
DOWNLOADS_DIR = FETCHER_BASE / "downloads"

# Local PDF storage
PDF_STORAGE_PATH = Path(os.getenv("PDF_STORAGE_PATH", str(DATA_DIR / "pdfs")))


async def list_tools() -> list[Tool]:
    """List browser-based PDF tools."""
    return [
        Tool(
            name="queue_pdf_download",
            description=(
                "Queue a PDF for download via browser automation. "
                "The Windows-side PDF fetcher will download using VPN access. "
                "Use get_download_queue_status to check progress."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Paper ID to download PDF for",
                    },
                },
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="queue_batch_pdf_download",
            description=(
                "Queue multiple papers for PDF download via browser automation. "
                "More efficient than queueing one at a time."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of paper IDs to download PDFs for",
                    },
                },
                "required": ["paper_ids"],
            },
        ),
        Tool(
            name="get_download_queue_status",
            description=(
                "Get status of the PDF download queue. Shows pending, completed, "
                "and failed downloads."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "Optional: check status of specific paper",
                    },
                },
            },
        ),
        Tool(
            name="process_downloaded_pdfs",
            description=(
                "Process PDFs that have been downloaded by the browser fetcher. "
                "Extracts text, computes hash, and updates database."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "auto_match": {
                        "type": "boolean",
                        "description": "Try to match PDFs to papers by DOI in filename",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="clear_download_queue",
            description="Clear completed/failed items from the download queue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "clear_all": {
                        "type": "boolean",
                        "description": "Clear all items including pending (default: only completed/failed)",
                        "default": False,
                    },
                },
            },
        ),
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a browser PDF tool."""
    if name == "queue_pdf_download":
        return _queue_pdf_download(arguments)
    elif name == "queue_batch_pdf_download":
        return _queue_batch_pdf_download(arguments)
    elif name == "get_download_queue_status":
        return _get_download_queue_status(arguments)
    elif name == "process_downloaded_pdfs":
        return _process_downloaded_pdfs(arguments)
    elif name == "clear_download_queue":
        return _clear_download_queue(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


def _queue_pdf_download(arguments: dict[str, Any]) -> list[TextContent]:
    """Queue a single paper for PDF download."""
    paper_id = arguments["paper_id"]

    try:
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()

            if not paper:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "paper_id": paper_id,
                        "message": "Paper not found",
                    }, indent=2),
                )]

            # Check if already has PDF
            if paper.file_path:
                file_path = Path(paper.file_path)
                if file_path.exists():
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "status": "already_exists",
                            "paper_id": paper_id,
                            "file_path": str(file_path),
                        }, indent=2),
                    )]

            doi = paper.doi
            if not doi:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "status": "error",
                        "paper_id": paper_id,
                        "message": "Paper has no DOI - cannot generate download URL",
                    }, indent=2),
                )]

            title = paper.title or ""

        # Generate PDF URL
        pdf_url = _get_pdf_url_for_doi(doi)

        # Add to queue
        queue = _load_queue()

        # Check if already in queue
        existing = next(
            (item for item in queue if item["paper_id"] == paper_id),
            None,
        )
        if existing:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "already_queued",
                    "paper_id": paper_id,
                    "queue_status": existing.get("status", "pending"),
                }, indent=2),
            )]

        # Add new item
        queue_item = {
            "paper_id": paper_id,
            "doi": doi,
            "url": pdf_url,
            "title": title[:100],
            "status": "pending",
            "queued_at": datetime.now().isoformat(),
        }
        queue.append(queue_item)
        _save_queue(queue)

        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "queued",
                "paper_id": paper_id,
                "url": pdf_url,
                "message": "Added to download queue. Run start_fetcher.bat on Windows to process.",
            }, indent=2),
        )]

    except Exception as e:
        logger.error(f"Error queueing PDF: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


def _queue_batch_pdf_download(arguments: dict[str, Any]) -> list[TextContent]:
    """Queue multiple papers for PDF download."""
    paper_ids = arguments["paper_ids"]

    results = {
        "queued": [],
        "already_queued": [],
        "already_has_pdf": [],
        "no_doi": [],
        "errors": [],
    }

    queue = _load_queue()
    existing_ids = {item["paper_id"] for item in queue}

    with get_session() as session:
        for paper_id in paper_ids:
            try:
                # Skip if already in queue
                if paper_id in existing_ids:
                    results["already_queued"].append(paper_id)
                    continue

                paper = session.query(Paper).filter(Paper.id == paper_id).first()
                if not paper:
                    results["errors"].append({"paper_id": paper_id, "error": "Paper not found"})
                    continue

                # Check if already has PDF
                if paper.file_path and Path(paper.file_path).exists():
                    results["already_has_pdf"].append(paper_id)
                    continue

                doi = paper.doi
                if not doi:
                    results["no_doi"].append(paper_id)
                    continue

                # Generate PDF URL and add to queue
                pdf_url = _get_pdf_url_for_doi(doi)
                queue_item = {
                    "paper_id": paper_id,
                    "doi": doi,
                    "url": pdf_url,
                    "title": (paper.title or "")[:100],
                    "status": "pending",
                    "queued_at": datetime.now().isoformat(),
                }
                queue.append(queue_item)
                results["queued"].append(paper_id)

            except Exception as e:
                results["errors"].append({"paper_id": paper_id, "error": str(e)})

    _save_queue(queue)

    return [TextContent(
        type="text",
        text=json.dumps({
            "summary": {
                "queued": len(results["queued"]),
                "already_queued": len(results["already_queued"]),
                "already_has_pdf": len(results["already_has_pdf"]),
                "no_doi": len(results["no_doi"]),
                "errors": len(results["errors"]),
            },
            "details": results,
            "message": (
                f"Queued {len(results['queued'])} papers. "
                "Run start_fetcher.bat on Windows to process."
            ),
        }, indent=2),
    )]


def _get_download_queue_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get status of the download queue."""
    paper_id = arguments.get("paper_id")

    queue = _load_queue()
    status = _load_status()

    if paper_id:
        # Get status for specific paper
        queue_item = next(
            (item for item in queue if item["paper_id"] == paper_id),
            None,
        )
        status_item = status.get(str(paper_id))

        return [TextContent(
            type="text",
            text=json.dumps({
                "paper_id": paper_id,
                "queue_item": queue_item,
                "download_status": status_item,
            }, indent=2),
        )]

    # Summarize entire queue
    summary = {
        "pending": [],
        "success": [],
        "failed": [],
        "login_required": [],
        "other": [],
    }

    for item in queue:
        item_status = item.get("status", "pending")
        item_summary = {
            "paper_id": item["paper_id"],
            "title": item.get("title", "")[:50],
            "doi": item.get("doi"),
        }

        if item_status == "pending":
            summary["pending"].append(item_summary)
        elif item_status == "success":
            item_summary["file_path"] = item.get("file_path")
            summary["success"].append(item_summary)
        elif item_status == "failed":
            item_summary["message"] = item.get("message")
            summary["failed"].append(item_summary)
        elif item_status == "login_required":
            summary["login_required"].append(item_summary)
        else:
            item_summary["status"] = item_status
            summary["other"].append(item_summary)

    # Check downloads folder for unprocessed PDFs
    unprocessed_pdfs = []
    if DOWNLOADS_DIR.exists():
        for pdf in DOWNLOADS_DIR.glob("*.pdf"):
            unprocessed_pdfs.append({
                "filename": pdf.name,
                "size_kb": pdf.stat().st_size // 1024,
            })

    return [TextContent(
        type="text",
        text=json.dumps({
            "queue_summary": {
                "pending": len(summary["pending"]),
                "success": len(summary["success"]),
                "failed": len(summary["failed"]),
                "login_required": len(summary["login_required"]),
            },
            "pending": summary["pending"],
            "success": summary["success"],
            "failed": summary["failed"],
            "login_required": summary["login_required"],
            "unprocessed_pdfs": unprocessed_pdfs,
            "fetcher_running": _check_fetcher_running(),
        }, indent=2),
    )]


def _process_downloaded_pdfs(arguments: dict[str, Any]) -> list[TextContent]:
    """Process downloaded PDFs and update database.

    Processes PDFs from two sources:
    1. Files tracked in status.json (from Windows-side fetcher or manual downloads)
    2. PDFs in the downloads directory (for DOI-based matching)

    Uses shutil.copy2 + unlink for cross-filesystem compatibility (WSL).
    """
    auto_match = arguments.get("auto_match", True)

    # Load status and queue
    status = _load_status()
    queue = _load_queue()

    results = {
        "processed": [],
        "already_imported": [],
        "no_match": [],
        "errors": [],
    }

    # Helper to convert Windows path to WSL path
    def to_wsl_path(windows_path: str) -> Path:
        """Convert Windows path to WSL path."""
        if not windows_path:
            return None
        # Handle both C:\\ and C:\ formats
        path = windows_path.replace("\\", "/")
        if path.startswith("C:/"):
            path = "/mnt/c/" + path[3:]
        elif path.startswith("c:/"):
            path = "/mnt/c/" + path[3:]
        return Path(path)

    # Collect PDFs to process from status.json (successful downloads)
    pdfs_to_process = []
    for paper_id_str, info in status.items():
        if info.get("status") == "success" and info.get("file_path"):
            pdf_path = to_wsl_path(info["file_path"])
            if pdf_path and pdf_path.exists():
                pdfs_to_process.append({
                    "path": pdf_path,
                    "paper_id": info.get("paper_id"),
                    "doi": info.get("doi"),
                    "source": "status.json",
                })

    # Also check downloads directory for untracked PDFs
    if DOWNLOADS_DIR.exists():
        tracked_names = {p["path"].name for p in pdfs_to_process}
        for pdf_path in DOWNLOADS_DIR.glob("*.pdf"):
            if pdf_path.name not in tracked_names:
                pdfs_to_process.append({
                    "path": pdf_path,
                    "paper_id": None,
                    "doi": None,
                    "source": "downloads_dir",
                })

    logger.info(f"Found {len(pdfs_to_process)} PDFs to process")

    with get_session() as session:
        for pdf_info in pdfs_to_process:
            pdf_path = pdf_info["path"]
            paper_id = pdf_info["paper_id"]
            doi = pdf_info["doi"]

            try:
                # If no paper_id, try to match by DOI from filename
                if not paper_id and auto_match:
                    filename = pdf_path.stem
                    # Filename format: 10.1016_j.memsci.2020.118610.pdf
                    if filename.startswith("10."):
                        doi = filename.replace("_", "/", 1)
                        paper = session.query(Paper).filter(Paper.doi == doi).first()
                        if paper:
                            paper_id = paper.id

                if not paper_id:
                    results["no_match"].append({
                        "filename": pdf_path.name,
                        "doi": doi,
                    })
                    continue

                # Get paper
                paper = session.query(Paper).filter(Paper.id == paper_id).first()
                if not paper:
                    results["errors"].append({
                        "filename": pdf_path.name,
                        "error": f"Paper {paper_id} not found",
                    })
                    continue

                # Check if already has this PDF
                if paper.file_path:
                    existing = Path(paper.file_path)
                    if existing.exists():
                        new_hash = _compute_file_hash(pdf_path)
                        if new_hash == paper.file_hash:
                            results["already_imported"].append({
                                "paper_id": paper_id,
                                "filename": pdf_path.name,
                            })
                            # Delete duplicate source file
                            pdf_path.unlink()
                            continue

                # Copy PDF to storage location (use copy for cross-filesystem support)
                PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
                dest_path = PDF_STORAGE_PATH / pdf_path.name

                # Handle duplicate filenames
                if dest_path.exists():
                    base = pdf_path.stem
                    suffix = pdf_path.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = PDF_STORAGE_PATH / f"{base}_{counter}{suffix}"
                        counter += 1

                # Copy then delete (cross-filesystem safe)
                shutil.copy2(pdf_path, dest_path)
                pdf_path.unlink()

                # Extract text and compute hash
                full_text, word_count = _extract_text_from_pdf(dest_path)
                file_hash = _compute_file_hash(dest_path)

                # Update paper in database
                paper.file_path = str(dest_path)
                paper.file_hash = file_hash
                paper.word_count = word_count
                # NOTE: No longer setting paper.full_text - use ExtractionService.extract_pdf_and_store()
                # to create PaperChunk records instead. Call queue_pdf_extraction() after this.

                results["processed"].append({
                    "paper_id": paper_id,
                    "doi": doi or paper.doi,
                    "file_path": str(dest_path),
                    "word_count": word_count,
                })

                logger.info(f"Processed PDF for paper {paper_id}: {dest_path}")

            except Exception as e:
                logger.error(f"Error processing {pdf_path.name}: {e}")
                results["errors"].append({
                    "filename": pdf_path.name,
                    "error": str(e),
                })

    return [TextContent(
        type="text",
        text=json.dumps({
            "summary": {
                "processed": len(results["processed"]),
                "already_imported": len(results["already_imported"]),
                "no_match": len(results["no_match"]),
                "errors": len(results["errors"]),
            },
            "details": results,
        }, indent=2),
    )]


def _clear_download_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Clear the download queue."""
    clear_all = arguments.get("clear_all", False)

    queue = _load_queue()
    original_count = len(queue)

    if clear_all:
        queue = []
    else:
        # Keep only pending items
        queue = [item for item in queue if item.get("status") == "pending"]

    _save_queue(queue)

    return [TextContent(
        type="text",
        text=json.dumps({
            "cleared": original_count - len(queue),
            "remaining": len(queue),
        }, indent=2),
    )]


# Helper functions

def _load_queue() -> list:
    """Load the download queue."""
    if QUEUE_FILE.exists():
        try:
            with open(QUEUE_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def _save_queue(queue: list):
    """Save the download queue."""
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def _load_status() -> dict:
    """Load status of completed downloads."""
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def _check_fetcher_running() -> bool:
    """Check if the PDF fetcher is running (heuristic)."""
    # Check if queue was modified recently
    if QUEUE_FILE.exists():
        mtime = QUEUE_FILE.stat().st_mtime
        age = datetime.now().timestamp() - mtime
        return age < 60  # Modified in last minute
    return False


def _get_pdf_url_for_doi(doi: str) -> str:
    """Generate the best PDF URL for a DOI."""
    # Elsevier - use ScienceDirect
    if doi.startswith("10.1016"):
        # The Playwright fetcher will handle the actual download
        # We just need to get to the article page
        return f"https://doi.org/{doi}"

    # ACS
    if doi.startswith("10.1021"):
        return f"https://pubs.acs.org/doi/pdf/{doi}"

    # Wiley
    if doi.startswith("10.1002"):
        return f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}"

    # Nature
    if doi.startswith("10.1038"):
        return f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf"

    # Springer
    if doi.startswith("10.1007"):
        return f"https://link.springer.com/content/pdf/{doi}.pdf"

    # RSC
    if doi.startswith("10.1039"):
        return f"https://pubs.rsc.org/en/content/articlepdf/{doi}"

    # Default: use DOI resolver
    return f"https://doi.org/{doi}"


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


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
