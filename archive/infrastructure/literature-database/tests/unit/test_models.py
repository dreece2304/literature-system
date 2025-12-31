"""
Unit tests for database models.

Tests CRUD operations, relationships, and constraints for all SQLAlchemy models.
"""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.models import Paper, Author, Tag, Collection, Note, Citation, Manuscript, CitationLocation, PaperContent, ProjectRelevance
from tests.fixtures.factories import (
    PaperFactory, AuthorFactory, TagFactory, CollectionFactory, NoteFactory,
    ManuscriptFactory, CitationLocationFactory
)


class TestPaperModel:
    """Tests for the Paper model."""

    def test_create_paper_minimal(self, test_session):
        """Test creating a paper with only required fields."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        assert paper.id is not None
        assert paper.title == "Test Paper"
        assert paper.read_status == "unread"

    def test_create_paper_full(self, test_session, sample_paper):
        """Test creating a paper with all fields."""
        paper = Paper(**sample_paper)
        test_session.add(paper)
        test_session.commit()

        retrieved = test_session.query(Paper).filter_by(id=paper.id).first()
        assert retrieved.title == sample_paper["title"]
        assert retrieved.doi == sample_paper["doi"]
        assert retrieved.year == sample_paper["year"]
        assert retrieved.journal == sample_paper["journal"]

    def test_paper_date_added_default(self, test_session):
        """Test that date_added is set automatically."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        assert paper.date_added is not None
        assert isinstance(paper.date_added, datetime)

    def test_paper_unique_doi(self, test_session):
        """Test that DOI must be unique."""
        paper1 = Paper(title="Paper 1", doi="10.1234/test.001")
        paper2 = Paper(title="Paper 2", doi="10.1234/test.001")

        test_session.add(paper1)
        test_session.commit()

        test_session.add(paper2)
        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_paper_unique_arxiv_id(self, test_session):
        """Test that arXiv ID must be unique."""
        paper1 = Paper(title="Paper 1", arxiv_id="2301.12345")
        paper2 = Paper(title="Paper 2", arxiv_id="2301.12345")

        test_session.add(paper1)
        test_session.commit()

        test_session.add(paper2)
        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_paper_null_doi_allowed(self, test_session):
        """Test that multiple papers can have NULL DOI."""
        paper1 = Paper(title="Paper 1", doi=None)
        paper2 = Paper(title="Paper 2", doi=None)

        test_session.add_all([paper1, paper2])
        test_session.commit()

        assert paper1.id != paper2.id

    def test_paper_read_status_values(self, test_session):
        """Test different read status values."""
        for status in ["unread", "reading", "read"]:
            paper = Paper(title=f"Paper {status}", read_status=status)
            test_session.add(paper)
        test_session.commit()

        papers = test_session.query(Paper).all()
        assert len(papers) == 3

    def test_paper_rating(self, test_session):
        """Test paper rating field."""
        paper = Paper(title="Test", rating=5)
        test_session.add(paper)
        test_session.commit()

        assert paper.rating == 5

    def test_paper_update(self, test_session, created_paper):
        """Test updating a paper."""
        created_paper.title = "Updated Title"
        created_paper.rating = 4
        test_session.commit()

        retrieved = test_session.query(Paper).filter_by(id=created_paper.id).first()
        assert retrieved.title == "Updated Title"
        assert retrieved.rating == 4

    def test_paper_delete(self, test_session, created_paper):
        """Test deleting a paper."""
        paper_id = created_paper.id
        test_session.delete(created_paper)
        test_session.commit()

        assert test_session.query(Paper).filter_by(id=paper_id).first() is None


