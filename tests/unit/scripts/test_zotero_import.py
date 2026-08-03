"""Unit tests for the one-shot Zotero import script (scripts.zotero_import).

Covers the pure logic: reading PDF attachments and item metadata from a
zotero.sqlite snapshot, and planning the import with hash-based dedupe.
"""
import sqlite3

import pytest

from scripts.zotero_import import (
    ImportDecision,
    ZoteroAttachment,
    ZoteroItemMeta,
    _execute_plan,
    build_paper_lookup,
    find_existing_paper,
    normalize_doi,
    plan_import,
    plan_localize,
    read_item_metadata,
    read_pdf_attachments,
    title_key,
)


# =============================================================================
# Zotero sqlite fixture (minimal schema subset)
# =============================================================================

ZOTERO_SCHEMA = """
CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
CREATE TABLE items (
    itemID INTEGER PRIMARY KEY,
    itemTypeID INTEGER,
    libraryID INTEGER DEFAULT 1,
    key TEXT UNIQUE
);
CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
CREATE TABLE itemAttachments (
    itemID INTEGER PRIMARY KEY,
    parentItemID INTEGER,
    linkMode INTEGER,
    contentType TEXT,
    path TEXT
);
CREATE TABLE creators (
    creatorID INTEGER PRIMARY KEY,
    firstName TEXT,
    lastName TEXT
);
CREATE TABLE itemCreators (
    itemID INTEGER,
    creatorID INTEGER,
    creatorTypeID INTEGER DEFAULT 1,
    orderIndex INTEGER DEFAULT 0
);
INSERT INTO itemTypes VALUES (1, 'journalArticle'), (2, 'attachment'),
    (3, 'note'), (4, 'document');
INSERT INTO fields VALUES (1, 'title'), (2, 'date'), (3, 'DOI'),
    (4, 'publicationTitle');
"""


class ZoteroDbBuilder:
    """Builds a minimal zotero.sqlite for tests."""

    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.executescript(ZOTERO_SCHEMA)
        self._next_item_id = 1
        self._next_value_id = 1
        self._next_creator_id = 1

    def add_item(self, key, type_id=1, title=None, date=None, doi=None,
                 journal=None, authors=None, deleted=False):
        item_id = self._next_item_id
        self._next_item_id += 1
        self.conn.execute(
            "INSERT INTO items (itemID, itemTypeID, key) VALUES (?, ?, ?)",
            (item_id, type_id, key),
        )
        field_values = {1: title, 2: date, 3: doi, 4: journal}
        for field_id, value in field_values.items():
            if value is None:
                continue
            value_id = self._next_value_id
            self._next_value_id += 1
            self.conn.execute(
                "INSERT INTO itemDataValues VALUES (?, ?)", (value_id, value))
            self.conn.execute(
                "INSERT INTO itemData VALUES (?, ?, ?)",
                (item_id, field_id, value_id),
            )
        for order, (first, last) in enumerate(authors or []):
            creator_id = self._next_creator_id
            self._next_creator_id += 1
            self.conn.execute(
                "INSERT INTO creators VALUES (?, ?, ?)",
                (creator_id, first, last),
            )
            self.conn.execute(
                "INSERT INTO itemCreators (itemID, creatorID, orderIndex) "
                "VALUES (?, ?, ?)",
                (item_id, creator_id, order),
            )
        if deleted:
            self.conn.execute(
                "INSERT INTO deletedItems VALUES (?)", (item_id,))
        return item_id

    def add_attachment(self, key, parent_item_id, content_type="application/pdf",
                       link_mode=0, path="storage:paper.pdf"):
        item_id = self.add_item(key, type_id=2)
        self.conn.execute(
            "INSERT INTO itemAttachments VALUES (?, ?, ?, ?, ?)",
            (item_id, parent_item_id, link_mode, content_type, path),
        )
        return item_id

    def finish(self):
        self.conn.commit()
        self.conn.close()
        return self.path


@pytest.fixture
def zotero_db(tmp_path):
    """Return a builder for a throwaway zotero.sqlite."""
    return ZoteroDbBuilder(str(tmp_path / "zotero.sqlite"))


def make_attachment(parent_key="KEY1", attachment_key="ATT1",
                    filename="paper.pdf", parent_type="journalArticle"):
    return ZoteroAttachment(
        parent_key=parent_key,
        parent_type=parent_type,
        attachment_key=attachment_key,
        filename=filename,
    )


# =============================================================================
# read_pdf_attachments
# =============================================================================

