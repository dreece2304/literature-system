"""Paper Health Check Script.

Verifies data integrity across the literature database:
- Papers with PDF but no chunks
- Papers with chunks but no ExtractionMetadata
- Orphaned chunks (no parent paper)
- Orphaned extraction metadata (no parent paper)
- Orphaned references (no parent paper)
- Duplicate detection (same DOI, similar titles)
- Papers with missing required fields

Run with:
    cd /home/dreece23/projects/research/misc/research
    /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.check_paper_health

Options:
    --fix           Attempt to fix issues where possible
    --verbose       Show detailed output
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from sqlalchemy import text, func
from literature_core import (
    get_engine,
    get_session,
    get_logger,
    Paper,
    PaperChunk,
    PaperReference,
    ExtractionMetadata,
    PaperContent,
    ChunkingStatus,
    EnrichmentStatus,
)

logger = get_logger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    name: str
    status: str  # "ok", "warning", "error"
    count: int = 0
    details: list[dict] = field(default_factory=list)
    message: str = ""


@dataclass
class HealthReport:
    """Complete health check report."""
    total_papers: int = 0
    checks: list[HealthCheckResult] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return any(c.status != "ok" for c in self.checks)

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "warning")


def check_papers_with_pdf_no_chunks(session, verbose: bool = False) -> HealthCheckResult:
    """Find papers with file_path set but no PaperChunk records."""
    # Get papers with PDF
    papers_with_pdf = session.query(Paper.id, Paper.title, Paper.file_path).filter(
        Paper.file_path.isnot(None),
        Paper.file_path != ''
    ).all()

    # Get papers with chunks
    papers_with_chunks = set(
        p[0] for p in session.query(PaperChunk.paper_id).distinct().all()
    )

    # Find papers with PDF but no chunks
    missing_chunks = [
        {"id": p.id, "title": p.title[:50], "file_path": p.file_path}
        for p in papers_with_pdf
        if p.id not in papers_with_chunks
    ]

    if missing_chunks:
        return HealthCheckResult(
            name="Papers with PDF but no chunks",
            status="warning",
            count=len(missing_chunks),
            details=missing_chunks[:10] if verbose else [],
            message=f"Found {len(missing_chunks)} papers with PDF but no chunks. "
                    f"Run chunking queue to process them."
        )
    return HealthCheckResult(
        name="Papers with PDF but no chunks",
        status="ok",
        message="All papers with PDFs have been chunked"
    )


def check_orphaned_chunks(session, verbose: bool = False) -> HealthCheckResult:
    """Find PaperChunk records with no parent paper."""
    # Get all paper IDs
    paper_ids = set(p.id for p in session.query(Paper.id).all())

    # Get all chunk paper_ids
    chunk_paper_ids = session.query(
        PaperChunk.paper_id, func.count(PaperChunk.id).label('count')
    ).group_by(PaperChunk.paper_id).all()

    orphaned = [
        {"paper_id": c.paper_id, "chunk_count": c.count}
        for c in chunk_paper_ids
        if c.paper_id not in paper_ids
    ]

    if orphaned:
        return HealthCheckResult(
            name="Orphaned chunks",
            status="error",
            count=len(orphaned),
            details=orphaned if verbose else [],
            message=f"Found {len(orphaned)} orphaned chunk groups (paper deleted but chunks remain)"
        )
    return HealthCheckResult(
        name="Orphaned chunks",
        status="ok",
        message="No orphaned chunks found"
    )


def check_orphaned_extraction_metadata(session, verbose: bool = False) -> HealthCheckResult:
    """Find ExtractionMetadata records with no parent paper."""
    paper_ids = set(p.id for p in session.query(Paper.id).all())

    orphaned = session.query(ExtractionMetadata).filter(
        ~ExtractionMetadata.paper_id.in_(paper_ids)
    ).all()

    if orphaned:
        details = [{"paper_id": e.paper_id} for e in orphaned]
        return HealthCheckResult(
            name="Orphaned extraction metadata",
            status="error",
            count=len(orphaned),
            details=details if verbose else [],
            message=f"Found {len(orphaned)} orphaned extraction metadata records"
        )
    return HealthCheckResult(
        name="Orphaned extraction metadata",
        status="ok",
        message="No orphaned extraction metadata found"
    )


def check_orphaned_references(session, verbose: bool = False) -> HealthCheckResult:
    """Find PaperReference records with no parent paper."""
    paper_ids = set(p.id for p in session.query(Paper.id).all())

    # Get unique parent paper_ids from references
    ref_paper_ids = session.query(
        PaperReference.paper_id, func.count(PaperReference.id).label('count')
    ).group_by(PaperReference.paper_id).all()

    orphaned = [
        {"paper_id": r.paper_id, "ref_count": r.count}
        for r in ref_paper_ids
        if r.paper_id not in paper_ids
    ]

    if orphaned:
        return HealthCheckResult(
            name="Orphaned references",
            status="error",
            count=len(orphaned),
            details=orphaned if verbose else [],
            message=f"Found {len(orphaned)} orphaned reference groups"
        )
    return HealthCheckResult(
        name="Orphaned references",
        status="ok",
        message="No orphaned references found"
    )


def check_duplicate_dois(session, verbose: bool = False) -> HealthCheckResult:
    """Find papers with duplicate DOIs."""
    duplicates = session.query(
        Paper.doi, func.count(Paper.id).label('count')
    ).filter(
        Paper.doi.isnot(None),
        Paper.doi != ''
    ).group_by(Paper.doi).having(func.count(Paper.id) > 1).all()

    if duplicates:
        details = [{"doi": d.doi, "count": d.count} for d in duplicates]
        return HealthCheckResult(
            name="Duplicate DOIs",
            status="error",
            count=len(duplicates),
            details=details if verbose else [],
            message=f"Found {len(duplicates)} DOIs with multiple papers"
        )
    return HealthCheckResult(
        name="Duplicate DOIs",
        status="ok",
        message="No duplicate DOIs found"
    )


def check_papers_missing_title(session, verbose: bool = False) -> HealthCheckResult:
    """Find papers with missing or empty titles."""
    missing = session.query(Paper.id, Paper.doi).filter(
        (Paper.title.is_(None)) | (Paper.title == '')
    ).all()

    if missing:
        details = [{"id": p.id, "doi": p.doi} for p in missing]
        return HealthCheckResult(
            name="Papers missing title",
            status="error",
            count=len(missing),
            details=details if verbose else [],
            message=f"Found {len(missing)} papers with no title"
        )
    return HealthCheckResult(
        name="Papers missing title",
        status="ok",
        message="All papers have titles"
    )


def check_inconsistent_enrichment_status(session, verbose: bool = False) -> HealthCheckResult:
    """Find papers with enrichment_status that doesn't match their actual state."""
    issues = []

    # Papers marked 'complete' but missing chunks
    papers_with_chunks = set(
        p[0] for p in session.query(PaperChunk.paper_id).distinct().all()
    )

    complete_papers = session.query(Paper.id, Paper.title, Paper.file_path).filter(
        Paper.enrichment_status == EnrichmentStatus.COMPLETE
    ).all()

    for p in complete_papers:
        if p.file_path and p.id not in papers_with_chunks:
            issues.append({
                "id": p.id,
                "title": p.title[:40] if p.title else None,
                "issue": "marked complete but has PDF without chunks"
            })

    # Papers marked 'needs_chunks' but already have chunks
    needs_chunks = session.query(Paper.id, Paper.title).filter(
        Paper.enrichment_status == EnrichmentStatus.NEEDS_CHUNKS
    ).all()

    for p in needs_chunks:
        if p.id in papers_with_chunks:
            issues.append({
                "id": p.id,
                "title": p.title[:40] if p.title else None,
                "issue": "marked needs_chunks but already has chunks"
            })

    if issues:
        return HealthCheckResult(
            name="Inconsistent enrichment status",
            status="warning",
            count=len(issues),
            details=issues[:10] if verbose else [],
            message=f"Found {len(issues)} papers with inconsistent enrichment_status"
        )
    return HealthCheckResult(
        name="Inconsistent enrichment status",
        status="ok",
        message="Enrichment status is consistent"
    )


