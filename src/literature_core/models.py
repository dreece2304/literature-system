"""SQLAlchemy models for literature database."""
from sqlalchemy import (
    Column, Integer, String, Text, Float,
    DateTime, ForeignKey, Table, JSON, Index
)
from sqlalchemy.orm import declarative_base, relationship, backref
from sqlalchemy.sql import func

Base = declarative_base()

# Association tables for many-to-many relationships
paper_authors = Table(
    'paper_authors',
    Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id', ondelete='CASCADE'), index=True),
    Column('author_id', Integer, ForeignKey('authors.id', ondelete='CASCADE'), index=True),
    Column('position', Integer),  # Author order
    Index('ix_paper_authors_both', 'paper_id', 'author_id'),  # Covering index
)

paper_tags = Table(
    'paper_tags',
    Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id', ondelete='CASCADE'), index=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'), index=True),
)

paper_collections = Table(
    'paper_collections',
    Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id', ondelete='CASCADE'), index=True),
    Column('collection_id', Integer, ForeignKey('collections.id', ondelete='CASCADE'), index=True),
)


class Paper(Base):
    __tablename__ = 'papers'
    __table_args__ = (
        # Composite index for common filter combination
        Index('ix_papers_year_status', 'year', 'read_status'),
    )

    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    abstract = Column(Text)
    year = Column(Integer, index=True)
    doi = Column(String(100), unique=True, nullable=True)
    arxiv_id = Column(String(50), unique=True, nullable=True)
    pubmed_id = Column(String(50), unique=True, nullable=True)

    # File management
    file_path = Column(String(500))
    file_hash = Column(String(64))  # SHA256 hash for deduplication

    # Zotero integration
    zotero_key = Column(String(50), unique=True, nullable=True)
    zotero_version = Column(Integer)

    # Metadata
    journal = Column(String(200))
    volume = Column(String(50))
    issue = Column(String(50))
    pages = Column(String(50))
    publisher = Column(String(200))

    # Citation tracking
    citation_key = Column(String(100), unique=True, nullable=True, index=True)
    citation_count = Column(Integer, default=0)

    # User interaction
    date_added = Column(DateTime, default=func.now(), index=True)
    date_modified = Column(DateTime, onupdate=func.now())
    date_read = Column(DateTime)
    rating = Column(Integer, index=True)  # 1-5 stars
    read_status = Column(String(20), default='unread', index=True)  # unread, reading, read

    # Validation status (external database verification)
    validation_status = Column(String(20), default='unvalidated', index=True)  # unvalidated, verified, not_found, error
    validation_source = Column(String(50))  # crossref, semantic_scholar, openalex, etc.
    validation_date = Column(DateTime)
    validation_confidence = Column(Float)  # 0.0-1.0 confidence score

    # Extracted content
    full_text = Column(Text)
    word_count = Column(Integer)

    # Relationships
    authors = relationship('Author', secondary=paper_authors, back_populates='papers',
                           order_by=paper_authors.c.position)
    tags = relationship('Tag', secondary=paper_tags, back_populates='papers')
    collections = relationship('Collection', secondary=paper_collections, back_populates='papers')
    notes = relationship('Note', back_populates='paper', cascade='all, delete-orphan')
    citations_made = relationship('Citation', foreign_keys='Citation.citing_paper_id', back_populates='citing_paper')
    citations_received = relationship('Citation', foreign_keys='Citation.cited_paper_id', back_populates='cited_paper')


class Author(Base):
    __tablename__ = 'authors'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, index=True)
    orcid = Column(String(20), unique=True, nullable=True)
    email = Column(String(100))
    affiliation = Column(String(300))

    # Relationships
    papers = relationship('Paper', secondary=paper_authors, back_populates='authors')


class Tag(Base):
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50))  # topic, method, field, etc.
    color = Column(String(7))  # Hex color for UI

    # Relationships
    papers = relationship('Paper', secondary=paper_tags, back_populates='tags')


class Collection(Base):
    __tablename__ = 'collections'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey('collections.id'), index=True)

    # Zotero sync
    zotero_key = Column(String(50), unique=True, nullable=True)

    # Relationships
    papers = relationship('Paper', secondary=paper_collections, back_populates='collections')
    children = relationship('Collection')


class Note(Base):
    __tablename__ = 'notes'
    __table_args__ = (
        # Composite index for common filter combination
        Index('ix_notes_paper_type', 'paper_id', 'note_type'),
    )

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), index=True)
    content = Column(Text, nullable=False)
    note_type = Column(String(20), index=True)  # highlight, comment, summary
    page_number = Column(Integer)
    position = Column(String(100))  # JSON coordinates for highlights

    created_at = Column(DateTime, default=func.now())
    modified_at = Column(DateTime, onupdate=func.now())

    # Relationships
    paper = relationship('Paper', back_populates='notes')


class Citation(Base):
    __tablename__ = 'citations'

    id = Column(Integer, primary_key=True)
    citing_paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'))
    cited_paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'))
    context = Column(Text)  # Text around the citation

    # Relationships
    citing_paper = relationship('Paper', foreign_keys=[citing_paper_id], back_populates='citations_made')
    cited_paper = relationship('Paper', foreign_keys=[cited_paper_id], back_populates='citations_received')


class SearchIndex(Base):
    """Track what's been indexed for search."""
    __tablename__ = 'search_index'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'))
    indexed_at = Column(DateTime, default=func.now())
    index_version = Column(String(20))


class Manuscript(Base):
    """Track external manuscript projects for citation mapping."""
    __tablename__ = 'manuscripts'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    project_path = Column(String(500))
    tex_directory = Column(String(500))
    bib_file = Column(String(500))
    description = Column(Text)

    last_scanned = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    citation_locations = relationship('CitationLocation', back_populates='manuscript', cascade='all, delete-orphan')


class CitationLocation(Base):
    """Track where papers are cited in manuscripts."""
    __tablename__ = 'citation_locations'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=True)
    manuscript_id = Column(Integer, ForeignKey('manuscripts.id', ondelete='CASCADE'), nullable=False)

    citation_key = Column(String(100), nullable=False)
    file_path = Column(String(500))
    line_number = Column(Integer)
    context = Column(Text)
    section_inferred = Column(String(100))
    priority = Column(String(20))

    scan_date = Column(DateTime, default=func.now())

    # Relationships
    paper = relationship('Paper', backref='citation_locations')
    manuscript = relationship('Manuscript', back_populates='citation_locations')


class PaperContent(Base):
    """AI-extracted structured content from papers."""
    __tablename__ = 'paper_contents'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), unique=True, nullable=False)

    extraction_date = Column(DateTime, default=func.now())
    extraction_depth = Column(String(50))
    schema_version = Column(String(20), default='1.0')
    extractor_model = Column(String(100))

    paper_type = Column(String(50))
    topics = Column(JSON)
    one_sentence_summary = Column(Text)

    key_findings = Column(JSON)
    methodology_summary = Column(Text)
    structured_data = Column(JSON)

    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    paper = relationship('Paper', backref=backref('content', uselist=False))


class ProjectRelevance(Base):
    """Paper relevance to specific research projects."""
    __tablename__ = 'project_relevances'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False)
    project_name = Column(String(200), nullable=False)

    overall_relevance = Column(String(20))
    relevance_summary = Column(Text)
    primary_use = Column(String(100))

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    paper = relationship('Paper', backref='project_relevances')
