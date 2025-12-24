"""
Citation mapping service for tracking paper citations in manuscripts.

Provides functionality to:
- Register and manage manuscript projects
- Scan LaTeX files for citation locations
- Match citations to papers in the database
- Generate citation key suggestions (AuthorYearFirstWord format)
- Export citation registries
"""
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from src.models import Paper, Manuscript, CitationLocation


@dataclass
class CitationMatch:
    """Represents a single citation found in a LaTeX file."""
    citation_key: str
    file_path: str
    line_number: int
    context: str
    section_inferred: str


@dataclass
class CitationScanResult:
    """Results from scanning a manuscript for citations."""
    manuscript_id: int
    total_citations: int
    unique_keys: int
    matched_to_papers: int
    unmatched_keys: List[str]
    locations_created: int
    scan_time: datetime = field(default_factory=datetime.now)


@dataclass
class CitationCheckResult:
    """Results from checking citation consistency."""
    manuscript_id: int
    total_papers_cited: int
    papers_with_citation_key: int
    papers_without_citation_key: int
    orphan_citations: List[str]  # Citation keys not matching any paper
    duplicate_locations: int
    issues: List[str]


class CitationService:
    """Service for managing citation mapping between papers and manuscripts."""

    # Pattern to match \cite{key1,key2,...} or \cite[...]{key1,key2,...}
    # Also matches \citet, \citep, \citeauthor, etc.
    CITE_PATTERN = re.compile(r'\\cite[tp]?(?:author)?(?:\[[^\]]*\])?\{([^}]+)\}')

    # Directories to skip during scanning
    SKIP_DIRECTORIES = {'Archive', 'archive', 'OLD', 'old', 'backup', 'Backup'}

    def __init__(self, db: Session):
        """Initialize the service with a database session."""
        self.db = db

    # ========== Manuscript Management ==========

    def register_manuscript(
        self,
        name: str,
        project_path: str,
        tex_directory: str = "paper/tex",
        bib_file: Optional[str] = None,
        description: Optional[str] = None
    ) -> Manuscript:
        """
        Register a new manuscript project for citation tracking.

        Args:
            name: Unique identifier for the manuscript (e.g., "Paper2")
            project_path: Absolute path to the project root
            tex_directory: Relative path to the tex directory from project_path
            bib_file: Relative path to the .bib file
            description: Optional description of the manuscript

        Returns:
            The created Manuscript object

        Raises:
            ValueError: If a manuscript with that name already exists
        """
        existing = self.db.query(Manuscript).filter_by(name=name).first()
        if existing:
            raise ValueError(f"Manuscript '{name}' already exists")

        manuscript = Manuscript(
            name=name,
            project_path=project_path,
            tex_directory=tex_directory,
            bib_file=bib_file,
            description=description
        )
        self.db.add(manuscript)
        self.db.commit()
        return manuscript

    def get_manuscript(self, manuscript_id: int) -> Optional[Manuscript]:
        """Get a manuscript by ID."""
        return self.db.query(Manuscript).filter_by(id=manuscript_id).first()

    def get_manuscript_by_name(self, name: str) -> Optional[Manuscript]:
        """Get a manuscript by name."""
        return self.db.query(Manuscript).filter_by(name=name).first()

    def list_manuscripts(self) -> List[Manuscript]:
        """List all registered manuscripts."""
        return self.db.query(Manuscript).all()

    def update_manuscript(
        self,
        manuscript_id: int,
        **kwargs
    ) -> Optional[Manuscript]:
        """Update manuscript fields."""
        manuscript = self.get_manuscript(manuscript_id)
        if not manuscript:
            return None

        for key, value in kwargs.items():
            if hasattr(manuscript, key):
                setattr(manuscript, key, value)

        self.db.commit()
        return manuscript

    def delete_manuscript(self, manuscript_id: int) -> bool:
        """Delete a manuscript and all its citation locations."""
        manuscript = self.get_manuscript(manuscript_id)
        if not manuscript:
            return False

        self.db.delete(manuscript)
        self.db.commit()
        return True

    # ========== Citation Scanning ==========

    def scan_citations(
        self,
        manuscript_id: int,
        clear_existing: bool = True
    ) -> CitationScanResult:
        """
        Scan a manuscript's LaTeX files for citations and update the database.

        Args:
            manuscript_id: ID of the manuscript to scan
            clear_existing: If True, delete existing citation locations before scanning

        Returns:
            CitationScanResult with scan statistics
        """
        manuscript = self.get_manuscript(manuscript_id)
        if not manuscript:
            raise ValueError(f"Manuscript {manuscript_id} not found")

        # Build full tex directory path
        tex_path = Path(manuscript.project_path) / manuscript.tex_directory

        if not tex_path.exists():
            raise FileNotFoundError(f"TeX directory not found: {tex_path}")

        # Clear existing locations if requested
        if clear_existing:
            self.db.query(CitationLocation).filter_by(
                manuscript_id=manuscript_id
            ).delete()

        # Scan for citations
        citations = self._find_citations_in_tex(tex_path)

        # Build citation key -> paper mapping
        key_to_paper = self._build_citation_key_map()

        # Create citation locations
        matched_keys = set()
        unmatched_keys = set()
        locations_created = 0

        for key, matches in citations.items():
            paper = key_to_paper.get(key)
            if paper:
                matched_keys.add(key)
            else:
                unmatched_keys.add(key)

            for match in matches:
                location = CitationLocation(
                    paper_id=paper.id if paper else None,
                    manuscript_id=manuscript_id,
                    citation_key=key,
                    file_path=match.file_path,
                    line_number=match.line_number,
                    context=match.context,
                    section_inferred=match.section_inferred
                )
                self.db.add(location)
                locations_created += 1

        # Update paper citation counts
        for key in matched_keys:
            paper = key_to_paper[key]
            paper.citation_count = len(citations[key])

        # Update manuscript last_scanned
        manuscript.last_scanned = datetime.now()
        self.db.commit()

        return CitationScanResult(
            manuscript_id=manuscript_id,
            total_citations=sum(len(m) for m in citations.values()),
            unique_keys=len(citations),
            matched_to_papers=len(matched_keys),
            unmatched_keys=list(unmatched_keys),
            locations_created=locations_created
        )

    def _find_citations_in_tex(self, tex_dir: Path) -> Dict[str, List[CitationMatch]]:
        """
        Scan all .tex files for citation commands.

        Returns:
            Dict mapping citation_key -> list of CitationMatch objects
        """
        citations: Dict[str, List[CitationMatch]] = {}

        for tex_file in tex_dir.rglob("*.tex"):
            # Skip archive directories
            if any(skip_dir in tex_file.parts for skip_dir in self.SKIP_DIRECTORIES):
                continue

            relative_path = tex_file.relative_to(tex_dir.parent)

            try:
                with open(tex_file, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        # Find all citations in this line
                        for match in self.CITE_PATTERN.finditer(line):
                            # Split multiple keys (e.g., \cite{A,B,C})
                            keys = [k.strip() for k in match.group(1).split(',')]

                            for key in keys:
                                if not key:
                                    continue

                                if key not in citations:
                                    citations[key] = []

                                # Extract context (~40 chars before and after)
                                start = max(0, match.start() - 40)
                                end = min(len(line), match.end() + 40)
                                context = line[start:end].strip()

                                # Infer section from file path
                                section_inferred = relative_path.stem

                                citations[key].append(CitationMatch(
                                    citation_key=key,
                                    file_path=str(relative_path),
                                    line_number=line_num,
                                    context=context,
                                    section_inferred=section_inferred
                                ))
            except UnicodeDecodeError:
                # Skip files that can't be read as UTF-8
                continue

        return citations

    def _build_citation_key_map(self) -> Dict[str, Paper]:
        """Build a mapping from citation_key to Paper."""
        papers = self.db.query(Paper).filter(Paper.citation_key.isnot(None)).all()
        return {p.citation_key: p for p in papers}

    # ========== Citation Validation ==========

    def check_citations(self, manuscript_id: int) -> CitationCheckResult:
        """
        Check citation consistency for a manuscript.

        Returns issues like:
        - Citation keys not matching any paper
        - Duplicate citation locations
        - Papers cited but missing citation_key
        """
        manuscript = self.get_manuscript(manuscript_id)
        if not manuscript:
            raise ValueError(f"Manuscript {manuscript_id} not found")

        locations = self.db.query(CitationLocation).filter_by(
            manuscript_id=manuscript_id
        ).all()

        # Gather statistics
        unique_keys = set(loc.citation_key for loc in locations)
        orphan_citations = [loc.citation_key for loc in locations if loc.paper_id is None]
        orphan_keys = list(set(orphan_citations))

        # Check for duplicates (same key, file, line)
        seen = set()
        duplicates = 0
        for loc in locations:
            key = (loc.citation_key, loc.file_path, loc.line_number)
            if key in seen:
                duplicates += 1
            seen.add(key)

        # Count papers with/without citation_key
        papers_cited = self.db.query(Paper).filter(
            Paper.id.in_([loc.paper_id for loc in locations if loc.paper_id])
        ).all()

        with_key = sum(1 for p in papers_cited if p.citation_key)
        without_key = sum(1 for p in papers_cited if not p.citation_key)

        # Build issues list
        issues = []
        if orphan_keys:
            issues.append(f"{len(orphan_keys)} citation keys not matched to papers")
        if duplicates:
            issues.append(f"{duplicates} duplicate citation locations found")
        if without_key:
            issues.append(f"{without_key} cited papers missing citation_key")

        return CitationCheckResult(
            manuscript_id=manuscript_id,
            total_papers_cited=len(unique_keys),
            papers_with_citation_key=with_key,
            papers_without_citation_key=without_key,
            orphan_citations=orphan_keys,
            duplicate_locations=duplicates,
            issues=issues
        )

    # ========== Citation Key Generation ==========

    def generate_citation_key(self, paper: Paper) -> str:
        """
        Generate a citation key in AuthorYearFirstWord format.

        Examples:
        - "Dameron2008Alucone" for a paper about alucone by Dameron in 2008
        - "Smith2024Machine" for a machine learning paper by Smith in 2024

        Args:
            paper: Paper to generate key for

        Returns:
            Generated citation key string
        """
        # Get first author's last name
        if paper.authors:
            # Assume name format: "First Last" or "Last, First"
            author_name = paper.authors[0].name
            if ',' in author_name:
                last_name = author_name.split(',')[0].strip()
            else:
                parts = author_name.split()
                last_name = parts[-1] if parts else "Unknown"
        else:
            last_name = "Unknown"

        # Clean last name (remove non-alphanumeric)
        last_name = re.sub(r'[^a-zA-Z]', '', last_name)

        # Get year
        year = paper.year or "XXXX"

        # Get first significant word from title
        title_words = paper.title.split()
        # Skip common words
        skip_words = {'a', 'an', 'the', 'on', 'of', 'in', 'for', 'to', 'with', 'by'}
        first_word = "Paper"
        for word in title_words:
            clean_word = re.sub(r'[^a-zA-Z]', '', word)
            if clean_word.lower() not in skip_words and len(clean_word) > 2:
                first_word = clean_word.capitalize()
                break

        return f"{last_name}{year}{first_word}"

    def suggest_citation_keys(
        self,
        papers: Optional[List[Paper]] = None
    ) -> List[Tuple[Paper, str]]:
        """
        Suggest citation keys for papers that don't have one.

        Args:
            papers: Specific papers to suggest keys for. If None, finds all without keys.

        Returns:
            List of (paper, suggested_key) tuples
        """
        if papers is None:
            papers = self.db.query(Paper).filter(Paper.citation_key.is_(None)).all()

        suggestions = []
        for paper in papers:
            suggested = self.generate_citation_key(paper)
            # Ensure uniqueness
            existing = self.db.query(Paper).filter_by(citation_key=suggested).first()
            if existing:
                # Append a letter
                for char in 'abcdefghijklmnopqrstuvwxyz':
                    candidate = f"{suggested}{char}"
                    if not self.db.query(Paper).filter_by(citation_key=candidate).first():
                        suggested = candidate
                        break
            suggestions.append((paper, suggested))

        return suggestions

    def set_citation_key(self, paper_id: int, citation_key: str) -> bool:
        """
        Set the citation key for a paper.

        Args:
            paper_id: ID of the paper
            citation_key: Citation key to set

        Returns:
            True if successful, False if paper not found or key already exists
        """
        paper = self.db.query(Paper).filter_by(id=paper_id).first()
        if not paper:
            return False

        # Check for uniqueness
        existing = self.db.query(Paper).filter_by(citation_key=citation_key).first()
        if existing and existing.id != paper_id:
            raise ValueError(f"Citation key '{citation_key}' already exists")

        paper.citation_key = citation_key
        self.db.commit()
        return True

    # ========== Citation Queries ==========

    def get_paper_citations(self, paper_id: int) -> List[CitationLocation]:
        """Get all citation locations for a specific paper."""
        return self.db.query(CitationLocation).filter_by(paper_id=paper_id).all()

    def get_citations_by_key(self, citation_key: str) -> List[CitationLocation]:
        """Get all citation locations for a citation key."""
        return self.db.query(CitationLocation).filter_by(citation_key=citation_key).all()

    def get_manuscript_citations(
        self,
        manuscript_id: int,
        include_unmatched: bool = True
    ) -> List[CitationLocation]:
        """Get all citation locations for a manuscript."""
        query = self.db.query(CitationLocation).filter_by(manuscript_id=manuscript_id)
        if not include_unmatched:
            query = query.filter(CitationLocation.paper_id.isnot(None))
        return query.all()

    # ========== Export ==========

    def export_registry(
        self,
        manuscript_id: int,
        format: str = 'json'
    ) -> str:
        """
        Export citation registry in the specified format.

        Args:
            manuscript_id: ID of the manuscript
            format: 'json' or 'csv'

        Returns:
            Exported data as string
        """
        import json
        import csv
        import io

        manuscript = self.get_manuscript(manuscript_id)
        if not manuscript:
            raise ValueError(f"Manuscript {manuscript_id} not found")

        locations = self.get_manuscript_citations(manuscript_id)

        if format == 'json':
            data = {
                "manuscript": {
                    "id": manuscript.id,
                    "name": manuscript.name,
                    "project_path": manuscript.project_path,
                    "last_scanned": str(manuscript.last_scanned) if manuscript.last_scanned else None
                },
                "citations": []
            }

            # Group by citation key
            by_key: Dict[str, List[CitationLocation]] = {}
            for loc in locations:
                if loc.citation_key not in by_key:
                    by_key[loc.citation_key] = []
                by_key[loc.citation_key].append(loc)

            for key, locs in sorted(by_key.items()):
                paper = locs[0].paper
                entry = {
                    "citation_key": key,
                    "paper_id": paper.id if paper else None,
                    "paper_title": paper.title if paper else None,
                    "total_citations": len(locs),
                    "locations": [
                        {
                            "file": loc.file_path,
                            "line": loc.line_number,
                            "context": loc.context,
                            "section": loc.section_inferred
                        }
                        for loc in locs
                    ]
                }
                data["citations"].append(entry)

            return json.dumps(data, indent=2)

        elif format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                'citation_key', 'paper_id', 'paper_title', 'file',
                'line', 'context', 'section'
            ])

            for loc in locations:
                writer.writerow([
                    loc.citation_key,
                    loc.paper.id if loc.paper else '',
                    loc.paper.title if loc.paper else '',
                    loc.file_path,
                    loc.line_number,
                    loc.context,
                    loc.section_inferred
                ])

            return output.getvalue()

        else:
            raise ValueError(f"Unsupported format: {format}")
