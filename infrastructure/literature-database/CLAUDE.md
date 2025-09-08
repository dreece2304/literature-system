# Claude Development Governance for Literature Database

## Project Overview

**Project Name**: literature-database
**Purpose**: Core document management system for research papers, providing single source of truth for all literature data.
**Architecture**: Lightweight core service with API for modular extensions

### Project Ecosystem
1. **literature-database** (THIS PROJECT) - Core PDF/metadata management
2. **literature-ai** (future) - LLM, embeddings, RAG features  
3. **literature-search** (future) - External API aggregator for paper sources
4. **literature-viz** (future) - Visualization and dashboards

## Core Principle: Single Source of Truth

- No duplicate implementations
- No parallel systems  
- Every piece of data has exactly ONE authoritative location
- Every functionality exists in exactly ONE place
- No redundant code, utilities, or data stores

## Strict Governance Rules

### 1. File Organization

**ALLOWED locations:**
- `/src/` - Core functionality ONLY, organized by module
  - `/src/extractors/` - PDF/document extractors
  - `/src/analyzers/` - Content analysis  
  - `/src/api/` - FastAPI endpoints
  - `/src/utils/` - Shared utilities (must be truly shared)
  - `/src/models.py` - Database models (single source)
  - `/src/database.py` - Database connections (single source)
- `/scripts/` - Standalone executable scripts
- `/tests/` - All tests, mirroring `/src/` structure
- `/notebooks/` - Jupyter notebooks for analysis
- `/config/` - Configuration files only
- `/docs/` - Documentation

**FORBIDDEN:**
- Creating ANY files in root directory (except .env, requirements.txt, setup.py)
- Creating "temp", "old", "backup", "v2" versions of files
- Creating misc or random utility files
- Creating duplicate functionality in different locations

### 2. Error Handling Protocol

When encountering ANY error:

1. **Document the full trace** - Show complete error output
2. **Fix at source** - Identify and fix root cause in original file
3. **Verify the fix** - Test that it works
4. **Confirm no side effects** - Check dependent code still works

**NEVER:**
- Create workaround functions
- Add try/except blocks that hide real issues
- Make "v2" or "fixed" versions of files  
- Comment out broken code instead of fixing it
- Create bypass or placeholder solutions

### 3. Code Modification Protocol

When modifying existing code:

1. **Check single source of truth** - Ensure changes don't create duplication
2. **Justify if refactoring** - Explain why refactor is necessary
3. **Update ALL references** - Find and update all dependent code
4. **Maintain interfaces** - Don't break existing APIs without updating callers
5. **Update in same session** - All related changes must be complete

### 4. Git Workflow

**Branch Strategy:**
- `main` - Stable, working code only
- Small fixes/updates can go directly to main
- Feature branches for major work: `feature/name`
- Experimental branches for testing: `experimental/name`

**Commit Requirements:**
- Format: `type: description`
- Types: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Show git status before committing
- Show git diff for review
- Never auto-commit without showing changes

### 5. Dependency Management

**Installation Protocol:**
1. Try `mamba install` FIRST
2. Use `pip install` only if not in conda-forge
3. ALWAYS specify exact versions
4. Update both requirements.txt AND environment.yml
5. Document why package is needed

**Keep Lightweight:**
- Justify every new dependency
- Prefer standard library when possible
- AI/ML packages go in literature-ai project
- Heavy processing goes in extension projects

### 6. Testing Requirements

**Every code change MUST:**
1. Include tests in `/tests/`
2. Pass all existing tests
3. Validate all inputs
4. Use database transactions
5. Log errors properly (no silent failures)

**Pre-commit Checklist:**
- [ ] Run black formatter
- [ ] Run tests
- [ ] Check for API keys/secrets
- [ ] Verify relative paths only
- [ ] Update documentation

### 7. Communication Protocol (Checkpoint System)

For EVERY task, Claude MUST:

1. **STATE GOAL** - What will be accomplished
2. **LIST FILES** - What will be created/modified
3. **IMPLEMENT** - Show the code
4. **SUMMARIZE** - What was done
5. **SUGGEST NEXT** - Logical next steps

Never combine unrelated tasks in one response.

### 8. Documentation Standards

**Required Documentation:**

1. **Code Level:**
   - Docstrings for ALL functions/classes
   - Type hints for ALL function parameters
   - Inline comments for complex logic

2. **Project Level:**
   - README.md - Keep updated with features
   - CHANGELOG.md - Track all changes
   - API.md - Document all endpoints
   - dependencies.md - Explain why each package exists

3. **Decision Tracking:**
   - decisions.md - Architectural choices with reasoning
   - exceptions.md - Any approved governance exceptions
   - migrations.md - Guide for major refactors

### 9. Exception Handling

If governance rules conflict with best practice:

1. **TRY WITHIN RULES FIRST** - Document attempts
2. **IDENTIFY CONFLICT** - Explain why rules don't work
3. **REQUEST PERMISSION** - Propose minimal exception
4. **WAIT FOR APPROVAL** - Never proceed without explicit approval
5. **DOCUMENT EXCEPTION** - Log in exceptions.md with date and reason
6. **UPDATE GOVERNANCE** - Modify rules to handle future cases

## Environment Specification

```yaml
name: litdb
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pandas
  - numpy
  - sqlalchemy
  - psycopg2-binary
  - jupyterlab
  - ipykernel
  - pytest
  - black
  - pylint
  - pyyaml
  - python-dotenv
  - requests
  - beautifulsoup4
Additional pip packages:

pyzotero
pdfplumber
PyPDF2
bibtexparser
whoosh
fastapi
uvicorn
click
rich
loguru
alembic

API Contract for Extensions
The core API must remain stable for extensions:
Endpoints:

GET /papers - List papers with filters
GET /papers/{id} - Get single paper with metadata
POST /papers - Add new paper
PUT /papers/{id} - Update paper
DELETE /papers/{id} - Remove paper
GET /search - Full-text search
POST /sync/zotero - Trigger Zotero sync

Database Access:

Extensions can have read-only database access
All writes must go through API
Vector stores and AI data in separate databases

Project Boundaries
IN SCOPE for this project:

PDF storage and retrieval
Metadata management
Zotero synchronization
Basic search functionality
RESTful API
Database CRUD operations

OUT OF SCOPE (goes in extensions):

LLM integration
Semantic search
Embeddings/vectors
Complex visualizations
External API calls (except Zotero)
Machine learning features

Approval Record
Developer: @dreec
Date Established: 2024-12-XX
Last Updated: 2024-12-XX
Exception Log
[Exceptions will be logged here with date, reason, and resolution]

REMINDER TO CLAUDE: These governance rules are absolute unless explicitly overridden by the developer with written approval in the conversation. Always follow the checkpoint protocol for every response.
