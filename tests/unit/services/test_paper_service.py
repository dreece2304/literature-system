"""Unit tests for PaperService.

Currently covers list() pagination correctness when author/tag joins
produce duplicated rows (audit finding: pagination operated on join rows,
yielding short pages and duplicate/skipped papers across pages).
"""
from __future__ import annotations

from services import PaperService


class TestPaperServiceListPagination:
    """Tests for PaperService.list pagination over joined filters."""

    @staticmethod
    def _create_papers_with_multiple_matching_authors(count: int) -> list[int]:
        """Create papers that each have TWO authors matching 'wang'."""
        ids = []
        for i in range(count):
            paper = PaperService.create(
                title=f"Paper {i}",
                year=2020 + i,
                authors=[f"Wang Xi {i}", f"Wang Yu {i}", f"Smith {i}"],
            )
            ids.append(paper["id"])
        return ids

    def test_page_size_matches_limit_with_multi_author_join(self, db):
        """A page must contain `limit` distinct papers even when the author
        join produces multiple rows per paper."""
        self._create_papers_with_multiple_matching_authors(6)

        result = PaperService.list(author="wang", limit=3, offset=0)

        assert result.total == 6
        assert len(result.papers) == 3, (
            f"Expected a full page of 3 papers, got {len(result.papers)} "
            "(pagination applied to duplicated join rows)"
        )

    def test_no_duplicates_or_gaps_across_pages(self, db):
        """Iterating pages by offset must return every matching paper exactly once."""
        created_ids = set(self._create_papers_with_multiple_matching_authors(7))

        seen: list[int] = []
        offset = 0
        limit = 3
        while offset < 7:
            page = PaperService.list(author="wang", limit=limit, offset=offset)
            seen.extend(p["id"] for p in page.papers)
            offset += limit

        assert len(seen) == len(set(seen)), f"Duplicate papers across pages: {seen}"
        assert set(seen) == created_ids, (
            f"Papers skipped across pages: missing {created_ids - set(seen)}"
        )

    def test_unfiltered_list_pagination_unaffected(self, db):
        """Sanity: pagination without join filters still works."""
        for i in range(5):
            PaperService.create(title=f"Plain {i}")

        page1 = PaperService.list(limit=2, offset=0)
        page2 = PaperService.list(limit=2, offset=2)
        page3 = PaperService.list(limit=2, offset=4)

        all_ids = [p["id"] for p in page1.papers + page2.papers + page3.papers]
        assert page1.total == 5
        assert len(all_ids) == 5
        assert len(set(all_ids)) == 5

    def test_multi_author_paper_appears_once_per_page(self, db):
        """A single paper with several matching authors must appear once."""
        paper = PaperService.create(
            title="Multi-author paper",
            authors=["Wang A", "Wang B", "Wang C"],
        )

        result = PaperService.list(author="wang", limit=10, offset=0)

        ids = [p["id"] for p in result.papers]
        assert ids.count(paper["id"]) == 1
        assert result.total == 1
