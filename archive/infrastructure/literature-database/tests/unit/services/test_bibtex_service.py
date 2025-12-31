"""
Unit tests for BibtexService.

Tests BibTeX parsing, generation, analysis, and fixing.
"""
import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.models import Paper, Author, Manuscript, CitationLocation
from src.services.bibtex_service import BibtexService, BibEntry


# Sample BibTeX content for testing
SAMPLE_BIB_CONTENT = """
@article{Smith2020,
  author = {John Smith and Jane Doe},
  title = {A Study of Machine Learning},
  journal = {Journal of AI},
  year = {2020},
  volume = {15},
  pages = {100--120},
  doi = {10.1234/jai.2020.001}
}

@inproceedings{Jones2021,
  author = {Bob Jones},
  title = {Deep Learning Advances},
  booktitle = {Proceedings of ML Conference},
  year = {2021},
  pages = {50--60},
  doi = {10.1234/mlc.2021.002}
}

@book{Brown2019,
  author = {Alice Brown},
  title = {Introduction to Neural Networks},
  publisher = {Tech Press},
  year = {2019}
}
"""

DUPLICATE_BIB_CONTENT = """
@article{Smith2020,
  author = {John Smith},
  title = {Paper One},
  journal = {Journal A},
  year = {2020},
  doi = {10.1234/same.doi}
}

@article{Smith2020Copy,
  author = {John Smith},
  title = {Paper One},
  journal = {Journal A},
  year = {2020},
  doi = {10.1234/same.doi}
}
"""


class TestBibEntryParsing:
    """Tests for parsing BibTeX entries."""

    @pytest.fixture
    def bib_file(self, tmp_path):
        """Create a temporary bib file."""
        bib_path = tmp_path / "test.bib"
        bib_path.write_text(SAMPLE_BIB_CONTENT)
        return str(bib_path)

    def test_parse_bib_file(self, test_session, bib_file):
        """Test parsing a .bib file."""
        service = BibtexService(test_session)
        entries = service.parse_bib_file(bib_file)

        assert len(entries) == 3
        keys = [e.citation_key for e in entries]
        assert 'Smith2020' in keys
        assert 'Jones2021' in keys
        assert 'Brown2019' in keys

    def test_parse_entry_type(self, test_session, bib_file):
        """Test extracting entry types."""
        service = BibtexService(test_session)
        entries = service.parse_bib_file(bib_file)

        entry_types = {e.citation_key: e.entry_type for e in entries}
        assert entry_types['Smith2020'] == 'article'
        assert entry_types['Jones2021'] == 'inproceedings'
        assert entry_types['Brown2019'] == 'book'

    def test_parse_entry_fields(self, test_session, bib_file):
        """Test extracting entry fields."""
        service = BibtexService(test_session)
        entries = service.parse_bib_file(bib_file)

        smith = next(e for e in entries if e.citation_key == 'Smith2020')
        assert smith.title == 'A Study of Machine Learning'
        assert smith.year == '2020'
        assert smith.doi == '10.1234/jai.2020.001'
        assert 'John Smith' in smith.author

    def test_parse_nonexistent_file(self, test_session):
        """Test parsing a file that doesn't exist."""
        service = BibtexService(test_session)
        with pytest.raises(FileNotFoundError):
            service.parse_bib_file("/nonexistent/path.bib")


class TestBibAnalysis:
    """Tests for analyzing .bib files."""

    @pytest.fixture
    def bib_with_duplicates(self, tmp_path):
        """Create a bib file with duplicates."""
        bib_path = tmp_path / "duplicates.bib"
        bib_path.write_text(DUPLICATE_BIB_CONTENT)
        return str(bib_path)

    @pytest.fixture
    def manuscript(self, test_session):
        """Create a test manuscript."""
        ms = Manuscript(name="TestMS", project_path="/test")
        test_session.add(ms)
        test_session.commit()
        return ms

    def test_analyze_total_entries(self, test_session, tmp_path):
        """Test counting total entries."""
        bib_path = tmp_path / "test.bib"
        bib_path.write_text(SAMPLE_BIB_CONTENT)

        service = BibtexService(test_session)
        result = service.analyze_bib_file(str(bib_path))

        assert result.total_entries == 3
        assert result.unique_keys == 3

    def test_analyze_doi_presence(self, test_session, tmp_path):
        """Test checking DOI presence."""
        bib_path = tmp_path / "test.bib"
        bib_path.write_text(SAMPLE_BIB_CONTENT)

        service = BibtexService(test_session)
        result = service.analyze_bib_file(str(bib_path))

        assert result.entries_with_doi == 2
        assert result.entries_without_doi == 1

    def test_analyze_detects_potential_duplicates(self, test_session, bib_with_duplicates):
        """Test detecting potential duplicate entries."""
        service = BibtexService(test_session)
        result = service.analyze_bib_file(bib_with_duplicates)

        assert len(result.potential_duplicates) > 0


