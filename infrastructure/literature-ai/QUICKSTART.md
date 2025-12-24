# Literature AI MCP Server - Quickstart

## Current State (2025-12-23)

**Branch**: `feature/mcp-plugin`
**Last commit**: `95fe640` - VPN and OpenURL resolver support for PDF acquisition

### What's Working
- MCP server with 50+ tools for literature management
- Paper CRUD, search (keyword + semantic), external API lookups
- PDF acquisition with multiple strategies (open access, VPN, OpenURL, EZProxy)
- Project-level citation management (BibTeX parsing, health checks)
- Collections, notes, import/export

### Database Status
- **416 papers** in database
- **79 have PDFs**, 21 need PDFs
- **0 papers** in extraction queue

## Quick Commands

### Run Tests
```bash
cd /home/dreece23/projects/research/misc/research/infrastructure/literature-ai
/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q
```

### Start Database API (required for MCP server)
```bash
cd /home/dreece23/projects/research/misc/research/infrastructure/literature-database
/home/dreece23/miniforge3/bin/mamba run -n litai uvicorn src.api.main:app --port 8001
```

### Test MCP Server Standalone
```bash
cd /home/dreece23/projects/research/misc/research/infrastructure/literature-ai
/home/dreece23/miniforge3/bin/mamba run -n litai python -m src.mcp_server.server
```

## PDF Acquisition

### Method 1: Browser Automation (Recommended for VPN)

Since the MCP server runs in WSL and can't use Windows VPN, use browser automation:

**One-time setup (Windows PowerShell/CMD):**
```cmd
cd C:\Users\dreec\literature-ai
setup.bat
```

**Workflow:**
```python
# 1. Queue papers for download (MCP tool)
queue_batch_pdf_download(paper_ids=[1, 3, 4, 9, 17, 18, 20, 23, 24, 25, 26])

# 2. Start the fetcher on Windows (while on VPN)
# Double-click: C:\Users\dreec\literature-ai\start_fetcher.bat
# Or run: python pdf_fetcher.py --watch

# 3. Browser opens, handle any login prompts
# 4. Process downloaded PDFs (MCP tool)
process_downloaded_pdfs()
```

**Check status:**
```python
get_download_queue_status()
```

### Method 2: Direct Download (for Open Access)

```python
acquire_paper_pdf(paper_id=3)  # Tries open access sources
```

Supported publishers: Elsevier, ACS, Wiley, Nature, Springer, RSC, Taylor&Francis, MDPI

## Pending Work

1. **Paper 392** needs manual DB cleanup (has linked content, couldn't delete)
2. **21 papers** still need PDFs - test with user on VPN
3. **OpenURL resolver** may need HTML parsing adjustments for UW Primo

## Current Session (2025-12-23)

**Key Finding**: MCP server runs server-side and cannot use local VPN connection.

### What was done:
- ✅ All 70 tests pass
- ✅ Fixed Elsevier URL construction to handle `linkinghub.elsevier.com` URLs
- ✅ Verified correct PII lookup: DOI `10.1016/j.memsci.2020.118610` → PII `S037673882031187X`
- ❌ **VPN limitation**: MCP server cannot download from publishers because it runs on server (WSL), not local machine with VPN

### Workaround Options:
1. **Manual download**: User downloads PDFs in browser while on VPN
2. **Proxy the MCP server through VPN** - requires network configuration
3. **Use OpenURL resolver** - but Primo response parsing may need work

### Papers needing PDFs (21 total):
IDs: 1, 3, 4, 9, 17, 18, 20, 23, 24, 25, 26, 45, 46, 49, 59, 62, 66, 68, 84, 87, 96
All have DOIs (mostly Elsevier memsci journals - DOI prefix 10.1016)

## Key Files

| File | Purpose |
|------|---------|
| `src/mcp_server/server.py` | Main MCP server, tool routing |
| `src/mcp_server/tools/pdf.py` | PDF acquisition (VPN/OpenURL added) |
| `src/mcp_server/tools/project.py` | Project-level citation tools (14 tools) |
| `src/mcp_server/tools/papers.py` | Core paper CRUD |
| `src/mcp_server/tools/search.py` | Keyword + semantic search |
| `src/mcp_server/tools/external.py` | CrossRef, OpenAlex, arXiv APIs |

## Paper2 Integration

MCP config at `/home/dreece23/projects/research/Paper2/.mcp.json`:
```json
{
  "mcpServers": {
    "literature": {
      "type": "stdio",
      "command": "/home/dreece23/miniforge3/bin/mamba",
      "args": ["run", "-n", "litai", "--cwd",
               "/home/dreece23/projects/research/misc/research/infrastructure/literature-ai",
               "python", "-m", "src.mcp_server.server"],
      "env": {"LITERATURE_DB_URL": "http://localhost:8001"}
    }
  }
}
```
