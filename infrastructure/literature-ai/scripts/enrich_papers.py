#!/usr/bin/env python3
"""
Enrich papers missing metadata using external APIs.

This script fetches papers with missing abstracts from the literature-database
and enriches them using CrossRef, OpenAlex, and other APIs.
"""

import asyncio

import httpx
from loguru import logger
from tqdm import tqdm

from config.settings import settings, LOGS_DIR
from src.services.external_search import ExternalSearchService


async def fetch_papers_needing_enrichment(api_url: str) -> list:
    """Fetch papers that need metadata enrichment."""
    base_url = api_url.rstrip('/')
    if not base_url.endswith('/api/v1'):
        base_url = f"{base_url}/api/v1"

    logger.info(f"Fetching papers from {base_url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get all papers
        papers = []
        offset = 0
        limit = 100

        while True:
            response = await client.get(
                f"{base_url}/papers",
                params={"offset": offset, "limit": limit}
            )
            response.raise_for_status()
            data = response.json()

            items = data.get('items', data) if isinstance(data, dict) else data
            if not items:
                break

            papers.extend(items)
            offset += limit

            if isinstance(data, dict) and offset >= data.get('total', 0):
                break

    # Filter papers needing enrichment
    needs_enrichment = []
    for paper in papers:
        abstract = paper.get('abstract', '')
        if not abstract or len(abstract.strip()) < 20:
            needs_enrichment.append(paper)

    return needs_enrichment


async def enrich_paper_metadata(
    service: ExternalSearchService,
    paper: dict
) -> dict | None:
    """Try to enrich a paper's metadata using external APIs."""
    title = paper.get('title', '')
    doi = paper.get('doi')
    arxiv_id = paper.get('arxiv_id')
    _year = paper.get('year')  # noqa: F841 - reserved for future matching

    if not title:
        return None

    enriched = {}

    # Strategy 1: If we have a DOI, use CrossRef/OpenAlex/SemanticScholar directly
    if doi:
        logger.debug(f"Enriching via DOI: {doi}")

        # Try CrossRef
        results = await service._search_crossref_multi(f"doi:{doi}", limit=1)
        if results and results[0].abstract:
            enriched['abstract'] = results[0].abstract
            enriched['source'] = 'crossref'
            # Still try to get citation count from Semantic Scholar
            ss_results = await service._search_semantic_scholar_query(title, limit=1)
            if ss_results and ss_results[0].citation_count is not None:
                enriched['citation_count'] = ss_results[0].citation_count
            return enriched

        # Try OpenAlex
        results = await service._search_openalex(f"doi:{doi}", limit=1)
        if results and results[0].abstract:
            enriched['abstract'] = results[0].abstract
            enriched['source'] = 'openalex'
            # Try to get citation count from Semantic Scholar
            ss_results = await service._search_semantic_scholar_query(title, limit=1)
            if ss_results and ss_results[0].citation_count is not None:
                enriched['citation_count'] = ss_results[0].citation_count
            return enriched

        # Try Semantic Scholar
        results = await service._search_semantic_scholar_query(f"doi:{doi}", limit=1)
        if results and results[0].abstract:
            enriched['abstract'] = results[0].abstract
            enriched['source'] = 'semantic_scholar'
            if results[0].citation_count is not None:
                enriched['citation_count'] = results[0].citation_count
            if results[0].pdf_url:
                enriched['pdf_url'] = results[0].pdf_url
            return enriched

    # Strategy 2: Search by title
    logger.debug(f"Enriching via title search: {title[:50]}...")

    # Try OpenAlex (comprehensive)
    results = await service._search_openalex(title, limit=3)
    for result in results:
        if result.abstract and service._title_similarity(title, result.title) > 0.7:
            enriched['abstract'] = result.abstract
            if result.doi and not doi:
                enriched['doi'] = result.doi
            enriched['source'] = 'openalex'
            # Try to get citation count from Semantic Scholar
            ss_results = await service._search_semantic_scholar_query(title, limit=1)
            if ss_results and ss_results[0].citation_count is not None:
                enriched['citation_count'] = ss_results[0].citation_count
            return enriched

    # Try CrossRef
    results = await service._search_crossref_multi(title, limit=3)
    for result in results:
        if result.abstract and result.confidence > 0.7:
            enriched['abstract'] = result.abstract
            if result.doi and not doi:
                enriched['doi'] = result.doi
            enriched['source'] = 'crossref'
            # Try to get citation count from Semantic Scholar
            ss_results = await service._search_semantic_scholar_query(title, limit=1)
            if ss_results and ss_results[0].citation_count is not None:
                enriched['citation_count'] = ss_results[0].citation_count
            return enriched

    # Try Semantic Scholar by title
    results = await service._search_semantic_scholar_query(title, limit=3)
    for result in results:
        if result.abstract and service._title_similarity(title, result.title) > 0.7:
            enriched['abstract'] = result.abstract
            if result.doi and not doi:
                enriched['doi'] = result.doi
            if result.citation_count is not None:
                enriched['citation_count'] = result.citation_count
            if result.pdf_url:
                enriched['pdf_url'] = result.pdf_url
            enriched['source'] = 'semantic_scholar'
            return enriched

    # Strategy 3: If arXiv paper, try arXiv API
    if arxiv_id:
        logger.debug(f"Enriching via arXiv: {arxiv_id}")
        results = await service._search_arxiv(f"id:{arxiv_id}", limit=1)
        if results and results[0].abstract:
            enriched['abstract'] = results[0].abstract
            enriched['source'] = 'arxiv'
            # Try to get citation count from Semantic Scholar
            ss_results = await service._search_semantic_scholar_query(title, limit=1)
            if ss_results and ss_results[0].citation_count is not None:
                enriched['citation_count'] = ss_results[0].citation_count
            return enriched

    return None


async def get_paper(api_url: str, paper_id: int) -> dict | None:
    """Fetch a paper by ID."""
    base_url = api_url.rstrip('/')
    if not base_url.endswith('/api/v1'):
        base_url = f"{base_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{base_url}/papers/{paper_id}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch paper {paper_id}: {e}")
    return None


