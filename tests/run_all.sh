#!/bin/bash
# Run all Contabulate tests
# Usage: ./tests/run_all.sh

set -e
cd "$(dirname "$0")/.."

echo "========================================="
echo "Contabulate Test Suite"
echo "========================================="

FAILED=0

echo ""
echo "1. Python DB tests"
echo "-----------------------------------------"
if python3 tests/test_db.py; then
    echo "✅ Python DB tests passed"
else
    echo "❌ Python DB tests failed"
    FAILED=1
fi

echo ""
echo "2. Node.js search tests"
echo "-----------------------------------------"
if node tests/test_search.js; then
    echo "✅ Node.js search tests passed"
else
    echo "❌ Node.js search tests failed"
    FAILED=1
fi

echo ""
echo "========================================="
if [ $FAILED -eq 0 ]; then
    echo "All test suites passed! ✅"
else
    echo "Some tests failed ❌"
    exit 1
fi
