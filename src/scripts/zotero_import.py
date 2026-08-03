"""One-shot Zotero import - attach storage PDFs and import missing items.

Reads a zotero.sqlite snapshot directly (no running Zotero app or API needed),
maps PDF attachments to DB papers via zotero_key, and plans an import that
never duplicates a PDF already in the managed store (SHA256 dedupe against
papers.file_hash and within the batch).

Usage (dry-run by default):
    cd src && mamba run -n litai python -m scripts.zotero_import
    cd src && mamba run -n litai python -m scripts.zotero_import --execute

The live Zotero data dir is read from --zotero-dir (default: the Windows
install at /mnt/c/Users/dreec/Zotero). The sqlite file is copied to a temp
location before reading so the live DB is never touched.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

DEFAULT_ZOTERO_DIR = "/mnt/c/Users/dreec/Zotero"
SWEEP_COLLECTION = "swept-2026-07"


@dataclass
class ZoteroAttachment:
    """A stored PDF attachment in a Zotero library."""
    parent_key: str
    parent_type: str
    attachment_key: str
    filename: str


@dataclass
class ZoteroItemMeta:
    """Metadata for a top-level Zotero item."""
    key: str
    title: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    authors: list[str] = field(default_factory=list)


@dataclass
class ImportDecision:
    """Planned action for one attachment."""
    attachment: ZoteroAttachment
    action: str  # attach, new_import, skip_has_pdf, skip_duplicate_hash,
    #              skip_missing_file, skip_extra_pdf
    paper_id: Optional[int] = None
    file_hash: Optional[str] = None


def read_pdf_attachments(sqlite_path: str) -> list[ZoteroAttachment]:
    """Read stored (non-linked) PDF attachments with non-deleted parents."""
    query = """
        SELECT p.key, pt.typeName, a.key, ia.path
        FROM itemAttachments ia
        JOIN items a ON a.itemID = ia.itemID
        JOIN items p ON p.itemID = ia.parentItemID
        JOIN itemTypes pt ON pt.itemTypeID = p.itemTypeID
        WHERE ia.contentType = 'application/pdf'
          AND ia.linkMode IN (0, 1)
          AND ia.path LIKE 'storage:%'
          AND p.itemID NOT IN (SELECT itemID FROM deletedItems)
          AND a.itemID NOT IN (SELECT itemID FROM deletedItems)
        ORDER BY p.key, a.key
    """
    with sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(query).fetchall()
    return [
        ZoteroAttachment(
            parent_key=parent_key,
            parent_type=parent_type,
            attachment_key=attachment_key,
            filename=path[len("storage:"):],
        )
        for parent_key, parent_type, attachment_key, path in rows
    ]


def read_item_metadata(sqlite_path: str, keys: list[str]) -> dict[str, ZoteroItemMeta]:
    """Read title/year/DOI/journal/authors for the given item keys."""
    placeholders = ",".join("?" for _ in keys)
    field_query = f"""
        SELECT i.key, f.fieldName, idv.value
        FROM items i
        JOIN itemData id ON id.itemID = i.itemID
        JOIN fields f ON f.fieldID = id.fieldID
        JOIN itemDataValues idv ON idv.valueID = id.valueID
        WHERE i.key IN ({placeholders})
          AND f.fieldName IN ('title', 'date', 'DOI', 'publicationTitle')
    """
    creator_query = f"""
        SELECT i.key, c.firstName, c.lastName
        FROM items i
        JOIN itemCreators ic ON ic.itemID = i.itemID
        JOIN creators c ON c.creatorID = ic.creatorID
        WHERE i.key IN ({placeholders})
        ORDER BY i.key, ic.orderIndex
    """
    with sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True) as conn:
        field_rows = conn.execute(field_query, keys).fetchall()
        creator_rows = conn.execute(creator_query, keys).fetchall()

    metas = {key: ZoteroItemMeta(key=key) for key in keys}
    for key, field_name, value in field_rows:
        meta = metas[key]
        if field_name == "title":
            meta.title = value
        elif field_name == "DOI":
            meta.doi = value
        elif field_name == "publicationTitle":
            meta.journal = value
        elif field_name == "date":
            match = re.search(r"\b(\d{4})\b", value or "")
            meta.year = int(match.group(1)) if match else None
    for key, first, last in creator_rows:
        name = " ".join(part for part in (first, last) if part)
        if name:
            metas[key].authors.append(name)
    return metas


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """Normalize a DOI for comparison: strip resolver prefixes, lowercase.

    Mirrors PaperService._normalize_doi so Zotero DOIs like
    'https://doi.org/10.1021/XYZ' compare equal to a stored '10.1021/xyz'.
    """
    if not doi:
        return None
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi or None


def title_key(title: Optional[str]) -> Optional[str]:
    """Case/whitespace-insensitive key for exact title matching."""
    if not title:
        return None
    key = " ".join(title.split()).lower()
    return key or None


def build_paper_lookup(papers: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """Build normalized DOI and title lookups from {'id', 'doi', 'title'} dicts.

    Returns (papers_by_doi, papers_by_title); first paper wins on collisions.
    """
    papers_by_doi: dict[str, int] = {}
    papers_by_title: dict[str, int] = {}
    for paper in papers:
        doi = normalize_doi(paper.get("doi"))
        if doi and doi not in papers_by_doi:
            papers_by_doi[doi] = paper["id"]
        title = title_key(paper.get("title"))
        if title and title not in papers_by_title:
            papers_by_title[title] = paper["id"]
    return papers_by_doi, papers_by_title


def find_existing_paper(
    meta: ZoteroItemMeta,
    papers_by_doi: dict[str, int],
    papers_by_title: dict[str, int],
) -> Optional[int]:
    """Return the id of an existing paper matching meta, or None.

    Matches by normalized DOI first, then by exact (case/whitespace-
    insensitive) title. Guards the new_import path against re-creating
    papers imported earlier without a zotero_key (e.g. DOI stored with a
    'https://doi.org/' prefix or different casing, or DOI-less items that
    share a title).
    """
    doi = normalize_doi(meta.doi)
    if doi is not None and doi in papers_by_doi:
        return papers_by_doi[doi]
    title = title_key(meta.title)
    if title is not None and title in papers_by_title:
        return papers_by_title[title]
    return None


def plan_import(
    attachments: list[ZoteroAttachment],
    papers_by_key: dict[str, dict],
    known_hashes: set[str],
    hash_of: Callable[[ZoteroAttachment], Optional[str]],
) -> list[ImportDecision]:
    """Decide what to do with each attachment, deduping PDFs by hash.

    papers_by_key maps zotero_key -> {"id": int, "file_path": str | None}.
    known_hashes holds SHA256 hashes already present in the DB.
    hash_of returns the attachment file's hash, or None if the file is missing.
    """
    seen_hashes = set(known_hashes)
    handled_parents: set[str] = set()
    decisions = []
    for att in attachments:
        paper = papers_by_key.get(att.parent_key)
        paper_id = paper["id"] if paper else None

        if att.parent_key in handled_parents:
            decisions.append(ImportDecision(att, "skip_extra_pdf", paper_id))
            continue
        if paper and paper["file_path"]:
            handled_parents.add(att.parent_key)
            decisions.append(ImportDecision(att, "skip_has_pdf", paper_id))
            continue

        file_hash = hash_of(att)
        if file_hash is None:
            decisions.append(ImportDecision(att, "skip_missing_file", paper_id))
            continue
        if file_hash in seen_hashes:
            decisions.append(
                ImportDecision(att, "skip_duplicate_hash", paper_id, file_hash))
            continue

        seen_hashes.add(file_hash)
        handled_parents.add(att.parent_key)
        action = "attach" if paper else "new_import"
        decisions.append(ImportDecision(att, action, paper_id, file_hash))
    return decisions


def plan_localize(papers: list[dict], managed_root: Path) -> list[dict]:
    """Plan copying externally-stored PDFs into the managed store.

    papers is a list of {"id": int, "file_path": str | None}. Papers whose
    file already lives under managed_root (or have no file) are skipped;
    existing external files get 'localize', vanished ones 'missing_source'.
    """
    managed_root = Path(managed_root).resolve()
    plan = []
    for paper in papers:
        file_path = paper.get("file_path")
        if not file_path:
            continue
        path = Path(file_path)
        try:
            resolved = path.resolve()
            if resolved.is_relative_to(managed_root):
                continue
        except OSError:
            pass
        action = "localize" if path.is_file() else "missing_source"
        plan.append({"paper_id": paper["id"], "source": str(path), "action": action})
    return plan


# =============================================================================
# Execution (thin glue over tested planner + existing services)
# =============================================================================

def _storage_pdf_path(storage_dir: Path, att: ZoteroAttachment) -> Optional[Path]:
    """Locate an attachment's PDF on disk, tolerating renamed files."""
    candidate = storage_dir / att.attachment_key / att.filename
    if candidate.is_file():
        return candidate
    folder = storage_dir / att.attachment_key
    if folder.is_dir():
        pdfs = sorted(folder.glob("*.pdf"))
        if pdfs:
            return pdfs[0]
    return None


