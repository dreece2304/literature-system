#!/usr/bin/env python3
"""
Acquire PDFs for papers in the database.

This script downloads PDFs from:
1. Open access sources (Unpaywall, Springer OA, Semantic Scholar, arXiv)
2. Institutional access via UW EZProxy (requires authentication)

Usage:
    python scripts/acquire_pdfs.py              # Open access only
    python scripts/acquire_pdfs.py --use-proxy  # Include UW institutional access
"""

import argparse
import asyncio
import hashlib
import http.cookiejar
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
from loguru import logger
from tqdm import tqdm

from config.settings import settings, DATA_DIR, LOGS_DIR
from src.services.external_search import ExternalSearchService

# PDF storage configuration
PDF_STORAGE_PATH = Path(os.getenv("PDF_STORAGE_PATH", str(DATA_DIR / "pdfs")))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))

# UW EZProxy configuration
UW_EZPROXY_PREFIX = "offcampus.lib.washington.edu"
UW_LOGIN_URL = "https://login.offcampus.lib.washington.edu/login"
COOKIE_FILE = DATA_DIR / ".uw_cookies.txt"


def get_ezproxy_url(url: str) -> str:
    """Convert a URL to use UW EZProxy for institutional access."""
    parsed = urlparse(url)
    # Insert EZProxy suffix into domain: doi.org -> doi.org.offcampus.lib.washington.edu
    proxied_host = f"{parsed.netloc}.{UW_EZPROXY_PREFIX}"
    return urlunparse(parsed._replace(netloc=proxied_host))


def load_cookies() -> dict:
    """Load saved cookies from file."""
    cookies = {}
    if COOKIE_FILE.exists():
        try:
            jar = http.cookiejar.MozillaCookieJar(str(COOKIE_FILE))
            jar.load(ignore_discard=True, ignore_expires=True)
            for cookie in jar:
                cookies[cookie.name] = cookie.value
            logger.info(f"Loaded {len(cookies)} cookies from {COOKIE_FILE}")
        except Exception as e:
            logger.warning(f"Could not load cookies: {e}")
    return cookies


def prompt_for_login(url: str) -> bool:
    """Open browser for UW login and prompt user to continue."""
    print("\n" + "=" * 60)
    print("UW AUTHENTICATION REQUIRED")
    print("=" * 60)
    print(f"\nOpening browser for UW login...")
    print(f"URL: {url}")
    print("\nAfter logging in:")
    print("1. The PDF should start downloading in your browser")
    print("2. Export cookies using a browser extension (e.g., 'cookies.txt')")
    print(f"3. Save to: {COOKIE_FILE}")
    print("\nOr press Enter to skip this paper, 'q' to quit proxy attempts")
    
    webbrowser.open(url)
    
    response = input("\nPress Enter after login, 'q' to disable proxy, or 's' to skip: ").strip().lower()
    if response == 'q':
        return False  # Disable proxy for rest of session
    return True  # Continue with proxy


async def fetch_papers_needing_pdfs(api_url: str) -> list:
    """Fetch papers that don't have PDFs yet."""
    base_url = api_url.rstrip('/')
    if not base_url.endswith('/api/v1'):
        base_url = f"{base_url}/api/v1"

    logger.info(f"Fetching papers from {base_url}")

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

    # Filter papers needing PDFs (no file_path and has DOI or arxiv_id)
    needs_pdf = []
    for paper in papers:
        file_path = paper.get('file_path')
        if not file_path:
            doi = paper.get('doi')
            arxiv_id = paper.get('arxiv_id')
            if doi or arxiv_id:
                needs_pdf.append(paper)

    return needs_pdf


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
    if 'authors' in current and current['authors']:
        if isinstance(current['authors'][0], dict):
            current['authors'] = [a.get('name', '') for a in current['authors'] if a.get('name')]

    if 'tags' in current and current['tags']:
        if isinstance(current['tags'][0], dict):
            current['tags'] = [t.get('name', '') for t in current['tags'] if t.get('name')]

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


