#!/bin/bash

# Ralph Loop for Feed Forward Story Generation
# Usage: ./ralph.sh [max_iterations]
#
# This script runs Claude Code in an autonomous loop to generate, refine,
# and validate engineering stories from user feedback. Each iteration
# reads PROMPT.md and continues until completion or max iterations.

set -e  # Exit on error

# Configuration
MAX_ITERATIONS=${1:-15}  # Default 15 iterations
ITERATION=0
COMPLETION_PROMISE="<promise>LOOP_COMPLETE</promise>"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/outputs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Header
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Ralph Wiggum Autonomous Loop - Feed Forward          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Max iterations: $MAX_ITERATIONS"
echo "  Working directory: $SCRIPT_DIR"
echo "  Prompt file: PROMPT.md"
echo "  Output directory: $OUTPUT_DIR"
echo ""

# Verify required files exist
echo -e "${YELLOW}Verifying required files...${NC}"

if [ ! -f "${SCRIPT_DIR}/PROMPT.md" ]; then
    echo -e "${RED}ERROR: PROMPT.md not found in ${SCRIPT_DIR}${NC}"
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/prd.json" ]; then
    echo -e "${RED}ERROR: prd.json not found in ${SCRIPT_DIR}${NC}"
    exit 1
fi

if [ ! -f "${SCRIPT_DIR}/progress.txt" ]; then
    echo -e "${RED}ERROR: progress.txt not found in ${SCRIPT_DIR}${NC}"
    exit 1
fi

echo -e "${GREEN}  ✓ PROMPT.md${NC}"
echo -e "${GREEN}  ✓ prd.json${NC}"
echo -e "${GREEN}  ✓ progress.txt${NC}"
echo ""

# Log start time
echo "=== Ralph Loop Started at $(date) ===" >> "${SCRIPT_DIR}/progress.txt"
echo "" >> "${SCRIPT_DIR}/progress.txt"

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

    # Run Claude Code with prompt
    # Change to script directory so relative paths work
    cd "${SCRIPT_DIR}"

    echo -e "${YELLOW}Running Claude Code...${NC}"
    echo ""

    # Run claude with the prompt file, capturing output
    if claude --dangerously-skip-permissions < PROMPT.md > "${ITERATION_OUTPUT}" 2>&1; then
        echo -e "${GREEN}Claude execution completed${NC}"
    else
        CLAUDE_EXIT=$?
        echo -e "${RED}Claude exited with code: $CLAUDE_EXIT${NC}"
        echo "Exit code: $CLAUDE_EXIT" >> "${SCRIPT_DIR}/progress.txt"
    fi

    # Check for completion promise
    if grep -q "$COMPLETION_PROMISE" "${ITERATION_OUTPUT}"; then
        echo ""
        echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║     COMPLETION PROMISE DETECTED                          ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "${GREEN}Loop finished successfully at iteration $ITERATION${NC}"
        echo ""

        # Log completion
        echo "Completed: $(date)" >> "${SCRIPT_DIR}/progress.txt"
        echo "Status: SUCCESS - Completion promise detected" >> "${SCRIPT_DIR}/progress.txt"
        echo "" >> "${SCRIPT_DIR}/progress.txt"
        echo "=== Ralph Loop Completed Successfully ===" >> "${SCRIPT_DIR}/progress.txt"

        # Show final output
        echo -e "${BLUE}Final output:${NC}"
        echo "---"
        tail -100 "${ITERATION_OUTPUT}"
        echo "---"

        exit 0
    fi

    # Check for plateau promise (acceptable stopping point)
    if grep -q "<promise>PLATEAU_REACHED</promise>" "${ITERATION_OUTPUT}"; then
        echo ""
        echo -e "${YELLOW}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}║     PLATEAU REACHED - Acceptable Stopping Point          ║${NC}"
        echo -e "${YELLOW}╚══════════════════════════════════════════════════════════╝${NC}"
        echo ""

        echo "Status: PLATEAU - Acceptable stopping point" >> "${SCRIPT_DIR}/progress.txt"
        exit 0
    fi

    # Check for critical errors
    ERROR_COUNT=$(grep -ci "error\|exception\|failed" "${ITERATION_OUTPUT}" 2>/dev/null | head -1 || echo "0")

    if [ "$ERROR_COUNT" -gt 20 ]; then
        echo -e "${RED}WARNING: High error count detected: $ERROR_COUNT errors${NC}"
        echo -e "${RED}Claude may be stuck. Review progress.txt for details.${NC}"
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
echo "Check progress.txt and prd.json for current state."
echo ""

# Log termination
echo "=== Ralph Loop Terminated (Max Iterations) ===" >> "${SCRIPT_DIR}/progress.txt"
echo "Final iteration: $ITERATION" >> "${SCRIPT_DIR}/progress.txt"
echo "Time: $(date)" >> "${SCRIPT_DIR}/progress.txt"

exit 1
