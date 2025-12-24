"""
Manuscript parser for extracting structure and context.

Supports LaTeX and Markdown documents, extracting sections, citations,
and current writing context.
"""

import re
from typing import List, Optional
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger


@dataclass
class Section:
    """Represents a document section."""

    level: int
    title: str
    content: str
    start_line: int
    end_line: int
    citations: List[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        """Count words in section content."""
        return len(self.content.split())


@dataclass
class ManuscriptStructure:
    """Represents the structure of a manuscript."""

    title: str
    abstract: str
    sections: List[Section]
    all_citations: List[str]
    document_type: str  # 'latex' or 'markdown'

    @property
    def total_words(self) -> int:
        """Total word count."""
        return sum(s.word_count for s in self.sections)

    def get_section_by_title(self, title: str) -> Optional[Section]:
        """Get section by title (case-insensitive)."""
        title_lower = title.lower()
        for section in self.sections:
            if section.title.lower() == title_lower:
                return section
        return None

    def get_sections_by_level(self, level: int) -> List[Section]:
        """Get all sections at a specific level."""
        return [s for s in self.sections if s.level == level]


class ManuscriptParser:
    """
    Parser for LaTeX and Markdown manuscripts.

    Features:
    - Section extraction
    - Citation detection
    - Title and abstract extraction
    - Line number tracking
    """

    def __init__(self):
        """Initialize parser."""
        logger.debug("ManuscriptParser initialized")

    def parse_file(self, file_path: Path) -> Optional[ManuscriptStructure]:
        """
        Parse a manuscript file.

        Args:
            file_path: Path to manuscript file

        Returns:
            ManuscriptStructure or None if parsing fails
        """
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None

        # Determine document type
        suffix = file_path.suffix.lower()
        if suffix == ".tex":
            return self.parse_latex(content)
        elif suffix in [".md", ".markdown"]:
            return self.parse_markdown(content)
        else:
            logger.warning(f"Unsupported file type: {suffix}")
            return None

    def parse_latex(self, content: str) -> ManuscriptStructure:
        """
        Parse LaTeX document.

        Args:
            content: LaTeX document content

        Returns:
            ManuscriptStructure
        """
        lines = content.split("\n")

        # Extract title
        title = self._extract_latex_title(content)

        # Extract abstract
        abstract = self._extract_latex_abstract(content)

        # Extract sections
        sections = self._extract_latex_sections(lines)

        # Extract all citations
        all_citations = self._extract_latex_citations(content)

        logger.info(
            f"Parsed LaTeX: {len(sections)} sections, "
            f"{len(all_citations)} citations"
        )

        return ManuscriptStructure(
            title=title,
            abstract=abstract,
            sections=sections,
            all_citations=all_citations,
            document_type="latex",
        )

    def parse_markdown(self, content: str) -> ManuscriptStructure:
        """
        Parse Markdown document.

        Args:
            content: Markdown document content

        Returns:
            ManuscriptStructure
        """
        lines = content.split("\n")

        # Extract title (first # heading)
        title = self._extract_markdown_title(lines)

        # Extract abstract (section labeled "Abstract")
        abstract = self._extract_markdown_abstract(lines)

        # Extract sections
        sections = self._extract_markdown_sections(lines)

        # Extract citations (various formats)
        all_citations = self._extract_markdown_citations(content)

        logger.info(
            f"Parsed Markdown: {len(sections)} sections, "
            f"{len(all_citations)} citations"
        )

        return ManuscriptStructure(
            title=title,
            abstract=abstract,
            sections=sections,
            all_citations=all_citations,
            document_type="markdown",
        )

    def _extract_latex_title(self, content: str) -> str:
        """Extract title from LaTeX."""
        match = re.search(r"\\title\{([^}]+)\}", content)
        if match:
            return match.group(1).strip()
        return "Untitled"

    def _extract_latex_abstract(self, content: str) -> str:
        """Extract abstract from LaTeX."""
        match = re.search(
            r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
            content,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        return ""

    def _extract_latex_sections(self, lines: List[str]) -> List[Section]:
        """Extract sections from LaTeX."""
        sections = []
        current_section = None
        current_content = []

        # Patterns for different section levels
        section_patterns = [
            (r"\\section\{([^}]+)\}", 1),
            (r"\\subsection\{([^}]+)\}", 2),
            (r"\\subsubsection\{([^}]+)\}", 3),
        ]

        for line_num, line in enumerate(lines, 1):
            # Check if this is a section heading
            is_section = False
            for pattern, level in section_patterns:
                match = re.search(pattern, line)
                if match:
                    # Save previous section
                    if current_section:
                        content_text = "\n".join(current_content)
                        current_section.content = content_text
                        current_section.end_line = line_num - 1
                        current_section.citations = self._extract_latex_citations(
                            content_text
                        )
                        sections.append(current_section)

                    # Start new section
                    current_section = Section(
                        level=level,
                        title=match.group(1).strip(),
                        content="",
                        start_line=line_num,
                        end_line=line_num,
                    )
                    current_content = []
                    is_section = True
                    break

            # Add line to current section content
            if not is_section and current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            content_text = "\n".join(current_content)
            current_section.content = content_text
            current_section.end_line = len(lines)
            current_section.citations = self._extract_latex_citations(content_text)
            sections.append(current_section)

        return sections

    def _extract_latex_citations(self, content: str) -> List[str]:
        """Extract citation keys from LaTeX."""
        # Match \cite{key}, \citep{key}, \citet{key}, etc.
        pattern = r"\\cite[a-z]*\{([^}]+)\}"
        matches = re.findall(pattern, content)

        # Split comma-separated citations
        citations = []
        for match in matches:
            keys = [k.strip() for k in match.split(",")]
            citations.extend(keys)

        return list(set(citations))  # Remove duplicates

    def _extract_markdown_title(self, lines: List[str]) -> str:
        """Extract title from Markdown."""
        for line in lines:
            if line.startswith("# "):
                return line[2:].strip()
        return "Untitled"

    def _extract_markdown_abstract(self, lines: List[str]) -> str:
        """Extract abstract from Markdown."""
        in_abstract = False
        abstract_lines = []

        for line in lines:
            # Check for Abstract heading
            if re.match(r"#+\s*Abstract", line, re.IGNORECASE):
                in_abstract = True
                continue

            # Stop at next heading
            if in_abstract and line.startswith("#"):
                break

            if in_abstract:
                abstract_lines.append(line)

        return "\n".join(abstract_lines).strip()

    def _extract_markdown_sections(self, lines: List[str]) -> List[Section]:
        """Extract sections from Markdown."""
        sections = []
        current_section = None
        current_content = []

        for line_num, line in enumerate(lines, 1):
            # Check if this is a heading
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)

            if heading_match:
                # Save previous section
                if current_section:
                    content_text = "\n".join(current_content)
                    current_section.content = content_text
                    current_section.end_line = line_num - 1
                    current_section.citations = self._extract_markdown_citations(
                        content_text
                    )
                    sections.append(current_section)

                # Start new section
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                current_section = Section(
                    level=level,
                    title=title,
                    content="",
                    start_line=line_num,
                    end_line=line_num,
                )
                current_content = []

            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            content_text = "\n".join(current_content)
            current_section.content = content_text
            current_section.end_line = len(lines)
            current_section.citations = self._extract_markdown_citations(content_text)
            sections.append(current_section)

        return sections

    def _extract_markdown_citations(self, content: str) -> List[str]:
        """Extract citations from Markdown."""
        citations = []

        # Format 1: [AuthorYear]
        pattern1 = r"\[([A-Z][a-z]+\d{4}[a-z]?)\]"
        matches1 = re.findall(pattern1, content)
        citations.extend(matches1)

        # Format 2: [@citekey]
        pattern2 = r"\[@([a-z0-9_-]+)\]"
        matches2 = re.findall(pattern2, content)
        citations.extend(matches2)

        return list(set(citations))  # Remove duplicates
