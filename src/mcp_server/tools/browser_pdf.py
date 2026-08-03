"""Browser-based PDF acquisition tools for MCP server.

These tools work with the Windows-side Playwright PDF fetcher to download
PDFs that require VPN/institutional access.

Architecture:
    MCP Server (WSL) <--queue.json--> PDF Fetcher (Windows) --> downloads/
                     <--status.json--

Consolidated tools:
    - queue_pdf_download: Queue papers for download (single or batch)
    - get_download_queue_status: Check queue status
    - process_downloaded_pdfs: Import downloaded PDFs
    - clear_download_queue: Clear completed/failed items
"""

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
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from literature_core import get_session, Paper, serialize
from services.pdf_service import PDFService


# Paths for Windows-side fetcher (accessible from WSL via /mnt/c/)
WINDOWS_USER = os.getenv("WINDOWS_USER", "dreec")
FETCHER_BASE = Path(f"/mnt/c/Users/{WINDOWS_USER}/literature-ai")
QUEUE_FILE = FETCHER_BASE / "queue.json"
STATUS_FILE = FETCHER_BASE / "status.json"
DOWNLOADS_DIR = FETCHER_BASE / "downloads"

# Local PDF storage
PDF_STORAGE_PATH = Path(os.getenv("PDF_STORAGE_PATH", str(DATA_DIR / "pdfs")))


async def list_tools() -> list[Tool]:
    """Browser PDF tools are now consolidated into pdf.py.

    This module is kept as internal helpers for pdf.py.
    Use pdf.py's acquire_pdf(method="browser_queue") and manage_pdf() instead.
    """
    return []  # No tools exposed - consolidated into pdf.py


