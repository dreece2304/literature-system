# LLM Integration Plan for Literature Database

## Overview

Per CLAUDE.md governance, **LLM integration is OUT OF SCOPE** for the core `literature-database` project. This document outlines the proper architecture for LLM features.

## Architecture Strategy

### Core Project (literature-database)
**KEEPS:**
- PDF storage and metadata management
- Basic search and CRUD operations  
- RESTful API for extensions
- Zotero synchronization

**DOES NOT INCLUDE:**
- LLM models or inference
- Vector embeddings  
- Semantic search
- AI-based categorization

### Extension Project (literature-ai)
**NEW PROJECT** for LLM features:
- Qwen2.5 model integration
- Intelligent categorization and tagging
- Research paper summarization
- Semantic search and embeddings
- Question-answering over papers

## Implementation Plan

### Phase 1: API Extension Points
Add endpoints to core project to support AI features:

```python
# Core API endpoints for AI extension
GET /api/papers/{id}/raw_content    # Get paper text for AI processing
POST /api/papers/{id}/ai_metadata   # AI updates metadata
GET /api/papers/uncategorized       # Papers needing categorization
PUT /api/papers/{id}/categories     # Update AI-generated categories
```

### Phase 2: Literature-AI Project Setup
Create separate project structure:

```
literature-ai/
├── requirements.txt              # Qwen2.5, transformers, etc.
├── src/
│   ├── models/
│   │   ├── qwen_categorizer.py   # Qwen2.5 for categorization  
│   │   ├── summarizer.py         # Paper summarization
│   │   └── embeddings.py         # Vector embeddings
│   ├── services/
│   │   ├── ai_service.py         # Main AI orchestration
│   │   └── core_api_client.py    # Interface to core database
│   └── api/
│       └── ai_endpoints.py       # AI-specific API
├── models/                       # Local model storage
├── config/
└── tests/
```

### Phase 3: Qwen2.5 Integration
- Use local Qwen2.5-7B-Instruct model
- Categorize papers by field (Materials Science, Chemistry, etc.)
- Extract research themes and methodologies
- Generate intelligent summaries

## Benefits of This Architecture

### ✅ Governance Compliance
- Core project stays lightweight and focused
- AI complexity isolated in separate project
- Clean separation of concerns

### ✅ Performance
- Core operations unaffected by AI processing
- Optional AI features don't slow down basic functionality
- AI processing can run asynchronously

### ✅ Maintainability  
- Easier to update/replace AI models
- Core database operations remain stable
- Independent deployment and scaling

## Quick Fix Alternative

For immediate needs, temporarily add materials science patterns to current categorization:

```python
# Add to organize_collection.py field_patterns
'Materials Science': [
    'atomic layer deposition', 'ALD', 'molecular layer deposition', 'MLD',
    'membrane', 'nanoporous', 'thin film', 'surface modification',
    'catalysis', 'electrocatalysis', 'materials characterization'
],
'Chemical Engineering': [
    'separation', 'filtration', 'mass transfer', 'reaction engineering',
    'process optimization', 'membrane reactor', 'chemical synthesis'
]
```

## Recommendation

1. **Immediate**: Add materials science patterns for basic categorization
2. **Future**: Implement proper literature-ai project for advanced AI features
3. **Timeline**: AI project can be developed in parallel without affecting core functionality

## Next Steps

1. Add materials science categorization patterns (quick fix)
2. Define AI extension API endpoints  
3. Create literature-ai project structure
4. Integrate Qwen2.5 for intelligent processing