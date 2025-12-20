# Changelog

All notable changes to the Literature Database service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Service Port**: 8001 | **Monorepo Path**: `infrastructure/literature-database/`

---

## [1.1.0] - 2024-12-20

### Added - Standalone Merge & Data Migration

#### Citation Management System
- **BibtexService**: Generate BibTeX from database papers
- **CitationService**: Scan LaTeX manuscripts for citations
- **Manuscript model**: Track manuscripts and their citations
- **CitationLocation model**: Track where papers are cited
- **PaperContent model**: Store extracted paper content for AI
- **ProjectRelevance model**: Track paper relevance to projects

#### API Routers
- **citations.py**: Manuscript CRUD, citation scanning, BibTeX export
- **integration.py**: Paper content, project relevance, extraction queue

#### Scripts & CLI
- **citation_mapping.py**: CLI for citation/BibTeX operations

#### Code Quality
- All Pydantic schemas updated to ConfigDict (v2 compatible)
- PyPDF2 replaced with pypdf
- 124 unit tests passing, 0 warnings
- Flake8 linting clean

#### Governance
- Hookify rules for code quality enforcement
- Overnight dev configuration with mamba

### Changed
- Author ordering now tracked via position column
- Database migrated from standalone (25 MB, 2356 papers)
- Search index migrated (3.3 MB)
- All API credentials consolidated in .env

---

## [1.0.0] - 2024-09-08

### Initial Monorepo Integration Release

This release transforms the Literature Database from a standalone CLI tool into a full-featured microservice ready for monorepo integration.

### Added

#### FastAPI Service Layer
- **REST API** with comprehensive endpoints on port 8001
- **Health check** endpoint (`/health`) with detailed system status
- **API documentation** at `/docs` with interactive Swagger UI
- **CORS middleware** configured for frontend integration
- **Request middleware** with UUID tracking for request tracing

#### Event Publishing System
- **Redis integration** for real-time event publishing
- **Event schemas** for paper operations (added, updated, deleted)
- **Sync events** for Zotero synchronization status
- **Graceful degradation** when Redis is unavailable

#### Service Configuration
- **Environment-based config** with `.env` support
- **Centralized configuration** management in `src/config.py`
- **Backward compatibility** with existing `config/settings.yml`

#### Docker Configuration
- **Multi-stage Dockerfile** with development and production targets
- **Development compose** with SQLite + Redis
- **Production compose** with PostgreSQL + Redis
- **Health checks** for all services

### API Endpoints
```
/health                    # Service health and status
/docs                      # Interactive API documentation
/api/v1/papers            # CRUD operations for papers
/api/v1/papers/{id}       # Individual paper operations
/api/v1/search            # Full-text search functionality
/api/v1/sync/zotero       # Zotero synchronization
/api/v1/sync/zotero/{id}  # Sync status monitoring
/api/v1/citations/*       # Citation management (v1.1.0)
/api/v1/integration/*     # AI integration endpoints (v1.1.0)
```

### Event Types
- **paper.added** - Published when new papers are created
- **paper.updated** - Published when paper metadata changes
- **paper.deleted** - Published when papers are removed
- **sync.completed** - Published when Zotero sync finishes

---

## Pre-Monorepo Features

### Manuscript Collections System
- Complete manuscript citation management workflow
- Create collections for organizing papers by writing project
- Search-based paper discovery and addition
- Automatic BibTeX bibliography generation

### PDF Reference Linking
- Efficient PDF storage through Zotero reference linking
- Automatic SHA256 hash-based deduplication
- Batch processing with progress indicators

### Zotero Integration
- Local Zotero API integration
- Author ordering preservation
- DOI and metadata extraction
- WSL2 networking support

---

## Technical Details

### Service Architecture
- **Port**: 8001
- **Database**: SQLite (development) / PostgreSQL (production)
- **Events**: Redis pub/sub for inter-service communication
- **API Version**: v1

### Current Statistics
- 2356 papers with author ordering
- 124 unit tests passing
- Full citation management capability

---

## Quick Start

```bash
# Run tests
/home/dreece23/miniforge3/bin/mamba run -n litdb python -m pytest tests/unit/ -q

# Start service
python run_service.py

# Docker
docker-compose up -d
```