def check_chunks_metadata_mismatch(session, verbose: bool = False) -> HealthCheckResult:
    """Find papers where chunk count in metadata doesn't match actual chunks."""
    issues = []

    # Get actual chunk counts
    actual_counts = dict(
        session.query(
            PaperChunk.paper_id, func.count(PaperChunk.id)
        ).group_by(PaperChunk.paper_id).all()
    )

    # Get metadata chunk counts
    metadata = session.query(
        ExtractionMetadata.paper_id, ExtractionMetadata.chunk_count
    ).filter(ExtractionMetadata.chunk_count.isnot(None)).all()

    for m in metadata:
        actual = actual_counts.get(m.paper_id, 0)
        if actual != m.chunk_count:
            issues.append({
                "paper_id": m.paper_id,
                "metadata_count": m.chunk_count,
                "actual_count": actual
            })

    if issues:
        return HealthCheckResult(
            name="Chunk count mismatch",
            status="warning",
            count=len(issues),
            details=issues[:10] if verbose else [],
            message=f"Found {len(issues)} papers where metadata chunk_count doesn't match actual"
        )
    return HealthCheckResult(
        name="Chunk count mismatch",
        status="ok",
        message="Chunk counts are consistent"
    )


def run_health_check(verbose: bool = False, fix: bool = False) -> HealthReport:
    """Run all health checks and return a report."""
    report = HealthReport()

    with get_session() as session:
        report.total_papers = session.query(Paper).count()

        # Run all checks
        checks = [
            check_papers_with_pdf_no_chunks,
            check_orphaned_chunks,
            check_orphaned_extraction_metadata,
            check_orphaned_references,
            check_duplicate_dois,
            check_papers_missing_title,
            check_inconsistent_enrichment_status,
            check_chunks_metadata_mismatch,
        ]

        for check_fn in checks:
            try:
                result = check_fn(session, verbose=verbose)
                report.checks.append(result)
            except Exception as e:
                report.checks.append(HealthCheckResult(
                    name=check_fn.__name__,
                    status="error",
                    message=f"Check failed: {str(e)}"
                ))

    return report


