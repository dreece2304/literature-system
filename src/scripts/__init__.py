"""Maintenance scripts for Literature MCP Server.

Available scripts:
- health_check: Check system component health
- integrity_check: Verify database integrity
- reindex: Rebuild search indexes and embeddings
- backup: Backup database and files
- maintenance: Combined maintenance runner
"""

from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
