# Development Commands Cheatsheet

## Environment Management

### Mamba/Conda Commands
```bash
# Create new environment
mamba create -n <env_name> python=3.11 -y

# Activate environment
mamba activate <env_name>

# List environments
mamba env list

# Export environment
mamba env export > environment.yml

# Create from file
mamba env create -f environment.yml

# Update environment
mamba env update -f environment.yml

# Remove environment
mamba remove -n <env_name> --all
```

### Service-Specific Environments
```bash
# Quick activation commands
alias litai='mamba activate litai'
alias litai='mamba activate litai'
alias litsearch='mamba activate litsearch'
alias litgw='mamba activate gateway'
```

## Git Workflow Commands

### Branch Management
```bash
# Create feature branch
git checkout -b feat/service/feature-name

# Create fix branch
git checkout -b fix/service/issue-name

# Create experimental branch
git checkout -b experimental/concept-name

# List all branches
git branch -a

# Delete local branch
git branch -d branch-name

# Delete remote branch
git push origin --delete branch-name
```

### Commit Standards
```bash
# Commit formats
git commit -m "database: feat: add zotero sync"
git commit -m "ai: fix: memory leak in embeddings"
git commit -m "search: refactor: extract api clients"
git commit -m "gateway: docs: update api documentation"
git commit -m "dashboard: test: add unit tests for components"
git commit -m "monorepo: chore: update dependencies"

# Amend last commit
git commit --amend

# Interactive rebase (clean history)
git rebase -i HEAD~3
```

### Syncing and Merging
```bash
# Update from main
git checkout main
git pull origin main
git checkout your-branch
git rebase main

# Merge feature to main
git checkout main
git merge feat/service/feature-name

# Stash changes
git stash save "work in progress"
git stash pop
git stash list
```

## Database Commands

### PostgreSQL
```bash
# Connect to database
psql -U lituser -d literature_db

# Common psql commands
\l          # List databases
\dt         # List tables
\d papers   # Describe table
\q          # Quit

# Backup database
pg_dump -U lituser literature_db > backup.sql

# Restore database
psql -U lituser literature_db < backup.sql

# Drop and recreate
dropdb literature_db
createdb literature_db
```

### Alembic Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "add new column"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current version
alembic current

# Show history
alembic history

# Reset database
alembic downgrade base
alembic upgrade head
```

### SQLite Commands
```bash
# Open SQLite database
sqlite3 data/metadata/literature.db

# SQLite commands
.tables         # List tables
.schema papers  # Show table structure
.exit          # Exit

# Backup SQLite
sqlite3 literature.db ".backup backup.db"
```

## Testing Commands

### Pytest
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_api.py

# Run specific test
pytest tests/test_api.py::test_get_paper

# Run with verbose output
pytest -v

# Run with print statements
pytest -s

# Run failed tests only
pytest --lf

# Run tests matching pattern
pytest -k "test_paper"

# Parallel execution
pytest -n 4
```

### Testing Each Service
```bash
# Literature Database
cd infrastructure/literature-database
pytest tests/ -v

# Literature AI
cd infrastructure/literature-ai
pytest tests/ -v

# Literature Search
cd infrastructure/literature-search
pytest tests/ -v

# Integration tests
cd tests/integration
pytest -v
```

## API Development Commands

### FastAPI/Uvicorn
```bash
# Start development server
uvicorn src.api:app --reload --port 8001

# With specific host
uvicorn src.api:app --host 0.0.0.0 --port 8001

# With environment file
uvicorn src.api:app --env-file .env

# Production mode
uvicorn src.api:app --workers 4

# Debug mode
uvicorn src.api:app --reload --log-level debug
```

### API Testing with curl
```bash
# GET request
curl http://localhost:8001/api/v1/papers

# POST request
curl -X POST http://localhost:8001/api/v1/papers \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Paper"}'

# PUT request
curl -X PUT http://localhost:8001/api/v1/papers/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "read"}'

# DELETE request
curl -X DELETE http://localhost:8001/api/v1/papers/1

# With authentication
curl -H "Authorization: Bearer TOKEN" http://localhost:8001/api/v1/papers

# Pretty print JSON
curl http://localhost:8001/api/v1/papers | python -m json.tool
```

### HTTPie (better than curl)
```bash
# Install
pip install httpie

# GET request
http :8001/api/v1/papers

# POST request
http POST :8001/api/v1/papers title="Test Paper"

# With headers
http :8001/api/v1/papers Authorization:"Bearer TOKEN"
```

## Ollama/LLM Commands

### Model Management
```bash
# List models
ollama list

# Pull model
ollama pull qwen:7b-q4_K_M

# Run model interactively
ollama run qwen:7b

# Delete model
ollama rm model_name

# Show model info
ollama show qwen:7b
```

