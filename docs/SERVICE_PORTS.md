# Service Port Assignments

## Core Services

| Service | Port | URL | Purpose | Status |
|---------|------|-----|---------|--------|
| **API Gateway** | 8000 | http://localhost:8000 | Public entry point for all services | 🔲 Pending |
| **Literature Database** | 8001 | http://localhost:8001 | Paper storage and metadata API | ✅ In Progress |
| **Literature AI** | 8002 | http://localhost:8002 | LLM services (triage, writing, reading) | 🔲 Pending |
| **Literature Search** | 8003 | http://localhost:8003 | External paper search APIs | 🔲 Pending |
| **Web Dashboard** | 3000 | http://localhost:3000 | Frontend UI | 🔲 Pending |

## Infrastructure Services

| Service | Port | Purpose | Docker/Native |
|---------|------|---------|---------------|
| **PostgreSQL** | 5432 | Main database | Docker preferred |
| **Redis** | 6379 | Cache and job queue | Docker preferred |
| **Elasticsearch** | 9200 | Full-text search (future) | Docker |
| **Kibana** | 5601 | Elasticsearch UI (optional) | Docker |
| **Ollama** | 11434 | Local LLM server | Native |

## Development Tools

| Tool | Port | Purpose |
|------|------|---------|
| **Jupyter Lab** | 8888 | Research notebooks |
| **Flower** | 5555 | Celery monitoring (optional) |
| **pgAdmin** | 5050 | PostgreSQL admin (optional) |

## WebSocket Endpoints

| Service | Port | Purpose |
|---------|------|---------|
| **AI Streaming** | 8002 | LLM response streaming |
| **Dashboard WS** | 3001 | Real-time updates |

## API Endpoints Structure

```
http://localhost:8000/api/v1/
├── /papers             → Routes to :8001
├── /search             → Routes to :8003
├── /ai/
│   ├── /triage        → Routes to :8002
│   ├── /write         → Routes to :8002
│   └── /read          → Routes to :8002
├── /sync/
│   └── /zotero        → Routes to :8001
└── /health            → Gateway health + all services

http://localhost:8001/api/v1/  (Literature Database)
├── /papers
│   ├── GET    /       → List papers
│   ├── POST   /       → Add paper
│   ├── GET    /{id}   → Get paper
│   ├── PUT    /{id}   → Update paper
│   └── DELETE /{id}   → Delete paper
├── /authors
├── /tags
├── /collections
├── /notes
└── /sync/zotero

http://localhost:8002/api/v1/  (Literature AI)
├── /triage
│   └── POST   /       → Score and filter papers
├── /write
│   └── POST   /assist → Writing suggestions
├── /read
│   └── POST   /qa     → Answer questions about papers
├── /embed
│   └── POST   /       → Create embeddings
└── /models
    └── GET    /       → List available models

http://localhost:8003/api/v1/  (Literature Search)
├── /search
│   ├── POST   /       → Search all sources
│   ├── POST   /arxiv
│   ├── POST   /semantic_scholar
│   ├── POST   /pubmed
│   └── POST   /crossref
└── /fetch
    └── POST   /pdf    → Download PDF from URL
```

## Environment Variables

```bash
# .env file in each service
SERVICE_NAME=literature-database
SERVICE_PORT=8001
DATABASE_URL=postgresql://user:pass@localhost:5432/litdb
REDIS_URL=redis://localhost:6379
OLLAMA_URL=http://localhost:11434
API_GATEWAY_URL=http://localhost:8000

# For web dashboard
REACT_APP_API_URL=http://localhost:8000
REACT_APP_WS_URL=ws://localhost:3001
```

## Docker Compose Ports (Optional)

```yaml
version: '3.8'
services:
  postgres:
    ports:
      - "5432:5432"
  
  redis:
    ports:
      - "6379:6379"
  
  literature-db:
    ports:
      - "8001:8001"
    depends_on:
      - postgres
      - redis
  
  literature-ai:
    ports:
      - "8002:8002"
    depends_on:
      - literature-db
  
  literature-search:
    ports:
      - "8003:8003"
  
  api-gateway:
    ports:
      - "8000:8000"
    depends_on:
      - literature-db
      - literature-ai
      - literature-search
  
  web-dashboard:
    ports:
      - "3000:3000"
    depends_on:
      - api-gateway
```

## Port Conflict Resolution

If ports are already in use:

1. **Check what's using the port:**
   ```bash
   # Linux/WSL
   sudo lsof -i :8000
   
   # Or
   netstat -tlnp | grep 8000
   ```

2. **Alternative ports if needed:**
   - API Gateway: 8000 → 9000
   - Database API: 8001 → 9001
   - AI Service: 8002 → 9002
   - Search Service: 8003 → 9003
   - Dashboard: 3000 → 3001

3. **Update all references in:**
   - Service `.env` files
   - `docker-compose.yml`
   - Frontend config
   - This document

## Service Discovery

For production, consider using:
- **Consul** on port 8500
- **etcd** on port 2379
- Or use Docker's internal DNS

## Security Notes

- All services bind to `127.0.0.1` in development
- Only API Gateway should be exposed in production
- Use reverse proxy (nginx) for production deployment
- Enable CORS only for trusted origins