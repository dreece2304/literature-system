"""
Unit tests for CitationService.

Tests manuscript management, citation scanning, key generation, and export.
"""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.models import Paper, Author, Manuscript, CitationLocation
from src.services.citation_service import CitationService, CitationMatch
from tests.fixtures.factories import PaperFactory, AuthorFactory, ManuscriptFactory


class TestManuscriptManagement:
    """Tests for manuscript CRUD operations."""

    def test_register_manuscript(self, test_session):
        """Test registering a new manuscript."""
        service = CitationService(test_session)

        manuscript = service.register_manuscript(
            name="Paper2",
            project_path="/home/user/Paper2",
            tex_directory="paper/tex",
            bib_file="paper/bib/references.bib",
            description="PhD thesis paper on MLD"
        )

        assert manuscript.id is not None
        assert manuscript.name == "Paper2"
        assert manuscript.project_path == "/home/user/Paper2"
        assert manuscript.tex_directory == "paper/tex"

    def test_register_duplicate_name_fails(self, test_session):
        """Test that duplicate manuscript names are rejected."""
        service = CitationService(test_session)

        service.register_manuscript(name="Paper2", project_path="/path1")

        with pytest.raises(ValueError, match="already exists"):
            service.register_manuscript(name="Paper2", project_path="/path2")

    def test_get_manuscript_by_id(self, test_session):
        """Test retrieving manuscript by ID."""
        service = CitationService(test_session)
        ms = service.register_manuscript(name="Test", project_path="/test")

        retrieved = service.get_manuscript(ms.id)
        assert retrieved.name == "Test"

    def test_get_manuscript_by_name(self, test_session):
        """Test retrieving manuscript by name."""
        service = CitationService(test_session)
        service.register_manuscript(name="Paper2", project_path="/test")

        retrieved = service.get_manuscript_by_name("Paper2")
        assert retrieved is not None
        assert retrieved.name == "Paper2"

    def test_get_nonexistent_manuscript(self, test_session):
        """Test getting a manuscript that doesn't exist."""
        service = CitationService(test_session)

        assert service.get_manuscript(999) is None
        assert service.get_manuscript_by_name("nonexistent") is None

    def test_list_manuscripts(self, test_session):
        """Test listing all manuscripts."""
        service = CitationService(test_session)

        service.register_manuscript(name="Paper1", project_path="/p1")
        service.register_manuscript(name="Paper2", project_path="/p2")
        service.register_manuscript(name="Paper3", project_path="/p3")

        manuscripts = service.list_manuscripts()
        assert len(manuscripts) == 3

    def test_update_manuscript(self, test_session):
        """Test updating manuscript fields."""
        service = CitationService(test_session)
        ms = service.register_manuscript(name="Test", project_path="/old")

        updated = service.update_manuscript(ms.id, project_path="/new", description="Updated")

        assert updated.project_path == "/new"
        assert updated.description == "Updated"

    def test_delete_manuscript(self, test_session):
        """Test deleting a manuscript."""
        service = CitationService(test_session)
        ms = service.register_manuscript(name="ToDelete", project_path="/test")
        ms_id = ms.id

        assert service.delete_manuscript(ms_id)
        assert service.get_manuscript(ms_id) is None

    def test_delete_nonexistent_manuscript(self, test_session):
        """Test deleting a manuscript that doesn't exist."""
        service = CitationService(test_session)
        assert not service.delete_manuscript(999)


