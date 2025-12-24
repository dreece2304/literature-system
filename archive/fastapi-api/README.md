# Archived: FastAPI HTTP Layer

**Date Archived**: December 2024
**Reason**: Replaced with direct database access via service layer

## What Was Archived

### literature-database-api/
FastAPI REST API for literature-database:
- `main.py` - FastAPI app initialization
- `routers/` - API route handlers (papers, collections, notes, etc.)
- `schemas.py` - Pydantic request/response models
- `converters.py` - ORM to schema converters

### literature-ai-api/
FastAPI REST API for literature-ai:
- `main.py` - FastAPI app with semantic search endpoints
- `endpoints/` - Route handlers
- `schemas.py` - Pydantic models

### database_client.py
HTTP client wrapper that made `httpx` calls to the FastAPI server.

## Why It Was Removed

The original architecture had an unnecessary HTTP hop:

```
Old: Claude Code → MCP Server → HTTP → FastAPI → SQLAlchemy → SQLite
```

This added:
- Network latency
- Serialization/deserialization overhead
- Separate process management
- Port conflicts
- Extra debugging complexity

The new architecture uses direct database access:

```
New: Claude Code → MCP Server → Service Layer → SQLAlchemy → SQLite
```

## New Architecture

MCP tools now use the service layer directly:
- `src/services/paper_service.py`
- `src/services/collection_service.py`
- `src/services/note_service.py`
- `src/services/search_service.py`
- `src/services/pdf_service.py`
- `src/services/import_export_service.py`
- `src/services/citation_service.py`

## If You Need This Code

This code is kept for reference only. If you need to restore HTTP access for some reason:

1. Move the directories back:
   ```bash
   mv archive/fastapi-api/literature-database-api infrastructure/literature-database/src/api
   mv archive/fastapi-api/literature-ai-api infrastructure/literature-ai/src/api
   ```

2. Add FastAPI dependencies back to requirements

3. Update startup scripts

**Note**: This is not recommended. The service layer approach is simpler and faster.
