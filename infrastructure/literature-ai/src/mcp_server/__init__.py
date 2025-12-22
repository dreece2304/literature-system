"""
Literature MCP Server - Claude Code plugin for literature management.

This MCP server exposes tools for:
- Paper management (CRUD, search)
- Semantic search via ChromaDB
- External API lookups (CrossRef, OpenAlex, Semantic Scholar)
- Citation management
"""

from .server import main, main_async, server

__all__ = ["main", "main_async", "server"]