async def update_paper(api_url: str, paper_id: int, updates: dict) -> bool:
    """Update a paper via the API (using PUT)."""
    base_url = api_url.rstrip('/')
    if not base_url.endswith('/api/v1'):
        base_url = f"{base_url}/api/v1"

    # Fetch current paper
    current = await get_paper(api_url, paper_id)
    if not current:
        logger.error(f"Could not fetch paper {paper_id} for update")
        return False

    # Merge updates
    for key, value in updates.items():
        current[key] = value

    # Convert nested objects to format expected by API
    # Authors: list of objects -> list of strings
    if 'authors' in current and current['authors']:
        if isinstance(current['authors'][0], dict):
            current['authors'] = [a.get('name', '') for a in current['authors'] if a.get('name')]

    # Tags: list of objects -> list of strings
    if 'tags' in current and current['tags']:
        if isinstance(current['tags'][0], dict):
            current['tags'] = [t.get('name', '') for t in current['tags'] if t.get('name')]

    # Collections: remove (not typically updated via this endpoint)
    current.pop('collections', None)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.put(
                f"{base_url}/papers/{paper_id}",
                json=current
            )
            if response.status_code in (200, 204):
                return True
            else:
                logger.error(f"API returned {response.status_code}: {response.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Failed to update paper {paper_id}: {e}")
            return False


async def main():
    """Main enrichment function."""
    logger.remove()
    logger.add(
        LOGS_DIR / "enrich_papers.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
    )

    logger.info("=" * 60)
    logger.info("Paper Metadata Enrichment")
    logger.info("=" * 60)

    # Initialize services
    api_url = settings.litdb.api_url
    logger.info(f"Using API: {api_url}")

    service = ExternalSearchService()

    # Fetch papers needing enrichment
    logger.info("Fetching papers needing enrichment...")
    papers = await fetch_papers_needing_enrichment(api_url)
    logger.info(f"Found {len(papers)} papers needing enrichment")

    if not papers:
        logger.info("All papers have metadata. Nothing to do!")
        return 0

    # Enrich papers
    enriched_count = 0
    failed_count = 0
    skipped_count = 0

    with tqdm(total=len(papers), desc="Enriching papers") as pbar:
        for paper in papers:
            paper_id = paper['id']
            title = paper.get('title', 'Unknown')[:50]

            try:
                enriched = await enrich_paper_metadata(service, paper)

                if enriched:
                    # Update paper via API
                    updates = {'abstract': enriched['abstract']}
                    if 'doi' in enriched:
                        updates['doi'] = enriched['doi']
                    if 'citation_count' in enriched:
                        updates['citation_count'] = enriched['citation_count']
                    if 'pdf_url' in enriched:
                        updates['pdf_url'] = enriched['pdf_url']

                    success = await update_paper(api_url, paper_id, updates)

                    extras = []
                    if 'citation_count' in enriched:
                        extras.append(f"citations: {enriched['citation_count']}")
                    if 'pdf_url' in enriched:
                        extras.append("PDF found")
                    extra_str = f" [{', '.join(extras)}]" if extras else ""

                    if success:
                        enriched_count += 1
                        logger.info(
                            f"Enriched: {title}... (source: {enriched['source']}){extra_str}"
                        )
                    else:
                        failed_count += 1
                        logger.warning(f"Failed to update: {title}...")
                else:
                    skipped_count += 1
                    logger.debug(f"No metadata found: {title}...")

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing {title}...: {e}")

            pbar.update(1)
            pbar.set_postfix({
                'enriched': enriched_count,
                'failed': failed_count,
                'skipped': skipped_count
            })

    # Summary
    logger.info("=" * 60)
    logger.info("Enrichment Complete!")
    logger.info("=" * 60)
    logger.info(f"Total processed: {len(papers)}")
    logger.info(f"Successfully enriched: {enriched_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"No metadata found: {skipped_count}")
    logger.info("=" * 60)

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
