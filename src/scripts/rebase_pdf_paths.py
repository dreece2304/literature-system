"""Rebase papers.file_path after moving the project to a new machine.

file_path is stored absolute, so cloning the repo and restoring data/pdfs on
another machine leaves every paper pointing at the old machine's filesystem.
All managed PDFs live flat in data/pdfs, so rebasing is basename mapping:
each paper whose stored path does not resolve is repointed to
<pdf_storage_path>/<basename> when that file exists.

Usage (dry-run by default; run on the NEW machine after restoring data/):
    cd src && mamba run -n litai python -m scripts.rebase_pdf_paths
    cd src && mamba run -n litai python -m scripts.rebase_pdf_paths --execute
"""
from __future__ import annotations

import argparse
from pathlib import Path, PureWindowsPath


def _basename(file_path: str) -> str:
    """Basename that also survives Windows-style stored paths."""
    if "\\" in file_path:
        return PureWindowsPath(file_path).name
    return Path(file_path).name


def plan_rebase(papers: list[dict], storage_root: Path) -> list[dict]:
    """Plan repointing stale absolute file_paths into storage_root.

    papers is a list of {"id": int, "file_path": str | None}. Papers whose
    stored path still resolves are skipped; the rest get action "rebase"
    when <storage_root>/<basename> exists, else "missing".
    """
    storage_root = Path(storage_root)
    plan = []
    for paper in papers:
        file_path = paper.get("file_path")
        if not file_path:
            continue
        if Path(file_path).is_file():
            continue
        candidate = storage_root / _basename(file_path)
        if candidate.is_file():
            plan.append({
                "paper_id": paper["id"],
                "old_path": file_path,
                "new_path": str(candidate.resolve()),
                "action": "rebase",
            })
        else:
            plan.append({
                "paper_id": paper["id"],
                "old_path": file_path,
                "action": "missing",
            })
    return plan


def run(execute: bool) -> dict:
    """Plan (and optionally apply) the rebase against the live DB."""
    from literature_core import get_logger
    from literature_core.config import settings
    from literature_core.database import get_session
    from literature_core.models import Paper

    logger = get_logger(__name__)

    with get_session() as session:
        rows = session.query(Paper.id, Paper.file_path).all()
    papers = [{"id": r.id, "file_path": r.file_path} for r in rows]

    plan = plan_rebase(papers, storage_root=settings.pdf_storage_path)
    rebases = [p for p in plan if p["action"] == "rebase"]
    missing = [p for p in plan if p["action"] == "missing"]

    if execute and rebases:
        with get_session() as session:
            for item in rebases:
                paper = session.query(Paper).filter(
                    Paper.id == item["paper_id"]).first()
                paper.file_path = item["new_path"]
        logger.info(f"Rebased {len(rebases)} paper file paths")

    return {"executed": execute, "rebased": len(rebases),
            "missing": missing, "unchanged": len(papers) - len(plan)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true",
                        help="Apply changes (default is dry-run)")
    args = parser.parse_args()

    result = run(args.execute)
    mode = "EXECUTED" if args.execute else "DRY RUN"
    print(f"{mode}: {result['rebased']} to rebase, "
          f"{len(result['missing'])} missing, {result['unchanged']} already fine")
    for item in result["missing"][:20]:
        print(f"  missing: paper {item['paper_id']}: {item['old_path']}")


if __name__ == "__main__":
    main()
