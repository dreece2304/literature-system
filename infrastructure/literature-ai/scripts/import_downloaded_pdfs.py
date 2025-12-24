#!/usr/bin/env python3
"""
Batch import downloaded PDFs into the literature database.

Reads queue.json for successful downloads, copies PDFs to standard storage,
and updates paper records with file paths. Text extraction is handled
separately by Claude via MCP tools for better quality extraction.

Usage:
    python import_downloaded_pdfs.py [--queue-file PATH] [--dry-run]
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import httpx


# Configuration
DEFAULT_QUEUE_FILE = Path("/mnt/c/Users/dreec/literature-ai/queue.json")
PDF_STORAGE_PATH = Path("/mnt/c/Users/dreec/literature-ai/pdfs")
API_URL = "http://localhost:8001/api/v1"


def windows_to_wsl_path(windows_path: str) -> Path:
    """Convert Windows path to WSL path."""
    if not windows_path:
        return None

    # Handle paths like C:\Users\... -> /mnt/c/Users/...
    path = windows_path.replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        path = f"/mnt/{drive}{path[2:]}"

    return Path(path)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def generate_filename(paper_id: int, doi: str) -> str:
    """Generate a standardized filename for the PDF."""
    if doi:
        base = doi.replace("/", "_").replace(":", "_")
    else:
        base = f"paper_{paper_id}"
    return f"{base}.pdf"


def get_paper(client: httpx.Client, paper_id: int) -> dict | None:
    """Fetch paper from database."""
    try:
        response = client.get(f"{API_URL}/papers/{paper_id}")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  Failed to fetch paper {paper_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"  Error fetching paper {paper_id}: {e}")
        return None


def update_paper(client: httpx.Client, paper_id: int, paper_data: dict, updates: dict) -> bool:
    """Update paper in database."""
    # Prepare data for update
    update_data = dict(paper_data)

    # Convert authors/tags if they're objects
    if "authors" in update_data and update_data["authors"]:
        if isinstance(update_data["authors"][0], dict):
            update_data["authors"] = [
                a.get("name", "") for a in update_data["authors"] if a.get("name")
            ]
    if "tags" in update_data and update_data["tags"]:
        if isinstance(update_data["tags"][0], dict):
            update_data["tags"] = [
                t.get("name", "") for t in update_data["tags"] if t.get("name")
            ]

    update_data.pop("collections", None)
    update_data.update(updates)

    try:
        response = client.put(f"{API_URL}/papers/{paper_id}", json=update_data)
        if response.status_code in (200, 204):
            return True
        else:
            print(f"  Failed to update paper {paper_id}: {response.status_code}")
            print(f"  Response: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"  Error updating paper {paper_id}: {e}")
        return False


def process_paper(client: httpx.Client, entry: dict, dry_run: bool = False) -> bool:
    """Process a single paper entry from the queue."""
    paper_id = entry["paper_id"]
    doi = entry.get("doi", "")
    title = entry.get("title", "Unknown")
    windows_path = entry.get("file_path")

    print(f"\nProcessing paper {paper_id}: {title[:60]}...")

    if not windows_path:
        print("  No file path in queue entry")
        return False

    # Convert Windows path to WSL path
    source_path = windows_to_wsl_path(windows_path)
    if not source_path or not source_path.exists():
        print(f"  Source file not found: {source_path}")
        return False

    print(f"  Source: {source_path}")

    # Generate destination path
    filename = generate_filename(paper_id, doi)
    dest_path = PDF_STORAGE_PATH / filename

    if dry_run:
        print(f"  [DRY RUN] Would copy to: {dest_path}")
        print(f"  [DRY RUN] Would extract text and update database")
        return True

    # Create storage directory if needed
    PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

    # Copy file to storage
    try:
        shutil.copy2(source_path, dest_path)
        print(f"  Copied to: {dest_path}")
    except Exception as e:
        print(f"  Error copying file: {e}")
        return False

    # Compute hash
    file_hash = compute_file_hash(dest_path)
    print(f"  Hash: {file_hash[:16]}...")

    # Fetch current paper data
    paper_data = get_paper(client, paper_id)
    if not paper_data:
        return False

    # Prepare updates (text extraction done separately by Claude via MCP)
    updates = {
        "file_path": str(dest_path),
        "file_hash": file_hash,
    }

    # Update database
    print("  Updating database...")
    if update_paper(client, paper_id, paper_data, updates):
        print("  Success!")
        return True
    else:
        return False


def main():
    parser = argparse.ArgumentParser(description="Import downloaded PDFs into database")
    parser.add_argument(
        "--queue-file",
        type=Path,
        default=DEFAULT_QUEUE_FILE,
        help=f"Path to queue.json file (default: {DEFAULT_QUEUE_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--paper-id",
        type=int,
        help="Process only this paper ID",
    )
    args = parser.parse_args()

    # Load queue
    if not args.queue_file.exists():
        print(f"Queue file not found: {args.queue_file}")
        sys.exit(1)

    with open(args.queue_file) as f:
        queue = json.load(f)

    # Filter to successful downloads
    successful = [
        entry for entry in queue
        if entry.get("status") == "success" and entry.get("file_path")
    ]

    if args.paper_id:
        successful = [e for e in successful if e["paper_id"] == args.paper_id]

    print(f"Found {len(successful)} successful downloads to process")

    if not successful:
        print("Nothing to import.")
        return

    if args.dry_run:
        print("\n=== DRY RUN MODE ===\n")

    # Process each paper
    results = {"success": 0, "failed": 0}

    with httpx.Client(timeout=60.0) as client:
        # Test API connection
        try:
            response = client.get(f"{API_URL}/papers", params={"limit": 1})
            response.raise_for_status()
        except Exception as e:
            print(f"Error connecting to API at {API_URL}: {e}")
            print("Make sure the literature-database server is running.")
            sys.exit(1)

        for entry in successful:
            if process_paper(client, entry, args.dry_run):
                results["success"] += 1
            else:
                results["failed"] += 1

    # Summary
    print(f"\n{'='*50}")
    print(f"Import complete!")
    print(f"  Successful: {results['success']}")
    print(f"  Failed: {results['failed']}")


if __name__ == "__main__":
    main()
