#!/usr/bin/env python3
"""
Comprehensive Phase 1 Testing Script

Tests:
1. Config bug fixes (temperature parameters work)
2. Score persistence to SQLite
3. Context-aware scoring
4. Scores persist across sessions
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.triager import get_triager_agent
from src.services.search_service import get_search_service
from src.services.score_storage import get_score_storage


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


async def test_config_fix():
    """Test that temperature config works (no AttributeError)."""
    print(f"\n{bcolors.HEADER}Test 1: Config Bug Fix{bcolors.ENDC}")
    print("Testing that agents can access temperature settings...")

    try:
        triager = get_triager_agent()

        # This should work now (previously would throw AttributeError)
        from config.settings import settings
        temp = settings.ollama.triager_temperature
        print(f"{bcolors.OKGREEN}✓ Triager temperature setting accessible: {temp}{bcolors.ENDC}")

        reader_temp = settings.ollama.reader_temperature
        print(f"{bcolors.OKGREEN}✓ Reader temperature setting accessible: {reader_temp}{bcolors.ENDC}")

        return True
    except AttributeError as e:
        print(f"{bcolors.FAIL}✗ Config error: {e}{bcolors.ENDC}")
        return False


async def test_score_persistence():
    """Test that scores are persisted to SQLite."""
    print(f"\n{bcolors.HEADER}Test 2: Score Persistence{bcolors.ENDC}")
    print("Testing score storage to SQLite database...")

    try:
        triager = get_triager_agent()
        storage = get_score_storage()

        # Add a mock paper directly to search service for testing
        search_service = get_search_service()

        # Create mock paper data
        mock_paper = {
            "paper_id": "mock-001",
            "title": "Deep Learning for Natural Language Processing",
            "authors": "Smith, J., Johnson, A.",
            "year": 2023,
            "abstract": "This paper explores deep learning techniques for NLP tasks including sentiment analysis and text classification.",
            "preview": "Deep learning has revolutionized NLP...",
            "venue": "NeurIPS 2023",
            "citation_count": 42
        }

        # Add paper to vectorstore (simplified - just for testing)
        # Note: In production this would come from literature-database
        print(f"  Using mock paper: {mock_paper['title']}")

        # Manually add paper to search service's paper cache
        search_service._paper_cache = {"mock-001": mock_paper}

        # Score the paper
        print("  Scoring paper...")
        score_result = await triager.score_paper(
            paper_id="mock-001",
            research_interests=["machine learning", "NLP"],
            current_projects=["Text classification"],
            context_id="test-context-1"
        )

        print(f"{bcolors.OKGREEN}✓ Paper scored: {score_result.score}/10 - {score_result.action}{bcolors.ENDC}")
        print(f"  Justification: {score_result.justification[:100]}...")

        # Verify score was persisted
        stored_score = storage.get_score("mock-001", "test-context-1")

        if stored_score:
            print(f"{bcolors.OKGREEN}✓ Score persisted to SQLite!{bcolors.ENDC}")
            print(f"  Stored score: {stored_score.score}/10")
            print(f"  Context: {stored_score.context_id}")
            return True
        else:
            print(f"{bcolors.FAIL}✗ Score not found in storage{bcolors.ENDC}")
            return False

    except Exception as e:
        print(f"{bcolors.FAIL}✗ Error: {e}{bcolors.ENDC}")
        import traceback
        traceback.print_exc()
        return False


async def test_context_aware_scoring():
    """Test that same paper can have different scores in different contexts."""
    print(f"\n{bcolors.HEADER}Test 3: Context-Aware Scoring{bcolors.ENDC}")
    print("Testing that same paper can have different scores per context...")

    try:
        triager = get_triager_agent()
        storage = get_score_storage()
        search_service = get_search_service()

        # Use same mock paper as before
        mock_paper = {
            "paper_id": "mock-002",
            "title": "Reinforcement Learning in Robotics",
            "authors": "Chen, L., Williams, K.",
            "year": 2024,
            "abstract": "Application of RL algorithms to robotic manipulation tasks.",
            "preview": "Reinforcement learning enables robots...",
            "venue": "ICRA 2024",
            "citation_count": 15
        }

        search_service._paper_cache["mock-002"] = mock_paper

        # Score in Context 1 (RL research)
        print("  Scoring for RL project...")
        score1 = await triager.score_paper(
            paper_id="mock-002",
            research_interests=["reinforcement learning", "robotics"],
            current_projects=["Robot learning"],
            context_id="rl-project"
        )

        print(f"  Context 'rl-project': Score = {score1.score}/10")

        # Score in Context 2 (NLP research - should be less relevant)
        print("  Scoring for NLP project...")
        score2 = await triager.score_paper(
            paper_id="mock-002",
            research_interests=["natural language processing", "sentiment analysis"],
            current_projects=["Text mining"],
            context_id="nlp-project"
        )

        print(f"  Context 'nlp-project': Score = {score2.score}/10")

        # Verify both scores are stored separately
        stored_rl = storage.get_score("mock-002", "rl-project")
        stored_nlp = storage.get_score("mock-002", "nlp-project")

        if stored_rl and stored_nlp:
            print(f"{bcolors.OKGREEN}✓ Both contexts stored separately!{bcolors.ENDC}")
            print(f"  RL context: {stored_rl.score}/10")
            print(f"  NLP context: {stored_nlp.score}/10")

            if stored_rl.score != stored_nlp.score:
                print(f"{bcolors.OKGREEN}✓ Scores differ by context (as expected)!{bcolors.ENDC}")
            else:
                print(f"{bcolors.WARNING}⚠ Scores are the same (LLM may have given same score){bcolors.ENDC}")

            return True
        else:
            print(f"{bcolors.FAIL}✗ Not all scores were stored{bcolors.ENDC}")
            return False

    except Exception as e:
        print(f"{bcolors.FAIL}✗ Error: {e}{bcolors.ENDC}")
        import traceback
        traceback.print_exc()
        return False


async def test_get_top_papers():
    """Test retrieving top-scored papers."""
    print(f"\n{bcolors.HEADER}Test 4: Get Top Papers{bcolors.ENDC}")
    print("Testing retrieval of top-scored papers...")

    try:
        triager = get_triager_agent()

        # Get top papers from rl-project context
        top_papers = await triager.get_top_papers(
            min_score=0,
            limit=10,
            context_id="rl-project"
        )

        print(f"  Found {len(top_papers)} scored papers in 'rl-project' context")

        if len(top_papers) > 0:
            print(f"{bcolors.OKGREEN}✓ Top papers retrieved successfully!{bcolors.ENDC}")
            for i, paper in enumerate(top_papers, 1):
                print(f"  {i}. {paper['title']} - Score: {paper['score']}/10")
            return True
        else:
            print(f"{bcolors.WARNING}⚠ No papers found (may be expected if previous tests failed){bcolors.ENDC}")
            return True  # Not a failure

    except Exception as e:
        print(f"{bcolors.FAIL}✗ Error: {e}{bcolors.ENDC}")
        import traceback
        traceback.print_exc()
        return False


async def test_stats():
    """Test statistics endpoint."""
    print(f"\n{bcolors.HEADER}Test 5: Statistics{bcolors.ENDC}")
    print("Testing score statistics...")

    try:
        storage = get_score_storage()

        # Get overall stats
        stats = storage.get_stats()
        print(f"  Total scores: {stats['total_scores']}")
        print(f"  Average score: {stats['avg_score']}")
        print(f"  Action counts: {stats['action_counts']}")

        # Get contexts
        contexts = storage.get_contexts()
        print(f"\n  Available contexts: {len(contexts)}")
        for ctx in contexts:
            print(f"    - {ctx['context_id']}: {ctx['paper_count']} papers, avg score {ctx['avg_score']}")

        print(f"{bcolors.OKGREEN}✓ Statistics retrieved successfully!{bcolors.ENDC}")
        return True

    except Exception as e:
        print(f"{bcolors.FAIL}✗ Error: {e}{bcolors.ENDC}")
        import traceback
        traceback.print_exc()
        return False


async def test_persistence_check():
    """Verify scores exist in SQLite database file."""
    print(f"\n{bcolors.HEADER}Test 6: Database Persistence{bcolors.ENDC}")
    print("Checking that scores are actually in SQLite file...")

    try:
        from config.settings import DATA_DIR
        import sqlite3

        db_path = DATA_DIR / "scores.db"

        if not db_path.exists():
            print(f"{bcolors.FAIL}✗ Database file not found: {db_path}{bcolors.ENDC}")
            return False

        print(f"  Database file: {db_path}")
        print(f"  File size: {db_path.stat().st_size} bytes")

        # Query database directly
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM paper_scores")
        count = cursor.fetchone()[0]

        cursor.execute("SELECT paper_id, context_id, score, scored_at FROM paper_scores LIMIT 5")
        rows = cursor.fetchall()

        conn.close()

        print(f"\n  Total scores in database: {count}")

        if count > 0:
            print(f"{bcolors.OKGREEN}✓ Scores persisted to disk!{bcolors.ENDC}")
            print("\n  Sample scores:")
            for row in rows:
                print(f"    - {row[0]} ({row[1]}): {row[2]}/10 at {row[3]}")
            return True
        else:
            print(f"{bcolors.WARNING}⚠ No scores in database{bcolors.ENDC}")
            return False

    except Exception as e:
        print(f"{bcolors.FAIL}✗ Error: {e}{bcolors.ENDC}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print(f"\n{bcolors.BOLD}{'='*60}{bcolors.ENDC}")
    print(f"{bcolors.BOLD}Phase 1 Comprehensive Testing{bcolors.ENDC}")
    print(f"{bcolors.BOLD}{'='*60}{bcolors.ENDC}")

    results = []

    # Run tests
    results.append(("Config Fix", await test_config_fix()))
    results.append(("Score Persistence", await test_score_persistence()))
    results.append(("Context-Aware Scoring", await test_context_aware_scoring()))
    results.append(("Get Top Papers", await test_get_top_papers()))
    results.append(("Statistics", await test_stats()))
    results.append(("Database Persistence", await test_persistence_check()))

    # Summary
    print(f"\n{bcolors.BOLD}{'='*60}{bcolors.ENDC}")
    print(f"{bcolors.BOLD}Test Summary{bcolors.ENDC}")
    print(f"{bcolors.BOLD}{'='*60}{bcolors.ENDC}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{bcolors.OKGREEN}PASS{bcolors.ENDC}" if result else f"{bcolors.FAIL}FAIL{bcolors.ENDC}"
        print(f"  {test_name}: {status}")

    print(f"\n{bcolors.BOLD}Total: {passed}/{total} tests passed{bcolors.ENDC}")

    if passed == total:
        print(f"\n{bcolors.OKGREEN}{'✓ All Phase 1 tests passed!'}{bcolors.ENDC}")
        return 0
    else:
        print(f"\n{bcolors.WARNING}{'⚠ Some tests failed - review output above'}{bcolors.ENDC}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
