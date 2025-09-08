# Literature Database Service

Core document management service for the research monorepo. Provides the single source of truth for all literature data with intelligent organization, full-text search, and seamless Zotero integration.

**Service Port**: 8001 | **API Docs**: http://localhost:8001/docs

## ✨ Features

### 📚 **Core Paper Management**
- **PDF Processing**: Automatic text extraction and metadata parsing
- **Smart Organization**: Auto-categorization by field, venue, and time period
- **Deduplication**: Hash-based duplicate detection and management
- **Full-Text Search**: Powered by Whoosh with highlighting and suggestions

### 🔄 **Zotero Integration**
- **Local API Support**: Direct integration with running Zotero instance
- **Web API Fallback**: Cloud sync when local API unavailable
- **Real-Time Sync**: Bidirectional synchronization of papers and metadata
- **Collection Mapping**: Automatic collection and tag synchronization

### 🎯 **Smart Features**
- **AI-Powered Categorization**: Automatic field detection (ML, NLP, CV, etc.)
- **Venue Recognition**: Identifies top-tier conferences and journals  
- **Author Networks**: Groups papers by prolific authors
- **Interactive Organization**: Manual review and categorization tools

### 🖥️ **Service Interfaces**
- **Command Line**: Full-featured CLI with rich output
- **REST API**: FastAPI service on port 8001
- **API Gateway**: Integrated routing via api-gateway
- **Web Dashboard**: Modern frontend via web-dashboard service

## 🚀 Quick Start

### 1. **Environment Setup**
```bash
# Navigate to service directory (from monorepo root)
cd infrastructure/literature-database

# Activate monorepo environment
conda activate research-monorepo

# Verify installation
python -m src.cli --help
```

### 2. **Initialize Database**
```bash
# Create database and directory structure
python -m src.cli init

# Verify setup
python scripts/test_setup.py
```

### 3. **Choose Your Integration**

#### Option A: Zotero Local API (Recommended)
```bash
# Test connection (make sure Zotero is running)
python scripts/test_zotero_local.py

# Sync from Zotero
python -m src.cli sync
```

#### Option B: Zotero Web API
```bash
# Interactive setup wizard
python scripts/setup_zotero.py

# Sync from Zotero
python -m src.cli sync
```

#### Option C: Direct PDF Import
```bash
# Migrate existing PDF collection
python scripts/migrate_pdfs.py "/path/to/your/pdfs" --copy --organize

# Auto-organize imported papers
python scripts/organize_collection.py auto-categorize
```

## 📖 Usage Examples

### **Command Line Interface**
```bash
# View collection statistics
python -m src.cli stats

# Search papers
python -m src.cli search "machine learning transformers"

# Add a PDF file
python -m src.cli add paper.pdf --tags "deep-learning,nlp"

# List recent papers
python -m src.cli list --limit 10

# Show paper details
python -m src.cli show 123

# Start web API server
python -m src.cli serve --host 0.0.0.0 --port 8000
```

### **Collection Organization**
```bash
# Analyze your collection
python scripts/organize_collection.py analyze

# Auto-categorize papers
python scripts/organize_collection.py auto-categorize

# Interactive paper-by-paper organization
python scripts/organize_collection.py interactive

# Get suggestions for specific paper
python scripts/organize_collection.py suggest 123
```

### **PDF Migration**
```bash
# Dry run (preview changes)
python scripts/migrate_pdfs.py "/path/to/pdfs" --dry-run

# Full migration with organization
python scripts/migrate_pdfs.py "/path/to/pdfs" --copy --organize

# Keep files in place (no copying)
python scripts/migrate_pdfs.py "/path/to/pdfs" --no-copy
```

## 🏗️ Architecture

```
literature-database/
├── src/                    # Core application
│   ├── api/               # FastAPI web server
│   ├── extractors/        # PDF and Zotero processors
│   ├── services/          # Business logic
│   ├── utils/             # Shared utilities
│   ├── models.py          # Database schema
│   ├── database.py        # Database connections
│   └── cli.py             # Command-line interface
├── scripts/               # Utility scripts
│   ├── migrate_pdfs.py    # PDF collection migration
│   ├── organize_collection.py # Materials science organization
│   ├── manuscript_collections.py # Manuscript citation management
│   ├── link_zotero_references.py # PDF reference linking
│   ├── setup_zotero.py    # Zotero setup wizard
│   └── test_*.py          # Testing utilities
├── config/               # Configuration files
│   ├── settings.yml      # Application settings
│   └── credentials.yml   # API keys (not in git)
├── data/                 # Data storage
│   ├── pdfs/            # Organized PDF storage
│   ├── metadata/        # SQLite database
│   └── cache/           # Search indices
└── tests/               # Test suite
```

