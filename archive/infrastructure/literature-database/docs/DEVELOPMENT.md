# Literature Database Development Guide

Development setup and workflows for the literature-database service in the research monorepo.

## 📋 Prerequisites

This assumes you have already set up the main research monorepo. If not, see the main repository setup documentation.

### Required Tools
- **Python 3.11+** (managed via monorepo environment)
- **SQLite** (for local development database)
- **Zotero** (optional, for development sync testing)
- **Redis** (optional, for event publishing development)

## 🚀 Service Development Setup

### Navigate to Service Directory

```bash
# From monorepo root
cd infrastructure/literature-database
```

### Environment Setup

```bash
# Activate the monorepo conda environment
conda activate research-monorepo

# Install service-specific dependencies (if not already installed)
pip install -r requirements.txt

# Verify CLI tools work
python -m src.cli --help
```

### Database Initialization

```bash
# Initialize development database
python -m src.cli init

# Run development verification
python scripts/test_setup.py
```

Expected output:
```
✓ All tests passed! Setup is complete.
✓ 10 tables created
✓ Directory structure validated
```

## ⚙️ Development Configuration

### Local Configuration (`config/settings.yml`)

```yaml
# Development Database Configuration  
database:
  type: "sqlite"
  path: "data/metadata/literature.db"
  
# PDF Processing (development settings)
pdf:
  storage_path: "data/pdfs"
  extract_text: true
  extract_images: false
  ocr_enabled: false  # Keep disabled for faster development
  
# Search Configuration
search:
  index_path: "data/cache/search_index"
  
# Zotero Integration (for testing)
zotero:
  windows_path: "/mnt/c/Users/[YOUR-USERNAME]/Zotero"  # If using WSL2
  library_type: "user"

# Event Publishing (optional for development)
events:
  redis_url: "redis://localhost:6379"
  enabled: true
  
# Development Logging
logging:
  level: "DEBUG"  # More verbose for development
  file: "logs/litdb.log"
```

### API Development Settings

The service runs on **port 8001** in the monorepo architecture:

```bash
# Start development API server
python run_service.py

# Or with auto-reload for development
uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload
```

Access points:
- **API Docs**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/health
- **API Base**: http://localhost:8001/api/v1/

## 🔧 Development Workflows

### 1. API Development

```bash
# Start service with auto-reload
uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload

# Test API endpoints
curl http://localhost:8001/health
curl http://localhost:8001/api/v1/papers
```

### 2. Redis Event Publishing Setup

#### Install Redis (Ubuntu/WSL2)
```bash
# Install Redis server
sudo apt update
sudo apt install redis-server

# Start Redis service
sudo systemctl start redis-server

# Enable Redis to start on boot
sudo systemctl enable redis-server

# Test Redis connection
redis-cli ping
```

#### Install Redis Python Client
```bash
# Install redis package
pip install redis

# Or add to requirements.txt
echo "redis>=4.0.0" >> requirements.txt
pip install -r requirements.txt
```

#### Test Event Publishing
```bash
# Run event publishing tests
python test_events.py

# Monitor Redis events in real-time
redis-cli monitor

# Subscribe to specific event channels
redis-cli subscribe paper.added paper.updated paper.deleted sync.completed
```

#### Event Development Workflow
```bash
# Terminal 1: Start Redis subscriber
redis-cli subscribe paper.added

# Terminal 2: Start the service
python run_service.py

# Terminal 3: Create a paper via API (triggers event)
curl -X POST http://localhost:8001/api/v1/papers \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Paper", "abstract": "Test abstract"}'

# Check Terminal 1 for published event
```

### 3. CLI Development

```bash
# Test CLI commands
python -m src.cli stats
python -m src.cli search "test"

# Debug CLI issues
python -m src.cli --debug search "test"
```

### 4. Database Development

```bash
# Reset development database
rm data/metadata/literature.db
python -m src.cli init

# Add test data
python scripts/add_papers_demo.py

# Inspect database
sqlite3 data/metadata/literature.db ".tables"
```

### 5. Search Development

```bash
# Rebuild search index
rm -rf data/cache/search_index
python -m src.cli reindex

# Test search functionality
python -m src.cli search "machine learning" --debug
```

## 🧪 Testing & Quality Assurance

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test modules
pytest tests/test_paper_service.py
pytest tests/test_search_service.py

# Run with coverage
pytest --cov=src tests/
```

### Code Quality

```bash
# Format code
black src/ scripts/ tests/

# Type checking  
mypy src/

# Linting
pylint src/
```

### Integration Testing

```bash
# Test complete workflow
python scripts/test_setup.py

# Test Zotero integration (if configured)
python scripts/test_zotero_local.py

# Test API endpoints
python scripts/test_api_endpoints.py