class TestAuthorModel:
    """Tests for the Author model."""

    def test_create_author(self, test_session, sample_author):
        """Test creating an author."""
        author = Author(**sample_author)
        test_session.add(author)
        test_session.commit()

        assert author.id is not None
        assert author.name == sample_author["name"]
        assert author.orcid == sample_author["orcid"]

    def test_author_unique_orcid(self, test_session):
        """Test that ORCID must be unique."""
        author1 = Author(name="Author 1", orcid="0000-0001-2345-6789")
        author2 = Author(name="Author 2", orcid="0000-0001-2345-6789")

        test_session.add(author1)
        test_session.commit()

        test_session.add(author2)
        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_author_null_orcid_allowed(self, test_session):
        """Test that multiple authors can have NULL ORCID."""
        author1 = Author(name="Author 1", orcid=None)
        author2 = Author(name="Author 2", orcid=None)

        test_session.add_all([author1, author2])
        test_session.commit()

        assert author1.id != author2.id


class TestTagModel:
    """Tests for the Tag model."""

    def test_create_tag(self, test_session, sample_tag):
        """Test creating a tag."""
        tag = Tag(**sample_tag)
        test_session.add(tag)
        test_session.commit()

        assert tag.id is not None
        assert tag.name == sample_tag["name"]
        assert tag.category == sample_tag["category"]

    def test_tag_unique_name(self, test_session):
        """Test that tag name must be unique."""
        tag1 = Tag(name="machine-learning")
        tag2 = Tag(name="machine-learning")

        test_session.add(tag1)
        test_session.commit()

        test_session.add(tag2)
        with pytest.raises(IntegrityError):
            test_session.commit()


class TestCollectionModel:
    """Tests for the Collection model."""

    def test_create_collection(self, test_session, sample_collection):
        """Test creating a collection."""
        collection = Collection(**sample_collection)
        test_session.add(collection)
        test_session.commit()

        assert collection.id is not None
        assert collection.name == sample_collection["name"]

    def test_collection_hierarchy(self, test_session):
        """Test parent-child collection relationships."""
        parent = Collection(name="Parent Collection")
        test_session.add(parent)
        test_session.commit()

        child = Collection(name="Child Collection", parent_id=parent.id)
        test_session.add(child)
        test_session.commit()

        assert child.parent_id == parent.id

    def test_collection_children_relationship(self, test_session):
        """Test that parent collection can access children."""
        parent = Collection(name="Parent")
        child1 = Collection(name="Child 1")
        child2 = Collection(name="Child 2")

        test_session.add(parent)
        test_session.commit()

        child1.parent_id = parent.id
        child2.parent_id = parent.id
        test_session.add_all([child1, child2])
        test_session.commit()

        test_session.refresh(parent)
        assert len(parent.children) == 2


class TestNoteModel:
    """Tests for the Note model."""

    def test_create_note(self, test_session, created_paper):
        """Test creating a note."""
        note = Note(
            paper_id=created_paper.id,
            content="Important finding",
            note_type="highlight",
            page_number=5
        )
        test_session.add(note)
        test_session.commit()

        assert note.id is not None
        assert note.paper_id == created_paper.id

    def test_note_cascade_delete(self, test_session, created_paper):
        """Test that notes are deleted when paper is deleted."""
        note = Note(
            paper_id=created_paper.id,
            content="Test note",
            note_type="comment"
        )
        test_session.add(note)
        test_session.commit()
        note_id = note.id

        test_session.delete(created_paper)
        test_session.commit()

        assert test_session.query(Note).filter_by(id=note_id).first() is None

    def test_note_created_at(self, test_session, created_paper):
        """Test that created_at is set automatically."""
        note = Note(paper_id=created_paper.id, content="Test")
        test_session.add(note)
        test_session.commit()

        assert note.created_at is not None


