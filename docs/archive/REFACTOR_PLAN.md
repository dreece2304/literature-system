# Refactor Plan: Simplify Literature Management Architecture

## Executive Summary

Eliminate the HTTP API layer between MCP tools and SQLite database to reduce complexity and latency.

**Current Flow:**
```
Claude Code → MCP Server → HTTP (httpx) → FastAPI → SQLAlchemy → SQLite
```

**Target Flow:**
```
Claude Code → MCP Server → SQLAlchemy → SQLite
```

---

## Current Architecture Analysis

### How MCP Tools Currently Access Data

**Location:** `infrastructure/literature-ai/src/mcp_server/tools/*.py`

Every MCP tool uses `httpx.AsyncClient` to make HTTP calls to the FastAPI server running on port 8001:

```python
# From tools/papers.py
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    api_url = get_api_url()
    async with httpx.AsyncClient(timeout=30.0) as client:
        if name == "list_papers":
            response = await client.get(f"{api_url}/papers", params=params)
```

### What database_client.py Does

**Location:** `infrastructure/literature-ai/src/services/database_client.py`

Despite its name, this is NOT a database client - it's an **HTTP wrapper** around the REST API:

```python
class DatabaseClient:
    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        raw_url = base_url or settings.litdb.api_url
        self.base_url = raw_url.rstrip('/')
        if not self.base_url.endswith('/api/v1'):
            self.base_url = f"{self.base_url}/api/v1"
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout))
```

It provides async methods that wrap HTTP calls:
- `get_papers()` → `GET /papers`
- `get_paper(id)` → `GET /papers/{id}`
- `create_paper()` → `POST /papers`
- etc.

### Duplicate Code Between Services

| Component | literature-database | literature-ai |
|-----------|---------------------|---------------|
| Models | `src/models.py` (SQLAlchemy ORM) | None (uses HTTP) |
| Database access | `src/database.py` (engine/session) | `database_client.py` (HTTP wrapper) |
| Search logic | `src/api/routes/search.py` | `tools/search.py` (calls API) |
| Paper CRUD | `src/api/routes/papers.py` | `tools/papers.py` (calls API) |

**Key insight:** The literature-ai service has no direct database code - everything goes through HTTP.

---

## Files That Will Be Modified

### Tool Modules (10 files)

1. **`infrastructure/literature-ai/src/mcp_server/tools/papers.py`**
   - Replace `httpx` calls with direct SQLAlchemy queries
   - Import models and session from literature-database

2. **`infrastructure/literature-ai/src/mcp_server/tools/search.py`**
   - Replace HTTP calls with direct database/ChromaDB access

3. **`infrastructure/literature-ai/src/mcp_server/tools/notes.py`**
   - Direct CRUD operations on Note model

4. **`infrastructure/literature-ai/src/mcp_server/tools/collections.py`**
   - Direct CRUD operations on Collection model

5. **`infrastructure/literature-ai/src/mcp_server/tools/pdf.py`**
   - Direct database access for PDF status/metadata

6. **`infrastructure/literature-ai/src/mcp_server/tools/project.py`**
   - Direct access for citation/manuscript operations

7. **`infrastructure/literature-ai/src/mcp_server/tools/import_export.py`**
   - Direct BibTeX parsing and database insertion

8. **`infrastructure/literature-ai/src/mcp_server/tools/external.py`**
   - Keep external API calls (CrossRef, Semantic Scholar, etc.)
   - Replace internal HTTP with direct DB writes

9. **`infrastructure/literature-ai/src/mcp_server/tools/zotero.py`**
   - Direct database access for Zotero sync

10. **`infrastructure/literature-ai/src/mcp_server/tools/browser_pdf.py`**
    - Direct database updates for PDF download queue

### New Files to Create

1. **`infrastructure/literature-ai/src/db/session.py`**
   - Shared database session factory
   - Imports engine/models from literature-database
   - Provides async-compatible session management

