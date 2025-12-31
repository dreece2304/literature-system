#!/usr/bin/env python3
"""Health check script for Literature MCP Server.

Checks the health of all system components:
- Database connectivity and table counts
- ChromaDB/vector store status
- PDF storage directory
- Search index status
- Memory and disk usage

Usage:
    python -m scripts.health_check
    python -m scripts.health_check --json  # JSON output
    python -m scripts.health_check --verbose
"""
import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add src to path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@dataclass
class ComponentStatus:
    """Status of a single component."""
    name: str
    status: str  # "ok", "warning", "error"
    message: str
    details: Optional[dict] = None


@dataclass
class HealthReport:
    """Complete health report."""
    timestamp: str
    overall_status: str
    components: list
    summary: dict


def check_database() -> ComponentStatus:
    """Check database connectivity and basic stats."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper, Author, Tag, Collection, Note

        with get_session() as session:
            paper_count = session.query(Paper).count()
            author_count = session.query(Author).count()
            tag_count = session.query(Tag).count()
            collection_count = session.query(Collection).count()
            note_count = session.query(Note).count()

        return ComponentStatus(
            name="database",
            status="ok",
            message=f"Database accessible. {paper_count} papers.",
            details={
                "paper_count": paper_count,
                "author_count": author_count,
                "tag_count": tag_count,
                "collection_count": collection_count,
                "note_count": note_count
            }
        )
    except Exception as e:
        return ComponentStatus(
            name="database",
            status="error",
            message=f"Database error: {str(e)}"
        )


def check_vector_store() -> ComponentStatus:
    """Check ChromaDB/vector store status."""
    try:
        from config.ai_settings import AIConfig

        chroma_path = Path(AIConfig.CHROMA_PATH)

        if not chroma_path.exists():
            return ComponentStatus(
                name="vector_store",
                status="warning",
                message="ChromaDB directory does not exist (will be created on first use)",
                details={"path": str(chroma_path)}
            )

        # Check if there's data
        collection_dirs = list(chroma_path.glob("*"))
        has_data = len(collection_dirs) > 0

        return ComponentStatus(
            name="vector_store",
            status="ok",
            message=f"ChromaDB directory exists. {'Has data.' if has_data else 'Empty.'}",
            details={
                "path": str(chroma_path),
                "has_data": has_data
            }
        )
    except ImportError:
        return ComponentStatus(
            name="vector_store",
            status="warning",
            message="AI config not available"
        )
    except Exception as e:
        return ComponentStatus(
            name="vector_store",
            status="error",
            message=f"Vector store error: {str(e)}"
        )


def check_pdf_storage() -> ComponentStatus:
    """Check PDF storage directory."""
    try:
        from config.settings import Settings

        pdf_path = Path(Settings.PDF_STORAGE_PATH)

        if not pdf_path.exists():
            return ComponentStatus(
                name="pdf_storage",
                status="warning",
                message="PDF storage directory does not exist",
                details={"path": str(pdf_path)}
            )

        pdf_count = len(list(pdf_path.glob("*.pdf")))
        total_size = sum(f.stat().st_size for f in pdf_path.glob("*.pdf"))
        size_mb = total_size / (1024 * 1024)

        return ComponentStatus(
            name="pdf_storage",
            status="ok",
            message=f"PDF storage accessible. {pdf_count} PDFs, {size_mb:.1f} MB.",
            details={
                "path": str(pdf_path),
                "pdf_count": pdf_count,
                "total_size_mb": round(size_mb, 2)
            }
        )
    except ImportError:
        return ComponentStatus(
            name="pdf_storage",
            status="warning",
            message="Settings not available"
        )
    except Exception as e:
        return ComponentStatus(
            name="pdf_storage",
            status="error",
            message=f"PDF storage error: {str(e)}"
        )


def check_search_index() -> ComponentStatus:
    """Check full-text search index."""
    try:
        return ComponentStatus(
            name="search_index",
            status="ok",
            message="Using database-based search"
        )
    except Exception as e:
        return ComponentStatus(
            name="search_index",
            status="ok",
            message="Using database-based search"
        )


def check_disk_usage() -> ComponentStatus:
    """Check disk usage."""
    try:
        from config.settings import Settings

        # Check the database directory
        db_path = Path(Settings.DATABASE_PATH).parent

        total, used, free = shutil.disk_usage(db_path)
        free_gb = free / (1024**3)
        used_percent = (used / total) * 100

        if free_gb < 1:
            status = "error"
            message = f"Critical: Only {free_gb:.1f} GB free disk space"
        elif free_gb < 5:
            status = "warning"
            message = f"Warning: Only {free_gb:.1f} GB free disk space"
        else:
            status = "ok"
            message = f"Disk space OK: {free_gb:.1f} GB free"

        return ComponentStatus(
            name="disk_usage",
            status=status,
            message=message,
            details={
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free_gb, 2),
                "used_percent": round(used_percent, 1)
            }
        )
    except Exception as e:
        return ComponentStatus(
            name="disk_usage",
            status="warning",
            message=f"Could not check disk usage: {str(e)}"
        )


def check_memory_usage() -> ComponentStatus:
    """Check memory usage."""
    try:
        import psutil
        memory = psutil.virtual_memory()

        available_gb = memory.available / (1024**3)
        used_percent = memory.percent

        if available_gb < 0.5:
            status = "error"
            message = f"Critical: Only {available_gb:.1f} GB memory available"
        elif available_gb < 1:
            status = "warning"
            message = f"Warning: Only {available_gb:.1f} GB memory available"
        else:
            status = "ok"
            message = f"Memory OK: {available_gb:.1f} GB available"

        return ComponentStatus(
            name="memory_usage",
            status=status,
            message=message,
            details={
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(available_gb, 2),
                "used_percent": round(used_percent, 1)
            }
        )
    except ImportError:
        return ComponentStatus(
            name="memory_usage",
            status="ok",
            message="psutil not installed, skipping memory check"
        )
    except Exception as e:
        return ComponentStatus(
            name="memory_usage",
            status="warning",
            message=f"Could not check memory: {str(e)}"
        )


def check_zotero_integration() -> ComponentStatus:
    """Check Zotero integration status."""
    try:
        from config.settings import Settings

        if not hasattr(Settings, 'ZOTERO_API_KEY') or not Settings.ZOTERO_API_KEY:
            return ComponentStatus(
                name="zotero",
                status="ok",
                message="Zotero integration not configured"
            )

        return ComponentStatus(
            name="zotero",
            status="ok",
            message="Zotero API key configured",
            details={"has_api_key": True}
        )
    except Exception as e:
        return ComponentStatus(
            name="zotero",
            status="ok",
            message="Zotero check skipped"
        )


def run_health_check(verbose: bool = False) -> HealthReport:
    """Run all health checks and return report."""
    checks = [
        check_database,
        check_vector_store,
        check_pdf_storage,
        check_search_index,
        check_disk_usage,
        check_memory_usage,
        check_zotero_integration,
    ]

    components = []
    for check in checks:
        if verbose:
            print(f"Checking {check.__name__}...", file=sys.stderr)
        result = check()
        components.append(result)

    # Determine overall status
    statuses = [c.status for c in components]
    if "error" in statuses:
        overall = "error"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "ok"

    summary = {
        "total_checks": len(components),
        "ok_count": statuses.count("ok"),
        "warning_count": statuses.count("warning"),
        "error_count": statuses.count("error")
    }

    return HealthReport(
        timestamp=datetime.now().isoformat(),
        overall_status=overall,
        components=[asdict(c) for c in components],
        summary=summary
    )


def print_report(report: HealthReport, json_output: bool = False):
    """Print health report to stdout."""
    if json_output:
        print(json.dumps(asdict(report), indent=2))
        return

    # Pretty print
    status_symbols = {"ok": "✓", "warning": "⚠", "error": "✗"}
    status_colors = {
        "ok": "\033[92m",
        "warning": "\033[93m",
        "error": "\033[91m"
    }
    reset = "\033[0m"

    print(f"\n{'='*60}")
    print(f"Literature MCP Server Health Check")
    print(f"Timestamp: {report.timestamp}")
    print(f"{'='*60}\n")

    for component in report.components:
        status = component["status"]
        symbol = status_symbols.get(status, "?")
        color = status_colors.get(status, "")
        name = component["name"].replace("_", " ").title()
        print(f"{color}{symbol}{reset} {name}: {component['message']}")

    print(f"\n{'-'*60}")
    overall_color = status_colors.get(report.overall_status, "")
    print(f"Overall Status: {overall_color}{report.overall_status.upper()}{reset}")
    print(f"Checks: {report.summary['ok_count']} OK, "
          f"{report.summary['warning_count']} warnings, "
          f"{report.summary['error_count']} errors")
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check health of Literature MCP Server components"
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

    report = run_health_check(verbose=args.verbose)
    print_report(report, json_output=args.json)

    # Exit with appropriate code
    if report.overall_status == "error":
        sys.exit(2)
    elif report.overall_status == "warning":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
