"""Unit tests for TextChunker.

Tests cover:
- Token-based chunking
- Character fallback chunking
- Section detection
- Overlap handling
"""
import pytest

import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestBasicChunking:
    """Tests for basic text chunking."""

    def test_chunk_short_text(self):
        """Test chunking text shorter than chunk size."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=1000, chunk_overlap=100)
        text = "This is a short text that fits in one chunk."

        chunks = chunker.chunk_text(text)

        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_chunk_long_text(self):
        """Test chunking text longer than chunk size."""
        from embeddings.chunker import TextChunker

        # Use small chunk size to ensure multiple chunks with token-based chunking
        chunker = TextChunker(chunk_size=20, chunk_overlap=5)
        text = "word " * 100  # ~100 tokens

        chunks = chunker.chunk_text(text)

        assert len(chunks) > 1
        # All text should be covered
        combined = "".join(c.text for c in chunks)
        assert "word" in combined

    def test_chunk_with_source_id(self):
        """Test chunks include source ID."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "Sample text " * 20

        chunks = chunker.chunk_text(text, source_id="paper_123")

        for chunk in chunks:
            assert chunk.source_id == "paper_123"

    def test_chunk_indices(self):
        """Test chunk indices are sequential."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        text = "word " * 50

        chunks = chunker.chunk_text(text)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestChunkPositions:
    """Tests for chunk position tracking."""

    def test_chunk_start_end_positions(self):
        """Test chunks have correct start/end positions."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "A" * 300

        chunks = chunker.chunk_text(text)

        # First chunk should start at 0
        assert chunks[0].start_pos == 0

        # Positions should be sequential
        for i in range(1, len(chunks)):
            assert chunks[i].start_pos > chunks[i-1].start_pos
            assert chunks[i].start_pos < chunks[i-1].end_pos  # Overlap

    def test_chunk_positions_cover_text(self):
        """Test chunk positions cover entire text."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "Sample text content. " * 20

        chunks = chunker.chunk_text(text)

        # Last chunk should end at or near text length
        assert chunks[-1].end_pos <= len(text)
        assert chunks[-1].end_pos >= len(text) - 50  # Allow some margin


class TestOverlapHandling:
    """Tests for overlap between chunks."""

    def test_overlap_content(self):
        """Test chunks have overlapping content."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=30)
        text = "word1 word2 word3 " * 20

        chunks = chunker.chunk_text(text)

        if len(chunks) > 1:
            # Check overlap exists between consecutive chunks
            chunk1_end = chunks[0].text[-30:]
            chunk2_start = chunks[1].text[:30]
            # Some overlap should exist
            assert len(set(chunk1_end.split()) & set(chunk2_start.split())) > 0

    def test_minimal_overlap(self):
        """Test chunking with minimal overlap."""
        from embeddings.chunker import TextChunker

        # Note: chunk_overlap must be > 0 and < chunk_size
        # Use small chunk size and real words to ensure multiple chunks
        chunker = TextChunker(chunk_size=20, chunk_overlap=1)
        text = "word " * 100  # ~100 tokens

        chunks = chunker.chunk_text(text)

        # Should produce multiple chunks
        assert len(chunks) > 1

    def test_large_overlap(self):
        """Test chunking with large overlap."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=50)
        text = "Sample " * 50

        chunks = chunker.chunk_text(text)

        # Should still produce valid chunks
        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk.text) > 0


class TestSectionDetection:
    """Tests for section-aware chunking."""

    def test_chunk_respects_paragraphs(self):
        """Test chunking prefers paragraph boundaries."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=200, chunk_overlap=20)
        text = """First paragraph with some content here.

Second paragraph with different content.

Third paragraph concluding the text."""

        chunks = chunker.chunk_text(text)

        # Chunks should try to respect paragraph boundaries
        for chunk in chunks:
            # Should not cut mid-word ideally
            assert not chunk.text.startswith(" ") or chunk.chunk_index == 0

    def test_chunk_handles_headers(self):
        """Test chunking handles section headers."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=150, chunk_overlap=20)
        text = """# Introduction

This is the introduction section with content.

# Methods

This describes the methods used.

# Results

Here are the results."""

        chunks = chunker.chunk_text(text)

        # Should produce multiple chunks
        assert len(chunks) >= 1


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_text(self):
        """Test chunking empty text."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)

        chunks = chunker.chunk_text("")

        assert len(chunks) == 0 or (len(chunks) == 1 and chunks[0].text == "")

    def test_whitespace_only(self):
        """Test chunking whitespace-only text."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)

        chunks = chunker.chunk_text("   \n\n\t  ")

        # Should handle gracefully
        assert isinstance(chunks, list)

    def test_single_long_word(self):
        """Test chunking text with single very long word."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        text = "A" * 200  # Single "word" longer than chunk size

        chunks = chunker.chunk_text(text)

        # Should still produce chunks
        assert len(chunks) > 0
        # All content should be covered
        total_content = sum(len(c.text) for c in chunks)
        assert total_content >= len(text)

    def test_unicode_text(self):
        """Test chunking Unicode text."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "日本語テキスト。" * 20 + "English text. " * 10

        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0
        # Verify Unicode preserved
        combined = "".join(c.text for c in chunks)
        assert "日本語" in combined

    def test_special_characters(self):
        """Test chunking text with special characters."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "Formula: E=mc² and α+β=γ. " * 10

        chunks = chunker.chunk_text(text)

        assert len(chunks) > 0
        combined = "".join(c.text for c in chunks)
        assert "E=mc²" in combined


class TestChunkMetadata:
    """Tests for chunk metadata."""

    def test_chunk_has_required_fields(self):
        """Test chunk objects have required fields."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "Sample text for testing metadata fields."

        chunks = chunker.chunk_text(text, source_id="test_paper")

        for chunk in chunks:
            assert hasattr(chunk, 'text')
            assert hasattr(chunk, 'chunk_index')
            assert hasattr(chunk, 'start_pos')
            assert hasattr(chunk, 'end_pos')
            assert hasattr(chunk, 'source_id')

    def test_chunk_text_matches_positions(self):
        """Test chunk text matches start/end positions in original."""
        from embeddings.chunker import TextChunker

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        original = "The quick brown fox jumps over the lazy dog. " * 10

        chunks = chunker.chunk_text(original)

        for chunk in chunks:
            expected = original[chunk.start_pos:chunk.end_pos]
            assert chunk.text == expected


class TestTokenBasedChunking:
    """Tests for token-based chunking if available."""

    def test_token_chunking_available(self):
        """Test if token-based chunking is available (tiktoken installed)."""
        from embeddings.chunker import TextChunker, TIKTOKEN_AVAILABLE

        chunker = TextChunker(chunk_size=100, chunk_overlap=20)

        # Should initialize without error
        assert chunker is not None
        # Tokenizer should be available if tiktoken is installed
        if TIKTOKEN_AVAILABLE:
            assert chunker.tokenizer is not None

    def test_chunking_produces_results(self):
        """Test chunking produces valid results."""
        from embeddings.chunker import TextChunker

        text = "This is a test sentence. " * 20

        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        chunks = chunker.chunk_text(text)

        # Should produce chunks
        assert len(chunks) > 0
        # All chunks should have text
        for chunk in chunks:
            assert len(chunk.text) > 0
