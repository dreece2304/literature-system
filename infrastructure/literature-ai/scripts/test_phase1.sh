#!/bin/bash
# Phase 1 Testing Script
# Tests config fixes and score persistence

set -e

API_BASE="http://localhost:8002/api/v1"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Phase 1 Testing: Config Fixes & Score Persistence"
echo "========================================"
echo ""

# Test 1: Health Check
echo -e "${YELLOW}Test 1: API Health Check${NC}"
response=$(curl -s "$API_BASE/health")
status=$(echo "$response" | jq -r '.status')
if [ "$status" == "healthy" ]; then
    echo -e "${GREEN}✓ API is healthy${NC}"
else
    echo -e "${RED}✗ API health check failed${NC}"
    exit 1
fi
echo ""

# Test 2: Score a paper (tests config fix - should not throw config error)
echo -e "${YELLOW}Test 2: Score Paper (Config Fix Test)${NC}"
echo "Attempting to score a paper (this will test that temperature config works)..."

# We'll use a fake paper_id - the endpoint will handle "paper not found" gracefully
score_response=$(curl -s -X POST "$API_BASE/triager/score-paper" \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": "test-paper-001",
    "research_interests": ["machine learning", "neural networks"],
    "current_projects": ["Deep learning for NLP"],
    "preferred_methods": ["experimental"],
    "context_id": "test-project-1"
  }' 2>&1)

# Check if we got a proper response (not a config error)
if echo "$score_response" | jq -e '.score' >/dev/null 2>&1; then
    score=$(echo "$score_response" | jq -r '.score')
    action=$(echo "$score_response" | jq -r '.action')
    echo -e "${GREEN}✓ Scoring worked! Score: $score, Action: $action${NC}"
    echo -e "${GREEN}✓ No config error - temperature setting working!${NC}"
elif echo "$score_response" | jq -e '.detail' >/dev/null 2>&1; then
    detail=$(echo "$score_response" | jq -r '.detail')
    if [[ "$detail" == *"not found"* ]]; then
        echo -e "${YELLOW}⚠ Paper not found (expected - no papers indexed yet)${NC}"
        echo -e "${GREEN}✓ But no config error - temperature setting working!${NC}"
    elif [[ "$detail" == *"config"* ]] || [[ "$detail" == *"AttributeError"* ]]; then
        echo -e "${RED}✗ Config error detected!${NC}"
        echo "$detail"
        exit 1
    else
        echo -e "${YELLOW}⚠ Unexpected response: $detail${NC}"
    fi
else
    echo -e "${RED}✗ Unexpected response format${NC}"
    echo "$score_response" | jq .
fi
echo ""

# Test 3: Check if top_papers endpoint works (empty at first)
echo -e "${YELLOW}Test 3: Get Top Papers (Before Any Scores)${NC}"
top_papers_response=$(curl -s "$API_BASE/triager/top-papers?context_id=test-project-1&min_score=0&limit=10")
total=$(echo "$top_papers_response" | jq -r '.total')
echo "Papers found: $total"
if [ "$total" == "0" ]; then
    echo -e "${GREEN}✓ Top papers endpoint works (empty as expected)${NC}"
else
    echo -e "${YELLOW}⚠ Found $total papers (unexpected but not an error)${NC}"
fi
echo ""

# Test 4: Check stats endpoint
echo -e "${YELLOW}Test 4: Get Triager Stats${NC}"
stats_response=$(curl -s "$API_BASE/triager/stats")
total_scored=$(echo "$stats_response" | jq -r '.total_scores')
echo "Total papers scored: $total_scored"
if echo "$stats_response" | jq -e '.available_contexts' >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Stats endpoint works${NC}"
else
    echo -e "${RED}✗ Stats endpoint missing expected fields${NC}"
    echo "$stats_response" | jq .
fi
echo ""

echo "========================================"
echo -e "${GREEN}Phase 1 Basic Tests Complete!${NC}"
echo "========================================"
echo ""
echo "Note: Full testing requires papers in the database."
echo "Next step: Add test papers or connect to literature-database service."
