# Literature Database Service

A lightweight core document management service for research papers, providing a single source of truth for literature data within the research monorepo.

## Overview

The Literature Database Service is designed as a microservice within a larger research monorepo, handling PDF storage, metadata management, and Zotero synchronization. It provides a RESTful API for other services to interact with the literature data.

### Service Specifications
- **Port**: 8001
- **Health Check**: `/health`
- **API Documentation**: http://localhost:8001/docs (when running)
- **Database**: SQLite (development) / PostgreSQL (production)
- **Event Publishing**: Redis (optional)

## Quick Start

### Development Setup

1. **Activate Environment**:
   ```bash
   mamba activate litdb
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the Service**:
   ```bash
   python run_service.py
   # Service will be available at http://localhost:8001
   ```

### Docker Setup

1. **Development with SQLite**:
   ```bash
   docker-compose up -d
   ```

2. **Development with PostgreSQL**:
   ```bash
   docker-compose --profile postgres up -d
   ```

3. **Production Deployment**:
   ```bash
   cp .env.docker .env
   # Edit .env with production values
   docker-compose -f docker-compose.prod.yml up -d
   ```

## API Endpoints

### Core Paper Management

#### Get All Papers
```http
GET /papers?offset=0&limit=100&author=&title=&tags=
```
- **Query Parameters**: offset, limit, author, title, tags
- **Response**: List of papers with metadata
- **Example**: `GET /papers?author=Smith&limit=50`

#### Get Single Paper
```http
GET /papers/{paper_id}
```
- **Parameters**: paper_id (integer)
- **Response**: Paper details with authors, tags, collections
- **Example**: `GET /papers/123`

#### Add New Paper
```http
POST /papers
Content-Type: application/json

{
  "title": "Research Paper Title",
  "authors": ["John Doe", "Jane Smith"],
  "abstract": "Paper abstract...",
  "year": 2024,
  "doi": "10.1000/182",
  "tags": ["machine learning", "nlp"],
  "file_path": "/path/to/paper.pdf"
}
```

#### Update Paper
```http
PUT /papers/{paper_id}
Content-Type: application/json

{
  "title": "Updated Title",
  "tags": ["updated", "tags"]
}
```

#### Delete Paper
```http
DELETE /papers/{paper_id}
```

### Search and Discovery

#### Full-Text Search
```http
GET /search?q=machine learning&limit=50
```
- **Query Parameters**: q (query string), limit
- **Response**: Ranked search results with highlights

#### Get Authors
```http
GET /authors?limit=100
```
- **Response**: List of all authors with paper counts

#### Get Tags
```http
GET /tags?limit=100
```
- **Response**: List of all tags with usage counts

#### Get Collections
```http
GET /collections?limit=100
```
- **Response**: List of all collections with paper counts

### Zotero Integration

#### Trigger Zotero Sync
```http
POST /sync/zotero
Content-Type: application/json

{
  "user_id": "12345678",
  "api_key": "your_api_key",
  "library_type": "user"
}
```

#### Get Sync Status
```http
GET /sync/zotero/status
```

### System Endpoints

#### Health Check
```http
GET /health
```
- **Response**: Service status, database connectivity, Redis status

#### Service Information
```http
GET /info
```
- **Response**: Version, environment, configuration details

## Event Publishing

The service publishes events to Redis when configured:

### Paper Events
- `paper.added` - New paper created
- `paper.updated` - Paper metadata updated  
- `paper.deleted` - Paper removed

### Sync Events
- `sync.completed` - Zotero sync finished
- `sync.failed` - Sync encountered errors

### Event Structure
```json
{
  "event_type": "paper.added",
  "timestamp": "2024-01-01T12:00:00Z",
  "paper_id": 123,
  "paper_title": "Research Paper",
  "user_id": "user123",
  "changes": ["title", "authors"],
  "metadata": {"source": "api"}
}
```

## Monorepo Integration

### Service Discovery
- **Internal**: `http://literature-database:8001` (Docker network)
- **External**: `http://localhost:8001` (development)
- **Network**: `research-monorepo-network`

### Shared Types
The service uses shared types from `/shared/types/api_contracts.py`:
- `Paper` - Core paper model
- `Author` - Author information
- `Tag` - Tagging system
- `Collection` - Paper collections
- `PaperEvent` - Event publishing schema

