# Literature Database Service Troubleshooting

Troubleshooting guide for the literature-database service in the research monorepo.

**Service Context**: Port 8001 | Path: `infrastructure/literature-database/`

## 🚨 Quick Diagnostics

### System Health Check
```bash
# Run comprehensive system test (from service directory)
cd infrastructure/literature-database
python scripts/test_setup.py

# Check CLI functionality  
python -m src.cli stats

# Test database connection
python -c "
from src.database import get_session
session = next(get_session())
print('Database connection: OK')
session.close()
"
```

### Log Analysis
```bash
# View recent logs
tail -50 logs/litdb.log

# Search for errors
grep -i error logs/litdb.log | tail -20

# Monitor real-time logs
tail -f logs/litdb.log
```

## 🔧 Common Issues and Solutions

### 1. Environment and Installation Issues

#### Issue: `conda activate research-monorepo` fails
**Symptoms:**
```
EnvironmentNameNotFound: Could not find conda environment: litdb
```

**Solutions:**
```bash
# List available environments
mamba env list

# Create environment if missing
mamba create -n litdb python=3.11
mamba activate litdb
pip install -r requirements.txt

# Alternative: Use conda instead
conda activate litdb
```

#### Issue: Import errors for src modules
**Symptoms:**
```
ModuleNotFoundError: No module named 'src'
```

**Solutions:**
```bash
# Ensure you're in the project directory
cd literature-database

# Check PYTHONPATH
echo $PYTHONPATH

# Run from project root
python -m src.cli --help

# Alternative: Add to path temporarily
export PYTHONPATH="${PYTHONPATH}:${PWD}"
```

#### Issue: Missing dependencies
**Symptoms:**
```
ModuleNotFoundError: No module named 'pdfplumber'
```

**Solutions:**
```bash
# Install missing packages
pip install pdfplumber pypdf2 sqlalchemy

# Reinstall all requirements
pip install -r requirements.txt --force-reinstall

# Check installed packages
pip list | grep -E "pdf|sql|zotero"
```

### 2. Database Issues

#### Issue: Database initialization fails
**Symptoms:**
```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table
```

**Solutions:**
```bash
# Reinitialize database
python -m src.cli init

# Check database file exists
ls -la data/metadata/literature.db

# Manual initialization
python scripts/init_db.py

# Reset database completely
rm data/metadata/literature.db
python -m src.cli init
```

#### Issue: Database corruption
**Symptoms:**
```
sqlite3.DatabaseError: database disk image is malformed
```

**Solutions:**
```bash
# Backup corrupted database
cp data/metadata/literature.db data/metadata/literature.db.corrupted

# Try to repair
sqlite3 data/metadata/literature.db ".recover" > recovered.sql
sqlite3 data/metadata/literature_new.db < recovered.sql
mv data/metadata/literature_new.db data/metadata/literature.db

# If repair fails, reinitialize
rm data/metadata/literature.db
python -m src.cli init
# Re-import your PDFs
```

#### Issue: Permission denied on database
**Symptoms:**
```
sqlite3.OperationalError: attempt to write a readonly database
```

**Solutions:**
```bash
# Check file permissions
ls -la data/metadata/literature.db

# Fix permissions
chmod 664 data/metadata/literature.db
chmod 755 data/metadata/

# Check directory permissions
ls -la data/
```

### 3. PDF Processing Issues

#### Issue: PDF extraction fails
**Symptoms:**
```
Failed to extract from PDF: [file.pdf]
```

**Solutions:**
```bash
# Test individual PDF
python -c "
from src.extractors.pdf_extractor import PDFExtractor
extractor = PDFExtractor()
try:
    result = extractor.extract('/path/to/problem.pdf')
    print('PDF extraction successful')
except Exception as e:
    print(f'Error: {e}')
"

# Check PDF file
file "/path/to/problem.pdf"

# Test with different PDF tools
pdfinfo "/path/to/problem.pdf"
pdftotext "/path/to/problem.pdf" -

# Skip problematic PDFs
python scripts/migrate_pdfs.py "/path/to/pdfs" --skip-errors
```

#### Issue: Password-protected PDFs
**Symptoms:**
```
PdfReadError: file has not been decrypted
```

**Solutions:**
```bash
# Decrypt PDFs first (if you have passwords)
qpdf --password=PASSWORD --decrypt input.pdf output.pdf

# Skip encrypted PDFs during import
# (automatic in current implementation)

# List encrypted PDFs in directory
find /path/to/pdfs -name "*.pdf" -exec qpdf --show-encryption {} \; 2>/dev/null | grep -B1 "encrypted"
```

#### Issue: Large PDF files causing memory issues
**Symptoms:**
```
MemoryError: Unable to allocate array
```

