"""
External search service for finding papers via academic APIs.

Supports:
- CrossRef: DOI lookup by title/author (best for DOI resolution)
- Semantic Scholar: Paper search and metadata (good for CS/ML papers)
- OpenAlex: Open access paper search (comprehensive, free)
- Unpaywall: Find open access PDFs
- arXiv: Preprints in physics, CS, math
- PubMed: Biomedical literature
- Springer: Nature/Springer publications

Rate Limits (built-in):
- CrossRef: No strict limit with polite email header
- Semantic Scholar: 1 req/sec with API key
- OpenAlex: 10 req/sec with email header
- arXiv: ~1 req/3 sec recommended
- PubMed: 3 req/sec without API key
"""
import os
import re
import time
import asyncio
import httpx
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


# Rate limit settings (seconds between requests per API)
RATE_LIMITS = {
    "crossref": 0.2,       # 5 req/sec max, be polite
    "semantic_scholar": 1.1,  # 1 req/sec strict
    "openalex": 0.15,      # 10 req/sec with email
    "arxiv": 3.5,          # 1 req/3 sec recommended
    "pubmed": 0.4,         # 3 req/sec without key
    "unpaywall": 0.5,      # Conservative
}


@dataclass
class PaperResult:
    """Result from external paper search."""
    title: str
    authors: List[str]
    year: Optional[int]
    doi: Optional[str]
    journal: Optional[str]
    abstract: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    source: str = "unknown"
    confidence: float = 0.0
    citation_count: Optional[int] = None
    arxiv_id: Optional[str] = None


class RateLimiter:
    """Simple rate limiter that tracks last request time per API."""

    def __init__(self):
        self._last_request: Dict[str, float] = {}

    async def wait(self, api_name: str):
        """Wait if needed to respect rate limit for the given API."""
        if api_name not in RATE_LIMITS:
            return

        min_interval = RATE_LIMITS[api_name]
        last_time = self._last_request.get(api_name, 0)
        elapsed = time.time() - last_time

        if elapsed < min_interval:
            wait_time = min_interval - elapsed
            await asyncio.sleep(wait_time)

        self._last_request[api_name] = time.time()


