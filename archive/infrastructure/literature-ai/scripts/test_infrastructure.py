#!/usr/bin/env python3
"""
Test script for literature-ai infrastructure components.

Tests:
1. Configuration loading
2. Embedding generation
3. Text chunking
4. Vector store operations
5. End-to-end pipeline
"""

import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()


def test_configuration():
    """Test configuration loading."""
    console.print("\n[bold cyan]═══ Testing Configuration ═══[/bold cyan]")

    try:
        from config.settings import settings

        console.print("✓ Settings loaded successfully", style="green")

        # Display key settings
        table = Table(title="Configuration Summary")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Environment", settings.environment)
        table.add_row("Ollama Host", settings.ollama.host)
        table.add_row("Writer Model", settings.ollama.writer_model)
        table.add_row("Triager Model", settings.ollama.triager_model)
        table.add_row("Embedding Model", settings.embedding.model_name)
        table.add_row("Embedding Dimension", str(settings.embedding.dimension))
        table.add_row("Chunk Size", str(settings.embedding.chunk_size))
        table.add_row("ChromaDB Collection", settings.chromadb.collection_name)
        table.add_row("Redis Host", f"{settings.redis.host}:{settings.redis.port}")

        console.print(table)
        return True

    except Exception as e:
        console.print(f"✗ Configuration test failed: {e}", style="red")
        return False


