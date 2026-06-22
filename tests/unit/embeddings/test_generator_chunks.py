"""Regression tests for EmbeddingGenerator.embed_paper_chunks.

Usage:
    mamba run -n litai python -m pytest tests/unit/embeddings/test_generator_chunks.py -q

Covers the single-chunk double-nesting bug: when a paper chunks to exactly one
chunk, generate() (called with a list) already returns a 2D array of shape
(1, dim), so the special-case re-wrapping produced a 2D per-chunk embedding
([[...]]) that ChromaDB rejected once the service wrapped it again ([[[...]]]).
"""
from __future__ import annotations

import pytest

from embeddings.generator import EmbeddingGenerator


def _nesting_depth(value) -> int:
    depth = 0
    while isinstance(value, list):
        depth += 1
        if not value:
            break
        value = value[0]
    return depth


@pytest.fixture(scope="module")
def generator() -> EmbeddingGenerator:
    return EmbeddingGenerator()


def test_single_chunk_embedding_is_flat(generator):
    """A paper that produces exactly one chunk must yield a flat (depth-1) embedding."""
    text = (
        "Zinc oxide thin films grown by atomic layer deposition exhibit tunable "
        "electronic and optical properties. "
    ) * 4  # ~420 chars -> one chunk at default chunk_size=500
    chunk_embeddings = generator.embed_paper_chunks(paper_id=999_999, full_text=text)

    assert len(chunk_embeddings) == 1
    embedding = chunk_embeddings[0].embedding
    assert _nesting_depth(embedding) == 1, "single-chunk embedding must be a flat list of floats"
    assert all(isinstance(x, float) for x in embedding)


def test_multi_chunk_embeddings_are_flat(generator):
    """Multi-chunk papers must also yield flat (depth-1) per-chunk embeddings."""
    text = (
        "Zinc oxide thin films grown by atomic layer deposition exhibit tunable "
        "electronic and optical properties suitable for nanolithography. "
    ) * 60  # large enough to produce several chunks
    chunk_embeddings = generator.embed_paper_chunks(paper_id=999_998, full_text=text)

    assert len(chunk_embeddings) > 1
    for ce in chunk_embeddings:
        assert _nesting_depth(ce.embedding) == 1
        assert all(isinstance(x, float) for x in ce.embedding)