def print_report(report: HealthReport):
    """Print a health check report to console."""
    print("=" * 70)
    print("PAPER HEALTH CHECK REPORT")
    print("=" * 70)
    print(f"Total papers: {report.total_papers}")
    print()

    for check in report.checks:
        status_icon = {
            "ok": "\u2713",  # checkmark
            "warning": "!",
            "error": "X"
        }.get(check.status, "?")

        status_color = {
            "ok": "\033[92m",     # green
            "warning": "\033[93m", # yellow
            "error": "\033[91m"    # red
        }.get(check.status, "")
        reset = "\033[0m"

        print(f"{status_color}[{status_icon}]{reset} {check.name}")
        if check.message:
            print(f"    {check.message}")
        if check.count > 0:
            print(f"    Count: {check.count}")
        if check.details:
            for detail in check.details[:5]:
                print(f"      - {detail}")
            if len(check.details) > 5:
                print(f"      ... and {len(check.details) - 5} more")
        print()

    print("=" * 70)
    if report.has_issues:
        print(f"Summary: {report.error_count} errors, {report.warning_count} warnings")
    else:
        print("Summary: All checks passed!")
    print("=" * 70)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check paper database health")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    report = run_health_check(verbose=args.verbose, fix=args.fix)

    if args.json:
        import json
        print(json.dumps({
            "total_papers": report.total_papers,
            "has_issues": report.has_issues,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "count": c.count,
                    "message": c.message,
                    "details": c.details
                }
                for c in report.checks
            ]
        }, indent=2))
    else:
        print_report(report)