class TestCitationKeyGeneration:
    """Tests for citation key generation."""

    def test_generate_citation_key_basic(self, test_session):
        """Test generating a citation key."""
        service = CitationService(test_session)

        author = Author(name="John Dameron")
        test_session.add(author)
        test_session.commit()

        paper = Paper(
            title="Alucone MLD Growth Mechanisms",
            year=2008
        )
        paper.authors.append(author)
        test_session.add(paper)
        test_session.commit()

        key = service.generate_citation_key(paper)
        assert key == "Dameron2008Alucone"

    def test_generate_citation_key_skip_common_words(self, test_session):
        """Test that common words are skipped in key generation."""
        service = CitationService(test_session)

        author = Author(name="Jane Smith")
        test_session.add(author)
        test_session.commit()

        paper = Paper(
            title="The Study of Machine Learning Applications",
            year=2024
        )
        paper.authors.append(author)
        test_session.add(paper)
        test_session.commit()

        key = service.generate_citation_key(paper)
        assert key == "Smith2024Study"

    def test_generate_citation_key_no_author(self, test_session):
        """Test key generation when paper has no authors."""
        service = CitationService(test_session)

        paper = Paper(title="Anonymous Paper", year=2023)
        test_session.add(paper)
        test_session.commit()

        key = service.generate_citation_key(paper)
        assert key == "Unknown2023Anonymous"

    def test_generate_citation_key_last_first_format(self, test_session):
        """Test key generation with 'Last, First' author name format."""
        service = CitationService(test_session)

        author = Author(name="Dameron, S. M.")
        test_session.add(author)
        test_session.commit()

        paper = Paper(title="Alucone Films", year=2008)
        paper.authors.append(author)
        test_session.add(paper)
        test_session.commit()

        key = service.generate_citation_key(paper)
        assert key == "Dameron2008Alucone"

    def test_set_citation_key(self, test_session):
        """Test setting a citation key."""
        service = CitationService(test_session)

        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        assert service.set_citation_key(paper.id, "Test2024Key")
        test_session.refresh(paper)
        assert paper.citation_key == "Test2024Key"

    def test_set_citation_key_duplicate_fails(self, test_session):
        """Test that duplicate citation keys are rejected."""
        service = CitationService(test_session)

        paper1 = Paper(title="Paper 1", citation_key="Existing2024")
        paper2 = Paper(title="Paper 2")
        test_session.add_all([paper1, paper2])
        test_session.commit()

        with pytest.raises(ValueError, match="already exists"):
            service.set_citation_key(paper2.id, "Existing2024")

    def test_suggest_citation_keys(self, test_session):
        """Test suggesting keys for papers without one."""
        service = CitationService(test_session)

        author = Author(name="John Test")
        test_session.add(author)
        test_session.commit()

        paper1 = Paper(title="First Paper", year=2024, citation_key="Existing2024")
        paper2 = Paper(title="Second Paper", year=2023)
        paper2.authors.append(author)

        test_session.add_all([paper1, paper2])
        test_session.commit()

        suggestions = service.suggest_citation_keys()

        assert len(suggestions) == 1
        assert suggestions[0][0].id == paper2.id
        assert suggestions[0][1] == "Test2023Second"


class TestCitationScanning:
    """Tests for LaTeX file scanning."""

    @pytest.fixture
    def tex_directory(self, tmp_path):
        """Create a temporary TeX directory with sample files."""
        tex_dir = tmp_path / "paper" / "tex"
        tex_dir.mkdir(parents=True)

        # Create introduction.tex
        intro = tex_dir / "introduction.tex"
        intro.write_text(r"""
\section{Introduction}
Recent advances in MLD have been significant \cite{Dameron2008Alucone}.
Multiple studies support this \cite{Smith2020, Jones2021}.
As shown by \citet{Brown2019}, the results are promising.
See also \citep[p.~42]{Wilson2022}.
""")

        # Create methods.tex
        methods = tex_dir / "methods.tex"
        methods.write_text(r"""
\section{Methods}
Following the procedure from \cite{Dameron2008Alucone}, we prepared samples.
The characterization was done per \cite{Lee2023}.
""")

        # Create Archive/old.tex (should be skipped)
        archive_dir = tex_dir / "Archive"
        archive_dir.mkdir()
        old_file = archive_dir / "old.tex"
        old_file.write_text(r"\cite{OldRef2010}")

        return tmp_path

    def test_scan_citations(self, test_session, tex_directory):
        """Test scanning a manuscript for citations."""
        service = CitationService(test_session)

        # Create manuscript pointing to temp directory
        manuscript = service.register_manuscript(
            name="TestPaper",
            project_path=str(tex_directory),
            tex_directory="paper/tex"
        )

        result = service.scan_citations(manuscript.id)

        assert result.manuscript_id == manuscript.id
        assert result.total_citations > 0
        assert result.unique_keys > 0
        assert "Dameron2008Alucone" in [
            loc.citation_key for loc in
            service.get_manuscript_citations(manuscript.id)
        ]

    def test_scan_skips_archive(self, test_session, tex_directory):
        """Test that Archive directories are skipped."""
        service = CitationService(test_session)

        manuscript = service.register_manuscript(
            name="TestPaper",
            project_path=str(tex_directory),
            tex_directory="paper/tex"
        )

        service.scan_citations(manuscript.id)
        locations = service.get_manuscript_citations(manuscript.id)

        # OldRef2010 should not be found (in Archive)
        keys = [loc.citation_key for loc in locations]
        assert "OldRef2010" not in keys

    def test_scan_handles_multiple_keys(self, test_session, tex_directory):
        """Test handling multiple comma-separated citation keys."""
        service = CitationService(test_session)

        manuscript = service.register_manuscript(
            name="TestPaper",
            project_path=str(tex_directory),
            tex_directory="paper/tex"
        )

        service.scan_citations(manuscript.id)
        locations = service.get_manuscript_citations(manuscript.id)

        keys = [loc.citation_key for loc in locations]
        assert "Smith2020" in keys
        assert "Jones2021" in keys

    def test_scan_matches_papers(self, test_session, tex_directory):
        """Test that citations are matched to papers with citation_key."""
        service = CitationService(test_session)

        # Create a paper with matching citation key
        paper = Paper(
            title="Alucone MLD Growth",
            citation_key="Dameron2008Alucone"
        )
        test_session.add(paper)
        test_session.commit()

        manuscript = service.register_manuscript(
            name="TestPaper",
            project_path=str(tex_directory),
            tex_directory="paper/tex"
        )

        result = service.scan_citations(manuscript.id)

        assert result.matched_to_papers >= 1
        locations = service.get_paper_citations(paper.id)
        assert len(locations) > 0

    def test_scan_updates_last_scanned(self, test_session, tex_directory):
        """Test that last_scanned is updated after scan."""
        service = CitationService(test_session)

        manuscript = service.register_manuscript(
            name="TestPaper",
            project_path=str(tex_directory),
            tex_directory="paper/tex"
        )

        assert manuscript.last_scanned is None

        service.scan_citations(manuscript.id)
        test_session.refresh(manuscript)

        assert manuscript.last_scanned is not None

    def test_scan_nonexistent_manuscript(self, test_session):
        """Test scanning a manuscript that doesn't exist."""
        service = CitationService(test_session)

        with pytest.raises(ValueError, match="not found"):
            service.scan_citations(999)

    def test_scan_nonexistent_directory(self, test_session, tmp_path):
        """Test scanning when tex directory doesn't exist."""
        service = CitationService(test_session)

        manuscript = service.register_manuscript(
            name="TestPaper",
            project_path=str(tmp_path),
            tex_directory="nonexistent/path"
        )

        with pytest.raises(FileNotFoundError):
            service.scan_citations(manuscript.id)


