#!/bin/bash
#
# Codebase Search VDD Loop Orchestrator
#
# Runs the iterative VDD loop for improving codebase search quality.
# Follows the architecture in docs/architecture/codebase-search-vdd.md
#
# Usage:
#   ./run_vdd_loop.sh [OPTIONS]
#
# Options:
#   --baseline         Run baseline (iteration 0) only, then exit
#   --iteration N      Start from iteration N instead of auto-detecting
#   --max-iterations N Override max iterations from config
#   --dry-run          Analyze and propose changes but don't modify code
#   --manual           Pause after each iteration for manual review (legacy mode)
#
# Examples:
#   ./run_vdd_loop.sh                      # Full autonomous run
#   ./run_vdd_loop.sh --baseline           # Just run baseline measurement
#   ./run_vdd_loop.sh --dry-run            # See what changes would be made
#   ./run_vdd_loop.sh --max-iterations 5   # Run up to 5 iterations
#   ./run_vdd_loop.sh --manual             # Human-in-the-loop mode
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/outputs"
CONFIG_FILE="$SCRIPT_DIR/config.json"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"

# Parse arguments
BASELINE_ONLY=false
START_ITERATION=""
MAX_ITERATIONS=""
DRY_RUN=false
MANUAL_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --baseline)
            BASELINE_ONLY=true
            shift
            ;;
        --iteration)
            START_ITERATION="$2"
            shift 2
            ;;
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --manual)
            MANUAL_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Load config values
BASELINE_BATCH_SIZE=$(jq -r '.baseline_batch_size' "$CONFIG_FILE")
ITERATION_BATCH_SIZE=$(jq -r '.iteration_batch_size' "$CONFIG_FILE")
CONFIG_MAX_ITERATIONS=$(jq -r '.max_iterations' "$CONFIG_FILE")
MIN_ITERATIONS=$(jq -r '.min_iterations' "$CONFIG_FILE")
PRECISION_THRESHOLD=$(jq -r '.precision_threshold' "$CONFIG_FILE")
RECALL_THRESHOLD=$(jq -r '.recall_threshold' "$CONFIG_FILE")
CALIBRATION_ITERATIONS=$(jq -r '.calibration_iterations' "$CONFIG_FILE")

MAX_ITERATIONS="${MAX_ITERATIONS:-$CONFIG_MAX_ITERATIONS}"

echo "=== Codebase Search VDD Loop ==="
echo "Config: $CONFIG_FILE"
echo "Output: $OUTPUT_DIR"
echo "Max iterations: $MAX_ITERATIONS"
echo ""

# Function to run a single iteration
run_iteration() {
    local iteration_num=$1
    local batch_size=$2
    local iteration_dir="$OUTPUT_DIR/iteration_$iteration_num"

    echo "--- Iteration $iteration_num ---"
    mkdir -p "$iteration_dir"

    # Step 1: Fetch conversations
    echo "[1/4] Fetching $batch_size conversations..."
    python3 "$SCRIPT_DIR/fetch_conversations.py" \
        --batch-size "$batch_size" \
        > "$iteration_dir/conversations.json" \
        2> "$iteration_dir/fetch.log"

    local conv_count=$(jq 'length' "$iteration_dir/conversations.json")
    echo "      Fetched $conv_count conversations"

    # Step 2: Run search
    echo "[2/4] Running codebase search..."
    python3 "$SCRIPT_DIR/run_search.py" \
        < "$iteration_dir/conversations.json" \
        > "$iteration_dir/search_results.json" \
        2> "$iteration_dir/search.log"

    # Step 3: Evaluate results
    echo "[3/4] Evaluating with dual exploration..."

    # Note: evaluate_results.py determines calibration mode internally
    # based on iteration_number in the JSON input
    python3 "$SCRIPT_DIR/evaluate_results.py" \
        < "$iteration_dir/search_results.json" \
        > "$iteration_dir/evaluation.json" \
        2> "$iteration_dir/evaluation.log"

    # Step 4: Calculate metrics
    echo "[4/4] Calculating metrics..."
    local precision=$(jq -r '.aggregate.precision // 0' "$iteration_dir/evaluation.json")
    local recall=$(jq -r '.aggregate.recall // 0' "$iteration_dir/evaluation.json")
    local gestalt=$(jq -r '.aggregate.gestalt // 0' "$iteration_dir/evaluation.json")

    echo ""
    echo "Results for iteration $iteration_num:"
    echo "  Precision: $precision"
    echo "  Recall:    $recall"
    echo "  Gestalt:   $gestalt"

    # Update progress file
    cat >> "$PROGRESS_FILE" << EOF

## Iteration $iteration_num
Date: $(date '+%Y-%m-%d %H:%M:%S')
Batch size: $batch_size
Precision: $precision
Recall: $recall
Gestalt: $gestalt
EOF

    # Return metrics for convergence check
    echo "$precision $recall $gestalt"
}

