# Research Ecosystem Master Plan

## Vision
A unified research environment that understands what you're writing and provides intelligent literature support throughout the research process.

## Architecture Overview
research/                          (Monorepo Root)
├── infrastructure/               (Core Services)
│   ├── literature-database/     ✅ (Current Project)
│   ├── literature-ai/           🔲 (Phase 2)
│   ├── literature-search/       🔲 (Phase 3)
│   └── api-gateway/            🔲 (Phase 4)
├── active/                      (Current Research)
│   └── [current-paper]/
│       ├── .context
│       ├── analysis/
│       ├── figures/
│       └── manuscript/
├── archive/                     (Completed Work)
└── web-dashboard/              🔲 (Phase 5)

## Development Phases

### Phase 1: Core Database (CURRENT) ✅
**Project:** `literature-database`
**Timeline:** 1-2 weeks
**Goals:**
- Complete Zotero sync functionality
- PDF storage and extraction
- Basic metadata management
- RESTful API with FastAPI
- Full-text search with Whoosh

**Key Features:**
- Import existing Zotero library
- Extract text from PDFs
- Store in SQLite/PostgreSQL
- Search papers by content
- Tag and collection management

### Phase 2: AI Intelligence Layer 🔲
**Project:** `literature-ai`
**Timeline:** 2-3 weeks
**Goals:**
- Writing assistant (PRIMARY)
- Triage assistant for bulk imports
- Deep reading assistant for paper understanding

**Architecture:**
literature-ai/
├── agents/
│   ├── writer.py        # Suggests citations while writing
│   ├── triager.py       # Scores and filters bulk papers
│   └── reader.py        # Answers questions about papers
├── context/
│   ├── detector.py      # Scans active projects
│   └── tracker.py       # Maintains research context
├── embeddings/
│   └── vectorstore.py   # ChromaDB/Qdrant for semantic search
└── pipelines/
├── smart_import.py  # Collection → Score → Triage → Import
└── write_assist.py  # Context → Find papers → Suggest text

**Key Features:**
- Auto-detect what section you're writing
- Find papers for TODO citations
- Generate paragraph drafts with proper citations
- Score paper relevance (0-10) for triage
- Answer questions about paper content

### Phase 3: External Search Integration 🔲
**Project:** `literature-search`
**Timeline:** 1-2 weeks
**Goals:**
- Clean, unified API for external sources
- Prevent duplicate downloads
- Auto-fetch missing papers

**Supported APIs:**
```python
sources = {
    'arxiv': ArxivAPI(),
    'semantic_scholar': S2API(),
    'pubmed': PubMedAPI(),
    'crossref': CrossRefAPI(),
    'unpaywall': UnpaywallAPI(),  # For open access
}
Key Features:

Unified search across all sources
Deduplication by DOI/title
Auto-download open access PDFs
Rate limiting and caching
Bulk paper enrichment (add missing metadata)

Phase 4: API Gateway 🔲
Project: api-gateway
Timeline: 1 week
Goals:

Single entry point for all services
Route requests to appropriate service
Handle authentication (if needed)
Coordinate cross-service operations

Endpoints:
/api/v1/
  /papers         → literature-database
  /ai/write       → literature-ai
  /ai/triage      → literature-ai
  /search         → literature-search
  /context        → Current research context
  /workflow       → Complex operations
Phase 5: Web Dashboard 🔲
Project: web-dashboard
Timeline: 2-3 weeks
Goals:

Visual interface for entire system
Real-time writing assistance
Literature management
Research overview

Key Views:

Writing View (Primary)

Split pane: manuscript + suggestions
Citation search sidebar
Missing reference alerts


Triage View

Bulk paper import interface
Relevance scores visualization
Quick accept/reject actions


Library View

Browse all papers
Collections and tags
Reading status tracking


Context View

Current research overview
Active manuscripts
Recent searches and activity



Data Flow Examples
Example 1: Writing Assistance
1. You edit manuscript/main.tex
2. Context detector notices you're in Discussion section
3. Sees \cite{TODO_dopamine_controversy}
4. AI searches literature-db for relevant papers
5. Ranks by relevance to your paragraph
6. Suggests: "Consider citing Wise (2004) and Berridge (2007)"
7. You click to insert formatted citation
Example 2: Bulk Paper Triage
1. Download 100 papers on new topic
2. Drop folder into web dashboard
3. System extracts metadata + abstracts
4. Triager scores relevance (0-10)
5. Shows top 20 with explanations
6. You mark 10 as "must read"
7. Reader creates summaries for those 10
8. Papers imported to main database
Example 3: Missing Citation Detection
1. Open dashboard while writing
2. System reads your manuscript
3. Detects claim: "dopamine encodes reward prediction error"
4. Checks if you have supporting citations
5. Alerts: "This claim needs support. See Schultz et al. (1997)"
6. One click to add citation
Technology Stack
Backend

Database: PostgreSQL (upgrade from SQLite)
API: FastAPI + Pydantic
Queue: Celery + Redis (for long operations)
Search: Elasticsearch (upgrade from Whoosh)
Vectors: Qdrant or ChromaDB
LLM: Ollama (local) or OpenAI API

Frontend (Dashboard)

Framework: React or Vue.js
UI: Tailwind CSS or Material-UI
Editor: CodeMirror or Monaco (for LaTeX)
Graphs: D3.js or Cytoscape (citation networks)
State: Redux or Pinia

Development Tools

Monorepo: Nx or Turborepo (optional)
Testing: Pytest + Playwright
CI/CD: GitHub Actions
Deployment: Docker Compose

Success Metrics

Writing Speed: Reduce time to find appropriate citations by 80%
Triage Efficiency: Process 100 papers in <10 minutes
Coverage: Never miss important papers in your field
Context Switching: Zero friction between writing and literature search
Deduplication: 100% prevention of duplicate paper storage

Migration Path
Week 1-2: Complete Phase 1

Finish literature-database
Import your existing Zotero library
Verify search works well

Week 3-4: Start Phase 2

Build writing assistant first
Test with your current paper
Iterate on context detection

Week 5: Add Phase 3

Implement key APIs you actually used
Focus on arxiv + semantic scholar first

Week 6: Integration

Connect all services
Build basic dashboard
Test full workflows

Next Immediate Steps

Complete literature-database Zotero sync
Import your paper library
Test search functionality
Plan the context file structure
Start literature-ai with writing assistant