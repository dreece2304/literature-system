"""Data integrity audit - one place for every "is the database lying to us" check.

Replaces scripts/integrity_check.py and scripts/paper_health_check.py, which
had drifted into checking overlapping things (both did duplicate DOIs, both
did orphan sweeps) while neither caught the failure mode that actually bit us:
work recorded as complete that silently never happened.

`scripts/health_check.py` is deliberately NOT merged here - it checks
infrastructure (database reachable, vector store up, disk, memory), which is a
different question from whether the stored data is coherent.

Usage:
    cd src && mamba run -n litai python -m scripts.audit
    cd src && mamba run -n litai python -m scripts.audit --json
    cd src && mamba run -n litai python -m scripts.audit --fix
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

from sqlalchemy import bindparam, text

from literature_core import get_logger, get_session

logger = get_logger(__name__)

ERROR, WARN, INFO = "error", "warning", "info"


@dataclass
class Check:
    """One audit question, expressed as a counting query plus an example query."""
    key: str
    severity: str
    description: str
    count_sql: str
    sample_sql: str = ""
    fix_sql: str = ""
    fix_note: str = ""


@dataclass
class Finding:
    key: str
    severity: str
    description: str
    count: int
    samples: list = field(default_factory=list)
    fixable: bool = False


@dataclass
class AuditReport:
    """Findings after the run, plus what --fix repaired (check key -> rows)."""
    findings: list[Finding]
    fixed: dict[str, int] = field(default_factory=dict)


# --- silent-failure checks (the class of bug this module exists for) ----------

SILENT_FAILURE_CHECKS = [
    Check(
        key="empty_extraction_marked_complete",
        severity=ERROR,
        description="extraction_depth='comprehensive' but no summary and no findings",
        count_sql="""
            select count(*) from paper_contents
            where extraction_depth = 'comprehensive'
              and trim(coalesce(deep_one_sentence_summary, one_sentence_summary, '')) = ''
              and (key_findings is null or key_findings in ('', '[]', 'null'))""",
        sample_sql="""
            select paper_id from paper_contents
            where extraction_depth = 'comprehensive'
              and trim(coalesce(deep_one_sentence_summary, one_sentence_summary, '')) = ''
              and (key_findings is null or key_findings in ('', '[]', 'null')) limit 10""",
        fix_sql="""
            update paper_contents set extraction_depth = NULL, deep_extraction_date = NULL
            where extraction_depth = 'comprehensive'
              and trim(coalesce(deep_one_sentence_summary, one_sentence_summary, '')) = ''
              and (key_findings is null or key_findings in ('', '[]', 'null'))""",
        fix_note="requeue for re-extraction",
    ),
    Check(
        key="deep_date_without_any_summary",
        severity=ERROR,
        description="deep_extraction_date set but no summary in either the deep or quick columns",
        # Deliberately NOT flagging rows whose summary sits in the quick
        # columns. Until this was fixed, ExtractionService stamped
        # deep_extraction_date while writing content to the quick columns, so
        # ~203 legacy rows have that layout. Every consumer reads
        # `deep_X or quick_X`, so those rows are legacy, not broken - the
        # harmful case is a deep date with no summary anywhere.
        count_sql="""
            select count(*) from paper_contents
            where deep_extraction_date is not null
              and trim(coalesce(deep_one_sentence_summary, one_sentence_summary, '')) = ''""",
        sample_sql="""
            select paper_id from paper_contents
            where deep_extraction_date is not null
              and trim(coalesce(deep_one_sentence_summary, one_sentence_summary, '')) = '' limit 10""",
    ),
    Check(
        key="chunking_complete_without_chunks",
        severity=ERROR,
        description="chunking_status='complete' but the paper has no chunks",
        count_sql="""
            select count(*) from extraction_metadata em
            where em.chunking_status = 'complete'
              and not exists (select 1 from paper_chunks pc where pc.paper_id = em.paper_id)""",
        sample_sql="""
            select paper_id from extraction_metadata em
            where em.chunking_status = 'complete'
              and not exists (select 1 from paper_chunks pc where pc.paper_id = em.paper_id) limit 10""",
    ),
    Check(
        key="chunk_count_mismatch",
        severity=WARN,
        description="extraction_metadata.chunk_count disagrees with actual chunk rows",
        count_sql="""
            select count(*) from extraction_metadata em where em.chunk_count is not null
              and em.chunk_count != (select count(*) from paper_chunks pc where pc.paper_id = em.paper_id)""",
        sample_sql="""
            select paper_id from extraction_metadata em where em.chunk_count is not null
              and em.chunk_count != (select count(*) from paper_chunks pc where pc.paper_id = em.paper_id)
            limit 10""",
        fix_sql="""
            update extraction_metadata set chunk_count =
              (select count(*) from paper_chunks pc where pc.paper_id = extraction_metadata.paper_id)
            where chunk_count is not null and chunk_count !=
              (select count(*) from paper_chunks pc where pc.paper_id = extraction_metadata.paper_id)""",
        fix_note="recount from paper_chunks",
    ),
    Check(
        key="empty_chunks",
        severity=ERROR,
        description="chunk rows whose content is empty or whitespace",
        count_sql="select count(*) from paper_chunks where trim(coalesce(content, '')) = ''",
        sample_sql="select paper_id from paper_chunks where trim(coalesce(content, '')) = '' limit 10",
    ),
]

# --- structural checks (absorbed from integrity_check + paper_health_check) ---

STRUCTURAL_CHECKS = [
    Check(key="orphan_chunks", severity=ERROR,
          description="chunks whose paper no longer exists",
          count_sql="select count(*) from paper_chunks where paper_id not in (select id from papers)",
          sample_sql="select distinct paper_id from paper_chunks where paper_id not in (select id from papers) limit 10",
          fix_sql="delete from paper_chunks where paper_id not in (select id from papers)",
          fix_note="delete orphans"),
    Check(key="orphan_extraction_metadata", severity=ERROR,
          description="extraction_metadata whose paper no longer exists",
          count_sql="select count(*) from extraction_metadata where paper_id not in (select id from papers)",
          sample_sql="select paper_id from extraction_metadata where paper_id not in (select id from papers) limit 10",
          fix_sql="delete from extraction_metadata where paper_id not in (select id from papers)",
          fix_note="delete orphans"),
    Check(key="orphan_paper_contents", severity=ERROR,
          description="paper_contents whose paper no longer exists",
          count_sql="select count(*) from paper_contents where paper_id not in (select id from papers)",
          sample_sql="select paper_id from paper_contents where paper_id not in (select id from papers) limit 10",
          fix_sql="delete from paper_contents where paper_id not in (select id from papers)",
          fix_note="delete orphans"),
    Check(key="orphan_notes", severity=ERROR,
          description="notes whose paper no longer exists",
          count_sql="select count(*) from notes where paper_id is not null "
                    "and paper_id not in (select id from papers)",
          sample_sql="select id from notes where paper_id is not null "
                     "and paper_id not in (select id from papers) limit 10"),
    Check(key="orphan_references", severity=WARN,
          description="paper_references whose citing paper no longer exists",
          count_sql="select count(*) from paper_references where paper_id not in (select id from papers)",
          sample_sql="select paper_id from paper_references where paper_id not in (select id from papers) limit 10"),
    Check(key="missing_title", severity=ERROR,
          description="papers with no title",
          count_sql="select count(*) from papers where trim(coalesce(title, '')) = ''",
          sample_sql="select id from papers where trim(coalesce(title, '')) = '' limit 10"),
    Check(key="duplicate_doi", severity=WARN,
          description="DOIs shared by more than one paper",
          count_sql="select count(*) from (select doi from papers where trim(coalesce(doi, '')) != '' "
                    "group by lower(doi) having count(*) > 1)",
          sample_sql="select doi from papers where trim(coalesce(doi, '')) != '' "
                     "group by lower(doi) having count(*) > 1 limit 10"),
    Check(key="fts_drift", severity=ERROR,
          description="papers missing from the FTS index",
          count_sql="select count(*) from papers where id not in (select rowid from papers_fts)",
          sample_sql="select id from papers where id not in (select rowid from papers_fts) limit 10",
          fix_note="rebuild with: python -m scripts.migrate_fts5 --rebuild"),
]

ALL_CHECKS = SILENT_FAILURE_CHECKS + STRUCTURAL_CHECKS


OUTAGE_KEY = "verification_written_during_outage"
OUTAGE_FIX_NOTE = "clear outage-written verification"

CLEAR_OUTAGE_SQL = text(
    "update paper_contents set verification = NULL, verification_score = NULL "
    "where paper_id in :ids"
).bindparams(bindparam("ids", expanding=True))


def _outage_victims(session) -> list[int]:
    """Every paper whose verification was written while the NLI verifier was unreachable.

    Not expressible in SQL: the signature is a JSON evidence blob in which
    every claim came back `supported: null`, meaning nothing was actually
    checked and the score describes an outage rather than the extraction.
    Returns the full (uncapped) list so --fix clears all of them.
    """
    rows = session.execute(text(
        "select paper_id, verification from paper_contents where verification is not null")).fetchall()
    victims = []
    for paper_id, blob in rows:
        try:
            payload = json.loads(blob) if isinstance(blob, str) else blob
        except (TypeError, ValueError):
            continue
        claims = ((payload or {}).get("evidence") or {}).get("claims") or []
        if claims and all(c.get("supported") is None for c in claims):
            victims.append(paper_id)
    return victims


def _verification_outage_finding(session) -> Finding:
    victims = _outage_victims(session)
    return Finding(
        key=OUTAGE_KEY, severity=ERROR,
        description="verification scored with every claim unchecked (verifier was down)",
        count=len(victims), samples=victims[:10], fixable=bool(victims))


def _missing_pdf_finding(session) -> Finding:
    """file_path recorded but nothing on disk - only answerable outside SQL."""
    rows = session.execute(text(
        "select id, file_path from papers where trim(coalesce(file_path, '')) != ''")).fetchall()
    missing = [pid for pid, path in rows if not os.path.exists(path)]
    return Finding(
        key="missing_pdf_on_disk", severity=ERROR,
        description="papers whose file_path does not exist on disk",
        count=len(missing), samples=missing[:10],
        fixable=False)


def _collect(session) -> list[Finding]:
    findings: list[Finding] = []
    for check in ALL_CHECKS:
        count = session.execute(text(check.count_sql)).scalar() or 0
        samples = []
        if count and check.sample_sql:
            samples = [r[0] for r in session.execute(text(check.sample_sql)).fetchall()]
        findings.append(Finding(
            key=check.key, severity=check.severity, description=check.description,
            count=count, samples=samples, fixable=bool(check.fix_sql)))
    findings.append(_verification_outage_finding(session))
    findings.append(_missing_pdf_finding(session))
    return findings


def _apply_fixes(session) -> dict[str, int]:
    """Run every fix_sql plus the outage clear; returns rows repaired per check key."""
    fixed: dict[str, int] = {}
    for check in ALL_CHECKS:
        if not check.fix_sql:
            continue
        rows = session.execute(text(check.fix_sql)).rowcount
        if rows:
            fixed[check.key] = rows
            logger.info("audit fix applied", extra={"check": check.key, "rows": rows})
    victims = _outage_victims(session)
    if victims:
        rows = session.execute(CLEAR_OUTAGE_SQL, {"ids": victims}).rowcount
        fixed[OUTAGE_KEY] = rows
        logger.info("audit fix applied", extra={"check": OUTAGE_KEY, "rows": rows})
    return fixed


def run_audit(fix: bool = False) -> AuditReport:
    """Collect findings; with fix=True, repair first and report the post-fix state."""
    with get_session() as session:
        fixed: dict[str, int] = {}
        if fix:
            fixed = _apply_fixes(session)
            session.commit()
        findings = _collect(session)
    return AuditReport(findings=findings, fixed=fixed)


def _fix_note(key: str) -> str:
    if key == OUTAGE_KEY:
        return OUTAGE_FIX_NOTE
    return next((c.fix_note for c in ALL_CHECKS if c.key == key), "")


def print_report(report: AuditReport, json_output: bool = False) -> None:
    findings = report.findings
    if json_output:
        print(json.dumps({"findings": [f.__dict__ for f in findings], "fixed": report.fixed},
                         indent=2, default=str))
        return

    errors = [f for f in findings if f.count and f.severity == ERROR]
    warns = [f for f in findings if f.count and f.severity == WARN]
    clean = [f for f in findings if not f.count]

    print("\n" + "=" * 66)
    print("DATA INTEGRITY AUDIT")
    print("=" * 66)

    if report.fixed:
        print("\nFIXED")
        for key, rows in report.fixed.items():
            print(f"  {rows:>6}  {key} ({_fix_note(key)})")

    for label, group in (("ERRORS", errors), ("WARNINGS", warns)):
        if not group:
            continue
        print(f"\n{label}")
        for f in group:
            flag = "  [--fix]" if f.fixable else ""
            print(f"  {f.count:>6}  {f.description}{flag}")
            if f.samples:
                print(f"          e.g. {', '.join(str(s) for s in f.samples[:8])}")

    print(f"\nCLEAN ({len(clean)} checks passed)")
    for f in clean:
        print(f"     ok  {f.description}")

    print("\n" + "-" * 66)
    print(f"{len(errors)} error check(s), {len(warns)} warning check(s), {len(clean)} clean")
    if any(f.fixable for f in errors + warns):
        print("Re-run with --fix to repair the fixable ones.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit stored data for silent failures")
    parser.add_argument("--fix", action="store_true", help="Repair the fixable findings")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    report = run_audit(fix=args.fix)
    print_report(report, json_output=args.json)
    return 1 if any(f.count and f.severity == ERROR for f in report.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
