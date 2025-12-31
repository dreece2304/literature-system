"""
Unit tests for TriagerAgent

Tests the critical scoring functionality and bug fixes.
"""

import pytest
from unittest.mock import AsyncMock, Mock


@pytest.mark.unit
class TestTriagerAgent:
    """Test suite for TriagerAgent."""

    @pytest.mark.asyncio
    async def test_score_paper_with_found_paper(self, mock_triager_agent, mock_llm_service, mock_search_service):
        """Test scoring a paper that exists in the database."""
        # Setup mock responses
        mock_search_service.get_paper_summary.return_value = {
            "paper_id": "test-001",
            "title": "Test Paper",
            "authors": "Smith, J.",
            "year": 2023,
            "preview": "This is a test paper",
            "venue": "Test Conf",
            "citation_count": 10,
        }

        mock_llm_service.generate_json.return_value = {
            "paper_id": "test-001",
            "score": 8,
            "justification": "Highly relevant",
            "dimensions": {"relevance": 0.9, "novelty": 0.7},
            "key_takeaways": ["Interesting approach"],
            "action": "must_read",
        }

        # Execute
        result = await mock_triager_agent.score_paper(
            paper_id="test-001",
            research_interests=["machine learning"],
            context_id="test-context",
        )

        # Verify
        assert result.paper_id == "test-001"
        assert result.score == 8
        assert result.action == "must_read"
        assert result.title == "Test Paper"

        # Verify LLM was called with correct temperature (bug fix verification)
        mock_llm_service.generate_json.assert_called_once()
        call_kwargs = mock_llm_service.generate_json.call_args.kwargs
        assert "temperature" in call_kwargs
        # Temperature should be from settings.ollama.triager_temperature (default 0.3)
        assert call_kwargs["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_score_paper_not_found(self, mock_triager_agent, mock_search_service):
        """Test scoring when paper is not found."""
        # Setup - paper not found
        mock_search_service.get_paper_summary.return_value = None

        # Execute
        result = await mock_triager_agent.score_paper(
            paper_id="nonexistent",
            research_interests=["ML"],
        )

        # Verify - should return 0 score without calling LLM
        assert result.paper_id == "nonexistent"
        assert result.score == 0
        assert result.action == "skip"
        assert result.justification == "Paper not found in database"

    @pytest.mark.asyncio
    async def test_score_paper_persists_to_storage(self, mock_triager_agent, mock_search_service, mock_llm_service):
        """Test that scores are persisted to storage."""
        # Setup
        mock_search_service.get_paper_summary.return_value = {
            "paper_id": "test-002",
            "title": "Test Paper 2",
            "authors": "Johnson, A.",
            "year": 2024,
            "preview": "Another test",
            "venue": "Test Conf",
            "citation_count": 5,
        }

        mock_llm_service.generate_json.return_value = {
            "paper_id": "test-002",
            "score": 7,
            "justification": "Good paper",
            "dimensions": {"relevance": 0.8},
            "key_takeaways": ["Novel idea"],
            "action": "should_read",
        }

        # Execute
        await mock_triager_agent.score_paper(
            paper_id="test-002",
            research_interests=["NLP"],
            context_id="nlp-project",
        )

        # Verify score was stored
        stored_score = mock_triager_agent.score_storage.get_score("test-002", "nlp-project")
        assert stored_score is not None
        assert stored_score.score == 7
        assert stored_score.context_id == "nlp-project"

    @pytest.mark.asyncio
    async def test_score_paper_with_context_id(self, mock_triager_agent, mock_search_service, mock_llm_service):
        """Test that context_id is properly used."""
        mock_search_service.get_paper_summary.return_value = {
            "paper_id": "test-003",
            "title": "Test",
            "authors": "Author",
            "year": 2023,
            "preview": "Test",
        }

        mock_llm_service.generate_json.return_value = {
            "score": 6,
            "justification": "Test",
            "dimensions": {},
            "key_takeaways": [],
            "action": "skim",
        }

        # Score in different contexts
        await mock_triager_agent.score_paper(
            paper_id="test-003",
            research_interests=["ML"],
            context_id="context-a",
        )

        await mock_triager_agent.score_paper(
            paper_id="test-003",
            research_interests=["RL"],
            context_id="context-b",
        )

        # Verify both contexts have separate scores
        score_a = mock_triager_agent.score_storage.get_score("test-003", "context-a")
        score_b = mock_triager_agent.score_storage.get_score("test-003", "context-b")

        assert score_a is not None
        assert score_b is not None
        assert score_a.context_id != score_b.context_id

    @pytest.mark.asyncio
    async def test_get_top_papers(self, mock_triager_agent):
        """Test retrieving top papers."""
        # Pre-populate storage with scores
        storage = mock_triager_agent.score_storage
        storage.store_score(
            paper_id="p1",
            score=9,
            justification="Excellent",
            dimensions={},
            key_takeaways=[],
            action="must_read",
            research_interests=["ML"],
            title="Paper 1",
            authors="Author 1",
            context_id="ctx-1",
        )

        storage.store_score(
            paper_id="p2",
            score=6,
            justification="OK",
            dimensions={},
            key_takeaways=[],
            action="should_read",
            research_interests=["ML"],
            title="Paper 2",
            authors="Author 2",
            context_id="ctx-1",
        )

        # Execute
        top_papers = await mock_triager_agent.get_top_papers(
            min_score=7,
            limit=10,
            context_id="ctx-1",
        )

        # Verify
        assert len(top_papers) == 1
        assert top_papers[0]["paper_id"] == "p1"
        assert top_papers[0]["score"] == 9

    @pytest.mark.asyncio
    async def test_get_top_papers_filters_by_context(self, mock_triager_agent):
        """Test that get_top_papers filters by context."""
        storage = mock_triager_agent.score_storage

        # Add papers to different contexts
        storage.store_score(
            paper_id="p1",
            score=8,
            justification="Good",
            dimensions={},
            key_takeaways=[],
            action="must_read",
            research_interests=["ML"],
            title="Paper 1",
            authors="Author 1",
            context_id="ctx-a",
        )

        storage.store_score(
            paper_id="p2",
            score=9,
            justification="Great",
            dimensions={},
            key_takeaways=[],
            action="must_read",
            research_interests=["NLP"],
            title="Paper 2",
            authors="Author 2",
            context_id="ctx-b",
        )

        # Get papers from ctx-a only
        top_papers = await mock_triager_agent.get_top_papers(
            min_score=0,
            limit=10,
            context_id="ctx-a",
        )

        # Should only have papers from ctx-a
        assert len(top_papers) == 1
        assert top_papers[0]["paper_id"] == "p1"

    @pytest.mark.asyncio
    async def test_score_batch(self, mock_triager_agent, mock_search_service, mock_llm_service):
        """Test batch scoring of papers."""
        # Setup mock search service
        def get_summary(paper_id):
            if paper_id == "p1":
                return {
                    "paper_id": "p1",
                    "title": "Paper 1",
                    "authors": "A1",
                    "year": 2023,
                    "preview": "Abstract 1",
                }
            elif paper_id == "p2":
                return {
                    "paper_id": "p2",
                    "title": "Paper 2",
                    "authors": "A2",
                    "year": 2024,
                    "preview": "Abstract 2",
                }
            return None

        mock_search_service.get_paper_summary.side_effect = get_summary

        mock_llm_service.generate_json.return_value = {
            "scores": [
                {"paper_id": "p1", "score": 8},
                {"paper_id": "p2", "score": 6},
            ],
            "ranked_ids": ["p1", "p2"],
            "summary": {"must_read": 1, "should_read": 1},
        }

        # Execute
        result = await mock_triager_agent.score_batch(
            paper_ids=["p1", "p2"],
            research_interests=["ML"],
        )

        # Verify
        assert len(result.scores) == 2
        assert result.ranked_ids == ["p1", "p2"]
        assert "must_read" in result.summary

    @pytest.mark.asyncio
    async def test_compare_papers(self, mock_triager_agent, mock_search_service, mock_llm_service):
        """Test comparing two papers."""
        # Setup
        def get_summary(paper_id):
            summaries = {
                "pa": {
                    "paper_id": "pa",
                    "title": "Paper A",
                    "authors": "Author A",
                    "year": 2023,
                    "preview": "Preview A",
                },
                "pb": {
                    "paper_id": "pb",
                    "title": "Paper B",
                    "authors": "Author B",
                    "year": 2024,
                    "preview": "Preview B",
                },
            }
            return summaries.get(paper_id)

        mock_search_service.get_paper_summary.side_effect = get_summary

        mock_llm_service.generate_json.return_value = {
            "more_relevant": "pa",
            "score_a": 8,
            "score_b": 6,
            "comparison": {"relevance": "A is more relevant"},
            "recommendation": "Read A first",
        }

        # Execute
        result = await mock_triager_agent.compare_papers(
            paper_id_a="pa",
            paper_id_b="pb",
            research_goal="Study ML algorithms",
        )

        # Verify
        assert result["more_relevant"] == "pa"
        assert result["score_a"] == 8
        assert result["score_b"] == 6

    @pytest.mark.asyncio
    async def test_compare_papers_handles_missing_papers(self, mock_triager_agent, mock_search_service):
        """Test that compare handles missing papers gracefully."""
        # One paper missing
        def get_summary(paper_id):
            if paper_id == "exists":
                return {"paper_id": "exists", "title": "Exists"}
            return None

        mock_search_service.get_paper_summary.side_effect = get_summary

        # Execute
        result = await mock_triager_agent.compare_papers(
            paper_id_a="exists",
            paper_id_b="missing",
            research_goal="Test",
        )

        # Should return error
        assert "error" in result

    def test_triager_agent_initialization(self, mock_triager_agent):
        """Test that TriagerAgent initializes correctly."""
        assert mock_triager_agent.agent_name == "triager"
        assert mock_triager_agent.search_service is not None
        assert mock_triager_agent.score_storage is not None

    def test_singleton_pattern(self):
        """Test that get_triager_agent returns singleton."""
        from src.agents.triager import get_triager_agent

        agent1 = get_triager_agent()
        agent2 = get_triager_agent()

        assert agent1 is agent2
