"""
ReaderAgent: RAG-powered Q&A over paper collection.

Uses retrieval-augmented generation to answer questions about papers.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

from src.agents.base import BaseAgent
from src.services.search_service import get_search_service
from config.settings import settings


@dataclass
class QAResponse:
    """Q&A response with citations."""

    question: str
    answer: str
    citations: List[Dict[str, Any]]
    confidence: str  # high, medium, low
    limitations: Optional[str]
    follow_up_questions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": self.citations,
            "confidence": self.confidence,
            "limitations": self.limitations,
            "follow_up_questions": self.follow_up_questions,
        }


@dataclass
class PaperSummary:
    """Paper summary result."""

    paper_id: str
    title: str
    research_question: str
    methodology: str
    key_findings: List[str]
    contributions: List[str]
    limitations: List[str]
    future_work: List[str]
    one_sentence_summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "research_question": self.research_question,
            "methodology": self.methodology,
            "key_findings": self.key_findings,
            "contributions": self.contributions,
            "limitations": self.limitations,
            "future_work": self.future_work,
            "one_sentence_summary": self.one_sentence_summary,
        }


class ReaderAgent(BaseAgent):
    """
    Reader agent for RAG-powered Q&A.

    Capabilities:
    - Answer questions about papers using RAG
    - Summarize individual papers
    - Extract and compare methodologies
    - Find related papers
    """

    def __init__(self):
        """Initialize reader agent."""
        super().__init__(agent_name="reader")
        self.search_service = get_search_service()
        logger.info("ReaderAgent initialized")

    async def process(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Main processing method for the agent.

        Args:
            action: Action to perform (ask, summarize, extract_methodology)
            **kwargs: Arguments for the specific action

        Returns:
            Result dictionary
        """
        action = kwargs.get("action", "ask")

        if action == "ask":
            result = await self.ask(
                question=kwargs["question"],
                top_k=kwargs.get("top_k", 5),
                score_threshold=kwargs.get("score_threshold"),
            )
            return result.to_dict()

        elif action == "summarize":
            result = await self.summarize_paper(
                paper_id=kwargs["paper_id"]
            )
            return result.to_dict()

        elif action == "find_related":
            return await self.find_related_papers(
                paper_id=kwargs["paper_id"],
                top_k=kwargs.get("top_k", 10),
            )

        else:
            raise ValueError(f"Unknown action: {action}")

    async def ask(
        self,
        question: str,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
    ) -> QAResponse:
        """
        Answer a question using RAG.

        Retrieves relevant paper chunks and uses LLM to answer the question
        based only on the retrieved context.

        Args:
            question: Question to answer
            top_k: Number of paper chunks to retrieve
            score_threshold: Minimum similarity score for retrieval

        Returns:
            QAResponse with answer and citations
        """
        logger.info(f"Answering question: {question[:100]}...")

        # Step 1: Retrieve relevant papers using semantic search
        search_results = self.search_service.search(
            query=question,
            top_k=top_k,
            score_threshold=score_threshold,
        )

        if not search_results:
            logger.warning("No relevant papers found for question")
            return QAResponse(
                question=question,
                answer="I don't have enough information to answer this question. No relevant papers were found in the collection.",
                citations=[],
                confidence="low",
                limitations="No relevant papers found",
                follow_up_questions=[],
            )

        # Step 2: Format paper contexts for LLM
        papers_context = self._format_papers_context(search_results)

        # Step 3: Generate answer using LLM
        prompt = self._format_prompt(
            "answer_question",
            question=question,
            papers_context=papers_context,
        )

        response = await self._generate_json(
            prompt, temperature=settings.ollama.reader_temperature
        )

        # Parse response
        return QAResponse(
            question=question,
            answer=response.get("answer", "Unable to generate answer"),
            citations=response.get("citations", []),
            confidence=response.get("confidence", "low"),
            limitations=response.get("limitations"),
            follow_up_questions=response.get("follow_up_questions", []),
        )

    async def summarize_paper(self, paper_id: str) -> PaperSummary:
        """
        Summarize a paper comprehensively.

        Args:
            paper_id: Paper identifier

        Returns:
            PaperSummary with detailed breakdown
        """
        logger.info(f"Summarizing paper: {paper_id}")

        # Get paper details
        paper = self.search_service.get_paper_summary(paper_id)

        if not paper:
            raise ValueError(f"Paper not found: {paper_id}")

        # Get full paper content (all chunks)
        search_results = self.search_service.vectorstore.get(
            where={"paper_id": paper_id},
            limit=100,  # Get all chunks for this paper
        )

        # Combine chunks to get full text
        full_text = "\n\n".join([chunk["text"] for chunk in search_results])

        # Generate summary using LLM
        prompt = self._format_prompt(
            "summarize_paper",
            title=paper["title"],
            authors=paper["authors"],
            year=paper.get("year", "Unknown"),
            full_text=full_text[:8000],  # Limit to avoid context overflow
        )

        response = await self._generate_json(
            prompt, temperature=settings.ollama.reader_temperature
        )

        # Parse response
        return PaperSummary(
            paper_id=paper_id,
            title=paper["title"],
            research_question=response.get("research_question", "Unknown"),
            methodology=response.get("methodology", "Unknown"),
            key_findings=response.get("key_findings", []),
            contributions=response.get("contributions", []),
            limitations=response.get("limitations", []),
            future_work=response.get("future_work", []),
            one_sentence_summary=response.get("one_sentence_summary", ""),
        )

    async def find_related_papers(
        self,
        paper_id: str,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Find papers related to a given paper.

        Args:
            paper_id: Reference paper ID
            top_k: Number of related papers to find

        Returns:
            Dict with related papers and relationships
        """
        logger.info(f"Finding papers related to: {paper_id}")

        # Use search service to find similar papers
        similar_papers = self.search_service.find_similar_papers(
            paper_id=paper_id,
            top_k=top_k,
        )

        # Group by similarity score ranges
        highly_related = [p for p in similar_papers if p.score >= 0.8]
        moderately_related = [p for p in similar_papers if 0.6 <= p.score < 0.8]
        somewhat_related = [p for p in similar_papers if p.score < 0.6]

        return {
            "reference_paper_id": paper_id,
            "total_related": len(similar_papers),
            "highly_related": [self._format_search_result(p) for p in highly_related],
            "moderately_related": [self._format_search_result(p) for p in moderately_related],
            "somewhat_related": [self._format_search_result(p) for p in somewhat_related],
        }

    def _format_papers_context(self, search_results: List) -> str:
        """
        Format search results into context for LLM.

        Args:
            search_results: List of SearchResult objects

        Returns:
            Formatted context string
        """
        contexts = []

        for i, result in enumerate(search_results, 1):
            context = f"""
Paper {i}: {result.title}
Authors: {result.authors}
Year: {result.year}
Relevance: {result.score:.2f}

Content:
{result.text}
            """.strip()
            contexts.append(context)

        return "\n\n---\n\n".join(contexts)

    def _format_search_result(self, result) -> Dict[str, Any]:
        """Format search result for API response."""
        return {
            "paper_id": result.paper_id,
            "title": result.title,
            "authors": result.authors,
            "year": result.year,
            "similarity_score": result.score,
            "excerpt": result.text[:200] + "..." if len(result.text) > 200 else result.text,
        }


# Singleton instance
_reader_agent: Optional[ReaderAgent] = None


def get_reader_agent() -> ReaderAgent:
    """Get or create reader agent singleton."""
    global _reader_agent
    if _reader_agent is None:
        _reader_agent = ReaderAgent()
    return _reader_agent
