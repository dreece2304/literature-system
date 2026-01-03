# Claude-Powered Extraction Workflow

## Key Changes (Jan 2026)
- Removed Claude API - extraction is now local-only (Ollama) OR via Claude Code session
- Added `store_full_extraction` MCP tool with all citation-matching fields
- Fixed database path: `data/literature.db` (not infrastructure/...)
- Added VLLMClient for potential YaRN extended context (not working on 8GB VRAM)

## MCP Tools for Claude Extraction
1. `get_paper_content(paper_id)` - Get paper text
2. `store_full_extraction(paper_id, ...)` - Save extraction with all fields

## Extended Fields Available
- quantitative_results: [{metric, value, unit, conditions}]
- citable_claims: Specific quotable assertions
- techniques_used: [{technique, purpose, specifics}]
- experimental_conditions: {materials, temperature_range, pressure, key_parameters}
- prior_work_comparison: [{reference_claim, this_work, improvement}]
- research_context: {problem_addressed, novelty, limitations, significance}
- citation_contexts: {introduction, methods, results, discussion}

## Files Modified
- src/config/ai_settings.py - database path, VLLMSettings, removed ClaudeSettings
- src/services/extraction_service.py - VLLMClient, removed ClaudeClient
- src/services/paper_service.py - store_extraction accepts structured_data
- src/mcp_server/tools/papers.py - store_full_extraction tool
- scripts/continuous_extraction.py - local-only backends

## For Overnight Extraction
```bash
mamba run -n litai python scripts/continuous_extraction.py
```