async def find_pdf_url(service: ExternalSearchService, paper: dict) -> str | None:
    """Try to find a PDF URL for a paper using various sources."""
    doi = paper.get('doi')
    title = paper.get('title', '')
    arxiv_id = paper.get('arxiv_id')

    # Strategy 1: If we have a DOI, try Unpaywall first (most reliable for OA)
    if doi:
        logger.debug(f"Checking Unpaywall for DOI: {doi}")
        pdf_url = await service.find_pdf_url(doi)
        if pdf_url:
            logger.debug(f"Found PDF via Unpaywall: {pdf_url}")
            return pdf_url

    # Strategy 2: Try Springer Open Access
    if doi:
        logger.debug(f"Checking Springer OA for DOI: {doi}")
        pdf_url = await service.search_springer_openaccess_by_doi(doi)
        if pdf_url:
            logger.debug(f"Found PDF via Springer OA: {pdf_url}")
            return pdf_url

    # Strategy 3: Try Semantic Scholar (returns openAccessPdf)
    if title:
        logger.debug(f"Checking Semantic Scholar for title: {title[:50]}...")
        results = await service._search_semantic_scholar_query(title, limit=1)
        if results and results[0].pdf_url:
            # Verify title match
            if service._title_similarity(title, results[0].title) > 0.8:
                logger.debug(f"Found PDF via Semantic Scholar: {results[0].pdf_url}")
                return results[0].pdf_url

    # Strategy 4: arXiv papers have predictable PDF URLs
    if arxiv_id:
        # Clean arxiv_id (remove version if present for URL)
        clean_id = arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id
        pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
        logger.debug(f"Using arXiv PDF URL: {pdf_url}")
        return pdf_url

    return None


async def download_pdf(url: str, output_path: Path, cookies: dict = None) -> bool:
    """Download a PDF from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        headers=headers,
        cookies=cookies or {}
    ) as client:
        try:
            response = await client.get(url)

            if response.status_code == 401 or response.status_code == 403:
                logger.debug(f"Access denied (HTTP {response.status_code}) - may need authentication")
                return False

            if response.status_code != 200:
                logger.warning(f"Failed to download PDF: HTTP {response.status_code}")
                return False

            # Check content type
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
                # Check if it's a login page
                if "html" in content_type.lower():
                    logger.debug("Got HTML instead of PDF - likely needs authentication")
                    return False
                logger.warning(f"Not a PDF: {content_type}")
                return False

            # Check file size
            content = response.content
            size_mb = len(content) / (1024 * 1024)
            if size_mb > MAX_FILE_SIZE_MB:
                logger.warning(f"PDF too large: {size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB")
                return False

            # Verify it's actually a PDF
            if not content.startswith(b'%PDF'):
                logger.warning("Downloaded file is not a valid PDF")
                return False

            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            output_path.write_bytes(content)
            logger.debug(f"Downloaded {size_mb:.1f}MB to {output_path}")
            return True

        except httpx.TimeoutException:
            logger.warning(f"Timeout downloading PDF from {url}")
            return False
        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return False


def get_publisher_pdf_url(doi: str) -> str | None:
    """Get direct PDF URL from publisher using DOI."""
    # Common publisher patterns for PDF URLs
    publishers = {
        "10.1016": f"https://www.sciencedirect.com/science/article/pii/",  # Elsevier
        "10.1021": f"https://pubs.acs.org/doi/pdf/{doi}",  # ACS
        "10.1002": f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}",  # Wiley
        "10.1038": f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf",  # Nature
        "10.1039": f"https://pubs.rsc.org/en/content/articlepdf/{doi}",  # RSC
        "10.1063": f"https://pubs.aip.org/aip/jap/article-pdf/doi/{doi}",  # AIP
        "10.1103": f"https://journals.aps.org/prl/pdf/{doi}",  # APS
        "10.1007": f"https://link.springer.com/content/pdf/{doi}.pdf",  # Springer
    }
    
    for prefix, url_template in publishers.items():
        if doi.startswith(prefix):
            return url_template
    
    return None


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_text_from_pdf(file_path: Path) -> tuple[str, int]:
    """Extract text from PDF using pdfplumber.

    Returns (full_text, word_count).
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed, skipping text extraction")
        return "", 0

    full_text = []

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)

        combined = "\n\n".join(full_text)
        word_count = len(combined.split())

        return combined, word_count

    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return "", 0


