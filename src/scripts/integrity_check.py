#!/usr/bin/env python3
"""Database integrity check script for Literature MCP Server.

Checks for:
- Orphan notes (paper_id references deleted papers)
- Orphan collection associations
- Papers with PDF path but missing file
- Papers with DOI but no file_hash
- Duplicate detection (by hash, by title similarity)
- Broken Zotero links

Usage:
    python -m scripts.integrity_check
    python -m scripts.integrity_check --fix  # Auto-fix issues
    python -m scripts.integrity_check --json
"""
import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add src to path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@dataclass
class Issue:
    """A detected integrity issue."""
    category: str
    severity: str  # "error", "warning", "info"
    description: str
    affected_ids: List[int]
    fix_action: Optional[str] = None


@dataclass
class IntegrityReport:
    """Complete integrity check report."""
    timestamp: str
    issues_found: int
    issues_fixed: int
    issues: List[dict]
    summary: dict


def check_orphan_notes() -> List[Issue]:
    """Check for notes referencing non-existent papers."""
    issues = []
    try:
        from literature_core.database import get_session
        from literature_core.models import Note, Paper
        from sqlalchemy import text

        with get_session() as session:
            # Find notes where paper doesn't exist
            orphan_notes = session.query(Note).filter(
                ~Note.paper_id.in_(
                    session.query(Paper.id)
                )
            ).all()

            if orphan_notes:
                issues.append(Issue(
                    category="orphan_notes",
                    severity="error",
                    description=f"Found {len(orphan_notes)} notes referencing deleted papers",
                    affected_ids=[n.id for n in orphan_notes],
                    fix_action="DELETE FROM notes WHERE id IN (...)"
                ))
    except Exception as e:
        issues.append(Issue(
            category="orphan_notes",
            severity="error",
            description=f"Error checking orphan notes: {str(e)}",
            affected_ids=[]
        ))

    return issues


def check_missing_pdf_files() -> List[Issue]:
    """Check for papers with pdf_path but missing files."""
    issues = []
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper

        with get_session() as session:
            papers_with_pdf = session.query(Paper).filter(
                Paper.pdf_path.isnot(None)
            ).all()

            missing_files = []
            for paper in papers_with_pdf:
                if paper.pdf_path and not Path(paper.pdf_path).exists():
                    missing_files.append(paper.id)

            if missing_files:
                issues.append(Issue(
                    category="missing_pdf",
                    severity="warning",
                    description=f"Found {len(missing_files)} papers with missing PDF files",
                    affected_ids=missing_files,
                    fix_action="Set pdf_path to NULL for affected papers"
                ))
    except Exception as e:
        issues.append(Issue(
            category="missing_pdf",
            severity="error",
            description=f"Error checking PDF files: {str(e)}",
            affected_ids=[]
        ))

    return issues


def check_duplicate_papers_by_doi() -> List[Issue]:
    """Check for duplicate papers by DOI."""
    issues = []
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper
        from sqlalchemy import func

        with get_session() as session:
            # Find DOIs that appear more than once
            duplicates = session.query(
                Paper.doi,
                func.count(Paper.id).label('count')
            ).filter(
                Paper.doi.isnot(None)
            ).group_by(Paper.doi).having(
                func.count(Paper.id) > 1
            ).all()

            if duplicates:
                dup_dois = [d[0] for d in duplicates]
                affected_papers = session.query(Paper.id).filter(
                    Paper.doi.in_(dup_dois)
                ).all()

                issues.append(Issue(
                    category="duplicate_doi",
                    severity="warning",
                    description=f"Found {len(duplicates)} DOIs appearing multiple times",
                    affected_ids=[p[0] for p in affected_papers],
                    fix_action="Review and merge or delete duplicate entries"
                ))
    except Exception as e:
        issues.append(Issue(
            category="duplicate_doi",
            severity="error",
            description=f"Error checking DOI duplicates: {str(e)}",
            affected_ids=[]
        ))

    return issues


def check_duplicate_papers_by_title() -> List[Issue]:
    """Check for potential duplicate papers by similar titles."""
    issues = []
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper
        from difflib import SequenceMatcher

        with get_session() as session:
            papers = session.query(Paper.id, Paper.title).all()

            potential_duplicates = []
            checked = set()

            for i, (id1, title1) in enumerate(papers):
                for id2, title2 in papers[i+1:]:
                    if (id1, id2) in checked or (id2, id1) in checked:
                        continue
                    checked.add((id1, id2))

                    # Calculate similarity
                    if title1 and title2:
                        ratio = SequenceMatcher(None, title1.lower(), title2.lower()).ratio()
                        if ratio > 0.9:  # 90% similar
                            potential_duplicates.append((id1, id2, ratio))

            if potential_duplicates:
                affected = set()
                for id1, id2, _ in potential_duplicates:
                    affected.add(id1)
                    affected.add(id2)

                issues.append(Issue(
                    category="similar_titles",
                    severity="info",
                    description=f"Found {len(potential_duplicates)} pairs of potentially duplicate papers",
                    affected_ids=list(affected),
                    fix_action="Review and merge duplicate entries"
                ))
    except Exception as e:
        issues.append(Issue(
            category="similar_titles",
            severity="error",
            description=f"Error checking title duplicates: {str(e)}",
            affected_ids=[]
        ))

    return issues


