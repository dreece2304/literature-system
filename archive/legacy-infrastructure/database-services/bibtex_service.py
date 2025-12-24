"""
BibTeX integration service for literature database.

Provides functionality to:
- Parse .bib files and extract entries
- Generate .bib entries from database papers
- Detect duplicates and inconsistencies
- Match citation keys to papers using fuzzy matching
- Fix and standardize .bib files
"""
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set
from difflib import SequenceMatcher
from sqlalchemy.orm import Session

from src.models import Paper, CitationLocation


@dataclass
class BibEntry:
    """Represents a parsed BibTeX entry."""
    entry_type: str  # article, book, inproceedings, etc.
    citation_key: str
    fields: Dict[str, str]
    raw_text: str = ""
    line_number: int = 0

    @property
    def title(self) -> Optional[str]:
        return self.fields.get('title')

    @property
    def author(self) -> Optional[str]:
        return self.fields.get('author')

    @property
    def year(self) -> Optional[str]:
        return self.fields.get('year')

    @property
    def doi(self) -> Optional[str]:
        return self.fields.get('doi')

    @property
    def journal(self) -> Optional[str]:
        return self.fields.get('journal') or self.fields.get('booktitle')


@dataclass
class BibAnalysisResult:
    """Results from analyzing a .bib file."""
    total_entries: int
    unique_keys: int
    duplicate_keys: List[str]
    entries_with_doi: int
    entries_without_doi: int
    matched_to_database: int
    unmatched_entries: List[str]
    inconsistent_keys: List[Tuple[str, str, str]]  # (bib_key, suggested_key, reason)
    missing_required_fields: List[Tuple[str, List[str]]]  # (key, missing_fields)
    potential_duplicates: List[Tuple[str, str, float]]  # (key1, key2, similarity)


@dataclass
class BibFixResult:
    """Results from fixing a .bib file."""
    entries_processed: int
    keys_standardized: int
    duplicates_removed: int
    entries_added_from_db: int
    entries_updated: int
    warnings: List[str]


@dataclass
class BibMatch:
    """A match between a bib entry and a database paper."""
    bib_key: str
    paper_id: int
    paper_title: str
    match_type: str  # 'exact_key', 'doi', 'title', 'fuzzy'
    confidence: float  # 0.0 to 1.0