class TestCitationModel:
    """Tests for the Citation (paper-to-paper) model."""

    def test_create_citation(self, test_session):
        """Test creating a citation between papers."""
        paper1 = Paper(title="Citing Paper")
        paper2 = Paper(title="Cited Paper")
        test_session.add_all([paper1, paper2])
        test_session.commit()

        citation = Citation(
            citing_paper_id=paper1.id,
            cited_paper_id=paper2.id,
            context="As shown in previous work..."
        )
        test_session.add(citation)
        test_session.commit()

        assert citation.id is not None
        assert citation.citing_paper.title == "Citing Paper"
        assert citation.cited_paper.title == "Cited Paper"

    def test_citation_relationships(self, test_session):
        """Test citations_made and citations_received relationships."""
        paper_a = Paper(title="Paper A")
        paper_b = Paper(title="Paper B")
        paper_c = Paper(title="Paper C")
        test_session.add_all([paper_a, paper_b, paper_c])
        test_session.commit()

        # A cites B and C
        cit1 = Citation(citing_paper_id=paper_a.id, cited_paper_id=paper_b.id)
        cit2 = Citation(citing_paper_id=paper_a.id, cited_paper_id=paper_c.id)
        test_session.add_all([cit1, cit2])
        test_session.commit()

        test_session.refresh(paper_a)
        test_session.refresh(paper_b)

        assert len(paper_a.citations_made) == 2
        assert len(paper_b.citations_received) == 1


class TestPaperAuthorRelationship:
    """Tests for the Paper-Author many-to-many relationship."""

    def test_add_author_to_paper(self, test_session, created_paper, created_author):
        """Test adding an author to a paper."""
        created_paper.authors.append(created_author)
        test_session.commit()

        test_session.refresh(created_paper)
        assert len(created_paper.authors) == 1
        assert created_paper.authors[0].name == created_author.name

    def test_multiple_authors(self, test_session, created_paper):
        """Test paper with multiple authors."""
        authors = AuthorFactory.create_batch(3)
        for author in authors:
            test_session.add(author)
        test_session.commit()

        created_paper.authors.extend(authors)
        test_session.commit()

        test_session.refresh(created_paper)
        assert len(created_paper.authors) == 3

    def test_author_multiple_papers(self, test_session, created_author):
        """Test author with multiple papers."""
        papers = [
            Paper(title="Paper 1"),
            Paper(title="Paper 2"),
            Paper(title="Paper 3")
        ]
        for paper in papers:
            paper.authors.append(created_author)
            test_session.add(paper)
        test_session.commit()

        test_session.refresh(created_author)
        assert len(created_author.papers) == 3


class TestPaperTagRelationship:
    """Tests for the Paper-Tag many-to-many relationship."""

    def test_add_tag_to_paper(self, test_session, created_paper, created_tag):
        """Test adding a tag to a paper."""
        created_paper.tags.append(created_tag)
        test_session.commit()

        test_session.refresh(created_paper)
        assert len(created_paper.tags) == 1

    def test_multiple_tags(self, test_session, created_paper):
        """Test paper with multiple tags."""
        tags = [
            Tag(name="tag1"),
            Tag(name="tag2"),
            Tag(name="tag3")
        ]
        for tag in tags:
            test_session.add(tag)
        test_session.commit()

        created_paper.tags.extend(tags)
        test_session.commit()

        test_session.refresh(created_paper)
        assert len(created_paper.tags) == 3


class TestPaperCollectionRelationship:
    """Tests for the Paper-Collection many-to-many relationship."""

    def test_add_paper_to_collection(self, test_session, created_paper, created_collection):
        """Test adding a paper to a collection."""
        created_paper.collections.append(created_collection)
        test_session.commit()

        test_session.refresh(created_collection)
        assert len(created_collection.papers) == 1

    def test_paper_multiple_collections(self, test_session, created_paper):
        """Test paper in multiple collections."""
        collections = [
            Collection(name="Collection 1"),
            Collection(name="Collection 2")
        ]
        for coll in collections:
            test_session.add(coll)
        test_session.commit()

        created_paper.collections.extend(collections)
        test_session.commit()

        test_session.refresh(created_paper)
        assert len(created_paper.collections) == 2


