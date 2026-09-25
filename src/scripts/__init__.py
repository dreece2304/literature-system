"""Maintenance scripts for Literature MCP Server.

Available scripts:
- health_check: Check infrastructure health (database, vector store, disk)
- audit: Check stored data for silent failures and structural damage
- enrich_pipeline: backfill -> embed -> extract -> verify batch runner
- reindex: Rebuild search indexes and embeddings
- backup: Backup database and files
- maintenance: Combined maintenance runner
"""

from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
