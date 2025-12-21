"""
Writer Agent for intelligent citation suggestions.

Provides context-aware citation recommendations, outline expansion,
and writing assistance for academic manuscripts.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

from src.agents.base import BaseAgent
from src.services.search_service import get_search_service, SearchResult
from src.services.citation_service import get_citation_service
from src.context.detector import get_context_detector


@dataclass
class CitationSuggestion:
    """Represents a citation suggestion."""

    paper_id: str
    title: str
    authors: str
    year: Optional[int]
    relevance_score: float
    contribution: str  # What this paper adds
    integration_suggestion: str  # How to incorporate
    quote_suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "relevance_score": round(self.relevance_score, 4),
            "contribution": self.contribution,
            "integration_suggestion": self.integration_suggestion,
            "quote_suggestion": self.quote_suggestion,
        }


class WriterAgent(BaseAgent):
    """
    Agent for writing assistance and citation suggestions.

    Features:
    - Context-aware citation recommendations
    - Outline expansion with citations
    - Missing citation detection
    - Citation integration suggestions
    """

    def __init__(self):
        """Initialize writer agent."""
        super().__init__("writer")

        self.search_service = get_search_service()
        self.citation_service = get_citation_service()
        self.context_detector = get_context_detector()

        logger.info("WriterAgent initialized")

    async def suggest_citations(
        self,
        text: str,
        claim: Optional[str] = None,
        n: int = 5,
        use_context: bool = True,
    ) -> List[CitationSuggestion]:
        """
        Suggest citations for given text.

        Args:
            text: Text needing citations
            claim: Specific claim to support (optional)
            n: Number of suggestions
            use_context: Use manuscript context if available

        Returns:
            List of CitationSuggestion objects
        """
        logger.info(f"Suggesting citations for text (n={n})")

        # Get context if available
        context_data = None
        if use_context:
            context_data = self.context_detector.get_context_for_citation()

        # Search for relevant papers
        search_query = claim if claim else text
        search_results = self.search_service.search(
            query=search_query,
            top_k=n * 2,  # Get extra for filtering
        )

        if not search_results:
            logger.warning("No papers found for citation suggestion")
            return []

        # Format papers for LLM
        papers_text = self._format_papers_for_llm(search_results[:10])

        # Build prompt
        prompt = self._format_prompt(
            "citation_suggestion",
            section=context_data.get("active_section", "Unknown") if context_data else "Unknown",
            text=text,
            claim=claim or "Support the statements in this text",
            papers=papers_text,
            n=n,
        )

        # Get LLM suggestions
        try:
            response = await self._generate_json(prompt)

            suggestions = response.get("suggestions", [])

            # Convert to CitationSuggestion objects
            citation_suggestions = []
            for sug in suggestions[:n]:
                # Find the search result for this paper
                search_result = self._find_search_result(sug.get("paper_id"), search_results)

                if not search_result:
                    continue

                citation_suggestions.append(
                    CitationSuggestion(
                        paper_id=sug.get("paper_id", ""),
                        title=sug.get("title", ""),
                        authors=sug.get("authors", ""),
                        year=sug.get("year"),
                        relevance_score=sug.get("relevance_score", search_result.score),
                        contribution=sug.get("contribution", ""),
                        integration_suggestion=sug.get("integration_suggestion", ""),
                        quote_suggestion=sug.get("quote_suggestion"),
                    )
                )

            logger.info(f"Generated {len(citation_suggestions)} citation suggestions")
            return citation_suggestions

        except Exception as e:
            logger.error(f"Failed to generate citation suggestions: {e}")

            # Fallback: return top search results as suggestions
            return self._create_fallback_suggestions(search_results[:n])

    async def expand_outline(
        self,
        section: str,
        outline: str,
        target_length: int = 500,
        min_citations: int = 3,
    ) -> Dict[str, Any]:
        """
        Expand an outline with citations.

        Args:
            section: Section name
            outline: Section outline/bullet points
            target_length: Target word count
            min_citations: Minimum citations to include

        Returns:
            Expanded section with citations
        """
        logger.info(f"Expanding outline for section: {section}")

        # Search for relevant papers based on outline
        search_results = self.search_service.search(
            query=f"{section}: {outline}",
            top_k=10,
        )

        papers_text = self._format_papers_for_llm(search_results)

        # Build prompt
        prompt = self._format_prompt(
            "outline_expansion",
            section=section,
            outline=outline,
            tone="academic",
            target_length=target_length,
            citation_style="[AuthorYear]",
            papers=papers_text,
            min_citations=min_citations,
        )

        try:
            response = await self._generate_json(prompt)

            logger.info(
                f"Expanded outline: {response.get('word_count', 0)} words, "
                f"{response.get('citation_count', 0)} citations"
            )

            return response

        except Exception as e:
            logger.error(f"Failed to expand outline: {e}")
            return {
                "section": section,
                "paragraphs": [],
                "word_count": 0,
                "citation_count": 0,
                "error": str(e),
            }

    async def detect_missing_citations(
        self,
        text: str,
    ) -> List[Dict[str, Any]]:
        """
        Detect claims that need citations.

        Args:
            text: Text to analyze

        Returns:
            List of uncited claims with suggestions
        """
        logger.info("Detecting missing citations in text")

        # Get relevant papers for context
        search_results = self.search_service.search(query=text, top_k=10)
        papers_text = self._format_papers_for_llm(search_results)

        # Build prompt
        prompt = self._format_prompt(
            "detect_missing_citations",
            text=text,
            papers=papers_text,
        )

        try:
            response = await self._generate_json(prompt)

            uncited_claims = response.get("uncited_claims", [])

            logger.info(f"Found {len(uncited_claims)} uncited claims")
            return uncited_claims

        except Exception as e:
            logger.error(f"Failed to detect missing citations: {e}")
            return []

    async def enhance_citation(
        self,
        current_text: str,
        paper_id: str,
    ) -> Dict[str, Any]:
        """
        Suggest improvements for citation usage.

        Args:
            current_text: Current text with citation
            paper_id: ID of cited paper

        Returns:
            Enhancement suggestions
        """
        logger.info(f"Enhancing citation for paper: {paper_id}")

        # Get paper details
        paper_summary = self.search_service.get_paper_summary(paper_id)

        if not paper_summary:
            logger.warning(f"Paper not found: {paper_id}")
            return {"error": "Paper not found"}

        # Build prompt
        prompt = self._format_prompt(
            "enhance_citation",
            current_text=current_text,
            title=paper_summary["title"],
            authors=paper_summary["authors"],
            abstract=paper_summary["preview"],
            findings="Key findings from the paper",  # Would extract from paper
        )

        try:
            response = await self._generate_json(prompt)
            return response

        except Exception as e:
            logger.error(f"Failed to enhance citation: {e}")
            return {"error": str(e)}

    def _format_papers_for_llm(self, search_results: List[SearchResult]) -> str:
        """
        Format search results as text for LLM.

        Args:
            search_results: List of SearchResult objects

        Returns:
            Formatted papers text
        """
        papers = []
        for i, result in enumerate(search_results, 1):
            paper_text = f"""
