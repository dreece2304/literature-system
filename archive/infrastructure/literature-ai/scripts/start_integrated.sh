#!/bin/bash
# Start literature-ai MCP server
#
# ARCHITECTURE CHANGE (Dec 2024):
# The MCP server now accesses the SQLite database directly via the service layer.
# No HTTP API (FastAPI on port 8001) is required.
#
# Old: Claude Code → MCP → HTTP → FastAPI → SQLAlchemy → SQLite
# New: Claude Code → MCP → Services → SQLAlchemy → SQLite

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LITAI_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$LITAI_ROOT")")"

echo "========================================"
echo "Literature MCP Server"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check prerequisites
echo "Checking prerequisites..."

# 1. Check conda environment
if ! conda env list | grep -q "litai"; then
    echo -e "${RED}✗ litai environment not found${NC}"
    echo "  Please create the environment first"
    exit 1
fi
echo -e "${GREEN}✓ litai conda environment found${NC}"

# 2. Check database exists
DB_PATH="$PROJECT_ROOT/infrastructure/literature-database/data/literature.db"
if [ ! -f "$DB_PATH" ]; then
    echo -e "${YELLOW}⚠ Database not found at $DB_PATH${NC}"
    echo "  A new database will be created on first access"
else
    echo -e "${GREEN}✓ Database found: $DB_PATH${NC}"
fi

# 3. Check Ollama (optional, for LLM features)
if curl -s http://localhost:11434/api/version > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama is running (LLM features available)${NC}"
else
    echo -e "${YELLOW}⚠ Ollama is not running (LLM features disabled)${NC}"
fi

echo ""
echo "========================================"
echo "Starting MCP Server"
echo "========================================"
echo ""

# Create log directory
mkdir -p "$LITAI_ROOT/logs"

cd "$LITAI_ROOT"

echo "Architecture: MCP → Services → SQLAlchemy → SQLite (no HTTP)"
echo "Database: $DB_PATH"
echo ""

# Start the MCP server
echo "→ Starting MCP server..."
echo "  Run: python -m src.mcp_server.server"
echo ""

# For development, run directly
# In production, Claude Code starts the MCP server via stdio
exec conda run -n litai python -m src.mcp_server.server