### Data Flow
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────┐
│   Frontend      │    │ Literature DB    │    │   Redis     │
│   Services      │───▶│     Service      │───▶│   Events    │
└─────────────────┘    └──────────────────┘    └─────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │   Database   │
                       │ SQLite/PSQL  │
                       └──────────────┘
```

## Configuration

### Environment Variables

```bash
# Service Configuration
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8001
SERVICE_NAME=literature-database

# Database
DATABASE_URL=sqlite:///data/metadata/literature.db
# OR: postgresql://user:pass@localhost:5432/literature_db

# Redis (Optional)
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=true

# Zotero
ZOTERO_LIBRARY_TYPE=user
ZOTERO_WINDOWS_PATH=/path/to/zotero

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/litdb.log

# Development
DEBUG=false
RELOAD=false
```

### Configuration Files
- `.env` - Environment variables
- `config/settings.yml` - Legacy YAML configuration (backward compatible)
- `config/logging.yml` - Logging configuration

## Testing

### Run All Tests
```bash
# Unit tests
python -m pytest tests/ -v

# Integration tests
python -m pytest tests/test_api_integration.py -v

# Event publishing tests
python -m pytest tests/test_event_publishing.py -v
```

### Verification Script
```bash
# Comprehensive integration verification
python tests/verify_integration.py

# With detailed output
python tests/verify_integration.py --verbose

# Save report to file
python tests/verify_integration.py --save-report
```

### Manual API Testing
```bash
# Health check
curl http://localhost:8001/health

# Get papers
curl http://localhost:8001/papers?limit=10

# Search
curl "http://localhost:8001/search?q=machine%20learning"
```

## Development

### File Structure
```
├── src/                    # Core application code
│   ├── api/               # FastAPI endpoints & converters
│   ├── services/          # Business logic services
│   ├── extractors/        # PDF/document processing
│   ├── analyzers/         # Content analysis
│   ├── utils/            # Shared utilities
│   ├── models.py         # Database models
│   ├── database.py       # DB connections
│   └── config.py         # Configuration management
├── tests/                 # All tests
├── scripts/              # Standalone scripts
├── config/               # Configuration files
├── docs/                 # Documentation
├── data/                 # Data storage
└── logs/                 # Log files
```

### Adding New Features

1. **API Endpoints**: Add to `src/api/main.py`
2. **Database Models**: Update `src/models.py`
3. **Business Logic**: Create in `src/services/`
4. **Tests**: Mirror structure in `tests/`
5. **Documentation**: Update this README and API docs

### Database Schema

The service uses SQLAlchemy models with these core entities:
- **Paper** - Core document with metadata
- **Author** - Author information with many-to-many to papers
- **Tag** - Tagging system with many-to-many to papers
- **Collection** - Paper groupings
- **ZoteroMetadata** - Zotero synchronization data

## Monitoring

### Health Monitoring
```bash
# Service health
curl http://localhost:8001/health

# Database status
curl http://localhost:8001/health | jq '.database'

# Redis connectivity
curl http://localhost:8001/health | jq '.redis'
```

### Logs
```bash
# View logs
tail -f logs/litdb.log

# Docker logs
docker-compose logs -f literature-database
```

### Metrics
- Paper count: 323 (current)
- API response time: < 100ms average
- Memory usage: ~200MB typical
- Database size: ~50MB (323 papers)

## Troubleshooting

### Common Issues

1. **Port 8001 in use**:
   ```bash
   lsof -i :8001
   # Kill process or change port in docker-compose.yml
   ```

2. **Database connection**:
   ```bash
   # Check database file permissions
   ls -la data/metadata/literature.db
   
   # Reset database
   rm data/metadata/literature.db
   python -c "from src.models import Base; from src.database import get_engine, load_config; engine = get_engine(load_config()); Base.metadata.create_all(bind=engine)"
   ```

3. **Redis connection**:
   ```bash
   # Check Redis status
   redis-cli ping
   
   # Start Redis
   docker-compose up redis -d
   ```

4. **Import errors**:
   ```bash
   # Verify shared types
   ls -la ../../shared/types/api_contracts.py
   
   # Check Python path
   python -c "import sys; print(sys.path)"
   ```

### Support

- **Documentation**: See `docs/` directory
- **Issues**: Check Docker validation with `python scripts/validate_docker.py`
- **Integration**: Run `python tests/verify_integration.py`

---

**Ready for monorepo integration! 🚀**