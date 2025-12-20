"""Business logic for paper management."""
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from loguru import logger

from src.models import Paper, Author, Tag, Collection
from src.api.schemas import PaperCreate, PaperUpdate
from src.extractors.pdf_extractor import PDFExtractor
from src.extractors.metadata_extractor import MetadataExtractor


class PaperService:
    """Service for paper management operations."""

    def __init__(self):
        self.pdf_extractor = PDFExtractor()
        self.metadata_extractor = MetadataExtractor()

    def list_papers(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict] = None
    ) -> List[Paper]:
        """List papers with optional filtering."""
        query = db.query(Paper)

        if filters:
            if 'author' in filters:
                query = query.join(Paper.authors).filter(
                    Author.name.ilike(f"%{filters['author']}%")
                )

            if 'tag' in filters:
                query = query.join(Paper.tags).filter(
                    Tag.name.ilike(f"%{filters['tag']}%")
                )

            if 'year' in filters:
                query = query.filter(Paper.year == filters['year'])

            if 'journal' in filters:
                query = query.filter(
                    Paper.journal.ilike(f"%{filters['journal']}%")
                )

        return query.offset(skip).limit(limit).all()

    def get_paper(self, db: Session, paper_id: int) -> Optional[Paper]:
        """Get a single paper by ID."""
        return db.query(Paper).filter(Paper.id == paper_id).first()

    def create_paper(self, db: Session, paper_data: PaperCreate) -> Paper:
        """Create a new paper."""
        # Check for duplicate DOI
        if paper_data.doi:
            existing = db.query(Paper).filter(Paper.doi == paper_data.doi).first()
            if existing:
                raise ValueError(f"Paper with DOI {paper_data.doi} already exists")

        # Create paper object
        paper = Paper(
            title=paper_data.title,
            abstract=paper_data.abstract,
            year=paper_data.year,
            doi=paper_data.doi,
            arxiv_id=paper_data.arxiv_id,
            pubmed_id=paper_data.pubmed_id,
            journal=paper_data.journal,
            volume=paper_data.volume,
            issue=paper_data.issue,
            pages=paper_data.pages,
            publisher=paper_data.publisher,
            rating=paper_data.rating,
            read_status=paper_data.read_status,
            file_path=paper_data.file_path
        )

        # Add authors
        if paper_data.authors:
            for author_name in paper_data.authors:
                author = self._get_or_create_author(db, author_name)
                paper.authors.append(author)

        # Add tags
        if paper_data.tags:
            for tag_name in paper_data.tags:
                tag = self._get_or_create_tag(db, tag_name)
                paper.tags.append(tag)

        # Add collections
        if paper_data.collections:
            for collection_name in paper_data.collections:
                collection = self._get_or_create_collection(db, collection_name)
                paper.collections.append(collection)

        db.add(paper)
        db.commit()
        db.refresh(paper)

        logger.info(f"Created paper: {paper.title}")
        return paper

    def update_paper(
        self,
        db: Session,
        paper_id: int,
        paper_update: PaperUpdate
    ) -> Optional[Paper]:
        """Update an existing paper."""
        paper = self.get_paper(db, paper_id)
        if not paper:
            return None

        # Update basic fields
        update_data = paper_update.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field not in ['authors', 'tags', 'collections'] and value is not None:
                setattr(paper, field, value)

        # Update authors if provided
        if paper_update.authors is not None:
            paper.authors.clear()
            for author_name in paper_update.authors:
                author = self._get_or_create_author(db, author_name)
                paper.authors.append(author)

        # Update tags if provided
        if paper_update.tags is not None:
            paper.tags.clear()
            for tag_name in paper_update.tags:
                tag = self._get_or_create_tag(db, tag_name)
                paper.tags.append(tag)

        # Update collections if provided
        if paper_update.collections is not None:
            paper.collections.clear()
            for collection_name in paper_update.collections:
                collection = self._get_or_create_collection(db, collection_name)
                paper.collections.append(collection)

        db.commit()
        db.refresh(paper)

        logger.info(f"Updated paper: {paper.title}")
        return paper

    def delete_paper(self, db: Session, paper_id: int) -> bool:
        """Delete a paper."""
        paper = self.get_paper(db, paper_id)
        if not paper:
            return False

        # Remove associated file if it exists
        if paper.file_path and Path(paper.file_path).exists():
            try:
                Path(paper.file_path).unlink()
                logger.info(f"Deleted file: {paper.file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete file {paper.file_path}: {e}")

        db.delete(paper)
        db.commit()

        logger.info(f"Deleted paper: {paper.title}")
        return True

    def add_paper_from_file(self, db: Session, file_path: Path) -> Paper:
        """Add a paper by processing a PDF file."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not self.pdf_extractor.is_supported(file_path):
            raise ValueError(f"Unsupported file type: {file_path.suffix}")

        try:
            # Extract data from PDF
            extracted_data = self.pdf_extractor.extract(file_path)

            # Check for duplicate by hash
            existing = db.query(Paper).filter(
                Paper.file_hash == extracted_data['file_hash']
            ).first()
            if existing:
                raise ValueError(f"File already exists in database: {existing.title}")

            # Extract metadata from text
            metadata = self.metadata_extractor.extract_from_text(
                extracted_data['full_text'],
                file_path.name
            )

            # Extract authors from text
            authors = self.metadata_extractor.extract_authors_from_text(
                extracted_data['full_text']
            )

            # Create paper data
            paper_data = PaperCreate(
                title=metadata.get('title', file_path.stem),
                abstract=metadata.get('abstract', ''),
                year=metadata.get('year'),
                doi=metadata.get('doi'),
                arxiv_id=metadata.get('arxiv_id'),
                pubmed_id=metadata.get('pubmed_id'),
                journal=metadata.get('journal'),
                file_path=str(file_path),
                authors=authors
            )

            # Create the paper
            paper = self.create_paper(db, paper_data)

            # Update with extracted data
            paper.full_text = extracted_data['full_text']
            paper.word_count = extracted_data['word_count']
            paper.file_hash = extracted_data['file_hash']

            db.commit()
            db.refresh(paper)

            logger.info(f"Added paper from file: {file_path}")
            return paper

        except Exception as e:
            logger.error(f"Failed to add paper from file {file_path}: {e}")
            raise

    def _get_or_create_author(self, db: Session, name: str) -> Author:
        """Get existing author or create new one."""
        author = db.query(Author).filter(Author.name == name).first()
        if not author:
            author = Author(name=name)
            db.add(author)
        return author

    def _get_or_create_tag(self, db: Session, name: str) -> Tag:
        """Get existing tag or create new one."""
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
        return tag

    def _get_or_create_collection(self, db: Session, name: str) -> Collection:
        """Get existing collection or create new one."""
        collection = db.query(Collection).filter(Collection.name == name).first()
        if not collection:
            collection = Collection(name=name)
            db.add(collection)
        return collection
