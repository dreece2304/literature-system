# Service Setup Order

## Prerequisites Check

```bash
# Check system requirements
python --version          # Should be 3.11+
nvidia-smi                # Check GPU (RTX 4070 8GB)
ollama --version         # For LLM support
redis-cli ping           # Redis running
psql --version          # PostgreSQL available

# Check WSL2 (if on Windows)
wsl --list --verbose    # Should show Ubuntu/Debian
```

## Phase 1: Infrastructure Setup

### 1.1 Database Setup
```bash
# Option A: PostgreSQL (Production)
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# Create database
sudo -u postgres psql
CREATE DATABASE literature_db;
CREATE USER lituser WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE literature_db TO lituser;
\q

# Option B: SQLite (Development)
# No setup needed, will be created automatically
```

### 1.2 Redis Setup
```bash
# Install Redis
sudo apt install redis-server

# Start Redis
sudo systemctl start redis-server

# Verify
redis-cli ping  # Should return PONG
```

### 1.3 Ollama Setup (for LLM)
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve  # Keep this running in a terminal

# In another terminal, pull Qwen model
ollama pull qwen:7b-q4_K_M  # ~4GB download

# Test model
ollama run qwen:7b-q4_K_M "Hello"
```

## Phase 2: Core Services Setup

### 2.1 Literature Database Service
```bash
# Terminal 1: Database Service
cd research/infrastructure/literature-database

# Create and activate environment
mamba create -n litdb python=3.11 -y
mamba activate litdb

# Install dependencies
mamba install -c conda-forge \
    pandas sqlalchemy psycopg2-binary \
    fastapi uvicorn pyyaml python-dotenv -y

pip install \
    pyzotero pdfplumber PyPDF2 \
    bibtexparser whoosh alembic \
    click rich loguru

# Initialize database
python scripts/init_db.py

# Run migrations
alembic upgrade head

# Start service
uvicorn src.api:app --port 8001 --reload

# Verify
curl http://localhost:8001/health
```

### 2.2 Literature Search Service
```bash
# Terminal 2: Search Service
cd research/infrastructure/literature-search

# Create environment
mamba create -n litsearch python=3.11 -y
mamba activate litsearch

# Install dependencies
pip install \
    fastapi uvicorn \
    requests beautifulsoup4 \
    arxiv scholarly semanticscholar \
    httpx tenacity

# Start service
uvicorn src.api:app --port 8003 --reload

# Verify
curl http://localhost:8003/health
```

### 2.3 Literature AI Service
```bash
# Terminal 3: AI Service (requires Ollama running)
cd research/infrastructure/literature-ai

# Create environment
mamba create -n litai python=3.11 -y
mamba activate litai

# Install dependencies
mamba install -c conda-forge \
    numpy pandas scikit-learn -y

pip install \
    fastapi uvicorn \
    langchain ollama \
    chromadb sentence-transformers \
    celery redis

# Initialize vector database
python scripts/init_vectordb.py

# Start service
uvicorn src.api:app --port 8002 --reload

# Verify
curl http://localhost:8002/health
curl http://localhost:8002/api/v1/models
```

## Phase 3: Integration Layer

### 3.1 API Gateway
```bash
# Terminal 4: Gateway
cd research/infrastructure/api-gateway

# Create environment
mamba create -n gateway python=3.11 -y
mamba activate gateway

# Install dependencies
pip install \
    fastapi uvicorn \
    httpx aiohttp \
    redis pydantic

# Start gateway
uvicorn src.api:app --port 8000 --reload

# Verify all services through gateway
curl http://localhost:8000/health
```

### 3.2 Web Dashboard
```bash
# Terminal 5: Frontend
cd research/web-dashboard

# Install Node.js dependencies
npm install  # or yarn install

# Configure API endpoint
echo "REACT_APP_API_URL=http://localhost:8000" > .env

# Start development server
npm start  # or yarn start

# Opens browser at http://localhost:3000
```

## Phase 4: Background Workers

### 4.1 Celery Workers
```bash
# Terminal 6: Celery worker for PDF processing
cd research/infrastructure/literature-database
mamba activate litdb
celery -A src.tasks worker --loglevel=info --queue=extraction

