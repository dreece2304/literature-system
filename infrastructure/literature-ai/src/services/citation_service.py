"""
Citation service for bibliography generation and BibTeX handling.

Provides utilities for formatting citations, generating bibliographies,
and converting between citation formats.
"""

import re
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass
from loguru import logger


@dataclass
class Citation:
    """Represents a single citation."""

    paper_id: str
    title: str
    authors: str
    year: Optional[int]
    venue: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    pages: Optional[str] = None
    volume: Optional[str] = None
    number: Optional[str] = None

    @property
    def cite_key(self) -> str:
        """
        Generate BibTeX citation key.

        Format: FirstAuthorYearFirstWord
        Example: vaswani2017attention
        """
        # Extract first author's last name
        first_author = self.authors.split(",")[0].split(" and ")[0].strip()
        last_name = first_author.split()[-1].lower()

        # Remove special characters
        last_name = re.sub(r"[^a-z]", "", last_name)

        # Extract first significant word from title
        words = re.findall(r"\b[a-z]{4,}\b", self.title.lower())
        first_word = words[0] if words else "paper"

        # Combine
        year_str = str(self.year) if self.year else "xxxx"
        return f"{last_name}{year_str}{first_word}"

    def to_bibtex(self, entry_type: str = "article") -> str:
        """
        Generate BibTeX entry.

        Args:
            entry_type: BibTeX entry type (article, inproceedings, etc.)

        Returns:
            BibTeX string
        """
        lines = [f"@{entry_type}{{{self.cite_key},"]

        # Required fields
        lines.append(f"  title = {{{self.title}}},")
        lines.append(f"  author = {{{self.authors}}},")

        if self.year:
            lines.append(f"  year = {{{self.year}}},")

        # Optional fields
        if self.venue:
            if entry_type == "inproceedings":
                lines.append(f"  booktitle = {{{self.venue}}},")
            else:
                lines.append(f"  journal = {{{self.venue}}},")

        if self.volume:
            lines.append(f"  volume = {{{self.volume}}},")

        if self.number:
            lines.append(f"  number = {{{self.number}}},")

        if self.pages:
            lines.append(f"  pages = {{{self.pages}}},")

        if self.doi:
            lines.append(f"  doi = {{{self.doi}}},")

        if self.url:
            lines.append(f"  url = {{{self.url}}},")

        lines.append("}")

        return "\n".join(lines)

    def to_apa(self) -> str:
        """
        Format citation in APA style.

        Returns:
            APA formatted citation string
        """
        # Authors (APA format: LastName, F. M.)
        # For simplicity, keep as-is (proper formatting would parse names)
        authors = self.authors

        # Year
        year_str = f"({self.year})" if self.year else "(n.d.)"

        # Title (italicized in actual APA)
        title = self.title

        # Venue
        venue_str = f" {self.venue}." if self.venue else ""

        # DOI
        doi_str = f" https://doi.org/{self.doi}" if self.doi else ""

        return f"{authors}. {year_str}. {title}.{venue_str}{doi_str}"

    def to_mla(self) -> str:
        """
        Format citation in MLA style.

        Returns:
            MLA formatted citation string
        """
        # Authors (MLA format: LastName, FirstName.)
        authors = self.authors

        # Title (in quotes)
        title = f'"{self.title}"'

        # Venue (italicized in actual MLA)
        venue_str = f" {self.venue}" if self.venue else ""

        # Year
        year_str = f", {self.year}" if self.year else ""

        # Pages
        pages_str = f", pp. {self.pages}" if self.pages else ""

        return f"{authors}. {title}.{venue_str}{year_str}{pages_str}."

    def to_chicago(self) -> str:
        """
        Format citation in Chicago style.

        Returns:
            Chicago formatted citation string
        """
        # Authors
        authors = self.authors

        # Year
        year_str = f" {self.year}." if self.year else ""

        # Title (in quotes for articles, italics for books)
        title = f'"{self.title}."'

        # Venue
        venue_str = f" {self.venue}" if self.venue else ""

        # Volume/number
        vol_str = ""
        if self.volume:
            vol_str = f" {self.volume}"
            if self.number:
                vol_str += f", no. {self.number}"

        # Pages
        pages_str = f": {self.pages}" if self.pages else ""

        return f"{authors}.{year_str} {title}{venue_str}{vol_str}{pages_str}."


