"""
Conversion functions between database models and API contracts.

Handles the transformation between SQLAlchemy ORM models and Pydantic API models
while preserving all data integrity for the 323 existing papers.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

# Import database models
from src.models import (
    Paper as PaperModel,
    Author as AuthorModel,
    Tag as TagModel,
    Collection as CollectionModel
)


def db_author_to_api(db_author: AuthorModel) -> Dict[str, Any]:
    """Convert database Author model to API Author dict."""
    return {
        "id": db_author.id,
        "name": db_author.name,
        "orcid": db_author.orcid,
        "email": db_author.email,
        "affiliation": db_author.affiliation
    }


def db_tag_to_api(db_tag: TagModel) -> Dict[str, Any]:
    """Convert database Tag model to API Tag dict."""
    return {
        "id": db_tag.id,
        "name": db_tag.name,
        "category": db_tag.category,
        "color": db_tag.color
    }


def db_collection_to_api(db_collection: CollectionModel, session: Optional[Session] = None) -> Dict[str, Any]:
    """Convert database Collection model to API Collection dict."""
    # Calculate paper count if session provided
    paper_count = 0
    if session and db_collection.papers:
        paper_count = len(db_collection.papers)

    return {
        "id": db_collection.id,
        "name": db_collection.name,
        "description": db_collection.description,
        "parent_id": db_collection.parent_id,
        "zotero_key": db_collection.zotero_key,
        "paper_count": paper_count
    }


def db_paper_to_api(db_paper: PaperModel, session: Optional[Session] = None) -> Dict[str, Any]:
    """
    Convert database Paper model to API Paper dict.

    Args:
        db_paper: SQLAlchemy Paper model instance
        session: Optional SQLAlchemy session for calculating collection paper counts

    Returns:
        Dict containing all fields for API Paper model
    """
    # Convert related objects
    authors = [db_author_to_api(author) for author in (db_paper.authors or [])]
    tags = [db_tag_to_api(tag) for tag in (db_paper.tags or [])]
    collections = [db_collection_to_api(collection, session) for collection in (db_paper.collections or [])]

    return {
        "id": db_paper.id,
        "title": db_paper.title,
        "abstract": db_paper.abstract,
        "year": db_paper.year,
        "doi": db_paper.doi,
        "arxiv_id": db_paper.arxiv_id,
        "pubmed_id": db_paper.pubmed_id,
        "journal": db_paper.journal,
        "volume": db_paper.volume,
        "issue": db_paper.issue,
        "pages": db_paper.pages,
        "publisher": db_paper.publisher,
        "rating": db_paper.rating,
        "read_status": db_paper.read_status or "unread",
        "file_path": db_paper.file_path,
        "file_hash": db_paper.file_hash,
        "zotero_key": db_paper.zotero_key,
        "zotero_version": db_paper.zotero_version,
        "date_added": db_paper.date_added,
        "date_modified": db_paper.date_modified,
        "date_read": db_paper.date_read,
        "word_count": db_paper.word_count,
        "authors": authors,
        "tags": tags,
        "collections": collections
    }


def api_paper_create_to_db_data(api_paper_create: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert API PaperCreate data to database insertion data.

    Args:
        api_paper_create: Dict from PaperCreate.model_dump()

    Returns:
        Dict suitable for creating database Paper model
    """
    # Extract relationship data (handled separately)
    authors = api_paper_create.pop("authors", []) or []
    tags = api_paper_create.pop("tags", []) or []
    collections = api_paper_create.pop("collections", []) or []

    # Convert main paper data
    db_data = {
        "title": api_paper_create.get("title"),
        "abstract": api_paper_create.get("abstract"),
        "year": api_paper_create.get("year"),
        "doi": api_paper_create.get("doi"),
        "arxiv_id": api_paper_create.get("arxiv_id"),
        "pubmed_id": api_paper_create.get("pubmed_id"),
        "journal": api_paper_create.get("journal"),
        "volume": api_paper_create.get("volume"),
        "issue": api_paper_create.get("issue"),
        "pages": api_paper_create.get("pages"),
        "publisher": api_paper_create.get("publisher"),
        "rating": api_paper_create.get("rating"),
        "read_status": api_paper_create.get("read_status", "unread"),
        "file_path": api_paper_create.get("file_path"),
        "date_added": datetime.utcnow()
    }

    # Remove None values
    db_data = {k: v for k, v in db_data.items() if v is not None}

    # Store relationship data for separate handling
    db_data["_authors"] = authors
    db_data["_tags"] = tags
    db_data["_collections"] = collections

    return db_data


