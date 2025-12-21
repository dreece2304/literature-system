# Literature-AI Quickstart - Resume Tomorrow

## Current Status

### What's Working
- **literature-database** (port 8001): Fully operational with 426 papers
- **literature-ai** (port 8002): Service works, 94 papers synced to vectorstore
- All tests passing (70 tests in literature-ai, 182 tests in literature-database)
- GPU detected (RTX 4070, ~5GB VRAM available)
- Ollama connected with qwen:7b models
- Redis events enabled

### Known Issues to Fix

#### 1. Database Pagination Bug (literature-database)
**Location**: `infrastructure/literature-database/src/api/routers/papers.py` (likely)
**Issue**: Pagination returns same papers at different offsets. At offset=400 with limit=100, returns 100 items instead of 26.
**Impact**: Sync script only gets ~100 papers instead of 426.
**To test**:
```bash
curl -s 'http://localhost:8001/api/v1/papers?offset=400&limit=100' | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Expected 26, got {len(d[\"items\"])}')"
```

#### 2. Sync Script Gets Only ~100 Papers
**Location**: `infrastructure/literature-ai/scripts/sync_papers.py`
**Status**: Fixed deduplication, but limited by database pagination bug
**Workaround**: Currently syncs first 100 papers (94 with abstracts)

## Quickstart Commands

### 1. Start Services
```bash
# From infrastructure/literature-ai directory
cd /home/dreece23/projects/research/misc/research/infrastructure/literature-ai

# Start Redis (if not running)
redis-server &

# Start Ollama (if not running)
ollama serve &

# Start literature-database (in another terminal)
cd ../literature-database
/home/dreece23/miniforge3/bin/mamba run -n litai python -m uvicorn src.api.main:app --port 8001 --host 0.0.0.0

# Start literature-ai (in another terminal)
cd ../literature-ai
PYTHONPATH=. /home/dreece23/miniforge3/bin/mamba run -n litai python -m uvicorn src.api.main:app --port 8002 --host 0.0.0.0
```

### 2. Sync Papers to Vectorstore
```bash
cd /home/dreece23/projects/research/misc/research/infrastructure/literature-ai
/home/dreece23/miniforge3/bin/mamba run -n litai python scripts/sync_papers.py
```

### 3. Test Search
```bash
curl -s -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "membrane fouling", "top_k": 3}' | python3 -m json.tool
```

### 4. Test Citation Suggestions
```bash
curl -s -X POST http://localhost:8002/api/v1/writer/suggest-citations \
  -H "Content-Type: application/json" \
  -d '{"text": "Membrane fouling is a major challenge in water treatment.", "n": 3}' | python3 -m json.tool
```

## Health Check URLs
- Database: http://localhost:8001/health
- AI Service: http://localhost:8002/api/v1/health
- API Docs: http://localhost:8001/docs and http://localhost:8002/docs

## Environment
- Conda env: `litai` (consolidated from litdb + litai)
- Python: 3.11
- PyTorch with CUDA 12.1 support

## Next Steps
1. Fix pagination bug in literature-database
2. Re-run sync to get all 426 papers indexed
3. Test all AI endpoints (writer, triager, reader)
4. Set up event consumer for automatic sync
