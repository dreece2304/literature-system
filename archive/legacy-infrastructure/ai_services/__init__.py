"""AI-specific services for literature management.

These services provide LLM integration, paper scoring, and Claude API access.
They are separate from the core database services in src/services/.
"""

from .llm_service import LLMService, get_llm_service
from .claude_service import ClaudeService, get_claude_service
from .score_storage import ScoreStorage, get_score_storage

__all__ = [
    "LLMService",
    "get_llm_service",
    "ClaudeService",
    "get_claude_service",
    "ScoreStorage",
    "get_score_storage",
]