# Terminal 7: Celery worker for embeddings
cd research/infrastructure/literature-ai
mamba activate litai
celery -A src.tasks worker --loglevel=info --queue=embeddings
```

### 4.2 Celery Beat (Scheduled Tasks)
```bash
# Terminal 8: Scheduled tasks
cd research/infrastructure/literature-database
mamba activate litdb
celery -A src.tasks beat --loglevel=info
```

## Startup Scripts

### All-in-One Development Start
```bash
#!/bin/bash
# scripts/start_dev.sh

echo "Starting Research Infrastructure..."

# Start infrastructure
echo "Starting Redis..."
redis-server --daemonize yes

echo "Starting Ollama..."
ollama serve &
OLLAMA_PID=$!
sleep 5

# Start services
echo "Starting Literature Database..."
cd infrastructure/literature-database
mamba activate litdb
uvicorn src.api:app --port 8001 --reload &
DB_PID=$!

echo "Starting Literature AI..."
cd ../literature-ai
mamba activate litai
uvicorn src.api:app --port 8002 --reload &
AI_PID=$!

echo "Starting Literature Search..."
cd ../literature-search
mamba activate litsearch
uvicorn src.api:app --port 8003 --reload &
SEARCH_PID=$!

echo "Starting API Gateway..."
cd ../api-gateway
mamba activate gateway
uvicorn src.api:app --port 8000 --reload &
GW_PID=$!

echo "All services started!"
echo "Database: http://localhost:8001"
echo "AI: http://localhost:8002"
echo "Search: http://localhost:8003"
echo "Gateway: http://localhost:8000"

# Wait for interrupt
wait
```

### Docker Compose Alternative
```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: literature_db
      POSTGRES_USER: lituser
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  literature-db:
    build: ./infrastructure/literature-database
    ports:
      - "8001:8001"
    depends_on:
      - postgres
      - redis
    environment:
      DATABASE_URL: postgresql://lituser:password@postgres:5432/literature_db
      REDIS_URL: redis://redis:6379

  # ... other services

volumes:
  postgres_data:
```

## Verification Steps

### 1. Check All Services
```bash
# Health check script
#!/bin/bash
# scripts/health_check.sh

echo "Checking services..."

check_service() {
    if curl -s "http://localhost:$2/health" > /dev/null; then
        echo "✅ $1 is running on port $2"
    else
        echo "❌ $1 is not responding on port $2"
    fi
}

check_service "API Gateway" 8000
check_service "Literature Database" 8001
check_service "Literature AI" 8002
check_service "Literature Search" 8003
check_service "Web Dashboard" 3000

# Check Ollama
if ollama list > /dev/null 2>&1; then
    echo "✅ Ollama is running"
else
    echo "❌ Ollama is not running"
fi

# Check Redis
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is running"
else
    echo "❌ Redis is not running"
fi
```

### 2. Test Basic Operations
```bash
# Test paper import
curl -X POST http://localhost:8000/api/v1/papers \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Paper", "authors": [{"name": "Test Author"}]}'

# Test search
curl "http://localhost:8000/api/v1/search?query=machine+learning"

# Test AI triage
curl -X POST http://localhost:8000/api/v1/ai/triage \
  -H "Content-Type: application/json" \
  -d '{"papers": [...], "context": "reinforcement learning"}'
```

## Troubleshooting

### Port Already in Use
```bash
# Find process using port
sudo lsof -i :8001

# Kill process
kill -9 <PID>
```

### Ollama GPU Issues
```bash
# Check GPU is visible
nvidia-smi

# Set CUDA visible devices
export CUDA_VISIBLE_DEVICES=0

# Restart Ollama
ollama serve
```

### Database Connection Failed
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check can connect
psql -U lituser -d literature_db -h localhost

# Check credentials in .env files
```

### Redis Connection Failed
```bash
# Check Redis is running
sudo systemctl status redis-server

# Test connection
redis-cli ping

# Check Redis is listening
netstat -tlnp | grep 6379
```

## Production Deployment

For production, use:
1. Docker Compose or Kubernetes
2. Nginx as reverse proxy
3. SSL certificates
4. Environment-specific configs
5. Monitoring (Prometheus/Grafana)
6. Log aggregation (ELK stack)
7. Backup strategy for database