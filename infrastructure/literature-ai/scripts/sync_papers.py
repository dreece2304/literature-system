#!/usr/bin/env python3
"""
Sync all papers from literature-database to literature-ai vector store.

This script fetches all papers from the literature-database API and
adds them to the ChromaDB vector store for citation suggestions.
"""

import asyncio

import httpx
from loguru import logger
from tqdm import tqdm

from config.settings import settings, LOGS_DIR
from src.embeddings.generator import get_embedding_generator
from src.embeddings.vectorstore import get_vector_store


async def fetch_all_papers(api_url: str) -> list:
    """Fetch all papers from literature-database API."""
    # Ensure we use the correct API prefix
    base_url = api_url.rstrip('/')
    if not base_url.endswith('/api/v1'):
        base_url = f"{base_url}/api/v1"

    logger.info(f"Fetching papers from {base_url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get total count first
        response = await client.get(f"{base_url}/papers", params={"limit": 1})
        response.raise_for_status()

        # Fetch all papers (paginated)
        seen_ids = set()
        all_papers = []
        offset = 0
        limit = 100
        total = None

        while True:
            response = await client.get(
                f"{base_url}/papers",
                params={"offset": offset, "limit": limit}
            )
            response.raise_for_status()
            data = response.json()

            # Handle paginated response format {total, items}
            if isinstance(data, dict) and 'items' in data:
                papers = data['items']
                total = data.get('total', total)
            else:
                papers = data

            if not papers:
                break

            # Deduplicate by paper ID
            new_papers = 0
            for paper in papers:
                paper_id = paper.get('id')
                if paper_id and paper_id not in seen_ids:
                    seen_ids.add(paper_id)
                    all_papers.append(paper)
                    new_papers += 1

            offset += limit

            logger.info(f"Fetched {len(all_papers)} / {total or '?'} papers (new: {new_papers})...")

            # Stop if no new papers (pagination wrapped around)
            if new_papers == 0:
                break

            # Stop if we've fetched all papers
            if total and len(all_papers) >= total:
                break

    return all_papers


def add_paper_to_vectorstore(generator, vectorstore, paper: dict) -> bool:
    """Add a single paper to the vector store."""
    try:
        # Extract paper data
        paper_id = str(paper['id'])
        title = paper.get('title', 'Unknown')
        abstract = paper.get('abstract', '')

        # Use abstract for embedding (full text is too long for single embedding)
        text = abstract if abstract else title

        if not text or len(text.strip()) < 10:
            return False

        # Build metadata - ChromaDB doesn't accept None values
        metadata = {
            'paper_id': paper_id,
            'title': title,
        }

        # Only add non-None values
        if paper.get('year') is not None:
            metadata['year'] = paper.get('year')
        if paper.get('doi'):
            metadata['doi'] = paper.get('doi')
        if paper.get('journal'):
            metadata['journal'] = paper.get('journal')

        # Extract authors
        authors = paper.get('authors', [])
        if authors:
            if isinstance(authors[0], dict):
                author_names = [a.get('name', '') for a in authors if a.get('name')]
            else:
                author_names = [a for a in authors if a]
            if author_names:
                metadata['authors'] = ', '.join(author_names)
            else:
                metadata['authors'] = 'Unknown'
        else:
            metadata['authors'] = 'Unknown'

        # Generate embedding
        embedding = generator.generate(text)

        # Add to vectorstore
        vectorstore.add(
            id=paper_id,
            embedding=embedding,
            metadata=metadata,
            document=text[:2000]  # Truncate document for storage
        )

        return True

    except Exception as e:
        logger.error(f"Failed to add paper {paper.get('id')}: {e}")
        return False


async def main():
    """Main sync function."""
    logger.remove()
    logger.add(
        LOGS_DIR / "sync_papers.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
    )

    logger.info("=" * 60)
    logger.info("Syncing Papers from literature-database to literature-ai")
    logger.info("=" * 60)

    # Initialize embedding generator and vectorstore
    logger.info("Initializing embedding generator...")
    generator = get_embedding_generator()
    logger.info(f"Loaded model: {generator.model_name}")

    logger.info("Initializing vectorstore...")
    vectorstore = get_vector_store()

    # Get current vector store count
    current_count = vectorstore.count()
    logger.info(f"Current papers in vector store: {current_count}")

    # Fetch all papers from database
    api_url = settings.litdb.api_url
    logger.info(f"Fetching papers from {api_url}...")

    try:
        papers = await fetch_all_papers(api_url)
        logger.info(f"Found {len(papers)} papers in literature-database")
    except Exception as e:
        logger.error(f"Failed to fetch papers: {e}")
        return 1

    if not papers:
        logger.warning("No papers found in database")
        return 0

    # Filter papers that have abstracts (for embedding)
    papers_with_abstract = [
        p for p in papers
        if p.get('abstract') and len(p.get('abstract', '').strip()) > 10
    ]

    logger.info(f"Papers with abstracts: {len(papers_with_abstract)}")
    logger.info(f"Papers without abstracts: {len(papers) - len(papers_with_abstract)}")

    # Add papers to vector store
    logger.info("Adding papers to vector store...")

    success_count = 0
    failed_count = 0

    with tqdm(total=len(papers_with_abstract), desc="Syncing papers") as pbar:
        for paper in papers_with_abstract:
            success = add_paper_to_vectorstore(generator, vectorstore, paper)

            if success:
                success_count += 1
            else:
                failed_count += 1

            pbar.update(1)
            pbar.set_postfix({
                'success': success_count,
                'failed': failed_count
            })

    # Final stats
    new_count = vectorstore.count()

    logger.info("=" * 60)
    logger.info("Sync Complete!")
    logger.info("=" * 60)
    logger.info(f"Papers processed: {len(papers_with_abstract)}")
    logger.info(f"Successfully added: {success_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Vector store before: {current_count}")
    logger.info(f"Vector store after: {new_count}")
    logger.info(f"Net increase: {new_count - current_count}")
    logger.info("=" * 60)

    logger.info("\nYou can now use citation suggestions with your full library!")
    logger.info("Try: curl -X POST http://localhost:8002/api/v1/writer/suggest-citations \\")
    logger.info('  -H "Content-Type: application/json" \\')
    logger.info('  -d \'{"text":"your text here","n":5}\'')

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
