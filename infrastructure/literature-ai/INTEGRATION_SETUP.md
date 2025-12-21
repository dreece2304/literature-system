# Literature-AI Integration Setup

## Overview

This guide shows you how to integrate literature-ai with literature-database so that:
1. Papers from your Zotero library automatically sync to the vector store
2. Citation suggestions use your actual paper collection
3. Everything updates in real-time via Redis events

## Architecture

```
[Zotero] → [literature-database:8001] → [Redis] → [literature-ai:8002]
                     ↓                      ↓            ↓
                 SQLite/PostgreSQL    paper.events   ChromaDB
```

**Event Flow:**
1. literature-database receives papers (from Zotero sync or API)
2. Publishes `paper.added` event to Redis channel
3. literature-ai event consumer listens on Redis
4. Automatically generates embeddings and stores in ChromaDB
5. Papers immediately available for citation suggestions

---

## Prerequisites

### 1. Redis (Already Running ✅)

```bash
# Verify Redis is running
redis-cli ping
# Should output: PONG
```

### 2. Literature Database Service

The literature-database service needs to be running on port 8001.

**Check if it's running:**
```bash
curl http://localhost:8001/health
```

**If not running, start it:**
```bash
cd /home/dreece23/research/research/infrastructure/literature-database

# Activate the database environment
mamba activate litdb

# Start the service
python run_service.py
# OR
uvicorn src.api.main:app --host 0.0.0.0 --port 8001
```

---

## Setup Steps

### Step 1: Start All Services

Use the provided startup script:

```bash
cd /home/dreece23/research/research/infrastructure/literature-ai

# Make script executable
chmod +x scripts/start_integrated.sh

# Start everything
./scripts/start_integrated.sh
```

This will start:
1. literature-database (port 8001)
2. literature-ai API (port 8002)
3. Event consumer (background process)

### Step 2: Verify Services

```bash
# Check literature-database
curl http://localhost:8001/health

# Check literature-ai
curl http://localhost:8002/health

# Check event consumer status
curl http://localhost:8002/api/v1/events/stats
```

### Step 3: Add Papers to Database

**Option A: Via Zotero Sync** (if configured)
```bash
# Trigger Zotero sync in literature-database
curl -X POST http://localhost:8001/api/v1/sync/zotero
```

**Option B: Manual Upload**
```bash
# Upload a PDF
curl -X POST http://localhost:8001/api/v1/papers \
  -F "file=@path/to/paper.pdf" \
  -F "title=Paper Title" \
  -F "authors=Author Name"
```

**Option C: Import from JSON**
```bash
# Import paper metadata
curl -X POST http://localhost:8001/api/v1/papers \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Attention Is All You Need",
    "authors": "Vaswani, A., et al.",
    "year": 2017,
    "abstract": "The dominant sequence transduction models..."
  }'
```

### Step 4: Verify Auto-Sync

```bash
# Check event consumer stats
curl http://localhost:8002/api/v1/events/stats

# Should show:
# {
#   "events_received": N,
#   "papers_processed": N,
#   "embeddings_generated": N
# }

# Search papers in vector store
curl -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "attention mechanisms", "top_k": 5}'
```

---

## Testing the Integration

### Test 1: Add Paper → Auto-Index

```bash
# 1. Add a paper to database
PAPER_ID=$(curl -s -X POST http://localhost:8001/api/v1/papers \
  -H "Content-Type: application/json" \
  -d '{
    "title": "BERT: Pre-training of Deep Bidirectional Transformers",
    "authors": "Devlin, J., et al.",
    "year": 2019,
    "abstract": "We introduce a new language representation model called BERT..."
  }' | jq -r '.id')

echo "Created paper: $PAPER_ID"

# 2. Wait 2-3 seconds for event processing
sleep 3

# 3. Search for it in literature-ai
curl -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "BERT language model", "top_k": 3}'

# Should find the paper!
```

### Test 2: Get Citation Suggestions

```bash
# Now that papers are indexed, try citation suggestions
curl -X POST http://localhost:8002/api/v1/writer/suggest-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Bidirectional transformers have shown strong performance on NLP tasks.",
    "n": 3
  }'

# Should suggest BERT and related papers
```

### Test 3: Find Missing Citations

```bash
curl -X POST http://localhost:8002/api/v1/writer/detect-missing-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Transformer models use self-attention mechanisms. Pre-training on large corpora improves downstream task performance. BERT introduced masked language modeling.",
    "context": "Introduction"
  }'
```

---

## Configuration

### Environment Variables

Create `.env` file in literature-ai directory:

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PAPER_EVENTS_CHANNEL=paper.events

