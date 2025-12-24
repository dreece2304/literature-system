"""Collection Service - Business logic for collection operations.

This service provides all collection-related operations including CRUD,
hierarchy management, and paper associations.

Usage:
    from services import CollectionService

    # Get all root collections
    collections = CollectionService.list()

    # Get a collection with papers
    collection = CollectionService.get(123)

    # Add papers to a collection
    result = CollectionService.add_papers(123, [1, 2, 3])
"""
from __future__ import annotations

from dataclasses import dataclass
from literature_core import (
    get_session,
    get_logger,
    Collection,
    Paper,
    CollectionNotFoundError,
    ValidationError,
)

logger = get_logger(__name__)


@dataclass
class CollectionListResult:
    """Result of a collection list operation."""
    collections: list[dict]
    count: int


@dataclass
class PaperOperationResult:
    """Result of adding/removing papers from a collection."""
    processed: list[int]
    skipped: list[int]
    reason: str  # "added", "removed", "already_in", "not_in"


class CollectionService:
    """Service for collection-related operations."""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def collection_to_dict(collection: Collection, include_papers: bool = False) -> dict:
        """Convert Collection model to dictionary.

        Args:
            collection: Collection ORM instance
            include_papers: Whether to include paper IDs

        Returns:
            Dictionary representation of the collection
        """
        result = {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "parent_id": collection.parent_id,
            "paper_count": len(collection.papers) if collection.papers else 0,
        }
        if include_papers:
            result["paper_ids"] = [p.id for p in collection.papers]
        return result

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    @classmethod
    def get(cls, collection_id: int, include_papers: bool = True) -> dict:
        """Get a collection by ID.

        Args:
            collection_id: The collection's database ID
            include_papers: Whether to include paper IDs

        Returns:
            Dictionary representation of the collection

        Raises:
            CollectionNotFoundError: If collection doesn't exist
        """
        with get_session() as session:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if not collection:
                raise CollectionNotFoundError(collection_id)
            return cls.collection_to_dict(collection, include_papers=include_papers)

    @classmethod
    def list(
        cls,
        parent_id: int | None = None,
        list_all: bool = False,
    ) -> CollectionListResult:
        """List collections with optional hierarchy filtering.

        Args:
            parent_id: Filter to children of this collection (None for root)
            list_all: If True, ignore hierarchy and return all collections

        Returns:
            CollectionListResult with collections and count
        """
        with get_session() as session:
            query = session.query(Collection)

            if not list_all:
                if parent_id is not None:
                    query = query.filter(Collection.parent_id == parent_id)
                else:
                    query = query.filter(Collection.parent_id.is_(None))

            collections = query.order_by(Collection.name).all()

            return CollectionListResult(
                collections=[cls.collection_to_dict(c) for c in collections],
                count=len(collections),
            )

    @classmethod
    def create(
        cls,
        name: str,
        description: str | None = None,
        parent_id: int | None = None,
    ) -> dict:
        """Create a new collection.

        Args:
            name: Collection name (required)
            description: Collection description
            parent_id: Parent collection ID for nesting

        Returns:
            Dictionary representation of the created collection

        Raises:
            ValidationError: If name is empty
            CollectionNotFoundError: If parent doesn't exist
        """
        if not name or not name.strip():
            raise ValidationError("name", "Collection name is required")

        with get_session() as session:
            # Verify parent exists if specified
            if parent_id is not None:
                parent = session.query(Collection).filter(
                    Collection.id == parent_id
                ).first()
                if not parent:
                    raise CollectionNotFoundError(parent_id)

            collection = Collection(
                name=name.strip(),
                description=description,
                parent_id=parent_id,
            )
            session.add(collection)
            session.flush()

            logger.info(f"Created collection {collection.id}: {name}")
            return cls.collection_to_dict(collection)

    @classmethod
    def update(
        cls,
        collection_id: int,
        name: str | None = None,
        description: str | None = None,
        parent_id: int | None = None,
    ) -> dict:
        """Update an existing collection.

        Args:
            collection_id: Collection ID to update
            name: New name
            description: New description
            parent_id: New parent collection ID

        Returns:
            Updated collection dictionary

        Raises:
            CollectionNotFoundError: If collection or parent doesn't exist
            ValidationError: If trying to set collection as its own parent
        """
        with get_session() as session:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if not collection:
                raise CollectionNotFoundError(collection_id)

            # Validate parent_id if provided
            if parent_id is not None:
                if parent_id == collection_id:
                    raise ValidationError("parent_id", "Collection cannot be its own parent")
                parent = session.query(Collection).filter(
                    Collection.id == parent_id
                ).first()
                if not parent:
                    raise CollectionNotFoundError(parent_id)
                collection.parent_id = parent_id

            if name is not None:
                collection.name = name.strip()
            if description is not None:
                collection.description = description

            logger.info(f"Updated collection {collection_id}")
            return cls.collection_to_dict(collection)

    @classmethod
    def delete(cls, collection_id: int) -> dict:
        """Delete a collection (papers are NOT deleted, just unlinked).

        Args:
            collection_id: Collection ID to delete

        Returns:
            Dict with deleted collection info

        Raises:
            CollectionNotFoundError: If collection doesn't exist
        """
        with get_session() as session:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if not collection:
                raise CollectionNotFoundError(collection_id)

            name = collection.name
            session.delete(collection)

            logger.info(f"Deleted collection {collection_id}: {name}")
            return {"id": collection_id, "name": name}

    # =========================================================================
    # Hierarchy Operations
    # =========================================================================

    @classmethod
    def get_children(cls, collection_id: int) -> CollectionListResult:
        """Get child collections of a collection.

        Args:
            collection_id: Parent collection ID

        Returns:
            CollectionListResult with child collections
        """
        with get_session() as session:
            children = session.query(Collection).filter(
                Collection.parent_id == collection_id
            ).order_by(Collection.name).all()

            return CollectionListResult(
                collections=[cls.collection_to_dict(c) for c in children],
                count=len(children),
            )

    # =========================================================================
    # Paper Association Operations
    # =========================================================================

    @classmethod
    def add_papers(
        cls,
        collection_id: int,
        paper_ids: list[int],
    ) -> PaperOperationResult:
        """Add papers to a collection.

        Args:
            collection_id: Collection ID
            paper_ids: List of paper IDs to add

        Returns:
            PaperOperationResult with added and skipped IDs

        Raises:
            CollectionNotFoundError: If collection doesn't exist
        """
        with get_session() as session:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if not collection:
                raise CollectionNotFoundError(collection_id)

            added = []
            skipped = []

            for paper_id in paper_ids:
                paper = session.query(Paper).filter(Paper.id == paper_id).first()
                if paper:
                    if paper not in collection.papers:
                        collection.papers.append(paper)
                        added.append(paper_id)
                    else:
                        skipped.append(paper_id)
                # Silently skip non-existent papers

            logger.info(f"Added {len(added)} papers to collection {collection_id}")
            return PaperOperationResult(
                processed=added,
                skipped=skipped,
                reason="already_in" if skipped else "added",
            )

    @classmethod
    def remove_papers(
        cls,
        collection_id: int,
        paper_ids: list[int],
    ) -> PaperOperationResult:
        """Remove papers from a collection.

        Args:
            collection_id: Collection ID
            paper_ids: List of paper IDs to remove

        Returns:
            PaperOperationResult with removed and skipped IDs

        Raises:
            CollectionNotFoundError: If collection doesn't exist
        """
        with get_session() as session:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if not collection:
                raise CollectionNotFoundError(collection_id)

            removed = []
            skipped = []

            for paper_id in paper_ids:
                paper = session.query(Paper).filter(Paper.id == paper_id).first()
                if paper and paper in collection.papers:
                    collection.papers.remove(paper)
                    removed.append(paper_id)
                else:
                    skipped.append(paper_id)

            logger.info(f"Removed {len(removed)} papers from collection {collection_id}")
            return PaperOperationResult(
                processed=removed,
                skipped=skipped,
                reason="not_in" if skipped else "removed",
            )

    @classmethod
    def get_papers(cls, collection_id: int) -> list[dict]:
        """Get all papers in a collection.

        Args:
            collection_id: Collection ID

        Returns:
            List of paper summary dicts

        Raises:
            CollectionNotFoundError: If collection doesn't exist
        """
        with get_session() as session:
            collection = session.query(Collection).filter(
                Collection.id == collection_id
            ).first()
            if not collection:
                raise CollectionNotFoundError(collection_id)

            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "year": p.year,
                    "authors": [a.name for a in p.authors],
                }
                for p in collection.papers
            ]
