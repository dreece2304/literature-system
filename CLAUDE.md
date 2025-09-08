# Claude Development Governance - Research Monorepo

## Master Project Overview

**Monorepo Name**: research
**Purpose**: Unified research environment with intelligent literature management and writing assistance
**LLM Infrastructure**: Local Qwen models via Ollama (RTX 4070 8GB VRAM compatible)
**Development Method**: Claude Code agents with strict governance

## Repository Structure
research/                          [ROOT - PROTECTED]
├── infrastructure/               [CORE SERVICES]
│   ├── literature-database/     [Agent: DB-Manager]
│   ├── literature-ai/           [Agent: AI-Builder]
│   ├── literature-search/       [Agent: Search-Builder]
│   └── api-gateway/            [Agent: Gateway-Builder]
├── active/                      [RESEARCH WORK]
│   └── */                      [User-managed]
├── archive/                    [COMPLETED WORK]
├── web-dashboard/              [Agent: UI-Builder]
├── shared/                     [SHARED UTILITIES]
│   ├── configs/
│   ├── scripts/
│   └── types/
└── docs/                       [DOCUMENTATION]

## Multi-Agent Coordination

### Agent Boundaries
Each Claude Code agent operates within assigned boundaries:

```yaml
agents:
  DB-Manager:
    owns: infrastructure/literature-database/
    can_read: [shared/, active/]
    can_write: [infrastructure/literature-database/, shared/types/]
    
  AI-Builder:
    owns: infrastructure/literature-ai/
    can_read: [all]
    can_write: [infrastructure/literature-ai/, shared/configs/]
    requires: literature-database API running
    
  Search-Builder:
    owns: infrastructure/literature-search/
    can_read: [shared/, infrastructure/literature-database/]
    can_write: [infrastructure/literature-search/]
    
  UI-Builder:
    owns: web-dashboard/
    can_read: [all]
    can_write: [web-dashboard/, shared/types/]
    
  Gateway-Builder:
    owns: infrastructure/api-gateway/
    can_read: [all]
    can_write: [infrastructure/api-gateway/]
Agent Communication Rules

No Direct Cross-Modification: Agents CANNOT modify other agents' owned directories
API Contracts: Communication happens through documented APIs only
Shared Types: Common interfaces defined in shared/types/
Change Requests: Must document in docs/agent-requests.md for cross-boundary changes
Conflict Resolution: User arbitrates any conflicts between agents

Core Governance Principles
1. SINGLE SOURCE OF TRUTH [ABSOLUTE]
Monorepo Level:

Each service owns its data domain completely
No duplicate implementations across services
Shared logic MUST be in shared/ directory
API contracts are the only integration points

Examples:

Paper metadata: ONLY in literature-database
Embeddings: ONLY in literature-ai
External API calls: ONLY in literature-search
UI components: ONLY in web-dashboard

2. FILE ORGANIZATION [STRICT]
Allowed Locations:
infrastructure/*/
  ├── src/           # Source code
  ├── tests/         # Tests (mirror src/)
  ├── config/        # Service config
  ├── scripts/       # Service scripts
  └── docs/          # Service docs

web-dashboard/
  ├── src/
  ├── public/
  ├── tests/
  └── docs/

shared/              # ONLY truly shared code
  ├── configs/       # Shared configurations
  ├── scripts/       # Cross-service scripts
  └── types/         # TypeScript/Python type definitions
FORBIDDEN:

Files in monorepo root (except .gitignore, README.md, CLAUDE.md, etc.)
Duplicate utilities across services
"temp", "old", "backup" directories
Cross-service imports except through APIs

3. ERROR HANDLING [MANDATORY]
All agents MUST follow:

Show complete error trace
Fix at the source
Verify the fix works
Test dependent services still work
Document in service's CHANGELOG.md

NEVER:

Create workarounds in different services
Add try/except to hide cross-service issues
Create "fixed" versions of files
Bypass broken APIs with direct DB access

4. GIT WORKFLOW [ENFORCED]
main                 [Protected, stable]
├── dev             [Integration branch]
├── feat/*          [New features]
├── fix/*           [Bug fixes]
├── refactor/*      [Code improvements]
└── experimental/*  [R&D work]
Commit Format:
<service>: <type>: <description>

Examples:
- database: feat: add zotero sync
- ai: fix: memory leak in embeddings
- dashboard: refactor: extract components
- monorepo: chore: update dependencies
5. DEPENDENCY MANAGEMENT [CRITICAL]
Global Rules:

Each service has its own environment/requirements
Use mamba/conda for scientific packages
Pin ALL versions exactly
Document GPU requirements explicitly

AI Service Special Requirements:
yaml# infrastructure/literature-ai/environment.yml
name: literature-ai
channels:
  - conda-forge
  - pytorch
dependencies:
  - python=3.11
  - pytorch=2.0.*  # Compatible with CUDA
  - transformers=4.*
  - pip:
    - ollama
    - langchain
    - chromadb
    
# GPU Requirements:
# - NVIDIA RTX 4070 or better
# - 8GB+ VRAM
# - CUDA 11.8+
# - Qwen model: ~4GB VRAM per 7B parameters
6. LLM CONFIGURATION [SPECIFIC]
For literature-ai service:
python# infrastructure/literature-ai/config/llm_config.py
LLM_CONFIG = {
    "provider": "ollama",
    "base_url": "http://localhost:11434",
    "models": {
        "writer": "qwen:7b-q4_K_M",      # ~4GB VRAM
        "triager": "qwen:7b-q4_K_M",     # Can share
        "reader": "qwen:14b-q4_K_M",     # ~7GB VRAM
    },
    "fallback": "qwen:7b-q4_K_M",
    "max_context": 8192,
    "temperature": {
        "writer": 0.7,
        "triager": 0.3,
        "reader": 0.1,
    }
}

# IMPORTANT: RTX 4070 8GB VRAM Limits
# - Can run 7B model with 4-bit quantization
# - Can run 14B model with aggressive quantization
# - Cannot run multiple models simultaneously
# - Must unload models between switches
7. TESTING REQUIREMENTS [MANDATORY]
Service Level:

Each service must have >80% test coverage
Integration tests for API endpoints
Unit tests for business logic

Monorepo Level:
bash# shared/scripts/test_all.sh
#!/bin/bash
# Run all service tests
for service in infrastructure/*/; do
    echo "Testing $service"
    cd $service && pytest
done

# Run integration tests
cd tests/integration && pytest
8. API CONTRACTS [IMMUTABLE]
Version Management:
python# All APIs must version endpoints
/api/v1/papers       # Current stable
/api/v2/papers       # Breaking changes
/api/experimental/   # Unstable features
Documentation Requirements:

OpenAPI/Swagger specs for each service
Shared types in shared/types/
Breaking changes require version bump
Deprecation notices 2 weeks before removal

9. CONTEXT AWARENESS [INTELLIGENT]
Active Research Context:
yaml# active/current-paper/.context
version: 1.0
project:
  name: "Neural dynamics study"
  stage: "writing"
  manuscript: "manuscript/main.tex"
  
llm_preferences:
  model: "qwen:7b"  # Override default
  style: "academic"
  citations: "apa"
  
focus:
  topics: ["reinforcement learning", "dopamine"]
  sections: ["discussion"]
  todos: ["find controversy papers", "missing citations"]
10. CHECKPOINT PROTOCOL [REQUIRED]
Every Claude agent response MUST include:
markdown## CHECKPOINT: [Task Name]

**SERVICE**: [Which service/agent]
**GOAL**: [What will be accomplished]
**FILES TO MODIFY**:
- path/to/file1.py [CREATE/MODIFY/DELETE]
- path/to/file2.py [CREATE/MODIFY/DELETE]

**IMPLEMENTATION**:
[actual code]

**VERIFICATION**:
- [ ] Tests pass
- [ ] Service starts
- [ ] API responds
- [ ] No breaking changes

**SUMMARY**: [What was done]
**NEXT STEPS**: [Suggested followup]
Performance Constraints
GPU/Memory Limits (RTX 4070 8GB)

Max model size: ~14B parameters with 4-bit quantization
Embedding batch size: 32 documents
Vector dimension limit: 768 (for efficiency)
Concurrent models: 1 (must serialize)

Service Resource Allocation
yamlresources:
  literature-database:
    ram: 2GB
    cpu: 2 cores
    
  literature-ai:
    ram: 8GB
    gpu: 7GB VRAM
    cpu: 4 cores
    
  literature-search:
    ram: 1GB
    cpu: 1 core
    
  web-dashboard:
    ram: 1GB
    cpu: 1 core
    
  api-gateway:
    ram: 512MB
    cpu: 1 core
Development Workflow
Starting New Feature
bash# 1. Agent creates feature branch
git checkout -b feat/service-name/feature-name

# 2. Agent implements with checkpoint protocol
# 3. Agent runs tests
cd infrastructure/service-name && pytest

# 4. Agent commits with proper format
git add -A
git commit -m "service: feat: description"

# 5. User reviews and merges
Debugging Protocol
bash# 1. Identify failing service
./shared/scripts/health_check.sh

# 2. Check service logs
tail -f infrastructure/*/logs/*.log

# 3. Run service tests
cd infrastructure/service-name && pytest -v

# 4. Fix at source (no workarounds!)
Inter-Service Communication
Valid Patterns
python# ✅ GOOD: Through API
response = requests.get("http://localhost:8001/api/v1/papers")

# ✅ GOOD: Through message queue
celery.send_task("literature_ai.tasks.embed")

# ✅ GOOD: Through shared types
from shared.types import PaperMetadata
Invalid Patterns
python# ❌ BAD: Direct database access
from literature_database.models import Paper

# ❌ BAD: Cross-service imports
from literature_ai.embeddings import embed

# ❌ BAD: Shared mutable state
GLOBAL_CACHE = {}  # Don't do this!
Exception Handling
When governance conflicts with best practice:

DOCUMENT: Create issue in docs/governance-exceptions.md
JUSTIFY: Explain why rule doesn't work
PROPOSE: Minimal exception needed
WAIT: User must approve
UPDATE: Modify this document if pattern will recur

Monitoring and Observability
Each service MUST implement:
python# Health check endpoint
GET /health -> {"status": "ok", "version": "1.0.0"}

# Metrics endpoint  
GET /metrics -> Prometheus format

# Structured logging
logger.info("action", extra={"service": "name", "user": "id"})
Approval Record
Developer: @dreec
Established: 2024-12-XX
Last Updated: 2024-12-XX
LLM Choice: Qwen (local via Ollama)
GPU: NVIDIA RTX 4070 8GB
Agent Assignment Log
ServiceAgentStatusLast Updatedliterature-databaseDB-ManagerActive-literature-aiAI-BuilderPending-literature-searchSearch-BuilderPending-web-dashboardUI-BuilderPending-api-gatewayGateway-BuilderPending-
Exception Log
[Exceptions will be logged here with date, service, reason, and resolution]

REMEMBER: Each Claude Code agent must respect service boundaries, follow the checkpoint protocol, and work within the constraints of the RTX 4070 8GB VRAM limit when implementing LLM features.

