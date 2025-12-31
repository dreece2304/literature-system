#!/usr/bin/env python3
"""Combined maintenance runner for Literature MCP Server.

Runs all maintenance tasks in sequence:
- Health check
- Integrity check
- Reindex (optional)
- Backup (optional)

Usage:
    python -m scripts.maintenance              # Run health + integrity checks
    python -m scripts.maintenance --all        # Run all maintenance tasks
    python -m scripts.maintenance --reindex    # Include reindexing
    python -m scripts.maintenance --backup     # Include backup
    python -m scripts.maintenance --fix        # Auto-fix issues
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
class MaintenanceReport:
    """Complete maintenance report."""
    timestamp: str
    overall_status: str
    tasks_run: List[str]
    health_report: Optional[dict]
    integrity_report: Optional[dict]
    reindex_report: Optional[dict]
    backup_report: Optional[dict]
    duration_seconds: float
    summary: dict


def run_health_check(verbose: bool = False) -> dict:
    """Run health check and return report."""
    try:
        from scripts.health_check import run_health_check as health_check
        report = health_check(verbose=verbose)
        return asdict(report)
    except Exception as e:
        return {
            "overall_status": "error",
            "error": str(e)
        }


def run_integrity_check(fix: bool = False, verbose: bool = False) -> dict:
    """Run integrity check and return report."""
    try:
        from scripts.integrity_check import run_integrity_check as integrity_check
        report = integrity_check(fix=fix, verbose=verbose)
        return asdict(report)
    except Exception as e:
        return {
            "issues_found": -1,
            "error": str(e)
        }


def run_reindex(mode: str = "incremental", verbose: bool = False) -> dict:
    """Run reindexing and return report."""
    try:
        from scripts.reindex import run_reindex as reindex
        result = reindex(mode=mode, verbose=verbose)
        return asdict(result)
    except Exception as e:
        return {
            "papers_processed": 0,
            "error": str(e)
        }


def run_backup(output_dir: str, verbose: bool = False) -> dict:
    """Run backup and return report."""
    try:
        from scripts.backup import run_backup as backup
        result = backup(
            output_dir=output_dir,
            include_pdfs=False,
            include_chroma=True,
            compress=False,
            verbose=verbose
        )
        return asdict(result)
    except Exception as e:
        return {
            "backup_dir": None,
            "error": str(e)
        }


def run_maintenance(
    run_reindex: bool = False,
    run_backup_task: bool = False,
    backup_dir: str = "./backups",
    reindex_mode: str = "incremental",
    fix_issues: bool = False,
    verbose: bool = False
) -> MaintenanceReport:
    """Run all maintenance tasks."""
    import time
    start_time = time.time()

    tasks_run = []
    health_report = None
    integrity_report = None
    reindex_report = None
    backup_report = None

    # Always run health check
    if verbose:
        print("Running health check...", file=sys.stderr)
    health_report = run_health_check(verbose=verbose)
    tasks_run.append("health_check")

    # Always run integrity check
    if verbose:
        print("Running integrity check...", file=sys.stderr)
    integrity_report = run_integrity_check(fix=fix_issues, verbose=verbose)
    tasks_run.append("integrity_check")

    # Optional: reindex
    if run_reindex:
        if verbose:
            print(f"Running reindex ({reindex_mode})...", file=sys.stderr)
        reindex_report = run_reindex(mode=reindex_mode, verbose=verbose)
        tasks_run.append("reindex")

    # Optional: backup
    if run_backup_task:
        if verbose:
            print("Running backup...", file=sys.stderr)
        backup_report = run_backup(output_dir=backup_dir, verbose=verbose)
        tasks_run.append("backup")

    # Determine overall status
    statuses = []
    if health_report:
        statuses.append(health_report.get("overall_status", "unknown"))
    if integrity_report:
        if integrity_report.get("error"):
            statuses.append("error")
        elif integrity_report.get("summary", {}).get("errors", 0) > 0:
            statuses.append("error")
        elif integrity_report.get("summary", {}).get("warnings", 0) > 0:
            statuses.append("warning")
        else:
            statuses.append("ok")

    if "error" in statuses:
        overall_status = "error"
    elif "warning" in statuses:
        overall_status = "warning"
    else:
        overall_status = "ok"

    # Build summary
    summary = {
        "tasks_completed": len(tasks_run),
        "health_status": health_report.get("overall_status") if health_report else None,
        "integrity_issues": integrity_report.get("issues_found", 0) if integrity_report else None,
        "integrity_fixed": integrity_report.get("issues_fixed", 0) if integrity_report else None,
        "papers_reindexed": reindex_report.get("papers_processed", 0) if reindex_report else None,
        "backup_size_mb": backup_report.get("total_size_mb") if backup_report else None,
    }

    duration = time.time() - start_time

    return MaintenanceReport(
        timestamp=datetime.now().isoformat(),
        overall_status=overall_status,
        tasks_run=tasks_run,
        health_report=health_report,
        integrity_report=integrity_report,
        reindex_report=reindex_report,
        backup_report=backup_report,
        duration_seconds=round(duration, 2),
        summary=summary
    )


def print_report(report: MaintenanceReport, json_output: bool = False):
    """Print maintenance report."""
    if json_output:
        print(json.dumps(asdict(report), indent=2))
        return

    status_colors = {
        "ok": "\033[92m",
        "warning": "\033[93m",
        "error": "\033[91m"
    }
    reset = "\033[0m"

    print(f"\n{'='*60}")
    print("Literature MCP Server Maintenance Report")
    print(f"Timestamp: {report.timestamp}")
    print(f"{'='*60}\n")

    # Overall status
    color = status_colors.get(report.overall_status, "")
    print(f"Overall Status: {color}{report.overall_status.upper()}{reset}")
    print(f"Tasks Run: {', '.join(report.tasks_run)}")
    print(f"Duration: {report.duration_seconds}s\n")

    # Health check results
    if report.health_report:
        print(f"{'-'*40}")
        print("HEALTH CHECK")
        print(f"{'-'*40}")
        health_status = report.health_report.get("overall_status", "unknown")
        color = status_colors.get(health_status, "")
        print(f"Status: {color}{health_status.upper()}{reset}")

        if "components" in report.health_report:
            for comp in report.health_report["components"]:
                comp_color = status_colors.get(comp["status"], "")
                print(f"  {comp_color}•{reset} {comp['name']}: {comp['message']}")
        print()

    # Integrity check results
    if report.integrity_report:
        print(f"{'-'*40}")
        print("INTEGRITY CHECK")
        print(f"{'-'*40}")

        if report.integrity_report.get("error"):
            print(f"Error: {report.integrity_report['error']}")
        else:
            issues = report.integrity_report.get("issues_found", 0)
            fixed = report.integrity_report.get("issues_fixed", 0)
            print(f"Issues Found: {issues}")
            if fixed > 0:
                print(f"Issues Fixed: {fixed}")

            summary = report.integrity_report.get("summary", {})
            if summary:
                print(f"  Errors: {summary.get('errors', 0)}")
                print(f"  Warnings: {summary.get('warnings', 0)}")
                print(f"  Info: {summary.get('info', 0)}")
        print()

    # Reindex results
    if report.reindex_report:
        print(f"{'-'*40}")
        print("REINDEX")
        print(f"{'-'*40}")

        if report.reindex_report.get("error"):
            print(f"Error: {report.reindex_report['error']}")
        else:
            print(f"Papers Processed: {report.reindex_report.get('papers_processed', 0)}")
            print(f"Embeddings Created: {report.reindex_report.get('embeddings_created', 0)}")
            print(f"Chunks Processed: {report.reindex_report.get('chunks_processed', 0)}")
        print()

    # Backup results
    if report.backup_report:
        print(f"{'-'*40}")
        print("BACKUP")
        print(f"{'-'*40}")

        if report.backup_report.get("error"):
            print(f"Error: {report.backup_report['error']}")
        else:
            print(f"Location: {report.backup_report.get('backup_dir', 'N/A')}")
            print(f"Size: {report.backup_report.get('total_size_mb', 0)} MB")
        print()

    # Summary
    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for key, value in report.summary.items():
        if value is not None:
            print(f"  {key}: {value}")
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run maintenance tasks for Literature MCP Server"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all maintenance tasks"
    )
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Include reindexing task"
    )
    parser.add_argument(
        "--reindex-mode",
        choices=["full", "incremental"],
        default="incremental",
        help="Reindex mode (default: incremental)"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Include backup task"
    )
    parser.add_argument(
        "--backup-dir",
        default="./backups",
        help="Backup output directory"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix integrity issues"
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

    # Determine which tasks to run
    do_reindex = args.all or args.reindex
    do_backup = args.all or args.backup

    report = run_maintenance(
        run_reindex=do_reindex,
        run_backup_task=do_backup,
        backup_dir=args.backup_dir,
        reindex_mode=args.reindex_mode,
        fix_issues=args.fix,
        verbose=args.verbose
    )

    print_report(report, json_output=args.json)

    # Exit code based on status
    if report.overall_status == "error":
        sys.exit(2)
    elif report.overall_status == "warning":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