class TestReadPdfAttachments:

    def test_returns_stored_pdf_with_parent_key_and_filename(self, zotero_db):
        parent = zotero_db.add_item("AAAA1111", title="A Paper")
        zotero_db.add_attachment("BBBB2222", parent, path="storage:my file.pdf")
        path = zotero_db.finish()

        result = read_pdf_attachments(path)

        assert len(result) == 1
        att = result[0]
        assert att.parent_key == "AAAA1111"
        assert att.parent_type == "journalArticle"
        assert att.attachment_key == "BBBB2222"
        assert att.filename == "my file.pdf"

    def test_excludes_attachments_of_deleted_parents(self, zotero_db):
        parent = zotero_db.add_item("AAAA1111", deleted=True)
        zotero_db.add_attachment("BBBB2222", parent)
        path = zotero_db.finish()

        assert read_pdf_attachments(path) == []

    def test_excludes_non_pdf_attachments(self, zotero_db):
        parent = zotero_db.add_item("AAAA1111")
        zotero_db.add_attachment(
            "BBBB2222", parent, content_type="text/html",
            path="storage:snapshot.html")
        path = zotero_db.finish()

        assert read_pdf_attachments(path) == []

    def test_excludes_linked_file_attachments(self, zotero_db):
        parent = zotero_db.add_item("AAAA1111")
        zotero_db.add_attachment(
            "BBBB2222", parent, link_mode=2,
            path="/absolute/path/elsewhere.pdf")
        path = zotero_db.finish()

        assert read_pdf_attachments(path) == []


# =============================================================================
# read_item_metadata
# =============================================================================

class TestReadItemMetadata:

    def test_returns_title_year_doi_journal_authors(self, zotero_db):
        zotero_db.add_item(
            "AAAA1111",
            title="Atomic Layer Deposition Review",
            date="2019-05-01 2019",
            doi="10.1234/ald.2019",
            journal="Chem. Mater.",
            authors=[("Ada", "Lovelace"), ("Grace", "Hopper")],
        )
        path = zotero_db.finish()

        meta = read_item_metadata(path, ["AAAA1111"])["AAAA1111"]

        assert meta.title == "Atomic Layer Deposition Review"
        assert meta.year == 2019
        assert meta.doi == "10.1234/ald.2019"
        assert meta.journal == "Chem. Mater."
        assert meta.authors == ["Ada Lovelace", "Grace Hopper"]

    def test_handles_missing_fields(self, zotero_db):
        zotero_db.add_item("AAAA1111", title="Bare Item")
        path = zotero_db.finish()

        meta = read_item_metadata(path, ["AAAA1111"])["AAAA1111"]

        assert meta.title == "Bare Item"
        assert meta.year is None
        assert meta.doi is None
        assert meta.authors == []


# =============================================================================
# plan_import
# =============================================================================

class TestPlanImport:

    def test_attaches_pdf_to_known_paper_without_pdf(self):
        att = make_attachment(parent_key="KEY1")
        papers = {"KEY1": {"id": 42, "file_path": None}}

        plan = plan_import([att], papers, known_hashes=set(),
                           hash_of=lambda a: "hash1")

        assert len(plan) == 1
        assert plan[0].action == "attach"
        assert plan[0].paper_id == 42

    def test_skips_paper_that_already_has_pdf(self):
        att = make_attachment(parent_key="KEY1")
        papers = {"KEY1": {"id": 42, "file_path": "/pdfs/existing.pdf"}}

        plan = plan_import([att], papers, known_hashes=set(),
                           hash_of=lambda a: "hash1")

        assert plan[0].action == "skip_has_pdf"

    def test_skips_hash_already_in_database(self):
        att = make_attachment(parent_key="KEY1")
        papers = {"KEY1": {"id": 42, "file_path": None}}

        plan = plan_import([att], papers, known_hashes={"hash1"},
                           hash_of=lambda a: "hash1")

        assert plan[0].action == "skip_duplicate_hash"

    def test_dedupes_identical_hashes_within_batch(self):
        att1 = make_attachment(parent_key="KEY1", attachment_key="ATT1")
        att2 = make_attachment(parent_key="KEY2", attachment_key="ATT2")
        papers = {
            "KEY1": {"id": 1, "file_path": None},
            "KEY2": {"id": 2, "file_path": None},
        }

        plan = plan_import([att1, att2], papers, known_hashes=set(),
                           hash_of=lambda a: "same-hash")

        assert plan[0].action == "attach"
        assert plan[1].action == "skip_duplicate_hash"

    def test_marks_new_import_when_paper_not_in_db(self):
        att = make_attachment(parent_key="NEWKEY")

        plan = plan_import([att], {}, known_hashes=set(),
                           hash_of=lambda a: "hash1")

        assert plan[0].action == "new_import"
        assert plan[0].paper_id is None

    def test_skips_attachment_whose_file_is_missing(self):
        att = make_attachment(parent_key="KEY1")
        papers = {"KEY1": {"id": 42, "file_path": None}}

        plan = plan_import([att], papers, known_hashes=set(),
                           hash_of=lambda a: None)

        assert plan[0].action == "skip_missing_file"

    def test_takes_first_pdf_when_parent_has_several(self):
        att1 = make_attachment(parent_key="KEY1", attachment_key="ATT1",
                               filename="v1.pdf")
        att2 = make_attachment(parent_key="KEY1", attachment_key="ATT2",
                               filename="v2.pdf")
        papers = {"KEY1": {"id": 42, "file_path": None}}
        hashes = {"ATT1": "h1", "ATT2": "h2"}

        plan = plan_import([att1, att2], papers, known_hashes=set(),
                           hash_of=lambda a: hashes[a.attachment_key])

        assert plan[0].action == "attach"
        assert plan[1].action == "skip_extra_pdf"


