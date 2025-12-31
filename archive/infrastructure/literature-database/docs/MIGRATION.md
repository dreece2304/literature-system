# Migration Guide: Standalone to Monorepo

Complete migration instructions for users upgrading from standalone literature-database to the research monorepo architecture.

## 🚀 Migration Overview

**What's Changing:**
- Literature-database becomes a service in a larger research monorepo
- Service moves from port 8000 → **8001**
- API Gateway handles routing and authentication
- Shared types and utilities across services
- Enhanced service orchestration

**What Stays the Same:**
- All your data (323 papers, collections, PDFs)
- Core functionality and CLI commands
- Zotero synchronization
- File paths and references

## 📋 Pre-Migration Checklist

### 1. Backup Your Data

**Critical**: Always backup before migration!

```bash
# Navigate to your current installation
cd ~/literature-database  # or wherever your installation is

# Backup database
cp data/metadata/literature.db ~/literature-db-backup.db

# Backup configuration
cp -r config/ ~/config-backup/

# List your current paper count for verification
python -m src.cli stats | grep "Total papers"
```

**Expected**: 323 papers, collections intact

### 2. Export Current Configuration

```bash
# Export current settings
cat config/settings.yml > ~/migration-settings.txt

# Note any custom paths or integrations
echo "Current Zotero path: $(grep windows_path config/settings.yml)" >> ~/migration-settings.txt
```

### 3. Document Custom Scripts

```bash
# List any custom scripts you've added
ls scripts/custom_* 2>/dev/null || echo "No custom scripts"

# Note any modifications to core files
git status  # If using git
```

## 🔧 Migration Steps

### Step 1: Install Monorepo

```bash
# Clone the research monorepo
cd ~/
git clone <monorepo-url> research
cd research

# Set up the conda environment
conda env create -f environment.yml
conda activate research-monorepo

# Verify monorepo structure
ls infrastructure/literature-database/
```

### Step 2: Migrate Data

```bash
# Navigate to new literature-database service
cd infrastructure/literature-database

# Copy your database
cp ~/literature-db-backup.db data/metadata/literature.db

# Migrate configuration
# Edit config/settings.yml with your previous settings
nano config/settings.yml
```

**Configuration Migration:**
```yaml
# Update these key settings:
database:
  type: "sqlite"
  path: "data/metadata/literature.db"  # ✅ Same path

# Update your Zotero path if using WSL2:  
zotero:
  windows_path: "/mnt/c/Users/[YOUR-USERNAME]/Zotero"  # Update username

# API now runs on port 8001 (not 8000)
api:
  port: 8001  # ⚠️ Changed from 8000
  host: "0.0.0.0"

# Add shared services configuration
monorepo:
  api_gateway_url: "http://localhost:8080"
  service_name: "literature-database"
```

### Step 3: Verify Data Integrity

```bash
# Initialize new service (doesn't overwrite existing data)
python -m src.cli init

# Verify all your papers are there
python -m src.cli stats

# Expected output:
# ✓ Total papers: 323
# ✓ Papers with PDFs: 289 (89%)
# ✓ Collections: [your collection count]
```

### Step 4: Update Scripts and Paths

**Update Custom Scripts:**
```bash
# If you have custom scripts, update their import paths:
# OLD: from src.models import Paper
# NEW: from src.models import Paper  # Same, no change needed

# Update any hardcoded paths:
# OLD: ~/literature-database/data/
# NEW: ~/research/infrastructure/literature-database/data/
```

**Service Port Changes:**
```bash
# Old API calls on port 8000:
# curl http://localhost:8000/api/v1/papers

# New API calls on port 8001:  
# curl http://localhost:8001/api/v1/papers

# Or via API Gateway (production):
# curl http://localhost:8080/literature-database/api/v1/papers
```

### Step 5: Test Migration

```bash
# Test CLI functionality
python -m src.cli search "machine learning" --limit 5

# Test Zotero sync (if configured)
python scripts/test_zotero_local.py

# Start service
python run_service.py

# Test API in another terminal
curl http://localhost:8001/health
```

## 🔄 Service Integration

### Accessing via API Gateway

In production, access through the API Gateway:

```bash
# Direct service access (development)
curl http://localhost:8001/api/v1/papers

# Via API Gateway (production) 
curl http://localhost:8080/literature-database/api/v1/papers
```

### Shared Types Usage

The service now uses shared types from the monorepo:

```python
# New shared type imports (automatic)
from shared.types.api_contracts import Paper, SearchRequest, SearchResponse

# Your existing scripts will work unchanged
# Internal imports still work the same way
from src.models import Paper
from src.services.paper_service import PaperService
```

## 🚨 Troubleshooting Migration Issues

### Data Not Found

**Symptom**: CLI shows 0 papers after migration

**Solution**:
```bash
# Check if database file exists
ls -la data/metadata/literature.db

# If missing, copy backup again
cp ~/literature-db-backup.db data/metadata/literature.db

# Reinitialize if needed (won't overwrite data)
python -m src.cli init
```

