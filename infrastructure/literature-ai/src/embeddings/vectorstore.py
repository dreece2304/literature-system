"""
Vector store implementation using ChromaDB.

This module provides a clean interface for storing and retrieving paper embeddings,
with support for metadata filtering, batch operations, and persistence.
"""

from typing import List, Dict, Optional
from pathlib import Path
import numpy as np
from loguru import logger

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.error("ChromaDB not available. Please install: pip install chromadb")

from config.settings import settings


class VectorStore:
    """
    Wrapper for ChromaDB vector database.

    Features:
    - Persistent storage of embeddings
    - Metadata-based filtering
    - Cosine similarity search
    - Batch operations
    - Collection management
    """

    def __init__(
        self,
        collection_name: Optional[str] = None,
        persist_directory: Optional[Path] = None,
        distance_metric: Optional[str] = None,
    ):
        """
        Initialize the vector store.

        Args:
            collection_name: Name of the collection (default: from settings)
            persist_directory: Directory for persistence (default: from settings)
            distance_metric: Distance metric ('cosine', 'l2', 'ip')
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB is required. Install with: pip install chromadb")

        self.collection_name = collection_name or settings.chromadb.collection_name
        self.persist_directory = persist_directory or settings.chromadb.persist_directory
        self.distance_metric = distance_metric or settings.chromadb.distance_metric

        # Ensure persistence directory exists
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client
        logger.info(f"Initializing ChromaDB at {self.persist_directory}")
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Get or create collection
        self.collection = self._get_or_create_collection()

        logger.info(
            f"VectorStore initialized: collection='{self.collection_name}', "
            f"count={self.count()}, metric={self.distance_metric}"
        )

    def _get_or_create_collection(self):
        """Get existing collection or create new one."""
        try:
            # Try to get existing collection
            collection = self.client.get_collection(
                name=self.collection_name,
                embedding_function=None,  # We provide embeddings directly
            )
            logger.debug(f"Loaded existing collection: {self.collection_name}")
        except Exception:
            # Create new collection
            metadata = {"hnsw:space": self.distance_metric}
            collection = self.client.create_collection(
                name=self.collection_name,
                metadata=metadata,
                embedding_function=None,
            )
            logger.info(f"Created new collection: {self.collection_name}")

        return collection

    def add(
        self,
        id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict] = None,
        document: Optional[str] = None,
    ):
        """
        Add a single embedding to the store.

        Args:
            id: Unique identifier for this embedding
            embedding: Embedding vector
            metadata: Optional metadata dictionary
            document: Optional source document text
        """
        self.add_batch(
            ids=[id],
            embeddings=[embedding],
            metadatas=[metadata] if metadata else None,
            documents=[document] if document else None,
        )

    def add_batch(
        self,
        ids: List[str],
        embeddings: List[np.ndarray],
        metadatas: Optional[List[Dict]] = None,
        documents: Optional[List[str]] = None,
    ):
        """
        Add multiple embeddings in batch.

        Args:
            ids: List of unique identifiers
            embeddings: List of embedding vectors
            metadatas: Optional list of metadata dictionaries
            documents: Optional list of source documents
        """
        if len(ids) != len(embeddings):
            raise ValueError("ids and embeddings must have same length")

        # Convert embeddings to list format
        embeddings_list = [
            emb.tolist() if isinstance(emb, np.ndarray) else emb
            for emb in embeddings
        ]

        # Sanitize metadata (ChromaDB doesn't support nested dicts)
        if metadatas:
            metadatas = [self._sanitize_metadata(m) for m in metadatas]

        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings_list,
                metadatas=metadatas,
                documents=documents,
            )
            logger.debug(f"Added {len(ids)} embeddings to collection")
        except Exception as e:
            logger.error(f"Failed to add embeddings: {e}")
            raise

    def update(
        self,
        id: str,
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict] = None,
        document: Optional[str] = None,
    ):
        """
        Update an existing embedding.

        Args:
            id: ID of embedding to update
            embedding: New embedding vector (optional)
            metadata: New metadata (optional)
            document: New document (optional)
        """
        update_data = {"ids": [id]}

        if embedding is not None:
            update_data["embeddings"] = [embedding.tolist() if isinstance(embedding, np.ndarray) else embedding]

        if metadata is not None:
            update_data["metadatas"] = [self._sanitize_metadata(metadata)]

        if document is not None:
            update_data["documents"] = [document]

        try:
            self.collection.update(**update_data)
            logger.debug(f"Updated embedding: {id}")
        except Exception as e:
            logger.error(f"Failed to update embedding {id}: {e}")
            raise

    def delete(self, ids: List[str]):
        """
        Delete embeddings by ID.

        Args:
            ids: List of IDs to delete
        """
        try:
            self.collection.delete(ids=ids)
            logger.debug(f"Deleted {len(ids)} embeddings")
        except Exception as e:
            logger.error(f"Failed to delete embeddings: {e}")
            raise

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: Optional[int] = None,
        where: Optional[Dict] = None,
        score_threshold: Optional[float] = None,
        include: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Search for similar embeddings.

        Args:
            query_embedding: Query vector
            top_k: Number of results to return (default: from settings)
            where: Metadata filter (ChromaDB where clause)
            score_threshold: Minimum similarity score (default: from settings)
            include: What to include in results (default: ["metadatas", "documents", "distances"])

        Returns:
            List of result dictionaries with keys:
                - id: Document ID
                - distance: Distance score
                - metadata: Metadata dict
                - document: Source document (if included)
        """
        if top_k is None:
            top_k = settings.chromadb.top_k

        if score_threshold is None:
            score_threshold = settings.chromadb.score_threshold

        if include is None:
            include = ["metadatas", "documents", "distances"]

        # Convert embedding to list
        query_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding

        try:
            results = self.collection.query(
                query_embeddings=[query_list],
                n_results=top_k,
                where=where,
                include=include,
            )

            # Process results
            processed_results = []
            for i in range(len(results["ids"][0])):
                result_id = results["ids"][0][i]
                distance = results["distances"][0][i] if "distances" in results else None

                # Convert distance to similarity score (for cosine)
                if distance is not None and self.distance_metric == "cosine":
                    # ChromaDB cosine distance is 1 - cosine_similarity
                    similarity = 1.0 - distance
                else:
                    similarity = -distance if distance is not None else None

                # Apply threshold
                if score_threshold is not None and similarity is not None:
                    if similarity < score_threshold:
                        continue

                result_dict = {
                    "id": result_id,
                    "score": similarity,
                    "distance": distance,
                }

                if "metadatas" in results and results["metadatas"]:
                    result_dict["metadata"] = results["metadatas"][0][i]

                if "documents" in results and results["documents"]:
                    result_dict["document"] = results["documents"][0][i]

                processed_results.append(result_dict)

            logger.debug(
                f"Search returned {len(processed_results)} results "
                f"(threshold={score_threshold})"
            )

            return processed_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def get(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict] = None,
        limit: Optional[int] = None,
        include: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Get embeddings by ID or filter.

        Args:
            ids: Specific IDs to retrieve
            where: Metadata filter
            limit: Maximum number of results
            include: What to include in results

        Returns:
            List of embedding dictionaries
        """
        if include is None:
            include = ["metadatas", "documents", "embeddings"]

        try:
            results = self.collection.get(
                ids=ids,
                where=where,
                limit=limit,
                include=include,
            )

            # Process results
            processed_results = []
            for i in range(len(results["ids"])):
                result_dict = {"id": results["ids"][i]}

                if "embeddings" in results and results["embeddings"] is not None:
                    result_dict["embedding"] = np.array(results["embeddings"][i])

                if "metadatas" in results and results["metadatas"] is not None:
                    result_dict["metadata"] = results["metadatas"][i]

                if "documents" in results and results["documents"] is not None:
                    result_dict["document"] = results["documents"][i]

                processed_results.append(result_dict)

            return processed_results

        except Exception as e:
            logger.error(f"Get operation failed: {e}")
            raise

    def exists(self, id: str) -> bool:
        """
        Check if an embedding with given ID exists.

        Args:
            id: ID to check

        Returns:
            True if exists, False otherwise
        """
        try:
            result = self.collection.get(ids=[id], include=[])
            return len(result["ids"]) > 0
        except Exception:
            return False

    def count(self) -> int:
        """Get the total number of embeddings in the collection."""
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Count failed: {e}")
            return 0

    def reset(self):
        """Delete all embeddings from the collection."""
        try:
            # Delete the collection and recreate
            self.client.delete_collection(name=self.collection_name)
            self.collection = self._get_or_create_collection()
            logger.info(f"Reset collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Reset failed: {e}")
            raise

    def get_stats(self) -> Dict:
        """
        Get statistics about the vector store.

        Returns:
            Dictionary with statistics
        """
        return {
            "collection_name": self.collection_name,
            "count": self.count(),
            "distance_metric": self.distance_metric,
            "persist_directory": str(self.persist_directory),
        }

    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """
        Sanitize metadata for ChromaDB compatibility.

        ChromaDB only supports flat dictionaries with simple types.

        Args:
            metadata: Original metadata

        Returns:
            Sanitized metadata
        """
        if not metadata:
            return {}

        sanitized = {}
        for key, value in metadata.items():
            # Convert complex types to strings
            if isinstance(value, (dict, list)):
                sanitized[key] = str(value)
            elif isinstance(value, (int, float, str, bool)) or value is None:
                sanitized[key] = value
            else:
                sanitized[key] = str(value)

        return sanitized

    def __repr__(self) -> str:
        return (
            f"VectorStore("
            f"collection='{self.collection_name}', "
            f"count={self.count()}, "
            f"metric='{self.distance_metric}')"
        )


# Global singleton instance
_vectorstore_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """
    Get the global VectorStore instance (singleton pattern).

    Returns:
        Shared VectorStore instance
    """
    global _vectorstore_instance

    if _vectorstore_instance is None:
        _vectorstore_instance = VectorStore()

    return _vectorstore_instance


def reset_vector_store():
    """Reset the global vector store instance (useful for testing)."""
    global _vectorstore_instance
    if _vectorstore_instance is not None:
        _vectorstore_instance.reset()
    _vectorstore_instance = None
