"""Unit tests for the one-shot Zotero import script (scripts.zotero_import).

Covers the pure logic: reading PDF attachments and item metadata from a
zotero.sqlite snapshot, and planning the import with hash-based dedupe.
"""
import sqlite3

import pytest

from scripts.zotero_import import (
    ZoteroAttachment,
    plan_import,
    plan_localize,
    read_item_metadata,
    read_pdf_attachments,
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
