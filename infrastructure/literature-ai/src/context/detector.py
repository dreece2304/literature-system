"""
Context detector for manuscript monitoring.

Watches for manuscript files and maintains current writing context
for intelligent citation suggestions.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from loguru import logger

from src.context.parser import ManuscriptParser
from src.context.tracker import get_context_tracker, WritingContext


class ContextDetector:
    """
    Detects and monitors writing context from manuscript files.

    Features:
    - File watching (manual refresh for now)
    - Automatic structure parsing
    - Context updates
    - Multi-manuscript support
    """

    def __init__(self):
        """Initialize context detector."""
        self.parser = ManuscriptParser()
        self.tracker = get_context_tracker()

        # File watching state
        self.watched_files: Dict[str, datetime] = {}
        self.watching = False

        logger.info("ContextDetector initialized")

    def load_manuscript(
        self,
        manuscript_path: Path,
        set_active: bool = True,
    ) -> Optional[WritingContext]:
        """
        Load and parse a manuscript.

        Args:
            manuscript_path: Path to manuscript file
            set_active: Set as active manuscript

        Returns:
            WritingContext or None if parsing fails
        """
        if not manuscript_path.exists():
            logger.error(f"Manuscript not found: {manuscript_path}")
            return None

        logger.info(f"Loading manuscript: {manuscript_path}")

        # Parse manuscript
        structure = self.parser.parse_file(manuscript_path)
        if not structure:
            logger.error(f"Failed to parse manuscript: {manuscript_path}")
            return None

        # Add to tracker
        context = self.tracker.add_manuscript(manuscript_path, structure)

        # Set as active if requested
        if set_active:
            self.tracker.set_active_manuscript(manuscript_path)

        # Start watching this file
        self.watched_files[str(manuscript_path.resolve())] = manuscript_path.stat().st_mtime

        logger.info(
            f"Loaded manuscript: {structure.title} "
            f"({len(structure.sections)} sections, "
            f"{structure.total_words} words)"
        )

        return context

    def refresh_manuscript(self, manuscript_path: Path) -> bool:
        """
        Refresh manuscript structure (reparse).

        Args:
            manuscript_path: Path to manuscript

        Returns:
            True if successful
        """
        logger.debug(f"Refreshing manuscript: {manuscript_path}")

        structure = self.parser.parse_file(manuscript_path)
        if not structure:
            return False

        self.tracker.update_manuscript(manuscript_path, structure)
        return True

    def check_for_updates(self) -> List[Path]:
        """
        Check watched files for updates.

        Returns:
            List of updated file paths
        """
        updated_files = []

        for file_str, last_mtime in list(self.watched_files.items()):
            file_path = Path(file_str)

            if not file_path.exists():
                # File deleted
                logger.warning(f"Watched file deleted: {file_path}")
                del self.watched_files[file_str]
                self.tracker.remove_manuscript(file_path)
                continue

            current_mtime = file_path.stat().st_mtime

            if current_mtime > last_mtime:
                # File modified
                logger.info(f"File modified: {file_path.name}")
                if self.refresh_manuscript(file_path):
                    updated_files.append(file_path)
                    self.watched_files[file_str] = current_mtime

        return updated_files

    def set_active_section(self, section_title: str):
        """
        Set the active section in the current manuscript.

        Args:
            section_title: Section title
        """
        self.tracker.update_active_section(section_title)

    def update_cursor_position(self, line_num: int):
        """
        Update cursor position in active manuscript.

        Args:
            line_num: Current line number
        """
        self.tracker.update_cursor_position(line_num)

    def update_recent_text(self, text: str):
        """
        Update recent text being edited.

        Args:
            text: Recent text content
        """
        self.tracker.update_recent_text(text)

    def set_writing_goal(self, goal: str):
        """
        Set writing goal for active manuscript.

        Args:
            goal: Writing goal description
        """
        self.tracker.set_writing_goal(goal)

    def set_research_topics(self, topics: List[str]):
        """
        Set research topics for active manuscript.

        Args:
            topics: List of research topics/keywords
        """
        self.tracker.set_research_topics(topics)

    def get_context(self) -> Optional[WritingContext]:
        """
        Get current writing context.

        Returns:
            WritingContext or None
        """
        return self.tracker.get_active_context()

    def get_context_for_citation(self) -> Optional[Dict[str, Any]]:
        """
        Get context suitable for citation suggestions.

        Returns:
            Context dictionary with relevant information
        """
        context = self.get_context()
        if not context:
            return None

        section = context.get_active_section_obj()

        return {
            "manuscript_title": context.structure.title,
            "active_section": context.active_section,
            "section_content": section.content if section else "",
            "recent_text": context.recent_text,
            "existing_citations": context.get_existing_citations(),
            "section_citations": context.get_section_citations(),
            "writing_goal": context.writing_goal,
            "research_topics": context.research_topics,
        }

    def detect_section_from_text(self, text: str) -> Optional[str]:
        """
        Detect which section text belongs to (fuzzy matching).

        Args:
            text: Text to match

        Returns:
            Section title or None
        """
        context = self.get_context()
        if not context:
            return None

        # Simple heuristic: check if text appears in any section
        text_lower = text.lower()

        for section in context.structure.sections:
            if text_lower in section.content.lower():
                return section.title

        return None

    def suggest_section_for_claim(self, claim: str) -> Optional[str]:
        """
        Suggest which section a claim should go in.

        Args:
            claim: Claim or statement text

        Returns:
            Suggested section title
        """
        context = self.get_context()
        if not context:
            return None

        # Simple heuristic based on keywords
        claim_lower = claim.lower()

        # Introduction keywords
        if any(
            kw in claim_lower
            for kw in ["introduce", "overview", "motivation", "problem"]
        ):
            intro = context.structure.get_section_by_title("introduction")
            if intro:
                return intro.title

        # Methods keywords
        if any(
            kw in claim_lower
            for kw in ["method", "approach", "algorithm", "implementation"]
        ):
            methods = (
                context.structure.get_section_by_title("methods")
                or context.structure.get_section_by_title("methodology")
            )
            if methods:
                return methods.title

        # Results keywords
        if any(kw in claim_lower for kw in ["result", "finding", "experiment"]):
            results = context.structure.get_section_by_title("results")
            if results:
                return results.title

        # Discussion keywords
        if any(
            kw in claim_lower
            for kw in ["discuss", "implication", "limitation", "future"]
        ):
            discussion = context.structure.get_section_by_title("discussion")
            if discussion:
                return discussion.title

        # Related work keywords
        if any(kw in claim_lower for kw in ["prior", "previous", "related", "work"]):
            related = (
                context.structure.get_section_by_title("related work")
                or context.structure.get_section_by_title("literature review")
            )
            if related:
                return related.title

        # Default to active section
        return context.active_section

    def get_manuscript_outline(self) -> Optional[Dict[str, Any]]:
        """
        Get manuscript outline.

        Returns:
            Outline dictionary with sections and word counts
        """
        context = self.get_context()
        if not context:
            return None

        sections_info = []
        for section in context.structure.sections:
            sections_info.append({
                "title": section.title,
                "level": section.level,
                "word_count": section.word_count,
                "citations": len(section.citations),
            })

        return {
            "title": context.structure.title,
            "total_words": context.structure.total_words,
            "total_sections": len(context.structure.sections),
            "sections": sections_info,
        }

    def start_watching(self):
        """Start file watching (placeholder for async implementation)."""
        self.watching = True
        logger.info("File watching enabled")

    def stop_watching(self):
        """Stop file watching."""
        self.watching = False
        logger.info("File watching disabled")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get detector statistics.

        Returns:
            Statistics dictionary
        """
        tracker_stats = self.tracker.get_stats()

        return {
            **tracker_stats,
            "watched_files": len(self.watched_files),
            "watching": self.watching,
        }


# Global singleton instance
_context_detector: Optional[ContextDetector] = None


def get_context_detector() -> ContextDetector:
    """
    Get global ContextDetector instance (singleton).

    Returns:
        Shared ContextDetector instance
    """
    global _context_detector

    if _context_detector is None:
        _context_detector = ContextDetector()

    return _context_detector


def reset_context_detector():
    """Reset global context detector (useful for testing)."""
    global _context_detector
    _context_detector = None