### Port Conflicts

**Symptom**: "Port 8001 already in use"

**Solution**:
```bash
# Check what's using port 8001
lsof -i :8001

# Kill conflicting process if safe
pkill -f "uvicorn.*8001"

# Or configure different port temporarily
uvicorn src.api.main:app --port 8002
```

### Zotero Connection Issues

**Symptom**: Sync fails after migration

**Solution**:
```bash
# Test Zotero connectivity
python scripts/test_zotero_local.py

# Update Zotero path in config
nano config/settings.yml

# If using WSL2, check networking
python scripts/fix_wsl2_networking.py
```

### Search Index Issues

**Symptom**: Search returns no results

**Solution**:
```bash
# Rebuild search index
rm -rf data/cache/search_index
python -m src.cli reindex

# Verify search works
python -m src.cli search "energy storage"
```

## 🔍 Verification Checklist

After migration, verify everything works:

### ✅ Data Integrity
- [ ] **Paper Count**: `python -m src.cli stats` shows 323 papers
- [ ] **Collections**: All collections present with correct paper counts
- [ ] **PDFs**: PDF file paths still accessible (289 papers with PDFs)
- [ ] **Authors/Tags**: All metadata preserved

### ✅ Core Functionality  
- [ ] **CLI Commands**: `python -m src.cli search "test"` works
- [ ] **API Service**: `curl http://localhost:8001/health` returns healthy
- [ ] **Search**: Full-text search returns expected results
- [ ] **Sync**: Zotero sync works (if configured)

### ✅ Integration
- [ ] **Port**: Service runs on 8001 (not 8000)
- [ ] **API Gateway**: Can access via gateway if configured
- [ ] **Shared Types**: No import errors in existing scripts
- [ ] **Configuration**: All paths and settings updated

## 🌟 New Features Available

### Monorepo Benefits

**Enhanced Architecture:**
- Service discovery and orchestration
- Centralized logging and monitoring  
- Shared authentication and authorization
- Cross-service data integration

**Future Extensions:**
- **literature-ai**: LLM integration for summarization
- **literature-search**: External API aggregation
- **literature-viz**: Advanced visualization tools
- **web-dashboard**: Modern web interface

### API Gateway Features

**Unified Access:**
```bash
# All services through single gateway
curl http://localhost:8080/literature-database/api/v1/papers
curl http://localhost:8080/literature-ai/api/v1/summarize
curl http://localhost:8080/literature-search/api/v1/discover
```

**Enhanced Security:**
- JWT authentication
- Rate limiting
- Request logging
- CORS handling

## 📈 Performance Improvements

### Service Optimizations

**Database:**
- Connection pooling
- Query optimization
- Async operations

**Search:**
- Improved indexing
- Better query parsing
- Result caching

**API:**
- FastAPI async endpoints
- Response compression
- Request validation

## 📚 Updated Documentation

### New Documentation Structure

**Service-Specific:**
- `ARCHITECTURE.md` - Service boundaries and design
- `DEVELOPMENT.md` - Development setup and workflows  
- `API.md` - Complete API reference with examples

**Cross-References:**
- Main monorepo README for system setup
- Shared utilities documentation
- Integration guides for other services

### Command Reference

**Core Commands (Unchanged):**
```bash
# Same CLI commands work as before
python -m src.cli sync
python -m src.cli search "query"
python -m src.cli stats
```

**New Service Commands:**
```bash
# Start service (new)
python run_service.py

# Health check
curl http://localhost:8001/health

# API documentation
open http://localhost:8001/docs
```

## 🎯 Next Steps After Migration

### 1. Explore New Features

```bash
# Try the enhanced API
curl http://localhost:8001/api/v1/stats

# Explore API documentation
open http://localhost:8001/docs

# Test WebSocket events (if enabled)
wscat -c ws://localhost:8001/ws/events
```

### 2. Integration Opportunities  

**With Future Services:**
- Set up literature-ai for automated summarization
- Configure literature-search for paper discovery
- Enable literature-viz for network analysis

**With Web Dashboard:**
- Access via modern web interface
- Real-time search and organization
- Collaborative features

### 3. Optimization

**Performance Tuning:**
- Monitor service metrics
- Optimize search queries
- Configure caching

**Workflow Integration:**
- Customize API workflows
- Set up automated syncing
- Configure notification events

---

## 🆘 Need Help?

### Support Resources

**Documentation:**
- Main README: `~/research/README.md`
- Service docs: `docs/` directory
- API reference: `http://localhost:8001/docs`

**Diagnostics:**
```bash
# Service health
curl http://localhost:8001/health

# Database status  
python -m src.cli stats

# Configuration check
python scripts/test_setup.py
```

**Rollback Plan:**
If migration fails, you can always return to your standalone installation using the backup files created in the pre-migration checklist.

---

**Migration Complete! Welcome to the Research Monorepo! 🎉**

Your literature database is now a robust service in a scalable research architecture, ready for enhanced functionality and cross-service integration.