"""
Text chunking for long documents.

This module handles splitting long papers into chunks suitable for embedding,
with configurable overlap and token-aware splitting.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from loguru import logger

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available, falling back to character-based chunking")

from config.settings import settings


@dataclass
class TextChunk:
    """Represents a chunk of text with metadata."""

    text: str
    start_pos: int
    end_pos: int
    chunk_index: int
    source_id: Optional[str] = None
    metadata: Optional[Dict] = None

    @property
    def length(self) -> int:
        """Get the length of the chunk text."""
        return len(self.text)

    def __repr__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"TextChunk(index={self.chunk_index}, len={self.length}, text='{preview}')"


class TextChunker:
    """
    Chunks long texts into smaller segments for embedding.

    Features:
    - Token-aware chunking (using tiktoken)
    - Configurable chunk size and overlap
    - Preserves paragraph boundaries when possible
    - Metadata tracking for each chunk
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        encoding_name: str = "cl100k_base",
    ):
        """
        Initialize the text chunker.

        Args:
            chunk_size: Maximum tokens per chunk (default: from settings)
            chunk_overlap: Overlap between chunks in tokens (default: from settings)
            encoding_name: Tiktoken encoding to use (default: cl100k_base for GPT-4)
        """
        self.chunk_size = chunk_size or settings.embedding.chunk_size
        self.chunk_overlap = chunk_overlap or settings.embedding.chunk_overlap

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        # Initialize tokenizer if available
        self.tokenizer = None
        if TIKTOKEN_AVAILABLE:
            try:
                self.tokenizer = tiktoken.get_encoding(encoding_name)
                logger.debug(f"Initialized tiktoken with encoding: {encoding_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize tiktoken: {e}")
                self.tokenizer = None

        self.encoding_name = encoding_name if self.tokenizer else "char-based"

    def chunk_text(
        self,
        text: str,
        source_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> List[TextChunk]:
        """
        Chunk a long text into smaller segments.

        Args:
            text: Text to chunk
            source_id: Identifier for the source document
            metadata: Additional metadata to attach to chunks

        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to chunker")
            return []

        # Clean text
        text = text.strip()

        # Use token-based or character-based chunking
        if self.tokenizer:
            chunks = self._chunk_by_tokens(text)
        else:
            chunks = self._chunk_by_characters(text)

        # Wrap in TextChunk objects
        result = []
        for i, (chunk_text, start, end) in enumerate(chunks):
            result.append(
                TextChunk(
                    text=chunk_text,
                    start_pos=start,
                    end_pos=end,
                    chunk_index=i,
                    source_id=source_id,
                    metadata=metadata,
                )
            )

        logger.debug(
            f"Chunked text ({len(text)} chars) into {len(result)} chunks "
            f"(size={self.chunk_size}, overlap={self.chunk_overlap})"
        )

        return result

    def _chunk_by_tokens(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Chunk text based on token count.

        Returns:
            List of (chunk_text, start_char, end_char) tuples
        """
        # Encode entire text
        tokens = self.tokenizer.encode(text)
        total_tokens = len(tokens)

        if total_tokens <= self.chunk_size:
            # No chunking needed
            return [(text, 0, len(text))]

        chunks = []
        start_token = 0

        while start_token < total_tokens:
            # Determine end token for this chunk
            end_token = min(start_token + self.chunk_size, total_tokens)

            # Extract chunk tokens
            chunk_tokens = tokens[start_token:end_token]

            # Decode back to text
            chunk_text = self.tokenizer.decode(chunk_tokens)

            # Find character positions (approximate)
            if start_token == 0:
                start_char = 0
            else:
                # Decode up to start_token to find character position
                prefix = self.tokenizer.decode(tokens[:start_token])
                start_char = len(prefix)

            if end_token == total_tokens:
                end_char = len(text)
            else:
                prefix = self.tokenizer.decode(tokens[:end_token])
                end_char = len(prefix)

            chunks.append((chunk_text, start_char, end_char))

            # Move to next chunk with overlap
            start_token += self.chunk_size - self.chunk_overlap

        return chunks

    def _chunk_by_characters(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Chunk text based on character count (fallback method).

        Uses approximate token-to-char ratio of 4:1.

        Returns:
            List of (chunk_text, start_char, end_char) tuples
        """
        # Approximate: 1 token ≈ 4 characters
        char_chunk_size = self.chunk_size * 4
        char_overlap = self.chunk_overlap * 4

        if len(text) <= char_chunk_size:
            return [(text, 0, len(text))]

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + char_chunk_size, len(text))

            # Try to break at paragraph or sentence boundary
            if end < len(text):
                # Look for paragraph break
                paragraph_break = text.rfind("\n\n", start, end)
                if paragraph_break > start + char_chunk_size // 2:
                    end = paragraph_break + 2

                # Look for sentence break
                elif "." in text[start:end]:
                    last_period = text.rfind(".", start, end)
                    if last_period > start + char_chunk_size // 2:
                        end = last_period + 1

            chunk_text = text[start:end]
            chunks.append((chunk_text, start, end))

            # Move to next chunk with overlap
            start = end - char_overlap

        return chunks

    def chunk_paper(
        self,
        paper_data: Dict,
        fields: Optional[List[str]] = None,
    ) -> List[TextChunk]:
        """
        Chunk a paper's text fields.

        Args:
            paper_data: Dictionary containing paper data
            fields: Fields to chunk (default: ['full_text', 'abstract'])

        Returns:
            List of text chunks with paper metadata
        """
        if fields is None:
            fields = ["full_text", "abstract"]

        paper_id = paper_data.get("id", paper_data.get("paper_id", "unknown"))
        all_chunks = []

        for field in fields:
            text = paper_data.get(field)

            if not text or not isinstance(text, str) or not text.strip():
                continue

            # Prepare metadata
            metadata = {
                "paper_id": paper_id,
                "field": field,
                "title": paper_data.get("title", "Unknown"),
                "authors": paper_data.get("authors", "Unknown"),
                "year": paper_data.get("year"),
            }

            # Chunk this field
            chunks = self.chunk_text(
                text=text,
                source_id=f"{paper_id}:{field}",
                metadata=metadata,
            )

            all_chunks.extend(chunks)

        logger.debug(
            f"Chunked paper {paper_id} into {len(all_chunks)} chunks from {len(fields)} fields"
        )

        return all_chunks

    def chunk_papers_batch(
        self,
        papers: List[Dict],
        fields: Optional[List[str]] = None,
    ) -> Dict[str, List[TextChunk]]:
        """
        Chunk multiple papers efficiently.

        Args:
            papers: List of paper dictionaries
            fields: Fields to chunk for each paper

        Returns:
            Dictionary mapping paper_id to list of chunks
        """
        result = {}

        for paper in papers:
            paper_id = paper.get("id", paper.get("paper_id", "unknown"))
            chunks = self.chunk_paper(paper, fields=fields)
            result[paper_id] = chunks

        total_chunks = sum(len(chunks) for chunks in result.values())
        logger.info(
            f"Chunked {len(papers)} papers into {total_chunks} total chunks"
        )

        return result

    def get_chunk_stats(self, chunks: List[TextChunk]) -> Dict:
        """
        Get statistics about a list of chunks.

        Args:
            chunks: List of text chunks

        Returns:
            Dictionary with statistics
        """
        if not chunks:
            return {
                "count": 0,
                "total_chars": 0,
                "avg_chars": 0,
                "min_chars": 0,
                "max_chars": 0,
            }

        lengths = [chunk.length for chunk in chunks]

        return {
            "count": len(chunks),
            "total_chars": sum(lengths),
            "avg_chars": sum(lengths) / len(lengths),
            "min_chars": min(lengths),
            "max_chars": max(lengths),
        }

    def __repr__(self) -> str:
        return (
            f"TextChunker("
            f"chunk_size={self.chunk_size}, "
            f"overlap={self.chunk_overlap}, "
            f"encoding={self.encoding_name})"
        )


# Global singleton instance
_chunker_instance: Optional[TextChunker] = None


def get_text_chunker() -> TextChunker:
    """
    Get the global TextChunker instance (singleton pattern).

    Returns:
        Shared TextChunker instance
    """
    global _chunker_instance

    if _chunker_instance is None:
        _chunker_instance = TextChunker()

    return _chunker_instance


def reset_text_chunker():
    """Reset the global chunker instance (useful for testing)."""
    global _chunker_instance
    _chunker_instance = None