class BibtexService:
    """Service for BibTeX file management and database integration."""

    # BibTeX entry pattern
    ENTRY_PATTERN = re.compile(
        r'@(\w+)\s*\{\s*([^,\s]+)\s*,(.+?)\n\}',
        re.DOTALL | re.MULTILINE
    )

    # Field pattern
    FIELD_PATTERN = re.compile(
        r'(\w+)\s*=\s*[{"](.+?)[}"](?:,|\s*$)',
        re.DOTALL
    )

    # Required fields by entry type
    REQUIRED_FIELDS = {
        'article': ['author', 'title', 'journal', 'year'],
        'book': ['author', 'title', 'publisher', 'year'],
        'inproceedings': ['author', 'title', 'booktitle', 'year'],
        'incollection': ['author', 'title', 'booktitle', 'year'],
        'phdthesis': ['author', 'title', 'school', 'year'],
        'misc': ['title'],
    }

    def __init__(self, db: Session):
        """Initialize the service with a database session."""
        self.db = db

    # ========== BibTeX Parsing ==========

    def parse_bib_file(self, bib_path: str) -> List[BibEntry]:
        """
        Parse a .bib file and return list of entries.

        Args:
            bib_path: Path to the .bib file

        Returns:
            List of BibEntry objects
        """
        path = Path(bib_path)
        if not path.exists():
            raise FileNotFoundError(f"BibTeX file not found: {bib_path}")

        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        return self._parse_bib_content(content)

    def _parse_bib_content(self, content: str) -> List[BibEntry]:
        """Parse BibTeX content string."""
        entries = []

        # More robust parsing - handle multi-line entries
        # Split by @ but keep the @
        raw_entries = re.split(r'(?=@\w+\s*\{)', content)

        for raw in raw_entries:
            raw = raw.strip()
            if not raw or raw.startswith('%'):
                continue

            # Extract entry type and key
            header_match = re.match(r'@(\w+)\s*\{\s*([^,\s]+)\s*,', raw)
            if not header_match:
                continue

            entry_type = header_match.group(1).lower()
            citation_key = header_match.group(2)

            # Extract fields
            fields = {}
            # Find the content between the first { and last }
            brace_start = raw.find('{')
            brace_end = raw.rfind('}')
            if brace_start == -1 or brace_end == -1:
                continue

            field_content = raw[brace_start+1:brace_end]

            # Parse fields - handle nested braces
            current_pos = field_content.find(',') + 1  # Skip the key
            while current_pos < len(field_content):
                # Find field name
                field_match = re.match(r'\s*(\w+)\s*=\s*', field_content[current_pos:])
                if not field_match:
                    break

                field_name = field_match.group(1).lower()
                value_start = current_pos + field_match.end()

                # Extract value (handle braces or quotes)
                value, value_end = self._extract_field_value(field_content, value_start)
                if value is not None:
                    # Clean the value
                    value = self._clean_field_value(value)
                    fields[field_name] = value

                current_pos = value_end + 1

            entries.append(BibEntry(
                entry_type=entry_type,
                citation_key=citation_key,
                fields=fields,
                raw_text=raw
            ))

        return entries

    def _extract_field_value(self, content: str, start: int) -> Tuple[Optional[str], int]:
        """Extract a field value handling nested braces."""
        if start >= len(content):
            return None, start

        # Skip whitespace
        while start < len(content) and content[start] in ' \t\n':
            start += 1

        if start >= len(content):
            return None, start

        delimiter = content[start]
        if delimiter == '{':
            end_delimiter = '}'
        elif delimiter == '"':
            end_delimiter = '"'
        else:
            # Unquoted value (number or macro)
            end = start
            while end < len(content) and content[end] not in ',}\n':
                end += 1
            return content[start:end].strip(), end

        # Handle nested braces
        depth = 1
        pos = start + 1
        while pos < len(content) and depth > 0:
            if content[pos] == '{':
                depth += 1
            elif content[pos] == '}':
                depth -= 1
            elif content[pos] == end_delimiter and delimiter == '"':
                depth = 0
            pos += 1

        return content[start+1:pos-1], pos

    def _clean_field_value(self, value: str) -> str:
        """Clean a BibTeX field value."""
        # Remove extra whitespace
        value = ' '.join(value.split())
        # Remove surrounding braces if present
        while value.startswith('{') and value.endswith('}'):
            value = value[1:-1]
        return value.strip()

    # ========== Analysis ==========

    def analyze_bib_file(
        self,
        bib_path: str,
        manuscript_id: Optional[int] = None
    ) -> BibAnalysisResult:
        """
        Analyze a .bib file for issues and inconsistencies.

        Args:
            bib_path: Path to the .bib file
            manuscript_id: Optional manuscript ID to check citations against

        Returns:
            BibAnalysisResult with analysis details
        """
        entries = self.parse_bib_file(bib_path)

        # Track keys for duplicate detection
        seen_keys = {}
        duplicate_keys = []

        # Track DOI presence
        entries_with_doi = 0
        entries_without_doi = 0

        # Track matching
        matched_to_database = 0
        unmatched_entries = []

        # Track issues
        inconsistent_keys = []
        missing_required_fields = []

        # Build database lookup indexes
        db_by_doi = self._build_doi_index()
        db_by_key = self._build_citation_key_index()

        for entry in entries:
            # Check for duplicate keys
            if entry.citation_key in seen_keys:
                duplicate_keys.append(entry.citation_key)
            seen_keys[entry.citation_key] = entry

            # Check DOI
            if entry.doi:
                entries_with_doi += 1
            else:
                entries_without_doi += 1

            # Check database match
            match = self._find_paper_match(entry, db_by_doi, db_by_key)
            if match:
                matched_to_database += 1

                # Check key consistency
                paper = self.db.query(Paper).filter_by(id=match.paper_id).first()
                suggested_key = self._generate_standard_key(paper)
                if entry.citation_key != suggested_key and entry.citation_key.lower() != suggested_key.lower():
                    inconsistent_keys.append((
                        entry.citation_key,
                        suggested_key,
                        f"Matched to paper {match.paper_id} via {match.match_type}"
                    ))
            else:
                unmatched_entries.append(entry.citation_key)

            # Check required fields
            required = self.REQUIRED_FIELDS.get(entry.entry_type, ['title'])
            missing = [f for f in required if f not in entry.fields]
            if missing:
                missing_required_fields.append((entry.citation_key, missing))

        # Find potential duplicates (same paper, different keys)
        potential_duplicates = self._find_potential_duplicates(entries)

        return BibAnalysisResult(
            total_entries=len(entries),
            unique_keys=len(seen_keys),
            duplicate_keys=list(set(duplicate_keys)),
            entries_with_doi=entries_with_doi,
            entries_without_doi=entries_without_doi,
            matched_to_database=matched_to_database,
            unmatched_entries=unmatched_entries,
            inconsistent_keys=inconsistent_keys,
            missing_required_fields=missing_required_fields,
            potential_duplicates=potential_duplicates
        )

    def _build_doi_index(self) -> Dict[str, Paper]:
        """Build index of papers by DOI."""
        papers = self.db.query(Paper).filter(Paper.doi.isnot(None)).all()
        return {self._normalize_doi(p.doi): p for p in papers if p.doi}

    def _build_citation_key_index(self) -> Dict[str, Paper]:
        """Build index of papers by citation key."""
        papers = self.db.query(Paper).filter(Paper.citation_key.isnot(None)).all()
        return {p.citation_key.lower(): p for p in papers if p.citation_key}

    def _normalize_doi(self, doi: str) -> str:
        """Normalize DOI for comparison."""
        if not doi:
            return ""
        doi = doi.lower().strip()
        # Remove common prefixes
        for prefix in ['https://doi.org/', 'http://doi.org/', 'doi:', 'doi.org/']:
            if doi.startswith(prefix):
                doi = doi[len(prefix):]
        return doi

    def _find_paper_match(
        self,
        entry: BibEntry,
        db_by_doi: Dict[str, Paper],
        db_by_key: Dict[str, Paper]
    ) -> Optional[BibMatch]:
        """Find a database paper matching a bib entry."""
        # 1. Try exact citation key match
        if entry.citation_key.lower() in db_by_key:
            paper = db_by_key[entry.citation_key.lower()]
            return BibMatch(
                bib_key=entry.citation_key,
                paper_id=paper.id,
                paper_title=paper.title,
                match_type='exact_key',
                confidence=1.0
            )

        # 2. Try DOI match
        if entry.doi:
            normalized_doi = self._normalize_doi(entry.doi)
            if normalized_doi in db_by_doi:
                paper = db_by_doi[normalized_doi]
                return BibMatch(
                    bib_key=entry.citation_key,
                    paper_id=paper.id,
                    paper_title=paper.title,
                    match_type='doi',
                    confidence=1.0
                )

        # 3. Try fuzzy title match
        if entry.title:
            match = self._fuzzy_title_match(entry.title, entry.year)
            if match:
                return match

        return None

    def _fuzzy_title_match(
        self,
        title: str,
        year: Optional[str] = None
    ) -> Optional[BibMatch]:
        """Find paper by fuzzy title matching."""
        # Normalize title
        normalized = self._normalize_title(title)

        # Query papers, optionally filtering by year
        query = self.db.query(Paper)
        if year:
            try:
                query = query.filter(Paper.year == int(year))
            except ValueError:
                pass

        papers = query.limit(500).all()  # Limit for performance

        best_match = None
        best_score = 0.0

        for paper in papers:
            if not paper.title:
                continue

            paper_normalized = self._normalize_title(paper.title)
            score = SequenceMatcher(None, normalized, paper_normalized).ratio()

            if score > best_score and score >= 0.85:  # 85% threshold
                best_score = score
                best_match = BibMatch(
                    bib_key="",  # Will be set by caller
                    paper_id=paper.id,
                    paper_title=paper.title,
                    match_type='title',
                    confidence=score
                )

        return best_match

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        # Lowercase, remove punctuation, extra whitespace
        title = title.lower()
        title = re.sub(r'[^\w\s]', ' ', title)
        title = ' '.join(title.split())
        return title

    def _find_potential_duplicates(
        self,
        entries: List[BibEntry]
    ) -> List[Tuple[str, str, float]]:
        """Find entries that might be duplicates of each other."""
        duplicates = []

        for i, e1 in enumerate(entries):
            for e2 in entries[i+1:]:
                # Same DOI = definite duplicate
                if e1.doi and e2.doi:
                    if self._normalize_doi(e1.doi) == self._normalize_doi(e2.doi):
                        duplicates.append((e1.citation_key, e2.citation_key, 1.0))
                        continue

                # Similar titles = potential duplicate
                if e1.title and e2.title:
                    t1 = self._normalize_title(e1.title)
                    t2 = self._normalize_title(e2.title)
                    score = SequenceMatcher(None, t1, t2).ratio()
                    if score >= 0.90:  # 90% similarity threshold
                        duplicates.append((e1.citation_key, e2.citation_key, score))

        return duplicates

    # ========== Generation ==========

    def generate_bib_entry(self, paper: Paper) -> str:
        """Generate a BibTeX entry for a paper."""
        # Determine entry type
        if paper.journal:
            if 'proc' in paper.journal.lower() or 'conference' in paper.journal.lower():
                entry_type = 'inproceedings'
            else:
                entry_type = 'article'
        else:
            entry_type = 'misc'

        # Generate citation key
        key = paper.citation_key or self._generate_standard_key(paper)

        # Build fields
        fields = []

        # Authors
        if paper.authors:
            author_str = ' and '.join([a.name for a in paper.authors])
            fields.append(f'  author = {{{author_str}}}')

        # Title
        fields.append(f'  title = {{{paper.title}}}')

        # Journal/Booktitle
        if paper.journal:
            if entry_type == 'inproceedings':
                fields.append(f'  booktitle = {{{paper.journal}}}')
            else:
                fields.append(f'  journal = {{{paper.journal}}}')

        # Year
        if paper.year:
            fields.append(f'  year = {{{paper.year}}}')

        # Volume, Issue, Pages
        if paper.volume:
            fields.append(f'  volume = {{{paper.volume}}}')
        if paper.issue:
            fields.append(f'  number = {{{paper.issue}}}')
        if paper.pages:
            fields.append(f'  pages = {{{paper.pages}}}')

        # Publisher
        if paper.publisher:
            fields.append(f'  publisher = {{{paper.publisher}}}')

        # DOI
        if paper.doi:
            fields.append(f'  doi = {{{paper.doi}}}')

        # Build entry
        fields_str = ',\n'.join(fields)
        return f'@{entry_type}{{{key},\n{fields_str}\n}}'

    def _generate_standard_key(self, paper: Paper) -> str:
        """Generate a standardized citation key for a paper."""
        # Get first author's last name
        if paper.authors:
            author_name = paper.authors[0].name
            if ',' in author_name:
                last_name = author_name.split(',')[0].strip()
            else:
                parts = author_name.split()
                last_name = parts[-1] if parts else "Unknown"
        else:
            last_name = "Unknown"

        # Clean last name
        last_name = re.sub(r'[^a-zA-Z]', '', last_name)

        # Year
        year = paper.year or "XXXX"

        # First significant word from title
        if paper.title:
            skip_words = {'a', 'an', 'the', 'on', 'of', 'in', 'for', 'to', 'with', 'by'}
            for word in paper.title.split():
                clean_word = re.sub(r'[^a-zA-Z]', '', word)
                if clean_word.lower() not in skip_words and len(clean_word) > 2:
                    first_word = clean_word.capitalize()
                    break
            else:
                first_word = "Paper"
        else:
            first_word = "Paper"

        return f"{last_name}{year}{first_word}"

    def generate_bib_file(
        self,
        paper_ids: Optional[List[int]] = None,
        manuscript_id: Optional[int] = None,
        include_uncited: bool = False
    ) -> str:
        """
        Generate a complete .bib file from database papers.

        Args:
            paper_ids: Specific paper IDs to include
            manuscript_id: Generate for papers cited in this manuscript
            include_uncited: Include papers not cited in the manuscript

        Returns:
            BibTeX content as string
        """
        entries = []
        entries.append(f"% Generated by literature-database on {datetime.now().strftime('%Y-%m-%d')}")
        entries.append("% Total entries: {count}")  # Placeholder
        entries.append("")

        papers = []

        if paper_ids:
            papers = self.db.query(Paper).filter(Paper.id.in_(paper_ids)).all()
        elif manuscript_id:
            # Get papers cited in this manuscript
            locations = self.db.query(CitationLocation).filter_by(
                manuscript_id=manuscript_id
            ).filter(CitationLocation.paper_id.isnot(None)).all()

            paper_ids_cited = list(set(loc.paper_id for loc in locations))
            papers = self.db.query(Paper).filter(Paper.id.in_(paper_ids_cited)).all()

            if include_uncited:
                # Add all papers with citation keys
                other_papers = self.db.query(Paper).filter(
                    Paper.citation_key.isnot(None),
                    ~Paper.id.in_(paper_ids_cited)
                ).all()
                papers.extend(other_papers)
        else:
            # All papers with citation keys
            papers = self.db.query(Paper).filter(
                Paper.citation_key.isnot(None)
            ).all()

        # Generate entries
        for paper in sorted(papers, key=lambda p: p.citation_key or self._generate_standard_key(p)):
            entries.append(self.generate_bib_entry(paper))
            entries.append("")

        # Update count
        content = '\n'.join(entries)
        content = content.replace("{count}", str(len(papers)))

        return content

    # ========== Fixing ==========

    def fix_bib_file(
        self,
        bib_path: str,
        output_path: Optional[str] = None,
        standardize_keys: bool = True,
        remove_duplicates: bool = True,
        add_missing_from_db: bool = True,
        manuscript_id: Optional[int] = None,
        dry_run: bool = False
    ) -> Tuple[str, BibFixResult]:
        """
        Fix and standardize a .bib file.

        Args:
            bib_path: Path to the input .bib file
            output_path: Path for output (None = same as input)
            standardize_keys: Standardize citation keys
            remove_duplicates: Remove duplicate entries
            add_missing_from_db: Add entries for missing citations from DB
            manuscript_id: Manuscript ID for finding missing citations
            dry_run: If True, don't write changes

        Returns:
            Tuple of (output content, BibFixResult)
        """
        entries = self.parse_bib_file(bib_path)

        # Build indexes
        db_by_doi = self._build_doi_index()
        db_by_key = self._build_citation_key_index()

        result = BibFixResult(
            entries_processed=len(entries),
            keys_standardized=0,
            duplicates_removed=0,
            entries_added_from_db=0,
            entries_updated=0,
            warnings=[]
        )

        # Track seen entries for duplicate removal
        seen_dois: Set[str] = set()
        seen_titles: Set[str] = set()
        output_entries: List[BibEntry] = []
        key_mapping: Dict[str, str] = {}  # old_key -> new_key

        for entry in entries:
            # Check for duplicates
            if remove_duplicates:
                if entry.doi:
                    norm_doi = self._normalize_doi(entry.doi)
                    if norm_doi in seen_dois:
                        result.duplicates_removed += 1
                        result.warnings.append(f"Removed duplicate (DOI): {entry.citation_key}")
                        continue
                    seen_dois.add(norm_doi)

                if entry.title:
                    norm_title = self._normalize_title(entry.title)
                    if norm_title in seen_titles:
                        result.duplicates_removed += 1
                        result.warnings.append(f"Removed duplicate (title): {entry.citation_key}")
                        continue
                    seen_titles.add(norm_title)

            # Standardize key
            new_key = entry.citation_key
            if standardize_keys:
                match = self._find_paper_match(entry, db_by_doi, db_by_key)
                if match:
                    paper = self.db.query(Paper).filter_by(id=match.paper_id).first()
                    suggested = self._generate_standard_key(paper)
                    if new_key != suggested:
                        key_mapping[entry.citation_key] = suggested
                        new_key = suggested
                        result.keys_standardized += 1

            # Create updated entry
            updated = BibEntry(
                entry_type=entry.entry_type,
                citation_key=new_key,
                fields=entry.fields.copy(),
                raw_text=entry.raw_text
            )
            output_entries.append(updated)

        # Add missing entries from database
        if add_missing_from_db and manuscript_id:
            # Find citations that aren't in the bib file
            locations = self.db.query(CitationLocation).filter_by(
                manuscript_id=manuscript_id
            ).all()

            existing_keys = {e.citation_key.lower() for e in output_entries}
            existing_keys.update(k.lower() for k in key_mapping.values())

            for loc in locations:
                if loc.citation_key.lower() not in existing_keys:
                    # Try to find paper by citation key
                    paper = None
                    if loc.paper_id:
                        paper = self.db.query(Paper).filter_by(id=loc.paper_id).first()
                    else:
                        # Try fuzzy match
                        paper = self._fuzzy_key_to_paper(loc.citation_key)

                    if paper:
                        new_entry = BibEntry(
                            entry_type='article',
                            citation_key=paper.citation_key or self._generate_standard_key(paper),
                            fields={
                                'title': paper.title,
                                'year': str(paper.year) if paper.year else '',
                                'doi': paper.doi or '',
                            }
                        )
                        output_entries.append(new_entry)
                        result.entries_added_from_db += 1
                        existing_keys.add(new_entry.citation_key.lower())

        # Generate output
        output_lines = [
            "% BibTeX file fixed by literature-database",
            f"% Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"% Total entries: {len(output_entries)}",
            ""
        ]

        for entry in sorted(output_entries, key=lambda e: e.citation_key.lower()):
            output_lines.append(self._regenerate_entry(entry))
            output_lines.append("")

        output_content = '\n'.join(output_lines)

        # Write if not dry run
        if not dry_run:
            out_path = output_path or bib_path
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(output_content)

        return output_content, result, key_mapping

    def _regenerate_entry(self, entry: BibEntry) -> str:
        """Regenerate a BibTeX entry with clean formatting."""
        lines = [f'@{entry.entry_type}{{{entry.citation_key},']

        # Order fields nicely
        field_order = ['author', 'title', 'journal', 'booktitle', 'year',
                       'volume', 'number', 'pages', 'publisher', 'doi', 'url']

        for field in field_order:
            if field in entry.fields and entry.fields[field]:
                value = entry.fields[field]
                lines.append(f'  {field} = {{{value}}},')

        # Add any remaining fields
        for field, value in entry.fields.items():
            if field not in field_order and value:
                lines.append(f'  {field} = {{{value}}},')

        # Remove trailing comma from last field
        if lines[-1].endswith(','):
            lines[-1] = lines[-1][:-1]

        lines.append('}')
        return '\n'.join(lines)

    def _fuzzy_key_to_paper(self, citation_key: str) -> Optional[Paper]:
        """Try to find a paper from a citation key using fuzzy matching."""
        # Extract author and year from key
        match = re.match(r'([A-Za-z]+)(\d{4})', citation_key)
        if not match:
            return None

        author_part = match.group(1).lower()
        year = int(match.group(2))

        # Search papers by year and author
        papers = self.db.query(Paper).filter(Paper.year == year).all()

        for paper in papers:
            for author in paper.authors:
                author_last = author.name.split()[-1].lower() if author.name else ""
                if author_last.startswith(author_part) or author_part.startswith(author_last):
                    return paper

        return None

    # ========== Queries ==========

    def get_missing_bib_entries(
        self,
        manuscript_id: int,
        bib_path: str
    ) -> List[Tuple[str, Optional[Paper]]]:
        """
        Find citation keys used in manuscript but missing from .bib file.

        Returns:
            List of (citation_key, matching_paper_or_none)
        """
        # Get citations from manuscript
        locations = self.db.query(CitationLocation).filter_by(
            manuscript_id=manuscript_id
        ).all()
        cited_keys = set(loc.citation_key for loc in locations)

        # Get keys in bib file
        entries = self.parse_bib_file(bib_path)
        bib_keys = set(e.citation_key for e in entries)

        # Find missing
        missing = []
        for key in cited_keys - bib_keys:
            # Try to find matching paper
            loc = next((loc_item for loc_item in locations if loc_item.citation_key == key), None)
            paper = None
            if loc and loc.paper_id:
                paper = self.db.query(Paper).filter_by(id=loc.paper_id).first()
            else:
                paper = self._fuzzy_key_to_paper(key)
            missing.append((key, paper))

        return missing

    def get_unused_bib_entries(
        self,
        manuscript_id: int,
        bib_path: str
    ) -> List[BibEntry]:
        """
        Find .bib entries not cited in the manuscript.

        Returns:
            List of unused BibEntry objects
        """
        # Get citations from manuscript
        locations = self.db.query(CitationLocation).filter_by(
            manuscript_id=manuscript_id
        ).all()
        cited_keys = set(loc.citation_key.lower() for loc in locations)

        # Get entries in bib file
        entries = self.parse_bib_file(bib_path)

        # Find unused
        unused = [e for e in entries if e.citation_key.lower() not in cited_keys]
        return unused
