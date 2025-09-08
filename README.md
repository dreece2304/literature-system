# Research Monorepo

A unified research environment with intelligent literature management and writing assistance.

## Architecture

```
research/
├── infrastructure/          # Core services
│   ├── literature-database/ # Paper storage and metadata
│   ├── literature-ai/      # LLM services
│   ├── literature-search/  # External APIs
│   └── api-gateway/        # Service orchestration
├── active/                 # Current research projects
├── archive/               # Completed projects
├── web-dashboard/         # Frontend UI
├── shared/               # Shared code and types
└── docs/                # Documentation
```

## Quick Start

1. **Setup Infrastructure**
   ```bash
   ./scripts/setup_infrastructure.sh
   ```

2. **Start Services**
   ```bash
   ./scripts/start_dev.sh
   ```

3. **Access Dashboard**
   Open http://localhost:3000

## Services

| Service | Port | Status |
|---------|------|--------|
| API Gateway | 8000 | 🔲 Pending |
| Literature DB | 8001 | ✅ Ready |
| Literature AI | 8002 | 🔲 Pending |
| Literature Search | 8003 | 🔲 Pending |
| Web Dashboard | 3000 | 🔲 Pending |

## Documentation

- [Setup Guide](docs/SETUP_ORDER.md)
- [API Documentation](docs/API_CONTRACTS.md)
- [Development Guide](docs/DEVELOPMENT_COMMANDS.md)
- [Claude Governance](CLAUDE.md)
