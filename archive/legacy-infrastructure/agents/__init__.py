"""
Agents module for literature-ai.

Provides AI-powered agents for various literature tasks.
"""

from src.agents.base import BaseAgent
from src.agents.extractor import ExtractorAgent, ExtractionResult, RelevanceResult

__all__ = [
    "BaseAgent",
    "ExtractorAgent",
    "ExtractionResult",
    "RelevanceResult",
]
