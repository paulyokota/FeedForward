#!/bin/bash

# Ralph V2 Loop - Pipeline Optimization
# Usage: ./ralph_v2.sh [max_iterations] [min_iterations]
#
# This script runs Claude Code in an autonomous loop to optimize the
# Feed Forward pipeline. Unlike V1, Ralph V2 modifies the pipeline itself
# rather than individual stories.
#
# Completion is blocked until min_iterations is reached to ensure
# thorough optimization and prevent premature completion.

set -e  # Exit on error

# Configuration
MAX_ITERATIONS=${1:-15}  # Default 15 iterations
MIN_ITERATIONS=${2:-3}   # Default 3 minimum iterations before completion allowed
ITERATION=0
COMPLETION_PROMISE="<promise>LOOP_COMPLETE</promise>"
PLATEAU_PROMISE="<promise>PLATEAU_REACHED</promise>"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/outputs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PROMPT_FILE="PROMPT_V2.md"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Header
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Ralph V2 - Pipeline Optimization Loop                ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Min iterations: $MIN_ITERATIONS (completion blocked before this)"
echo "  Max iterations: $MAX_ITERATIONS"
echo "  Working directory: $SCRIPT_DIR"
echo "  Prompt file: $PROMPT_FILE"
echo "  Output directory: $OUTPUT_DIR"
echo ""

# Verify required files exist
echo -e "${YELLOW}Verifying required files...${NC}"

if [ ! -f "${SCRIPT_DIR}/${PROMPT_FILE}" ]; then
    echo -e "${RED}ERROR: ${PROMPT_FILE} not found in ${SCRIPT_DIR}${NC}"
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/progress.txt" ]; then
    echo -e "${RED}ERROR: progress.txt not found in ${SCRIPT_DIR}${NC}"
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/test_data/manifest.json" ]; then
    echo -e "${RED}ERROR: test_data/manifest.json not found${NC}"
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/run_pipeline_test.py" ]; then
    echo -e "${RED}ERROR: run_pipeline_test.py not found${NC}"
    exit 1
fi

echo -e "${GREEN}  ✓ ${PROMPT_FILE}${NC}"
echo -e "${GREEN}  ✓ progress.txt${NC}"
echo -e "${GREEN}  ✓ test_data/manifest.json${NC}"
echo -e "${GREEN}  ✓ run_pipeline_test.py${NC}"
echo ""

# Log start time
echo "=== Ralph V2 Loop Started at $(date) ===" >> "${SCRIPT_DIR}/progress.txt"
echo "" >> "${SCRIPT_DIR}/progress.txt"

# Add fresh run marker (prevents premature completion)
echo -e "${YELLOW}Adding fresh run marker...${NC}"
echo "=== FRESH RUN MARKER ===" >> "${SCRIPT_DIR}/progress.txt"
echo "This is a new run. Previous completion status is invalid." >> "${SCRIPT_DIR}/progress.txt"
echo "Ralph must make pipeline changes before declaring completion." >> "${SCRIPT_DIR}/progress.txt"
echo "MINIMUM ITERATIONS: $MIN_ITERATIONS (completion blocked before this)" >> "${SCRIPT_DIR}/progress.txt"
echo "MAXIMUM ITERATIONS: $MAX_ITERATIONS (HARD CAP - must stop at this iteration)" >> "${SCRIPT_DIR}/progress.txt"
echo "SCOPING VALIDATION: Uses local codebase access via Read/Glob tools" >> "${SCRIPT_DIR}/progress.txt"
echo "" >> "${SCRIPT_DIR}/progress.txt"

# Invalidate previous test results (force re-evaluation)
echo -e "${YELLOW}Clearing previous test results...${NC}"
rm -f "${OUTPUT_DIR}"/test_results_*.json 2>/dev/null || true

