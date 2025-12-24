"""Chunk models for text embedding.

This module defines dataclasses for text chunks and chunk embeddings
used in chunk-level semantic search.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextChunk:
    """A chunk of text from a paper with metadata."""

    paper_id: int
    chunk_index: int
    text: str
    start_char: int
    end_char: int
    section: str | None = None

    @property
    def chunk_id(self) -> str:
        """Generate unique chunk ID."""
        return f"{self.paper_id}_{self.chunk_index}"

    @property
    def length(self) -> int:
        """Get the length of the chunk text."""
        return len(self.text)

    def __repr__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        section_str = f", section={self.section}" if self.section else ""
        return f"TextChunk(id={self.chunk_id}, len={self.length}{section_str}, text='{preview}')"


@dataclass
class ChunkEmbedding:
    """A text chunk with its embedding vector."""

    chunk_id: str
    paper_id: int
    chunk_index: int
    text: str
    embedding: list[float]
    section: str | None = None

    def to_metadata(self) -> dict:
        """Convert to ChromaDB metadata dict."""
        return {
            "paper_id": self.paper_id,
            "chunk_index": self.chunk_index,
            "section": self.section or "",
        }


@dataclass
class ChunkSearchResult:
    """A search result from chunk-level search."""

    chunk_id: str
    paper_id: int
    chunk_index: int
    text: str
    score: float
    section: str | None = None

    def __repr__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"ChunkSearchResult(paper={self.paper_id}, score={self.score:.3f}, text='{preview}')"