Paper {i}:
ID: {result.paper_id}
Title: {result.title}
Authors: {result.authors}
Year: {result.year or 'N/A'}
Relevance: {result.score:.3f}
Content: {result.text[:200]}...
"""
            papers.append(paper_text.strip())

        return "\n\n".join(papers)

    def _find_search_result(
        self,
        paper_id: str,
        results: List[SearchResult],
    ) -> Optional[SearchResult]:
        """Find search result by paper ID."""
        for result in results:
            if result.paper_id == paper_id:
                return result
        return None

    def _create_fallback_suggestions(
        self,
        search_results: List[SearchResult],
    ) -> List[CitationSuggestion]:
        """
        Create fallback suggestions from search results.

        Args:
            search_results: List of SearchResult objects

        Returns:
            List of CitationSuggestion objects
        """
        suggestions = []

        for result in search_results:
            suggestions.append(
                CitationSuggestion(
                    paper_id=result.paper_id,
                    title=result.title,
                    authors=result.authors,
                    year=result.year,
                    relevance_score=result.score,
                    contribution=f"Relevant paper with similarity score {result.score:.2f}",
                    integration_suggestion=f"Consider citing this paper to support your argument",
                )
            )

        return suggestions

    async def process(
        self,
        action: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Main processing method for writer agent.

        Args:
            action: Action to perform (suggest_citations, expand_outline, etc.)
            **kwargs: Action-specific parameters

        Returns:
            Response dictionary
        """
        if action == "suggest_citations":
            suggestions = await self.suggest_citations(**kwargs)
            return {
                "action": action,
                "suggestions": [s.to_dict() for s in suggestions],
            }

        elif action == "expand_outline":
            result = await self.expand_outline(**kwargs)
            return {"action": action, **result}

        elif action == "detect_missing_citations":
            uncited = await self.detect_missing_citations(**kwargs)
            return {"action": action, "uncited_claims": uncited}

        elif action == "enhance_citation":
            enhancement = await self.enhance_citation(**kwargs)
            return {"action": action, **enhancement}

        else:
            raise ValueError(f"Unknown action: {action}")


# Global singleton instance
_writer_agent: Optional[WriterAgent] = None


def get_writer_agent() -> WriterAgent:
    """
    Get global WriterAgent instance (singleton).

    Returns:
        Shared WriterAgent instance
    """
    global _writer_agent

    if _writer_agent is None:
        _writer_agent = WriterAgent()

    return _writer_agent


async def reset_writer_agent():
    """Reset global writer agent (useful for testing)."""
    global _writer_agent
    _writer_agent = None
