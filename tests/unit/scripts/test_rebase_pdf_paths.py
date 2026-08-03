"""Unit tests for scripts.rebase_pdf_paths (post-migration path fixer).

After cloning the repo on a new machine and restoring data/pdfs, every
papers.file_path still holds the OLD machine's absolute path. The rebase
maps each to <new_storage>/<basename> when that file exists.
"""
from scripts.rebase_pdf_paths import plan_rebase


def make_papers(*paths):
    return [{"id": i + 1, "file_path": p} for i, p in enumerate(paths)]


class TestPlanRebase:

    def test_rebases_old_absolute_path_to_new_storage(self, tmp_path):
        (tmp_path / "10.1234_x.pdf").write_bytes(b"%PDF-1.4")
        papers = make_papers("/old/machine/data/pdfs/10.1234_x.pdf")

        plan = plan_rebase(papers, storage_root=tmp_path)

        assert len(plan) == 1
        assert plan[0]["action"] == "rebase"
        assert plan[0]["paper_id"] == 1
        assert plan[0]["new_path"] == str((tmp_path / "10.1234_x.pdf").resolve())

    def test_skips_paper_whose_path_already_resolves(self, tmp_path):
        pdf = tmp_path / "already_fine.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        papers = make_papers(str(pdf))

        assert plan_rebase(papers, storage_root=tmp_path) == []

    def test_flags_paper_whose_pdf_is_missing_from_storage(self, tmp_path):
        papers = make_papers("/old/machine/data/pdfs/gone.pdf")

        plan = plan_rebase(papers, storage_root=tmp_path)

        assert plan[0]["action"] == "missing"

    def test_ignores_papers_without_file_path(self, tmp_path):
        papers = [{"id": 1, "file_path": None}, {"id": 2, "file_path": ""}]

        assert plan_rebase(papers, storage_root=tmp_path) == []

    def test_handles_windows_style_source_paths(self, tmp_path):
        (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4")
        papers = make_papers("C:\\Users\\old\\data\\pdfs\\paper.pdf")

        plan = plan_rebase(papers, storage_root=tmp_path)

        assert plan[0]["action"] == "rebase"
        assert plan[0]["new_path"] == str((tmp_path / "paper.pdf").resolve())
