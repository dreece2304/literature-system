#!/bin/bash
# Stop all integrated literature services

echo "Stopping integrated literature services..."

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Stop event consumer
if pgrep -f "run_event_consumer" > /dev/null 2>&1; then
    echo "→ Stopping event consumer..."
    pkill -f "run_event_consumer"
    echo -e "${GREEN}✓ Event consumer stopped${NC}"
else
    echo "  Event consumer not running"
fi

# Stop literature-ai API
if lsof -i:8002 > /dev/null 2>&1; then
    echo "→ Stopping literature-ai API..."
    PID=$(lsof -ti:8002)
    kill $PID 2>/dev/null
    sleep 2
    if lsof -i:8002 > /dev/null 2>&1; then
        kill -9 $PID 2>/dev/null
    fi
    echo -e "${GREEN}✓ literature-ai API stopped${NC}"
else
    echo "  literature-ai API not running"
fi

# Stop literature-database (optional - may be used by other services)
if lsof -i:8001 > /dev/null 2>&1; then
    echo "→ Stopping literature-database..."
    PID=$(lsof -ti:8001)
    kill $PID 2>/dev/null
    sleep 2
    if lsof -i:8001 > /dev/null 2>&1; then
        kill -9 $PID 2>/dev/null
    fi
    echo -e "${GREEN}✓ literature-database stopped${NC}"
else
    echo "  literature-database not running"
fi

echo ""
echo -e "${GREEN}All services stopped${NC}"
