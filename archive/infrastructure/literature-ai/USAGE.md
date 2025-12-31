# Literature-AI Usage Guide

This guide provides practical examples for using the literature-ai service API.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Writer Agent Examples](#writer-agent-examples)
3. [Context Management Examples](#context-management-examples)
4. [Search & Bibliography Examples](#search--bibliography-examples)
5. [System Monitoring](#system-monitoring)
6. [Integration Patterns](#integration-patterns)

---

## Getting Started

### Start the Service

```bash
# Terminal 1: Start Ollama (if not already running)
ollama serve

# Terminal 2: Start literature-ai API
cd infrastructure/literature-ai
conda activate litai
uvicorn src.api.main:app --host 0.0.0.0 --port 8002
```

### Verify Service is Running

```bash
curl http://localhost:8002/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "literature-ai",
  "version": "0.1.0",
  "components": {
    "llm": {"status": "healthy", "ollama_reachable": true},
    "search": {"status": "healthy", "total_chunks": 0},
    "context": {"status": "healthy"},
    "gpu": {"available": true, "free_memory_gb": 6.23}
  }
}
```

---

## Writer Agent Examples

The WriterAgent provides AI-powered citation suggestions and writing assistance.

### 1. Get Citation Suggestions

Suggest relevant papers to cite for a given text passage.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/writer/suggest-citations"

data = {
    "text": "Deep learning has revolutionized computer vision, enabling models to achieve human-level performance on image classification tasks.",
    "claim": "deep learning improves computer vision",  # Optional: specific claim to support
    "n": 5,  # Number of suggestions
    "use_context": True  # Use manuscript context if available
}

response = requests.post(url, json=data)
suggestions = response.json()

for suggestion in suggestions['suggestions']:
    print(f"📄 {suggestion['title']}")
    print(f"   Authors: {suggestion['authors']}")
    print(f"   Year: {suggestion['year']}")
    print(f"   Relevance: {suggestion['relevance_score']:.2f}")
    print(f"   💡 {suggestion['contribution']}")
    print(f"   ✍️  {suggestion['integration_suggestion']}")
    print()
```

**curl Example:**
```bash
curl -X POST http://localhost:8002/api/v1/writer/suggest-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Machine learning models require large amounts of training data.",
    "n": 3
  }'
```

### 2. Expand Outline with Citations

Turn bullet points into full paragraphs with appropriate citations.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/writer/expand-outline"

data = {
    "section": "Related Work",
    "outline": """
    - Deep learning for image classification
    - Attention mechanisms in transformers
    - Transfer learning approaches
    """,
    "target_length": 300,  # Target word count
    "min_citations": 3
}

response = requests.post(url, json=data)
result = response.json()

print(f"Section: {result['section']}")
print(f"Word count: {result['word_count']}")
print(f"Citations: {result['citation_count']}\n")

for para in result['paragraphs']:
    print(f"Topic: {para['topic']}")
    print(f"Content: {para['content']}")
    print(f"Citations: {', '.join(para['citations'])}\n")
```

### 3. Detect Missing Citations

Find claims in your text that need citations.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/writer/detect-missing-citations"

data = {
    "text": """
    Neural networks have become the dominant approach in natural language processing.
    Transformers, in particular, have shown remarkable success across various tasks.
    Recent studies show that larger models consistently outperform smaller ones.
    """
}

response = requests.post(url, json=data)
result = response.json()

for claim in result['uncited_claims']:
    print(f"⚠️  Unsupported claim: {claim['text']}")
    print(f"   Reason: {claim['reason']}")
    print(f"   Suggested papers:")
    for paper in claim['suggested_papers']:
        print(f"   - {paper['title']} ({paper['year']})")
    print(f"   ✅ Revised: {claim['suggested_revision']}\n")
```

### 4. Enhance Existing Citation

Improve how a paper is cited in your text.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/writer/enhance-citation"

data = {
    "current_text": "Recent work has shown improvements in NLP [Smith et al., 2023].",
    "paper_id": "smith2023transformers"
}

response = requests.post(url, json=data)
result = response.json()

print(f"Current text:\n{result['current']}\n")
print(f"Improved text:\n{result['improved']}\n")
print(f"Specific findings added:")
for finding in result['specific_findings_added']:
    print(f"  • {finding}")
print(f"\nExplanation: {result['explanation']}")
```

---

## Context Management Examples

Load and track your manuscript for context-aware suggestions.

### 1. Load a Manuscript

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/context/load-manuscript"

data = {
    "manuscript_path": "/path/to/your/manuscript.tex",
    "set_active": True
}

response = requests.post(url, json=data)
result = response.json()

if result['success']:
    manuscript = result['manuscript']
    print(f"✅ Loaded: {manuscript['title']}")
    print(f"   Sections: {manuscript['total_sections']}")
    print(f"   Words: {manuscript['total_words']}")
    print(f"   Citations: {manuscript['total_citations']}")
    print(f"   Active section: {manuscript['active_section']}")
else:
    print(f"❌ Error: {result.get('error')}")
```

**Supported file formats:**
- LaTeX (`.tex`)
- Markdown (`.md`, `.markdown`)

### 2. Update Writing Context

Tell the agent what section you're working on.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/context/update"

data = {
    "active_section": "Introduction",
    "cursor_line": 45,
    "recent_text": "In this paper, we present a novel approach to...",
    "writing_goal": "Establish motivation for the research",
    "research_topics": ["machine learning", "computer vision"]
}

response = requests.post(url, json=data)
print(response.json())  # {"success": true, "message": "Context updated"}
```

### 3. Get Current Context

Retrieve the current writing context for your manuscript.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/context/current"

response = requests.get(url)
context = response.json()

print(f"Manuscript: {context['manuscript_title']}")
print(f"Active section: {context['active_section']}")
print(f"Section content: {context['section_content'][:100]}...")
print(f"Existing citations: {len(context['existing_citations'])}")
print(f"Writing goal: {context['writing_goal']}")
```

### 4. Get Manuscript Outline

View the structure of your manuscript.

**curl Example:**
```bash
curl http://localhost:8002/api/v1/context/outline
```

Response:
```json
{
  "title": "My Research Paper",
  "sections": [
    {
      "title": "Introduction",
      "level": 1,
      "word_count": 450,
      "citation_count": 5
    },
    {
      "title": "Related Work",
      "level": 1,
      "word_count": 620,
      "citation_count": 12
    }
  ]
}
```

---

## Search & Bibliography Examples

Search papers and generate bibliographies.

### 1. Semantic Search

Search for papers using natural language queries.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/search/"

data = {
    "query": "attention mechanisms in transformer models",
    "top_k": 10,
    "score_threshold": 0.7,  # Minimum similarity (0-1)
    "filters": {
        "year": {"$gte": 2020}  # Only papers from 2020 onwards
    }
}

response = requests.post(url, json=data)
results = response.json()

print(f"Query: {results['query']}")
print(f"Found {results['total']} results\n")

for result in results['results']:
    print(f"📄 {result['title']}")
    print(f"   Authors: {result['authors']}")
    print(f"   Year: {result['year']}")
    print(f"   Score: {result['score']:.3f}")
    print(f"   Excerpt: {result['text'][:150]}...\n")
```

### 2. Find Similar Papers

Find papers similar to a given paper.

**curl Example:**
```bash
curl -X POST http://localhost:8002/api/v1/search/similar \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": "vaswani2017attention",
    "top_k": 5
  }'
```

### 3. Generate Bibliography

Create formatted bibliography for your papers.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/search/bibliography"

data = {
    "paper_ids": [
        "vaswani2017attention",
        "devlin2019bert",
        "brown2020gpt3"
    ],
    "style": "apa",  # Options: apa, mla, chicago, bibtex
    "sort": True
}

response = requests.post(url, json=data)
result = response.json()

print(f"Bibliography ({result['style'].upper()}):\n")
print(result['bibliography'])
print(f"\n{result['paper_count']} papers")
```

**Supported citation styles:**
- `apa` - APA (American Psychological Association)
- `mla` - MLA (Modern Language Association)
- `chicago` - Chicago Manual of Style
- `bibtex` - BibTeX format

### 4. Format Inline Citation

Get properly formatted inline citation.

**Python Example:**
```python
import requests

url = "http://localhost:8002/api/v1/search/inline-citation"

data = {
    "paper_id": "vaswani2017attention",
    "style": "author-year"  # Options: author-year, numeric, superscript
}

response = requests.post(url, json=data)
citation = response.json()

print(f"Citation: {citation['citation']}")
# Output: [Vaswani et al., 2017]
```

---

## System Monitoring

Monitor service health and performance.

### 1. Health Check

**curl Example:**
```bash
curl http://localhost:8002/api/v1/health | jq
```

### 2. System Statistics

Get detailed statistics about all components.

**Python Example:**
```python
import requests

response = requests.get("http://localhost:8002/api/v1/stats")
stats = response.json()

# Embedding stats
print("Embedding Model:")
print(f"  Model: {stats['embedding_stats']['model']}")
print(f"  Dimension: {stats['embedding_stats']['dimension']}")
print(f"  Device: {stats['embedding_stats']['device']}")

# Vector store stats
print("\nVector Store:")
print(f"  Papers: {stats['vectorstore_stats']['estimated_papers']}")
print(f"  Chunks: {stats['vectorstore_stats']['count']}")
print(f"  Metric: {stats['vectorstore_stats']['distance_metric']}")

# LLM stats
print("\nLLM Service:")
print(f"  Current model: {stats['llm_stats']['current_model']}")
print(f"  Available models: {len(stats['llm_stats']['models_available'])}")
```

### 3. GPU Monitoring

Track GPU usage and temperature.

**curl Example:**
```bash
curl http://localhost:8002/api/v1/gpu | jq '.stats'
```

Response:
```json
{
  "device_id": 0,
  "total_memory_gb": 8.0,
  "used_memory_gb": 1.76,
  "free_memory_gb": 6.23,
  "memory_usage_percent": 22.0,
  "utilization_percent": 11,
  "temperature_c": 46
}
```

---

## Integration Patterns

### Text Editor Integration

Example Neovim plugin integration:

```lua
-- ~/.config/nvim/lua/litai.lua

local M = {}

function M.suggest_citations()
  -- Get visual selection
  local text = vim.fn.getreg('"')

  -- Call API
  local cmd = string.format(
    'curl -s -X POST http://localhost:8002/api/v1/writer/suggest-citations ' ..
    '-H "Content-Type: application/json" ' ..
    '-d \'{"text": "%s", "n": 5}\'',
    text:gsub('"', '\\"')
  )

  local response = vim.fn.system(cmd)
  local result = vim.fn.json_decode(response)

  -- Display suggestions
  local lines = {}
  for _, sug in ipairs(result.suggestions) do
    table.insert(lines, string.format("%s (%d) - %s",
      sug.title, sug.year, sug.contribution))
  end

  vim.api.nvim_echo({{table.concat(lines, "\n"), "Normal"}}, true, {})
end

return M
```

### Writing Workflow

Typical workflow for writing with literature-ai:

```python
import requests

base_url = "http://localhost:8002/api/v1"

# 1. Load your manuscript
requests.post(f"{base_url}/context/load-manuscript", json={
    "manuscript_path": "/path/to/paper.tex"
})

# 2. Set active section
requests.post(f"{base_url}/context/update", json={
    "active_section": "Related Work",
    "writing_goal": "Survey existing approaches"
})

# 3. Search for relevant papers
papers = requests.post(f"{base_url}/search/", json={
    "query": "neural architecture search",
    "top_k": 10
}).json()

# 4. Get citation suggestions as you write
suggestions = requests.post(f"{base_url}/writer/suggest-citations", json={
    "text": "Your paragraph here...",
    "use_context": True  # Uses loaded manuscript context
}).json()

# 5. Detect any missing citations
missing = requests.post(f"{base_url}/writer/detect-missing-citations", json={
    "text": "Your full section here..."
}).json()

# 6. Generate final bibliography
bib = requests.post(f"{base_url}/search/bibliography", json={
    "paper_ids": ["paper1", "paper2", "paper3"],
    "style": "apa"
}).json()
```

### Batch Processing

Process multiple documents:

```python
import requests
from pathlib import Path

base_url = "http://localhost:8002/api/v1"
manuscripts_dir = Path("/path/to/manuscripts")

for manuscript in manuscripts_dir.glob("*.tex"):
    print(f"Processing {manuscript.name}...")

    # Load manuscript
    response = requests.post(f"{base_url}/context/load-manuscript", json={
        "manuscript_path": str(manuscript),
        "set_active": True
    })

    # Get outline
    outline = requests.get(f"{base_url}/context/outline").json()

    # Check each section for missing citations
    for section in outline['sections']:
        requests.post(f"{base_url}/context/update", json={
            "active_section": section['title']
        })

        # Get section content and check citations
        context = requests.get(f"{base_url}/context/current").json()
        missing = requests.post(f"{base_url}/writer/detect-missing-citations", json={
            "text": context['section_content']
        }).json()

        if missing['uncited_claims']:
            print(f"  Section '{section['title']}' needs {len(missing['uncited_claims'])} citations")
```

---

## Troubleshooting

### Common Issues

**Problem**: "Connection refused" when calling API
```bash
# Solution: Make sure the server is running
uvicorn src.api.main:app --host 0.0.0.0 --port 8002
```

**Problem**: Empty search results
```bash
# Solution: Check if papers are indexed
curl http://localhost:8002/api/v1/search/stats

# If count is 0, no papers are in the vector store yet
# Papers are added automatically when the literature-database
# publishes paper.added events via Redis
```

**Problem**: Slow citation suggestions
```bash
# Solution: Check GPU memory and Ollama status
curl http://localhost:8002/api/v1/gpu

# Make sure Ollama is running
ollama ps
```

---

## Next Steps

- See [README.md](README.md) for architecture details
- View interactive API docs at http://localhost:8002/docs
- Check [config/prompts/](config/prompts/) for customizing agent behavior
- Explore [tests/](tests/) for more usage examples