def _copy_into_store(src: Path, paper: dict, storage_path: Path) -> Path:
    """Copy a PDF into the managed store under the canonical filename."""
    from services.pdf_service import PDFService

    storage_path.mkdir(parents=True, exist_ok=True)
    dest = storage_path / PDFService.generate_filename(paper)
    counter = 1
    while dest.exists():
        dest = storage_path / f"{dest.stem}_{counter}.pdf"
        counter += 1
    shutil.copy2(src, dest)
    return dest


def run(zotero_dir: str, execute: bool, report_path: str) -> dict:
    """Plan (and optionally execute) the import. Returns the report dict."""
    from literature_core import get_logger
    from literature_core.database import get_session
    from literature_core.models import Paper
    from services.pdf_service import PDFService

    logger = get_logger(__name__)
    zotero_path = Path(zotero_dir)
    storage_dir = zotero_path / "storage"

    # Snapshot the live sqlite so we never touch Zotero's own DB
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        shutil.copyfile(zotero_path / "zotero.sqlite", tmp.name)
        snapshot = tmp.name

    try:
        attachments = read_pdf_attachments(snapshot)

        with get_session() as session:
            rows = session.query(
                Paper.zotero_key, Paper.id, Paper.file_path, Paper.file_hash
            ).all()
        papers_by_key = {
            r.zotero_key: {"id": r.id, "file_path": r.file_path}
            for r in rows if r.zotero_key
        }
        known_hashes = {r.file_hash for r in rows if r.file_hash}

        hash_cache: dict[str, Optional[str]] = {}

        def hash_of(att: ZoteroAttachment) -> Optional[str]:
            if att.attachment_key not in hash_cache:
                path = _storage_pdf_path(storage_dir, att)
                hash_cache[att.attachment_key] = (
                    PDFService.compute_file_hash(path) if path else None)
            return hash_cache[att.attachment_key]

        decisions = plan_import(attachments, papers_by_key, known_hashes, hash_of)
        localize_plan = plan_localize(
            [{"id": r.id, "file_path": r.file_path} for r in rows],
            managed_root=PDFService.get_storage_path(),
        )

        counts: dict[str, int] = {}
        for d in decisions:
            counts[d.action] = counts.get(d.action, 0) + 1
        for item in localize_plan:
            counts[item["action"]] = counts.get(item["action"], 0) + 1
        logger.info(f"Zotero import plan: {counts}")

        report = {
            "zotero_dir": str(zotero_path),
            "executed": execute,
            "counts": counts,
            "decisions": [
                {**asdict(d.attachment), "action": d.action, "paper_id": d.paper_id}
                for d in decisions
            ],
            "localize": localize_plan,
            "attached": [],
            "imported": [],
            "localized": [],
            "errors": [],
        }

        if execute:
            _execute_plan(decisions, snapshot, storage_dir, report)
            _execute_localize(localize_plan, report)

        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        return report
    finally:
        Path(snapshot).unlink(missing_ok=True)


