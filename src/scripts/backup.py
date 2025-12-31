#!/usr/bin/env python3
"""Backup script for Literature MCP Server.

Creates backups of:
- SQLite database
- PDF storage directory
- ChromaDB persistence directory
- Export all papers to JSON/BibTeX

Usage:
    python -m scripts.backup --output-dir ~/backups
    python -m scripts.backup --output-dir ~/backups --include-pdfs
    python -m scripts.backup --output-dir ~/backups --compress
    python -m scripts.backup --list  # List existing backups
"""
import argparse
import json
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add src to path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@dataclass
class BackupResult:
    """Result of a backup operation."""
    timestamp: str
    backup_dir: str
    database_backup: Optional[str]
    pdf_backup: Optional[str]
    chroma_backup: Optional[str]
    export_backup: Optional[str]
    total_size_mb: float
    errors: List[str]
    duration_seconds: float


def get_backup_dir(output_dir: str) -> Path:
    """Create timestamped backup directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(output_dir) / f"literature_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_database(backup_dir: Path) -> Optional[str]:
    """Backup SQLite database."""
    try:
        from config.settings import Settings

        db_path = Path(Settings.DATABASE_PATH)
        if not db_path.exists():
            return None

        dest = backup_dir / "database" / db_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Use SQLite backup API for safe copy
        import sqlite3
        source_conn = sqlite3.connect(str(db_path))
        dest_conn = sqlite3.connect(str(dest))

        with dest_conn:
            source_conn.backup(dest_conn)

        source_conn.close()
        dest_conn.close()

        return str(dest)
    except Exception as e:
        print(f"Database backup failed: {e}", file=sys.stderr)
        return None


def backup_pdfs(backup_dir: Path, compress: bool = False) -> Optional[str]:
    """Backup PDF storage directory."""
    try:
        from config.settings import Settings

        pdf_path = Path(Settings.PDF_STORAGE_PATH)
        if not pdf_path.exists():
            return None

        if compress:
            dest = backup_dir / "pdfs.tar.gz"
            with tarfile.open(dest, "w:gz") as tar:
                tar.add(pdf_path, arcname="pdfs")
            return str(dest)
        else:
            dest = backup_dir / "pdfs"
            shutil.copytree(pdf_path, dest)
            return str(dest)
    except Exception as e:
        print(f"PDF backup failed: {e}", file=sys.stderr)
        return None


def backup_chroma(backup_dir: Path) -> Optional[str]:
    """Backup ChromaDB persistence directory."""
    try:
        from config.ai_settings import AIConfig

        chroma_path = Path(AIConfig.CHROMA_PATH)
        if not chroma_path.exists():
            return None

        dest = backup_dir / "chroma"
        shutil.copytree(chroma_path, dest)
        return str(dest)
    except ImportError:
        return None
    except Exception as e:
        print(f"ChromaDB backup failed: {e}", file=sys.stderr)
        return None


def export_papers(backup_dir: Path) -> Optional[str]:
    """Export all papers to JSON."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper, Author, Tag

        with get_session() as session:
            papers = session.query(Paper).all()

            export_data = []
            for paper in papers:
                paper_dict = {
                    "id": paper.id,
                    "title": paper.title,
                    "abstract": paper.abstract,
                    "year": paper.year,
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                    "journal": paper.journal,
                    "read_status": paper.read_status,
                    "rating": paper.rating,
                    "pdf_path": paper.pdf_path,
                    "authors": [a.name for a in paper.authors],
                    "tags": [t.name for t in paper.tags],
                    "created_at": paper.created_at.isoformat() if paper.created_at else None,
                    "updated_at": paper.updated_at.isoformat() if paper.updated_at else None,
                }
                export_data.append(paper_dict)

        dest = backup_dir / "papers_export.json"
        with open(dest, "w") as f:
            json.dump(export_data, f, indent=2)

        return str(dest)
    except Exception as e:
        print(f"Paper export failed: {e}", file=sys.stderr)
        return None


def get_directory_size(path: Path) -> float:
    """Get total size of directory in MB."""
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total / (1024 * 1024)


def list_backups(output_dir: str) -> List[dict]:
    """List existing backups."""
    backups = []
    output_path = Path(output_dir)

    if not output_path.exists():
        return backups

    for item in output_path.iterdir():
        if item.is_dir() and item.name.startswith("literature_backup_"):
            # Parse timestamp from name
            try:
                timestamp_str = item.name.replace("literature_backup_", "")
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                size_mb = get_directory_size(item)

                backups.append({
                    "name": item.name,
                    "path": str(item),
                    "timestamp": timestamp.isoformat(),
                    "size_mb": round(size_mb, 2)
                })
            except ValueError:
                continue

    return sorted(backups, key=lambda x: x["timestamp"], reverse=True)


def cleanup_old_backups(output_dir: str, keep: int = 5):
    """Remove old backups, keeping the most recent N."""
    backups = list_backups(output_dir)

    if len(backups) <= keep:
        return 0

    removed = 0
    for backup in backups[keep:]:
        try:
            shutil.rmtree(backup["path"])
            removed += 1
        except Exception as e:
            print(f"Failed to remove {backup['name']}: {e}", file=sys.stderr)

    return removed


