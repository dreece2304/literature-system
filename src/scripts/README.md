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

### Audit

Check stored data for silent failures and structural damage. Replaces the
former `integrity_check` and `paper_health_check`, which overlapped with each
other and missed the failure mode that matters most: work recorded as complete
that never actually happened.

```bash
# Check for issues
python -m scripts.audit

# Repair the fixable findings
python -m scripts.audit --fix

# JSON output
python -m scripts.audit --json
```

**Silent failures detected:**
- Verification scored while the NLI verifier was unreachable (every claim unchecked)
- `extraction_depth='comprehensive'` with no summary and no findings
- `deep_extraction_date` set with no summary in any column
- `chunking_status='complete'` with no chunks, or a `chunk_count` that disagrees
- Empty chunk rows

**Structural damage detected:**
- Orphan chunks, extraction metadata, contents, notes and references
- Papers with no title
- Duplicate DOIs
- Papers missing from the FTS index
- `file_path` recorded but no file on disk

**Exit codes:** `0` clean, `1` at least one error-severity finding (warnings alone
exit 0), so it works in cron. `--json` prints `{"findings": [...], "fixed": {...}}`,
where `fixed` maps each repaired check to the number of rows it touched.

### Enrich Pipeline

Backfill chunks, embed, deep-extract and verify in one resumable pass. Stages
run in the order `backfill -> embed -> extract -> verify`; `embed` runs before
the LLM stages so semantic search covers a paper as soon as it is chunked.

```bash
# Everything, 20 papers per stage
python -m scripts.enrich_pipeline --stage all --limit 20

# One stage, specific papers
python -m scripts.enrich_pipeline --stage embed --paper-ids 12,34,56

# Show what would be processed, no writes
python -m scripts.enrich_pipeline --stage all --dry-run
```

**Flags:** `--stage {backfill,embed,extract,verify,all}`, `--limit N`,
`--paper-ids 1,2,3`, `--dry-run`.

The `extract` and `verify` stages preflight Ollama and the judge model before
touching the database; if either is unreachable the stage aborts with exit 1
and a copy-pasteable remediation (`ollama serve` / `ollama pull ...`). The
`backfill` and `embed` stages do not need Ollama.

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
# Run health check + data audit only
python -m scripts.maintenance

# Run all maintenance tasks
python -m scripts.maintenance --all

# Include reindexing
python -m scripts.maintenance --reindex

# Include backup
python -m scripts.maintenance --backup --backup-dir ~/backups

# Repair audit findings (same as `audit --fix`)
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

# Monthly data audit with fixes
0 3 1 * * cd /path/to/project && python -m scripts.audit --fix --json
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

Two conventions are in use:

| Scripts | 0 | 1 | 2 |
|---------|---|---|---|
| `health_check`, `maintenance` | all OK | warnings detected | errors detected |
| `audit`, `enrich_pipeline`, `backup`, `reindex` | OK | failure (audit: an error-severity finding remains) | — |

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

**Wrong database / PDF / vector store path:**
- Paths come from `literature_core.config.settings` (`LITCORE_DATABASE_PATH`,
  `LITCORE_PDF_STORAGE_PATH`, `LITCORE_CHROMA_PATH`, ...), set as environment
  variables or in a `.env` in the working directory (`src/`)

**"Database error" in health check:**
- Check database path in settings
- Verify SQLite file permissions

**"Vector store error":**
- ChromaDB directory may not exist (will be created on first use)
- Check disk space availability

**Reindex fails:**
- Ensure embedding model is accessible
- Check VRAM availability for GPU-based embeddings