# Run baseline (iteration 0) if needed
baseline_dir="$OUTPUT_DIR/iteration_0"
if [ ! -f "$baseline_dir/evaluation.json" ]; then
    echo "Running baseline (iteration 0) with $BASELINE_BATCH_SIZE conversations..."
    run_iteration 0 "$BASELINE_BATCH_SIZE"
    echo ""
fi

if [ "$BASELINE_ONLY" = true ]; then
    echo "Baseline complete. Exiting."
    exit 0
fi

# Determine starting iteration
current_iteration=${START_ITERATION:-1}

# Find the last completed iteration if not specified
if [ -z "$START_ITERATION" ]; then
    for i in $(seq 1 $MAX_ITERATIONS); do
        if [ -f "$OUTPUT_DIR/iteration_$i/evaluation.json" ]; then
            current_iteration=$((i + 1))
        fi
    done
fi

echo "Starting from iteration $current_iteration"
echo ""

# Main iteration loop
while [ "$current_iteration" -le "$MAX_ITERATIONS" ]; do
    metrics=$(run_iteration "$current_iteration" "$ITERATION_BATCH_SIZE")
    precision=$(echo "$metrics" | awk '{print $1}')
    recall=$(echo "$metrics" | awk '{print $2}')
    gestalt=$(echo "$metrics" | awk '{print $3}')

    # Check convergence (only after minimum iterations)
    if [ "$current_iteration" -ge "$MIN_ITERATIONS" ]; then
        # Compare against thresholds
        precision_met=$(echo "$precision >= $PRECISION_THRESHOLD" | bc -l)
        recall_met=$(echo "$recall >= $RECALL_THRESHOLD" | bc -l)

        if [ "$precision_met" -eq 1 ] && [ "$recall_met" -eq 1 ]; then
            echo ""
            echo "=== CONVERGED ==="
            echo "Precision ($precision) >= $PRECISION_THRESHOLD"
            echo "Recall ($recall) >= $RECALL_THRESHOLD"
            echo "Completed after $current_iteration iterations"
            break
        fi
    fi

    # If in calibration phase (iterations 1-2), run model comparison
    if [ "$current_iteration" -le "$CALIBRATION_ITERATIONS" ]; then
        echo ""
        echo "Calibration data recorded for iteration $current_iteration"
    fi

    # Learning phase: Apply improvements to search logic
    iteration_dir="$OUTPUT_DIR/iteration_$current_iteration"

    if [ "$MANUAL_MODE" = true ]; then
        # Manual mode: Pause for human review
        echo ""
        echo "Learning phase: Review $iteration_dir/ and propose changes"
        echo "Press Enter to continue to next iteration..."
        read -r
    else
        # Autonomous mode: Run apply_learnings.py
        echo ""
        echo "[5/5] Applying learnings (autonomous mode)..."

        dry_run_flag=""
        if [ "$DRY_RUN" = true ]; then
            dry_run_flag="--dry-run"
            echo "      (dry-run mode - no code changes will be made)"
        fi

        python3 "$SCRIPT_DIR/apply_learnings.py" \
            $dry_run_flag \
            < "$iteration_dir/evaluation.json" \
            > "$iteration_dir/learnings.json" \
            2> "$iteration_dir/learnings.log"

        # Log the changes made
        changes_applied=$(jq -r '.application.changes_applied // 0' "$iteration_dir/learnings.json")
        expected_precision=$(jq -r '.proposal.expected_precision_delta // 0' "$iteration_dir/learnings.json")
        expected_recall=$(jq -r '.proposal.expected_recall_delta // 0' "$iteration_dir/learnings.json")

        echo "      Changes applied: $changes_applied"
        echo "      Expected precision delta: +$expected_precision"
        echo "      Expected recall delta: +$expected_recall"

        # Update progress file with learnings
        cat >> "$PROGRESS_FILE" << EOF