## 🔧 Configuration

### **Database Settings** (`config/settings.yml`)
```yaml
database:
  type: "sqlite"
  path: "data/metadata/literature.db"

pdf:
  storage_path: "data/pdfs"  # Local PDFs (optional)
  reference_zotero: true      # Link to Zotero PDFs (efficient)
  extract_text: true
  organize_by_year: true

search:
  index_path: "data/cache/search_index"

zotero:
  windows_path: "/mnt/c/Users/[username]/Zotero"
  library_type: "user"
```

### **API Credentials** (`config/credentials.yml`)
```yaml
zotero:
  api_key: "your-zotero-api-key"
  library_id: "your-user-id"
```

## 🌐 API Endpoints

The FastAPI server provides a complete REST API:

- `GET /papers` - List papers with filtering
- `GET /papers/{id}` - Get paper details  
- `POST /papers` - Create new paper
- `POST /papers/upload` - Upload PDF file
- `POST /search` - Full-text search
- `POST /sync/zotero` - Trigger Zotero sync
- `GET /stats` - Collection statistics
- `GET /authors` - List authors
- `GET /tags` - List tags
- `GET /collections` - List collections

Full API documentation available at `/docs` when server is running.

## 🧠 Smart Categorization

The system automatically detects and categorizes papers by:

### **Academic Fields**
- Machine Learning & AI
- Natural Language Processing  
- Computer Vision
- Data Science & Analytics
- Cybersecurity
- Software Engineering
- Human-Computer Interaction
- Database Systems

### **Publication Venues**
- Top-tier conferences (NeurIPS, ICML, ACL, etc.)
- Premier journals (Nature, Science, JMLR, etc.)
- Domain-specific venues by field

### **Paper Types**
- Survey papers and reviews
- Empirical studies and evaluations
- Theoretical analyses
- Application papers and case studies

## 🔍 Search Capabilities

### **Full-Text Search**
- Content-based search across titles, abstracts, and full text
- Stemming and relevance scoring
- Search result highlighting
- Query suggestions and auto-complete

### **Advanced Filtering**
- Filter by year, author, journal, tags
- Combine text search with metadata filters
- Sort by relevance, date, or citation count

### **Export and Integration**
- Export search results in multiple formats
- Integration with external tools via API
- Batch operations on search results

## 📊 Analytics and Insights

- **Collection Overview**: Papers, authors, venues, temporal distribution
- **Research Trends**: Track topic evolution over time
- **Author Networks**: Collaboration patterns and prolific researchers
- **Venue Analysis**: Publication patterns and impact metrics
- **Reading Progress**: Track read status and personal ratings

## 🔒 Security and Privacy

- **Local-First**: All data stored locally by default
- **API Key Security**: Credentials stored separately, not in version control
- **File Integrity**: SHA256 hashing for deduplication and verification
- **Backup Support**: Easy backup and restore of complete collections

## 🚨 Troubleshooting

### **WSL2 Zotero Connection Issues**
```bash
# Fix networking issues
python scripts/fix_wsl2_networking.py

# Test connection methods
python scripts/test_zotero_local.py
```

### **PDF Processing Issues**
- Ensure PDFs are not corrupted or password-protected
- Check file permissions and available disk space
- Verify pdfplumber and PyPDF2 installations

### **Database Issues**
```bash
# Reinitialize database
python -m src.cli init

# Test database connection
python scripts/test_setup.py
```

## 🤝 Contributing

This project follows strict governance principles defined in `CLAUDE.md`:

- **Single Source of Truth**: No duplicate code or data
- **Modular Architecture**: Clean separation of concerns
- **Comprehensive Testing**: All changes must include tests
- **Documentation**: Keep README and docs up to date

## 📄 License

[Add your license here]

---

**Built for researchers, by researchers.** 🎓
