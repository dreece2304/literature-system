# Service Architecture

## Current Architecture (December 2024)

The literature management system uses MCP (Model Context Protocol) for direct database access.
**No HTTP API layer is required for core operations.**

```
Claude Code → MCP Server → Service Layer → SQLAlchemy → SQLite
```

### MCP Server

The MCP server runs as a subprocess of Claude Code and communicates via stdio:

| Component | Description |
|-----------|-------------|
| **MCP Server** | `python -m src.mcp_server.server` |
| **Database** | SQLite at `infrastructure/literature-database/data/literature.db` |
| **Protocol** | stdio (no network ports) |

## Infrastructure Services (Optional)

These services are only needed for specific features:

| Service | Port | Purpose | When Needed |
|---------|------|---------|-------------|
| **Ollama** | 11434 | Local LLM server | AI extraction, summarization |
| **Redis** | 6379 | Event queue (Celery) | Background tasks |
| **ChromaDB** | (in-process) | Vector embeddings | Semantic search |

## External APIs (No local ports)

External academic APIs used for paper discovery:

| API | Purpose |
|-----|---------|
| **CrossRef** | DOI lookup, metadata |
| **Semantic Scholar** | Citations, open access |
| **arXiv** | Preprints, PDFs |
| **OpenAlex** | Open academic data |
| **Unpaywall** | Open access PDF URLs |

## Archived: HTTP API Layer

> **Note**: The FastAPI HTTP layer has been archived. It is no longer required.
> See `archive/fastapi-api/` for the old implementation.

The old architecture used HTTP:
```
# OLD - DEPRECATED
Claude Code → MCP → HTTP (port 8001) → FastAPI → SQLAlchemy → SQLite
```

## Starting the System

### For Claude Code Integration

Claude Code starts the MCP server automatically based on `.claude/settings.local.json`:

```json
{
  "mcpServers": {
    "literature": {
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/path/to/infrastructure/literature-ai"
    }
  }
}
```

### Manual Testing

```bash
# Start MCP server directly (for testing)
cd infrastructure/literature-ai
mamba run -n litai python -m src.mcp_server.server
```

### Optional Services

```bash
# Ollama (for LLM features)
ollama serve

# Redis (for background tasks)
redis-server
```

## Environment Variables

```bash
# Required
LITDB_DATABASE_PATH=/path/to/literature.db

# Optional (external APIs)
SEMANTIC_SCHOLAR_API_KEY=your_key
UNPAYWALL_EMAIL=your@email.com

# Optional (Zotero sync)
ZOTERO_API_KEY=your_key
ZOTERO_USER_ID=your_id
```

## Development Notes

### Port Conflicts

Since the MCP server uses stdio (no network ports), there are no port conflicts.
The only potential conflicts are with optional services:

| Service | Default Port | Alternative |
|---------|-------------|-------------|
| Ollama | 11434 | `OLLAMA_HOST=http://localhost:11435` |
| Redis | 6379 | `REDIS_URL=redis://localhost:6380` |

### Database Location

The SQLite database is at:
```
infrastructure/literature-database/data/literature.db
```

To use a different location, set:
```bash
LITDB_DATABASE_PATH=/your/path/literature.db
```
