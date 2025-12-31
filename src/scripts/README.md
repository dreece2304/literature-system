# Literature MCP Server - Maintenance Scripts

This directory contains maintenance and administration scripts for the Literature MCP Server.

## Available Scripts

### Health Check

Check the health of all system components:

```bash
# Basic health check
python -m scripts.health_check

# JSON output (for automation)
python -m scripts.health_check --json

# Verbose output
python -m scripts.health_check -v
```

**Checks performed:**
- Database connectivity and table counts
- ChromaDB/vector store status
- PDF storage directory accessibility
- Search index status
- Memory and disk usage
- Zotero integration configuration

**Exit codes:**
- `0`: All checks passed
- `1`: Warnings detected
- `2`: Errors detected

### Integrity Check

Verify database integrity and detect issues:

```bash
# Check for issues
python -m scripts.integrity_check

# Auto-fix issues
python -m scripts.integrity_check --fix

# JSON output
python -m scripts.integrity_check --json
```

**Issues detected:**
- Orphan notes (referencing deleted papers)
- Missing PDF files (path exists but file doesn't)
- Duplicate papers (by DOI)
- Similar titles (potential duplicates)
- Missing required fields (abstract, year)
- Broken Zotero links

**Exit codes:**
- `0`: No issues found
- `1`: Warnings only
- `2`: Errors found

### Reindex

Rebuild search indexes and embeddings:

```bash
# Incremental reindex (only missing items)
python -m scripts.reindex --incremental

# Full rebuild of all indexes
python -m scripts.reindex --full

# Reindex specific papers
python -m scripts.reindex --papers 1 2 3 4 5

# JSON output
python -m scripts.reindex --json

# Verbose output
python -m scripts.reindex -v
```

**Operations performed:**
- Regenerate embeddings for papers missing from vector store
- Create chunk embeddings for papers with full text
- Update search index timestamps

### Backup

Create backups of database and files:

```bash
# Basic backup (database + export)
python -m scripts.backup --output-dir ~/backups

# Include PDF files
python -m scripts.backup -o ~/backups --include-pdfs

# Compress backup
python -m scripts.backup -o ~/backups --compress

# List existing backups
python -m scripts.backup --list

# Cleanup old backups (keep last 5)
python -m scripts.backup --cleanup 5
```

**Backup contents:**
- SQLite database (using safe backup API)
- PDF storage directory (optional)
- ChromaDB persistence directory
- JSON export of all papers

### Maintenance (Combined Runner)

Run multiple maintenance tasks in sequence:

```bash
# Run health + integrity checks only
python -m scripts.maintenance

# Run all maintenance tasks
python -m scripts.maintenance --all

# Include reindexing
python -m scripts.maintenance --reindex

# Include backup
python -m scripts.maintenance --backup --backup-dir ~/backups

# Auto-fix integrity issues
python -m scripts.maintenance --fix

# JSON output (for automation/monitoring)
python -m scripts.maintenance --json
```

## Automation

### Cron Examples

```bash
# Daily health check at 6 AM
0 6 * * * cd /path/to/project && python -m scripts.health_check --json >> /var/log/literature-health.log

# Weekly full maintenance on Sunday at 2 AM
0 2 * * 0 cd /path/to/project && python -m scripts.maintenance --all --backup-dir ~/backups --json

# Monthly integrity check with fixes
0 3 1 * * cd /path/to/project && python -m scripts.integrity_check --fix --json
```

### Integration with Monitoring

All scripts support `--json` output for easy integration with monitoring systems:

```python
import subprocess
import json

result = subprocess.run(
    ["python", "-m", "scripts.health_check", "--json"],
    capture_output=True,
    text=True
)
report = json.loads(result.stdout)

if report["overall_status"] == "error":
    send_alert("Literature MCP Server health check failed!")
```

## Exit Codes

All scripts follow a consistent exit code convention:

| Code | Meaning |
|------|---------|
| 0 | Success / All OK |
| 1 | Warnings detected |
| 2 | Errors detected |

## Requirements

Scripts require the full Literature MCP Server environment:

```bash
# Activate the environment
conda activate litai

# Run scripts from src directory
cd /path/to/project/src
python -m scripts.health_check
```

## Troubleshooting

### Common Issues

**"Settings not available" warning:**
- Ensure `config/settings.py` exists and is properly configured

**"Database error" in health check:**
- Check database path in settings
- Verify SQLite file permissions

**"Vector store error":**
- ChromaDB directory may not exist (will be created on first use)
- Check disk space availability

**Reindex fails:**
- Ensure embedding model is accessible
- Check VRAM availability for GPU-based embeddings