# Test event publishing (requires Redis)
python test_events.py
```

## 📁 Development File Structure

```
infrastructure/literature-database/
├── src/
│   ├── api/
│   │   ├── main.py           # FastAPI app (port 8001)
│   │   ├── schemas.py        # Request/response models
│   │   └── __init__.py
│   ├── services/
│   │   ├── paper_service.py  # Business logic
│   │   ├── search_service.py # Whoosh integration
│   │   ├── event_service.py  # Redis event publishing
│   │   └── __init__.py
│   ├── extractors/          # PDF and metadata processing
│   ├── utils/               # Shared utilities
│   ├── models.py            # SQLAlchemy models
│   ├── database.py          # Database connection
│   └── cli.py               # Command-line interface
├── scripts/
│   ├── test_setup.py        # Development verification
│   ├── add_papers_demo.py   # Test data generation
│   └── manuscript_collections.py
├── tests/                   # Unit and integration tests
├── config/
│   └── settings.yml         # Service configuration
├── data/
│   ├── metadata/           # SQLite database
│   ├── pdfs/              # PDF storage (dev only)
│   └── cache/             # Search index
├── run_service.py          # Service startup script
└── requirements.txt        # Python dependencies
```

### Key Development Files

**Service Entry Points:**
- `run_service.py` - Start FastAPI service (production)
- `src/api/main.py` - FastAPI application definition
- `src/cli.py` - Command-line interface

**Business Logic:**
- `src/services/paper_service.py` - CRUD operations
- `src/services/search_service.py` - Full-text search
- `src/services/event_service.py` - Redis event publishing
- `src/models.py` - Database schema

**Development Tools:**
- `scripts/test_setup.py` - Environment verification
- `scripts/add_papers_demo.py` - Generate test data
- `test_events.py` - Event publishing tests
- `tests/` - Comprehensive test suite

## 🔗 Monorepo Integration

### Shared Types Usage

```python
# Import shared types from monorepo
from shared.types.api_contracts import (
    Paper, SearchRequest, SearchResponse, 
    HealthResponse, PaginatedResponse
)

# Use in API endpoints
@app.get("/api/v1/papers", response_model=PaginatedResponse[Paper])
async def list_papers():
    pass
```

### Cross-Service Communication

```python
# Service communicates through API Gateway
# Internal service URLs use service discovery

# For development, direct service calls:
import requests
response = requests.get("http://localhost:8001/api/v1/papers")
```

### Configuration Management

```python
# Load monorepo-aware configuration
from shared.config import load_service_config
config = load_service_config("literature-database")
```

## 🐛 Debugging & Troubleshooting

### Common Development Issues

#### 1. Port Conflicts
```bash
# Check if port 8001 is in use
lsof -i :8001

# Kill conflicting process
pkill -f "uvicorn.*8001"
```

#### 2. Database Lock Issues
```bash
# Check for open database connections
fuser data/metadata/literature.db

# Reset database connections
python -c "
from src.database import engine
engine.dispose()
"
```

#### 3. Search Index Corruption
```bash
# Clear and rebuild search index
rm -rf data/cache/search_index
python -m src.cli reindex
```

### Development Logging

```bash
# Watch development logs
tail -f logs/litdb.log

# Debug specific operations
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from src.services.paper_service import PaperService
# Your debugging code here
"
```

### Performance Profiling

```bash
# Profile API endpoints
pip install py-spy
py-spy record -o profile.svg -- python run_service.py

# Memory profiling
pip install memory-profiler
python -m memory_profiler src/services/paper_service.py
```

## 📊 Development Metrics

### Health Monitoring

```bash
# Service health check
curl http://localhost:8001/health

# Database statistics
python -m src.cli stats

# Search index statistics  
python -c "
from src.services.search_service import SearchService
search = SearchService()
print(search.get_index_stats())
"
```

### Development Data

```bash
# Generate test papers
python scripts/add_papers_demo.py --count 50

# Create test collections
python scripts/manuscript_collections.py --action create --title "Dev Collection"

# Test search with various queries
python -m src.cli search "machine learning" --limit 5
```

## 🚀 Production Deployment

### Service Startup

```bash
# Production startup (via run_service.py)
python run_service.py

# Or direct uvicorn (with production settings)
uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --workers 4
```

### Configuration for Production

```yaml
# config/settings.yml (production)
logging:
  level: "INFO"
  
pdf:
  ocr_enabled: false  # Keep disabled for performance
  
search:
  batch_size: 1000   # Optimize for larger collections
```

### Docker Development (Optional)

```dockerfile
# Dockerfile for containerized development
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8001
CMD ["python", "run_service.py"]
```

```bash
# Build and run container
docker build -t literature-database .
docker run -p 8001:8001 literature-database
```

## 📝 Development Guidelines

### Code Style
- Use **Black** for formatting
- Follow **PEP 8** naming conventions
- Type hints required for public APIs
- Docstrings for all public functions

### API Design
- RESTful endpoint design
- Proper HTTP status codes
- Comprehensive error handling
- OpenAPI/Swagger documentation

### Database Changes
- Use SQLAlchemy migrations for schema changes
- Test migrations in development first
- Backup data before production migrations

### Testing Requirements
- Unit tests for all business logic
- Integration tests for API endpoints
- Mock external dependencies (Zotero)
- Minimum 80% code coverage

---

**Ready to develop on the literature-database service! 🚀**