**Solutions:**
```bash
# Process PDFs in smaller batches
python scripts/migrate_pdfs.py "/path/to/pdfs" --batch-size 10

# Increase system swap
sudo swapon --show
sudo fallocate -l 4G /swapfile

# Skip very large files
find /path/to/pdfs -name "*.pdf" -size +100M -print
```

### 4. Zotero Integration Issues

#### Issue: Local API connection fails
**Symptoms:**
```
✗ Local API not available
Connection timeout after 5001 ms
```

**Solutions:**
```bash
# Check if Zotero is running
ps aux | grep -i zotero  # On Windows: tasklist | findstr zotero

# Verify HTTP server enabled in Zotero
# Edit → Preferences → Advanced → Config Editor
# extensions.zotero.httpServer.enabled = true

# Test connection methods
python scripts/test_zotero_local.py

# Fix WSL2 networking
python scripts/fix_wsl2_networking.py

# Windows firewall rule
netsh advfirewall firewall add rule name="Zotero API" dir=in action=allow protocol=TCP localport=23119

# Test direct connection
curl http://localhost:23119/api
curl http://$(ip route show default | awk '/default/ {print $3}'):23119/api
```

#### Issue: Web API authentication fails
**Symptoms:**
```
zotero.zotero.UnsupportedParams: API key invalid or insufficient permissions
```

**Solutions:**
```bash
# Verify API key in credentials.yml
cat config/credentials.yml

# Test API key manually
curl -H "Authorization: Bearer YOUR_API_KEY" "https://api.zotero.org/users/YOUR_USER_ID/items?limit=1"

# Get new API key
# Visit: https://www.zotero.org/settings/keys

# Check library ID
python -c "
from src.extractors.zotero_sync import ZoteroSync
sync = ZoteroSync()
print(f'Config: {sync.config}')
"
```

#### Issue: Zotero sync creates duplicates
**Symptoms:**
```
Multiple papers with same title/DOI
```

**Solutions:**
```bash
# Enable duplicate detection
python -c "
from src.database import get_session
from src.models import Paper
session = next(get_session())
duplicates = session.query(Paper.doi, session.func.count(Paper.id)).group_by(Paper.doi).having(session.func.count(Paper.id) > 1).all()
print(f'Duplicate DOIs: {len(duplicates)}')
session.close()
"

# Remove duplicates
python scripts/remove_duplicates.py --by-doi

# Prevent future duplicates
# (automatic in current implementation)
```

### 5. Search and Indexing Issues

#### Issue: Search returns no results
**Symptoms:**
```
python -m src.cli search "machine learning"
No results found.
```

**Solutions:**
```bash
# Check if search index exists
ls -la data/cache/search_index/

# Rebuild search index
python -m src.cli reindex

# Test index manually
python -c "
from src.services.search_service import SearchService
service = SearchService()
stats = service.get_index_stats()
print(f'Index stats: {stats}')
"

# Check papers have text
python -c "
from src.database import get_session
from src.models import Paper
session = next(get_session())
papers_with_text = session.query(Paper).filter(Paper.full_text.isnot(None)).count()
total_papers = session.query(Paper).count()
print(f'Papers with text: {papers_with_text}/{total_papers}')
session.close()
"
```

#### Issue: Search index corruption
**Symptoms:**
```
whoosh.index.LockError: Could not lock index
```

**Solutions:**
```bash
# Remove lock files
rm -f data/cache/search_index/*.lock

# Clear and rebuild index
rm -rf data/cache/search_index/
python -m src.cli reindex

# Check disk space
df -h data/cache/
```

### 6. CLI and API Issues

#### Issue: CLI commands not working
**Symptoms:**
```
python -m src.cli stats
AttributeError: module 'src.cli' has no attribute 'main'
```

**Solutions:**
```bash
# Check if CLI module exists
ls -la src/cli.py

# Run CLI directly
python src/cli.py stats

# Check Python path
python -c "import sys; print(sys.path)"

# Reinstall packages
pip install -r requirements.txt --force-reinstall
```

#### Issue: API server won't start
**Symptoms:**
```
python -m src.cli serve
Error: Address already in use
```

**Solutions:**
```bash
# Check what's using the port
netstat -tlnp | grep :8000
lsof -i :8000

# Kill process using port
kill $(lsof -t -i:8000)

# Use different port
python -m src.cli serve --port 8001

# Check FastAPI installation
pip show fastapi uvicorn
```

### 7. Performance Issues

#### Issue: Slow PDF processing
**Symptoms:**
```
PDF processing takes very long time
```

**Solutions:**
```bash
# Monitor system resources
htop
df -h

# Process in smaller batches
python scripts/migrate_pdfs.py "/path" --batch-size 50

# Disable OCR if enabled
# config/settings.yml: ocr_enabled: false

# Skip text extraction temporarily
# config/settings.yml: extract_text: false

# Use faster storage (SSD)
# Move data/ directory to SSD
```

