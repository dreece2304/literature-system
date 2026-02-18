#!/usr/bin/env python3
"""Reindex script for Literature MCP Server.

Rebuilds search indexes and embeddings:
- Regenerate embeddings for papers missing from ChromaDB
- Regenerate chunk embeddings for papers with PaperChunk records
- Update search index timestamps
- Clear and rebuild collections

Usage:
    python -m scripts.reindex --full         # Complete rebuild
    python -m scripts.reindex --incremental  # Only missing items
    python -m scripts.reindex --papers 1 2 3 # Specific papers
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from dataclasses import dataclass, field, asdict
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
    timestamp: str = ""
    mode: str = ""
    papers_processed: int = 0
    embeddings_created: int = 0
    chunks_processed: int = 0
    errors: List[tuple] = field(default_factory=list)  # (paper_id, error_msg)
    duration_seconds: float = 0.0


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


def get_papers_with_chunks() -> List[int]:
    """Get papers that have chunks available (extracted full text)."""
    from literature_core.database import get_session
    from literature_core.models import PaperChunk

    with get_session() as session:
        papers = session.query(PaperChunk.paper_id).distinct().all()
        return [p[0] for p in papers]


def create_paper_embedding(paper_id: int) -> tuple[bool, Optional[str]]:
    """Create embedding for a single paper. Returns (success, error_msg)."""
    try:
        from literature_core.database import get_session
        from literature_core.models import Paper
        from embeddings.generator import get_embedding_generator
        from embeddings.vectorstore import get_vector_store

        with get_session() as session:
            paper = session.get(Paper, paper_id)
            if not paper:
                return False, "Paper not found"

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
            return True, None
    except Exception as e:
        return False, str(e)


def create_paper_chunks(paper_id: int) -> tuple[int, Optional[str]]:
    """Create chunk embeddings for a paper. Returns (chunk_count, error_msg)."""
    try:
        from services.paper_service import PaperService
        from embeddings.generator import get_embedding_generator
        from embeddings.vectorstore import get_chunk_store
        from embeddings.chunker import TextChunker

        # Get full text from chunks
        full_text = PaperService.get_full_text(paper_id)
        if not full_text:
            return 0, None  # No full text, not an error

        # Chunk the text
        chunker = TextChunker()
        chunks = chunker.chunk_text(full_text, source_id=str(paper_id))

        if not chunks:
            return 0, None

        # Generate embeddings in batch
        gen = get_embedding_generator()
        store = get_chunk_store()

        chunk_ids = []
        embeddings = []
        texts = []
        metadatas = []

        for chunk in chunks:
            embedding = gen.generate(chunk.text)
            chunk_ids.append(f"{paper_id}_{chunk.chunk_index}")
            embeddings.append(embedding)
            texts.append(chunk.text)
            metadatas.append({
                "paper_id": paper_id,
                "chunk_index": chunk.chunk_index,
                "start_pos": chunk.start_pos,
                "end_pos": chunk.end_pos
            })

        # Add all chunks in batch
        store.add_chunks(chunk_ids, embeddings, texts, metadatas)

        return len(chunks), None
    except Exception as e:
        return 0, str(e)


def run_with_rich_display(
    mode: str,
    paper_ids: Optional[List[int]] = None
) -> ReindexResult:
    """Run reindexing with rich progress display."""
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn,
        TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
    )
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    result = ReindexResult()
    result.timestamp = datetime.now().isoformat()
    result.mode = mode
    start_time = time.time()

    # Determine which papers to process
    console.print("\n[bold]Phase 1/3: Determining papers to process...[/bold]")

    if paper_ids:
        target_papers = paper_ids
        console.print(f"  Specific papers requested: {len(target_papers)}")
    elif mode == "full":
        target_papers = get_all_paper_ids()
        console.print(f"  Full rebuild: {len(target_papers)} papers")
    else:
        target_papers = get_papers_needing_embeddings()
        console.print(f"  Incremental: {len(target_papers)} papers missing embeddings")

    if not target_papers:
        console.print("[green]No papers to process![/green]")
        result.duration_seconds = round(time.time() - start_time, 2)
        return result

    # Get papers with chunks for chunk embedding
    papers_with_chunks = set(get_papers_with_chunks())
    target_with_chunks = [p for p in target_papers if p in papers_with_chunks]
    console.print(f"  Papers with chunks to embed: {len(target_with_chunks)}")

    # Suppress all logging and warnings during progress display
    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)
    logging.getLogger("embeddings").setLevel(logging.ERROR)
    logging.getLogger("services").setLevel(logging.ERROR)
    logging.getLogger("literature_core").setLevel(logging.ERROR)
    logging.getLogger("chromadb").setLevel(logging.ERROR)
    logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)

    # Also suppress loguru (used by embeddings module)
    from loguru import logger as loguru_logger
    loguru_logger.disable("embeddings")
    loguru_logger.disable("embeddings.generator")
    loguru_logger.disable("embeddings.vectorstore")
    loguru_logger.disable("services")

    # Pre-initialize embedding generator to avoid log output during progress
    from embeddings.generator import get_embedding_generator
    from embeddings.vectorstore import get_vector_store, get_chunk_store
    console.print("  Initializing embedding model...")
    get_embedding_generator()
    get_vector_store()
    get_chunk_store()

    # Phase 2: Paper embeddings
    console.print("\n[bold]Phase 2/3: Creating paper embeddings...[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("[cyan]Paper embeddings...", total=len(target_papers))

        for paper_id in target_papers:
            success, error = create_paper_embedding(paper_id)
            if success:
                result.embeddings_created += 1
                desc = f"[green]✓[/green] Paper {paper_id}"
            else:
                result.errors.append((paper_id, f"Embedding: {error}"))
                desc = f"[red]✗[/red] Paper {paper_id}"

            result.papers_processed += 1
            progress.update(task, advance=1, description=desc)

    # Phase 3: Chunk embeddings
    if target_with_chunks:
        console.print("\n[bold]Phase 3/3: Creating chunk embeddings...[/bold]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("[cyan]Chunk embeddings...", total=len(target_with_chunks))

            for paper_id in target_with_chunks:
                chunk_count, error = create_paper_chunks(paper_id)
                if error:
                    result.errors.append((paper_id, f"Chunks: {error}"))
                    desc = f"[red]✗[/red] Paper {paper_id}"
                elif chunk_count > 0:
                    result.chunks_processed += chunk_count
                    desc = f"[green]✓[/green] Paper {paper_id}: {chunk_count} chunks"
                else:
                    desc = f"[yellow]○[/yellow] Paper {paper_id}: no text"

                progress.update(task, advance=1, description=desc)
    else:
        console.print("\n[bold]Phase 3/3: Chunk embeddings...[/bold]")
        console.print("  [dim]No papers with chunks to process[/dim]")

    # Restore logging
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger("embeddings").setLevel(logging.INFO)
    logging.getLogger("services").setLevel(logging.INFO)
    logging.getLogger("literature_core").setLevel(logging.INFO)

    result.duration_seconds = round(time.time() - start_time, 2)
    return result


def run_simple(
    mode: str,
    paper_ids: Optional[List[int]] = None,
    verbose: bool = False
) -> ReindexResult:
    """Run reindexing with simple text output."""
    result = ReindexResult()
    result.timestamp = datetime.now().isoformat()
    result.mode = mode
    start_time = time.time()

    # Determine which papers to process
    if paper_ids:
        target_papers = paper_ids
    elif mode == "full":
        target_papers = get_all_paper_ids()
    else:
        target_papers = get_papers_needing_embeddings()

    if verbose:
        print(f"Processing {len(target_papers)} papers...")

    # Process paper embeddings
    for paper_id in target_papers:
        if verbose:
            print(f"  Processing paper {paper_id}...")

        success, error = create_paper_embedding(paper_id)
        if success:
            result.embeddings_created += 1
        else:
            result.errors.append((paper_id, f"Embedding: {error}"))

        result.papers_processed += 1

    # Process chunks
    if mode == "full" or paper_ids:
        papers_with_chunks = set(get_papers_with_chunks())
        target_with_chunks = [p for p in target_papers if p in papers_with_chunks]

        for paper_id in target_with_chunks:
            chunk_count, error = create_paper_chunks(paper_id)
            if error:
                result.errors.append((paper_id, f"Chunks: {error}"))
            else:
                result.chunks_processed += chunk_count

    result.duration_seconds = round(time.time() - start_time, 2)
    return result


def print_result(result: ReindexResult, json_output: bool = False):
    """Print reindex result."""
    if json_output:
        # Convert errors to serializable format
        result_dict = asdict(result)
        result_dict["errors"] = [{"paper_id": e[0], "error": e[1]} for e in result.errors]
        print(json.dumps(result_dict, indent=2))
        return

    # Try rich output
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()

        # Summary table
        table = Table(title="Reindex Summary", show_header=False, box=None)
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")
        table.add_row("Mode", result.mode)
        table.add_row("Papers processed", str(result.papers_processed))
        table.add_row("Embeddings created", f"[green]{result.embeddings_created}[/green]")
        table.add_row("Chunks processed", str(result.chunks_processed))
        table.add_row("Duration", f"{result.duration_seconds}s")
        table.add_row("Errors", f"[red]{len(result.errors)}[/red]" if result.errors else "0")

        console.print()
        console.print(Panel(table, title="[bold green]Complete[/bold green]", border_style="green"))

        if result.errors:
            console.print("\n[red]Errors:[/red]")
            for paper_id, error in result.errors[:20]:
                console.print(f"  [{paper_id}] {error[:80]}")
            if len(result.errors) > 20:
                console.print(f"  [dim]... and {len(result.errors) - 20} more[/dim]")

    except ImportError:
        # Fallback to plain text
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
            for paper_id, error in result.errors[:20]:
                print(f"  [{paper_id}] {error[:80]}")
            if len(result.errors) > 20:
                print(f"  ... and {len(result.errors) - 20} more")

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
        help="Verbose output (simple mode only)"
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Use simple text output instead of rich progress"
    )
    args = parser.parse_args()

    # Determine mode
    if args.papers:
        mode = "specific"
    elif args.full:
        mode = "full"
    else:
        mode = "incremental"

    # Check for rich
    use_rich = not args.simple
    if use_rich:
        try:
            from rich.console import Console
        except ImportError:
            use_rich = False
            print("(Install 'rich' for better display: pip install rich)")

    if use_rich:
        result = run_with_rich_display(mode=mode, paper_ids=args.papers)
    else:
        result = run_simple(mode=mode, paper_ids=args.papers, verbose=args.verbose)

    print_result(result, json_output=args.json)

    if result.errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
