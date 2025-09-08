# Literature Database Setup Guide

Complete setup instructions for getting the Literature Database running on Windows 11 with WSL2.

## 📋 Prerequisites

### System Requirements
- **Windows 11** (22H2 or later recommended for best WSL2 networking)
- **WSL2** with Ubuntu or similar Linux distribution
- **Zotero** installed on Windows (optional but recommended)
- **Python 3.11+** in WSL2 environment
- **Git** for version control

### Hardware Requirements
- **8GB RAM minimum** (16GB+ recommended for large collections)
- **10GB free disk space** (more for PDF storage)
- **SSD recommended** for better performance

## 🚀 Installation Steps

### Step 1: Environment Setup

```bash
# Clone the repository
git clone <repository-url>
cd literature-database

# Create and activate conda environment
mamba create -n litdb python=3.11
mamba activate litdb

# Install Python dependencies
pip install -r requirements.txt

# Verify installation
python -m src.cli --help
```

### Step 2: Database Initialization

```bash
# Initialize database and directory structure
python -m src.cli init

# Run setup verification
python scripts/test_setup.py
```

Expected output:
```
✓ All tests passed! Setup is complete.
✓ 10 tables created
✓ Directory structure validated
```

### Step 3: Configuration

#### Basic Configuration (`config/settings.yml`)
```yaml
# Database Configuration  
database:
  type: "sqlite"
  path: "data/metadata/literature.db"
  
# PDF Processing
pdf:
  storage_path: "data/pdfs"
  extract_text: true
  extract_images: false
  ocr_enabled: false
  
# Search Configuration
search:
  index_path: "data/cache/search_index"
  
# Zotero Integration
zotero:
  windows_path: "/mnt/c/Users/[YOUR-USERNAME]/Zotero"
  library_type: "user"
  
# Logging
logging:
  level: "INFO"
  file: "logs/litdb.log"
```

#### API Credentials (`config/credentials.yml`)
```yaml
# Zotero API (optional - for web API sync)
zotero:
  api_key: ""
  library_id: ""
```

**Important:** Never commit `credentials.yml` to version control.

## 🔗 Zotero Integration Setup

### Option 1: Local API (Recommended)

This method uses Zotero's built-in HTTP API server for direct communication.

**Enable in Zotero:**
1. Open Zotero on Windows
2. **Edit → Preferences → Advanced → Config Editor**
3. Search for: `extensions.zotero.httpServer.enabled`
4. Set to: `true`
5. **Restart Zotero**

**Test Connection:**
```bash
# Test if local API is accessible from WSL2
python scripts/test_zotero_local.py
```

**Fix WSL2 Networking Issues:**
```bash
# Run comprehensive networking fix
python scripts/fix_wsl2_networking.py
```

### Option 2: Web API

If local API doesn't work, use Zotero's web API.

**Setup Steps:**
```bash
# Run interactive setup wizard
python scripts/setup_zotero.py
```

**Manual Setup:**
1. Get API key from: https://www.zotero.org/settings/keys
2. Create key with:
   - ✅ Allow library access
   - ✅ Allow write access
3. Update `config/credentials.yml` with your key
4. Find your User ID in Zotero settings or URL

### Option 3: Direct File Import

Skip Zotero integration and import PDFs directly.

```bash
# Import PDF collection
python scripts/migrate_pdfs.py "/path/to/pdfs" --copy --organize

# Auto-categorize imported papers
python scripts/organize_collection.py auto-categorize
```

## 📁 PDF Migration

### Migration Options

```bash
# Preview changes (dry run)
python scripts/migrate_pdfs.py "/path/to/pdfs" --dry-run

# Full migration with copying and organization
python scripts/migrate_pdfs.py "/path/to/pdfs" --copy --organize

# Import without copying files
python scripts/migrate_pdfs.py "/path/to/pdfs" --no-copy

# Skip duplicate detection
python scripts/migrate_pdfs.py "/path/to/pdfs" --include-duplicates
```

### Common PDF Paths on Windows

```bash
# Documents folder
python scripts/migrate_pdfs.py "/mnt/c/Users/[username]/Documents/Papers"

# Downloads folder
python scripts/migrate_pdfs.py "/mnt/c/Users/[username]/Downloads"

# Zotero storage (if extracting from Zotero)
python scripts/migrate_pdfs.py "/mnt/c/Users/[username]/Zotero/storage"
```

### Migration Process

