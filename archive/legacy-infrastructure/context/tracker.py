"""
Context tracking for active manuscripts.

Maintains state about what the user is currently working on,
including active section, recent edits, and writing goals.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger

from src.context.parser import ManuscriptStructure, Section


@dataclass
class WritingContext:
    """Represents the current writing context."""

    manuscript_path: Path
    structure: ManuscriptStructure
    active_section: Optional[str] = None  # Section title
    cursor_line: Optional[int] = None
    recent_text: str = ""  # Last few paragraphs
    writing_goal: Optional[str] = None  # User-specified goal
    research_topics: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def get_active_section_obj(self) -> Optional[Section]:
        """Get the active Section object."""
        if not self.active_section:
            return None
        return self.structure.get_section_by_title(self.active_section)

    def get_context_text(self, window_lines: int = 50) -> str:
        """
        Get context text around cursor position.

        Args:
            window_lines: Number of lines to include

        Returns:
            Context text
        """
        if not self.cursor_line:
            return self.recent_text

        # Get section at cursor
        section = self._find_section_at_line(self.cursor_line)
        if section:
            return section.content[:1000]  # First 1000 chars

        return self.recent_text

    def _find_section_at_line(self, line_num: int) -> Optional[Section]:
        """Find section containing the given line number."""
        for section in self.structure.sections:
            if section.start_line <= line_num <= section.end_line:
                return section
        return None

    def get_existing_citations(self) -> List[str]:
        """Get all citations in the manuscript."""
        return self.structure.all_citations

    def get_section_citations(self) -> List[str]:
        """Get citations in the active section."""
        section = self.get_active_section_obj()
        if section:
            return section.citations
        return []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "manuscript_path": str(self.manuscript_path),
            "title": self.structure.title,
            "active_section": self.active_section,
            "cursor_line": self.cursor_line,
            "writing_goal": self.writing_goal,
            "research_topics": self.research_topics,
            "total_sections": len(self.structure.sections),
            "total_words": self.structure.total_words,
            "total_citations": len(self.structure.all_citations),
            "last_updated": self.last_updated.isoformat(),
        }


class ContextTracker:
    """
    Tracks writing context across multiple manuscripts.

    Features:
    - Multiple manuscript tracking
    - Context switching
    - Auto-save context state
    - Writing session management
    """

    def __init__(self):
        """Initialize context tracker."""
        self.contexts: Dict[str, WritingContext] = {}
        self.active_manuscript: Optional[str] = None

        logger.info("ContextTracker initialized")

    def add_manuscript(
        self,
        manuscript_path: Path,
        structure: ManuscriptStructure,
    ) -> WritingContext:
        """
        Add a manuscript to tracking.

        Args:
            manuscript_path: Path to manuscript
            structure: Parsed manuscript structure

        Returns:
            WritingContext object
        """
        path_str = str(manuscript_path.resolve())

        context = WritingContext(
            manuscript_path=manuscript_path,
            structure=structure,
        )

        self.contexts[path_str] = context
        logger.info(f"Added manuscript to tracking: {manuscript_path.name}")

        return context

    def update_manuscript(
        self,
        manuscript_path: Path,
        structure: ManuscriptStructure,
    ):
        """
        Update manuscript structure.

        Args:
            manuscript_path: Path to manuscript
            structure: Updated manuscript structure
        """
        path_str = str(manuscript_path.resolve())

        if path_str in self.contexts:
            self.contexts[path_str].structure = structure
            self.contexts[path_str].last_updated = datetime.utcnow()
            logger.debug(f"Updated manuscript: {manuscript_path.name}")
        else:
            self.add_manuscript(manuscript_path, structure)

    def set_active_manuscript(self, manuscript_path: Path):
        """
        Set the active manuscript.

        Args:
            manuscript_path: Path to manuscript
        """
        path_str = str(manuscript_path.resolve())

        if path_str not in self.contexts:
            logger.warning(f"Manuscript not tracked: {manuscript_path}")
            return

        self.active_manuscript = path_str
        logger.info(f"Active manuscript: {manuscript_path.name}")

    def get_active_context(self) -> Optional[WritingContext]:
        """
        Get the active writing context.

        Returns:
            WritingContext or None
        """
        if not self.active_manuscript:
            return None

        return self.contexts.get(self.active_manuscript)

    def get_context(self, manuscript_path: Path) -> Optional[WritingContext]:
        """
        Get context for a specific manuscript.

        Args:
            manuscript_path: Path to manuscript

        Returns:
            WritingContext or None
        """
        path_str = str(manuscript_path.resolve())
        return self.contexts.get(path_str)

    def update_active_section(self, section_title: str):
        """
        Update the active section.

        Args:
            section_title: Section title
        """
        context = self.get_active_context()
        if context:
            context.active_section = section_title
            context.last_updated = datetime.utcnow()
            logger.debug(f"Active section: {section_title}")

    def update_cursor_position(self, line_num: int):
        """
        Update cursor position.

        Args:
            line_num: Line number
        """
        context = self.get_active_context()
        if context:
            context.cursor_line = line_num
            context.last_updated = datetime.utcnow()

    def update_recent_text(self, text: str):
        """
        Update recent text.

        Args:
            text: Recent text content
        """
        context = self.get_active_context()
        if context:
            context.recent_text = text
            context.last_updated = datetime.utcnow()

    def set_writing_goal(self, goal: str):
        """
        Set writing goal for active manuscript.

        Args:
            goal: Writing goal description
        """
        context = self.get_active_context()
        if context:
            context.writing_goal = goal
            logger.info(f"Writing goal set: {goal}")

    def set_research_topics(self, topics: List[str]):
        """
        Set research topics for active manuscript.

        Args:
            topics: List of research topics
        """
        context = self.get_active_context()
        if context:
            context.research_topics = topics
            logger.info(f"Research topics set: {topics}")

    def remove_manuscript(self, manuscript_path: Path):
        """
        Remove a manuscript from tracking.

        Args:
            manuscript_path: Path to manuscript
        """
        path_str = str(manuscript_path.resolve())

        if path_str in self.contexts:
            del self.contexts[path_str]
            logger.info(f"Removed manuscript: {manuscript_path.name}")

            # Clear active if this was it
            if self.active_manuscript == path_str:
                self.active_manuscript = None

    def list_manuscripts(self) -> List[Dict[str, Any]]:
        """
        List all tracked manuscripts.

        Returns:
            List of manuscript info dictionaries
        """
        return [ctx.to_dict() for ctx in self.contexts.values()]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get tracking statistics.

        Returns:
            Statistics dictionary
        """
        active_context = self.get_active_context()

        return {
            "total_manuscripts": len(self.contexts),
            "active_manuscript": (
                Path(self.active_manuscript).name if self.active_manuscript else None
            ),
            "active_context": active_context.to_dict() if active_context else None,
        }


# Global singleton instance
_context_tracker: Optional[ContextTracker] = None


def get_context_tracker() -> ContextTracker:
    """
    Get global ContextTracker instance (singleton).

    Returns:
        Shared ContextTracker instance
    """
    global _context_tracker

    if _context_tracker is None:
        _context_tracker = ContextTracker()

    return _context_tracker


def reset_context_tracker():
    """Reset global context tracker (useful for testing)."""
    global _context_tracker
    _context_tracker = None
