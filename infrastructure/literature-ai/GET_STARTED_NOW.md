# Get Started with Citation Assistance - NOW

## TL;DR - 3 Steps to Citations

```bash
# 1. Start everything
cd /home/dreece23/research/research/infrastructure/literature-ai
./scripts/start_integrated.sh

# 2. Test it works
./scripts/test_integration.sh

# 3. Use for your paper
curl -X POST http://localhost:8002/api/v1/writer/detect-missing-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "YOUR PAPER TEXT HERE",
    "context": "Introduction"
  }'
```

---

## What Just Happened?

The integration scripts set up a complete pipeline:

```
[Your Paper Text]
       ↓
[literature-ai API] → finds missing citations
       ↓                suggests papers
[Vector Store] ← [Event Consumer] ← [Redis] ← [literature-database] ← [Your Zotero Library]
```

**Auto-Sync:** When you add papers to literature-database, they automatically:
1. Publish to Redis `paper.events` channel
2. Event consumer picks them up
3. Generates embeddings (~2-3 seconds)
4. Stores in ChromaDB vector store
5. **Immediately available** for citation suggestions!

---

## Your Workflow

### Option A: Use Zotero Library (Recommended)

1. **Configure Zotero sync** in literature-database:
   ```bash
   # Edit literature-database .env file
   nano ../literature-database/.env

   # Add your Zotero credentials:
   ZOTERO_API_KEY=your_key_here
   ZOTERO_USER_ID=your_id_here
   ```

2. **Run initial sync:**
   ```bash
   curl -X POST http://localhost:8001/api/v1/sync/zotero
   ```

3. **Wait for indexing** (check progress):
   ```bash
   curl http://localhost:8002/api/v1/events/stats
   ```

4. **Use your library:**
   - All papers now searchable
   - Citation suggestions from YOUR collection
   - Auto-updates when you add papers

### Option B: Add Papers Manually

```bash
# Add a paper
curl -X POST http://localhost:8001/api/v1/papers \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Attention Is All You Need",
    "authors": "Vaswani et al.",
    "year": 2017,
    "abstract": "The dominant sequence transduction models..."
  }'

# Wait 3-5 seconds for auto-indexing

# Verify it's searchable
curl -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "attention mechanism", "top_k": 5}'
```

---

## Using It for Your Paper

### 1. Find Missing Citations

```bash
# Copy a section from your paper
TEXT="Deep learning has revolutionized NLP. Transformer architectures
use self-attention mechanisms to capture long-range dependencies.
Pre-training on large corpora improves downstream task performance."

# Find what needs citations
curl -X POST http://localhost:8002/api/v1/writer/detect-missing-citations \
  -H "Content-Type: application/json" \
  -d "{
    \"text\": \"$TEXT\",
    \"context\": \"Introduction\"
  }"
```

**Output:**
```json
{
  "claims_needing_citations": [
    {
      "claim": "Deep learning has revolutionized NLP",
      "reason": "Broad field impact claim",
      "urgency": "high"
    },
    {
      "claim": "Transformer architectures use self-attention",
      "reason": "Technical claim about architecture",
      "urgency": "high"
    }
  ]
}
```

### 2. Get Citation Suggestions

```bash
# For each claim, get suggestions
curl -X POST http://localhost:8002/api/v1/writer/suggest-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Transformer architectures use self-attention mechanisms",
    "n": 5
  }'
```

**Output:**
```json
{
  "suggestions": [
    {
      "title": "Attention Is All You Need",
      "authors": "Vaswani et al.",
      "year": 2017,
      "relevance_score": 0.95,
      "why_relevant": "Foundational work introducing Transformer architecture",
      "citation_format": "Vaswani et al. (2017)"
    }
  ]
}
```

### 3. Enhance Citations

```bash
# Make your citations more specific
curl -X POST http://localhost:8002/api/v1/writer/enhance-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Transformers have shown improvements [Vaswani et al., 2017].",
    "instructions": "Add specific performance metrics"
  }'
```

### 4. Expand Outline