def _execute_plan(decisions, snapshot, storage_dir, report) -> None:
    """Apply attach/new_import decisions via the service layer."""
    from literature_core import get_logger
    from literature_core.database import get_session
    from literature_core.models import Paper
    from services.collection_service import CollectionService
    from services.paper_service import PaperService
    from services.pdf_service import PDFService

    logger = get_logger(__name__)
    pdf_store = PDFService.get_storage_path()

    new_keys = [d.attachment.parent_key for d in decisions if d.action == "new_import"]
    metas = read_item_metadata(snapshot, new_keys) if new_keys else {}

    papers_by_doi: dict[str, int] = {}
    papers_by_title: dict[str, int] = {}
    if new_keys:
        with get_session() as session:
            existing_rows = session.query(Paper.id, Paper.doi, Paper.title).all()
        papers_by_doi, papers_by_title = build_paper_lookup(
            [{"id": r.id, "doi": r.doi, "title": r.title} for r in existing_rows])

    imported_ids = []
    for decision in decisions:
        att = decision.attachment
        try:
            if decision.action == "attach":
                src = _storage_pdf_path(storage_dir, att)
                with get_session() as session:
                    row = session.query(Paper.id, Paper.doi, Paper.arxiv_id).filter(
                        Paper.id == decision.paper_id).first()
                paper_dict = {"id": row.id, "doi": row.doi, "arxiv_id": row.arxiv_id}
                dest = _copy_into_store(src, paper_dict, pdf_store)
                PDFService.link_local_pdf(decision.paper_id, str(dest))
                report["attached"].append(
                    {"paper_id": decision.paper_id, "file": dest.name})

            elif decision.action == "new_import":
                meta = metas[att.parent_key]
                if not meta.title:
                    raise ValueError(f"No title for Zotero item {att.parent_key}")
                existing_id = find_existing_paper(meta, papers_by_doi, papers_by_title)
                if existing_id is not None:
                    # Already in the DB (DOI/title match, just no zotero_key):
                    # attach the PDF instead of creating a duplicate.
                    _attach_to_existing_paper(
                        existing_id, att, storage_dir, pdf_store, report)
                    continue
                created = PaperService.create(
                    title=meta.title, year=meta.year, doi=normalize_doi(meta.doi),
                    journal=meta.journal, authors=meta.authors,
                )
                with get_session() as session:
                    paper = session.query(Paper).filter(
                        Paper.id == created["id"]).first()
                    paper.zotero_key = att.parent_key
                    paper.import_method = "zotero"
                src = _storage_pdf_path(storage_dir, att)
                dest = _copy_into_store(src, created, pdf_store)
                PDFService.link_local_pdf(created["id"], str(dest))
                imported_ids.append(created["id"])
                report["imported"].append(
                    {"paper_id": created["id"], "title": meta.title,
                     "zotero_key": att.parent_key})
        except Exception as e:  # keep going; failures land in the report
            logger.error(f"Zotero import failed for {att.parent_key}: {e}")
            report["errors"].append({"zotero_key": att.parent_key, "error": str(e)})

    if imported_ids:
        try:
            collections = CollectionService.list(list_all=True).collections
            existing = next(
                (c for c in collections if c["name"] == SWEEP_COLLECTION), None)
            collection_id = existing["id"] if existing else CollectionService.create(
                name=SWEEP_COLLECTION,
                description="Papers imported during the 2026-07 PDF consolidation sweep",
            )["id"]
            CollectionService.add_papers(collection_id, imported_ids)
        except Exception as e:
            logger.error(f"Failed to tag imports into {SWEEP_COLLECTION}: {e}")
            report["errors"].append(
                {"collection": SWEEP_COLLECTION, "error": str(e)})