1. **Scanning**: Recursively finds all PDF files
2. **Duplicate Detection**: Uses SHA256 hashing to identify duplicates
3. **Text Extraction**: Extracts full text using pdfplumber
4. **Metadata Extraction**: Parses titles, authors, years, DOIs
5. **Organization**: Organizes files by publication year (optional)
6. **Database Population**: Creates database records with extracted data

## 🎯 Post-Setup Tasks

### 1. Initial Sync

```bash
# Sync from Zotero (if configured)
python -m src.cli sync

# View collection statistics
python -m src.cli stats
```

### 2. Collection Organization

```bash
# Analyze your collection
python scripts/organize_collection.py analyze

# Auto-categorize papers
python scripts/organize_collection.py auto-categorize

# Interactive organization
python scripts/organize_collection.py interactive
```

### 3. Search Index

```bash
# Build full-text search index
python -m src.cli reindex

# Test search functionality
python -m src.cli search "machine learning"
```

### 4. API Server (Optional)

```bash
# Start web API server
python -m src.cli serve --host 0.0.0.0 --port 8000

# Access API documentation
# Open http://localhost:8000/docs in browser
```

## 🔧 Advanced Configuration

### WSL2 Networking for Zotero

For Windows 11 22H2+, enable mirrored networking:

**Create/edit `%USERPROFILE%\.wslconfig`:**
```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=true
```

**Restart WSL:**
```powershell
# In Windows PowerShell as Administrator
wsl --shutdown
# Then restart your WSL2 terminal
```

### Performance Optimization

**For large collections (10,000+ papers):**

```yaml
# config/settings.yml
database:
  type: "postgresql"  # Consider PostgreSQL for large datasets
  
search:
  batch_size: 1000    # Larger batches for indexing
  
pdf:
  extract_images: false  # Disable for faster processing
  parallel_processing: true
```

### Custom Field Patterns

Add custom field detection patterns:

```python
# In organize_collection.py, add to field_patterns:
'Quantum Computing': [
    'quantum', 'qubit', 'quantum computing', 'quantum algorithm'
],
'Robotics': [
    'robot', 'robotics', 'autonomous', 'manipulation', 'navigation'
]
```

## 🚨 Troubleshooting

### Common Issues

#### 1. WSL2 Can't Connect to Zotero
```bash
# Run networking diagnostic
python scripts/fix_wsl2_networking.py

# Test all connection methods
python scripts/test_zotero_local.py
```

#### 2. PDF Processing Fails
```bash
# Check PDF file integrity
file "/path/to/paper.pdf"

# Test individual PDF
python -c "
from src.extractors.pdf_extractor import PDFExtractor
extractor = PDFExtractor()
result = extractor.extract('/path/to/paper.pdf')
print(f'Text length: {len(result.get(\"full_text\", \"\"))}')
"
```

#### 3. Database Corruption
```bash
# Backup current database
cp data/metadata/literature.db data/metadata/literature.db.backup

# Reinitialize database
python -m src.cli init

# Reimport data (if needed)
python scripts/migrate_pdfs.py "/path/to/pdfs" --copy
```

#### 4. Search Index Issues
```bash
# Clear and rebuild search index
rm -rf data/cache/search_index
python -m src.cli reindex
```

### Performance Issues

#### Slow PDF Processing
- **Disable OCR**: Set `ocr_enabled: false` in config
- **Limit text extraction**: Set reasonable limits for very large PDFs
- **Use SSD storage**: Move data directory to SSD

#### High Memory Usage
- **Process in batches**: Use smaller batch sizes for large collections
- **Monitor memory**: Use `htop` to watch memory usage
- **Limit concurrent operations**: Reduce parallel processing

### Getting Help

1. **Check logs**: `tail -f logs/litdb.log`
2. **Run diagnostics**: `python scripts/test_setup.py`
3. **Verify environment**: `python -m src.cli stats`
4. **Test components**: Use individual test scripts

## 📊 Verification Checklist

After setup, verify everything works:

- [ ] **Database initialized**: `python scripts/test_setup.py`
- [ ] **CLI working**: `python -m src.cli --help`
- [ ] **Zotero connection**: `python scripts/test_zotero_local.py`
- [ ] **PDF processing**: Import a test PDF
- [ ] **Search working**: `python -m src.cli search test`
- [ ] **API server**: `python -m src.cli serve` (optional)

## 🎉 Next Steps

Once setup is complete:

1. **Import your PDF collection**
2. **Sync with Zotero** (if configured)
3. **Explore organization tools**
4. **Set up regular sync schedule**
5. **Customize categorization patterns**
6. **Integrate with your research workflow**

Congratulations! Your Literature Database is ready to help organize your research papers! 🎓