def test_embedding_generator():
    """Test embedding generation."""
    console.print("\n[bold cyan]═══ Testing Embedding Generator ═══[/bold cyan]")

    try:
        from src.embeddings.generator import EmbeddingGenerator

        # Initialize generator
        console.print("Initializing embedding generator...")
        generator = EmbeddingGenerator()

        console.print(f"✓ Model loaded: {generator.model_name}", style="green")
        console.print(f"  Device: {generator.device}")
        console.print(f"  Dimension: {generator.dimension}")

        # Test single text
        console.print("\nTesting single text embedding...")
        test_text = "Neural networks for natural language processing"
        embedding = generator.generate(test_text)

        console.print(f"✓ Generated embedding shape: {embedding.shape}", style="green")
        console.print(f"  First 5 values: {embedding[:5]}")
        console.print(f"  Norm: {np.linalg.norm(embedding):.4f}")

        # Test batch
        console.print("\nTesting batch embedding...")
        test_texts = [
            "Deep learning for computer vision",
            "Reinforcement learning algorithms",
            "Transfer learning in NLP",
        ]
        embeddings = generator.generate(test_texts)

        console.print(f"✓ Generated {len(embeddings)} embeddings", style="green")
        console.print(f"  Shape: {embeddings.shape}")

        # Test similarity
        console.print("\nTesting similarity computation...")
        sim = generator.compute_similarity(embeddings[0], embeddings[1])
        console.print(f"✓ Similarity between text 1 and 2: {sim:.4f}", style="green")

        # Test paper embedding
        console.print("\nTesting paper embedding...")
        paper_data = {
            "title": "Attention Is All You Need",
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
            "authors": "Vaswani et al.",
            "year": 2017,
        }
        paper_embedding = generator.generate_for_paper(paper_data)
        console.print(f"✓ Generated paper embedding: {paper_embedding.shape}", style="green")

        return True

    except Exception as e:
        console.print(f"✗ Embedding generator test failed: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="dim red")
        return False


def test_text_chunker():
    """Test text chunking."""
    console.print("\n[bold cyan]═══ Testing Text Chunker ═══[/bold cyan]")

    try:
        from src.embeddings.chunker import TextChunker

        # Initialize chunker
        console.print("Initializing text chunker...")
        chunker = TextChunker(chunk_size=128, chunk_overlap=32)

        console.print(f"✓ Chunker initialized", style="green")
        console.print(f"  Chunk size: {chunker.chunk_size} tokens")
        console.print(f"  Overlap: {chunker.chunk_overlap} tokens")
        console.print(f"  Encoding: {chunker.encoding_name}")

        # Test with short text (no chunking needed)
        console.print("\nTesting short text (no chunking)...")
        short_text = "This is a short paper abstract about machine learning."
        chunks = chunker.chunk_text(short_text, source_id="test-short")

        console.print(f"✓ Short text: {len(chunks)} chunk(s)", style="green")

        # Test with long text
        console.print("\nTesting long text (requires chunking)...")
        long_text = " ".join([
            f"This is sentence {i} in a long paper about deep learning and neural networks."
            for i in range(100)
        ])
        chunks = chunker.chunk_text(long_text, source_id="test-long")

        console.print(f"✓ Long text: {len(chunks)} chunks", style="green")

        # Display chunk info
        table = Table(title="Chunk Details")
        table.add_column("Index", style="cyan")
        table.add_column("Length", style="yellow")
        table.add_column("Preview", style="white")

        for chunk in chunks[:3]:  # Show first 3
            preview = chunk.text[:60] + "..." if len(chunk.text) > 60 else chunk.text
            table.add_row(str(chunk.chunk_index), str(chunk.length), preview)

        if len(chunks) > 3:
            table.add_row("...", "...", "...")

        console.print(table)

        # Test paper chunking
        console.print("\nTesting paper chunking...")
        paper_data = {
            "id": "paper-001",
            "title": "Test Paper",
            "abstract": "This is a test abstract. " * 20,
            "full_text": "This is the full text of the paper. " * 100,
        }
        paper_chunks = chunker.chunk_paper(paper_data, fields=["abstract", "full_text"])

        console.print(f"✓ Paper chunked into {len(paper_chunks)} chunks", style="green")

        # Get stats
        stats = chunker.get_chunk_stats(paper_chunks)
        console.print(f"  Total characters: {stats['total_chars']}")
        console.print(f"  Average chunk size: {stats['avg_chars']:.0f} chars")

        return True

    except Exception as e:
        console.print(f"✗ Text chunker test failed: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="dim red")
        return False


def test_vector_store():
    """Test vector store operations."""
    console.print("\n[bold cyan]═══ Testing Vector Store ═══[/bold cyan]")

    try:
        from src.embeddings.vectorstore import VectorStore
        from src.embeddings.generator import EmbeddingGenerator

        # Initialize
        console.print("Initializing vector store...")
        store = VectorStore(collection_name="test_collection")

        console.print(f"✓ Vector store initialized", style="green")
        console.print(f"  Collection: {store.collection_name}")
        console.print(f"  Distance metric: {store.distance_metric}")
        console.print(f"  Current count: {store.count()}")

        # Clear any existing data
        if store.count() > 0:
            console.print("  Clearing existing data...")
            store.reset()

        # Generate test embeddings
        console.print("\nGenerating test embeddings...")
        generator = EmbeddingGenerator()

        test_papers = [
            {
                "id": "paper-1",
                "text": "Deep learning for computer vision applications",
                "metadata": {"title": "CV Paper", "year": 2020, "field": "computer_vision"},
            },
            {
                "id": "paper-2",
                "text": "Natural language processing with transformers",
                "metadata": {"title": "NLP Paper", "year": 2021, "field": "nlp"},
            },
            {
                "id": "paper-3",
                "text": "Reinforcement learning for robotics control",
                "metadata": {"title": "RL Paper", "year": 2019, "field": "reinforcement_learning"},
            },
        ]

        # Add to store
        console.print("\nAdding embeddings to store...")
        for paper in test_papers:
            embedding = generator.generate(paper["text"])
            store.add(
                id=paper["id"],
                embedding=embedding,
                metadata=paper["metadata"],
                document=paper["text"],
            )

        console.print(f"✓ Added {len(test_papers)} embeddings", style="green")
        console.print(f"  Store count: {store.count()}")

        # Test retrieval
        console.print("\nTesting retrieval by ID...")
        retrieved = store.get(ids=["paper-1"])
        console.print(f"✓ Retrieved 1 paper: {retrieved[0]['metadata']['title']}", style="green")

        # Test search
        console.print("\nTesting semantic search...")
        query_text = "computer vision and image recognition"
        query_embedding = generator.generate(query_text)

        results = store.search(query_embedding, top_k=3)

        console.print(f"✓ Search returned {len(results)} results", style="green")

        # Display results
        table = Table(title="Search Results")
        table.add_column("Rank", style="cyan")
        table.add_column("ID", style="yellow")
        table.add_column("Title", style="white")
        table.add_column("Score", style="green")

        for i, result in enumerate(results, 1):
            table.add_row(
                str(i),
                result["id"],
                result["metadata"]["title"],
                f"{result['score']:.4f}",
            )

        console.print(table)

        # Test filtered search
        console.print("\nTesting filtered search (year >= 2020)...")
        filtered_results = store.search(
            query_embedding,
            top_k=3,
            where={"year": {"$gte": 2020}},
        )

        console.print(f"✓ Filtered search returned {len(filtered_results)} results", style="green")
        for result in filtered_results:
            console.print(f"  - {result['metadata']['title']} ({result['metadata']['year']})")

        # Test update
        console.print("\nTesting update operation...")
        new_metadata = {"title": "CV Paper (Updated)", "year": 2020, "field": "computer_vision", "updated": True}
        store.update("paper-1", metadata=new_metadata)
        updated = store.get(ids=["paper-1"])
        console.print(f"✓ Updated metadata: {updated[0]['metadata']['title']}", style="green")

        # Test delete
        console.print("\nTesting delete operation...")
        store.delete(["paper-3"])
        console.print(f"✓ Deleted 1 paper. Store count: {store.count()}", style="green")

        # Get stats
        stats = store.get_stats()
        console.print("\nVector store stats:")
        for key, value in stats.items():
            console.print(f"  {key}: {value}")

        # Cleanup
        console.print("\nCleaning up test collection...")
        store.reset()

        return True

    except Exception as e:
        console.print(f"✗ Vector store test failed: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="dim red")
        return False


def test_end_to_end_pipeline():
    """Test the complete pipeline."""
    console.print("\n[bold cyan]═══ Testing End-to-End Pipeline ═══[/bold cyan]")

    try:
        from src.embeddings.generator import EmbeddingGenerator
        from src.embeddings.chunker import TextChunker
        from src.embeddings.vectorstore import VectorStore

        # Sample papers
        papers = [
            {
                "id": "e2e-paper-1",
                "title": "Attention Is All You Need",
                "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
                "full_text": "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms." * 50,
                "year": 2017,
                "authors": "Vaswani et al.",
            },
            {
                "id": "e2e-paper-2",
                "title": "BERT: Pre-training of Deep Bidirectional Transformers",
                "abstract": "We introduce a new language representation model called BERT.",
                "full_text": "BERT is designed to pre-train deep bidirectional representations from unlabeled text." * 50,
                "year": 2018,
                "authors": "Devlin et al.",
            },
        ]

        console.print(f"Processing {len(papers)} papers through full pipeline...")

        # Initialize components
        console.print("\n1. Initializing components...")
        generator = EmbeddingGenerator()
        chunker = TextChunker()
        store = VectorStore(collection_name="test_e2e")
        store.reset()  # Clean slate

        # Step 1: Chunk papers
        console.print("\n2. Chunking papers...")
        all_chunks = []
        for paper in papers:
            chunks = chunker.chunk_paper(paper, fields=["title", "abstract", "full_text"])
            all_chunks.extend(chunks)
            console.print(f"  - {paper['title']}: {len(chunks)} chunks")

        console.print(f"✓ Total chunks: {len(all_chunks)}", style="green")

        # Step 2: Generate embeddings
        console.print("\n3. Generating embeddings...")
        chunk_texts = [chunk.text for chunk in all_chunks]
        embeddings = generator.generate(chunk_texts, show_progress=True)

        console.print(f"✓ Generated {len(embeddings)} embeddings", style="green")

        # Step 3: Store in vector database
        console.print("\n4. Storing in vector database...")
        # Use global index to ensure unique IDs across all papers
        ids = [f"{chunk.metadata['paper_id']}_chunk_{i}" for i, chunk in enumerate(all_chunks)]
        metadatas = [chunk.metadata for chunk in all_chunks]
        documents = [chunk.text for chunk in all_chunks]

        store.add_batch(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

        console.print(f"✓ Stored {store.count()} chunks in vector store", style="green")

        # Step 4: Query the system
        console.print("\n5. Testing semantic search...")
        query = "transformer architecture and attention mechanisms"
        query_embedding = generator.generate(query)

        results = store.search(query_embedding, top_k=5)

        console.print(f"✓ Query: '{query}'", style="green")
        console.print(f"✓ Found {len(results)} relevant chunks:\n", style="green")

        for i, result in enumerate(results, 1):
            console.print(f"[bold cyan]{i}. Score: {result['score']:.4f}[/bold cyan]")
            console.print(f"   Paper: {result['metadata']['title']}")
            console.print(f"   Preview: {result['document'][:100]}...")
            console.print()

        # Cleanup
        console.print("Cleaning up...")
        store.reset()

        return True

    except Exception as e:
        console.print(f"✗ End-to-end pipeline test failed: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="dim red")
        return False


def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold yellow]Literature AI Infrastructure Test Suite[/bold yellow]",
        border_style="yellow"
    ))

    results = {}

    # Run tests
    results["Configuration"] = test_configuration()
    results["Embedding Generator"] = test_embedding_generator()
    results["Text Chunker"] = test_text_chunker()
    results["Vector Store"] = test_vector_store()
    results["End-to-End Pipeline"] = test_end_to_end_pipeline()

    # Summary
    console.print("\n" + "═" * 60)
    console.print("[bold cyan]Test Summary[/bold cyan]\n")

    table = Table()
    table.add_column("Test", style="cyan")
    table.add_column("Status", style="white")

    passed = 0
    failed = 0

    for test_name, result in results.items():
        if result:
            table.add_row(test_name, "[green]✓ PASSED[/green]")
            passed += 1
        else:
            table.add_row(test_name, "[red]✗ FAILED[/red]")
            failed += 1

    console.print(table)

    console.print(f"\n[bold]Total: {passed + failed} tests[/bold]")
    console.print(f"[green]Passed: {passed}[/green]")
    console.print(f"[red]Failed: {failed}[/red]")

    if failed == 0:
        console.print("\n[bold green]🎉 All tests passed![/bold green]")
        return 0
    else:
        console.print(f"\n[bold red]❌ {failed} test(s) failed[/bold red]")
        return 1


if __name__ == "__main__":
    exit(main())
