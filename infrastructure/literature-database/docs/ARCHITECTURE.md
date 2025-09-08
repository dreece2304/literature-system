# Literature Database Architecture

*Last Updated: 2025-01-09*

## Service Overview

The Literature Database is the **core document management service** in the research monorepo architecture. It provides the single source of truth for all literature data, with a lightweight design that serves as the foundation for specialized extension services.

## 📊 Current Service Status

- **Papers**: 323 papers imported from Zotero
- **PDF Coverage**: 289 PDFs linked (89% coverage) 
- **Storage Efficiency**: No duplicate PDFs - references Zotero storage
- **Categorization**: Materials science focused with 8+ specialized categories
- **Collections**: Manuscript citation management system operational
- **API Port**: 8001 (production service)

## 🏗️ Service Boundaries

### ✅ In Scope (Core Service)

**Document Management:**
- PDF processing and metadata extraction
- SQLite database with comprehensive schema
- File hash deduplication and reference linking
- Zotero synchronization (local + web API)

**Search & Organization:**
- Full-text search with Whoosh indexing
- Basic categorization using keyword patterns
- Collection management for manuscripts
- BibTeX bibliography generation

**API & Integration:**
- FastAPI REST API server (port 8001)
- Command-line interface with rich formatting
- Database CRUD operations
- Cross-service data access
- Redis event publishing for real-time notifications

### ❌ Out of Scope (Extension Services)

**AI & Machine Learning:**
- LLM models or inference → `literature-ai`
- Vector embeddings and semantic search → `literature-ai`
- Intelligent summarization → `literature-ai`
- Advanced AI-based categorization → `literature-ai`

**External Data Sources:**
- arXiv API integration → `literature-search`
- PubMed API integration → `literature-search`
- DOI resolution services → `literature-search`
- Real-time paper discovery → `literature-search`

**Visualization & Analytics:**
- Citation network analysis → `literature-viz`
- Research trend visualization → `literature-viz`
- Advanced dashboards → `literature-viz`
- Collaboration networks → `literature-viz`

## 🎯 Monorepo Architecture

```
research/
├── infrastructure/
│   ├── literature-database/     ← THIS SERVICE (port 8001)
│   ├── api-gateway/            ← Routes to all services
│   └── shared/                 ← Common types and utilities
├── services/
│   ├── literature-ai/          ← LLM, embeddings, RAG
│   ├── literature-search/      ← External API aggregation  
│   └── literature-viz/         ← Visualizations, dashboards
└── web-dashboard/              ← Frontend (port 3000)
```

### Service Communication

**API Gateway Pattern:**
- All external requests route through `api-gateway`
- Internal services communicate via shared types
- Cross-service data access through standardized APIs

**Shared Resources:**
- Common types in `shared/types/api_contracts.py`
- Database models serve all services
- Authentication handled at gateway level

## 🔧 Technical Implementation

### Core Technologies
- **Database**: SQLite with SQLAlchemy ORM
- **Search**: Whoosh full-text indexing
- **API**: FastAPI with automatic OpenAPI docs
- **CLI**: Rich formatting and Click commands
- **Sync**: Zotero local API and web API integration
- **Events**: Redis pub/sub for real-time notifications

### Database Schema
```python
# Core entities and relationships
Paper ↔ Author (many-to-many)
Paper ↔ Tag (many-to-many)  
Paper ↔ Collection (many-to-many)
Paper → Note (one-to-many)
Paper ↔ Citation (self-referential many-to-many)
```

### API Endpoints (Port 8001)
```
GET  /health                    # Service health check
GET  /api/v1/papers            # List papers with pagination
GET  /api/v1/papers/{id}       # Get single paper
POST /api/v1/papers            # Create new paper
PUT  /api/v1/papers/{id}       # Update paper
DELETE /api/v1/papers/{id}     # Delete paper
POST /api/v1/search            # Full-text search
POST /api/v1/sync/zotero       # Trigger Zotero sync
```

### Event Publishing System

**Real-time Notifications:**
- Paper operations publish events to Redis channels
- Event types: `paper.added`, `paper.updated`, `paper.deleted`, `sync.completed`
- Standardized event schema with timestamps and metadata
- Graceful degradation when Redis unavailable

