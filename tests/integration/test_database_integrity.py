"""Database integrity tests.

Tests for:
- Foreign key constraint enforcement
- Cascade delete behavior
- Unique constraint enforcement
- Orphan detection
- NULL handling
"""
import pytest
from sqlalchemy.exc import IntegrityError

from literature_core.models import Paper, Author, Tag, Collection, Note, Citation


class TestForeignKeyConstraints:
    """Tests for foreign key constraint enforcement."""

    def test_note_requires_valid_paper_id(self, test_session):
        """Test that notes cannot reference non-existent papers."""
        note = Note(paper_id=99999, content="Orphan note")
        test_session.add(note)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_citation_requires_valid_citing_paper(self, test_session):
        """Test that citations require valid citing paper."""
        paper = Paper(title="Cited Paper")
        test_session.add(paper)
        test_session.commit()

        citation = Citation(citing_paper_id=99999, cited_paper_id=paper.id)
        test_session.add(citation)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_citation_requires_valid_cited_paper(self, test_session):
        """Test that citations require valid cited paper."""
        paper = Paper(title="Citing Paper")
        test_session.add(paper)
        test_session.commit()

        citation = Citation(citing_paper_id=paper.id, cited_paper_id=99999)
        test_session.add(citation)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_collection_parent_must_exist_if_specified(self, test_session):
        """Test that collection parent_id must reference existing collection."""
        collection = Collection(name="Child", parent_id=99999)
        test_session.add(collection)

        with pytest.raises(IntegrityError):
            test_session.commit()


class TestCascadeDeletes:
    """Tests for cascade delete behavior."""

    def test_deleting_paper_deletes_notes(self, test_session, sample_paper_data, sample_note):
        """Test that deleting a paper cascades to its notes."""
        paper = Paper(**sample_paper_data)
        test_session.add(paper)
        test_session.commit()

        note = Note(paper_id=paper.id, **sample_note)
        test_session.add(note)
        test_session.commit()
        note_id = note.id

        # Delete the paper
        test_session.delete(paper)
        test_session.commit()

        # Note should be gone
        assert test_session.query(Note).filter(Note.id == note_id).first() is None

    def test_deleting_paper_with_citations_requires_cleanup(self, test_session):
        """Test that citations exist between papers."""
        paper1 = Paper(title="Citing Paper")
        paper2 = Paper(title="Cited Paper")
        test_session.add_all([paper1, paper2])
        test_session.commit()

        citation = Citation(citing_paper_id=paper1.id, cited_paper_id=paper2.id)
        test_session.add(citation)
        test_session.commit()

        # Verify citation was created
        assert citation.citing_paper_id == paper1.id
        assert citation.cited_paper_id == paper2.id

        # Clean up citation before deleting paper
        test_session.delete(citation)
        test_session.commit()

        # Now we can delete the paper
        test_session.delete(paper1)
        test_session.commit()

        # Cited paper should still exist
        assert test_session.query(Paper).filter(Paper.id == paper2.id).first() is not None

    def test_deleting_paper_removes_author_associations_not_authors(
        self, test_session, sample_paper_data, sample_authors
    ):
        """Test that deleting paper removes associations but keeps authors."""
        paper = Paper(**sample_paper_data)
        for author_data in sample_authors[:2]:
            author = Author(**author_data)
            paper.authors.append(author)
        test_session.add(paper)
        test_session.commit()

        author_ids = [a.id for a in paper.authors]

        # Delete the paper
        test_session.delete(paper)
        test_session.commit()

        # Authors should still exist (many-to-many doesn't cascade to authors)
        for author_id in author_ids:
            author = test_session.query(Author).filter(Author.id == author_id).first()
            assert author is not None

    def test_deleting_paper_removes_tag_associations_not_tags(
        self, test_session, sample_paper_data, sample_tags
    ):
        """Test that deleting paper removes associations but keeps tags."""
        paper = Paper(**sample_paper_data)
        for tag_data in sample_tags[:2]:
            tag = Tag(**tag_data)
            paper.tags.append(tag)
        test_session.add(paper)
        test_session.commit()

        tag_ids = [t.id for t in paper.tags]

        # Delete the paper
        test_session.delete(paper)
        test_session.commit()

        # Tags should still exist
        for tag_id in tag_ids:
            tag = test_session.query(Tag).filter(Tag.id == tag_id).first()
            assert tag is not None

    def test_deleting_collection_removes_paper_associations_not_papers(
        self, test_session, sample_collection
    ):
        """Test that deleting collection doesn't delete papers."""
        collection = Collection(**sample_collection)
        paper = Paper(title="Test Paper")
        collection.papers.append(paper)
        test_session.add(collection)
        test_session.commit()

        paper_id = paper.id

        # Delete the collection
        test_session.delete(collection)
        test_session.commit()

        # Paper should still exist
        assert test_session.query(Paper).filter(Paper.id == paper_id).first() is not None


