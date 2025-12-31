"""
Unit tests for ReaderAgent

Tests the RAG-powered Q&A functionality.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from dataclasses import dataclass


@pytest.mark.unit
class TestReaderAgent:
    """Test suite for ReaderAgent."""

    @pytest.mark.asyncio
    async def test_ask_with_found_papers(self, mock_reader_agent, mock_llm_service, mock_search_service):
        """Test asking a question when relevant papers exist."""
        # Setup mock search results
        @dataclass
        class MockSearchResult:
            paper_id: str
            title: str
            authors: str
            year: int
            score: float
            text: str

        search_results = [
            MockSearchResult(
                paper_id="p1",
                title="Paper 1",
                authors="Author A",
                year=2023,
                score=0.95,
                text="This paper discusses machine learning techniques.",
            ),
            MockSearchResult(
                paper_id="p2",
                title="Paper 2",
                authors="Author B",
                year=2024,
                score=0.85,
                text="Deep learning has shown great promise.",
            ),
        ]

        mock_search_service.search.return_value = search_results

        # Setup mock LLM response
        mock_llm_service.generate_json.return_value = {
            "answer": "Machine learning and deep learning are powerful techniques.",
            "citations": [
                {
                    "paper_id": "p1",
                    "title": "Paper 1",
                    "authors": "Author A",
                    "year": 2023,
                    "relevant_quote": "machine learning techniques",
                }
            ],
            "confidence": "high",
            "limitations": None,
            "follow_up_questions": ["What specific techniques work best?"],
        }

        # Execute
        result = await mock_reader_agent.ask(
            question="What are the main ML techniques?",
            top_k=5,
        )

        # Verify
        assert result.question == "What are the main ML techniques?"
        assert result.answer == "Machine learning and deep learning are powerful techniques."
        assert result.confidence == "high"
        assert len(result.citations) == 1
        assert len(result.follow_up_questions) == 1

        # Verify search was called
        mock_search_service.search.assert_called_once()

        # Verify LLM was called with reader temperature
        mock_llm_service.generate_json.assert_called_once()
        call_kwargs = mock_llm_service.generate_json.call_args.kwargs
        assert call_kwargs["temperature"] == 0.1  # reader_temperature from settings

    @pytest.mark.asyncio
    async def test_ask_with_no_papers_found(self, mock_reader_agent, mock_search_service):
        """Test asking when no relevant papers exist."""
        # Setup - no results
        mock_search_service.search.return_value = []

        # Execute
        result = await mock_reader_agent.ask(
            question="What is quantum computing?",
        )

        # Verify - should return low confidence response
        assert result.question == "What is quantum computing?"
        assert "don't have enough information" in result.answer.lower()
        assert result.confidence == "low"
        assert result.citations == []
        assert result.limitations == "No relevant papers found"

    @pytest.mark.asyncio
    async def test_summarize_paper_found(self, mock_reader_agent, mock_search_service, mock_llm_service):
        """Test summarizing a paper that exists."""
        # Setup mock paper summary
        mock_search_service.get_paper_summary.return_value = {
            "paper_id": "p1",
            "title": "Test Paper",
            "authors": "Author A",
            "year": 2023,
        }

        # Setup mock chunks (vectorstore.get)
        mock_reader_agent.search_service.vectorstore = Mock()
        mock_reader_agent.search_service.vectorstore.get.return_value = [
            {"text": "Introduction: This paper..."},
            {"text": "Methods: We used..."},
            {"text": "Results: We found..."},
        ]

        # Setup mock LLM response
        mock_llm_service.generate_json.return_value = {
            "research_question": "How does X affect Y?",
            "methodology": "Experimental study with control groups",
            "key_findings": ["Finding 1", "Finding 2"],
            "contributions": ["Contribution 1"],
            "limitations": ["Limited sample size"],
            "future_work": ["Expand to larger datasets"],
            "one_sentence_summary": "This paper studies X and Y.",
        }

        # Execute
        result = await mock_reader_agent.summarize_paper(paper_id="p1")

        # Verify
        assert result.paper_id == "p1"
        assert result.title == "Test Paper"
        assert result.research_question == "How does X affect Y?"
        assert len(result.key_findings) == 2
        assert len(result.contributions) == 1
        assert result.one_sentence_summary == "This paper studies X and Y."

    @pytest.mark.asyncio
    async def test_summarize_paper_not_found(self, mock_reader_agent, mock_search_service):
        """Test summarizing when paper doesn't exist."""
        # Setup - paper not found
        mock_search_service.get_paper_summary.return_value = None

        # Execute and verify exception
        with pytest.raises(ValueError, match="Paper not found"):
            await mock_reader_agent.summarize_paper(paper_id="nonexistent")

    @pytest.mark.asyncio
    async def test_find_related_papers(self, mock_reader_agent, mock_search_service):
        """Test finding related papers."""
        # Setup mock similar papers
        @dataclass
        class MockSearchResult:
            paper_id: str
            title: str
            authors: str
            year: int
            score: float
            text: str

        similar_papers = [
            MockSearchResult("p1", "Highly Related", "A", 2023, 0.9, "text1"),
            MockSearchResult("p2", "Moderately Related", "B", 2024, 0.7, "text2"),
            MockSearchResult("p3", "Somewhat Related", "C", 2022, 0.5, "text3"),
        ]

        mock_search_service.find_similar_papers.return_value = similar_papers

        # Execute
        result = await mock_reader_agent.find_related_papers(
            paper_id="reference",
            top_k=10,
        )

        # Verify
        assert result["reference_paper_id"] == "reference"
        assert result["total_related"] == 3
        assert len(result["highly_related"]) == 1
        assert len(result["moderately_related"]) == 1
        assert len(result["somewhat_related"]) == 1

        # Verify similarity grouping
        assert result["highly_related"][0]["similarity_score"] == 0.9
        assert result["moderately_related"][0]["similarity_score"] == 0.7
        assert result["somewhat_related"][0]["similarity_score"] == 0.5

    @pytest.mark.asyncio
    async def test_process_with_ask_action(self, mock_reader_agent):
        """Test process() method with ask action."""
        # Mock the ask method
        mock_response = Mock()
        mock_response.to_dict.return_value = {
            "question": "Test question",
            "answer": "Test answer",
            "citations": [],
            "confidence": "medium",
            "limitations": None,
            "follow_up_questions": [],
        }
        mock_reader_agent.ask = AsyncMock(return_value=mock_response)

        # Execute
        result = await mock_reader_agent.process(
            action="ask",
            question="Test question",
            top_k=5,
        )

        # Verify
        assert result["question"] == "Test question"
        assert result["answer"] == "Test answer"
        mock_reader_agent.ask.assert_called_once_with(
            question="Test question",
            top_k=5,
            score_threshold=None,
        )

    @pytest.mark.asyncio
    async def test_process_with_summarize_action(self, mock_reader_agent):
        """Test process() method with summarize action."""
        # Mock the summarize_paper method
        mock_summary = Mock()
        mock_summary.to_dict.return_value = {
            "paper_id": "p1",
            "title": "Test",
            "research_question": "RQ",
            "methodology": "Method",
            "key_findings": [],
            "contributions": [],
            "limitations": [],
            "future_work": [],
            "one_sentence_summary": "Summary",
        }
        mock_reader_agent.summarize_paper = AsyncMock(return_value=mock_summary)

        # Execute
        result = await mock_reader_agent.process(
            action="summarize",
            paper_id="p1",
        )

        # Verify
        assert result["paper_id"] == "p1"
        mock_reader_agent.summarize_paper.assert_called_once_with(paper_id="p1")

    @pytest.mark.asyncio
    async def test_process_with_find_related_action(self, mock_reader_agent):
        """Test process() method with find_related action."""
        # Mock the find_related_papers method
        mock_reader_agent.find_related_papers = AsyncMock(return_value={
            "reference_paper_id": "p1",
            "total_related": 0,
            "highly_related": [],
            "moderately_related": [],
            "somewhat_related": [],
        })

        # Execute
        result = await mock_reader_agent.process(
            action="find_related",
            paper_id="p1",
            top_k=10,
        )

        # Verify
        assert result["reference_paper_id"] == "p1"
        mock_reader_agent.find_related_papers.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_with_unknown_action(self, mock_reader_agent):
        """Test process() raises error for unknown action."""
        with pytest.raises(ValueError, match="Unknown action"):
            await mock_reader_agent.process(action="invalid_action")

    def test_format_papers_context(self, mock_reader_agent):
        """Test _format_papers_context method."""
        @dataclass
        class MockSearchResult:
            paper_id: str
            title: str
            authors: str
            year: int
            score: float
            text: str

        results = [
            MockSearchResult("p1", "Paper 1", "Author A", 2023, 0.9, "Text 1"),
            MockSearchResult("p2", "Paper 2", "Author B", 2024, 0.8, "Text 2"),
        ]

        context = mock_reader_agent._format_papers_context(results)

        # Verify format
        assert "Paper 1: Paper 1" in context
        assert "Authors: Author A" in context
        assert "Year: 2023" in context
        assert "Relevance: 0.90" in context
        assert "Text 1" in context
        assert "---" in context  # Separator

    def test_format_search_result(self, mock_reader_agent):
        """Test _format_search_result method."""
        @dataclass
        class MockResult:
            paper_id: str = "p1"
            title: str = "Test Paper"
            authors: str = "Author A"
            year: int = 2023
            score: float = 0.95
            text: str = "A" * 300  # Long text

        result = MockResult()
        formatted = mock_reader_agent._format_search_result(result)

        # Verify
        assert formatted["paper_id"] == "p1"
        assert formatted["title"] == "Test Paper"
        assert formatted["authors"] == "Author A"
        assert formatted["year"] == 2023
        assert formatted["similarity_score"] == 0.95
        assert len(formatted["excerpt"]) <= 203  # 200 + "..."
        assert formatted["excerpt"].endswith("...")

    def test_singleton_pattern(self):
        """Test that get_reader_agent returns singleton."""
        from src.agents.reader import get_reader_agent

        agent1 = get_reader_agent()
        agent2 = get_reader_agent()

        assert agent1 is agent2

    def test_reader_agent_initialization(self, mock_reader_agent):
        """Test that ReaderAgent initializes correctly."""
        assert mock_reader_agent.agent_name == "reader"
        assert mock_reader_agent.search_service is not None
        assert mock_reader_agent.model is not None

    @pytest.mark.asyncio
    async def test_ask_uses_correct_temperature(self, mock_reader_agent, mock_llm_service, mock_search_service):
        """Test that ask() uses reader_temperature setting."""
        from config.settings import settings

        # Setup mocks
        @dataclass
        class MockSearchResult:
            paper_id: str = "p1"
            title: str = "Test"
            authors: str = "Author"
            year: int = 2023
            score: float = 0.9
            text: str = "text"

        mock_search_service.search.return_value = [MockSearchResult()]
        mock_llm_service.generate_json.return_value = {
            "answer": "Answer",
            "citations": [],
            "confidence": "high",
            "limitations": None,
            "follow_up_questions": [],
        }

        # Execute
        await mock_reader_agent.ask(question="Test question")

        # Verify temperature
        call_kwargs = mock_llm_service.generate_json.call_args.kwargs
        assert call_kwargs["temperature"] == settings.ollama.reader_temperature
        assert call_kwargs["temperature"] == 0.1  # Default reader temp

    @pytest.mark.asyncio
    async def test_summarize_uses_correct_temperature(self, mock_reader_agent, mock_llm_service, mock_search_service):
        """Test that summarize_paper() uses reader_temperature."""
        from config.settings import settings

        # Setup mocks
        mock_search_service.get_paper_summary.return_value = {
            "paper_id": "p1",
            "title": "Test",
            "authors": "Author",
            "year": 2023,
        }
        mock_reader_agent.search_service.vectorstore = Mock()
        mock_reader_agent.search_service.vectorstore.get.return_value = [
            {"text": "Content"}
        ]
        mock_llm_service.generate_json.return_value = {
            "research_question": "RQ",
            "methodology": "Method",
            "key_findings": [],
            "contributions": [],
            "limitations": [],
            "future_work": [],
            "one_sentence_summary": "Summary",
        }

        # Execute
        await mock_reader_agent.summarize_paper(paper_id="p1")

        # Verify temperature
        call_kwargs = mock_llm_service.generate_json.call_args.kwargs
        assert call_kwargs["temperature"] == settings.ollama.reader_temperature