# Literature Database API
LITDB_API_URL=http://localhost:8001/api/v1
LITDB_TIMEOUT=30

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_WRITER_MODEL=qwen:7b-q4_K_M
OLLAMA_TRIAGER_MODEL=qwen:7b-q4_K_M
OLLAMA_READER_MODEL=qwen:7b-q4_K_M

# ChromaDB Configuration
CHROMA_PERSIST_DIRECTORY=./data/chroma
CHROMA_COLLECTION_NAME=papers
```

### Event Consumer Configuration

The event consumer runs automatically when you start the API with event support enabled.

**Start with event consumer:**
```bash
# Using the run script
python -c "
from src.api.main import app
from src.events.consumer import PaperEventConsumer
import asyncio
import uvicorn

async def start():
    # Start event consumer in background
    consumer = PaperEventConsumer()
    asyncio.create_task(consumer.start())

    # Start API
    config = uvicorn.Config(app, host='0.0.0.0', port=8002)
    server = uvicorn.Server(config)
    await server.serve()

asyncio.run(start())
"
```

**Or use the dedicated event consumer script:**
```bash
python scripts/run_event_consumer.py
```

---

## Monitoring

### Check Event Consumer Status

```bash
# Get consumer statistics
curl http://localhost:8002/api/v1/events/stats

# Response:
# {
#   "status": "running",
#   "events_received": 10,
#   "papers_processed": 10,
#   "papers_failed": 0,
#   "embeddings_generated": 10,
#   "uptime_seconds": 300
# }
```

### View Logs

```bash
# literature-ai logs
tail -f logs/literature-ai.log

# Event consumer logs
tail -f logs/event-consumer.log

# literature-database logs
tail -f ../literature-database/logs/service.log
```

### Test Redis Events Manually

```bash
# Subscribe to events (in terminal 1)
redis-cli
SUBSCRIBE paper.events

# Publish test event (in terminal 2)
redis-cli
PUBLISH paper.events '{"event_type":"paper.added","paper_id":"test-001","timestamp":"2025-11-15T10:00:00Z"}'
```

---

## Troubleshooting

### Papers Not Appearing in Vector Store

**Check 1: Event Consumer Running?**
```bash
curl http://localhost:8002/api/v1/events/stats
# Should show status: "running"
```

**Check 2: Redis Events Being Published?**
```bash
# In literature-database, check event publishing is enabled
curl http://localhost:8001/health
# Look for redis_connected: true
```

**Check 3: Manual Sync**
```bash
# Manually trigger sync for a paper
curl -X POST http://localhost:8002/api/v1/events/sync-paper/PAPER_ID
```

### Event Consumer Crashes

**Check logs:**
```bash
tail -f logs/event-consumer.log
```

**Common issues:**
- ChromaDB directory permissions
- Ollama not running
- Out of disk space for embeddings
- GPU memory issues

**Restart consumer:**
```bash
# Stop
pkill -f "run_event_consumer"

# Start
python scripts/run_event_consumer.py &
```

### Slow Embedding Generation

**Symptoms:** Papers take >10 seconds to appear in vector store

**Solutions:**
1. Use smaller model (already using q4_K_M quantization)
2. Reduce chunk size in chunker settings
3. Use Celery for async processing (not yet implemented)

---

## Performance

### Expected Timings

| Operation | Time | Notes |
|-----------|------|-------|
| Receive event | <10ms | Redis pub/sub |
| Fetch paper from DB | 50-200ms | HTTP request |
| Generate embeddings | 1-3s | Depends on paper length |
| Store in ChromaDB | 50-100ms | Vector insertion |
| **Total (event → searchable)** | **2-5s** | End-to-end |

### Scaling Considerations

**Current limits:**
- **Sequential processing**: One paper at a time
- **Memory**: ~500MB per paper during embedding
- **Disk**: ~2MB per paper in ChromaDB

**For large libraries (1000+ papers):**
- Consider Celery for parallel processing
- Use batch embedding operations
- Monitor disk usage

---

## Next Steps

Once integrated:

1. **Test citation workflow:**
   - Add papers to literature-database
   - Use writer endpoints for citation assistance
   - Verify suggestions match your library

2. **Set up Zotero sync:**
   - Configure Zotero API in literature-database
   - Run periodic syncs
   - All papers auto-index

3. **Customize prompts:**
   - Edit `config/prompts/writer.yaml`
   - Adjust citation suggestion criteria
   - Tune for your writing style

4. **Monitor performance:**
   - Watch event consumer stats
   - Check embedding generation times
   - Optimize as needed
