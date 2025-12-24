"""
Celery tasks for embedding generation.

Background tasks for processing papers and generating embeddings.
"""

from typing import Dict, Any, List
from loguru import logger

from src.tasks.celery_app import app
from src.embeddings.generator import get_embedding_generator
from src.embeddings.chunker import get_text_chunker
from src.embeddings.vectorstore import get_vectorstore


@app.task(name="src.tasks.embedding_tasks.generate_paper_embeddings", bind=True)
def generate_paper_embeddings(self, paper_id: str, paper_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate embeddings for a single paper (async task).

    Args:
        paper_id: Paper identifier
        paper_data: Paper metadata and content

    Returns:
        Task result with status and metrics
    """
    logger.info(f"[Task {self.request.id}] Generating embeddings for paper: {paper_id}")

    try:
        # Get services
        generator = get_embedding_generator()
        chunker = get_text_chunker()
        vectorstore = get_vectorstore()

        # Chunk the paper
        chunks = chunker.chunk_paper(
            paper_data=paper_data,
            fields=["title", "abstract", "full_text"],
        )

        if not chunks:
            logger.warning(f"No chunks generated for paper: {paper_id}")
            return {
                "paper_id": paper_id,
                "status": "skipped",
                "reason": "No content to embed",
                "chunks_created": 0,
            }

        # Generate embeddings
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = generator.generate(chunk_texts, show_progress=False)

        # Prepare for storage
        ids = [f"{paper_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [chunk.metadata for chunk in chunks]

        # Store in vector database
        vectorstore.add_batch(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(f"[Task {self.request.id}] ✅ Embedded paper {paper_id}: {len(chunks)} chunks")

        return {
            "paper_id": paper_id,
            "status": "success",
            "chunks_created": len(chunks),
            "embedding_dimension": generator.dimension,
        }

    except Exception as e:
        logger.error(f"[Task {self.request.id}] Failed to embed paper {paper_id}: {e}")
        return {
            "paper_id": paper_id,
            "status": "failed",
            "error": str(e),
        }


@app.task(name="src.tasks.embedding_tasks.batch_generate_embeddings", bind=True)
def batch_generate_embeddings(self, paper_ids: List[str], paper_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate embeddings for multiple papers in batch.

    Args:
        paper_ids: List of paper identifiers
        paper_data_list: List of paper metadata and content

    Returns:
        Batch result with summary statistics
    """
    logger.info(f"[Task {self.request.id}] Batch embedding {len(paper_ids)} papers")

    results = []
    for paper_id, paper_data in zip(paper_ids, paper_data_list):
        result = generate_paper_embeddings.apply(args=(paper_id, paper_data)).get()
        results.append(result)

    # Summarize results
    successful = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    total_chunks = sum(r.get("chunks_created", 0) for r in results)

    summary = {
        "total_papers": len(paper_ids),
        "successful": successful,
        "failed": failed,
        "total_chunks_created": total_chunks,
        "results": results,
    }

    logger.info(f"[Task {self.request.id}] Batch complete: {successful}/{len(paper_ids)} successful")

    return summary


@app.task(name="src.tasks.embedding_tasks.update_paper_embeddings", bind=True)
def update_paper_embeddings(self, paper_id: str, paper_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update embeddings for a paper (delete old, create new).

    Args:
        paper_id: Paper identifier
        paper_data: Updated paper metadata and content

    Returns:
        Update result
    """
    logger.info(f"[Task {self.request.id}] Updating embeddings for paper: {paper_id}")

    try:
        vectorstore = get_vectorstore()

        # Delete old embeddings
        vectorstore.delete(where={"paper_id": paper_id})

        # Generate new embeddings
        result = generate_paper_embeddings.apply(args=(paper_id, paper_data)).get()

        logger.info(f"[Task {self.request.id}] ✅ Updated embeddings for paper {paper_id}")

        return {
            **result,
            "operation": "update",
        }

    except Exception as e:
        logger.error(f"[Task {self.request.id}] Failed to update paper {paper_id}: {e}")
        return {
            "paper_id": paper_id,
            "status": "failed",
            "operation": "update",
            "error": str(e),
        }


@app.task(name="src.tasks.embedding_tasks.delete_paper_embeddings", bind=True)
def delete_paper_embeddings(self, paper_id: str) -> Dict[str, Any]:
    """
    Delete embeddings for a paper.

    Args:
        paper_id: Paper identifier

    Returns:
        Deletion result
    """
    logger.info(f"[Task {self.request.id}] Deleting embeddings for paper: {paper_id}")

    try:
        vectorstore = get_vectorstore()

        # Delete all chunks for this paper
        vectorstore.delete(where={"paper_id": paper_id})

        logger.info(f"[Task {self.request.id}] ✅ Deleted embeddings for paper {paper_id}")

        return {
            "paper_id": paper_id,
            "status": "deleted",
        }

    except Exception as e:
        logger.error(f"[Task {self.request.id}] Failed to delete paper {paper_id}: {e}")
        return {
            "paper_id": paper_id,
            "status": "failed",
            "error": str(e),
        }


@app.task(name="src.tasks.embedding_tasks.rebuild_vectorstore", bind=True)
def rebuild_vectorstore(self) -> Dict[str, Any]:
    """
    Rebuild the entire vector store (nuclear option).

    Warning: This will delete all existing embeddings.

    Returns:
        Rebuild result
    """
    logger.warning(f"[Task {self.request.id}] Rebuilding vector store (this will delete all data)")

    try:
        vectorstore = get_vectorstore()

        # Get count before deletion
        stats_before = vectorstore.get_stats()
        count_before = stats_before.get("count", 0)

        # Delete collection and recreate
        vectorstore.collection.delete()
        vectorstore._get_or_create_collection()

        stats_after = vectorstore.get_stats()

        logger.info(f"[Task {self.request.id}] ✅ Vector store rebuilt")

        return {
            "status": "rebuilt",
            "count_before": count_before,
            "count_after": stats_after.get("count", 0),
        }

    except Exception as e:
        logger.error(f"[Task {self.request.id}] Failed to rebuild vector store: {e}")
        return {
            "status": "failed",
            "error": str(e),
        }