# =============================================================================
# plan_localize
# =============================================================================

class TestPlanLocalize:
    """Papers whose file_path points outside the managed store get copied in."""

    def test_localizes_paper_pointing_outside_managed_store(self, tmp_path):
        store = tmp_path / "pdfs"
        external = tmp_path / "zotero" / "storage" / "KEY" / "paper.pdf"
        external.parent.mkdir(parents=True)
        external.write_bytes(b"%PDF-1.4 fake")
        papers = [{"id": 1, "file_path": str(external)}]

        plan = plan_localize(papers, managed_root=store)

        assert len(plan) == 1
        assert plan[0]["action"] == "localize"
        assert plan[0]["paper_id"] == 1

    def test_skips_paper_already_inside_managed_store(self, tmp_path):
        store = tmp_path / "pdfs"
        store.mkdir()
        inside = store / "10.1234_x.pdf"
        inside.write_bytes(b"%PDF-1.4 fake")
        papers = [{"id": 1, "file_path": str(inside)}]

        plan = plan_localize(papers, managed_root=store)

        assert plan == []

    def test_flags_missing_source_file(self, tmp_path):
        store = tmp_path / "pdfs"
        papers = [{"id": 1, "file_path": str(tmp_path / "gone.pdf")}]

        plan = plan_localize(papers, managed_root=store)

        assert plan[0]["action"] == "missing_source"

    def test_ignores_papers_without_file_path(self, tmp_path):
        papers = [{"id": 1, "file_path": None}, {"id": 2, "file_path": ""}]

        plan = plan_localize(papers, managed_root=tmp_path / "pdfs")

        assert plan == []


# =============================================================================
# normalize_doi / title_key
# =============================================================================

class TestNormalizeDoi:

    def test_strips_https_prefix_and_lowercases(self):
        assert normalize_doi("https://doi.org/10.1021/ACS.Xyz") == "10.1021/acs.xyz"

    def test_strips_http_and_doi_prefixes(self):
        assert normalize_doi("http://doi.org/10.1/A") == "10.1/a"
        assert normalize_doi("doi:10.1/A") == "10.1/a"

    def test_returns_none_for_missing_or_empty(self):
        assert normalize_doi(None) is None
        assert normalize_doi("") is None
        assert normalize_doi("   ") is None


class TestTitleKey:

    def test_case_and_whitespace_insensitive(self):
        assert title_key("  The   ALD Paper ") == title_key("the ald paper")

    def test_returns_none_for_missing_or_empty(self):
        assert title_key(None) is None
        assert title_key("   ") is None


# =============================================================================
# find_existing_paper (dedupe decision for new_import)
# =============================================================================

class TestFindExistingPaper:

    def test_matches_prefixed_zotero_doi_against_bare_db_doi(self):
        by_doi, by_title = build_paper_lookup(
            [{"id": 7, "doi": "10.1021/xyz", "title": "Stored Title"}])
        meta = ZoteroItemMeta(
            key="K", title="Different Title", doi="https://doi.org/10.1021/XYZ")

        assert find_existing_paper(meta, by_doi, by_title) == 7

    def test_matches_bare_zotero_doi_against_prefixed_db_doi(self):
        by_doi, by_title = build_paper_lookup(
            [{"id": 9, "doi": "https://doi.org/10.1021/XYZ", "title": "T"}])
        meta = ZoteroItemMeta(key="K", title="Other", doi="10.1021/xyz")

        assert find_existing_paper(meta, by_doi, by_title) == 9

    def test_matches_exact_title_when_no_doi(self):
        by_doi, by_title = build_paper_lookup(
            [{"id": 3, "doi": None, "title": "A Thesis  On Zincones"}])
        meta = ZoteroItemMeta(key="K", title="a thesis on zincones", doi=None)

        assert find_existing_paper(meta, by_doi, by_title) == 3

    def test_doi_match_takes_precedence_over_title(self):
        by_doi, by_title = build_paper_lookup([
            {"id": 1, "doi": "10.1/a", "title": "Title A"},
            {"id": 2, "doi": "10.1/b", "title": "Title B"},
        ])
        meta = ZoteroItemMeta(key="K", title="Title B", doi="10.1/a")

        assert find_existing_paper(meta, by_doi, by_title) == 1

    def test_returns_none_when_nothing_matches(self):
        by_doi, by_title = build_paper_lookup(
            [{"id": 1, "doi": "10.1/a", "title": "Title A"}])
        meta = ZoteroItemMeta(key="K", title="Brand New", doi="10.9/zzz")

        assert find_existing_paper(meta, by_doi, by_title) is None

    def test_no_title_match_on_missing_titles(self):
        by_doi, by_title = build_paper_lookup([{"id": 1, "doi": None, "title": None}])
        meta = ZoteroItemMeta(key="K", title=None, doi=None)

        assert find_existing_paper(meta, by_doi, by_title) is None


