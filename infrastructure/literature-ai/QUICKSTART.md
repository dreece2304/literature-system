# Literature AI - Quick Start Guide

## After Running Enrichment Scripts

If you've already run `enrich_papers.py` and `acquire_pdfs.py`, here's what to do next.

### Check Results

```bash
# Activate environment
mamba activate litai

# Check how many papers have abstracts now
curl -s http://localhost:8001/api/v1/papers?limit=500 | python -c "
import json, sys
data = json.load(sys.stdin)
items = data.get('items', data)
with_abstract = sum(1 for p in items if p.get('abstract') and len(p['abstract']) > 20)
with_pdf = sum(1 for p in items if p.get('file_path'))
with_fulltext = sum(1 for p in items if p.get('full_text'))
print(f'Total papers: {len(items)}')
print(f'With abstracts: {with_abstract}')
print(f'With PDFs: {with_pdf}')
print(f'With full text: {with_fulltext}')
"
```

### Sync to Vectorstore

After enrichment, sync the updated papers to ChromaDB for semantic search:

```bash
cd /home/dreece23/projects/research/misc/research/infrastructure/literature-ai
mamba run -n litai python scripts/sync_papers.py
```

### Start Services

```bash
# Terminal 1: Start literature-database API
cd infrastructure/literature-database
mamba run -n litai uvicorn src.api.main:app --port 8001

# Terminal 2: Start literature-ai API
cd infrastructure/literature-ai
mamba run -n litai uvicorn src.api.main:app --port 8002
```

### Verify Everything Works

```bash
# Check literature-database health
curl http://localhost:8001/health

# Check literature-ai health
curl http://localhost:8002/api/v1/health

# Test semantic search
curl -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "top_k": 5}'
```

## Common Tasks

### Re-run Enrichment (if needed)
```bash
mamba run -n litai python scripts/enrich_papers.py
```

### Re-run PDF Acquisition
```bash
mamba run -n litai python scripts/acquire_pdfs.py
```

### Run Tests
```bash
# Both services
cd infrastructure/literature-database && mamba run -n litai pytest tests/ -q
cd infrastructure/literature-ai && mamba run -n litai pytest tests/ -q
```

## Next Steps

1. **Use the Writer Agent** - Get citation suggestions for your manuscripts
2. **Use the Reader Agent** - Ask questions about your paper collection
3. **Add More Papers** - Import from Zotero or manually via API

## Troubleshooting

### API Not Responding
```bash
# Check if services are running
curl http://localhost:8001/health
curl http://localhost:8002/api/v1/health
```

### Missing Abstracts After Enrichment
- Some papers may not have abstracts in any API
- Check logs for rate limiting issues
- Re-run with DEBUG logging:
  ```bash
  LOG_LEVEL=DEBUG mamba run -n litai python scripts/enrich_papers.py
  ```

### PDF Downloads Failing
- Check network connectivity
- Some PDFs are behind paywalls (only OA papers are downloaded)
- arXiv PDFs should always work

### Vectorstore Issues
```bash
# Re-sync all papers
mamba run -n litai python scripts/sync_papers.py --force
```

## API Keys Status

All API keys are configured in `.env`:
- CrossRef: ✅ Working
- OpenAlex: ✅ Working
- Semantic Scholar: ✅ Working (approved key, 1 req/sec)
- Springer: ✅ Working (Meta v2 + Open Access)
- Unpaywall: ✅ Working
- arXiv: ✅ No key needed
- PubMed: ✅ Working