def generate_filename(paper: dict) -> str:
    """Generate a unique filename for a paper's PDF."""
    paper_id = paper.get('id', 'unknown')
    doi = paper.get('doi', '')
    arxiv_id = paper.get('arxiv_id', '')

    # Create base name from DOI or arxiv_id
    if doi:
        # Convert DOI to filesystem-safe format
        base = doi.replace('/', '_').replace(':', '_')
    elif arxiv_id:
        base = f"arxiv_{arxiv_id}"
    else:
        base = f"paper_{paper_id}"

    return f"{base}.pdf"


async def process_paper(
    service: ExternalSearchService,
    api_url: str,
    paper: dict,
    use_proxy: bool = False,
    cookies: dict = None,
) -> dict:
    """Process a single paper: find PDF, download, extract text, update DB.

    Args:
        service: External search service
        api_url: Literature database API URL
        paper: Paper dict with id, doi, title, etc.
        use_proxy: Whether to try UW EZProxy for paywalled content
        cookies: Authentication cookies for proxy access

    Returns a result dict with status.
    """
    paper_id = paper['id']
    title = paper.get('title', 'Unknown')[:50]
    doi = paper.get('doi')

    result = {
        'paper_id': paper_id,
        'title': title,
        'status': 'skipped',
        'pdf_url': None,
        'file_path': None,
        'word_count': 0,
        'via_proxy': False,
    }

    # Generate filename and path
    filename = generate_filename(paper)
    file_path = PDF_STORAGE_PATH / filename

    # Skip if already exists
    if file_path.exists():
        logger.debug(f"PDF already exists: {file_path}")
        result['status'] = 'exists'
        result['file_path'] = str(file_path)
        return result

    # Strategy 1: Try open access sources first
    pdf_url = await find_pdf_url(service, paper)
    success = False
    
    if pdf_url:
        result['pdf_url'] = pdf_url
        success = await download_pdf(pdf_url, file_path, cookies)
    
    # Strategy 2: If no OA URL or download failed, try publisher via proxy
    if not success and use_proxy and doi:
        publisher_url = get_publisher_pdf_url(doi)
        if publisher_url:
            proxy_url = get_ezproxy_url(publisher_url)
            logger.debug(f"Trying EZProxy URL: {proxy_url}")
            result['pdf_url'] = proxy_url
            result['via_proxy'] = True
            success = await download_pdf(proxy_url, file_path, cookies)
            
            if not success:
                # Try direct DOI resolution through proxy
                doi_url = f"https://doi.org/{doi}"
                proxy_url = get_ezproxy_url(doi_url)
                success = await download_pdf(proxy_url, file_path, cookies)
    
    if not success:
        if not pdf_url and not (use_proxy and doi):
            result['status'] = 'skipped'
        else:
            result['status'] = 'download_failed'
        return result

    result['file_path'] = str(file_path)

    # Extract text
    full_text, word_count = extract_text_from_pdf(file_path)
    result['word_count'] = word_count

    # Compute file hash
    file_hash = compute_file_hash(file_path)

    # Update paper in database
    updates = {
        'file_path': str(file_path),
        'file_hash': file_hash,
        'word_count': word_count
    }

    if full_text:
        updates['full_text'] = full_text

    success = await update_paper(api_url, paper_id, updates)

    if success:
        result['status'] = 'success'
    else:
        result['status'] = 'update_failed'

    return result