class TestBibGeneration:
    """Tests for generating BibTeX entries."""

    def test_generate_entry_article(self, test_session):
        """Test generating an article entry."""
        service = BibtexService(test_session)

        author = Author(name="John Smith")
        test_session.add(author)
        test_session.commit()

        paper = Paper(
            title="Test Paper",
            year=2024,
            journal="Test Journal",
            volume="10",
            pages="1-10",
            doi="10.1234/test"
        )
        paper.authors.append(author)
        paper.citation_key = "Smith2024Test"
        test_session.add(paper)
        test_session.commit()

        entry = service.generate_bib_entry(paper)

        assert '@article{Smith2024Test' in entry
        assert 'author = {John Smith}' in entry
        assert 'title = {Test Paper}' in entry
        assert 'year = {2024}' in entry
        assert 'doi = {10.1234/test}' in entry

    def test_generate_entry_without_doi(self, test_session):
        """Test generating entry for paper without DOI."""
        service = BibtexService(test_session)

        paper = Paper(title="Test Paper Without Reference", year=2023)
        paper.citation_key = "Unknown2023Test"
        test_session.add(paper)
        test_session.commit()

        entry = service.generate_bib_entry(paper)

        assert '@misc{Unknown2023Test' in entry
        # Check that no 'doi =' field is present (not counting word 'doi' in title)
        assert 'doi =' not in entry.lower()

    def test_generate_standard_key(self, test_session):
        """Test generating standardized citation keys."""
        service = BibtexService(test_session)

        author = Author(name="Sarah Johnson")
        test_session.add(author)
        test_session.commit()

        paper = Paper(title="Advances in Quantum Computing", year=2024)
        paper.authors.append(author)
        test_session.add(paper)
        test_session.commit()

        key = service._generate_standard_key(paper)
        assert key == "Johnson2024Advances"

    def test_generate_standard_key_skips_common_words(self, test_session):
        """Test that common words are skipped in key generation."""
        service = BibtexService(test_session)

        author = Author(name="Jane Doe")
        test_session.add(author)
        test_session.commit()

        paper = Paper(title="The Study of Machine Learning", year=2023)
        paper.authors.append(author)
        test_session.add(paper)
        test_session.commit()

        key = service._generate_standard_key(paper)
        assert key == "Doe2023Study"


class TestFuzzyMatching:
    """Tests for fuzzy title matching."""

    def test_normalize_title(self, test_session):
        """Test title normalization."""
        service = BibtexService(test_session)

        title1 = "A Study of Machine-Learning Applications"
        title2 = "a study of machine learning applications"

        norm1 = service._normalize_title(title1)
        norm2 = service._normalize_title(title2)

        assert norm1 == norm2

    def test_fuzzy_title_match(self, test_session):
        """Test fuzzy title matching."""
        service = BibtexService(test_session)

        paper = Paper(
            title="Molecular Layer Deposition of Alucone Films",
            year=2008
        )
        test_session.add(paper)
        test_session.commit()

        match = service._fuzzy_title_match(
            "Molecular layer deposition of alucone polymer films",
            "2008"
        )

        assert match is not None
        assert match.paper_id == paper.id
        assert match.confidence >= 0.85

    def test_fuzzy_match_no_match(self, test_session):
        """Test fuzzy matching with no match."""
        service = BibtexService(test_session)

        paper = Paper(
            title="Completely Different Topic About Cooking",
            year=2020
        )
        test_session.add(paper)
        test_session.commit()

        match = service._fuzzy_title_match(
            "Quantum Computing Advances",
            "2020"
        )

        assert match is None