class TestCitationValidation:
    """Tests for citation consistency checking."""

    def test_check_citations_no_issues(self, test_session):
        """Test checking citations with no issues."""
        service = CitationService(test_session)

        # Create paper with key
        paper = Paper(title="Test", citation_key="Test2024")
        test_session.add(paper)
        test_session.commit()

        # Create manuscript and location
        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add(manuscript)
        test_session.commit()

        location = CitationLocation(
            paper_id=paper.id,
            manuscript_id=manuscript.id,
            citation_key="Test2024",
            file_path="test.tex"
        )
        test_session.add(location)
        test_session.commit()

        result = service.check_citations(manuscript.id)

        assert result.total_papers_cited == 1
        assert len(result.orphan_citations) == 0
        assert len(result.issues) == 0

    def test_check_citations_orphan_keys(self, test_session):
        """Test detecting orphan citation keys."""
        service = CitationService(test_session)

        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add(manuscript)
        test_session.commit()

        # Citation without matching paper
        location = CitationLocation(
            manuscript_id=manuscript.id,
            citation_key="Nonexistent2024",
            file_path="test.tex"
        )
        test_session.add(location)
        test_session.commit()

        result = service.check_citations(manuscript.id)

        assert "Nonexistent2024" in result.orphan_citations
        assert any("not matched" in issue for issue in result.issues)

    def test_check_citations_nonexistent_manuscript(self, test_session):
        """Test checking citations for nonexistent manuscript."""
        service = CitationService(test_session)

        with pytest.raises(ValueError, match="not found"):
            service.check_citations(999)


class TestCitationQueries:
    """Tests for citation query methods."""

    def test_get_paper_citations(self, test_session):
        """Test getting citations for a specific paper."""
        service = CitationService(test_session)

        paper = Paper(title="Test", citation_key="Test2024")
        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add_all([paper, manuscript])
        test_session.commit()

        for i in range(3):
            location = CitationLocation(
                paper_id=paper.id,
                manuscript_id=manuscript.id,
                citation_key="Test2024",
                file_path=f"chapter{i}.tex"
            )
            test_session.add(location)
        test_session.commit()

        locations = service.get_paper_citations(paper.id)
        assert len(locations) == 3

    def test_get_citations_by_key(self, test_session):
        """Test getting citations by citation key."""
        service = CitationService(test_session)

        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add(manuscript)
        test_session.commit()

        location = CitationLocation(
            manuscript_id=manuscript.id,
            citation_key="Unique2024Key",
            file_path="test.tex"
        )
        test_session.add(location)
        test_session.commit()

        locations = service.get_citations_by_key("Unique2024Key")
        assert len(locations) == 1
        assert locations[0].citation_key == "Unique2024Key"

    def test_get_manuscript_citations_exclude_unmatched(self, test_session):
        """Test filtering out unmatched citations."""
        service = CitationService(test_session)

        paper = Paper(title="Test", citation_key="Test2024")
        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add_all([paper, manuscript])
        test_session.commit()

        # Matched citation
        loc1 = CitationLocation(
            paper_id=paper.id,
            manuscript_id=manuscript.id,
            citation_key="Test2024",
            file_path="test.tex"
        )
        # Unmatched citation
        loc2 = CitationLocation(
            manuscript_id=manuscript.id,
            citation_key="Orphan2024",
            file_path="test.tex"
        )
        test_session.add_all([loc1, loc2])
        test_session.commit()

        all_locations = service.get_manuscript_citations(manuscript.id)
        matched_only = service.get_manuscript_citations(manuscript.id, include_unmatched=False)

        assert len(all_locations) == 2
        assert len(matched_only) == 1