#### Issue: High memory usage
**Symptoms:**
```
System runs out of memory during processing
```

**Solutions:**
```bash
# Monitor memory usage
free -h
ps aux --sort=-%mem | head -10

# Reduce batch sizes
# Edit scripts to process fewer files at once

# Add swap space
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Clean up temporary files
python -c "
from src.utils.path_manager import PathManager
pm = PathManager()
pm.cleanup_temp_files(older_than_hours=1)
"
```

### 8. Configuration Issues

#### Issue: Configuration file errors
**Symptoms:**
```
yaml.scanner.ScannerError: mapping values are not allowed here
```

**Solutions:**
```bash
# Validate YAML syntax
python -c "
import yaml
with open('config/settings.yml', 'r') as f:
    config = yaml.safe_load(f)
    print('YAML is valid')
"

# Check file encoding
file config/settings.yml

# Recreate config from template
cp config/settings.yml config/settings.yml.backup
# Edit with proper YAML syntax

# Test configuration loading
python -c "
from src.extractors.zotero_sync import ZoteroSync
sync = ZoteroSync()
print('Configuration loaded successfully')
"
```

#### Issue: Path configuration problems  
**Symptoms:**
```
FileNotFoundError: [Errno 2] No such file or directory
```

**Solutions:**
```bash
# Check configured paths
python -c "
from src.utils.path_manager import PathManager
pm = PathManager()
print(f'PDF path: {pm.get_pdf_storage_path()}')
print(f'DB path: {pm.get_database_path()}')
print(f'Zotero path: {pm.get_zotero_path()}')
"

# Create missing directories
mkdir -p data/pdfs data/metadata data/cache logs temp

# Fix Windows path mapping
# Convert C:\Users\... to /mnt/c/Users/...

# Test path accessibility  
ls -la "/mnt/c/Users/[username]/Zotero/"
```

## 🔍 Advanced Debugging

### Enable Debug Logging
```bash
# Temporary debug mode
export LITDB_LOG_LEVEL=DEBUG
python -m src.cli stats

# Permanent debug mode
# Edit config/settings.yml:
# logging:
#   level: "DEBUG"
```

### Database Inspection
```bash
# Open database directly
sqlite3 data/metadata/literature.db

# Common queries
.tables
SELECT COUNT(*) FROM papers;
SELECT COUNT(*) FROM authors;
SELECT title, year FROM papers ORDER BY date_added DESC LIMIT 5;
.quit
```

### Network Debugging
```bash
# Test network connectivity
ping google.com
curl -I https://api.zotero.org/

# Check DNS resolution
nslookup api.zotero.org

# Test WSL2 networking
ip route show default
cat /etc/resolv.conf

# Windows host connectivity
ping $(ip route show default | awk '/default/ {print $3}')
```

### File System Debugging  
```bash
# Check disk space
df -h

# Check file permissions
ls -la data/
ls -la config/

# Check for corrupted files
find data/ -name "*.db" -exec file {} \;

# Monitor file access
inotifywait -m -r data/ --format '%w %f %e'
```

## 📞 Getting Help

### Before Seeking Help

1. **Run diagnostics**: `python scripts/test_setup.py`
2. **Check logs**: `tail -50 logs/litdb.log`
3. **Test components individually**: Use test scripts
4. **Document the exact error**: Include full error messages
5. **Note your environment**: OS, Python version, package versions

### Information to Include

```bash
# System information
uname -a
python --version
pip list | grep -E "pdf|sql|zotero|fast|rich"

# Project status
python -m src.cli stats
ls -la data/
head -20 logs/litdb.log
```

### Self-Help Resources

1. **Check configuration**: Verify all config files are correct
2. **Review logs**: Look for patterns in error messages  
3. **Test incrementally**: Start with basic functionality
4. **Compare working examples**: Use test scripts as reference
5. **Reset selectively**: Clear specific components rather than everything

### Recovery Procedures

#### Complete Reset
```bash
# Backup important data
cp -r data/ data_backup/

# Reset database
rm data/metadata/literature.db
python -m src.cli init

# Clear caches
rm -rf data/cache/
mkdir -p data/cache/

# Reset logs
> logs/litdb.log

# Test basic functionality
python scripts/test_setup.py
```

#### Partial Reset
```bash
# Reset just search index
rm -rf data/cache/search_index/
python -m src.cli reindex

# Reset just Zotero sync
python -c "
from src.database import get_session
from src.models import Paper
session = next(get_session())
session.query(Paper).update({'zotero_key': None, 'zotero_version': None})
session.commit()
session.close()
"
python -m src.cli sync
```

Remember: Most issues can be resolved by carefully following error messages and checking configuration. When in doubt, start with the basic diagnostics and work through the solutions systematically. 🔧