def api_paper_update_to_db_data(api_paper_update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert API PaperUpdate data to database update data.

    Args:
        api_paper_update: Dict from PaperUpdate.model_dump(exclude_unset=True)

    Returns:
        Dict suitable for updating database Paper model
    """
    # Extract relationship data (handled separately)
    authors = api_paper_update.pop("authors", None)
    tags = api_paper_update.pop("tags", None)
    collections = api_paper_update.pop("collections", None)

    # Convert main paper data
    db_data = {
        "title": api_paper_update.get("title"),
        "abstract": api_paper_update.get("abstract"),
        "year": api_paper_update.get("year"),
        "doi": api_paper_update.get("doi"),
        "arxiv_id": api_paper_update.get("arxiv_id"),
        "pubmed_id": api_paper_update.get("pubmed_id"),
        "journal": api_paper_update.get("journal"),
        "volume": api_paper_update.get("volume"),
        "issue": api_paper_update.get("issue"),
        "pages": api_paper_update.get("pages"),
        "publisher": api_paper_update.get("publisher"),
        "rating": api_paper_update.get("rating"),
        "read_status": api_paper_update.get("read_status"),
        "file_path": api_paper_update.get("file_path"),
        "date_read": api_paper_update.get("date_read"),
        "date_modified": datetime.utcnow()
    }

    # Remove None values (only update fields that were provided)
    db_data = {k: v for k, v in db_data.items() if v is not None}

    # Store relationship data for separate handling (only if provided)
    if authors is not None:
        db_data["_authors"] = authors
    if tags is not None:
        db_data["_tags"] = tags
    if collections is not None:
        db_data["_collections"] = collections

    return db_data


def resolve_authors_by_name(session: Session, author_names: List[str]) -> List[AuthorModel]:
    """
    Resolve author names to Author model instances, creating new ones if needed.

    Args:
        session: SQLAlchemy session
        author_names: List of author name strings

    Returns:
        List of Author model instances
    """
    authors = []
    for name in author_names:
        if not name or not name.strip():
            continue

        name = name.strip()

        # Try to find existing author
        author = session.query(AuthorModel).filter(AuthorModel.name == name).first()

        # Create new author if not found
        if not author:
            author = AuthorModel(name=name)
            session.add(author)
            session.flush()  # Get the ID

        authors.append(author)

    return authors


def resolve_tags_by_name(session: Session, tag_names: List[str]) -> List[TagModel]:
    """
    Resolve tag names to Tag model instances, creating new ones if needed.

    Args:
        session: SQLAlchemy session
        tag_names: List of tag name strings

    Returns:
        List of Tag model instances
    """
    tags = []
    for name in tag_names:
        if not name or not name.strip():
            continue

        name = name.strip()

        # Try to find existing tag
        tag = session.query(TagModel).filter(TagModel.name == name).first()

        # Create new tag if not found
        if not tag:
            tag = TagModel(name=name)
            session.add(tag)
            session.flush()  # Get the ID

        tags.append(tag)

    return tags


def resolve_collections_by_name(session: Session, collection_names: List[str]) -> List[CollectionModel]:
    """
    Resolve collection names to Collection model instances, creating new ones if needed.

    Args:
        session: SQLAlchemy session
        collection_names: List of collection name strings

    Returns:
        List of Collection model instances
    """
    collections = []
    for name in collection_names:
        if not name or not name.strip():
            continue

        name = name.strip()

        # Try to find existing collection
        collection = session.query(CollectionModel).filter(CollectionModel.name == name).first()

        # Create new collection if not found
        if not collection:
            collection = CollectionModel(name=name)
            session.add(collection)
            session.flush()  # Get the ID

        collections.append(collection)

    return collections


def update_paper_relationships(session: Session, paper: PaperModel, db_data: Dict[str, Any]) -> None:
    """
    Update paper relationships (authors, tags, collections) from converted data.

    Args:
        session: SQLAlchemy session
        paper: Paper model instance to update
        db_data: Database data dict containing relationship info
    """
    # Update authors if provided
    if "_authors" in db_data:
        author_names = db_data["_authors"]
        paper.authors = resolve_authors_by_name(session, author_names)

    # Update tags if provided
    if "_tags" in db_data:
        tag_names = db_data["_tags"]
        paper.tags = resolve_tags_by_name(session, tag_names)

    # Update collections if provided
    if "_collections" in db_data:
        collection_names = db_data["_collections"]
        paper.collections = resolve_collections_by_name(session, collection_names)


# Compatibility function for existing code
def convert_db_paper_to_api(db_paper: PaperModel, session: Optional[Session] = None) -> Dict[str, Any]:
    """
    Legacy compatibility function - use db_paper_to_api instead.

    This function exists to maintain compatibility with existing code.
    """
    return db_paper_to_api(db_paper, session)
