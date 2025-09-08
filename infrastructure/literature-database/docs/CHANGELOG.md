# Changelog - Literature Database Service

Changes to the literature-database service in the research monorepo.

**Service Port**: 8001 | **Monorepo Path**: `infrastructure/literature-database/`

## [2025-01-09] - Monorepo Integration & Event Publishing

### 🏗️ Architecture Changes
- **Service Integration**: Integrated into research monorepo architecture
- **Port Migration**: Service now runs on port 8001 (was 8000)
- **API Gateway**: Compatible with api-gateway routing and authentication
- **Shared Types**: Uses shared types from `shared.types.api_contracts`
- **Service Discovery**: Enhanced with health checks and service registration

### ⚡ Event Publishing System
- **Redis Integration**: Real-time event publishing for paper operations
- **Event Types**: `paper.added`, `paper.updated`, `paper.deleted`, `sync.completed`
- **Event Schema**: Standardized event structure with timestamps and metadata
- **Graceful Degradation**: Service functions normally without Redis
- **Cross-Service Communication**: Enables real-time notifications to other services

### 📚 Documentation Reorganization
- **ARCHITECTURE.md**: Combined service boundaries and current status (323 papers)
- **DEVELOPMENT.md**: Monorepo-focused development workflows
- **API.md**: Comprehensive API reference with all endpoints
- **MIGRATION.md**: Complete standalone-to-monorepo migration guide
- **Updated Paths**: All docs updated for `infrastructure/literature-database/` context

### 🔧 Service Enhancements
- **FastAPI Service**: Enhanced with health endpoints and async operations
- **Cross-Service Ready**: Prepared for literature-ai, literature-search integration
- **Redis Event Publishing**: Real-time event notifications for paper operations
- **Production Ready**: Service startup scripts and production configurations

## [2025-01-09] - Major Feature Updates & Fixes

### 🎉 Added

**Manuscript Collections System**
- Complete manuscript citation management workflow
- Create collections for organizing papers by writing project
- Search-based paper discovery and addition
- Interactive paper selection from search results
- Automatic BibTeX bibliography generation
- Related paper suggestions based on collection content
- Full CLI interface with rich formatting

**PDF Reference Linking**
- Efficient PDF storage through Zotero reference linking
- 74% PDF coverage achieved (239/323 papers)
- Eliminates duplicate PDF storage while maintaining access
- Automatic SHA256 hash-based deduplication
- Batch processing with progress indicators

**Materials Science Categorization**
- Specialized categorization for materials science research
- Categories: ALD, MLD, Electrocatalysis, Membranes, Batteries, etc.
- 400+ domain-specific keywords and patterns
- Replaces generic computer science categories

### 🔧 Fixed

**Zotero Integration Improvements**
- Fixed API endpoints from `/api/items` to `/api/users/0/items`
- Corrected JSON field access for nested Zotero data structure
- Fixed DOI constraint errors by converting empty strings to None
- Resolved WSL2 networking issues for local Zotero API access
- Paper count accuracy (323 papers vs 639 total items including attachments)

**Database & Search Fixes**
- Fixed PDF linking database commit issues with proper session management
- Fixed Whoosh index creation (replaced deprecated CLEAR method)
- Resolved Collection model creation errors
- Improved error handling and transaction management

### 📚 Documentation

**New Documentation**
- `MANUSCRIPT_COLLECTIONS.md` - Complete usage guide for citation management
- Updated `README.md` with materials science focus and new features
- Added workflow examples for manuscript bibliography generation
- Documented PDF reference linking strategy

**Updated Features**
- Architecture documentation reflects new scripts and workflows
- Configuration examples updated for PDF referencing
- Troubleshooting section expanded for WSL2 and Zotero issues

### 🏗️ Infrastructure

**Project Organization**
- Scripts properly organized by function
- Consistent error handling patterns across codebase
- Improved session management and database transactions
- Rich CLI formatting for better user experience

**Performance Improvements**
- Batch processing for PDF linking operations
- Periodic commits to avoid large database transactions
- Optimized search operations for collection management

### 📊 Statistics

**Current System Status**
- 323 papers successfully imported from Zotero
- 289 PDFs linked (89% coverage) without duplication
- Materials science categorization implemented
- Manuscript collection system fully operational
- All major Zotero integration issues resolved

### 🚀 Migration Notes

**For Existing Users**
- Run `python scripts/link_zotero_references.py --link` to enable PDF referencing
- Use `python scripts/organize_collection.py auto-categorize` to update categorization
- Create manuscript collections with `python scripts/manuscript_collections.py --action create`

**Configuration Updates**
- PDF storage now references Zotero files by default
- Materials science categories automatically applied
- No breaking changes to existing data

---

## Project Governance

This changelog follows the governance principles defined in `CLAUDE.md`:
- Single source of truth for all changes
- Complete documentation of modifications
- Clear migration paths for existing users
- Comprehensive testing and validation