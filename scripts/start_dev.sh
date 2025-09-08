#!/bin/bash
# Start all services for development

echo "🚀 Starting Research Infrastructure..."

# Check prerequisites
command -v redis-cli >/dev/null 2>&1 || { echo "❌ Redis is not installed"; exit 1; }
command -v ollama >/dev/null 2>&1 || { echo "❌ Ollama is not installed"; exit 1; }

# Start Redis if not running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis..."
    redis-server --daemonize yes
fi

# Start Ollama if not running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve > /dev/null 2>&1 &
    sleep 3
fi

# Function to start service in new terminal
start_service() {
    local name=$1
    local path=$2
    local env=$3
    local port=$4
    
    echo "Starting $name on port $port..."
    gnome-terminal --tab --title="$name" -- bash -c "cd $path && mamba activate $env && uvicorn src.api:app --port $port --reload; exec bash"
}

# Start services
start_service "Literature DB" "infrastructure/literature-database" "litdb" 8001
sleep 2
start_service "Literature AI" "infrastructure/literature-ai" "litai" 8002
sleep 2
start_service "Literature Search" "infrastructure/literature-search" "litsearch" 8003
sleep 2
start_service "API Gateway" "infrastructure/api-gateway" "gateway" 8000

echo "✅ All services starting..."
echo ""
echo "Services will be available at:"
echo "  API Gateway:    http://localhost:8000"
echo "  Literature DB:  http://localhost:8001"
echo "  Literature AI:  http://localhost:8002"
echo "  Literature Search: http://localhost:8003"
echo ""
echo "Check service health: ./scripts/health_check.sh"