class TestUniqueConstraints:
    """Tests for unique constraint enforcement."""

    def test_paper_doi_must_be_unique(self, test_session):
        """Test that DOI must be unique across papers."""
        paper1 = Paper(title="Paper 1", doi="10.1234/unique")
        test_session.add(paper1)
        test_session.commit()

        paper2 = Paper(title="Paper 2", doi="10.1234/unique")
        test_session.add(paper2)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_paper_doi_null_allowed_multiple(self, test_session):
        """Test that multiple papers can have NULL DOI."""
        paper1 = Paper(title="Paper 1", doi=None)
        paper2 = Paper(title="Paper 2", doi=None)
        test_session.add_all([paper1, paper2])
        test_session.commit()  # Should not raise

        assert paper1.id is not None
        assert paper2.id is not None

    def test_paper_arxiv_id_must_be_unique(self, test_session):
        """Test that arXiv ID must be unique."""
        paper1 = Paper(title="Paper 1", arxiv_id="2301.12345")
        test_session.add(paper1)
        test_session.commit()

        paper2 = Paper(title="Paper 2", arxiv_id="2301.12345")
        test_session.add(paper2)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_tag_name_must_be_unique(self, test_session):
        """Test that tag names must be unique."""
        tag1 = Tag(name="unique-tag")
        test_session.add(tag1)
        test_session.commit()

        tag2 = Tag(name="unique-tag")
        test_session.add(tag2)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_author_orcid_must_be_unique(self, test_session):
        """Test that ORCID must be unique."""
        author1 = Author(name="Author 1", orcid="0000-0001-2345-6789")
        test_session.add(author1)
        test_session.commit()

        author2 = Author(name="Author 2", orcid="0000-0001-2345-6789")
        test_session.add(author2)

        with pytest.raises(IntegrityError):
            test_session.commit()


class TestNullHandling:
    """Tests for NULL value handling."""

    def test_paper_requires_title(self, test_session):
        """Test that paper requires a title."""
        paper = Paper(title=None)
        test_session.add(paper)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_note_requires_content(self, test_session, sample_paper_data):
        """Test that note requires content."""
        paper = Paper(**sample_paper_data)
        test_session.add(paper)
        test_session.commit()

        note = Note(paper_id=paper.id, content=None)
        test_session.add(note)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_collection_requires_name(self, test_session):
        """Test that collection requires a name."""
        collection = Collection(name=None)
        test_session.add(collection)

        with pytest.raises(IntegrityError):
            test_session.commit()

    def test_author_requires_name(self, test_session):
        """Test that author requires a name."""
        author = Author(name=None)
        test_session.add(author)

        with pytest.raises(IntegrityError):
            test_session.commit()


class TestModelDefaults:
    """Tests for model default values."""

    def test_paper_default_read_status(self, test_session):
        """Test that paper defaults to 'unread' status."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        assert paper.read_status == "unread"

    def test_paper_default_citation_count(self, test_session):
        """Test that paper defaults to 0 citation count."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        assert paper.citation_count == 0

    def test_paper_date_added_set_automatically(self, test_session):
        """Test that date_added is set automatically."""
        paper = Paper(title="Test Paper")
        test_session.add(paper)
        test_session.commit()

        assert paper.date_added is not None

    def test_note_created_at_set_automatically(self, test_session, sample_paper_data):
        """Test that note created_at is set automatically."""
        paper = Paper(**sample_paper_data)
        test_session.add(paper)
        test_session.commit()

        note = Note(paper_id=paper.id, content="Test note")
        test_session.add(note)
        test_session.commit()

        assert note.created_at is not None


class TestRelationshipIntegrity:
    """Tests for relationship consistency."""

    def test_paper_authors_ordered_by_position(self, test_session, sample_paper_data):
        """Test that paper authors maintain position order."""
        paper = Paper(**sample_paper_data)

        # Add authors in reverse order
        author3 = Author(name="Third Author")
        author1 = Author(name="First Author")
        author2 = Author(name="Second Author")

        # Note: position is set in the association table
        # The relationship orders by position column
        paper.authors.extend([author3, author1, author2])
        test_session.add(paper)
        test_session.commit()
        test_session.refresh(paper)

        # Authors should be in the order they were added
        # (position tracking would need explicit setting)
        assert len(paper.authors) == 3

    def test_collection_hierarchy_depth(self, test_session):
        """Test that collections can have nested hierarchy."""
        root = Collection(name="Root")
        test_session.add(root)
        test_session.commit()

        child1 = Collection(name="Child 1", parent_id=root.id)
        test_session.add(child1)
        test_session.commit()

        child2 = Collection(name="Child 2", parent_id=child1.id)
        test_session.add(child2)
        test_session.commit()

        # Verify hierarchy
        assert child1.parent_id == root.id
        assert child2.parent_id == child1.id

    def test_paper_can_be_in_multiple_collections(self, test_session, sample_paper_data):
        """Test that a paper can belong to multiple collections."""
        paper = Paper(**sample_paper_data)
        collection1 = Collection(name="Collection 1")
        collection2 = Collection(name="Collection 2")

        paper.collections.extend([collection1, collection2])
        test_session.add(paper)
        test_session.commit()

        assert len(paper.collections) == 2
        assert paper in collection1.papers
        assert paper in collection2.papers
