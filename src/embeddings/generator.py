"""
Embedding generation using sentence-transformers.

This module handles:
- Loading and caching embedding models
- Generating embeddings for papers and text chunks
- Batch processing for efficiency
- GPU/CPU device management
"""
from __future__ import annotations

import hashlib
import re
from typing import List, Optional, Dict, Union
# dataclass import removed - unused
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from loguru import logger

from config.ai_settings import settings

# TextChunk and ChunkEmbedding are imported at runtime in methods where needed


# Common section headers in academic papers
SECTION_PATTERNS = [
    (r"^\s*(?:1\.?\s*)?(?:INTRODUCTION|Introduction)\s*$", "introduction"),
    (r"^\s*(?:2\.?\s*)?(?:BACKGROUND|Background|RELATED\s+WORK|Related\s+Work|LITERATURE\s+REVIEW|Literature\s+Review)\s*$", "background"),  # noqa: E501
    (r"^\s*(?:3\.?\s*)?(?:METHODS?|Methods?|METHODOLOGY|Methodology|EXPERIMENTAL|Experimental)\s*$", "methods"),
    (r"^\s*(?:4\.?\s*)?(?:RESULTS?|Results?|FINDINGS|Findings)\s*$", "results"),
    (r"^\s*(?:5\.?\s*)?(?:DISCUSSION|Discussion)\s*$", "discussion"),
    (r"^\s*(?:6\.?\s*)?(?:CONCLUSION|Conclusion|CONCLUSIONS|Conclusions|SUMMARY|Summary)\s*$", "conclusion"),
    (r"^\s*(?:ABSTRACT|Abstract)\s*$", "abstract"),
    (r"^\s*(?:REFERENCES?|References?|BIBLIOGRAPHY|Bibliography)\s*$", "references"),
    (r"^\s*(?:ACKNOWLEDGEMENTS?|Acknowledgements?)\s*$", "acknowledgements"),
    (r"^\s*(?:APPENDIX|Appendix|SUPPLEMENTARY|Supplementary)\s*$", "appendix"),
]


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

    # =========================================================================
    # Chunk Embedding Methods
    # =========================================================================

    def chunk_paper(
        self,
        paper_id: int,
        full_text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 100,
    ) -> list:
        """
        Split paper text into chunks with metadata.

        Args:
            paper_id: Paper ID for chunk identification
            full_text: Full text of the paper
            chunk_size: Target characters per chunk
            chunk_overlap: Overlap between chunks in characters
            min_chunk_size: Minimum chunk size (skip smaller chunks)

        Returns:
            List of TextChunk objects
        """
        from literature_core import TextChunk

        if not full_text or not full_text.strip():
            return []

        # Clean text
        text = self._clean_text(full_text)

        if len(text) < min_chunk_size:
            return []

        # Detect sections
        sections = self._detect_sections(text)

        # Split into chunks
        chunks = []
        pos = 0
        chunk_index = 0

        while pos < len(text):
            # Determine end position for this chunk
            end_pos = min(pos + chunk_size, len(text))

            # Try to end at a sentence boundary
            if end_pos < len(text):
                end_pos = self._find_sentence_boundary(text, pos, end_pos)

            # Extract chunk text
            chunk_text = text[pos:end_pos].strip()

            # Skip chunks that are too small
            if len(chunk_text) >= min_chunk_size:
                # Find which section this chunk belongs to
                section = self._get_section_for_position(pos, sections)

                chunks.append(TextChunk(
                    paper_id=paper_id,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    start_char=pos,
                    end_char=end_pos,
                    section=section,
                ))
                chunk_index += 1

            # Move to next position with overlap
            pos = end_pos - chunk_overlap if end_pos < len(text) else len(text)

            # Ensure we make progress
            if pos <= chunks[-1].start_char if chunks else 0:
                pos = end_pos

        logger.debug(
            f"Chunked paper {paper_id}: {len(text)} chars -> {len(chunks)} chunks"
        )
        return chunks

    def embed_paper_chunks(
        self,
        paper_id: int,
        full_text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list:
        """
        Chunk paper and generate embeddings for each chunk.

        Args:
            paper_id: Paper ID
            full_text: Full text of the paper
            chunk_size: Target characters per chunk
            chunk_overlap: Overlap between chunks

        Returns:
            List of ChunkEmbedding objects
        """
        from literature_core import ChunkEmbedding

        # Generate chunks
        chunks = self.chunk_paper(
            paper_id=paper_id,
            full_text=full_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if not chunks:
            return []

        # Batch embed all chunks
        texts = [c.text for c in chunks]
        embeddings = self.generate(texts, show_progress=False)

        # Convert to list if single embedding
        if len(chunks) == 1:
            embeddings = [embeddings]

        # Create ChunkEmbedding objects
        chunk_embeddings = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk_embeddings.append(ChunkEmbedding(
                chunk_id=chunk.chunk_id,
                paper_id=chunk.paper_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                embedding=embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
                section=chunk.section,
            ))

        logger.debug(
            f"Generated {len(chunk_embeddings)} chunk embeddings for paper {paper_id}"
        )
        return chunk_embeddings

    def _clean_text(self, text: str) -> str:
        """Clean text for chunking."""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        return text.strip()

    def _detect_sections(self, text: str) -> List[tuple]:
        """
        Detect section headers and their positions.

        Returns:
            List of (section_name, start_pos, end_pos) tuples
        """
        sections = []
        lines = text.split('\n')
        pos = 0

        for line in lines:
            for pattern, section_name in SECTION_PATTERNS:
                if re.match(pattern, line):
                    sections.append((section_name, pos, pos + len(line)))
                    break
            pos += len(line) + 1  # +1 for newline

        return sections

    def _get_section_for_position(
        self,
        pos: int,
        sections: List[tuple]
    ) -> Optional[str]:
        """Get the section name for a given character position."""
        current_section = None
        for section_name, start, _ in sections:
            if start <= pos:
                current_section = section_name
            else:
                break
        return current_section

    def _find_sentence_boundary(
        self,
        text: str,
        start: int,
        target_end: int
    ) -> int:
        """
        Find the best sentence boundary near the target end position.

        Prefers ending at sentence boundaries (. ! ?) but won't
        go too far back from the target.
        """
        # Look for sentence endings in the last 20% of the chunk
        search_start = start + int((target_end - start) * 0.8)
        search_text = text[search_start:target_end]

        # Find sentence endings
        for i in range(len(search_text) - 1, -1, -1):
            if search_text[i] in '.!?' and (i + 1 >= len(search_text) or search_text[i + 1] in ' \n\t'):
                return search_start + i + 1

        # No sentence boundary found, return original target
        return target_end

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