class TestBibFixing:
    """Tests for fixing .bib files."""

    @pytest.fixture
    def bib_to_fix(self, tmp_path):
        """Create a bib file that needs fixing."""
        content = """
@article{wrong_case_key,
  author = {Test Author},
  title = {Test Paper},
  journal = {Test Journal},
  year = {2024}
}
"""
        bib_path = tmp_path / "tofix.bib"
        bib_path.write_text(content)
        return str(bib_path)

    def test_fix_dry_run(self, test_session, bib_to_fix, tmp_path):
        """Test dry run doesn't modify file."""
        original_content = Path(bib_to_fix).read_text()

        service = BibtexService(test_session)

        # Create a manuscript for context
        ms = Manuscript(name="TestMS", project_path=str(tmp_path))
        test_session.add(ms)
        test_session.commit()

        output, result, mapping = service.fix_bib_file(
            bib_to_fix,
            manuscript_id=ms.id,
            dry_run=True
        )

        # Original file should be unchanged
        assert Path(bib_to_fix).read_text() == original_content
        assert result.entries_processed > 0

    def test_fix_removes_duplicates(self, test_session, tmp_path):
        """Test removing duplicate entries."""
        content = """
@article{Key1,
  author = {Author One},
  title = {Same Paper},
  journal = {Journal},
  year = {2024},
  doi = {10.1234/same}
}

@article{Key2,
  author = {Author One},
  title = {Same Paper},
  journal = {Journal},
  year = {2024},
  doi = {10.1234/same}
}
"""
        bib_path = tmp_path / "dups.bib"
        bib_path.write_text(content)

        service = BibtexService(test_session)
        ms = Manuscript(name="TestMS", project_path=str(tmp_path))
        test_session.add(ms)
        test_session.commit()

        output, result, mapping = service.fix_bib_file(
            str(bib_path),
            manuscript_id=ms.id,
            remove_duplicates=True,
            dry_run=True
        )

        assert result.duplicates_removed == 1


class TestMissingAndUnused:
    """Tests for finding missing and unused entries."""

    @pytest.fixture
    def setup_manuscript_with_citations(self, test_session, tmp_path):
        """Set up manuscript with citations and bib file."""
        # Create manuscript
        ms = Manuscript(name="TestMS", project_path=str(tmp_path))
        test_session.add(ms)
        test_session.commit()

        # Create citation locations
        for key in ['Cited2024', 'AlsoCited2023']:
            loc = CitationLocation(
                manuscript_id=ms.id,
                citation_key=key,
                file_path="test.tex"
            )
            test_session.add(loc)
        test_session.commit()

        # Create bib file with some entries
        bib_content = """
@article{Cited2024,
  author = {Author},
  title = {Cited Paper},
  journal = {Journal},
  year = {2024}
}

@article{Unused2022,
  author = {Other Author},
  title = {Unused Paper},
  journal = {Journal},
  year = {2022}
}
"""
        bib_path = tmp_path / "refs.bib"
        bib_path.write_text(bib_content)

        return ms, str(bib_path)

    def test_get_missing_bib_entries(self, test_session, setup_manuscript_with_citations):
        """Test finding citations not in .bib file."""
        ms, bib_path = setup_manuscript_with_citations
        service = BibtexService(test_session)

        missing = service.get_missing_bib_entries(ms.id, bib_path)

        # AlsoCited2023 is cited but not in bib
        missing_keys = [key for key, paper in missing]
        assert 'AlsoCited2023' in missing_keys
        assert 'Cited2024' not in missing_keys

    def test_get_unused_bib_entries(self, test_session, setup_manuscript_with_citations):
        """Test finding .bib entries not cited."""
        ms, bib_path = setup_manuscript_with_citations
        service = BibtexService(test_session)

        unused = service.get_unused_bib_entries(ms.id, bib_path)

        unused_keys = [e.citation_key for e in unused]
        assert 'Unused2022' in unused_keys
        assert 'Cited2024' not in unused_keys


class TestDOINormalization:
    """Tests for DOI handling."""

    def test_normalize_doi_removes_prefix(self, test_session):
        """Test that DOI prefixes are removed."""
        service = BibtexService(test_session)

        assert service._normalize_doi("https://doi.org/10.1234/test") == "10.1234/test"
        assert service._normalize_doi("http://doi.org/10.1234/test") == "10.1234/test"
        assert service._normalize_doi("doi:10.1234/test") == "10.1234/test"
        assert service._normalize_doi("10.1234/test") == "10.1234/test"

    def test_normalize_doi_lowercase(self, test_session):
        """Test that DOIs are lowercased."""
        service = BibtexService(test_session)

        assert service._normalize_doi("10.1234/TEST") == "10.1234/test"

    def test_normalize_doi_empty(self, test_session):
        """Test handling empty DOI."""
        service = BibtexService(test_session)

        assert service._normalize_doi("") == ""
        assert service._normalize_doi(None) == ""
