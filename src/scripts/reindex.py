#!/usr/bin/env python3
"""Reindex script for Literature MCP Server.

Rebuilds search indexes and embeddings:
- Regenerate embeddings for papers missing from ChromaDB
- Regenerate chunk embeddings for papers with full_text
- Update search index timestamps
- Clear and rebuild collections

Usage:
    python -m scripts.reindex --full         # Complete rebuild
    python -m scripts.reindex --incremental  # Only missing items
    python -m scripts.reindex --papers 1 2 3 # Specific papers
"""
import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add src to path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@dataclass
class ReindexResult:
    """Result of reindexing operation."""
    timestamp: str
    mode: str
    papers_processed: int
    embeddings_created: int
    chunks_processed: int
    errors: List[str]
    duration_seconds: float


def get_all_paper_ids() -> List[int]:
    """Get all paper IDs from database."""
    from literature_core.database import get_session
    from literature_core.models import Paper

    with get_session() as session:
        papers = session.query(Paper.id).all()
        return [p[0] for p in papers]


def get_papers_needing_embeddings() -> List[int]:
    """Get papers that don't have embeddings in vector store."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper
        from embeddings.vectorstore import get_vector_store

        store = get_vector_store()
        all_papers = get_all_paper_ids()

        # Check which papers exist in vector store
        missing = []
        for paper_id in all_papers:
            if not store.exists(str(paper_id)):
                missing.append(paper_id)

        return missing
    except Exception as e:
        print(f"Warning: Could not check vector store: {e}", file=sys.stderr)
        return []


def get_papers_with_full_text() -> List[int]:
    """Get papers that have full text for chunking."""
    from literature_core.database import get_session
    from literature_core.models import Paper

    with get_session() as session:
        papers = session.query(Paper.id).filter(
            Paper.full_text.isnot(None)
        ).all()
        return [p[0] for p in papers]


def create_paper_embedding(paper_id: int) -> bool:
    """Create embedding for a single paper."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper
        from embeddings.generator import get_embedding_generator
        from embeddings.vectorstore import get_vector_store

        with get_session() as session:
            paper = session.query(Paper).get(paper_id)
            if not paper:
                return False

            # Generate embedding
            gen = get_embedding_generator()
            text = f"{paper.title} {paper.abstract or ''}"
            embedding = gen.generate(text)

            # Store in vector store
            store = get_vector_store()
            store.add(
                str(paper.id),
                embedding,
                {
                    "title": paper.title,
                    "year": paper.year,
                    "has_abstract": paper.abstract is not None
                }
            )
            return True
    except Exception as e:
        print(f"Error creating embedding for paper {paper_id}: {e}", file=sys.stderr)
        return False


def create_paper_chunks(paper_id: int) -> int:
    """Create chunk embeddings for a paper with full text."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper
        from embeddings.generator import get_embedding_generator
        from embeddings.vectorstore import get_chunk_store
        from embeddings.chunker import TextChunker

        with get_session() as session:
            paper = session.query(Paper).get(paper_id)
            if not paper or not paper.full_text:
                return 0

            # Chunk the text
            chunker = TextChunker()
            chunks = chunker.chunk_text(paper.full_text, source_id=str(paper.id))

            # Generate embeddings
            gen = get_embedding_generator()
            store = get_chunk_store()

            for chunk in chunks:
                embedding = gen.generate(chunk.text)
                store.add(
                    f"{paper.id}_{chunk.chunk_index}",
                    embedding,
                    {
                        "paper_id": paper.id,
                        "chunk_index": chunk.chunk_index,
                        "start_pos": chunk.start_pos,
                        "end_pos": chunk.end_pos
                    },
                    chunk.text
                )

            return len(chunks)
    except Exception as e:
        print(f"Error creating chunks for paper {paper_id}: {e}", file=sys.stderr)
        return 0


def run_reindex(
    mode: str = "incremental",
    paper_ids: Optional[List[int]] = None,
    verbose: bool = False
) -> ReindexResult:
    """Run reindexing operation."""
    import time
    start_time = time.time()

    errors = []
    papers_processed = 0
    embeddings_created = 0
    chunks_processed = 0

    # Determine which papers to process
    if paper_ids:
        target_papers = paper_ids
    elif mode == "full":
        target_papers = get_all_paper_ids()
    else:  # incremental
        target_papers = get_papers_needing_embeddings()

    if verbose:
        print(f"Processing {len(target_papers)} papers...", file=sys.stderr)

    # Process paper embeddings
    for paper_id in target_papers:
        if verbose:
            print(f"  Processing paper {paper_id}...", file=sys.stderr)

        if create_paper_embedding(paper_id):
            embeddings_created += 1
        else:
            errors.append(f"Failed to create embedding for paper {paper_id}")

        papers_processed += 1

    # Process chunks for papers with full text
    if mode == "full" or paper_ids:
        papers_with_text = paper_ids or get_papers_with_full_text()
        for paper_id in papers_with_text:
            if paper_id in (paper_ids or target_papers):
                chunk_count = create_paper_chunks(paper_id)
                chunks_processed += chunk_count

    duration = time.time() - start_time

    return ReindexResult(
        timestamp=datetime.now().isoformat(),
        mode=mode,
        papers_processed=papers_processed,
        embeddings_created=embeddings_created,
        chunks_processed=chunks_processed,
        errors=errors,
        duration_seconds=round(duration, 2)
    )


def print_result(result: ReindexResult, json_output: bool = False):
    """Print reindex result."""
    if json_output:
        print(json.dumps(asdict(result), indent=2))
        return

    print(f"\n{'='*60}")
    print("Literature Reindex Complete")
    print(f"Timestamp: {result.timestamp}")
    print(f"Mode: {result.mode}")
    print(f"{'='*60}\n")

    print(f"Papers processed: {result.papers_processed}")
    print(f"Embeddings created: {result.embeddings_created}")
    print(f"Chunks processed: {result.chunks_processed}")
    print(f"Duration: {result.duration_seconds}s")

    if result.errors:
        print(f"\n{len(result.errors)} errors occurred:")
        for error in result.errors[:10]:  # Show first 10
            print(f"  - {error}")
        if len(result.errors) > 10:
            print(f"  ... and {len(result.errors) - 10} more")

    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Rebuild search indexes and embeddings"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Complete rebuild of all indexes"
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only process missing items (default)"
    )
    parser.add_argument(
        "--papers",
        nargs="+",
        type=int,
        help="Specific paper IDs to reindex"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    args = parser.parse_args()

    # Determine mode
    if args.papers:
        mode = "specific"
    elif args.full:
        mode = "full"
    else:
        mode = "incremental"

    result = run_reindex(
        mode=mode,
        paper_ids=args.papers,
        verbose=args.verbose
    )

    print_result(result, json_output=args.json)

    if result.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