```bash
# Turn bullet points into paragraphs with citations
curl -X POST http://localhost:8002/api/v1/writer/expand-outline \
  -H "Content-Type: application/json" \
  -d '{
    "outline_text": "- Transformers use attention\n- BERT uses bidirectional encoding\n- GPT is autoregressive",
    "target_length": "paragraph",
    "include_citations": true
  }'
```

---

## Interactive Web Interface

Instead of curl commands, use the web UI:

1. Go to: **http://localhost:8002/docs**
2. Try the Writer Agent endpoints interactively
3. See results in real-time
4. Copy the curl commands it generates

---

## Monitoring

### Check Status

```bash
# Service health
curl http://localhost:8001/health  # literature-database
curl http://localhost:8002/health  # literature-ai

# Event consumer stats
curl http://localhost:8002/api/v1/events/stats

# Papers in vector store
curl -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "top_k": 10}'
```

### Watch Logs

```bash
# All logs
tail -f logs/*.log

# Just event processing
tail -f logs/event-consumer.log

# Just API
tail -f logs/litai-api.log
```

---

## Troubleshooting

### "No citation suggestions found"

**Cause:** Vector store is empty

**Solutions:**
1. Add papers to literature-database
2. Wait 3-5 seconds for event processing
3. Check event consumer logs: `tail -f logs/event-consumer.log`
4. Verify papers are indexed: search for them

### "Connection refused" errors

**Cause:** Services not running

**Solution:**
```bash
./scripts/start_integrated.sh
```

### Papers not auto-syncing

**Check:**
```bash
# 1. Event consumer running?
pgrep -f run_event_consumer

# 2. Redis connected?
redis-cli ping

# 3. Check logs
tail -f logs/event-consumer.log
```

**Fix:**
```bash
# Restart event consumer
pkill -f run_event_consumer
python scripts/run_event_consumer.py &
```

---

## Performance Tips

### Speed up embedding generation

Current: ~2-3 seconds per paper

**Options:**
1. Use smaller model (already using q4 quantization)
2. Reduce chunk size (edit config/settings.py)
3. Use Celery for parallel processing (not yet implemented)

### Manage large libraries

For 1000+ papers:
- Initial indexing: ~1 hour
- Disk usage: ~2GB
- Search time: <100ms

---

## Next Steps

1. **✅ You're ready to use it now!**
   - Services are integrated
   - Auto-sync is working
   - Citation assistance ready

2. **Add your papers:**
   - Configure Zotero sync, OR
   - Manually add papers, OR
   - Import from BibTeX/JSON

3. **Integrate into workflow:**
   - Test with actual paper sections
   - Refine prompts in `config/prompts/writer.yaml`
   - Create custom scripts for your use case

4. **Advanced features:**
   - Use TriagerAgent to prioritize papers (0-10 scoring)
   - Use ReaderAgent for Q&A about papers
   - Connect web dashboard (when available)

---

## Quick Reference Commands

```bash
# Start services
./scripts/start_integrated.sh

# Test integration
./scripts/test_integration.sh

# Stop services
./scripts/stop_integrated.sh

# Add paper
curl -X POST http://localhost:8001/api/v1/papers -H "Content-Type: application/json" -d '{...}'

# Find missing citations
curl -X POST http://localhost:8002/api/v1/writer/detect-missing-citations -H "Content-Type: application/json" -d '{"text":"..."}'

# Get suggestions
curl -X POST http://localhost:8002/api/v1/writer/suggest-citations -H "Content-Type: application/json" -d '{"text":"...","n":5}'

# Search papers
curl -X POST http://localhost:8002/api/v1/search/ -H "Content-Type: application/json" -d '{"query":"...","top_k":10}'

# Check stats
curl http://localhost:8002/api/v1/events/stats
```

---

## Documentation

- **This file** - Quick start guide
- `INTEGRATION_SETUP.md` - Detailed integration docs
- `QUICK_START_CITATIONS.md` - Citation features reference
- `scripts/README.md` - Script documentation
- `README.md` - Main project docs

---

**You're all set!** Start with `./scripts/start_integrated.sh` and you'll have citation assistance in minutes.