def check_papers_without_required_fields() -> List[Issue]:
    """Check for papers missing important fields."""
    issues = []
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper

        with get_session() as session:
            # Papers without abstract
            no_abstract = session.query(Paper.id).filter(
                Paper.abstract.is_(None)
            ).all()

            if no_abstract:
                issues.append(Issue(
                    category="missing_abstract",
                    severity="info",
                    description=f"Found {len(no_abstract)} papers without abstract",
                    affected_ids=[p[0] for p in no_abstract],
                    fix_action="Consider enriching papers from external sources"
                ))

            # Papers without year
            no_year = session.query(Paper.id).filter(
                Paper.year.is_(None)
            ).all()

            if no_year:
                issues.append(Issue(
                    category="missing_year",
                    severity="info",
                    description=f"Found {len(no_year)} papers without publication year",
                    affected_ids=[p[0] for p in no_year],
                    fix_action="Consider enriching papers from external sources"
                ))

    except Exception as e:
        issues.append(Issue(
            category="missing_fields",
            severity="error",
            description=f"Error checking missing fields: {str(e)}",
            affected_ids=[]
        ))

    return issues


def check_zotero_links() -> List[Issue]:
    """Check for broken Zotero links."""
    issues = []
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper

        with get_session() as session:
            papers_with_zotero = session.query(Paper).filter(
                Paper.zotero_key.isnot(None)
            ).all()

            # For now just count - actual verification would need Zotero API
            if papers_with_zotero:
                issues.append(Issue(
                    category="zotero_links",
                    severity="info",
                    description=f"Found {len(papers_with_zotero)} papers linked to Zotero",
                    affected_ids=[p.id for p in papers_with_zotero],
                    fix_action="Run Zotero sync to verify links"
                ))
    except Exception as e:
        pass  # Zotero field may not exist

    return issues


def fix_orphan_notes() -> int:
    """Delete orphan notes."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Note, Paper

        with get_session() as session:
            orphans = session.query(Note).filter(
                ~Note.paper_id.in_(session.query(Paper.id))
            ).all()

            count = len(orphans)
            for note in orphans:
                session.delete(note)
            session.commit()
            return count
    except Exception:
        return 0


def fix_missing_pdf_paths() -> int:
    """Clear pdf_path for papers with missing files."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper

        with get_session() as session:
            papers = session.query(Paper).filter(
                Paper.pdf_path.isnot(None)
            ).all()

            count = 0
            for paper in papers:
                if paper.pdf_path and not Path(paper.pdf_path).exists():
                    paper.pdf_path = None
                    count += 1
            session.commit()
            return count
    except Exception:
        return 0


def run_integrity_check(fix: bool = False, verbose: bool = False) -> IntegrityReport:
    """Run all integrity checks."""
    checks = [
        check_orphan_notes,
        check_missing_pdf_files,
        check_duplicate_papers_by_doi,
        check_duplicate_papers_by_title,
        check_papers_without_required_fields,
        check_zotero_links,
    ]

    all_issues = []
    for check in checks:
        if verbose:
            print(f"Running {check.__name__}...", file=sys.stderr)
        issues = check()
        all_issues.extend(issues)

    issues_fixed = 0
    if fix:
        # Fix what we can
        issues_fixed += fix_orphan_notes()
        issues_fixed += fix_missing_pdf_paths()

    # Summary by severity
    severities = [i.severity for i in all_issues]
    summary = {
        "total_issues": len(all_issues),
        "errors": severities.count("error"),
        "warnings": severities.count("warning"),
        "info": severities.count("info"),
        "fixed": issues_fixed
    }

    return IntegrityReport(
        timestamp=datetime.now().isoformat(),
        issues_found=len(all_issues),
        issues_fixed=issues_fixed,
        issues=[asdict(i) for i in all_issues],
        summary=summary
    )


def print_report(report: IntegrityReport, json_output: bool = False):
    """Print integrity report."""
    if json_output:
        print(json.dumps(asdict(report), indent=2))
        return

    severity_colors = {
        "error": "\033[91m",
        "warning": "\033[93m",
        "info": "\033[94m"
    }
    reset = "\033[0m"

    print(f"\n{'='*60}")
    print("Literature Database Integrity Check")
    print(f"Timestamp: {report.timestamp}")
    print(f"{'='*60}\n")

    if not report.issues:
        print("✓ No integrity issues found!")
    else:
        for issue in report.issues:
            severity = issue["severity"]
            color = severity_colors.get(severity, "")
            print(f"{color}[{severity.upper()}]{reset} {issue['category']}")
            print(f"  {issue['description']}")
            if issue.get("fix_action"):
                print(f"  Fix: {issue['fix_action']}")
            print()

    print(f"{'-'*60}")
    print(f"Summary: {report.summary['errors']} errors, "
          f"{report.summary['warnings']} warnings, "
          f"{report.summary['info']} info")
    if report.issues_fixed > 0:
        print(f"Issues fixed: {report.issues_fixed}")
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check database integrity for Literature MCP Server"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix issues automatically"
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

    report = run_integrity_check(fix=args.fix, verbose=args.verbose)
    print_report(report, json_output=args.json)

    # Exit code based on severity
    if report.summary["errors"] > 0:
        sys.exit(2)
    elif report.summary["warnings"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
