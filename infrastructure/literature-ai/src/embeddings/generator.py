"""
Embedding generation using sentence-transformers.

This module handles:
- Loading and caching embedding models
- Generating embeddings for papers and text chunks
- Batch processing for efficiency
- GPU/CPU device management
"""

import hashlib
from typing import List, Optional, Dict, Union
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from loguru import logger

from config.settings import settings


class EmbeddingGenerator:
    """
    Generates embeddings using sentence-transformers models.

    Features:
    - Automatic model downloading and caching
    - Batch processing for efficiency
    - GPU acceleration when available
    - L2 normalization for cosine similarity
    - Deterministic embeddings (no randomness)
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        normalize: bool = True,
    ):
        """
        Initialize the embedding generator.

        Args:
            model_name: HuggingFace model identifier (default: from settings)
            device: Device to use ('cuda', 'cpu', or None for auto)
            normalize: Whether to L2 normalize embeddings (default: True)
        """
        self.model_name = model_name or settings.embedding.model_name
        self.normalize = normalize

        # Determine device
        if device is None:
            device = settings.embedding.device

        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available, falling back to CPU")
            device = "cpu"

        self.device = device

        # Load model
        logger.info(f"Loading embedding model: {self.model_name} on {self.device}")
        self.model = SentenceTransformer(self.model_name, device=self.device)

        # Get embedding dimension
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Model loaded. Embedding dimension: {self.dimension}")

        # Verify dimension matches config
        expected_dim = settings.embedding.dimension
        if self.dimension != expected_dim:
            logger.warning(
                f"Model dimension ({self.dimension}) differs from config ({expected_dim}). "
                f"Updating config to match model."
            )

    def generate(
        self,
        texts: Union[str, List[str]],
        batch_size: Optional[int] = None,
        show_progress: bool = False,
    ) -> np.ndarray:
        """
        Generate embeddings for one or more texts.

        Args:
            texts: Single text string or list of texts
            batch_size: Batch size for processing (default: from settings)
            show_progress: Whether to show progress bar

        Returns:
            numpy array of shape (n_texts, dimension) or (dimension,) for single text
        """
        # Handle single string input
        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        if not texts:
            raise ValueError("Cannot generate embeddings for empty text list")

        # Use default batch size if not provided
        if batch_size is None:
            batch_size = settings.embedding.batch_size

        # Generate embeddings
        logger.debug(f"Generating embeddings for {len(texts)} texts")
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=self.normalize,
            device=self.device,
            convert_to_numpy=True,
        )

        # Return single vector if single input
        if single_input:
            return embeddings[0]

        return embeddings

    def generate_for_paper(
        self,
        paper_data: Dict,
        fields: Optional[List[str]] = None,
    ) -> np.ndarray:
        """
        Generate embedding for a paper using specified fields.

        Args:
            paper_data: Dictionary containing paper metadata
            fields: Fields to combine for embedding (default: title + abstract)

        Returns:
            Embedding vector as numpy array
        """
        if fields is None:
            fields = ["title", "abstract"]

        # Combine specified fields
        text_parts = []
        for field in fields:
            value = paper_data.get(field)
            if value and isinstance(value, str) and value.strip():
                text_parts.append(value.strip())

        if not text_parts:
            raise ValueError(f"No valid text found in fields: {fields}")

        # Combine with newlines
        combined_text = "\n\n".join(text_parts)

        logger.debug(
            f"Generating embedding for paper '{paper_data.get('title', 'Unknown')}' "
            f"using fields: {fields}"
        )

        return self.generate(combined_text)

    def generate_batch(
        self,
        papers: List[Dict],
        fields: Optional[List[str]] = None,
        batch_size: Optional[int] = None,
        show_progress: bool = True,
    ) -> List[np.ndarray]:
        """
        Generate embeddings for multiple papers efficiently.

        Args:
            papers: List of paper dictionaries
            fields: Fields to use for each paper
            batch_size: Processing batch size
            show_progress: Whether to show progress bar

        Returns:
            List of embedding vectors
        """
        if fields is None:
            fields = ["title", "abstract"]

        # Prepare texts
        texts = []
        valid_indices = []

        for i, paper in enumerate(papers):
            text_parts = []
            for field in fields:
                value = paper.get(field)
                if value and isinstance(value, str) and value.strip():
                    text_parts.append(value.strip())

            if text_parts:
                texts.append("\n\n".join(text_parts))
                valid_indices.append(i)
            else:
                logger.warning(
                    f"Paper at index {i} has no valid text in fields {fields}, skipping"
                )

        if not texts:
            logger.warning("No valid papers to generate embeddings for")
            return []

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(texts)} papers")
        embeddings = self.generate(
            texts,
            batch_size=batch_size,
            show_progress=show_progress,
        )

        # Map back to original indices (insert None for skipped papers)
        result = [None] * len(papers)
        for i, embedding in zip(valid_indices, embeddings):
            result[i] = embedding

        return result

    def compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray,
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Similarity score in range [-1, 1]
        """
        # If embeddings are normalized, dot product = cosine similarity
        if self.normalize:
            return float(np.dot(embedding1, embedding2))

        # Otherwise compute cosine similarity
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(embedding1, embedding2) / (norm1 * norm2))

    def compute_similarity_batch(
        self,
        query_embedding: np.ndarray,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        """
        Compute similarities between a query and multiple embeddings.

        Args:
            query_embedding: Query vector of shape (dimension,)
            embeddings: Array of embeddings with shape (n, dimension)

        Returns:
            Array of similarity scores with shape (n,)
        """
        if self.normalize:
            # Simple dot product for normalized vectors
            return np.dot(embeddings, query_embedding)

        # Compute cosine similarity
        query_norm = np.linalg.norm(query_embedding)
        embeddings_norms = np.linalg.norm(embeddings, axis=1)

        # Avoid division by zero
        valid_mask = (query_norm > 0) & (embeddings_norms > 0)
        similarities = np.zeros(len(embeddings))

        if query_norm > 0:
            dot_products = np.dot(embeddings, query_embedding)
            similarities[valid_mask] = (
                dot_products[valid_mask] / (query_norm * embeddings_norms[valid_mask])
            )

        return similarities

    def get_text_hash(self, text: str) -> str:
        """
        Generate a hash for a text (useful for caching).

        Args:
            text: Input text

        Returns:
            SHA256 hash as hex string
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @property
    def model_info(self) -> Dict:
        """Get information about the loaded model."""
        return {
            "name": self.model_name,
            "dimension": self.dimension,
            "device": self.device,
            "normalize": self.normalize,
            "max_seq_length": self.model.max_seq_length,
        }

    def __repr__(self) -> str:
        return (
            f"EmbeddingGenerator("
            f"model={self.model_name}, "
            f"dim={self.dimension}, "
            f"device={self.device}, "
            f"normalize={self.normalize})"
        )


# Global singleton instance (lazy-loaded)
_generator_instance: Optional[EmbeddingGenerator] = None


def get_embedding_generator() -> EmbeddingGenerator:
    """
    Get the global EmbeddingGenerator instance (singleton pattern).

    Returns:
        Shared EmbeddingGenerator instance
    """
    global _generator_instance

    if _generator_instance is None:
        _generator_instance = EmbeddingGenerator()

    return _generator_instance


def reset_embedding_generator():
    """Reset the global generator instance (useful for testing)."""
    global _generator_instance
    _generator_instance = None
