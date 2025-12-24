"""Extract and parse academic paper metadata."""
import re
from typing import Dict, List, Optional


class MetadataExtractor:
    """Extract structured metadata from paper text and filenames."""

    def __init__(self):
        # Common academic paper patterns
        self.doi_pattern = re.compile(r'10\.\d{4,}/[^\s]+')
        self.arxiv_pattern = re.compile(r'arXiv:(\d{4}\.\d{4,5})')
        self.pubmed_pattern = re.compile(r'PMID:\s*(\d+)')
        self.year_pattern = re.compile(r'\b(19|20)\d{2}\b')

        # Journal patterns (common formats)
        self.journal_patterns = [
            re.compile(r'(?:Journal of|J\.|Proc\.|Proceedings of)\s+([^,\n]{10,50})'),
            re.compile(r'([A-Z][a-z]+\s+(?:[A-Z][a-z]+\s+)*(?:Journal|Review|Letters|Science))'),
        ]

    def extract_from_text(self, text: str, filename: Optional[str] = None) -> Dict:
        """
        Extract metadata from paper text and filename.

        Args:
            text: Full text of the paper
            filename: Optional filename for additional hints

        Returns:
            Dict containing extracted metadata
        """
        metadata = {}

        if not text:
            return metadata

        # Extract identifiers
        metadata.update(self._extract_identifiers(text))

        # Extract title (usually first substantial line)
        title = self._extract_title(text)
        if title:
            metadata['title'] = title

        # Extract year
        year = self._extract_year(text, filename)
        if year:
            metadata['year'] = year

        # Extract journal
        journal = self._extract_journal(text)
        if journal:
            metadata['journal'] = journal

        # Extract abstract
        abstract = self._extract_abstract(text)
        if abstract:
            metadata['abstract'] = abstract

        return metadata

    def _extract_identifiers(self, text: str) -> Dict:
        """Extract DOI, ArXiv ID, and PubMed ID."""
        identifiers = {}

        # DOI
        doi_match = self.doi_pattern.search(text)
        if doi_match:
            identifiers['doi'] = doi_match.group(0)

        # ArXiv
        arxiv_match = self.arxiv_pattern.search(text)
        if arxiv_match:
            identifiers['arxiv_id'] = arxiv_match.group(1)

        # PubMed
        pubmed_match = self.pubmed_pattern.search(text)
        if pubmed_match:
            identifiers['pubmed_id'] = pubmed_match.group(1)

        return identifiers

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract paper title from text."""
        lines = text.split('\n')

        # Look for the first substantial line (likely the title)
        for line in lines[:20]:  # Check first 20 lines
            line = line.strip()

            # Skip short lines, URLs, headers, etc.
            if (len(line) < 10 or
                line.startswith('http') or
                line.isupper() or
                line.isdigit() or
                    'page' in line.lower()):
                continue

            # Title should be substantial but not too long
            if 20 <= len(line) <= 200:
                # Clean up common title artifacts
                title = re.sub(r'\s+', ' ', line)
                title = title.strip('.,;:')
                return title

        return None

    def _extract_year(self, text: str, filename: Optional[str] = None) -> Optional[int]:
        """Extract publication year."""
        # First try filename for year hints
        if filename:
            filename_years = self.year_pattern.findall(filename)
            if filename_years:
                return int(filename_years[0])

        # Extract from text (look in first portion)
        text_sample = text[:2000]  # First 2000 chars
        years = self.year_pattern.findall(text_sample)

        if years:
            # Return most recent reasonable year
            valid_years = [int(y) for y in years if 1950 <= int(y) <= 2025]
            if valid_years:
                return max(valid_years)

        return None

    def _extract_journal(self, text: str) -> Optional[str]:
        """Extract journal name from text."""
        # Check first 1000 characters for journal patterns
        text_sample = text[:1000]

        for pattern in self.journal_patterns:
            match = pattern.search(text_sample)
            if match:
                journal = match.group(1).strip()
                if len(journal) > 5:  # Reasonable journal name length
                    return journal

        return None

    def _extract_abstract(self, text: str) -> Optional[str]:
        """Extract abstract from paper text."""
        # Look for abstract section
        abstract_patterns = [
            re.compile(r'Abstract[:\s]+(.*?)(?=\n\s*\n|\n\s*(?:Keywords|Introduction|1\.|\d+\.))',
                       re.IGNORECASE | re.DOTALL),
            re.compile(r'ABSTRACT[:\s]+(.*?)(?=\n\s*\n|\n\s*(?:KEYWORDS|INTRODUCTION|1\.|\d+\.))',
                       re.DOTALL),
        ]

        for pattern in abstract_patterns:
            match = pattern.search(text)
            if match:
                abstract = match.group(1).strip()
                # Clean up abstract
                abstract = re.sub(r'\s+', ' ', abstract)
                if 50 <= len(abstract) <= 2000:  # Reasonable abstract length
                    return abstract

        return None

    def extract_authors_from_text(self, text: str) -> List[str]:
        """Extract author names from text (basic implementation)."""
        authors = []

        # Look for author patterns in first few lines
        lines = text.split('\n')[:10]

        for line in lines:
            # Simple pattern for author names
            # This is a basic implementation - could be enhanced
            author_pattern = re.compile(r'([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)*[A-Z][a-z]+)')
            matches = author_pattern.findall(line)

            if matches and len(matches) <= 10:  # Reasonable number of authors
                authors.extend(matches)

        # Remove duplicates while preserving order
        seen = set()
        unique_authors = []
        for author in authors:
            if author not in seen and len(author) > 5:  # Reasonable name length
                seen.add(author)
                unique_authors.append(author)

        return unique_authors[:20]  # Limit to reasonable number