class ExternalSearchService:
    """Service for searching external academic databases."""

    def __init__(self):
        self.crossref_email = os.getenv("CROSSREF_MAILTO", os.getenv("UNPAYWALL_EMAIL"))
        self.semantic_scholar_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self.unpaywall_email = os.getenv("UNPAYWALL_EMAIL")
        self.openalex_email = os.getenv("OPENALEX_EMAIL")
        self.pubmed_email = os.getenv("PUBMED_EMAIL")
        self.pubmed_tool = os.getenv("PUBMED_TOOL", "literature-ai")
        self.springer_key = os.getenv("SPRINGER_API_KEY")
        self.arxiv_enabled = os.getenv("ENABLE_ARXIV", "true").lower() == "true"
        self._rate_limiter = RateLimiter()

    async def find_doi_by_title(self, title: str, author: Optional[str] = None,
                                 year: Optional[int] = None) -> Optional[PaperResult]:
        """Find DOI for a paper by title, optionally filtering by author/year."""
        # Try CrossRef first (most reliable for DOIs)
        result = await self._search_crossref(title, author, year)
        if result and result.confidence > 0.8:
            return result

        # Fall back to Semantic Scholar
        result = await self._search_semantic_scholar(title, author, year)
        if result and result.confidence > 0.8:
            return result

        return result  # Return best match even if low confidence

    async def search_all_sources(self, query: str, limit: int = 5) -> Dict[str, List[PaperResult]]:
        """Search ALL available sources and return results grouped by source."""
        results = {}

        # CrossRef
        cr_results = await self._search_crossref_multi(query, limit)
        if cr_results:
            results['crossref'] = cr_results

        # Semantic Scholar
        ss_results = await self._search_semantic_scholar_query(query, limit)
        if ss_results:
            results['semantic_scholar'] = ss_results

        # OpenAlex
        oa_results = await self._search_openalex(query, limit)
        if oa_results:
            results['openalex'] = oa_results

        # arXiv (if enabled)
        if self.arxiv_enabled:
            arxiv_results = await self._search_arxiv(query, limit)
            if arxiv_results:
                results['arxiv'] = arxiv_results

        # PubMed
        pubmed_results = await self._search_pubmed(query, limit)
        if pubmed_results:
            results['pubmed'] = pubmed_results

        # Springer/Nature
        springer_results = await self._search_springer(query, limit)
        if springer_results:
            results['springer'] = springer_results

        return results

    async def search_papers(self, query: str, limit: int = 10) -> List[PaperResult]:
        """Search for papers matching a query (aggregated from all sources)."""
        all_results = await self.search_all_sources(query, limit)

        # Flatten and deduplicate by DOI
        seen_dois = set()
        results = []
        for source_results in all_results.values():
            for r in source_results:
                if r.doi and r.doi in seen_dois:
                    continue
                if r.doi:
                    seen_dois.add(r.doi)
                results.append(r)

        return results[:limit]

    async def find_pdf_url(self, doi: str) -> Optional[str]:
        """Find open access PDF URL for a DOI using Unpaywall."""
        if not self.unpaywall_email:
            return None

        # Rate limit
        await self._rate_limiter.wait("unpaywall")

        url = f"https://api.unpaywall.org/v2/{doi}?email={self.unpaywall_email}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("best_oa_location"):
                        return data["best_oa_location"].get("url_for_pdf")
                    for loc in data.get("oa_locations", []):
                        if loc.get("url_for_pdf"):
                            return loc["url_for_pdf"]
            except Exception as e:
                print(f"Unpaywall error: {e}")
        return None

    # ==================== CrossRef ====================
    async def _search_crossref(self, title: str, author: Optional[str] = None,
                                year: Optional[int] = None) -> Optional[PaperResult]:
        """Search CrossRef for a paper by title."""
        results = await self._search_crossref_multi(title, 5, author, year)
        if results:
            return results[0]
        return None

    async def _search_crossref_multi(self, query: str, limit: int = 5,
                                      author: Optional[str] = None,
                                      year: Optional[int] = None) -> List[PaperResult]:
        """Search CrossRef returning multiple results."""
        # Rate limit
        await self._rate_limiter.wait("crossref")

        base_url = "https://api.crossref.org/works"

        params = {
            "query": query,
            "rows": limit,
            "select": "DOI,title,author,published-print,published-online,container-title,abstract,is-referenced-by-count"
        }
        if author:
            first_author = author.split(" and ")[0].split(",")[0].strip()
            params["query.author"] = first_author

        headers = {}
        if self.crossref_email:
            headers["User-Agent"] = f"LiteratureAI/1.0 (mailto:{self.crossref_email})"

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(base_url, params=params, headers=headers)
                if response.status_code != 200:
                    return results

                data = response.json()
                items = data.get("message", {}).get("items", [])

                for item in items:
                    item_title = item.get("title", [""])[0] if item.get("title") else ""
                    score = self._title_similarity(query, item_title)

                    item_year = None
                    if item.get("published-print"):
                        item_year = item["published-print"].get("date-parts", [[None]])[0][0]
                    elif item.get("published-online"):
                        item_year = item["published-online"].get("date-parts", [[None]])[0][0]

                    if year and item_year and year == item_year:
                        score += 0.1

                    authors = []
                    for auth in item.get("author", []):
                        name = f"{auth.get('given', '')} {auth.get('family', '')}".strip()
                        if name:
                            authors.append(name)

                    results.append(PaperResult(
                        title=item_title,
                        authors=authors,
                        year=item_year,
                        doi=item.get("DOI"),
                        journal=item.get("container-title", [""])[0] if item.get("container-title") else None,
                        abstract=item.get("abstract"),
                        source="crossref",
                        confidence=score,
                        citation_count=item.get("is-referenced-by-count")
                    ))

            except Exception as e:
                print(f"CrossRef error: {e}")

        # Sort by confidence
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results

    # ==================== Semantic Scholar ====================
    async def _search_semantic_scholar(self, title: str, author: Optional[str] = None,
                                        year: Optional[int] = None) -> Optional[PaperResult]:
        """Search Semantic Scholar for a paper by title."""
        results = await self._search_semantic_scholar_query(title, 5)
        if not results:
            return None

        # Find best match
        best = None
        best_score = 0.0
        for r in results:
            score = self._title_similarity(title, r.title)
            if year and r.year == year:
                score += 0.1
            if score > best_score:
                best_score = score
                best = r
                best.confidence = score
        return best

    async def _search_semantic_scholar_query(self, query: str, limit: int = 10) -> List[PaperResult]:
        """General search on Semantic Scholar."""
        # Rate limit - strict 1 req/sec
        await self._rate_limiter.wait("semantic_scholar")

        base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

        params = {
            "query": query,
            "limit": limit,
            "fields": "title,authors,year,externalIds,venue,abstract,openAccessPdf,citationCount"
        }

        headers = {}
        if self.semantic_scholar_key:
            headers["x-api-key"] = self.semantic_scholar_key

        results = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(base_url, params=params, headers=headers)
                if response.status_code != 200:
                    print(f"Semantic Scholar returned {response.status_code}")
                    return results

                data = response.json()

                for paper in data.get("data", []):
                    authors = [a.get("name", "") for a in paper.get("authors", [])]
                    doi = paper.get("externalIds", {}).get("DOI")
                    arxiv_id = paper.get("externalIds", {}).get("ArXiv")
                    pdf_url = None
                    if paper.get("openAccessPdf"):
                        pdf_url = paper["openAccessPdf"].get("url")

                    results.append(PaperResult(
                        title=paper.get("title", ""),
                        authors=authors,
                        year=paper.get("year"),
                        doi=doi,
                        journal=paper.get("venue"),
                        abstract=paper.get("abstract"),
                        pdf_url=pdf_url,
                        source="semantic_scholar",
                        confidence=1.0,
                        citation_count=paper.get("citationCount"),
                        arxiv_id=arxiv_id
                    ))

            except Exception as e:
                print(f"Semantic Scholar query error: {e}")

        return results

    # ==================== OpenAlex ====================
    async def _search_openalex(self, query: str, limit: int = 10) -> List[PaperResult]:
        """Search OpenAlex for papers."""
        # Rate limit
        await self._rate_limiter.wait("openalex")

        base_url = "https://api.openalex.org/works"

        params = {
            "search": query,
            "per_page": limit,
            "select": "id,doi,title,authorships,publication_year,primary_location,abstract_inverted_index,cited_by_count,open_access"
        }

        headers = {}
        if self.openalex_email:
            headers["User-Agent"] = f"mailto:{self.openalex_email}"

        results = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(base_url, params=params, headers=headers)
                if response.status_code != 200:
                    print(f"OpenAlex returned {response.status_code}")
                    return results

                data = response.json()

                for work in data.get("results", []):
                    # Extract authors
                    authors = []
                    for authorship in work.get("authorships", []):
                        author_name = authorship.get("author", {}).get("display_name")
                        if author_name:
                            authors.append(author_name)

                    # Extract journal
                    journal = None
                    primary_loc = work.get("primary_location", {})
                    if primary_loc and primary_loc.get("source"):
                        journal = primary_loc["source"].get("display_name")

                    # Extract DOI (remove https://doi.org/ prefix)
                    doi = work.get("doi")
                    if doi and doi.startswith("https://doi.org/"):
                        doi = doi[16:]

                    # Reconstruct abstract from inverted index
                    abstract = None
                    if work.get("abstract_inverted_index"):
                        try:
                            inv_idx = work["abstract_inverted_index"]
                            # Build word positions
                            positions = []
                            for word, pos_list in inv_idx.items():
                                for pos in pos_list:
                                    positions.append((pos, word))
                            positions.sort()
                            abstract = " ".join(word for _, word in positions)
                        except (KeyError, TypeError):
                            pass

                    # Get PDF URL
                    pdf_url = None
                    oa = work.get("open_access", {})
                    if oa.get("oa_url"):
                        pdf_url = oa["oa_url"]

                    results.append(PaperResult(
                        title=work.get("title", ""),
                        authors=authors,
                        year=work.get("publication_year"),
                        doi=doi,
                        journal=journal,
                        abstract=abstract,
                        pdf_url=pdf_url,
                        source="openalex",
                        confidence=1.0,
                        citation_count=work.get("cited_by_count")
                    ))

            except Exception as e:
                print(f"OpenAlex error: {e}")

        return results

    # ==================== arXiv ====================
    async def _search_arxiv(self, query: str, limit: int = 10) -> List[PaperResult]:
        """Search arXiv for preprints."""
        # Rate limit - arXiv requests ~3 sec between requests
        await self._rate_limiter.wait("arxiv")

        base_url = "https://export.arxiv.org/api/query"

        # Clean query for arXiv
        clean_query = query.replace(":", " ").replace("(", " ").replace(")", " ")

        params = {
            "search_query": f"all:{clean_query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance"
        }

        results = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(base_url, params=params)
                if response.status_code != 200:
                    print(f"arXiv returned {response.status_code}")
                    return results

                # Parse XML response
                root = ET.fromstring(response.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}

                for entry in root.findall("atom:entry", ns):
                    title = entry.find("atom:title", ns)
                    title_text = title.text.strip().replace("\n", " ") if title is not None else ""

                    # Get authors
                    authors = []
                    for author in entry.findall("atom:author", ns):
                        name = author.find("atom:name", ns)
                        if name is not None:
                            authors.append(name.text)

                    # Get abstract
                    summary = entry.find("atom:summary", ns)
                    abstract = summary.text.strip() if summary is not None else None

                    # Get year from published date
                    published = entry.find("atom:published", ns)
                    year = None
                    if published is not None and published.text:
                        year = int(published.text[:4])

                    # Get arxiv ID
                    arxiv_id_elem = entry.find("atom:id", ns)
                    arxiv_id = None
                    if arxiv_id_elem is not None:
                        # Extract ID from URL like http://arxiv.org/abs/2301.12345v1
                        arxiv_url = arxiv_id_elem.text
                        if "/abs/" in arxiv_url:
                            arxiv_id = arxiv_url.split("/abs/")[-1]

                    # Get PDF link
                    pdf_url = None
                    for link in entry.findall("atom:link", ns):
                        if link.get("title") == "pdf":
                            pdf_url = link.get("href")
                            break

                    # Get DOI if available
                    doi = None
                    doi_elem = entry.find("{http://arxiv.org/schemas/atom}doi", ns)
                    if doi_elem is not None:
                        doi = doi_elem.text

                    results.append(PaperResult(
                        title=title_text,
                        authors=authors,
                        year=year,
                        doi=doi,
                        journal="arXiv",
                        abstract=abstract,
                        pdf_url=pdf_url,
                        source="arxiv",
                        confidence=1.0,
                        arxiv_id=arxiv_id
                    ))

            except Exception as e:
                print(f"arXiv error: {e}")

        return results

    # ==================== Springer/Nature ====================
    async def _search_springer(self, query: str, limit: int = 10) -> List[PaperResult]:
        """Search Springer/Nature publications."""
        if not self.springer_key:
            return []

        await self._rate_limiter.wait("crossref")  # Reuse crossref rate limit

        base_url = "https://api.springernature.com/meta/v2/json"

        params = {
            "q": f'title:"{query}"',
            "api_key": self.springer_key,
            "p": limit,
            "s": 1  # Start from first result
        }

        results = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(base_url, params=params)
                if response.status_code != 200:
                    print(f"Springer returned {response.status_code}")
                    return results

                data = response.json()

                for record in data.get("records", []):
                    # Extract authors
                    authors = []
                    for creator in record.get("creators", []):
                        name = creator.get("creator", "")
                        if name:
                            authors.append(name)

                    # Extract DOI
                    doi = None
                    for identifier in record.get("identifier", []):
                        if identifier.get("type") == "doi":
                            doi = identifier.get("value")
                            break

                    # Extract year from publicationDate
                    year = None
                    pub_date = record.get("publicationDate")
                    if pub_date and len(pub_date) >= 4:
                        try:
                            year = int(pub_date[:4])
                        except ValueError:
                            pass

                    # Get PDF URL if available
                    pdf_url = None
                    for url_info in record.get("url", []):
                        if url_info.get("format") == "pdf":
                            pdf_url = url_info.get("value")
                            break

                    results.append(PaperResult(
                        title=record.get("title", ""),
                        authors=authors,
                        year=year,
                        doi=doi,
                        journal=record.get("publicationName"),
                        abstract=record.get("abstract"),
                        pdf_url=pdf_url,
                        source="springer",
                        confidence=1.0
                    ))

            except Exception as e:
                print(f"Springer error: {e}")

        return results

    # ==================== PubMed ====================
    async def _search_pubmed(self, query: str, limit: int = 10) -> List[PaperResult]:
        """Search PubMed for biomedical literature."""
        # Rate limit
        await self._rate_limiter.wait("pubmed")

        # First search for IDs
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

        params = {
            "db": "pubmed",
            "term": query,
            "retmax": limit,
            "retmode": "json",
            "sort": "relevance"
        }
        if self.pubmed_email:
            params["email"] = self.pubmed_email
        if self.pubmed_tool:
            params["tool"] = self.pubmed_tool

        results = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Get PMIDs
                response = await client.get(search_url, params=params)
                if response.status_code != 200:
                    print(f"PubMed search returned {response.status_code}")
                    return results

                data = response.json()
                pmids = data.get("esearchresult", {}).get("idlist", [])

                if not pmids:
                    return results

                # Fetch details for PMIDs
                fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "retmode": "xml"
                }
                if self.pubmed_email:
                    fetch_params["email"] = self.pubmed_email

                fetch_response = await client.get(fetch_url, params=fetch_params)
                if fetch_response.status_code != 200:
                    return results

                # Parse XML
                root = ET.fromstring(fetch_response.text)

                for article in root.findall(".//PubmedArticle"):
                    medline = article.find(".//MedlineCitation")
                    if medline is None:
                        continue

                    article_elem = medline.find(".//Article")
                    if article_elem is None:
                        continue

                    # Title
                    title_elem = article_elem.find(".//ArticleTitle")
                    title = title_elem.text if title_elem is not None else ""

                    # Authors
                    authors = []
                    for author in article_elem.findall(".//Author"):
                        lastname = author.find("LastName")
                        forename = author.find("ForeName")
                        if lastname is not None:
                            name = lastname.text
                            if forename is not None:
                                name = f"{forename.text} {name}"
                            authors.append(name)

                    # Year
                    year = None
                    pub_date = article_elem.find(".//PubDate/Year")
                    if pub_date is not None:
                        year = int(pub_date.text)

                    # Journal
                    journal_elem = article_elem.find(".//Journal/Title")
                    journal = journal_elem.text if journal_elem is not None else None

                    # Abstract
                    abstract_elem = article_elem.find(".//Abstract/AbstractText")
                    abstract = abstract_elem.text if abstract_elem is not None else None

                    # DOI
                    doi = None
                    for article_id in article.findall(".//ArticleId"):
                        if article_id.get("IdType") == "doi":
                            doi = article_id.text
                            break

                    # PMID
                    pmid = medline.find(".//PMID")
                    url = None
                    if pmid is not None:
                        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid.text}/"

                    results.append(PaperResult(
                        title=title,
                        authors=authors,
                        year=year,
                        doi=doi,
                        journal=journal,
                        abstract=abstract,
                        url=url,
                        source="pubmed",
                        confidence=1.0
                    ))

            except Exception as e:
                print(f"PubMed error: {e}")

        return results

    # ==================== Utility ====================

    # Common abbreviations in ALD/MLD literature
    ABBREVIATIONS = {
        'ald': 'atomic layer deposition',
        'mld': 'molecular layer deposition',
        'cvd': 'chemical vapor deposition',
        'pvd': 'physical vapor deposition',
        'xps': 'x-ray photoelectron spectroscopy',
        'ftir': 'fourier transform infrared',
        'sem': 'scanning electron microscopy',
        'tem': 'transmission electron microscopy',
        'afm': 'atomic force microscopy',
        'tma': 'trimethylaluminum',
        'dez': 'diethylzinc',
        'gpc': 'growth per cycle',
    }

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        t = text.lower()
        t = re.sub(r'[^\w\s]', '', t)  # Remove punctuation
        t = ' '.join(t.split())  # Normalize whitespace
        return t

    def _expand_abbreviations(self, text: str) -> str:
        """Expand common abbreviations in the text."""
        words = text.lower().split()
        expanded = []
        for word in words:
            if word in self.ABBREVIATIONS:
                expanded.append(self.ABBREVIATIONS[word])
            else:
                expanded.append(word)
        return ' '.join(expanded)

    def _edit_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein edit distance between two strings."""
        if len(s1) < len(s2):
            return self._edit_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def _fuzzy_word_match(self, word1: str, word2: str, max_distance: int = 2) -> bool:
        """Check if two words match with allowed typos (edit distance)."""
        if word1 == word2:
            return True
        # Only apply fuzzy matching to longer words (5+ chars)
        if len(word1) < 5 or len(word2) < 5:
            return False
        # Length difference check
        if abs(len(word1) - len(word2)) > max_distance:
            return False
        return self._edit_distance(word1, word2) <= max_distance

    def _fuzzy_jaccard(self, words1: set, words2: set) -> float:
        """Calculate Jaccard similarity with fuzzy word matching."""
        if not words1 or not words2:
            return 0.0

        # Count exact matches
        exact_matches = words1 & words2

        # Find fuzzy matches for remaining words
        remaining1 = words1 - exact_matches
        remaining2 = words2 - exact_matches
        fuzzy_matches = 0

        for w1 in remaining1:
            for w2 in remaining2:
                if self._fuzzy_word_match(w1, w2):
                    fuzzy_matches += 1
                    break  # Each word matches at most once

        total_matches = len(exact_matches) + fuzzy_matches
        union_size = len(words1 | words2)

        return total_matches / union_size if union_size > 0 else 0.0

    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles using multiple methods."""
        # Expand abbreviations first
        t1_expanded = self._expand_abbreviations(title1)
        t2_expanded = self._expand_abbreviations(title2)

        t1 = self._normalize_text(t1_expanded)
        t2 = self._normalize_text(t2_expanded)

        if not t1 or not t2:
            return 0.0

        words1 = set(t1.split())
        words2 = set(t2.split())

        if not words1 or not words2:
            return 0.0

        # Remove common stopwords for matching
        stopwords = {'a', 'an', 'the', 'of', 'in', 'for', 'on', 'to', 'and', 'with', 'by', 'from', 'as', 'at', 'its'}
        content_words1 = words1 - stopwords
        content_words2 = words2 - stopwords

        # Method 1: Fuzzy Jaccard similarity (handles typos)
        fuzzy_jaccard = self._fuzzy_jaccard(words1, words2)

        # Method 2: Query coverage - what fraction of query words appear in result?
        # This helps when query is short but all words match
        if content_words1:
            query_matches = sum(1 for w1 in content_words1
                              if any(self._fuzzy_word_match(w1, w2) for w2 in content_words2))
            query_coverage = query_matches / len(content_words1)
        else:
            query_coverage = 0.0

        # Method 3: Contains check (one title is a subset of the other)
        if t1 in t2 or t2 in t1:
            contains_bonus = 0.2
        else:
            contains_bonus = 0.0

        # Method 4: LCS similarity on sorted words (for longer texts)
        if len(words1) > 3 and len(words2) > 3:
            sorted1 = ' '.join(sorted(words1))
            sorted2 = ' '.join(sorted(words2))
            lcs_score = self._lcs_similarity(sorted1, sorted2) * 0.3
        else:
            lcs_score = 0.0

        # Weighted combination:
        # - If query is short (all content words match), boost with query_coverage
        # - If query is long, use Jaccard as primary
        if len(content_words1) <= 5 and query_coverage >= 0.8:
            # Short query with high coverage - boost confidence
            return min(1.0, query_coverage * 0.6 + fuzzy_jaccard * 0.3 + contains_bonus)
        else:
            # Normal case
            return min(1.0, fuzzy_jaccard * 0.5 + lcs_score + query_coverage * 0.2 + contains_bonus)

    def _lcs_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity based on longest common subsequence."""
        if not s1 or not s2:
            return 0.0

        # Use ratio of LCS length to average string length
        m, n = len(s1), len(s2)

        # Simple LCS length calculation
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])

        lcs_len = dp[m][n]
        return (2 * lcs_len) / (m + n)  # Similar to Dice coefficient

    def _author_match_score(self, query_author: Optional[str], result_authors: List[str]) -> float:
        """Score how well authors match (0.0 to 1.0)."""
        if not query_author or not result_authors:
            return 0.5  # Neutral if no author info

        query_author = self._normalize_text(query_author)
        query_parts = query_author.split()

        # Check if any query author name part appears in result authors
        for result_author in result_authors:
            result_norm = self._normalize_text(result_author)
            for part in query_parts:
                if len(part) > 2 and part in result_norm:
                    return 1.0  # Strong author match

        return 0.0  # No author match

    def calculate_match_confidence(self, query_title: str, result: PaperResult,
                                    query_author: Optional[str] = None,
                                    query_year: Optional[int] = None) -> float:
        """
        Calculate comprehensive match confidence score.

        Returns a score from 0.0 to 1.0 based on:
        - Title similarity (weighted 0.5)
        - Author match (weighted 0.3)
        - Year match (weighted 0.2)
        """
        # Title similarity (0-1)
        title_score = self._title_similarity(query_title, result.title)

        # Author match (0-1)
        author_score = self._author_match_score(query_author, result.authors)

        # Year match (0 or 1)
        year_score = 0.5  # Neutral default
        if query_year and result.year:
            if query_year == result.year:
                year_score = 1.0
            elif abs(query_year - result.year) == 1:
                year_score = 0.7  # Off by one year (publication lag)
            else:
                year_score = 0.0  # Wrong year is a strong negative signal

        # Weighted combination
        confidence = (
            title_score * 0.5 +
            author_score * 0.3 +
            year_score * 0.2
        )

        return round(confidence, 3)


    async def find_doi_by_citation(self, title: str, author: Optional[str] = None,
                                     year: Optional[int] = None,
                                     journal: Optional[str] = None) -> Optional[PaperResult]:
        """
        Find DOI using full citation metadata with improved matching.

        This method:
        1. Uses CrossRef bibliographic query for better matching
        2. Uses author/year for validation, not just title
        3. Returns None if confidence is too low (< 0.7)
        """
        # Build a full citation query string for CrossRef
        query_parts = [title]
        if author:
            first_author = author.split(" and ")[0].split(",")[0].strip()
            query_parts.insert(0, first_author)
        if journal:
            query_parts.append(journal)

        full_query = " ".join(query_parts)

        # Search CrossRef with bibliographic query
        await self._rate_limiter.wait("crossref")

        base_url = "https://api.crossref.org/works"
        params = {
            "query.bibliographic": full_query,
            "rows": 5,
            "select": "DOI,title,author,published-print,published-online,container-title,abstract"
        }

        headers = {}
        if self.crossref_email:
            headers["User-Agent"] = f"LiteratureAI/1.0 (mailto:{self.crossref_email})"

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(base_url, params=params, headers=headers)
                if response.status_code != 200:
                    return None

                data = response.json()
                items = data.get("message", {}).get("items", [])

                for item in items:
                    item_title = item.get("title", [""])[0] if item.get("title") else ""

                    item_year = None
                    if item.get("published-print"):
                        item_year = item["published-print"].get("date-parts", [[None]])[0][0]
                    elif item.get("published-online"):
                        item_year = item["published-online"].get("date-parts", [[None]])[0][0]

                    authors_list = []
                    for auth in item.get("author", []):
                        name = f"{auth.get('given', '')} {auth.get('family', '')}".strip()
                        if name:
                            authors_list.append(name)

                    result = PaperResult(
                        title=item_title,
                        authors=authors_list,
                        year=item_year,
                        doi=item.get("DOI"),
                        journal=item.get("container-title", [""])[0] if item.get("container-title") else None,
                        abstract=item.get("abstract"),
                        source="crossref",
                        confidence=0.0
                    )

                    # Calculate comprehensive confidence
                    result.confidence = self.calculate_match_confidence(
                        title, result, author, year
                    )
                    results.append(result)

            except Exception as e:
                print(f"CrossRef bibliographic error: {e}")
                return None

        if not results:
            return None

        # Sort by confidence and return best match
        results.sort(key=lambda x: x.confidence, reverse=True)
        best = results[0]

        # Only return if confidence is above threshold
        if best.confidence >= 0.7:
            return best

        return None


# Convenience functions for direct use
async def find_doi(title: str, author: str = None, year: int = None) -> Optional[str]:
    """Find DOI for a paper by title."""
    service = ExternalSearchService()
    result = await service.find_doi_by_title(title, author, year)
    return result.doi if result else None


async def find_doi_strict(title: str, author: str = None, year: int = None,
                          journal: str = None) -> Optional[Dict[str, Any]]:
    """
    Find DOI with strict matching using full citation metadata.

    Returns dict with 'doi' and 'confidence' if found, None otherwise.
    Only returns matches with confidence >= 0.7

    Search strategy:
    1. Try CrossRef bibliographic search first (most accurate)
    2. Fall back to manual CrossRef multi-search with expanded query
    3. Return best result above 0.7 threshold
    """
    service = ExternalSearchService()

    # Strategy 1: CrossRef bibliographic search
    result = await service.find_doi_by_citation(title, author, year, journal)
    if result:
        return {
            "doi": result.doi,
            "title": result.title,
            "authors": result.authors,
            "year": result.year,
            "journal": result.journal,
            "confidence": result.confidence,
            "source": result.source
        }

    # Strategy 2: Manual search with abbreviation expansion
    expanded_title = service._expand_abbreviations(title)
    results = await service._search_crossref_multi(expanded_title, 10, author, year)

    # Calculate confidence for each result and find best match
    best_match = None
    best_confidence = 0.0

    for r in results:
        confidence = service.calculate_match_confidence(title, r, author, year)
        if confidence >= 0.7 and confidence > best_confidence:
            best_confidence = confidence
            r.confidence = confidence
            best_match = r

    if best_match:
        return {
            "doi": best_match.doi,
            "title": best_match.title,
            "authors": best_match.authors,
            "year": best_match.year,
            "journal": best_match.journal,
            "confidence": best_match.confidence,
            "source": best_match.source
        }

    return None


async def search_external(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search external databases for papers."""
    service = ExternalSearchService()
    results = await service.search_papers(query, limit)
    return [
        {
            "title": r.title,
            "authors": r.authors,
            "year": r.year,
            "doi": r.doi,
            "journal": r.journal,
            "pdf_url": r.pdf_url,
            "source": r.source,
            "citation_count": r.citation_count
        }
        for r in results
    ]


async def search_all(query: str, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """Search all sources and return grouped results."""
    service = ExternalSearchService()
    all_results = await service.search_all_sources(query, limit)
    return {
        source: [
            {
                "title": r.title,
                "authors": r.authors,
                "year": r.year,
                "doi": r.doi,
                "journal": r.journal,
                "source": r.source,
                "citation_count": r.citation_count,
                "abstract": r.abstract[:200] + "..." if r.abstract and len(r.abstract) > 200 else r.abstract
            }
            for r in results
        ]
        for source, results in all_results.items()
    }
