# Integration Scripts

Quick reference for starting and testing the integrated literature services.

## Quick Start

```bash
# Start everything (database + AI + event consumer)
./scripts/start_integrated.sh

# Test the integration
./scripts/test_integration.sh

# Stop everything
./scripts/stop_integrated.sh
```

## Individual Scripts

### start_integrated.sh
Starts all services needed for full integration:
- literature-database (port 8001)
- literature-ai API (port 8002)
- Event consumer (background process)

**Prerequisites:**
- Redis running
- Ollama running
- conda environments: `litdb` and `litai`

### stop_integrated.sh
Stops all integrated services gracefully.

### test_integration.sh
End-to-end integration test:
1. Verifies services are running
2. Adds a test paper to database
3. Waits for event processing
4. Checks if paper appears in vector store
5. Tests citation suggestions
6. Shows event consumer statistics

### run_event_consumer.py
Standalone event consumer that:
- Listens to Redis `paper.events` channel
- Fetches papers from literature-database API
- Generates embeddings
- Stores in ChromaDB vector store

Can be run separately from the API:
```bash
python scripts/run_event_consumer.py
```

## Logs

All services log to `logs/` directory:
- `litdb-service.log` - literature-database API
- `litai-api.log` - literature-ai API
- `event-consumer.log` - Event consumer

```bash
# Watch all logs
tail -f logs/*.log

# Watch specific log
tail -f logs/event-consumer.log
```

## Troubleshooting

**Services won't start:**
```bash
# Check prerequisites
redis-cli ping                     # Should return PONG
curl http://localhost:11434/api/version  # Should return Ollama version
conda env list                     # Should show litdb and litai
```

**Papers not syncing:**
```bash
# Check event consumer is running
pgrep -f run_event_consumer

# Check event consumer logs
tail -f logs/event-consumer.log

# Manually test Redis pub/sub
redis-cli
SUBSCRIBE paper.events
```

**Port already in use:**
```bash
# Find what's using the port
lsof -i:8001  # or 8002

# Kill the process
kill <PID>
```

## See Also

- `../INTEGRATION_SETUP.md` - Detailed integration guide
- `../QUICK_START_CITATIONS.md` - Citation assistance usage
- `../README.md` - Main project documentation
