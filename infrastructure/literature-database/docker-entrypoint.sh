#!/bin/bash
# Docker entrypoint script for literature-database service
# Handles initialization and configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Literature Database Service...${NC}"

# Function to wait for service
wait_for_service() {
    local host=$1
    local port=$2
    local service=$3
    local max_attempts=30
    local attempt=1
    
    echo -e "${YELLOW}Waiting for $service to be ready at $host:$port...${NC}"
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            echo -e "${GREEN}$service is ready!${NC}"
            return 0
        fi
        echo -e "Attempt $attempt/$max_attempts: $service not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo -e "${RED}$service failed to become ready after $max_attempts attempts${NC}"
    return 1
}

# Wait for dependencies if they exist
if [ "$DATABASE_URL" != "sqlite"* ]; then
    # Extract postgres host and port from DATABASE_URL
    if [[ $DATABASE_URL =~ postgresql://.*@([^:]+):([0-9]+)/ ]]; then
        pg_host="${BASH_REMATCH[1]}"
        pg_port="${BASH_REMATCH[2]}"
        wait_for_service "$pg_host" "$pg_port" "PostgreSQL"
    fi
fi

# Wait for Redis if enabled
if [ "$REDIS_ENABLED" = "true" ] && [ -n "$REDIS_URL" ]; then
    if [[ $REDIS_URL =~ redis://([^:]+):([0-9]+) ]]; then
        redis_host="${BASH_REMATCH[1]}"
        redis_port="${BASH_REMATCH[2]}"
        wait_for_service "$redis_host" "$redis_port" "Redis"
    fi
fi

# Create necessary directories
echo -e "${BLUE}Creating necessary directories...${NC}"
mkdir -p data/metadata data/pdfs data/cache/search_index logs

# Set proper permissions
chown -R appuser:appuser data logs 2>/dev/null || true

# Initialize database if it doesn't exist (SQLite only)
if [[ "$DATABASE_URL" == "sqlite"* ]] && [ ! -f "data/metadata/literature.db" ]; then
    echo -e "${BLUE}Initializing SQLite database...${NC}"
    python -c "
from src.models import Base
from src.database import get_engine, load_config
try:
    config = load_config()
    engine = get_engine(config)
    Base.metadata.create_all(bind=engine)
    print('Database initialized successfully')
except Exception as e:
    print(f'Database initialization failed: {e}')
    exit(1)
"
fi

# Health check function
health_check() {
    echo -e "${BLUE}Performing health check...${NC}"
    curl -f "http://localhost:${SERVICE_PORT}/health" >/dev/null 2>&1
}

# Start the service based on the command
if [ "$1" = "test" ]; then
    echo -e "${BLUE}Running tests...${NC}"
    exec python run_tests.py
elif [ "$1" = "shell" ]; then
    echo -e "${BLUE}Starting interactive shell...${NC}"
    exec /bin/bash
elif [ "$1" = "migrate" ]; then
    echo -e "${BLUE}Running database migrations...${NC}"
    python -c "
from src.models import Base
from src.database import get_engine, load_config
config = load_config()
engine = get_engine(config)
Base.metadata.create_all(bind=engine)
print('Database migration completed')
"
else
    echo -e "${BLUE}Starting Literature Database Service on port ${SERVICE_PORT}...${NC}"
    
    # Start the service
    if [ "$DEBUG" = "true" ] || [ "$RELOAD" = "true" ]; then
        echo -e "${YELLOW}Starting in development mode with auto-reload...${NC}"
        exec python run_service.py --reload --log-level debug "$@"
    else
        echo -e "${GREEN}Starting in production mode...${NC}"
        exec python run_service.py "$@"
    fi
fi