# Quick Extraction Workflow with Project Relevance

## Current State
- `store_extraction` tool updated to accept `project_relevance` parameter
- Stores relevance scores in `ProjectRelevance` table
- Location: `src/mcp_server/tools/papers.py`

## Extraction Task

### Steps
1. Get extraction queue: `get_extraction_queue(limit=50)`
2. For papers WITH abstracts (word_count > 0):
   - `prepare_extraction(paper_id, tier="quick")`
   - Extract: `paper_type`, `topics` (3-5), `one_sentence_summary`
   - Score `project_relevance` for both projects
   - Store via `store_extraction`
3. Skip papers with empty abstracts (word_count: 0) - flag for manual entry
4. If abstract doesn't match title semantically:
   - Look up correct abstract via `lookup_paper_metadata(doi=...)` 
   - Update paper with correct abstract, or clear if not found

### Project Relevance Schema
```json
{
  "project_relevance": {
    "thesis": {
      "relevance": "high|medium|low|none",
      "reason": "Brief explanation",
      "primary_use": "background|methods|results_comparison|discussion|none"
    },
    "paper2": {
      "relevance": "high|medium|low|none", 
      "reason": "Brief explanation",
      "primary_use": "background|methods|results_comparison|discussion|none"
    }
  }
}
```

### Projects

**thesis** - PhD Thesis: High-Throughput MLD Thin Films
- Topics: MLD, ALD, thin films, EUV lithography, tincones, alucones, zincones, hybrid organic-inorganic, reactor design, high-throughput screening, photoresist
- Focus: High-throughput screening methodology for hybrid films with EUV applications
- High relevance: MLD/ALD thin films, EUV resists, tincones/alucones/zincones, reactor design
- Medium: Related thin film techniques, photoresist chemistry, screening methods
- Low: General ALD/CVD, photolithography basics, characterization

**paper2** - Paper 2: EUV Photoresist Performance
- Topics: EUV photoresist, alucones, zincones, MLD resist, photoresist stability, outgassing, pattern transfer, dose sensitivity, line-edge roughness
- Focus: Performance evaluation of alucone/zincone hybrid films as EUV photoresist candidates
- High relevance: EUV photoresists, alucone/zincone properties, resist performance metrics
- Medium: Related photoresist chemistry, EUV challenges, hybrid film properties
- Low: General photoresist concepts, lithography methods, thin film characterization

## Batch Processing
- Prepare 10 papers in parallel
- Verify abstracts match titles
- Extract 10 papers in parallel with project relevance
- ~50 papers remaining in queue (check with `get_extraction_queue`)
