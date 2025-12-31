# New MCP Tools - Implementation Plan

## Overview

New tools to enhance the literature management system, organized by implementation complexity.

## Phase 1: Reading & Discovery (Uses Existing Infrastructure)

### 1. Reading Queue Tools

| Tool | Description | Implementation |
|------|-------------|----------------|
| `get_reading_queue` | Get prioritized reading list | Query by read_status='unread' + priority |
| `mark_paper_read` | Quick status update | Wrapper around update_paper |
| `set_reading_priority` | Set priority (high/medium/low) | Update priority field |

**Database Support:** Paper model already has `read_status` and `priority` fields.

### 2. Similar Papers Tools

| Tool | Description | Implementation |
|------|-------------|----------------|
| `find_similar_papers` | Find papers similar to a given paper | Use VectorStore.search() with paper embedding |
| `find_papers_like_text` | Find papers matching free-form text | Embed text, search vectors |

**Infrastructure:** VectorStore already supports cosine similarity search.

### 3. Writing Assistant Tools

| Tool | Description | Implementation |
|------|-------------|----------------|
| `suggest_citations_for_text` | Given text snippet, suggest relevant papers | Embed text, search, return with citation keys |
| `get_quotable_passages` | Find passages relevant to a topic | Search chunk embeddings |

---

## Phase 2: Citation Network (Requires External APIs)

### 4. Citation Analysis Tools

| Tool | Description | Implementation |
|------|-------------|----------------|
| `get_paper_citations` | Get papers that cite a paper | Semantic Scholar /paper/{id}/citations |
| `get_paper_references` | Get papers a paper references | Semantic Scholar /paper/{id}/references |
| `find_common_references` | Papers sharing citations | Cross-reference analysis |
| `build_citation_graph` | JSON graph of citations | Aggregate citation data |

**API:** Uses existing external_search.py infrastructure with Semantic Scholar API.

---

## Phase 3: AI Extraction (Requires LLM)

### 5. Intelligent Extraction Tools

| Tool | Description | Implementation |
|------|-------------|----------------|
| `auto_extract_paper` | Generate summary/findings with LLM | Ollama + Qwen integration |
| `batch_extract_papers` | Process extraction queue | Async batch processing |
| `compare_papers` | AI comparison of two papers | LLM-based analysis |

**Requirements:** Ollama server with Qwen model (per CLAUDE.md, RTX 4070 compatible).

---

## Phase 4: Smart Organization

### 6. Tag & Organization Tools

| Tool | Description | Implementation |
|------|-------------|----------------|
| `suggest_paper_tags` | Auto-suggest tags based on content | Analyze similar papers' tags + topics |
| `find_research_gaps` | Identify unexplored areas | Topic modeling across corpus |
| `get_topic_clusters` | Cluster papers by topic | K-means on embeddings |

---

## Implementation Order

1. **Immediate (Phase 1):** Reading queue + similar papers (1-2 hours)
2. **Next (Phase 2):** Citation network tools (2-3 hours)
3. **Later (Phase 3):** LLM integration (4-6 hours, needs Ollama setup)
4. **Future (Phase 4):** Advanced organization (research)

---

## File Structure

```
src/mcp_server/tools/
├── papers.py           # Existing paper CRUD
├── search.py           # Existing search tools
├── discovery.py        # NEW: Similar papers, recommendations
├── reading.py          # NEW: Reading queue management
├── writing.py          # NEW: Writing assistant tools
├── citation_network.py # NEW: Citation graph tools
└── ai_extraction.py    # NEW: LLM-based extraction (Phase 3)
```

---

## Tool Schemas (Phase 1 Examples)

### find_similar_papers

```json
{
  "name": "find_similar_papers",
  "description": "Find papers similar to a given paper based on semantic similarity",
  "inputSchema": {
    "type": "object",
    "properties": {
      "paper_id": {
        "type": "integer",
        "description": "Paper ID to find similar papers for"
      },
      "limit": {
        "type": "integer",
        "default": 10,
        "description": "Maximum number of similar papers to return"
      },
      "min_similarity": {
        "type": "number",
        "default": 0.5,
        "description": "Minimum similarity score (0-1)"
      }
    },
    "required": ["paper_id"]
  }
}
```

### suggest_citations_for_text

```json
{
  "name": "suggest_citations_for_text",
  "description": "Suggest papers to cite for a given text snippet",
  "inputSchema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "Text snippet that needs citations"
      },
      "limit": {
        "type": "integer",
        "default": 5,
        "description": "Maximum number of suggestions"
      },
      "include_bibtex": {
        "type": "boolean",
        "default": false,
        "description": "Include BibTeX entries in response"
      }
    },
    "required": ["text"]
  }
}
```

### get_reading_queue

```json
{
  "name": "get_reading_queue",
  "description": "Get prioritized reading queue (unread papers sorted by priority)",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": {
        "type": "integer",
        "default": 20,
        "description": "Maximum papers to return"
      },
      "priority": {
        "type": "string",
        "enum": ["high", "medium", "low"],
        "description": "Filter by priority level"
      },
      "tag": {
        "type": "string",
        "description": "Filter by tag"
      }
    }
  }
}
```

---

## Testing Strategy

Each new tool module will have corresponding test file:
```
tests/integration/tools/
├── test_discovery_tools.py
├── test_reading_tools.py
├── test_writing_tools.py
└── test_citation_network_tools.py
```

Tests will use:
- In-memory database fixture
- Mock embedding generator (deterministic)
- Mock vector store (with test data)