Changes applied: $changes_applied
Expected precision delta: +$expected_precision
Expected recall delta: +$expected_recall
EOF
    fi

    current_iteration=$((current_iteration + 1))
done

# Final validation gate: verify the modified code is valid
echo ""
echo "=== Final Validation Gate ==="
echo ""

SEARCH_PROVIDER="$SCRIPT_DIR/../../src/story_tracking/services/codebase_context_provider.py"

# Check 1: Syntax validation (AST parsing)
VALIDATION_FAILED=false
FAILURE_TYPE=""

echo "[1/3] Checking Python syntax..."
if python3 -m py_compile "$SEARCH_PROVIDER" 2>/dev/null; then
    echo "      ✓ Syntax valid"
else
    echo "      ✗ SYNTAX ERROR - Code cannot be parsed"
    VALIDATION_FAILED=true
    FAILURE_TYPE="syntax"
fi

# Check 2: Import validation (can the module be imported)
echo "[2/3] Checking module import..."
if [ "$VALIDATION_FAILED" = false ]; then
    if python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR/../../src'); from story_tracking.services.codebase_context_provider import CodebaseContextProvider" 2>/dev/null; then
        echo "      ✓ Module imports successfully"
    else
        echo "      ✗ IMPORT ERROR - Module has runtime errors"
        VALIDATION_FAILED=true
        FAILURE_TYPE="import"
    fi
else
    echo "      - Skipped (syntax error)"
fi

# Check 3: Basic sanity check (required methods exist)
echo "[3/3] Checking required methods exist..."
if [ "$VALIDATION_FAILED" = false ]; then
    if python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/../../src')
from story_tracking.services.codebase_context_provider import CodebaseContextProvider
p = CodebaseContextProvider()
assert hasattr(p, 'explore_for_theme')
assert hasattr(p, '_extract_keywords')
assert hasattr(p, '_build_search_patterns')
print('OK')
" 2>/dev/null; then
        echo "      ✓ Required methods present"
    else
        echo "      ✗ MISSING METHODS - Key methods were removed"
        VALIDATION_FAILED=true
        FAILURE_TYPE="methods"
    fi
else
    echo "      - Skipped (prior error)"
fi

# Handle validation failure
if [ "$VALIDATION_FAILED" = true ]; then
    echo ""
    echo "=== VALIDATION FAILED ==="
    echo ""
    echo "The VDD loop made changes that broke the search provider."
    echo ""
    echo "To investigate and fix, run from Claude Code CLI:"
    echo "   Review the error: python3 -m py_compile $SEARCH_PROVIDER"
    echo "   View the changes: git diff $SEARCH_PROVIDER"
    echo "   Backups available: ls $SCRIPT_DIR/backups/"
    echo ""
    echo "Options:"
    echo "   1. Fix the issues manually and re-run validation"
    echo "   2. Restore from backup: cp $SCRIPT_DIR/backups/[latest].py $SEARCH_PROVIDER"
    echo "   3. Ask Claude Code to diagnose: 'Investigate the $FAILURE_TYPE error in $SEARCH_PROVIDER'"
    echo ""
    exit 1
fi

echo ""
echo "=== VDD Loop Complete ==="
echo ""
echo "Summary:"
echo "  Total iterations: $((current_iteration - 1))"
echo "  Progress log: $PROGRESS_FILE"
echo "  Modified file: $SEARCH_PROVIDER"
echo "  Backups: $SCRIPT_DIR/backups/"
echo ""
echo "=== Suggested Next Steps ==="
echo ""
echo "The codebase search logic has been modified. Before committing, run:"
echo ""
echo "1. Run existing tests to check for regressions:"
echo "   pytest tests/ -v -k codebase"
echo ""
echo "2. Run a five-personality code review on the changes:"
echo "   # From Claude Code CLI:"
echo "   /developer-kit:code-review src/story_tracking/services/codebase_context_provider.py"
echo ""
echo "3. If tests pass and review approves, commit the changes:"
echo "   git add src/story_tracking/services/codebase_context_provider.py"
echo "   git commit -m 'feat: VDD-optimized codebase search patterns'"
echo ""
echo "4. Optional: Create a PR with the VDD metrics:"
echo "   cat $PROGRESS_FILE"
echo ""
