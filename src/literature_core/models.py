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
    # Note: Full text is now stored in PaperChunk records (paper.chunks relationship)
    # Use PaperService.get_full_text(paper_id) to reconstruct full text from chunks
    word_count = Column(Integer)

    # Metadata provenance (tracks where paper data came from)
    metadata_source = Column(String(50), index=True)  # crossref, openalex, semantic_scholar, manual
    metadata_confidence = Column(Float)  # 0.0-1.0 confidence in metadata accuracy

    # Enrichment tracking (tracks what data is available/needed)
    enrichment_status = Column(String(50), default='pending', index=True)
    # Values: pending, needs_abstract, needs_pdf, needs_chunks, complete, failed

    # Import tracking
    import_method = Column(String(50))  # wizard, bibtex, external, manual, zotero
    import_date = Column(DateTime, default=func.now())

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


class PaperChunk(Base):
    """Text chunks extracted from PDF for sequential processing.

    Stores full PDF text split into manageable chunks for
    Claude to process sequentially and extract structured data.
    """
    __tablename__ = 'paper_chunks'
    __table_args__ = (
        Index('ix_paper_chunks_paper_order', 'paper_id', 'chunk_order'),
    )

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)

    chunk_order = Column(Integer, nullable=False)  # Order in document (0-indexed)
    content = Column(Text, nullable=False)
    word_count = Column(Integer)
    char_count = Column(Integer)

    # Page range for reference
    start_page = Column(Integer)
    end_page = Column(Integer)

    # Relationships
    paper = relationship('Paper', backref=backref('chunks', order_by='PaperChunk.chunk_order',
                                                   cascade='all, delete-orphan'))


class PaperTable(Base):
    """Tables extracted from PDF as markdown."""
    __tablename__ = 'paper_tables'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)

    table_order = Column(Integer, nullable=False)  # Order in document
    page_number = Column(Integer)

    markdown = Column(Text, nullable=False)
    caption = Column(Text)
    row_count = Column(Integer)
    col_count = Column(Integer)

    # Relationships
    paper = relationship('Paper', backref=backref('tables', order_by='PaperTable.table_order',
                                                   cascade='all, delete-orphan'))


class PaperFigure(Base):
    """Figure and table captions extracted from PDF."""
    __tablename__ = 'paper_figures'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)

    figure_type = Column(String(20), nullable=False)  # 'figure' or 'table'
    figure_number = Column(String(20), nullable=False)  # e.g., "1", "2a", "S1"
    caption = Column(Text, nullable=False)
    page_number = Column(Integer)

    # Relationships
    paper = relationship('Paper', backref=backref('figures', cascade='all, delete-orphan'))


class PaperReference(Base):
    """References extracted from a paper's bibliography/references section.

    Stores both raw reference text and parsed metadata for matching
    and potential import of referenced papers.
    """
    __tablename__ = 'paper_references'
    __table_args__ = (
        Index('ix_paper_refs_paper_order', 'paper_id', 'reference_order'),
    )

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)

    reference_order = Column(Integer, nullable=False)  # Order in references section
    raw_text = Column(Text, nullable=False)  # Full reference text as extracted

    # Parsed fields (best-effort extraction)
    parsed_title = Column(Text)
    parsed_authors = Column(Text)  # Comma-separated author names
    parsed_year = Column(Integer)
    parsed_journal = Column(String(500))
    parsed_doi = Column(String(100), index=True)
    parsed_arxiv_id = Column(String(50))

    # Matching status
    match_status = Column(String(20), default='unmatched', index=True)
    # Values: unmatched, matched, imported, skipped

    # Links to papers in database (if matched or imported)
    matched_paper_id = Column(Integer, ForeignKey('papers.id', ondelete='SET NULL'), index=True)

    # Confidence in parsed fields (0.0-1.0)
    parse_confidence = Column(Float)

    # Relationships
    paper = relationship('Paper', foreign_keys=[paper_id],
                        backref=backref('references', order_by='PaperReference.reference_order',
                                        cascade='all, delete-orphan'))
    matched_paper = relationship('Paper', foreign_keys=[matched_paper_id])


class ExtractionMetadata(Base):
    """Metadata about PDF extraction for a paper.

    Tracks extraction status and basic metrics.
    """
    __tablename__ = 'extraction_metadata'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), unique=True, nullable=False)

    extraction_method = Column(String(50))  # pdfplumber, pymupdf
    extraction_date = Column(DateTime, default=func.now())

    # Basic metrics
    chunk_count = Column(Integer)
    table_count = Column(Integer)
    figure_count = Column(Integer)
    reference_count = Column(Integer)
    word_count = Column(Integer)
    page_count = Column(Integer)

    # For re-extraction decisions
    pdf_hash = Column(String(64))  # To detect if PDF changed
    needs_reextraction = Column(Integer, default=0)

    # Chunking status (for auto-chunking workflow)
    chunking_status = Column(String(20), default='none')  # none, pending, processing, complete, failed
    chunking_error = Column(Text)  # Error message if chunking failed
    chunking_queued_at = Column(DateTime)  # When queued for processing

    # Relationships
    paper = relationship('Paper', backref=backref('extraction_metadata', uselist=False,
                                                   cascade='all, delete-orphan'))


class CitedClaim(Base):
    """Claims from a paper that cite other works.

    Tracks what claims a paper makes and which sources support them.
    Used for understanding citation context and building citation networks.
    """
    __tablename__ = 'cited_claims'
    __table_args__ = (
        Index('ix_cited_claims_paper_section', 'paper_id', 'section'),
    )

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)

    # The claim itself
    claim_text = Column(Text, nullable=False)  # The claim being made
    citation_marker = Column(String(100))  # "[Smith 2020]" or "[23]" or "Smith et al."

    # Referenced work (best-effort resolution)
    referenced_title = Column(Text)  # Resolved title if possible
    referenced_doi = Column(String(100), index=True)  # Resolved DOI if possible
    referenced_paper_id = Column(Integer, ForeignKey('papers.id', ondelete='SET NULL'), index=True)

    # Context
    section = Column(String(50), index=True)  # introduction, methods, results, discussion
    usefulness = Column(String(50))  # background, methods, comparison, key_finding, supports_claim

    # Chunk reference (where this claim was extracted from)
    chunk_id = Column(Integer, ForeignKey('paper_chunks.id', ondelete='SET NULL'))

    # Timestamps
    created_at = Column(DateTime, default=func.now())

    # Relationships
    paper = relationship('Paper', foreign_keys=[paper_id],
                        backref=backref('cited_claims', cascade='all, delete-orphan'))
    referenced_paper = relationship('Paper', foreign_keys=[referenced_paper_id])
    chunk = relationship('PaperChunk')
