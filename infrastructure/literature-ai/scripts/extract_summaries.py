#!/usr/bin/env python3
"""
Extract AI-generated summaries and key details from papers.

This script uses the local Ollama/Qwen models to analyze papers and extract:
- Research questions and objectives
- Methodology
- Key findings
- Contributions
- Limitations
- Domain-specific structured data

Usage:
    python scripts/extract_summaries.py              # Process all papers with full text
    python scripts/extract_summaries.py --limit 10   # Process only 10 papers
    python scripts/extract_summaries.py --paper-id 5 # Process specific paper
"""

import argparse
import asyncio
import json

import httpx
from loguru import logger
from tqdm import tqdm

from config.settings import settings, LOGS_DIR, DATA_DIR
from src.agents.extractor import ExtractorAgent


# Storage for extracted summaries
SUMMARIES_FILE = DATA_DIR / "extracted_summaries.json"


async def fetch_all_papers(api_url: str) -> list:
    """Fetch all papers from the API."""
    base_url = api_url.rstrip('/')
    if not base_url.endswith('/api/v1'):
        base_url = f"{base_url}/api/v1"

    async with httpx.AsyncClient(timeout=30.0) as client:
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

    return papers


async def get_papers_for_extraction(api_url: str, limit: int = None, paper_id: int = None) -> list:
    """Get papers that have full text and need extraction."""
    papers = await fetch_all_papers(api_url)

    # Filter to papers with full text (word_count > 100)
    papers_with_text = [
        p for p in papers
        if p.get('word_count') and p['word_count'] > 100
    ]

    if paper_id:
        papers_with_text = [p for p in papers_with_text if p['id'] == paper_id]

    if limit:
        papers_with_text = papers_with_text[:limit]

    return papers_with_text


def load_existing_summaries() -> dict:
    """Load previously extracted summaries."""
    if SUMMARIES_FILE.exists():
        try:
            with open(SUMMARIES_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load existing summaries: {e}")
    return {}


def save_summaries(summaries: dict):
    """Save extracted summaries to file."""
    SUMMARIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARIES_FILE, 'w') as f:
        json.dump(summaries, f, indent=2, default=str)


async def extract_paper_summary(extractor: ExtractorAgent, paper: dict) -> dict:
    """Extract summary and key details from a paper using AI."""
    paper_id = paper['id']
    
    try:
        # Use the extractor agent for comprehensive extraction
        result = await extractor.extract_comprehensive(paper_id)
        
        if result.success:
            return {
                'paper_id': paper_id,
                'title': paper.get('title', ''),
                'success': True,
                'extraction': result.content,
                'duration_ms': result.duration_ms,
            }
        else:
            return {
                'paper_id': paper_id,
                'title': paper.get('title', ''),
                'success': False,
                'error': result.error,
            }
    
    except Exception as e:
        logger.error(f"Extraction failed for paper {paper_id}: {e}")
        return {
            'paper_id': paper_id,
            'title': paper.get('title', ''),
            'success': False,
            'error': str(e),
        }


async def main(limit: int = None, paper_id: int = None, force: bool = False):
    """Main extraction function."""
    logger.remove()
    logger.add(
        LOGS_DIR / "extract_summaries.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
    )

    logger.info("=" * 60)
    logger.info("AI Paper Summary Extraction")
    logger.info("=" * 60)
    logger.info(f"Using Ollama at: {settings.ollama.host}")
    logger.info(f"Reader model: {settings.ollama.reader_model}")

    # Initialize services
    api_url = settings.litdb.api_url
    logger.info(f"Using API: {api_url}")
    extractor = ExtractorAgent()

    # Load existing summaries
    summaries = load_existing_summaries() if not force else {}
    logger.info(f"Loaded {len(summaries)} existing summaries")

    # Get papers to process
    logger.info("Fetching papers with full text...")
    papers = await get_papers_for_extraction(api_url, limit=limit, paper_id=paper_id)
    logger.info(f"Found {len(papers)} papers with full text")

    if not papers:
        logger.info("No papers to process!")
        return 0

    # Filter out already processed papers
    if not force:
        papers = [p for p in papers if str(p['id']) not in summaries]
        logger.info(f"Papers needing extraction: {len(papers)}")

    if not papers:
        logger.info("All papers already processed! Use --force to re-extract.")
        return 0

    # Process papers
    stats = {'success': 0, 'failed': 0}
    
    with tqdm(total=len(papers), desc="Extracting summaries") as pbar:
        for paper in papers:
            title = paper.get('title', 'Unknown')[:50]
            
            try:
                result = await extract_paper_summary(extractor, paper)
                
                if result['success']:
                    stats['success'] += 1
                    summaries[str(paper['id'])] = result
                    logger.info(f"Extracted: {title}...")
                    
                    # Save after each successful extraction
                    save_summaries(summaries)
                else:
                    stats['failed'] += 1
                    logger.warning(f"Failed: {title}... - {result.get('error', 'Unknown error')}")

            except Exception as e:
                stats['failed'] += 1
                logger.error(f"Error processing {title}...: {e}")

            pbar.update(1)
            pbar.set_postfix(stats)

    # Final save
    save_summaries(summaries)

    # Summary
    logger.info("=" * 60)
    logger.info("Extraction Complete!")
    logger.info("=" * 60)
    logger.info(f"Total processed: {len(papers)}")
    logger.info(f"Successfully extracted: {stats['success']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Summaries saved to: {SUMMARIES_FILE}")
    logger.info("=" * 60)

    return 0 if stats['failed'] == 0 else 1


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract AI-generated summaries from papers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Maximum number of papers to process"
    )
    parser.add_argument(
        "--paper-id", "-p",
        type=int,
        default=None,
        help="Process only this specific paper ID"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-extract summaries even if they exist"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exit(asyncio.run(main(
        limit=args.limit,
        paper_id=args.paper_id,
        force=args.force
    )))
