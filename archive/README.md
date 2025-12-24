# Archive Directory

This directory contains legacy code that is no longer used by the active MCP server.

## Archived: December 2024

### Full Consolidation (Dec 24, 2024)

All active code was consolidated into `src/`:
- `embeddings/` - Vector store and embedding generator
- `mcp_server/` - MCP server tools and resources
- `extractors/` - Zotero sync and local API
- `context/` - Context parsing
- `services/` - Paper, search, collection services
- `literature_core/` - Database models and configuration

The `infrastructure/literature-ai/src/` and `infrastructure/literature-database/src/` 
directories have been removed as their code now lives in `src/`.

### Original Archive Reason

The project was refactored to consolidate code:
- **Old**: Separate `infrastructure/literature-ai/` and `infrastructure/literature-database/` with duplicated services
- **New**: Single `src/` directory with canonical implementations

### Contents

#### `fastapi-api/`
The original FastAPI HTTP API layer. Removed when the architecture changed to direct database access:
- Old: `MCP Server → HTTP → FastAPI → SQLAlchemy → SQLite`
- New: `MCP Server → Services → SQLAlchemy → SQLite`

#### `legacy-infrastructure/`
Code from `infrastructure/` that was replaced or never used:

- **`agents/`** - AI agents (reader, writer, triager, extractor) - never integrated with MCP
- **`ai_services/`** - LLM services (Ollama, Claude API) - not used by MCP server
- **`events/`** - Event consumer for async processing - not used
- **`tasks/`** - Celery background tasks - not used
- **`utils/`** - Utility functions from literature-ai - not imported by MCP
- **`context/`** - Context detector/tracker - only `parser.py` is used (kept in main code)
- **`database-services/`** - Old service implementations from literature-database
- **`database-core/`** - Duplicate database.py, models.py, config.py (older versions without indexes)

### Recovery

If you need to restore any archived code:

```bash
# Example: restore agents
cp -r archive/legacy-infrastructure/agents/ infrastructure/literature-ai/src/agents/
```

### Do Not Delete

This archive is kept for reference. The code may contain useful patterns or logic
that could be adapted for future features.
