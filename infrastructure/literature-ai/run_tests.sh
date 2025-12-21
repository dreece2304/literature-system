#!/bin/bash
# Run pytest with coverage reporting
# Usage: bash run_tests.sh [options]

cd "$(dirname "$0")"

echo "========================================"
echo "Running Literature-AI Test Suite"
echo "========================================"
echo ""

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo "ERROR: pytest not found"
    echo "Please activate the litai conda environment first:"
    echo "  conda activate litai"
    exit 1
fi

# Run pytest with coverage
pytest -v "$@"

exit_code=$?

echo ""
echo "========================================"
if [ $exit_code -eq 0 ]; then
    echo "✓ Tests passed!"
else
    echo "✗ Tests failed (exit code: $exit_code)"
fi
echo "========================================"
echo ""
echo "Coverage report saved to: htmlcov/index.html"
echo ""

exit $exit_code
