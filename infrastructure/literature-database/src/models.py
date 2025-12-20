"""Database models for literature database."""
from sqlalchemy import (
    Column, Integer, String, Text,
    DateTime, ForeignKey, Table, JSON
)
from sqlalchemy.orm import declarative_base, relationship, backref
from sqlalchemy.sql import func

Base = declarative_base()

# Association tables for many-to-many relationships
paper_authors = Table(
    'paper_authors',
    Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id', ondelete='CASCADE')),
    Column('author_id', Integer, ForeignKey('authors.id', ondelete='CASCADE')),
    Column('position', Integer)  # Author order
)

paper_tags = Table(
    'paper_tags',
    Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id', ondelete='CASCADE')),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete='CASCADE'))
)

paper_collections = Table(
    'paper_collections',
    Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id', ondelete='CASCADE')),
    Column('collection_id', Integer, ForeignKey('collections.id', ondelete='CASCADE'))
)


class Paper(Base):
    __tablename__ = 'papers'

    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    abstract = Column(Text)
    year = Column(Integer)
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
    citation_key = Column(String(100), unique=True, nullable=True)  # BibTeX key (AuthorYearFirstWord format)
    citation_count = Column(Integer, default=0)  # Cached count of citation locations

    # User interaction
    date_added = Column(DateTime, default=func.now())
    date_modified = Column(DateTime, onupdate=func.now())
    date_read = Column(DateTime)
    rating = Column(Integer)  # 1-5 stars
    read_status = Column(String(20), default='unread')  # unread, reading, read

    # Extracted content
    full_text = Column(Text)  # Extracted text from PDF
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
    name = Column(String(200), nullable=False)
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
    name = Column(String(200), nullable=False)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey('collections.id'))

    # Zotero sync
    zotero_key = Column(String(50), unique=True, nullable=True)

    # Relationships
    papers = relationship('Paper', secondary=paper_collections, back_populates='collections')
    children = relationship('Collection')


class Note(Base):
    __tablename__ = 'notes'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'))
    content = Column(Text, nullable=False)
    note_type = Column(String(20))  # highlight, comment, summary
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
    project_path = Column(String(500))  # e.g., /home/dreece23/Paper2
    tex_directory = Column(String(500))  # e.g., paper/tex (relative to project_path)
    bib_file = Column(String(500))  # e.g., paper/bib/references.bib
    description = Column(Text)

    # Scan tracking
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

    citation_key = Column(String(100), nullable=False)  # BibTeX key from \cite{}
    file_path = Column(String(500))  # Relative .tex file path
    line_number = Column(Integer)
    context = Column(Text)  # ~80 chars surrounding the citation
    section_inferred = Column(String(100))  # Inferred from filename/structure
    priority = Column(String(20))  # 'key', 'supporting', or null

    scan_date = Column(DateTime, default=func.now())

    # Relationships
    paper = relationship('Paper', backref='citation_locations')
    manuscript = relationship('Manuscript', back_populates='citation_locations')


class PaperContent(Base):
    """AI-extracted structured content from papers."""
    __tablename__ = 'paper_contents'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), unique=True, nullable=False)

    # Extraction metadata
    extraction_date = Column(DateTime, default=func.now())
    extraction_depth = Column(String(50))  # CITATION_ONLY, BASIC, COMPREHENSIVE
    schema_version = Column(String(20), default='1.0')
    extractor_model = Column(String(100))  # e.g., 'claude-3-sonnet', 'qwen-7b'

    # Universal fields (all papers)
    paper_type = Column(String(50))  # research_article, review, conference, book_chapter, thesis, preprint
    topics = Column(JSON)  # List of topic tags
    one_sentence_summary = Column(Text)

    # Structured data
    key_findings = Column(JSON)  # List of {finding_id, statement, evidence, topics}
    methodology_summary = Column(Text)

    # Domain-specific data (flexible JSON for mld_growth, spectroscopy, mechanisms, etc.)
    structured_data = Column(JSON)

    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    paper = relationship('Paper', backref=backref('content', uselist=False))


class ProjectRelevance(Base):
    """Paper relevance to specific research projects."""
    __tablename__ = 'project_relevances'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False)
    project_name = Column(String(200), nullable=False)  # e.g., 'BTY-alucone', 'PhD-thesis'

    overall_relevance = Column(String(20))  # CRITICAL, HIGH, MEDIUM, LOW, NONE
    relevance_summary = Column(Text)
    primary_use = Column(String(100))  # introduction, methods, results, discussion

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    paper = relationship('Paper', backref='project_relevances')
