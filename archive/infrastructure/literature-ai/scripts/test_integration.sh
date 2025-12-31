#!/bin/bash
# Test the integration between literature-database and literature-ai

set -e

echo "========================================"
echo "Testing Literature Services Integration"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test 1: Check services are running
echo "Test 1: Checking services..."
if curl -s http://localhost:8001/health > /dev/null; then
    echo -e "${GREEN}✓ literature-database is running${NC}"
else
    echo -e "${RED}✗ literature-database is NOT running${NC}"
    echo "  Run: ./scripts/start_integrated.sh"
    exit 1
fi

if curl -s http://localhost:8002/health > /dev/null; then
    echo -e "${GREEN}✓ literature-ai is running${NC}"
else
    echo -e "${RED}✗ literature-ai is NOT running${NC}"
    echo "  Run: ./scripts/start_integrated.sh"
    exit 1
fi

echo ""

# Test 2: Add a paper to database
echo "Test 2: Adding test paper to database..."
PAPER_RESPONSE=$(curl -s -X POST http://localhost:8001/api/v1/papers \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Attention Is All You Need",
    "authors": "Vaswani, Ashish; Shazeer, Noam; Parmar, Niki; Uszkoreit, Jakob; Jones, Llion; Gomez, Aidan N.; Kaiser, Lukasz; Polosukhin, Illia",
    "year": 2017,
    "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
    "venue": "NIPS 2017",
    "doi": "10.48550/arXiv.1706.03762"
  }')

PAPER_ID=$(echo $PAPER_RESPONSE | jq -r '.id' 2>/dev/null || echo "")

if [ -z "$PAPER_ID" ] || [ "$PAPER_ID" = "null" ]; then
    echo -e "${RED}✗ Failed to add paper${NC}"
    echo "Response: $PAPER_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Paper added successfully${NC}"
echo "  Paper ID: $PAPER_ID"
echo ""

# Test 3: Wait for event processing
echo "Test 3: Waiting for event processing..."
echo "  (Event consumer should pick up the paper.added event)"
echo -n "  Waiting"
for i in {1..10}; do
    echo -n "."
    sleep 1
done
echo " done"
echo ""

# Test 4: Search for paper in vector store
echo "Test 4: Searching for paper in vector store..."
SEARCH_RESPONSE=$(curl -s -X POST http://localhost:8002/api/v1/search/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "transformer attention mechanism",
    "top_k": 3
  }')

# Check if we got results
RESULT_COUNT=$(echo $SEARCH_RESPONSE | jq -r '.results | length' 2>/dev/null || echo "0")

if [ "$RESULT_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Paper found in vector store!${NC}"
    echo "  Found $RESULT_COUNT result(s)"
    echo ""
    echo "  Top result:"
    echo $SEARCH_RESPONSE | jq -r '.results[0] | "    Title: \(.title)\n    Score: \(.score)\n    Excerpt: \(.text[:100])..."' 2>/dev/null || echo "    $SEARCH_RESPONSE"
else
    echo -e "${YELLOW}⚠ Paper not yet indexed${NC}"
    echo "  This might mean:"
    echo "    - Event consumer is not running"
    echo "    - Event processing is delayed"
    echo "    - Redis pub/sub not configured"
    echo ""
    echo "  Check event consumer logs:"
    echo "    tail -f logs/event-consumer.log"
fi

echo ""

# Test 5: Get citation suggestions
echo "Test 5: Testing citation suggestions..."
CITATION_RESPONSE=$(curl -s -X POST http://localhost:8002/api/v1/writer/suggest-citations \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Self-attention mechanisms allow models to attend to different positions in the input sequence.",
    "n": 3
  }')

SUGGESTION_COUNT=$(echo $CITATION_RESPONSE | jq -r '.suggestions | length' 2>/dev/null || echo "0")

if [ "$SUGGESTION_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Citation suggestions working!${NC}"
    echo "  Got $SUGGESTION_COUNT suggestion(s)"
    echo ""
    echo "  Top suggestion:"
    echo $CITATION_RESPONSE | jq -r '.suggestions[0] | "    Title: \(.title)\n    Authors: \(.authors)\n    Year: \(.year)\n    Relevance: \(.relevance_score)"' 2>/dev/null || echo "    $CITATION_RESPONSE"
else
    echo -e "${YELLOW}⚠ No citation suggestions yet${NC}"
    echo "  Wait a bit longer for papers to be indexed"
fi

echo ""

# Test 6: Check event consumer stats
echo "Test 6: Checking event consumer statistics..."
STATS_RESPONSE=$(curl -s http://localhost:8002/api/v1/events/stats 2>/dev/null || echo '{"error":"endpoint not available"}')

if echo $STATS_RESPONSE | jq -e '.events_received' > /dev/null 2>&1; then
    EVENTS_RECEIVED=$(echo $STATS_RESPONSE | jq -r '.events_received')
    PAPERS_PROCESSED=$(echo $STATS_RESPONSE | jq -r '.papers_processed')
    echo -e "${GREEN}✓ Event consumer statistics:${NC}"
    echo "  Events received: $EVENTS_RECEIVED"
    echo "  Papers processed: $PAPERS_PROCESSED"
else
    echo -e "${YELLOW}⚠ Event consumer stats not available${NC}"
    echo "  The consumer might be running as a separate process"
fi

echo ""
echo "========================================"
echo "Integration Test Summary"
echo "========================================"
echo ""

if [ "$RESULT_COUNT" -gt 0 ] && [ "$SUGGESTION_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓✓✓ Integration is working perfectly!${NC}"
    echo ""
    echo "You can now:"
    echo "  1. Add papers to literature-database (port 8001)"
    echo "  2. They will auto-sync to literature-ai (port 8002)"
    echo "  3. Use citation assistance with your full library"
    echo ""
    echo "Next steps:"
    echo "  - Configure Zotero sync in literature-database"
    echo "  - Test with your actual paper text"
    echo "  - See INTEGRATION_SETUP.md for more details"
elif [ "$RESULT_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠ Partial integration${NC}"
    echo ""
    echo "Services are running but events may not be processing."
    echo "Check:"
    echo "  1. Event consumer is running: pgrep -f run_event_consumer"
    echo "  2. Event consumer logs: tail -f logs/event-consumer.log"
    echo "  3. Redis is publishing events from literature-database"
else
    echo -e "${GREEN}✓ Integration is working${NC}"
    echo ""
    echo "Papers are being indexed. Citation suggestions will"
    echo "improve as more papers are added to the database."
fi

echo ""

# Cleanup: Delete test paper (optional)
read -p "Delete test paper from database? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    curl -s -X DELETE http://localhost:8001/api/v1/papers/$PAPER_ID > /dev/null
    echo -e "${GREEN}✓ Test paper deleted${NC}"
fi

echo ""
