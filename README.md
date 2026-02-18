# Research - Literature Management System

A unified research environment with intelligent literature management accessible via MCP (Model Context Protocol) for Claude Code and Claude Desktop.

## Quick Start

### 1. Verify Setup

```bash
cd src
mamba run -n litai python -m scripts.health_check
```

Expected output:
```
[PASS] Database: Database OK: 418 papers
[PASS] Services: PaperService OK
[PASS] Embeddings: OK
[PASS] Keyword Search: OK
[PASS] Semantic Search: OK
ALL CHECKS PASSED
```

### 2. Use with Claude Code

The MCP server is configured in `.mcp.json`. Claude Code will automatically connect to the literature server when you open this project.

Available commands:
- Search papers: "Find papers about ALD precursor chemistry"
- Generate citations: "Generate BibTeX for papers 42, 55, 78"
- Check thesis: "Verify citations in my chapter.tex"
- Enrich metadata: "Get citation count for paper 123"

## Architecture

```
research/
├── src/                    # Consolidated source code
│   ├── literature_core/    # Database models, ORM, config
│   ├── services/           # Business logic layer
│   ├── mcp_server/         # MCP server for Claude
│   ├── embeddings/         # Vector search (ChromaDB)
│   ├── extractors/         # Zotero sync
│   └── scripts/            # Utilities (health_check, backup)
├── tests/                  # Comprehensive test suite
│   ├── integration/        # MCP tool integration tests
│   ├── unit/               # Service layer unit tests
│   └── fixtures/           # Shared test fixtures
├── data/                   # Runtime data
│   ├── sqlite/             # SQLite database
│   ├── pdfs/               # PDF storage
│   └── embeddings/         # ChromaDB vectors
├── docs/                   # Documentation
├── archive/                # Archived legacy code
└── environment.yml         # Conda environment spec
```

## Database Statistics

| Metric | Count |
|--------|-------|
| Total Papers | 418 |
| Papers with Full Text | 365 |
| Papers with PDFs | 373 |
| Collections | 3 |

## MCP Integration

See [docs/MCP_USAGE.md](docs/MCP_USAGE.md) for detailed integration guide.

### Claude Code (.mcp.json)

```json
{
  "mcpServers": {
    "literature": {
      "type": "stdio",
      "command": "/path/to/mamba",
      "args": ["run", "-n", "litai", "python", "-m", "mcp_server.server"],
      "cwd": "/path/to/research/src"
    }
  }
}
```

## Search Capabilities

The system features **hybrid search** combining keyword (BM25) and semantic (vector) search:

```
# Recommended: Hybrid search for comprehensive discovery
hybrid_search("ALD precursor chemistry")

# Keyword-only: When you need exact term matches
keyword_search("hafnium oxide")

# Semantic: Find conceptually similar papers
semantic_search("thin film growth mechanisms")

# Check search health
get_search_status(detailed=true)
```

See [Search Architecture](docs/SEARCH.md) for details on FTS5, ChromaDB, and Reciprocal Rank Fusion.

## Documentation

### Workflow Guides (for Claude)
- [Paper Import Workflow](docs/PAPER_IMPORT_WORKFLOW.md) - Importing, processing, and completing papers
- [Research Workflow](docs/RESEARCH_WORKFLOW.md) - Search, citations, and manuscript support
- [Claude Extraction Workflow](docs/CLAUDE_EXTRACTION_WORKFLOW.md) - AI-powered paper extraction

### Reference
- [MCP Integration Guide](docs/MCP_USAGE.md) - How to use with Claude
- [Tool Reference](docs/TOOL_REFERENCE.md) - All MCP tool signatures
- [Search Architecture](docs/SEARCH.md) - FTS5, ChromaDB, hybrid search
- [Source Code Guide](src/README.md) - Code structure
- [Development Commands](docs/DEVELOPMENT_COMMANDS.md) - Dev workflow
- [Claude Governance](CLAUDE.md) - AI agent guidelines