---

## Files That Can Be Deleted

### Definitely Delete

1. **`infrastructure/literature-ai/src/services/database_client.py`**
   - HTTP wrapper - no longer needed with direct access

### Potentially Delete (after audit)

2. **`infrastructure/literature-database/src/api/`** (entire directory)
   - FastAPI routes no longer needed if all access is direct
   - **Risk:** Other consumers may depend on REST API - audit first

3. **Vestigial AI/LLM code** (if present):
   - `infrastructure/literature-ai/src/agents/`
   - Any Ollama/Claude API integration code
   - ExtractorAgent and related files

---

## Files to Keep (Shared/Reused)

1. **`infrastructure/literature-database/src/database.py`**
   - SQLAlchemy engine/session factory
   - Will be imported by MCP tools

2. **`infrastructure/literature-database/src/models.py`**
   - ORM models (Paper, Author, Tag, Collection, Note, etc.)
   - Will be imported by MCP tools

3. **`infrastructure/literature-database/src/core/`**
   - Any business logic that can be reused

---

## Potential Risks

### 1. Breaking External Consumers
- **Risk:** Scripts or tools that call the REST API directly will break
- **Mitigation:** Audit all callers before removing API
- **Check:** `grep -r "localhost:8001" .` and `grep -r "api/v1" .`

### 2. Session Management Complexity
- **Risk:** MCP tools are async; SQLAlchemy sessions need careful handling
- **Mitigation:** Use `run_sync()` wrapper or async SQLAlchemy 2.0
- **Pattern:**
  ```python
  from sqlalchemy.orm import Session
  from infrastructure.literature_database.src.database import get_session

  def get_papers():
      with get_session() as session:
          return session.query(Paper).all()
  ```

### 3. Import Path Changes
- **Risk:** MCP tools need to import from literature-database
- **Mitigation:** Add to Python path or restructure as proper packages
- **Option:** Symlink or sys.path manipulation

### 4. ChromaDB Integration
- **Risk:** Semantic search uses ChromaDB for embeddings
- **Mitigation:** Ensure ChromaDB access pattern works alongside SQLAlchemy
- **Current:** ChromaDB already accessed directly, not through HTTP

### 5. Transaction Boundaries
- **Risk:** HTTP gave natural request/response transaction boundaries
- **Mitigation:** Explicit commit/rollback in each tool function
- **Pattern:** Use context managers for session lifecycle

### 6. Testing Updates
- **Risk:** All MCP tool tests will need updating
- **Change:** Mock database instead of mock HTTP responses

---

## Known Bug to Fix During Refactor

**`store_extraction` schema mismatch:**
- Tool accepts: `key_findings: ["string", "string"]`
- Database expects: `key_findings: [{finding_id, statement, evidence, topics}]`
- **Action:** Align schemas during refactor

---

## Recommended Implementation Phases

### Phase 1: Create Shared Database Module
- New file: `infrastructure/literature-ai/src/db/session.py`
- Import engine/models from literature-database
- Provide sync session factory for MCP tools

### Phase 2: Proof-of-Concept with papers.py
- Refactor `papers.py` to use direct SQLAlchemy
- Validate pattern works with all paper operations
- Test thoroughly before proceeding

### Phase 3: Refactor Remaining Tools
- Apply proven pattern to all 10 tool modules
- One module at a time, test after each

### Phase 4: Deprecate API Layer
- Mark REST API endpoints as deprecated
- Monitor for external consumers
- Remove after confirmation period

### Phase 5: Cleanup
- Delete `database_client.py`
- Delete unused API routes
- Delete vestigial AI/LLM code
- Update all documentation

---

## Pre-Refactor Checklist

- [ ] Audit external API consumers
- [ ] Backup current database
- [ ] Document current test coverage
- [ ] Set up rollback plan
- [ ] Verify ChromaDB compatibility