# =============================================================================
# _execute_plan new_import dedupe (integration, in-memory DB)
# =============================================================================

class TestExecutePlanDedupe:
    """new_import decisions must not re-create papers already in the DB."""

    def _make_storage(self, tmp_path, attachment_key="ATT1"):
        storage_dir = tmp_path / "storage"
        pdf = storage_dir / attachment_key / "paper.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4 fake zotero pdf")
        return storage_dir

    def _patch_pdf_store(self, monkeypatch, tmp_path):
        from services.pdf_service import PDFService
        store = tmp_path / "pdfs"
        monkeypatch.setattr(PDFService, "get_storage_path", lambda: store)
        return store

    def test_new_import_attaches_to_existing_paper_with_doi_variant(
            self, db, zotero_db, tmp_path, monkeypatch):
        from literature_core.models import Paper
        from services.paper_service import PaperService

        self._patch_pdf_store(monkeypatch, tmp_path)
        existing = PaperService.create(title="Known Paper", doi="10.1021/xyz")

        zotero_db.add_item(
            "ZKEY1234", title="Known Paper (Zotero copy)",
            doi="https://doi.org/10.1021/XYZ")
        snapshot = zotero_db.finish()
        storage_dir = self._make_storage(tmp_path)

        decision = ImportDecision(
            make_attachment(parent_key="ZKEY1234", attachment_key="ATT1"),
            "new_import", None, "hash1")
        report = {"attached": [], "imported": [], "errors": []}

        _execute_plan([decision], snapshot, storage_dir, report)

        assert report["errors"] == []
        assert report["imported"] == []
        assert len(report["attached"]) == 1
        assert report["attached"][0]["paper_id"] == existing["id"]
        with db.get_session() as session:
            assert session.query(Paper).count() == 1
            paper = session.query(Paper).first()
            assert paper.file_path is not None
            assert paper.zotero_key == "ZKEY1234"

    def test_new_import_attaches_to_existing_paper_by_title_when_no_doi(
            self, db, zotero_db, tmp_path, monkeypatch):
        from literature_core.models import Paper
        from services.paper_service import PaperService

        self._patch_pdf_store(monkeypatch, tmp_path)
        existing = PaperService.create(title="A Thesis On Zincones")

        zotero_db.add_item("ZKEY1234", title="a thesis  on zincones")
        snapshot = zotero_db.finish()
        storage_dir = self._make_storage(tmp_path)

        decision = ImportDecision(
            make_attachment(parent_key="ZKEY1234", attachment_key="ATT1"),
            "new_import", None, "hash1")
        report = {"attached": [], "imported": [], "errors": []}

        _execute_plan([decision], snapshot, storage_dir, report)

        assert report["errors"] == []
        assert report["imported"] == []
        assert report["attached"][0]["paper_id"] == existing["id"]
        with db.get_session() as session:
            assert session.query(Paper).count() == 1

    def test_new_import_creates_paper_with_normalized_doi(
            self, db, zotero_db, tmp_path, monkeypatch):
        from literature_core.models import Paper

        self._patch_pdf_store(monkeypatch, tmp_path)

        zotero_db.add_item(
            "ZKEY1234", title="Fresh Paper",
            doi="https://doi.org/10.1021/NEW.Paper")
        snapshot = zotero_db.finish()
        storage_dir = self._make_storage(tmp_path)

        decision = ImportDecision(
            make_attachment(parent_key="ZKEY1234", attachment_key="ATT1"),
            "new_import", None, "hash1")
        report = {"attached": [], "imported": [], "errors": []}

        _execute_plan([decision], snapshot, storage_dir, report)

        assert report["errors"] == []
        assert len(report["imported"]) == 1
        with db.get_session() as session:
            paper = session.query(Paper).first()
            assert paper.doi == "10.1021/new.paper"