# Main loop
while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    ITERATION_OUTPUT="${OUTPUT_DIR}/iteration_${ITERATION}_${TIMESTAMP}.txt"

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  ITERATION $ITERATION of $MAX_ITERATIONS${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # Record iteration start in progress file
    echo "### Iteration $ITERATION" >> "${SCRIPT_DIR}/progress.txt"
    echo "Started: $(date)" >> "${SCRIPT_DIR}/progress.txt"

    # Change to script directory so relative paths work
    cd "${SCRIPT_DIR}"

    echo -e "${YELLOW}Running Claude Code with V2 prompt...${NC}"
    echo ""

    # Run claude with the V2 prompt file, capturing output
    if claude --dangerously-skip-permissions < "${PROMPT_FILE}" > "${ITERATION_OUTPUT}" 2>&1; then
        echo -e "${GREEN}Claude execution completed${NC}"
    else
        CLAUDE_EXIT=$?
        echo -e "${RED}Claude exited with code: $CLAUDE_EXIT${NC}"
        echo "Exit code: $CLAUDE_EXIT" >> "${SCRIPT_DIR}/progress.txt"
    fi

    # Check for completion promise
    if grep -q "$COMPLETION_PROMISE" "${ITERATION_OUTPUT}"; then
        # Enforce minimum iterations before accepting completion
        if [ $ITERATION -lt $MIN_ITERATIONS ]; then
            echo ""
            echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
            echo -e "${YELLOW}║     COMPLETION BLOCKED - Minimum iterations not met      ║${NC}"
            echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
            echo ""
            echo -e "${YELLOW}Ralph claimed completion at iteration $ITERATION, but minimum is $MIN_ITERATIONS${NC}"
            echo -e "${YELLOW}Continuing loop to ensure thorough optimization...${NC}"
            echo ""
            echo "WARNING: Completion promise rejected (iteration $ITERATION < min $MIN_ITERATIONS)" >> "${SCRIPT_DIR}/progress.txt"
            # Don't exit - continue the loop
        else
            echo ""
            echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
            echo -e "${GREEN}║     PIPELINE OPTIMIZATION COMPLETE                       ║${NC}"
            echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
            echo ""
            echo -e "${GREEN}Loop finished successfully at iteration $ITERATION${NC}"
            echo ""

            # Log completion
            echo "Completed: $(date)" >> "${SCRIPT_DIR}/progress.txt"
            echo "Status: SUCCESS - Pipeline optimization complete" >> "${SCRIPT_DIR}/progress.txt"
            echo "" >> "${SCRIPT_DIR}/progress.txt"
            echo "=== Ralph V2 Loop Completed Successfully ===" >> "${SCRIPT_DIR}/progress.txt"

            # Show final output
            echo -e "${BLUE}Final output:${NC}"
            echo "---"
            tail -100 "${ITERATION_OUTPUT}"
            echo "---"

            exit 0
        fi
    fi

    # Check for plateau promise
    if grep -q "$PLATEAU_PROMISE" "${ITERATION_OUTPUT}"; then
        echo ""
        echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}║     PLATEAU REACHED - Human Intervention Needed          ║${NC}"
        echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
        echo ""

        echo "Status: PLATEAU - Human intervention needed" >> "${SCRIPT_DIR}/progress.txt"

        # Show recommendation
        echo -e "${YELLOW}Ralph has reached a plateau. Review the output below:${NC}"
        echo "---"
        tail -50 "${ITERATION_OUTPUT}"
        echo "---"

        exit 0
    fi

    # Check for errors
    ERROR_COUNT=$(grep -ci "error\|exception\|failed" "${ITERATION_OUTPUT}" 2>/dev/null | head -1 || echo "0")

    if [ "$ERROR_COUNT" -gt 20 ]; then
        echo -e "${RED}WARNING: High error count detected: $ERROR_COUNT errors${NC}"
        echo -e "${RED}Review iteration output for details.${NC}"
        echo "Warning: High error count ($ERROR_COUNT)" >> "${SCRIPT_DIR}/progress.txt"
    fi

    # Record iteration end
    echo "Ended: $(date)" >> "${SCRIPT_DIR}/progress.txt"
    echo "Status: Continuing (no completion promise)" >> "${SCRIPT_DIR}/progress.txt"
    echo "" >> "${SCRIPT_DIR}/progress.txt"

    echo ""
    echo -e "${BLUE}Iteration $ITERATION complete${NC}"
    echo "  Output saved to: ${ITERATION_OUTPUT}"
    echo "  Completion promise: NOT FOUND (continuing...)"
    echo ""

    # Brief pause to avoid rate limits
    sleep 3
done

# Max iterations reached
echo ""
echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║     MAX ITERATIONS REACHED ($MAX_ITERATIONS)                            ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Loop terminated without completion promise."
echo "Check progress.txt and test results for current state."
echo ""

# Log termination
echo "=== Ralph V2 Loop Terminated (Max Iterations) ===" >> "${SCRIPT_DIR}/progress.txt"
echo "Final iteration: $ITERATION" >> "${SCRIPT_DIR}/progress.txt"
echo "Time: $(date)" >> "${SCRIPT_DIR}/progress.txt"

exit 1