def run_backup(
    output_dir: str,
    include_pdfs: bool = False,
    include_chroma: bool = True,
    compress: bool = False,
    verbose: bool = False
) -> BackupResult:
    """Run backup operation."""
    import time
    start_time = time.time()

    errors = []
    backup_dir = get_backup_dir(output_dir)

    if verbose:
        print(f"Creating backup in {backup_dir}", file=sys.stderr)

    # Backup database
    if verbose:
        print("  Backing up database...", file=sys.stderr)
    db_backup = backup_database(backup_dir)
    if not db_backup:
        errors.append("Database backup failed or not found")

    # Backup PDFs (optional)
    pdf_backup = None
    if include_pdfs:
        if verbose:
            print("  Backing up PDFs...", file=sys.stderr)
        pdf_backup = backup_pdfs(backup_dir, compress=compress)
        if not pdf_backup:
            errors.append("PDF backup failed or not found")

    # Backup ChromaDB
    chroma_backup = None
    if include_chroma:
        if verbose:
            print("  Backing up ChromaDB...", file=sys.stderr)
        chroma_backup = backup_chroma(backup_dir)
        # Don't treat missing chroma as error - might not be initialized

    # Export papers
    if verbose:
        print("  Exporting papers...", file=sys.stderr)
    export_backup = export_papers(backup_dir)
    if not export_backup:
        errors.append("Paper export failed")

    # Calculate total size
    total_size = get_directory_size(backup_dir)

    # Compress entire backup if requested
    if compress and not include_pdfs:  # PDFs already compressed separately
        if verbose:
            print("  Compressing backup...", file=sys.stderr)
        archive_path = backup_dir.parent / f"{backup_dir.name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(backup_dir, arcname=backup_dir.name)
        shutil.rmtree(backup_dir)
        backup_dir = archive_path

    duration = time.time() - start_time

    return BackupResult(
        timestamp=datetime.now().isoformat(),
        backup_dir=str(backup_dir),
        database_backup=db_backup,
        pdf_backup=pdf_backup,
        chroma_backup=chroma_backup,
        export_backup=export_backup,
        total_size_mb=round(total_size, 2),
        errors=errors,
        duration_seconds=round(duration, 2)
    )


def print_result(result: BackupResult, json_output: bool = False):
    """Print backup result."""
    if json_output:
        print(json.dumps(asdict(result), indent=2))
        return

    print(f"\n{'='*60}")
    print("Literature Backup Complete")
    print(f"Timestamp: {result.timestamp}")
    print(f"{'='*60}\n")

    print(f"Backup location: {result.backup_dir}")
    print(f"Total size: {result.total_size_mb} MB")
    print(f"Duration: {result.duration_seconds}s\n")

    print("Components:")
    if result.database_backup:
        print(f"  ✓ Database: {result.database_backup}")
    else:
        print("  ✗ Database: Not backed up")

    if result.pdf_backup:
        print(f"  ✓ PDFs: {result.pdf_backup}")
    else:
        print("  - PDFs: Not included")

    if result.chroma_backup:
        print(f"  ✓ ChromaDB: {result.chroma_backup}")
    else:
        print("  - ChromaDB: Not found or not backed up")

    if result.export_backup:
        print(f"  ✓ Export: {result.export_backup}")
    else:
        print("  ✗ Export: Failed")

    if result.errors:
        print(f"\n{len(result.errors)} issues:")
        for error in result.errors:
            print(f"  - {error}")

    print()


def print_backups(backups: List[dict], json_output: bool = False):
    """Print list of backups."""
    if json_output:
        print(json.dumps(backups, indent=2))
        return

    if not backups:
        print("No backups found.")
        return

    print(f"\n{'='*60}")
    print("Existing Backups")
    print(f"{'='*60}\n")

    for backup in backups:
        print(f"  {backup['name']}")
        print(f"    Created: {backup['timestamp']}")
        print(f"    Size: {backup['size_mb']} MB")
        print(f"    Path: {backup['path']}")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backup Literature MCP Server data"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./backups",
        help="Directory to store backups"
    )
    parser.add_argument(
        "--include-pdfs",
        action="store_true",
        help="Include PDF files in backup"
    )
    parser.add_argument(
        "--no-chroma",
        action="store_true",
        help="Exclude ChromaDB from backup"
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress backup to tar.gz"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List existing backups"
    )
    parser.add_argument(
        "--cleanup",
        type=int,
        metavar="N",
        help="Remove old backups, keeping the most recent N"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    args = parser.parse_args()

    # List backups
    if args.list:
        backups = list_backups(args.output_dir)
        print_backups(backups, json_output=args.json)
        sys.exit(0)

    # Cleanup old backups
    if args.cleanup:
        removed = cleanup_old_backups(args.output_dir, keep=args.cleanup)
        if args.json:
            print(json.dumps({"removed": removed}))
        else:
            print(f"Removed {removed} old backup(s)")
        sys.exit(0)

    # Run backup
    result = run_backup(
        output_dir=args.output_dir,
        include_pdfs=args.include_pdfs,
        include_chroma=not args.no_chroma,
        compress=args.compress,
        verbose=args.verbose
    )

    print_result(result, json_output=args.json)

    if result.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
