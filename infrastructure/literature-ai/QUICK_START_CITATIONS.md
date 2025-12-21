# Quick Start: Citation Assistance

## Prerequisites

1. **Start Ollama** (if not already running):
   ```bash
   # Check if Ollama is running
   curl http://localhost:11434/api/version

   # If not, start it
   ollama serve
   ```

2. **Activate Environment**:
   ```bash
   conda activate litai
   ```

3. **Start the API Server**:
   ```bash
   cd /home/dreece23/research/research/infrastructure/literature-ai
   uvicorn src.api.main:app --host 0.0.0.0 --port 8002 --reload
   ```

4. **Verify it's running**:
   ```bash
   curl http://localhost:8002/health
   ```

---

## Use Case 1: Find Missing Citations in Your Paper

**What it does**: Analyzes your text and identifies claims that need citations.

### Example Request:

```bash
curl -X POST http://localhost:8002/api/v1/writer/detect-missing-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Deep learning has revolutionized natural language processing in recent years. Transformer models have shown superior performance across multiple benchmarks. Self-attention mechanisms enable these models to capture long-range dependencies effectively.",
    "context": "Introduction section discussing recent advances in NLP"
  }'
```

### Example Response:

```json
{
  "claims_needing_citations": [
    {
      "claim": "Deep learning has revolutionized natural language processing in recent years",
      "reason": "Broad claim about field impact needs citation",
      "urgency": "high",
      "suggested_search": "deep learning NLP revolution"
    },
    {
      "claim": "Transformer models have shown superior performance across multiple benchmarks",
      "reason": "Performance claim requires empirical evidence",
      "urgency": "high",
      "suggested_search": "transformer models benchmark performance"
    }
  ],
  "total_claims": 2,
  "coverage_assessment": "low"
}
```

---

## Use Case 2: Get Citation Suggestions for Specific Text

**What it does**: Suggests relevant papers to cite for your text.

### Example Request:

```bash
curl -X POST http://localhost:8002/api/v1/writer/suggest-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Attention mechanisms have become fundamental to modern neural architectures, enabling models to focus on relevant parts of the input.",
    "n": 3,
    "context": "Background section on attention mechanisms"
  }'
```

### Example Response:

```json
{
  "suggestions": [
    {
      "paper_id": "vaswani2017attention",
      "title": "Attention Is All You Need",
      "authors": "Vaswani et al.",
      "year": 2017,
      "relevance_score": 0.95,
      "why_relevant": "Foundational paper introducing the Transformer architecture with self-attention",
      "citation_format": "Vaswani et al. (2017)"
    }
  ],
  "total_suggestions": 3,
  "query_used": "attention mechanisms neural architectures"
}
```

---

## Use Case 3: Enhance Existing Citations

**What it does**: Makes your citations more specific and impactful.

### Example Request:

```bash
curl -X POST http://localhost:8002/api/v1/writer/enhance-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Recent work has shown improvements in language models [Smith et al., 2023].",
    "instructions": "Make the citation more specific - what exactly did Smith show?"
  }'
```

### Example Response:

```json
{
  "enhanced_text": "Recent work has demonstrated significant improvements in few-shot learning capabilities of large language models, achieving 85% accuracy with only 10 examples [Smith et al., 2023].",
  "changes_made": [
    {
      "original": "improvements in language models",
      "enhanced": "improvements in few-shot learning capabilities of large language models, achieving 85% accuracy with only 10 examples",
      "reason": "Added specific metric and capability"
    }
  ],
  "confidence": "high"
}
```

---

## Use Case 4: Expand Outline with Citations

**What it does**: Turns bullet points into full paragraphs with proper citations.

### Example Request:

```bash
curl -X POST http://localhost:8002/api/v1/writer/expand-outline \
  -H "Content-Type: application/json" \
  -d '{
    "outline_text": "- Transformers revolutionized NLP\n- Self-attention key innovation\n- Used in BERT, GPT, T5",
    "target_length": "paragraph",
    "include_citations": true,
    "context": "Introduction paragraph"
  }'
```

### Example Response:

```json
{
  "expanded_text": "The introduction of Transformer architectures has fundamentally transformed the field of natural language processing (Vaswani et al., 2017). At the core of this innovation is the self-attention mechanism, which enables models to weigh the importance of different parts of the input sequence when making predictions (Bahdanau et al., 2015). This architectural breakthrough has been successfully adopted in numerous influential models, including BERT for bidirectional encoding (Devlin et al., 2019), GPT for autoregressive generation (Radford et al., 2018), and T5 for unified text-to-text tasks (Raffel et al., 2020).",
  "citations_added": 5,
  "word_count": 87
}
```

---

## Complete Workflow Example

Here's how to process a full section of your paper:

```bash
# 1. First, detect what needs citations
MISSING=$(curl -s -X POST http://localhost:8002/api/v1/writer/detect-missing-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your paper text here...",
    "context": "Introduction"
  }')

echo "$MISSING"

# 2. For each claim, get citation suggestions
curl -X POST http://localhost:8002/api/v1/writer/suggest-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The specific claim that needs a citation",
    "n": 5,
    "context": "Introduction"
  }'

# 3. Enhance your citations
curl -X POST http://localhost:8002/api/v1/writer/enhance-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your text with basic citations [Author, Year]",
    "instructions": "Add specific findings from the cited papers"
  }'
```

---

## Interactive API Documentation

For easier testing with a web interface:

1. Go to: http://localhost:8002/docs
2. Try out the Writer Agent endpoints:
   - POST /api/v1/writer/suggest-citations
   - POST /api/v1/writer/detect-missing-citations
   - POST /api/v1/writer/enhance-citations
   - POST /api/v1/writer/expand-outline

---

## Important Notes

### Current Limitation: Empty Vector Store

⚠️ **The vector store currently has no papers indexed!**

This means:
- Citation suggestions will return empty results
- You need to add papers to the database first

### Solution Options:

**Option A: Add papers manually (for testing)**
```python
# Python script to add a paper
from src.services.search_service import get_search_service

search = get_search_service()
search.add_paper(
    paper_id="vaswani2017",
    text="Full paper text or abstract...",
    metadata={
        "title": "Attention Is All You Need",
        "authors": "Vaswani et al.",
        "year": 2017,
        "venue": "NIPS"
    }
)
```

**Option B: Integration with literature-database** (Recommended)
- Connect to the literature-database service
- Papers will auto-sync via Redis events
- Full Zotero library becomes searchable

**Option C: Bulk import from files**
```python
# Script to import multiple papers
import json
from pathlib import Path
from src.services.search_service import get_search_service

search = get_search_service()

papers_dir = Path("path/to/papers")
for paper_file in papers_dir.glob("*.json"):
    with open(paper_file) as f:
        paper = json.load(f)
        search.add_paper(
            paper_id=paper["id"],
            text=paper["abstract"],  # or full_text
            metadata={
                "title": paper["title"],
                "authors": paper["authors"],
                "year": paper["year"]
            }
        )
```

---

## Next Steps

1. **Add some papers** to the vector store (use one of the options above)
2. **Test the endpoints** with your actual paper text
3. **Integrate with your writing workflow**

For integration with literature-database service:
- See: `../literature-database/README.md`
- The services communicate via Redis pub/sub
- Papers indexed in literature-database automatically appear here