### API Usage
```bash
# Generate completion
curl http://localhost:11434/api/generate \
  -d '{
    "model": "qwen:7b",
    "prompt": "Hello"
  }'

# Chat completion
curl http://localhost:11434/api/chat \
  -d '{
    "model": "qwen:7b",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

## Redis Commands

### Redis CLI
```bash
# Connect to Redis
redis-cli

# Common commands
PING              # Test connection
KEYS *            # List all keys
GET key           # Get value
SET key value     # Set value
DEL key          # Delete key
FLUSHALL         # Clear all data
INFO             # Server info
MONITOR          # Watch commands

# Check queue sizes
redis-cli LLEN celery:queue:default
```

### Celery Commands
```bash
# Start worker
celery -A src.tasks worker --loglevel=info

# Start with specific queue
celery -A src.tasks worker -Q extraction,embeddings

# Start beat scheduler
celery -A src.tasks beat --loglevel=info

# Purge all tasks
celery -A src.tasks purge

# Inspect active tasks
celery -A src.tasks inspect active

# Flower monitoring
celery -A src.tasks flower
```

## Docker Commands

### Container Management
```bash
# Build image
docker build -t literature-db .

# Run container
docker run -p 8001:8001 literature-db

# List containers
docker ps -a

# Stop container
docker stop <container_id>

# Remove container
docker rm <container_id>

# View logs
docker logs <container_id>

# Execute command in container
docker exec -it <container_id> bash
```

### Docker Compose
```bash
# Start all services
docker-compose up

# Start in background
docker-compose up -d

# Stop services
docker-compose down

# Rebuild images
docker-compose build

# View logs
docker-compose logs -f service_name

# Scale service
docker-compose up --scale worker=3
```

## Code Quality Commands

### Formatting
```bash
# Format with black
black src/ tests/

# Check without changing
black --check src/

# Format specific file
black src/api.py
```

### Linting
```bash
# Run pylint
pylint src/

# Run flake8
flake8 src/

# Run mypy (type checking)
mypy src/
```

### Pre-commit Hooks
```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files

# Update hooks
pre-commit autoupdate
```

## Monitoring Commands

### System Monitoring
```bash
# GPU usage
nvidia-smi
watch -n 1 nvidia-smi

# CPU and memory
htop
top

# Disk usage
df -h
du -sh *

# Network connections
netstat -tlnp
ss -tlnp

# Process tree
pstree -p
```

### Log Viewing
```bash
# Tail logs
tail -f logs/app.log

# Tail multiple files
tail -f logs/*.log

# Search in logs
grep ERROR logs/app.log

# Last 100 lines
tail -n 100 logs/app.log

# Follow systemd logs
journalctl -f -u service_name
```

## Utility Scripts

### Health Check
```bash
#!/bin/bash
# scripts/health_check.sh

for port in 8000 8001 8002 8003; do
    if curl -s "http://localhost:$port/health" > /dev/null; then
        echo "✅ Service on port $port is healthy"
    else
        echo "❌ Service on port $port is down"
    fi
done
```

### Backup Script
```bash
#!/bin/bash
# scripts/backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/$DATE"

mkdir -p $BACKUP_DIR

# Backup database
pg_dump -U lituser literature_db > "$BACKUP_DIR/database.sql"

# Backup PDFs
tar -czf "$BACKUP_DIR/pdfs.tar.gz" data/pdfs/

# Backup configs
cp -r config/ "$BACKUP_DIR/config/"

echo "Backup completed: $BACKUP_DIR"
```

### Quick Start Script
```bash
#!/bin/bash
# scripts/quick_start.sh

# Start infrastructure
redis-server --daemonize yes
ollama serve &

# Start services in tmux
tmux new-session -d -s research
tmux send-keys -t research "cd infrastructure/literature-database && mamba activate litai && uvicorn src.api:app --port 8001" C-m
tmux new-window -t research
tmux send-keys -t research "cd infrastructure/literature-ai && mamba activate litai && uvicorn src.api:app --port 8002" C-m

# Attach to tmux
tmux attach -t research
```

## Troubleshooting Commands

### Port Debugging
```bash
# Find process using port
lsof -i :8001
netstat -tulpn | grep 8001
ss -tulpn | grep 8001

# Kill process on port
kill $(lsof -t -i:8001)
fuser -k 8001/tcp
```

### Python Debugging
```bash
# Start Python debugger
python -m pdb script.py

# IPython shell
ipython

# Debug FastAPI
uvicorn src.api:app --reload --log-level debug
```

### Memory Debugging
```bash
# Python memory profiler
pip install memory_profiler
python -m memory_profiler script.py

# GPU memory
nvidia-smi --query-gpu=memory.used --format=csv

# Clear GPU cache (in Python)
import torch
torch.cuda.empty_cache()
```