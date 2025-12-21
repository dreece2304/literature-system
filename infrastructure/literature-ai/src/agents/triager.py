"""
TriagerAgent: Intelligent paper scoring and prioritization.

Scores papers on a 0-10 scale based on relevance to research interests.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

from src.agents.base import BaseAgent
from src.services.search_service import get_search_service
from src.services.score_storage import get_score_storage
from config.settings import settings


@dataclass
class PaperScore:
    """Scored paper result."""

    paper_id: str
    title: str
    authors: str
    year: Optional[int]
    score: int  # 0-10
    justification: str
    dimensions: Dict[str, float]
    key_takeaways: List[str]
    action: str  # must_read, should_read, skim, skip

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "score": self.score,
            "justification": self.justification,
            "dimensions": self.dimensions,
            "key_takeaways": self.key_takeaways,
            "action": self.action,
        }


@dataclass
class BatchScoreResult:
    """Batch scoring result."""

    scores: List[Dict[str, Any]]
    ranked_ids: List[str]
    summary: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scores": self.scores,
            "ranked_ids": self.ranked_ids,
            "summary": self.summary,
        }


class TriagerAgent(BaseAgent):
    """
    Triager agent for intelligent paper prioritization.

    Capabilities:
    - Score individual papers (0-10 scale)
    - Batch score multiple papers
    - Compare papers for relevance
    - Create prioritized reading queues
    - Identify research gaps
    """

    def __init__(self):
        """Initialize triager agent."""
        super().__init__(agent_name="triager")
        self.search_service = get_search_service()
        self.score_storage = get_score_storage()
        logger.info("TriagerAgent initialized")

    async def process(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Main processing method for the agent.

        This is a convenience method that routes to specific scoring methods
        based on the action parameter.

        Args:
            action: Action to perform (score_paper, score_batch, compare_papers)
            **kwargs: Arguments for the specific action

        Returns:
            Result dictionary
        """
        action = kwargs.get("action", "score_paper")

        if action == "score_paper":
            result = await self.score_paper(
                paper_id=kwargs["paper_id"],
                research_interests=kwargs["research_interests"],
                current_projects=kwargs.get("current_projects"),
                preferred_methods=kwargs.get("preferred_methods"),
            )
            return result.to_dict()

        elif action == "score_batch":
            result = await self.score_batch(
                paper_ids=kwargs["paper_ids"],
                research_interests=kwargs["research_interests"],
                current_projects=kwargs.get("current_projects"),
                max_papers=kwargs.get("max_papers", 20),
            )
            return result.to_dict()

        elif action == "compare_papers":
            return await self.compare_papers(
                paper_id_a=kwargs["paper_id_a"],
                paper_id_b=kwargs["paper_id_b"],
                research_goal=kwargs["research_goal"],
            )

        else:
            raise ValueError(f"Unknown action: {action}")

    async def score_paper(
        self,
        paper_id: str,
        research_interests: List[str],
        current_projects: Optional[List[str]] = None,
        preferred_methods: Optional[List[str]] = None,
        context_id: str = "default",
    ) -> PaperScore:
        """
        Score a single paper for relevance.

        Args:
            paper_id: Paper identifier
            research_interests: List of research interest keywords
            current_projects: Current project descriptions
            preferred_methods: Preferred research methods

        Returns:
            PaperScore with 0-10 score and detailed breakdown
        """
        logger.info(f"Scoring paper: {paper_id}")

        # Get paper details
        paper_summary = self.search_service.get_paper_summary(paper_id)

        if not paper_summary:
            logger.warning(f"Paper not found: {paper_id}")
            return PaperScore(
                paper_id=paper_id,
                title="Unknown",
                authors="Unknown",
                year=None,
                score=0,
                justification="Paper not found in database",
                dimensions={},
                key_takeaways=[],
                action="skip",
            )

        # Format prompt
        prompt = self._format_prompt(
            "score_paper",
            interests=", ".join(research_interests),
            projects=", ".join(current_projects or ["No specific projects"]),
            methods=", ".join(preferred_methods or ["No specific methods"]),
            title=paper_summary["title"],
            authors=paper_summary["authors"],
            year=paper_summary.get("year", "Unknown"),
            venue=paper_summary.get("venue", "Unknown"),
            citation_count=paper_summary.get("citation_count", 0),
            abstract=paper_summary.get("preview", "No abstract available"),
        )

        # Get LLM response
        response = await self._generate_json(
            prompt, temperature=settings.ollama.triager_temperature
        )

        # Parse response
        score_data = self._parse_score_response(response, paper_summary)

        # Persist score to storage
        self.score_storage.store_score(
            paper_id=score_data["paper_id"],
            score=score_data["score"],
            justification=score_data["justification"],
            dimensions=score_data["dimensions"],
            key_takeaways=score_data["key_takeaways"],
            action=score_data["action"],
            research_interests=research_interests,
            title=score_data["title"],
            authors=score_data["authors"],
            year=score_data["year"],
            context_id=context_id,
        )

        return PaperScore(**score_data)

    async def score_batch(
        self,
        paper_ids: List[str],
        research_interests: List[str],
        current_projects: Optional[List[str]] = None,
        max_papers: int = 20,
    ) -> BatchScoreResult:
        """
        Score multiple papers in batch.

        Args:
            paper_ids: List of paper identifiers
            research_interests: List of research interest keywords
            current_projects: Current project descriptions
            max_papers: Maximum papers to score in one batch

        Returns:
            BatchScoreResult with scores and rankings
        """
        logger.info(f"Batch scoring {len(paper_ids)} papers")

        # Limit batch size
        if len(paper_ids) > max_papers:
            logger.warning(
                f"Batch size {len(paper_ids)} exceeds max {max_papers}, truncating"
            )
            paper_ids = paper_ids[:max_papers]

        # Get paper summaries
        papers = []
        for paper_id in paper_ids:
            summary = self.search_service.get_paper_summary(paper_id)
            if summary:
                papers.append(
                    {
                        "paper_id": paper_id,
                        "title": summary["title"],
                        "authors": summary["authors"],
                        "year": summary.get("year", "Unknown"),
                        "abstract": summary.get("preview", "")[:300],
                    }
                )

        if not papers:
            logger.warning("No valid papers found for batch scoring")
            return BatchScoreResult(scores=[], ranked_ids=[], summary={})

        # Format papers list for prompt
        papers_text = "\n\n".join(
            [
                f"Paper {i+1} (ID: {p['paper_id']}):\n"
                f"Title: {p['title']}\n"
                f"Authors: {p['authors']}\n"
                f"Year: {p['year']}\n"
                f"Abstract: {p['abstract'][:200]}..."
                for i, p in enumerate(papers)
            ]
        )

        # Format prompt
        prompt = self._format_prompt(
            "score_batch",
            interests=", ".join(research_interests),
            projects=", ".join(current_projects or ["No specific projects"]),
            papers=papers_text,
        )

        # Get LLM response
        response = await self._generate_json(
            prompt, temperature=settings.ollama.triager_temperature
        )

        # Parse response
        scores = response.get("scores", [])
        ranked_ids = response.get("ranked_ids", [])
        summary = response.get("summary", {})

        return BatchScoreResult(
            scores=scores,
            ranked_ids=ranked_ids,
            summary=summary,
        )

    async def compare_papers(
        self,
        paper_id_a: str,
        paper_id_b: str,
        research_goal: str,
    ) -> Dict[str, Any]:
        """
        Compare two papers for relevance to a research goal.

        Args:
            paper_id_a: First paper ID
            paper_id_b: Second paper ID
            research_goal: Research goal to compare against

        Returns:
            Comparison result with recommendations
        """
        logger.info(f"Comparing papers: {paper_id_a} vs {paper_id_b}")

        # Get paper summaries
        paper_a = self.search_service.get_paper_summary(paper_id_a)
        paper_b = self.search_service.get_paper_summary(paper_id_b)

        if not paper_a or not paper_b:
            return {"error": "One or both papers not found"}

        # Format papers for prompt
        paper_a_text = f"{paper_a['title']} ({paper_a['authors']}, {paper_a.get('year', 'N/A')})\n{paper_a.get('preview', '')[:300]}"
        paper_b_text = f"{paper_b['title']} ({paper_b['authors']}, {paper_b.get('year', 'N/A')})\n{paper_b.get('preview', '')[:300]}"

        # Format prompt
        prompt = self._format_prompt(
            "compare_papers",
            goal=research_goal,
            paper_a=paper_a_text,
            paper_b=paper_b_text,
        )

        # Get LLM response
        response = await self._generate_json(
            prompt, temperature=settings.ollama.triager_temperature
        )

        return response

    async def get_top_papers(
        self,
        min_score: int = 7,
        limit: int = 10,
        context_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Get top-scored papers from the collection.

        Args:
            min_score: Minimum score threshold (0-10)
            limit: Maximum number of papers to return
            context_id: Research context identifier

        Returns:
            List of top-scored papers with full score details
        """
        logger.info(f"Retrieving top papers (context: {context_id}, min_score: {min_score})")

        # Retrieve top scores from storage
        stored_scores = self.score_storage.get_top_papers(
            context_id=context_id,
            min_score=min_score,
            limit=limit,
        )

        # Convert to dict format for API response
        return [score.to_dict() for score in stored_scores]

    def _parse_score_response(
        self, response: Dict[str, Any], paper_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Parse LLM scoring response into PaperScore format.

        Args:
            response: LLM JSON response
            paper_summary: Original paper summary

        Returns:
            Formatted score data
        """
        return {
            "paper_id": response.get("paper_id", paper_summary.get("paper_id", "unknown")),
            "title": paper_summary.get("title", "Unknown"),
            "authors": paper_summary.get("authors", "Unknown"),
            "year": paper_summary.get("year"),
            "score": int(response.get("score", 0)),
            "justification": response.get("justification", "No justification provided"),
            "dimensions": response.get("dimensions", {}),
            "key_takeaways": response.get("key_takeaways", []),
            "action": response.get("action", "skip"),
        }


# Singleton instance
_triager_agent: Optional[TriagerAgent] = None


def get_triager_agent() -> TriagerAgent:
    """Get or create triager agent singleton."""
    global _triager_agent
    if _triager_agent is None:
        _triager_agent = TriagerAgent()
    return _triager_agent
