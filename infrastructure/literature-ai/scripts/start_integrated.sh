#!/bin/bash
# Start literature-ai with literature-database integration
# This script starts both services and the event consumer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LITAI_ROOT="$(dirname "$SCRIPT_DIR")"
LITDB_ROOT="/home/dreece23/research/research/infrastructure/literature-database"

echo "========================================"
echo "Starting Integrated Literature Services"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check prerequisites
echo "Checking prerequisites..."

# 1. Check Redis
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}✗ Redis is not running${NC}"
    echo "  Please start Redis first: redis-server"
    exit 1
fi
echo -e "${GREEN}✓ Redis is running${NC}"

# 2. Check Ollama
if ! curl -s http://localhost:11434/api/version > /dev/null 2>&1; then
    echo -e "${RED}✗ Ollama is not running${NC}"
    echo "  Please start Ollama first: ollama serve"
    exit 1
fi
echo -e "${GREEN}✓ Ollama is running${NC}"

# 3. Check conda environments
if ! conda env list | grep -q "litdb"; then
    echo -e "${YELLOW}⚠ litdb environment not found${NC}"
    echo "  literature-database may not start properly"
fi

if ! conda env list | grep -q "litai"; then
    echo -e "${RED}✗ litai environment not found${NC}"
    echo "  Please create the environment first"
    exit 1
fi
echo -e "${GREEN}✓ Conda environments found${NC}"

echo ""
echo "========================================"
echo "Starting Services"
echo "========================================"
echo ""

# Create log directory
mkdir -p "$LITAI_ROOT/logs"

# Function to check if port is in use
port_in_use() {
    lsof -i:$1 > /dev/null 2>&1
}

# 1. Start literature-database (if not running)
if port_in_use 8001; then
    echo -e "${YELLOW}→ literature-database already running on port 8001${NC}"
else
    echo "→ Starting literature-database..."
    if [ -d "$LITDB_ROOT" ]; then
        cd "$LITDB_ROOT"
        # Start in background
        conda run -n litdb python run_service.py > "$LITAI_ROOT/logs/litdb-service.log" 2>&1 &
        LITDB_PID=$!
        echo "  PID: $LITDB_PID"

        # Wait for service to be ready
        echo "  Waiting for service to start..."
        for i in {1..30}; do
            if curl -s http://localhost:8001/health > /dev/null 2>&1; then
                echo -e "${GREEN}✓ literature-database started${NC}"
                break
            fi
            sleep 1
        done

        if ! curl -s http://localhost:8001/health > /dev/null 2>&1; then
            echo -e "${RED}✗ Failed to start literature-database${NC}"
            echo "  Check logs: tail -f $LITAI_ROOT/logs/litdb-service.log"
            exit 1
        fi
    else
        echo -e "${RED}✗ literature-database directory not found at $LITDB_ROOT${NC}"
        exit 1
    fi
fi

# 2. Start literature-ai API (if not running)
cd "$LITAI_ROOT"

if port_in_use 8002; then
    echo -e "${YELLOW}→ literature-ai API already running on port 8002${NC}"
else
    echo "→ Starting literature-ai API..."
    conda run -n litai uvicorn src.api.main:app --host 0.0.0.0 --port 8002 \
        > "$LITAI_ROOT/logs/litai-api.log" 2>&1 &
    LITAI_PID=$!
    echo "  PID: $LITAI_PID"

    # Wait for service to be ready
    echo "  Waiting for service to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8002/health > /dev/null 2>&1; then
            echo -e "${GREEN}✓ literature-ai API started${NC}"
            break
        fi
        sleep 1
    done

    if ! curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo -e "${RED}✗ Failed to start literature-ai API${NC}"
        echo "  Check logs: tail -f $LITAI_ROOT/logs/litai-api.log"
        exit 1
    fi
fi

# 3. Start event consumer (if not already running)
if pgrep -f "run_event_consumer" > /dev/null 2>&1; then
    echo -e "${YELLOW}→ Event consumer already running${NC}"
else
    echo "→ Starting event consumer..."
    if [ -f "$LITAI_ROOT/scripts/run_event_consumer.py" ]; then
        conda run -n litai python "$LITAI_ROOT/scripts/run_event_consumer.py" \
            > "$LITAI_ROOT/logs/event-consumer.log" 2>&1 &
        CONSUMER_PID=$!
        echo "  PID: $CONSUMER_PID"
        sleep 2

        if ps -p $CONSUMER_PID > /dev/null; then
            echo -e "${GREEN}✓ Event consumer started${NC}"
        else
            echo -e "${RED}✗ Event consumer failed to start${NC}"
            echo "  Check logs: tail -f $LITAI_ROOT/logs/event-consumer.log"
        fi
    else
        echo -e "${YELLOW}⚠ Event consumer script not found, skipping...${NC}"
    fi
fi

echo ""
echo "========================================"
echo "Service Status"
echo "========================================"
echo ""
echo -e "${GREEN}All services started successfully!${NC}"
echo ""
echo "Service URLs:"
echo "  - literature-database: http://localhost:8001/docs"
echo "  - literature-ai:       http://localhost:8002/docs"
echo ""
echo "Logs:"
echo "  - literature-database: tail -f $LITAI_ROOT/logs/litdb-service.log"
echo "  - literature-ai API:   tail -f $LITAI_ROOT/logs/litai-api.log"
echo "  - Event consumer:      tail -f $LITAI_ROOT/logs/event-consumer.log"
echo ""
echo "Quick Tests:"
echo "  # Check health"
echo "  curl http://localhost:8001/health"
echo "  curl http://localhost:8002/health"
echo ""
echo "  # Add a test paper"
echo "  curl -X POST http://localhost:8001/api/v1/papers \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"title\":\"Test\",\"authors\":\"Smith\",\"year\":2023,\"abstract\":\"Test paper\"}'"
echo ""
echo "  # Search in vector store (wait 3-5 seconds after adding paper)"
echo "  curl -X POST http://localhost:8002/api/v1/search/ \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"query\":\"test\",\"top_k\":3}'"
echo ""
echo "To stop all services:"
echo "  ./scripts/stop_integrated.sh"
echo ""
