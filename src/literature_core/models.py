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
    """AI-extracted structured content from papers.

    Two-tier extraction system (schema v2.1):
    - Quick tier: paper_type, topics, one_sentence_summary (from abstract)
    - Deep tier: deep_* versions of quick fields + extended fields (from PDF)

    Both tiers persist separately for verification and audit trail.
    """
    __tablename__ = 'paper_contents'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'),
                      unique=True, nullable=False)

    # Extraction metadata
    quick_extraction_date = Column(DateTime)  # When quick tier was run
    deep_extraction_date = Column(DateTime)   # When deep tier was run
    extraction_depth = Column(String(50))     # "abstract_only" or "comprehensive"
    schema_version = Column(String(20), default='2.1')
    extractor_model = Column(String(100))
    deep_extractor_model = Column(String(100))  # Model used for deep extraction

    # Quick tier fields (from abstract only - preserved even after deep)
    paper_type = Column(String(50))
    topics = Column(JSON)
    one_sentence_summary = Column(Text)

    # Deep tier versions of quick fields (from full PDF - may differ)
    deep_paper_type = Column(String(50))
    deep_topics = Column(JSON)
    deep_one_sentence_summary = Column(Text)

    # Deep tier extended fields (only populated by deep extraction)
    key_findings = Column(JSON)
    methodology_summary = Column(Text)
    structured_data = Column(JSON)  # Extended fields as JSON

    # Verification (comparison of quick vs deep)
    verification = Column(JSON)  # {paper_type_matches, topics_overlap, notes}

    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    paper = relationship('Paper', backref=backref('content', uselist=False,
                                                  cascade='all, delete-orphan'))


class ProjectRelevance(Base):
    """Paper relevance to specific research projects.

    Used to:
    - Score papers against project topics (from data/projects.json)
    - Track deep extraction decisions (queue/skip/done)
    - Enable project-specific paper filtering

    Relevance levels: "high", "medium", "low", "none"
    """
    __tablename__ = 'project_relevances'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'),
                      nullable=False)
    project_name = Column(String(200), nullable=False)

    # Relevance scoring
    relevance_level = Column(String(20))      # high, medium, low, none
    matched_topics = Column(JSON)             # List of matched topic strings
    relevance_summary = Column(Text)          # Human-readable explanation
    primary_use = Column(String(100))         # background, methods, comparison

    # Deep extraction tracking
    deep_extract_decision = Column(String(20))  # queue, skip, done
    decision_reason = Column(String(200))       # Why (e.g., "high relevance")

    # Timestamps
    scored_at = Column(DateTime)              # When relevance was calculated
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


class PaperCitation(Base):
    """Citation relationships between papers in the library.

    Tracks which papers cite which other papers. Links are created when:
    - Importing references from a paper via external APIs
    - Matching PDF-extracted references to library papers
    - Manual linking

    This enables local citation graph queries without API calls.
    """
    __tablename__ = 'paper_citations'

    id = Column(Integer, primary_key=True)
    citing_paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)
    cited_paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)
    source = Column(String(50), nullable=False)  # 'openalex', 'semantic_scholar', 'pdf', 'manual'
    created_at = Column(DateTime, default=func.now())

    # Relationships
    citing_paper = relationship('Paper', foreign_keys=[citing_paper_id],
                                backref=backref('outgoing_citations', cascade='all, delete-orphan'))
    cited_paper = relationship('Paper', foreign_keys=[cited_paper_id],
                               backref=backref('incoming_citations', cascade='all, delete-orphan'))

    __table_args__ = (
        Index('ix_paper_citations_citing', 'citing_paper_id'),
        Index('ix_paper_citations_cited', 'cited_paper_id'),
    )


class ClaimCitation(Base):
    """Maps claims in a paper to their cited references.

    When we extract "ALD enables conformal coatings [17, 23]",
    we store the claim text, citation numbers, and link to the
    referenced papers (both in bibliography and library).

    Use cases:
    - Find source papers for claims
    - Build citation chains (A cites B cites C)
    - Verify if cited papers support claims
    """
    __tablename__ = 'claim_citations'

    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False)

    # The claim text from the paper
    claim_text = Column(Text, nullable=False)
    citation_numbers = Column(JSON)  # [17, 23] - numbers as they appear in text

    # Context
    section = Column(String(50))  # introduction, methods, results, discussion
    chunk_index = Column(Integer)  # Which chunk this came from
    claim_type = Column(String(50))  # fact, method, comparison, limitation

    # Links to references and library papers
    # One claim can cite multiple references, stored as JSON array of IDs
    reference_ids = Column(JSON)  # [ref_id_1, ref_id_2] - FKs to paper_references
    matched_paper_ids = Column(JSON)  # [paper_id_1, paper_id_2] - FKs to papers (if in library)

    # Status for each citation (parallel arrays)
    match_statuses = Column(JSON)  # ["matched", "unmatched", "imported"]

    # Importance/relevance
    importance = Column(String(20))  # high, medium, low

    created_at = Column(DateTime, default=func.now())

    # Relationships
    paper = relationship('Paper', backref=backref('claim_citations', cascade='all, delete-orphan'))

    __table_args__ = (
        Index('ix_claim_citations_paper_id', 'paper_id'),
        Index('ix_claim_citations_section', 'section'),
        Index('ix_claim_citations_claim_type', 'claim_type'),
    )


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
