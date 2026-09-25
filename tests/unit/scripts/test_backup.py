"""Tests for scripts.backup: paths come from literature_core settings, export uses real Paper columns."""
from __future__ import annotations

import json
import sqlite3

from literature_core import get_session
from literature_core.models import Paper
from scripts import backup


class TestExportPapers:
    def test_export_uses_current_paper_columns(self, db, tmp_path):
        with get_session() as s:
            s.add(Paper(title="Exported", file_path="/x/a.pdf"))
            s.commit()

        dest = backup.export_papers(tmp_path)

        assert dest is not None
        records = json.loads((tmp_path / "papers_export.json").read_text())
        assert len(records) == 1
        assert records[0]["title"] == "Exported"
        assert records[0]["file_path"] == "/x/a.pdf"
        assert "date_added" in records[0] and "date_modified" in records[0]


class TestBackupDatabase:
    def test_copies_settings_database_path(self, tmp_path, monkeypatch):
        from literature_core.config import settings

        src = tmp_path / "src.db"
        conn = sqlite3.connect(src)
        conn.execute("create table papers (id integer primary key, title text)")
        conn.execute("insert into papers (title) values ('a')")
        conn.commit()
        conn.close()
        monkeypatch.setattr(settings, "database_path", src)

        dest = backup.backup_database(tmp_path / "out")

        assert dest == str(tmp_path / "out" / "database" / "src.db")
        copy = sqlite3.connect(dest)
        assert copy.execute("select count(*) from papers").fetchone()[0] == 1
        copy.close()

    def test_missing_database_returns_none(self, tmp_path, monkeypatch):
        from literature_core.config import settings

        monkeypatch.setattr(settings, "database_path", tmp_path / "nope.db")
        assert backup.backup_database(tmp_path / "out") is None