async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Browser PDF tools are consolidated into pdf.py.

    This call_tool is kept for backwards compatibility but tools
    should be accessed through pdf.py's acquire_pdf and manage_pdf.
    """
    return [TextContent(type="text", text=serialize({
        "error": "Browser PDF tools consolidated into pdf.py. Use acquire_pdf or manage_pdf."
    }))]


def _queue_pdf_download(arguments: dict[str, Any]) -> list[TextContent]:
    """Queue paper(s) for PDF download."""
    paper_id = arguments.get("paper_id")
    paper_ids = arguments.get("paper_ids", [])

    # Handle single paper_id
    if paper_id and not paper_ids:
        paper_ids = [paper_id]

    if not paper_ids:
        return [TextContent(type="text", text=serialize({
            "error": "Must provide paper_id or paper_ids"
        }))]

    results = {
        "queued": [],
        "already_queued": [],
        "already_has_pdf": [],
        "no_doi": [],
        "not_found": [],
        "errors": [],
    }

    queue = _load_queue()
    existing_ids = {item["paper_id"] for item in queue}

    with get_session() as session:
        for pid in paper_ids:
            try:
                if pid in existing_ids:
                    results["already_queued"].append(pid)
                    continue

                paper = session.query(Paper).filter(Paper.id == pid).first()
                if not paper:
                    results["not_found"].append(pid)
                    continue

                if paper.file_path and Path(paper.file_path).exists():
                    results["already_has_pdf"].append(pid)
                    continue

                if not paper.doi:
                    results["no_doi"].append(pid)
                    continue

                pdf_url = _get_pdf_url_for_doi(paper.doi)
                queue.append({
                    "paper_id": pid,
                    "doi": paper.doi,
                    "url": pdf_url,
                    "title": (paper.title or "")[:100],
                    "status": "pending",
                    "queued_at": datetime.now().isoformat(),
                })
                results["queued"].append(pid)

            except Exception as e:
                results["errors"].append({"paper_id": pid, "error": str(e)})

    _save_queue(queue)

    return [TextContent(type="text", text=serialize({
        "summary": {k: len(v) for k, v in results.items()},
        "details": results,
        "message": f"Queued {len(results['queued'])} papers. Run start_fetcher.bat on Windows." if results["queued"] else "No papers queued.",
    }))]


def _get_download_queue_status(arguments: dict[str, Any]) -> list[TextContent]:
    """Get status of the download queue."""
    paper_id = arguments.get("paper_id")

    queue = _load_queue()
    status = _load_status()

    if paper_id:
        queue_item = next((item for item in queue if item["paper_id"] == paper_id), None)
        return [TextContent(type="text", text=serialize({
            "paper_id": paper_id,
            "queue_item": queue_item,
            "download_status": status.get(str(paper_id)),
        }))]

    summary = {"pending": [], "success": [], "failed": [], "login_required": []}

    for item in queue:
        item_status = item.get("status", "pending")
        item_info = {"paper_id": item["paper_id"], "doi": item.get("doi")}

        if item_status in summary:
            summary[item_status].append(item_info)

    unprocessed_pdfs = []
    if DOWNLOADS_DIR.exists():
        for pdf in DOWNLOADS_DIR.glob("*.pdf"):
            unprocessed_pdfs.append({"filename": pdf.name, "size_kb": pdf.stat().st_size // 1024})

    return [TextContent(type="text", text=serialize({
        "queue_summary": {k: len(v) for k, v in summary.items()},
        "pending": summary["pending"],
        "success": summary["success"],
        "failed": summary["failed"],
        "unprocessed_pdfs": unprocessed_pdfs,
    }))]


def _process_downloaded_pdfs(arguments: dict[str, Any]) -> list[TextContent]:
    """Process downloaded PDFs and update database."""
    auto_match = arguments.get("auto_match", True)

    status = _load_status()
    results = {"processed": [], "already_imported": [], "no_match": [], "errors": []}

    def to_wsl_path(windows_path: str) -> Path | None:
        if not windows_path:
            return None
        path = windows_path.replace("\\", "/")
        if path.lower().startswith("c:/"):
            path = "/mnt/c/" + path[3:]
        return Path(path)

    def sanitize_doi(doi: str) -> str:
        return doi.replace("/", "_").replace(":", "-") if doi else ""

    # Collect PDFs from status.json
    pdfs_to_process = []
    for paper_id_str, info in status.items():
        if info.get("status") == "success" and info.get("file_path"):
            pdf_path = to_wsl_path(info["file_path"])
            if pdf_path and pdf_path.exists():
                pdfs_to_process.append({
                    "path": pdf_path,
                    "paper_id": info.get("paper_id"),
                    "doi": info.get("doi"),
                })

    # Check downloads directory
    if DOWNLOADS_DIR.exists():
        tracked_names = {p["path"].name for p in pdfs_to_process}
        for pdf_path in DOWNLOADS_DIR.glob("*.pdf"):
            if pdf_path.name not in tracked_names:
                pdfs_to_process.append({"path": pdf_path, "paper_id": None, "doi": None})

    with get_session() as session:
        for pdf_info in pdfs_to_process:
            pdf_path = pdf_info["path"]
            paper_id = pdf_info["paper_id"]
            doi = pdf_info["doi"]

            try:
                # Auto-match by DOI in filename
                if not paper_id and auto_match:
                    filename = pdf_path.stem
                    if filename.startswith("10."):
                        doi = filename.replace("_", "/", 1)
                        paper = session.query(Paper).filter(Paper.doi == doi).first()
                        if paper:
                            paper_id = paper.id

                if not paper_id:
                    results["no_match"].append({"filename": pdf_path.name, "doi": doi})
                    continue

                paper = session.query(Paper).filter(Paper.id == paper_id).first()
                if not paper:
                    results["errors"].append({"filename": pdf_path.name, "error": f"Paper {paper_id} not found"})
                    continue

                # Check for duplicates
                if paper.file_path and Path(paper.file_path).exists():
                    new_hash = PDFService.compute_file_hash(pdf_path)
                    if new_hash == paper.file_hash:
                        results["already_imported"].append({"paper_id": paper_id})
                        pdf_path.unlink()
                        continue

                # Move to storage
                PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
                dest_path = PDF_STORAGE_PATH / f"{paper_id}_{sanitize_doi(paper.doi or doi)}.pdf"
                shutil.copy2(pdf_path, dest_path)
                pdf_path.unlink()

                # Extract text and update paper
                full_text, word_count = _extract_text_from_pdf(dest_path)
                paper.file_path = str(dest_path)
                paper.file_hash = PDFService.compute_file_hash(dest_path)
                paper.word_count = word_count

                results["processed"].append({"paper_id": paper_id, "file_path": str(dest_path), "word_count": word_count})

            except Exception as e:
                results["errors"].append({"filename": pdf_path.name, "error": str(e)})

    return [TextContent(type="text", text=serialize({
        "summary": {k: len(v) for k, v in results.items()},
        "details": results,
    }))]


def _clear_download_queue(arguments: dict[str, Any]) -> list[TextContent]:
    """Clear the download queue."""
    clear_all = arguments.get("clear_all", False)

    queue = _load_queue()
    original_count = len(queue)

    if clear_all:
        queue = []
    else:
        queue = [item for item in queue if item.get("status") == "pending"]

    _save_queue(queue)

    return [TextContent(type="text", text=serialize({
        "cleared": original_count - len(queue),
        "remaining": len(queue),
    }))]


# Helper functions

def _load_queue() -> list:
    if QUEUE_FILE.exists():
        try:
            with open(QUEUE_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def _save_queue(queue: list):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f)


def _load_status() -> dict:
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def _get_pdf_url_for_doi(doi: str) -> str:
    """Generate the best PDF URL for a DOI."""
    if doi.startswith("10.1016"):
        return f"https://doi.org/{doi}"
    if doi.startswith("10.1021"):
        return f"https://pubs.acs.org/doi/pdf/{doi}"
    if doi.startswith("10.1002"):
        return f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}"
    if doi.startswith("10.1038"):
        return f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf"
    if doi.startswith("10.1007"):
        return f"https://link.springer.com/content/pdf/{doi}.pdf"
    if doi.startswith("10.1039"):
        return f"https://pubs.rsc.org/en/content/articlepdf/{doi}"
    return f"https://doi.org/{doi}"


def _extract_text_from_pdf(file_path: Path) -> tuple[str, int]:
    try:
        import pdfplumber
    except ImportError:
        return "", 0

    try:
        with pdfplumber.open(file_path) as pdf:
            full_text = [page.extract_text() or "" for page in pdf.pages]
        combined = "\n\n".join(full_text)
        return combined, len(combined.split())
    except Exception as e:
        logger.error(f"Error extracting text: {e}")
        return "", 0
