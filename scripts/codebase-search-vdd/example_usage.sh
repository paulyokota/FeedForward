#!/bin/bash
#
# Example usage of evaluate_results.py
#
# This demonstrates how to use the dual exploration evaluator
# in the VDD iteration loop.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/outputs"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Codebase Search VDD - Example Usage ===${NC}\n"

# Check environment
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY not set"
    echo "Set it with: export ANTHROPIC_API_KEY='your-key-here'"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR/example"

echo -e "${GREEN}Step 1: Prepare search results${NC}"
echo "In a real iteration, run_search.py would generate this."
echo "For now, using test_input.json as example."
echo

echo -e "${GREEN}Step 2: Run evaluation${NC}"
echo "Command: cat test_input.json | python evaluate_results.py > outputs/example/evaluation.json"
echo

cat "$SCRIPT_DIR/test_input.json" | \
    python "$SCRIPT_DIR/evaluate_results.py" > "$OUTPUT_DIR/example/evaluation.json" 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Evaluation completed successfully${NC}\n"
else
    echo "✗ Evaluation failed. See error output above."
    exit 1
fi

echo -e "${GREEN}Step 3: View results${NC}"
echo "Output saved to: outputs/example/evaluation.json"
echo

# Display summary metrics
if command -v jq &> /dev/null; then
    echo "Summary metrics:"
    jq '.metrics.aggregate' "$OUTPUT_DIR/example/evaluation.json"
    echo
    echo "Per-product-area:"
    jq '.metrics.by_product_area' "$OUTPUT_DIR/example/evaluation.json"
    echo
    if [ "$(jq '.metrics.calibration' "$OUTPUT_DIR/example/evaluation.json")" != "null" ]; then
        echo "Calibration data:"
        jq '.metrics.calibration' "$OUTPUT_DIR/example/evaluation.json"
    fi
else
    echo "Install jq for pretty-printed metrics: brew install jq"
fi

echo
echo -e "${GREEN}Example complete!${NC}"
echo "See README.md for full documentation."
