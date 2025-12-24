#!/usr/bin/env python3
"""
Reindex all papers with chunk-level embeddings.

This script generates chunk embeddings for papers that have full text,
enabling semantic search to find content within paper bodies.

Usage:
    # Full reindex (all papers with full_text)
    python -m scripts.reindex_embeddings

    # Single paper
    python -m scripts.reindex_embeddings --paper-id 123

    # Dry run (preview only)
    python -m scripts.reindex_embeddings --dry-run

    # Custom chunk size
    python -m scripts.reindex_embeddings --chunk-size 600 --chunk-overlap 100

    # Show stats only
    python -m scripts.reindex_embeddings --stats
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add infrastructure path for embedding imports
_infra_path = Path(__file__).parent.parent.parent / "infrastructure/literature-ai/src"
sys.path.insert(0, str(_infra_path))

from literature_core import get_session, Paper, setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


def get_papers_with_fulltext(paper_id: int | None = None) -> list[Paper]:
    """Get papers that have full text available."""
    with get_session() as session:
        query = session.query(Paper).filter(Paper.full_text.isnot(None))

        if paper_id:
            query = query.filter(Paper.id == paper_id)

        papers = query.all()
        # Detach from session
        for p in papers:
            session.expunge(p)

        return papers


def reindex_paper(
    paper: Paper,
    generator,
    chunk_store,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> int:
    """
    Reindex a single paper.

    Returns:
        Number of chunks created
    """
    if not paper.full_text:
        return 0

    # Remove old chunks for this paper
    try:
        chunk_store.delete_paper_chunks(paper.id)
    except Exception as e:
        logger.debug(f"No existing chunks to delete for paper {paper.id}: {e}")

    # Generate chunk embeddings
    chunk_embeddings = generator.embed_paper_chunks(
        paper_id=paper.id,
        full_text=paper.full_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if not chunk_embeddings:
        return 0

    # Add to vector store
    chunk_store.add_chunks(
        chunk_ids=[c.chunk_id for c in chunk_embeddings],
        embeddings=[c.embedding for c in chunk_embeddings],
        texts=[c.text for c in chunk_embeddings],
        metadatas=[c.to_metadata() for c in chunk_embeddings],
    )

    return len(chunk_embeddings)


def show_stats():
    """Show current chunk store statistics."""
    from embeddings.vectorstore import get_chunk_store, get_vector_store

    print("\n" + "=" * 60)
    print("VECTOR STORE STATISTICS")
    print("=" * 60)

    # Paper-level embeddings
    try:
        paper_store = get_vector_store()
        paper_stats = paper_store.get_stats()
        print(f"\nPaper-level embeddings:")
        print(f"  Collection: {paper_stats['collection_name']}")
        print(f"  Count: {paper_stats['count']}")
        print(f"  Path: {paper_stats['persist_directory']}")
    except Exception as e:
        print(f"\nPaper-level embeddings: Error - {e}")

    # Chunk-level embeddings
    try:
        chunk_store = get_chunk_store()
        chunk_stats = chunk_store.get_stats()
        print(f"\nChunk-level embeddings:")
        print(f"  Collection: {chunk_stats['collection_name']}")
        print(f"  Total chunks: {chunk_stats['total_chunks']}")
        print(f"  Papers indexed: {chunk_stats['papers_indexed']}")
        print(f"  Path: {chunk_stats['persist_directory']}")
    except Exception as e:
        print(f"\nChunk-level embeddings: Error - {e}")

    # Database papers with full text
    papers = get_papers_with_fulltext()
    print(f"\nDatabase:")
    print(f"  Papers with full text: {len(papers)}")

    # Check for missing chunks
    indexed_paper_ids = set()
    try:
        chunk_store = get_chunk_store()
        stats = chunk_store.get_stats()
        # This is a rough estimate
        print(f"\nCoverage:")
        print(f"  Papers in DB with full_text: {len(papers)}")
        print(f"  Papers with chunk embeddings: {stats['papers_indexed']}")
        if len(papers) > stats['papers_indexed']:
            print(f"  Papers needing indexing: {len(papers) - stats['papers_indexed']}")
    except Exception:
        pass

    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reindex papers with chunk-level embeddings"
    )
    parser.add_argument(
        "--paper-id",
        type=int,
        help="Reindex single paper by ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't make changes",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Target characters per chunk (default: 500)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Overlap between chunks in characters (default: 50)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Papers to process before logging progress (default: 10)",
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    # Get papers to process
    papers = get_papers_with_fulltext(args.paper_id)

    if not papers:
        if args.paper_id:
            print(f"Paper {args.paper_id} not found or has no full text")
        else:
            print("No papers with full text found")
        return

    print("=" * 60)
    print("CHUNK EMBEDDING REINDEX")
    print("=" * 60)
    print(f"\nPapers to process: {len(papers)}")
    print(f"Chunk size: {args.chunk_size} chars")
    print(f"Chunk overlap: {args.chunk_overlap} chars")

    if args.dry_run:
        print("\nDRY RUN MODE - No changes will be made\n")

        # Show sample chunking for first paper
        if papers:
            from embeddings.generator import get_embedding_generator
            generator = get_embedding_generator()

            paper = papers[0]
            chunks = generator.chunk_paper(
                paper_id=paper.id,
                full_text=paper.full_text,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
            print(f"Sample: Paper {paper.id} would produce {len(chunks)} chunks")
            if chunks:
                print(f"  First chunk: {chunks[0].text[:100]}...")
                if len(chunks) > 1:
                    print(f"  Last chunk: {chunks[-1].text[:100]}...")

        # Estimate total chunks
        total_chars = sum(len(p.full_text) for p in papers if p.full_text)
        estimated_chunks = total_chars // (args.chunk_size - args.chunk_overlap)
        print(f"\nEstimated total chunks: ~{estimated_chunks}")
        return

    # Import embedding tools
    print("\nInitializing embedding model...")
    from embeddings.generator import get_embedding_generator
    from embeddings.vectorstore import get_chunk_store

    generator = get_embedding_generator()
    chunk_store = get_chunk_store()

    print(f"Model: {generator.model_name}")
    print(f"Device: {generator.device}")
    print(f"Embedding dimension: {generator.dimension}\n")

    # Process papers
    total_chunks = 0
    errors = 0

    try:
        from tqdm import tqdm
        iterator = tqdm(papers, desc="Indexing papers")
    except ImportError:
        iterator = papers
        print("(Install tqdm for progress bar: pip install tqdm)")

    for i, paper in enumerate(iterator):
        try:
            chunks = reindex_paper(
                paper=paper,
                generator=generator,
                chunk_store=chunk_store,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
            total_chunks += chunks

            if (i + 1) % args.batch_size == 0:
                logger.info(
                    f"Progress: {i + 1}/{len(papers)} papers, "
                    f"{total_chunks} chunks created"
                )

        except Exception as e:
            logger.error(f"Failed to index paper {paper.id}: {e}")
            errors += 1

    # Final stats
    print("\n" + "-" * 60)
    print(f"COMPLETE")
    print("-" * 60)
    print(f"Papers processed: {len(papers)}")
    print(f"Chunks created: {total_chunks}")
    print(f"Errors: {errors}")

    # Show final stats
    show_stats()


if __name__ == "__main__":
    main()