def _attach_to_existing_paper(paper_id: int, att: ZoteroAttachment,
                              storage_dir: Path, pdf_store: Path,
                              report: dict) -> None:
    """Attach a new_import PDF to a paper that already exists (dedupe hit).

    Records the zotero_key on the paper so future runs map it directly.
    The PDF is only linked when the paper has none yet.
    """
    from literature_core.database import get_session
    from literature_core.models import Paper
    from services.pdf_service import PDFService

    with get_session() as session:
        paper = session.query(Paper).filter(Paper.id == paper_id).first()
        if not paper.zotero_key:
            paper.zotero_key = att.parent_key
        has_pdf = bool(paper.file_path)
        paper_dict = {"id": paper.id, "doi": paper.doi, "arxiv_id": paper.arxiv_id}

    entry = {"paper_id": paper_id, "file": None, "matched_existing": True}
    if not has_pdf:
        src = _storage_pdf_path(storage_dir, att)
        dest = _copy_into_store(src, paper_dict, pdf_store)
        PDFService.link_local_pdf(paper_id, str(dest))
        entry["file"] = dest.name
    report["attached"].append(entry)


def _execute_localize(localize_plan: list[dict], report: dict) -> None:
    """Copy external PDFs into the managed store and repoint papers.

    Deliberately avoids link_local_pdf: the PDF content is unchanged, so
    word_count and enrichment_status must not be reset. Only file_path is
    updated, plus file_hash when missing (with a warning on mismatch).
    """
    from literature_core import get_logger
    from literature_core.database import get_session
    from literature_core.models import Paper
    from services.pdf_service import PDFService

    logger = get_logger(__name__)
    pdf_store = PDFService.get_storage_path()

    for item in localize_plan:
        if item["action"] != "localize":
            continue
        try:
            src = Path(item["source"])
            file_hash = PDFService.compute_file_hash(src)
            with get_session() as session:
                paper = session.query(Paper).filter(
                    Paper.id == item["paper_id"]).first()
                paper_dict = {"id": paper.id, "doi": paper.doi,
                              "arxiv_id": paper.arxiv_id}
                dest = _copy_into_store(src, paper_dict, pdf_store)
                if paper.file_hash and paper.file_hash != file_hash:
                    logger.warning(
                        f"Hash mismatch localizing paper {paper.id}: "
                        f"stored {paper.file_hash[:12]} != file {file_hash[:12]}")
                paper.file_path = str(dest.absolute())
                paper.file_hash = file_hash
            report["localized"].append(
                {"paper_id": item["paper_id"], "file": dest.name})
        except Exception as e:
            logger.error(f"Localize failed for paper {item['paper_id']}: {e}")
            report["errors"].append(
                {"paper_id": item["paper_id"], "error": str(e)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zotero-dir", default=DEFAULT_ZOTERO_DIR)
    parser.add_argument("--execute", action="store_true",
                        help="Apply changes (default is dry-run)")
    parser.add_argument(
        "--report",
        default=str(Path(__file__).resolve().parents[2]
                    / "data" / "consolidation" / "zotero_import_report.json"))
    args = parser.parse_args()

    report = run(args.zotero_dir, args.execute, args.report)
    print(f"{'EXECUTED' if args.execute else 'DRY RUN'}: {report['counts']}")
    print(f"Report written to {args.report}")


if __name__ == "__main__":
    main()