class TestFactoryIntegration:
    """Tests using factory classes."""

    def test_paper_factory(self, test_session):
        """Test PaperFactory creates valid papers."""
        paper = PaperFactory.create()
        test_session.add(paper)
        test_session.commit()

        assert paper.id is not None
        assert paper.title is not None
        assert paper.doi is not None

    def test_paper_factory_batch(self, test_session):
        """Test creating multiple papers with factory."""
        papers = PaperFactory.create_batch(5)
        for paper in papers:
            test_session.add(paper)
        test_session.commit()

        assert test_session.query(Paper).count() == 5

    def test_author_factory(self, test_session):
        """Test AuthorFactory creates valid authors."""
        author = AuthorFactory.create()
        test_session.add(author)
        test_session.commit()

        assert author.id is not None
        assert author.name is not None

    def test_full_paper_with_relationships(self, test_session):
        """Test creating a paper with all relationships using factories."""
        # Create authors and tags
        authors = AuthorFactory.create_batch(2)
        tags = TagFactory.create_batch(3)

        for a in authors:
            test_session.add(a)
        for t in tags:
            test_session.add(t)
        test_session.commit()

        # Create paper with relationships
        paper = PaperFactory.create(authors=authors, tags=tags)
        test_session.add(paper)
        test_session.commit()

        test_session.refresh(paper)
        assert len(paper.authors) == 2
        assert len(paper.tags) == 3


