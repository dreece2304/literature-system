# Literature AI - Quick Start Guide

## Using with Claude Code (Recommended)

The literature system is now integrated as an MCP server for Claude Code. This means Claude Code itself becomes the AI - no local LLMs or separate API keys needed.

### Prerequisites

1. **literature-database running on port 8001**
   ```bash
   cd infrastructure/literature-database
   mamba run -n litai uvicorn src.api.main:app --port 8001
   ```

2. **MCP server configured** (already done in ~/.claude.json)

### Activate the MCP Server

**Restart Claude Code** in the research project directory. The `literature` MCP server will automatically connect.

### Available Tools (23)

Once Claude Code restarts, you can ask it to use these tools:

#### Paper Management
- `list_papers` - List papers with filtering
- `get_paper {paper_id}` - Get paper details
- `add_paper` - Add new paper
- `update_paper` - Update paper metadata
- `search_papers {query}` - Search papers
- `get_paper_content {paper_id}` - Get full content for analysis
- `store_extraction` - Store AI analysis results
- `get_extraction_queue` - Get papers needing analysis

#### Search
- `keyword_search {query}` - Full-text search
- `semantic_search {query}` - Similarity search
- `search_by_author {name}` - Find papers by author
- `search_by_tag {tag}` - Find papers by tag

#### External APIs
- `lookup_paper_metadata` - Fetch from CrossRef/OpenAlex
- `find_open_access_pdf` - Find free PDF URLs
- `enrich_paper` - Auto-fill missing metadata
- `search_external_papers {query}` - Search external databases
- `get_citation_count` - Get citation count from Semantic Scholar

#### Citations
- `scan_manuscript {file_path}` - Extract \cite{} keys
- `check_citations` - Find orphan/unused citations
- `suggest_citation_key` - Generate BibTeX keys
- `generate_bibtex` - Create BibTeX entries
- `format_bibliography` - Format in APA/MLA/Chicago
- `validate_citations` - Check citation completeness

### Example Queries

Ask Claude Code:

- "Search for papers about machine learning"
- "Get the content of paper 42 and summarize it"
- "Find open access PDFs for papers missing files"
- "Scan my manuscript and check for missing citations"
- "Generate a BibTeX bibliography for papers tagged 'neural-networks'"

---

## Using Standalone API (Legacy Mode)

If you prefer local LLM processing:

### Start Services

```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start literature-database
cd infrastructure/literature-database
mamba run -n litai uvicorn src.api.main:app --port 8001

# Terminal 3: Start literature-ai
cd infrastructure/literature-ai
mamba run -n litai uvicorn src.api.main:app --port 8002
```

### Test Services

```bash
# Check health
curl http://localhost:8001/health
curl http://localhost:8002/api/v1/health

# Search papers
curl -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "top_k": 5}'
```

### API Documentation

- literature-database: http://localhost:8001/docs
- literature-ai: http://localhost:8002/docs

---

## Data Enrichment Scripts

These scripts work independently of the API mode:

```bash
# Enrich papers missing abstracts
mamba run -n litai python scripts/enrich_papers.py

# Download open access PDFs
mamba run -n litai python scripts/acquire_pdfs.py

# Sync papers to vectorstore
mamba run -n litai python scripts/sync_papers.py
```

---

## Troubleshooting

### MCP Server Not Connecting

1. Ensure literature-database is running on port 8001
2. Check the configuration in `~/.claude.json`
3. Restart Claude Code completely (not just refresh)

### Tools Not Appearing

The MCP tools are called automatically by Claude based on your requests. Just describe what you want:
- "Search for papers about X"
- "Get the details of paper Y"
- "Find citations in my manuscript"

### API Errors

```bash
# Check if literature-database is responding
curl http://localhost:8001/api/v1/papers?limit=1

# Check MCP server can import
/home/dreece23/miniforge3/envs/litai/bin/python -c \
  "from src.mcp_server import main; print('OK')"
```

---

## Next Steps

1. **Restart Claude Code** to activate the MCP server
2. **Ask Claude to search papers** to verify it's working
3. **Try paper analysis** - ask Claude to summarize a specific paper
4. **Run enrichment scripts** to fill in missing metadata