class CitationService:
    """
    Service for citation formatting and bibliography generation.

    Features:
    - Multiple citation styles (APA, MLA, Chicago, BibTeX)
    - Bibliography generation from paper lists
    - Citation key generation
    - Duplicate detection
    """

    def __init__(self):
        """Initialize citation service."""
        logger.info("CitationService initialized")

    def create_citation(self, paper_data: Dict[str, Any]) -> Citation:
        """
        Create a Citation object from paper data.

        Args:
            paper_data: Paper metadata dictionary

        Returns:
            Citation object
        """
        return Citation(
            paper_id=paper_data.get("id") or paper_data.get("paper_id", "unknown"),
            title=paper_data.get("title", "Untitled"),
            authors=paper_data.get("authors", "Unknown"),
            year=paper_data.get("year"),
            venue=paper_data.get("venue") or paper_data.get("journal"),
            doi=paper_data.get("doi"),
            url=paper_data.get("url"),
            pages=paper_data.get("pages"),
            volume=paper_data.get("volume"),
            number=paper_data.get("number"),
        )

    def generate_bibliography(
        self,
        papers: List[Dict[str, Any]],
        style: Literal["apa", "mla", "chicago", "bibtex"] = "apa",
        sort: bool = True,
    ) -> str:
        """
        Generate a bibliography from a list of papers.

        Args:
            papers: List of paper metadata dictionaries
            style: Citation style
            sort: Sort alphabetically by author

        Returns:
            Formatted bibliography string
        """
        logger.info(f"Generating {style.upper()} bibliography for {len(papers)} papers")

        # Create citations
        citations = [self.create_citation(paper) for paper in papers]

        # Sort if requested
        if sort:
            citations.sort(key=lambda c: c.authors)

        # Format based on style
        if style == "bibtex":
            entries = [c.to_bibtex() for c in citations]
            return "\n\n".join(entries)
        elif style == "apa":
            entries = [c.to_apa() for c in citations]
            return "\n\n".join(entries)
        elif style == "mla":
            entries = [c.to_mla() for c in citations]
            return "\n\n".join(entries)
        elif style == "chicago":
            entries = [c.to_chicago() for c in citations]
            return "\n\n".join(entries)
        else:
            raise ValueError(f"Unknown citation style: {style}")

    def format_inline_citation(
        self,
        paper_data: Dict[str, Any],
        style: Literal["author-year", "numeric", "superscript"] = "author-year",
    ) -> str:
        """
        Format an inline citation.

        Args:
            paper_data: Paper metadata
            style: Inline citation style

        Returns:
            Formatted inline citation
        """
        citation = self.create_citation(paper_data)

        if style == "author-year":
            # Extract first author's last name
            first_author = citation.authors.split(",")[0].split(" and ")[0].strip()
            last_name = first_author.split()[-1]

            year_str = str(citation.year) if citation.year else "n.d."

            # Handle multiple authors
            if " and " in citation.authors or "," in citation.authors:
                return f"[{last_name} et al., {year_str}]"
            else:
                return f"[{last_name}, {year_str}]"

        elif style == "numeric":
            # Would need to track numbering across document
            return "[1]"

        elif style == "superscript":
            return "¹"

        else:
            raise ValueError(f"Unknown inline style: {style}")

    def extract_citations_from_text(self, text: str) -> List[str]:
        """
        Extract citation markers from text.

        Args:
            text: Text containing citations

        Returns:
            List of citation markers (e.g., ["Smith2020", "Jones2021"])
        """
        # Match [AuthorYear] pattern
        pattern = r"\[([A-Za-z]+\d{4}[a-z]?)\]"
        matches = re.findall(pattern, text)

        logger.debug(f"Extracted {len(matches)} citations from text")
        return matches

    def resolve_citation_key(
        self,
        cite_key: str,
        available_papers: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a citation key to a paper.

        Args:
            cite_key: Citation key (e.g., "smith2020machine")
            available_papers: List of available papers

        Returns:
            Matching paper or None
        """
        # Create citations for all papers
        citations = [self.create_citation(paper) for paper in available_papers]

        # Find matching citation
        for i, citation in enumerate(citations):
            if citation.cite_key == cite_key.lower():
                return available_papers[i]

        logger.warning(f"Could not resolve citation key: {cite_key}")
        return None

    def deduplicate_citations(
        self,
        papers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Remove duplicate papers from citation list.

        Deduplication based on DOI, title, or cite key.

        Args:
            papers: List of paper metadata

        Returns:
            Deduplicated list
        """
        seen_dois = set()
        seen_titles = set()
        deduplicated = []

        for paper in papers:
            # Check DOI
            doi = paper.get("doi")
            if doi and doi in seen_dois:
                continue

            # Check title (case-insensitive)
            title = paper.get("title", "").lower().strip()
            if title and title in seen_titles:
                continue

            # Add to results
            deduplicated.append(paper)

            if doi:
                seen_dois.add(doi)
            if title:
                seen_titles.add(title)

        removed = len(papers) - len(deduplicated)
        if removed > 0:
            logger.info(f"Removed {removed} duplicate citations")

        return deduplicated

    def validate_citation(self, paper_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate citation data and report issues.

        Args:
            paper_data: Paper metadata

        Returns:
            Validation result with warnings/errors
        """
        warnings = []
        errors = []

        # Check required fields
        if not paper_data.get("title"):
            errors.append("Missing title")

        if not paper_data.get("authors"):
            errors.append("Missing authors")

        # Check optional but recommended fields
        if not paper_data.get("year"):
            warnings.append("Missing publication year")

        if not paper_data.get("venue") and not paper_data.get("journal"):
            warnings.append("Missing venue/journal")

        if not paper_data.get("doi") and not paper_data.get("url"):
            warnings.append("Missing DOI or URL")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }


# Global singleton instance
_citation_service: Optional[CitationService] = None


def get_citation_service() -> CitationService:
    """
    Get global CitationService instance (singleton).

    Returns:
        Shared CitationService instance
    """
    global _citation_service

    if _citation_service is None:
        _citation_service = CitationService()

    return _citation_service


def reset_citation_service():
    """Reset global citation service (useful for testing)."""
    global _citation_service
    _citation_service = None
