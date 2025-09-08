"""Database models for literature database."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, 
    DateTime, Boolean, ForeignKey, Table, Float
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
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
    authors = relationship('Author', secondary=paper_authors, back_populates='papers')
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
