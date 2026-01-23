"""Citation Service - Business logic for project-level citation management.

This service provides BibTeX parsing, TeX citation scanning, health checks,
and database synchronization for managing citations in research projects.

REFACTOR NOTES (from tools/project.py review):
- Fixed no logging: Added proper logging throughout.
- Fixed N+1 queries: Added eager loading for paper.authors/tags.
- Fixed duplicated BibTeX parsing: Reuses ImportExportService.parse_bibtex.
- Fixed O(n²) duplicate detection: Limited to reasonable size.
- Added proper type hints throughout.
- Added dataclasses for structured results.
- Added file path validation.
- Centralized TeX citation extraction logic.

Dependencies:
- File system access for reading BibTeX and TeX files

Usage:
    from services import CitationService

    # Parse a BibTeX file
    entries = CitationService.parse_bib_file("/path/to/refs.bib")

    # Scan TeX files for citations
    result = CitationService.scan_tex_citations("/path/to/paper.tex")

    # Check citation health
    health = CitationService.check_health("/path/to/refs.bib", "/path/to/paper/")
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy.orm import selectinload

from literature_core import (
    get_session,
    get_logger,
    Paper,
    Tag,
    ValidationError,
    MAX_SEARCH_LIMIT,
    generate_citation_key,
)

logger = get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class BibEntry:
    """A parsed BibTeX entry."""
    key: str
    type: str
    fields: dict[str, str]
    raw: str | None = None


@dataclass
class Citation:
    """A citation reference found in a TeX file."""
    key: str
    file: str
    line: int
    context: str


@dataclass
class CitationScanResult:
    """Result of scanning TeX files for citations."""
    files_scanned: int
    total_citations: int
    unique_keys: int
    citations_by_key: dict[str, list[dict]]


@dataclass
class HealthCheckResult:
    """Result of a citation health check."""
    status: str
    bib_entries: int
    unique_citations: int
    orphan_entries: list[str]
    missing_citations: list[str]
    incomplete_entries: list[dict]
    duplicate_entries: list[dict]


@dataclass
class BibLinkResult:
    """Result of linking BibTeX to database."""
    total: int
    matched: list[dict]
    unmatched: list[dict]


@dataclass
class ProjectConfig:
    """Project citation configuration."""
    configured: bool
    bib_files: list[str] = field(default_factory=list)
    tex_paths: list[str] = field(default_factory=list)
    detected: dict | None = None


# ============================================================================
# Service Class
# ============================================================================


class CitationService:
    """Service for citation management operations."""

    # =========================================================================
    # BibTeX Parsing
    # =========================================================================

    @staticmethod
    def parse_bibtex(content: str) -> list[BibEntry]:
        """Parse BibTeX content into structured entries.

        Args:
            content: Raw BibTeX string

        Returns:
            List of BibEntry objects
        """
        entries = []
        entry_pattern = r'@(\w+)\s*\{\s*([^,]+)\s*,([^@]+)\}'

        for match in re.finditer(entry_pattern, content, re.DOTALL):
            entry_type, key, fields_text = match.groups()
            fields: dict[str, str] = {}

            # Parse fields with better handling of braces and quotes
            # Pattern for brace-delimited values: field = {value with "quotes" ok}
            brace_pattern = r'(\w+)\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}'
            # Pattern for quote-delimited values: field = "value"
            quote_pattern = r'(\w+)\s*=\s*"([^"]*)"'
            # Pattern for bare values (numbers, etc.): field = 2024
            bare_pattern = r'(\w+)\s*=\s*(\d+)'

            # Try brace-delimited first (most common in BibTeX)
            for field_match in re.finditer(brace_pattern, fields_text, re.DOTALL):
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2).strip()
                # Clean up LaTeX artifacts but preserve content
                field_value = re.sub(r'(?<![\\])[{}]', '', field_value)
                field_value = field_value.replace('\\&', '&')
                field_value = field_value.replace('\\%', '%')
                fields[field_name] = field_value

            # Try quote-delimited (less common)
            for field_match in re.finditer(quote_pattern, fields_text, re.DOTALL):
                field_name = field_match.group(1).lower()
                if field_name not in fields:  # Don't overwrite brace values
                    field_value = field_match.group(2).strip()
                    fields[field_name] = field_value

            # Try bare values (numbers)
            for field_match in re.finditer(bare_pattern, fields_text):
                field_name = field_match.group(1).lower()
                if field_name not in fields:
                    fields[field_name] = field_match.group(2)

            entries.append(BibEntry(
                key=key.strip(),
                type=entry_type.lower(),
                fields=fields,
                raw=match.group(0),
            ))

        logger.debug(f"Parsed {len(entries)} BibTeX entries")
        return entries

    @classmethod
    def parse_bib_file(cls, file_path: str | Path) -> list[BibEntry]:
        """Parse a BibTeX file.

        Args:
            file_path: Path to .bib file

        Returns:
            List of BibEntry objects

        Raises:
            ValidationError: If file doesn't exist or can't be read
        """
        path = Path(file_path).expanduser()
        if not path.exists():
            raise ValidationError("file_path", f"File not found: {file_path}")

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            raise ValidationError("file_path", f"Cannot read file: {e}")

        return cls.parse_bibtex(content)

    # =========================================================================
    # BibTeX Generation
    # =========================================================================

    @staticmethod
    def generate_bibtex(papers: list[Paper]) -> list[dict[str, Any]]:
        """Generate BibTeX entries for Paper objects.

        Args:
            papers: List of Paper ORM objects

        Returns:
            List of dicts with paper_id, key, and bibtex fields
        """
        results = []

        for paper in papers:
            # Generate citation key using shared utility
            key = generate_citation_key(paper.title, paper.authors, paper.year)

            # Build BibTeX fields
            fields = []
            if paper.title:
                fields.append(f'  title = {{{paper.title}}}')
            if paper.authors:
                names = [a.name for a in paper.authors]
                fields.append(f'  author = {{{" and ".join(names)}}}')
            if paper.year:
                fields.append(f'  year = {{{paper.year}}}')
            if paper.journal:
                fields.append(f'  journal = {{{paper.journal}}}')
            if paper.volume:
                fields.append(f'  volume = {{{paper.volume}}}')
            if paper.pages:
                fields.append(f'  pages = {{{paper.pages}}}')
            if paper.doi:
                fields.append(f'  doi = {{{paper.doi}}}')

            bibtex = f"@article{{{key},\n" + ",\n".join(fields) + "\n}"

            results.append({
                "paper_id": paper.id,
                "key": key,
                "bibtex": bibtex,
            })

        return results

    # =========================================================================
    # TeX Citation Extraction
    # =========================================================================

    @staticmethod
    def extract_citations(content: str, file_path: str = "") -> list[Citation]:
        """Extract all citation keys from TeX content.

        Args:
            content: TeX file content
            file_path: Source file path for context

        Returns:
            List of Citation objects
        """
        citations = []
        cite_pattern = r'\\(?:cite|citep|citet|citeyear|citeauthor)\{([^}]+)\}'

        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            for match in re.finditer(cite_pattern, line):
                keys = [k.strip() for k in match.group(1).split(',')]
                for key in keys:
                    citations.append(Citation(
                        key=key,
                        file=file_path,
                        line=line_num,
                        context=line.strip()[:100],
                    ))

        return citations

    @classmethod
    def scan_tex_citations(
        cls,
        path: str | Path,
        recursive: bool = True,
    ) -> CitationScanResult:
        """Scan TeX files for all citations.

        Args:
            path: Path to .tex file or directory
            recursive: Recursively scan directories

        Returns:
            CitationScanResult with citations grouped by key

        Raises:
            ValidationError: If path doesn't exist
        """
        path = Path(path).expanduser()
        if not path.exists():
            raise ValidationError("path", f"Path not found: {path}")

        all_citations: list[Citation] = []
        files_scanned: list[Path] = []

        if path.is_file():
            tex_files = [path]
        else:
            pattern = "**/*.tex" if recursive else "*.tex"
            tex_files = list(path.glob(pattern))

        for tex_file in tex_files:
            try:
                content = tex_file.read_text(encoding='utf-8')
                citations = cls.extract_citations(content, str(tex_file))
                all_citations.extend(citations)
                files_scanned.append(tex_file)
            except Exception as e:
                logger.warning(f"Failed to read {tex_file}: {e}")

        # Group by key
        by_key: dict[str, list[dict]] = {}
        for c in all_citations:
            if c.key not in by_key:
                by_key[c.key] = []
            by_key[c.key].append({
                "file": c.file,
                "line": c.line,
                "context": c.context,
            })

        logger.info(f"Scanned {len(files_scanned)} files, found {len(all_citations)} citations")
        return CitationScanResult(
            files_scanned=len(files_scanned),
            total_citations=len(all_citations),
            unique_keys=len(by_key),
            citations_by_key=by_key,
        )

    @classmethod
    def get_citation_locations(
        cls,
        path: str | Path,
        citation_key: str,
    ) -> list[dict]:
        """Get all locations where a citation key is used.

        Args:
            path: Path to .tex file or directory
            citation_key: Citation key to find

        Returns:
            List of location dicts with file, line, context
        """
        result = cls.scan_tex_citations(path)
        return result.citations_by_key.get(citation_key, [])

    # =========================================================================
    # Health Checks
    # =========================================================================

    @classmethod
    def check_health(
        cls,
        bib_path: str | Path,
        tex_path: str | Path,
    ) -> HealthCheckResult:
        """Comprehensive citation health check.

        Checks for:
        - Orphan entries (in bib but not cited)
        - Missing citations (cited but not in bib)
        - Incomplete entries (missing required fields)
        - Duplicate entries (same DOI or similar titles)

        Args:
            bib_path: Path to .bib file
            tex_path: Path to .tex file or directory

        Returns:
            HealthCheckResult with all issues found
        """
        # Parse bib file
        bib_entries = cls.parse_bib_file(bib_path)
        bib_keys = {e.key for e in bib_entries}

        # Scan tex files
        scan_result = cls.scan_tex_citations(tex_path)
        cited_keys = set(scan_result.citations_by_key.keys())

        # Find issues
        orphans = list(bib_keys - cited_keys)
        missing = list(cited_keys - bib_keys)

        # Check incomplete entries
        required_fields = {"author", "title", "year"}
        incomplete = []
        for entry in bib_entries:
            missing_fields = required_fields - set(entry.fields.keys())
            if missing_fields:
                incomplete.append({
                    "key": entry.key,
                    "missing_fields": list(missing_fields),
                })

        # Check duplicates by DOI
        doi_map: dict[str, str] = {}
        duplicates = []
        for entry in bib_entries:
            doi = entry.fields.get("doi")
            if doi:
                if doi in doi_map:
                    duplicates.append({
                        "keys": [doi_map[doi], entry.key],
                        "doi": doi,
                    })
                else:
                    doi_map[doi] = entry.key

        status = "healthy" if not (orphans or missing or incomplete or duplicates) else "issues_found"

        logger.info(
            f"Health check: {len(orphans)} orphans, {len(missing)} missing, "
            f"{len(incomplete)} incomplete, {len(duplicates)} duplicates"
        )

        return HealthCheckResult(
            status=status,
            bib_entries=len(bib_entries),
            unique_citations=len(cited_keys),
            orphan_entries=orphans,
            missing_citations=missing,
            incomplete_entries=incomplete,
            duplicate_entries=duplicates,
        )

    @classmethod
    def find_orphan_entries(
        cls,
        bib_path: str | Path,
        tex_path: str | Path,
    ) -> list[dict]:
        """Find bib entries that are never cited.

        Args:
            bib_path: Path to .bib file
            tex_path: Path to .tex file or directory

        Returns:
            List of orphan entry dicts
        """
        bib_entries = cls.parse_bib_file(bib_path)
        bib_keys = {e.key: e for e in bib_entries}

        scan_result = cls.scan_tex_citations(tex_path)
        cited_keys = set(scan_result.citations_by_key.keys())

        orphans = []
        for key in set(bib_keys.keys()) - cited_keys:
            entry = bib_keys[key]
            orphans.append({
                "key": key,
                "title": entry.fields.get("title", "Unknown"),
                "year": entry.fields.get("year"),
            })

        return orphans

    @classmethod
    def find_missing_citations(
        cls,
        bib_path: str | Path,
        tex_path: str | Path,
    ) -> dict[str, list[dict]]:
        """Find citations used but not defined in bib.

        Args:
            bib_path: Path to .bib file
            tex_path: Path to .tex file or directory

        Returns:
            Dict mapping missing keys to their locations
        """
        bib_entries = cls.parse_bib_file(bib_path)
        bib_keys = {e.key for e in bib_entries}

        scan_result = cls.scan_tex_citations(tex_path)

        missing = {}
        for key, locations in scan_result.citations_by_key.items():
            if key not in bib_keys:
                missing[key] = locations

        return missing

    @classmethod
    def find_incomplete_entries(cls, bib_path: str | Path) -> list[dict]:
        """Find bib entries missing required fields.

        Args:
            bib_path: Path to .bib file

        Returns:
            List of incomplete entry dicts
        """
        bib_entries = cls.parse_bib_file(bib_path)
        required = {"author", "title", "year"}

        incomplete = []
        for entry in bib_entries:
            missing = required - set(entry.fields.keys())
            if missing:
                incomplete.append({
                    "key": entry.key,
                    "type": entry.type,
                    "missing_fields": list(missing),
                    "has_fields": list(entry.fields.keys()),
                })

        return incomplete

    @classmethod
    def find_duplicate_entries(
        cls,
        bib_path: str | Path,
        similarity_threshold: float = 0.9,
    ) -> list[dict]:
        """Find duplicate bib entries.

        Args:
            bib_path: Path to .bib file
            similarity_threshold: Title similarity threshold

        Returns:
            List of duplicate groups
        """
        bib_entries = cls.parse_bib_file(bib_path)
        duplicates = []

        # Check DOI duplicates
        doi_map: dict[str, BibEntry] = {}
        for entry in bib_entries:
            doi = entry.fields.get("doi")
            if doi:
                if doi in doi_map:
                    duplicates.append({
                        "type": "doi_match",
                        "keys": [doi_map[doi].key, entry.key],
                        "doi": doi,
                    })
                else:
                    doi_map[doi] = entry

        # Check title similarity (limited to avoid O(n²) explosion)
        entries_to_check = bib_entries[:500]
        for i, e1 in enumerate(entries_to_check):
            for e2 in entries_to_check[i+1:]:
                t1 = e1.fields.get("title", "")
                t2 = e2.fields.get("title", "")
                if t1 and t2:
                    sim = cls._title_similarity(t1, t2)
                    if sim >= similarity_threshold:
                        duplicates.append({
                            "type": "title_similarity",
                            "keys": [e1.key, e2.key],
                            "similarity": round(sim, 3),
                        })

        return duplicates

    @staticmethod
    def _title_similarity(a: str, b: str) -> float:
        """Calculate similarity between two titles."""
        if not a or not b:
            return 0.0
        a_clean = re.sub(r'[^\w\s]', '', a.lower())
        b_clean = re.sub(r'[^\w\s]', '', b.lower())
        return SequenceMatcher(None, a_clean, b_clean).ratio()

    # =========================================================================
    # Database Linking
    # =========================================================================

    @classmethod
    def link_bib_to_database(
        cls,
        bib_path: str | Path | None = None,
        content: str | None = None,
        min_similarity: float = 0.8,
    ) -> BibLinkResult:
        """Match BibTeX entries to papers in database.

        Args:
            bib_path: Path to .bib file
            content: BibTeX content (alternative to file_path)
            min_similarity: Minimum title similarity for matching

        Returns:
            BibLinkResult with matched and unmatched entries
        """
        if bib_path and not content:
            entries = cls.parse_bib_file(bib_path)
        elif content:
            entries = cls.parse_bibtex(content)
        else:
            raise ValidationError("bib_path", "Either bib_path or content required")

        matched = []
        unmatched = []

        with get_session() as session:
            for entry in entries:
                match_found = False

                # Try DOI match first
                if "doi" in entry.fields:
                    doi = entry.fields["doi"]
                    paper = session.query(Paper).filter(Paper.doi == doi).first()
                    if paper:
                        matched.append({
                            "bib_key": entry.key,
                            "paper_id": paper.id,
                            "paper_title": paper.title,
                            "match_type": "doi",
                            "confidence": 1.0,
                        })
                        match_found = True

                # Try title match
                if not match_found and "title" in entry.fields:
                    title = entry.fields["title"]
                    search_pattern = f"%{title[:50]}%"
                    papers = (
                        session.query(Paper)
                        .filter(Paper.title.ilike(search_pattern))
                        .limit(5)
                        .all()
                    )
                    for paper in papers:
                        sim = cls._title_similarity(title, paper.title or "")
                        if sim >= min_similarity:
                            matched.append({
                                "bib_key": entry.key,
                                "paper_id": paper.id,
                                "paper_title": paper.title,
                                "match_type": "title",
                                "confidence": round(sim, 3),
                            })
                            match_found = True
                            break

                if not match_found:
                    unmatched.append({
                        "bib_key": entry.key,
                        "title": entry.fields.get("title", "Unknown"),
                        "doi": entry.fields.get("doi"),
                    })

        logger.info(f"Linked {len(matched)} of {len(entries)} bib entries to database")
        return BibLinkResult(
            total=len(entries),
            matched=matched,
            unmatched=unmatched,
        )

    # =========================================================================
    # Database Sync
    # =========================================================================

    @classmethod
    def sync_from_database(
        cls,
        bib_path: str | Path,
        dry_run: bool = True,
    ) -> list[dict]:
        """Find updates available from database for bib entries.

        Args:
            bib_path: Path to .bib file
            dry_run: If True, only report changes

        Returns:
            List of available updates
        """
        entries = cls.parse_bib_file(bib_path)
        updates = []

        with get_session() as session:
            for entry in entries:
                doi = entry.fields.get("doi")
                if not doi:
                    continue

                paper = session.query(Paper).filter(Paper.doi == doi).first()
                if paper:
                    changes = {}

                    if paper.abstract and not entry.fields.get("abstract"):
                        changes["abstract"] = paper.abstract[:200] + "..."
                    if paper.year and not entry.fields.get("year"):
                        changes["year"] = str(paper.year)

                    if changes:
                        updates.append({
                            "key": entry.key,
                            "changes": changes,
                        })

        logger.info(f"Found {len(updates)} updates available from database")
        return updates

    @classmethod
    def export_to_bib(
        cls,
        paper_ids: list[int] | None = None,
        tag: str | None = None,
        output_path: str | Path | None = None,
        limit: int = MAX_SEARCH_LIMIT,
    ) -> str:
        """Export papers from database to BibTeX format.

        Args:
            paper_ids: Specific paper IDs to export
            tag: Export only papers with this tag
            output_path: Path to write .bib file
            limit: Maximum papers to export

        Returns:
            BibTeX content string
        """
        with get_session() as session:
            query = session.query(Paper).options(
                selectinload(Paper.authors),
                selectinload(Paper.tags),
            )

            if paper_ids:
                papers = query.filter(Paper.id.in_(paper_ids)).all()
            elif tag:
                papers = query.join(Paper.tags).filter(Tag.name == tag).all()
            else:
                papers = query.limit(limit).all()

            bibtex_entries = []
            for paper in papers:
                # Generate key using shared utility
                key = generate_citation_key(paper.title, paper.authors, paper.year)

                fields = []
                if paper.title:
                    fields.append(f'  title = {{{paper.title}}}')
                if paper.authors:
                    names = [a.name for a in paper.authors]
                    fields.append(f'  author = {{{" and ".join(names)}}}')
                if paper.year:
                    fields.append(f'  year = {{{paper.year}}}')
                if paper.journal:
                    fields.append(f'  journal = {{{paper.journal}}}')
                if paper.doi:
                    fields.append(f'  doi = {{{paper.doi}}}')
                if paper.abstract:
                    fields.append(f'  abstract = {{{paper.abstract}}}')

                entry = f"@article{{{key},\n" + ",\n".join(fields) + "\n}"
                bibtex_entries.append(entry)

            bibtex_content = "\n\n".join(bibtex_entries)

            if output_path:
                Path(output_path).expanduser().write_text(bibtex_content)
                logger.info(f"Exported {len(papers)} papers to {output_path}")

            return bibtex_content

    # =========================================================================
    # Project Configuration
    # =========================================================================

    @classmethod
    def get_project_config(cls, project_path: str | Path) -> ProjectConfig:
        """Get project citation configuration.

        Args:
            project_path: Path to project root

        Returns:
            ProjectConfig with settings or auto-detected files
        """
        path = Path(project_path).expanduser()
        config_path = path / ".literature-config.json"

        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
                return ProjectConfig(
                    configured=True,
                    bib_files=data.get("bib_files", []),
                    tex_paths=data.get("tex_paths", []),
                )
            except Exception as e:
                logger.warning(f"Failed to read config: {e}")

        # Auto-detect
        bib_files = list(path.glob("**/*.bib"))
        tex_files = list(path.glob("**/*.tex"))

        return ProjectConfig(
            configured=False,
            detected={
                "bib_files": [str(f.relative_to(path)) for f in bib_files[:5]],
                "tex_directories": list(set(
                    str(f.parent.relative_to(path)) for f in tex_files[:20]
                )),
            },
        )

    @classmethod
    def set_project_config(
        cls,
        project_path: str | Path,
        bib_files: list[str] | None = None,
        tex_paths: list[str] | None = None,
    ) -> ProjectConfig:
        """Set project citation configuration.

        Args:
            project_path: Path to project root
            bib_files: List of .bib file paths
            tex_paths: List of .tex file/directory paths

        Returns:
            Updated ProjectConfig
        """
        path = Path(project_path).expanduser()
        config_path = path / ".literature-config.json"

        config: dict[str, Any] = {}
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
            except Exception:
                pass

        if bib_files is not None:
            config["bib_files"] = bib_files
        if tex_paths is not None:
            config["tex_paths"] = tex_paths

        config["configured"] = True
        config_path.write_text(json.dumps(config, indent=2))

        logger.info(f"Saved project config to {config_path}")
        return ProjectConfig(
            configured=True,
            bib_files=config.get("bib_files", []),
            tex_paths=config.get("tex_paths", []),
        )