## 🚀 Production Workflows

### Daily Research Operations
```bash
# Navigate to service directory
cd infrastructure/literature-database

# Sync latest papers from Zotero
python -m src.cli sync

# Search collection
python -m src.cli search "atomic layer deposition"

# Auto-categorize new papers
python scripts/organize_collection.py auto-categorize

# Start API service
python run_service.py
```

### Manuscript Citation Management
```bash
# Create collection for manuscript
python scripts/manuscript_collections.py --action create --title "My Research Paper"

# Add relevant papers
python scripts/manuscript_collections.py --action add --collection-id 1 --search "your keywords"

# Export bibliography
python scripts/manuscript_collections.py --action export --collection-id 1
```

## 🔮 Extension Service Architecture

### Literature-AI Service Integration

**Planned API Extensions** (for AI service consumption):
```python
# Extension points for AI services
GET /api/v1/papers/{id}/raw_content    # Get paper text for processing
POST /api/v1/papers/{id}/ai_metadata   # AI updates metadata
GET /api/v1/papers/uncategorized       # Papers needing categorization
PUT /api/v1/papers/{id}/categories     # Update AI-generated categories
```

**Benefits of Separation:**
- Core operations unaffected by AI processing time
- Independent scaling and deployment
- Easy model updates without database changes
- Optional features don't impact basic functionality

### Literature-Search Service Integration

**External API Coordination:**
- Core service manages known papers
- Search service discovers new papers
- Automatic deduplication via DOI/arXiv matching
- Bulk import capabilities through core API

### Literature-Viz Service Integration

**Data Access Patterns:**
- Read-only access to paper relationships
- Citation network data export
- Collection statistics and trends
- Real-time updates via API webhooks

## 📁 Key Service Files

### Essential Production Scripts
- `run_service.py` - Start FastAPI service on port 8001
- `scripts/manuscript_collections.py` - Citation management
- `scripts/organize_collection.py` - Paper categorization
- `scripts/setup_zotero.py` - Initial Zotero configuration

### Core Implementation
- `src/api/main.py` - FastAPI application and endpoints
- `src/models.py` - Database schema and relationships
- `src/services/paper_service.py` - Business logic layer
- `src/services/search_service.py` - Whoosh search engine
- `src/services/event_service.py` - Redis event publishing
- `src/extractors/zotero_local_api.py` - Zotero integration

### Configuration & Data
- `config/settings.yml` - Service configuration
- `data/metadata/literature.db` - SQLite database
- `data/cache/search_index/` - Whoosh search index

## 🔧 Service Maintenance

### Regular Operations
- **Weekly**: Zotero synchronization
- **Monthly**: Search index optimization
- **Per manuscript**: Bibliography generation
- **As needed**: Category pattern updates

### Monitoring & Health
- Health check endpoint: `GET /health`
- Database integrity: Automatic foreign key constraints  
- Search index: Periodic reindexing capabilities
- API metrics: FastAPI automatic documentation

### Backup Strategy
- **Database**: `data/metadata/literature.db` (primary data)
- **Configuration**: `config/` directory settings
- **PDFs**: Managed by Zotero (no duplication)
- **Search Index**: Rebuilds automatically from database

## 🌟 Success Metrics

- **89% PDF Coverage**: Excellent full-text access
- **Zero Duplicate Storage**: Efficient Zotero integration
- **323 Papers Organized**: Comprehensive research library
- **Materials Science Focus**: Domain-appropriate categorization
- **Complete Citation Workflow**: Manuscript-ready output

## 🚦 Service Status: Production Ready

The literature-database service is **fully operational** and ready for production use as the core document management layer in the research monorepo architecture.

### Ready For:
- ✅ Daily research literature management
- ✅ Manuscript citation workflows  
- ✅ Full-text search and organization
- ✅ Cross-service data integration
- ✅ Extension service development

### Future Extensions:
- 🔄 **literature-ai**: LLM integration project
- 🔄 **literature-search**: External API aggregation  
- 🔄 **literature-viz**: Advanced visualization tools

---

**Architecture Status**: Complete and production-ready for monorepo integration 🎓