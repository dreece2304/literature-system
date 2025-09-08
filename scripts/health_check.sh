#!/bin/bash
# Check health of all services

echo "🏥 Checking Service Health..."
echo "=============================="

check_service() {
    local name=$1
    local port=$2
    
    if curl -s "http://localhost:$port/health" > /dev/null 2>&1; then
        echo "✅ $name (port $port) is healthy"
    else
        echo "❌ $name (port $port) is not responding"
    fi
}

# Check infrastructure
echo "Infrastructure:"
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is running"
else
    echo "❌ Redis is not running"
fi

if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running"
else
    echo "❌ Ollama is not running"
fi

echo ""
echo "Services:"
check_service "API Gateway" 8000
check_service "Literature Database" 8001
check_service "Literature AI" 8002
check_service "Literature Search" 8003
check_service "Web Dashboard" 3000