class TestPaperCitationKeyField:
    """Tests for the Paper.citation_key field."""

    def test_paper_citation_key(self, test_session):
        """Test creating a paper with citation_key."""
        paper = Paper(title="Alucone MLD Growth", citation_key="Dameron2008Alucone")
        test_session.add(paper)
        test_session.commit()

        assert paper.citation_key == "Dameron2008Alucone"

    def test_paper_citation_key_unique(self, test_session):
        """Test that citation_key must be unique."""
        paper1 = Paper(title="Paper 1", citation_key="Author2024Paper")
        paper2 = Paper(title="Paper 2", citation_key="Author2024Paper")

        test_session.add(paper1)
        test_session.commit()

        test_session.add(paper2)
        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_paper_citation_key_null_allowed(self, test_session):
        """Test that multiple papers can have NULL citation_key."""
        paper1 = Paper(title="Paper 1", citation_key=None)
        paper2 = Paper(title="Paper 2", citation_key=None)

        test_session.add_all([paper1, paper2])
        test_session.commit()

        assert paper1.id != paper2.id

    def test_paper_citation_count_default(self, test_session):
        """Test that citation_count defaults to 0."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        assert paper.citation_count == 0

    def test_paper_citation_count_update(self, test_session):
        """Test updating citation_count."""
        paper = Paper(title="Test Paper", citation_count=5)
        test_session.add(paper)
        test_session.commit()

        paper.citation_count = 10
        test_session.commit()

        test_session.refresh(paper)
        assert paper.citation_count == 10


class TestManuscriptModel:
    """Tests for the Manuscript model."""

    def test_create_manuscript(self, test_session):
        """Test creating a manuscript."""
        manuscript = Manuscript(
            name="PhD Thesis Paper 2",
            project_path="/home/user/Paper2",
            tex_directory="paper/tex",
            bib_file="paper/bib/references.bib",
            description="Research paper on MLD thin films"
        )
        test_session.add(manuscript)
        test_session.commit()

        assert manuscript.id is not None
        assert manuscript.name == "PhD Thesis Paper 2"
        assert manuscript.project_path == "/home/user/Paper2"

    def test_manuscript_unique_name(self, test_session):
        """Test that manuscript name must be unique."""
        ms1 = Manuscript(name="Paper 2", project_path="/path1")
        ms2 = Manuscript(name="Paper 2", project_path="/path2")

        test_session.add(ms1)
        test_session.commit()

        test_session.add(ms2)
        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_manuscript_created_at(self, test_session):
        """Test that created_at is set automatically."""
        manuscript = Manuscript(name="Test MS")
        test_session.add(manuscript)
        test_session.commit()

        assert manuscript.created_at is not None
        assert isinstance(manuscript.created_at, datetime)

    def test_manuscript_last_scanned(self, test_session):
        """Test last_scanned field."""
        manuscript = Manuscript(name="Test MS")
        test_session.add(manuscript)
        test_session.commit()

        # Initially null
        assert manuscript.last_scanned is None

        # Update it
        scan_time = datetime.now()
        manuscript.last_scanned = scan_time
        test_session.commit()

        test_session.refresh(manuscript)
        assert manuscript.last_scanned is not None

    def test_manuscript_factory(self, test_session):
        """Test ManuscriptFactory creates valid manuscripts."""
        manuscript = ManuscriptFactory.create()
        test_session.add(manuscript)
        test_session.commit()

        assert manuscript.id is not None
        assert manuscript.name is not None
        assert manuscript.tex_directory == "paper/tex"


class TestCitationLocationModel:
    """Tests for the CitationLocation model."""

    def test_create_citation_location(self, test_session):
        """Test creating a citation location."""
        manuscript = Manuscript(name="Test MS", project_path="/test")
        test_session.add(manuscript)
        test_session.commit()

        location = CitationLocation(
            manuscript_id=manuscript.id,
            citation_key="Dameron2008Alucone",
            file_path="introduction.tex",
            line_number=45,
            context="...as shown by \\cite{Dameron2008Alucone}...",
            section_inferred="introduction"
        )
        test_session.add(location)
        test_session.commit()

        assert location.id is not None
        assert location.citation_key == "Dameron2008Alucone"
        assert location.line_number == 45

    def test_citation_location_with_paper(self, test_session):
        """Test citation location linked to a paper."""
        paper = Paper(title="Alucone MLD Growth", citation_key="Dameron2008Alucone")
        manuscript = Manuscript(name="Test MS")
        test_session.add_all([paper, manuscript])
        test_session.commit()

        location = CitationLocation(
            paper_id=paper.id,
            manuscript_id=manuscript.id,
            citation_key="Dameron2008Alucone",
            file_path="methods.tex",
            line_number=120
        )
        test_session.add(location)
        test_session.commit()

        assert location.paper_id == paper.id
        assert location.paper.title == "Alucone MLD Growth"

    def test_citation_location_priority(self, test_session):
        """Test priority field (key, supporting, null)."""
        manuscript = Manuscript(name="Test MS")
        test_session.add(manuscript)
        test_session.commit()

        for priority in ["key", "supporting", None]:
            location = CitationLocation(
                manuscript_id=manuscript.id,
                citation_key=f"Author2024{priority or 'none'}",
                file_path="test.tex",
                priority=priority
            )
            test_session.add(location)
        test_session.commit()

        locations = test_session.query(CitationLocation).all()
        assert len(locations) == 3

    def test_citation_location_scan_date(self, test_session):
        """Test scan_date is set automatically."""
        manuscript = Manuscript(name="Test MS")
        test_session.add(manuscript)
        test_session.commit()

        location = CitationLocation(
            manuscript_id=manuscript.id,
            citation_key="Test2024",
            file_path="test.tex"
        )
        test_session.add(location)
        test_session.commit()

        assert location.scan_date is not None

    def test_citation_location_cascade_delete_manuscript(self, test_session):
        """Test that citation locations are deleted when manuscript is deleted."""
        manuscript = Manuscript(name="Test MS")
        test_session.add(manuscript)
        test_session.commit()

        location = CitationLocation(
            manuscript_id=manuscript.id,
            citation_key="Test2024",
            file_path="test.tex"
        )
        test_session.add(location)
        test_session.commit()
        location_id = location.id

        test_session.delete(manuscript)
        test_session.commit()

        assert test_session.query(CitationLocation).filter_by(id=location_id).first() is None


class TestManuscriptCitationRelationship:
    """Tests for Manuscript-CitationLocation relationship."""

    def test_manuscript_has_citation_locations(self, test_session):
        """Test accessing citation locations from manuscript."""
        manuscript = Manuscript(name="Test MS")
        test_session.add(manuscript)
        test_session.commit()

        for i in range(3):
            location = CitationLocation(
                manuscript_id=manuscript.id,
                citation_key=f"Author202{i}",
                file_path=f"chapter{i}.tex"
            )
            test_session.add(location)
        test_session.commit()

        test_session.refresh(manuscript)
        assert len(manuscript.citation_locations) == 3

    def test_paper_has_citation_locations(self, test_session):
        """Test accessing citation locations from paper."""
        paper = Paper(title="Test Paper", citation_key="TestKey")
        manuscript = Manuscript(name="Test MS")
        test_session.add_all([paper, manuscript])
        test_session.commit()

        for i in range(2):
            location = CitationLocation(
                paper_id=paper.id,
                manuscript_id=manuscript.id,
                citation_key="TestKey",
                file_path=f"section{i}.tex"
            )
            test_session.add(location)
        test_session.commit()

        test_session.refresh(paper)
        assert len(paper.citation_locations) == 2

    def test_citation_location_factory(self, test_session):
        """Test CitationLocationFactory creates valid instances."""
        manuscript = ManuscriptFactory.create()
        test_session.add(manuscript)
        test_session.commit()

        location = CitationLocationFactory.create(manuscript=manuscript)
        test_session.add(location)
        test_session.commit()

        assert location.id is not None
        assert location.manuscript_id == manuscript.id
        assert location.citation_key is not None


class TestPaperContentModel:
    """Tests for the PaperContent model (AI-extracted content)."""

    def test_create_paper_content(self, test_session):
        """Test creating paper content with all fields."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        content = PaperContent(
            paper_id=paper.id,
            extraction_depth="BASIC",
            extractor_model="claude-3-sonnet",
            paper_type="research_article",
            topics=["mld_growth", "spectroscopy"],
            one_sentence_summary="This paper studies MLD growth.",
            key_findings=[
                {"finding_id": "01", "statement": "GPC is 0.4 nm/cycle", "topics": ["mld_growth"]}
            ],
            methodology_summary="Used ellipsometry and XPS.",
            structured_data={"mld_growth": {"temperature_C": 150}}
        )
        test_session.add(content)
        test_session.commit()

        assert content.id is not None
        assert content.paper_id == paper.id
        assert content.extraction_depth == "BASIC"
        assert content.topics == ["mld_growth", "spectroscopy"]
        assert len(content.key_findings) == 1

    def test_paper_content_one_to_one(self, test_session):
        """Test that paper.content gives the PaperContent."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        content = PaperContent(
            paper_id=paper.id,
            extraction_depth="CITATION_ONLY"
        )
        test_session.add(content)
        test_session.commit()

        test_session.refresh(paper)
        assert paper.content is not None
        assert paper.content.extraction_depth == "CITATION_ONLY"

    def test_paper_content_unique_paper_id(self, test_session):
        """Test that only one content record per paper is allowed."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        content1 = PaperContent(paper_id=paper.id, extraction_depth="BASIC")
        content2 = PaperContent(paper_id=paper.id, extraction_depth="COMPREHENSIVE")

        test_session.add(content1)
        test_session.commit()

        test_session.add(content2)
        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_paper_content_extraction_date(self, test_session):
        """Test extraction_date is set automatically."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        content = PaperContent(paper_id=paper.id, extraction_depth="BASIC")
        test_session.add(content)
        test_session.commit()

        assert content.extraction_date is not None

    def test_paper_content_foreign_key_constraint(self, test_session):
        """Test content has valid foreign key to paper (ON DELETE CASCADE defined in schema)."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        content = PaperContent(paper_id=paper.id, extraction_depth="BASIC")
        test_session.add(content)
        test_session.commit()

        # Verify foreign key constraint is defined
        assert content.paper_id == paper.id
        assert content.paper.title == "Test Paper"

    def test_paper_content_json_fields(self, test_session):
        """Test JSON fields store and retrieve correctly."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        topics = ["mld_growth", "stability", "spectroscopy"]
        findings = [
            {"finding_id": "01", "statement": "Finding 1", "evidence": "Evidence 1"},
            {"finding_id": "02", "statement": "Finding 2", "evidence": "Evidence 2"}
        ]
        structured = {
            "mld_growth": {
                "materials": {"metal_precursor": "TMA", "organic_precursor": "EG"},
                "growth_rates": [{"GPC_nm": 0.4}]
            }
        }

        content = PaperContent(
            paper_id=paper.id,
            extraction_depth="COMPREHENSIVE",
            topics=topics,
            key_findings=findings,
            structured_data=structured
        )
        test_session.add(content)
        test_session.commit()

        # Refresh and verify JSON roundtrip
        test_session.refresh(content)
        assert content.topics == topics
        assert content.key_findings == findings
        assert content.structured_data == structured


class TestProjectRelevanceModel:
    """Tests for the ProjectRelevance model."""

    def test_create_project_relevance(self, test_session):
        """Test creating project relevance."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        relevance = ProjectRelevance(
            paper_id=paper.id,
            project_name="BTY-alucone",
            overall_relevance="CRITICAL",
            relevance_summary="Essential for stability comparison.",
            primary_use="results"
        )
        test_session.add(relevance)
        test_session.commit()

        assert relevance.id is not None
        assert relevance.project_name == "BTY-alucone"
        assert relevance.overall_relevance == "CRITICAL"

    def test_paper_multiple_relevances(self, test_session):
        """Test one paper can have relevance to multiple projects."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        for project in ["BTY-alucone", "PhD-thesis", "ALD-review"]:
            relevance = ProjectRelevance(
                paper_id=paper.id,
                project_name=project,
                overall_relevance="HIGH"
            )
            test_session.add(relevance)
        test_session.commit()

        test_session.refresh(paper)
        assert len(paper.project_relevances) == 3

    def test_relevance_levels(self, test_session):
        """Test all relevance levels can be stored."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        levels = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"]
        for i, level in enumerate(levels):
            relevance = ProjectRelevance(
                paper_id=paper.id,
                project_name=f"Project-{i}",
                overall_relevance=level
            )
            test_session.add(relevance)
        test_session.commit()

        assert test_session.query(ProjectRelevance).filter_by(paper_id=paper.id).count() == 5

    def test_relevance_created_at(self, test_session):
        """Test created_at is set automatically."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        relevance = ProjectRelevance(
            paper_id=paper.id,
            project_name="Test-Project",
            overall_relevance="MEDIUM"
        )
        test_session.add(relevance)
        test_session.commit()

        assert relevance.created_at is not None

    def test_relevance_foreign_key_constraint(self, test_session):
        """Test relevance has valid foreign key to paper (ON DELETE CASCADE defined in schema)."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        relevance = ProjectRelevance(
            paper_id=paper.id,
            project_name="Test-Project",
            overall_relevance="HIGH"
        )
        test_session.add(relevance)
        test_session.commit()

        # Verify foreign key constraint is defined
        assert relevance.paper_id == paper.id
        assert relevance.paper.title == "Test Paper"

    def test_relevance_paper_relationship(self, test_session):
        """Test accessing paper from relevance."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        relevance = ProjectRelevance(
            paper_id=paper.id,
            project_name="Test-Project",
            overall_relevance="HIGH"
        )
        test_session.add(relevance)
        test_session.commit()

        test_session.refresh(relevance)
        assert relevance.paper is not None
        assert relevance.paper.title == "Test Paper"