class TestCitationExport:
    """Tests for citation registry export."""

    def test_export_json(self, test_session):
        """Test exporting citations as JSON."""
        import json

        service = CitationService(test_session)

        paper = Paper(title="Test Paper", citation_key="Test2024")
        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add_all([paper, manuscript])
        test_session.commit()

        location = CitationLocation(
            paper_id=paper.id,
            manuscript_id=manuscript.id,
            citation_key="Test2024",
            file_path="intro.tex",
            line_number=42
        )
        test_session.add(location)
        test_session.commit()

        output = service.export_registry(manuscript.id, format='json')
        data = json.loads(output)

        assert data['manuscript']['name'] == "TestMS"
        assert len(data['citations']) == 1
        assert data['citations'][0]['citation_key'] == "Test2024"
        assert data['citations'][0]['paper_title'] == "Test Paper"

    def test_export_csv(self, test_session):
        """Test exporting citations as CSV."""
        service = CitationService(test_session)

        paper = Paper(title="Test Paper", citation_key="Test2024")
        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add_all([paper, manuscript])
        test_session.commit()

        location = CitationLocation(
            paper_id=paper.id,
            manuscript_id=manuscript.id,
            citation_key="Test2024",
            file_path="intro.tex",
            line_number=42
        )
        test_session.add(location)
        test_session.commit()

        output = service.export_registry(manuscript.id, format='csv')

        assert 'citation_key' in output  # Header
        assert 'Test2024' in output
        assert 'Test Paper' in output

    def test_export_invalid_format(self, test_session):
        """Test that invalid export format raises error."""
        service = CitationService(test_session)

        manuscript = Manuscript(name="TestMS", project_path="/test")
        test_session.add(manuscript)
        test_session.commit()

        with pytest.raises(ValueError, match="Unsupported format"):
            service.export_registry(manuscript.id, format='invalid')

    def test_export_nonexistent_manuscript(self, test_session):
        """Test exporting from nonexistent manuscript."""
        service = CitationService(test_session)

        with pytest.raises(ValueError, match="not found"):
            service.export_registry(999)


class TestCitePatterns:
    """Tests for citation regex pattern matching."""

    def test_cite_pattern_basic(self):
        """Test matching basic \\cite{key}."""
        pattern = CitationService.CITE_PATTERN
        match = pattern.search(r'\cite{Author2024}')
        assert match
        assert match.group(1) == "Author2024"

    def test_cite_pattern_optional_arg(self):
        """Test matching \\cite[optional]{key}."""
        pattern = CitationService.CITE_PATTERN
        match = pattern.search(r'\cite[p.~42]{Author2024}')
        assert match
        assert match.group(1) == "Author2024"

    def test_cite_pattern_citet(self):
        """Test matching \\citet{key}."""
        pattern = CitationService.CITE_PATTERN
        match = pattern.search(r'\citet{Author2024}')
        assert match
        assert match.group(1) == "Author2024"

    def test_cite_pattern_citep(self):
        """Test matching \\citep{key}."""
        pattern = CitationService.CITE_PATTERN
        match = pattern.search(r'\citep{Author2024}')
        assert match
        assert match.group(1) == "Author2024"

    def test_cite_pattern_citeauthor(self):
        """Test matching \\citeauthor{key}."""
        pattern = CitationService.CITE_PATTERN
        match = pattern.search(r'\citeauthor{Author2024}')
        assert match
        assert match.group(1) == "Author2024"

    def test_cite_pattern_multiple_keys(self):
        """Test matching multiple comma-separated keys."""
        pattern = CitationService.CITE_PATTERN
        match = pattern.search(r'\cite{A2024, B2023, C2022}')
        assert match
        keys = [k.strip() for k in match.group(1).split(',')]
        assert keys == ["A2024", "B2023", "C2022"]