async def main(use_proxy: bool = False):
    """Main PDF acquisition function."""
    logger.remove()
    logger.add(
        LOGS_DIR / "acquire_pdfs.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
    )

    logger.info("=" * 60)
    logger.info("PDF Acquisition Pipeline")
    logger.info("=" * 60)

    # Initialize services
    api_url = settings.litdb.api_url
    logger.info(f"Using API: {api_url}")
    logger.info(f"PDF storage: {PDF_STORAGE_PATH}")
    
    if use_proxy:
        logger.info(f"UW EZProxy: ENABLED")
        logger.info(f"Cookie file: {COOKIE_FILE}")
    else:
        logger.info("UW EZProxy: disabled (use --use-proxy to enable)")

    # Ensure storage directory exists
    PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

    # Load cookies if using proxy
    cookies = load_cookies() if use_proxy else {}

    service = ExternalSearchService()

    # Fetch papers needing PDFs
    logger.info("Fetching papers needing PDFs...")
    papers = await fetch_papers_needing_pdfs(api_url)
    logger.info(f"Found {len(papers)} papers needing PDFs")

    if not papers:
        logger.info("All papers have PDFs. Nothing to do!")
        return 0

    # Process papers
    stats = {
        'success': 0,
        'success_proxy': 0,
        'exists': 0,
        'download_failed': 0,
        'update_failed': 0,
        'skipped': 0
    }

    proxy_enabled = use_proxy

    with tqdm(total=len(papers), desc="Acquiring PDFs") as pbar:
        for paper in papers:
            try:
                result = await process_paper(
                    service, api_url, paper,
                    use_proxy=proxy_enabled,
                    cookies=cookies
                )
                
                if result['status'] == 'success':
                    if result.get('via_proxy'):
                        stats['success_proxy'] += 1
                    else:
                        stats['success'] += 1
                    logger.info(
                        f"Acquired: {result['title']}... "
                        f"({result['word_count']} words)"
                        f"{' [via proxy]' if result.get('via_proxy') else ''}"
                    )
                else:
                    stats[result['status']] += 1
                    if result['status'] == 'download_failed':
                        logger.debug(f"Download failed: {result['title']}...")

            except Exception as e:
                stats['skipped'] += 1
                logger.error(f"Error processing paper: {e}")

            pbar.update(1)
            display_stats = {k: v for k, v in stats.items() if v > 0}
            pbar.set_postfix(display_stats)

            # Small delay to be polite to servers
            await asyncio.sleep(0.5)

    # Summary
    logger.info("=" * 60)
    logger.info("PDF Acquisition Complete!")
    logger.info("=" * 60)
    logger.info(f"Total processed: {len(papers)}")
    logger.info(f"Successfully acquired (open access): {stats['success']}")
    if use_proxy:
        logger.info(f"Successfully acquired (via proxy): {stats['success_proxy']}")
    logger.info(f"Already existed: {stats['exists']}")
    logger.info(f"Download failed: {stats['download_failed']}")
    logger.info(f"Update failed: {stats['update_failed']}")
    logger.info(f"Skipped (no URL): {stats['skipped']}")
    logger.info("=" * 60)
    
    if stats['download_failed'] > 0 and use_proxy and not cookies:
        logger.info("\nTip: Some downloads failed. Try exporting browser cookies after logging in to UW.")
        logger.info(f"Save cookies to: {COOKIE_FILE}")

    return 0


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Acquire PDFs for papers in the literature database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/acquire_pdfs.py              # Open access only
    python scripts/acquire_pdfs.py --use-proxy  # Include UW institutional access

For UW access:
    1. Run with --use-proxy
    2. When prompted, log in to UW in your browser
    3. Export cookies using a browser extension
    4. Save to: data/.uw_cookies.txt
        """
    )
    parser.add_argument(
        "--use-proxy", "-p",
        action="store_true",
        help="Enable UW EZProxy for institutional access"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exit(asyncio.run(main(use_proxy=args.use_proxy)))
