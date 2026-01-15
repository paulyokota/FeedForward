#!/bin/bash
#
# Codebase Search VDD Loop Orchestrator
#
# Runs the iterative VDD loop for improving codebase search quality.
# Follows the architecture in docs/architecture/codebase-search-vdd.md
#
# Usage:
#   ./run_vdd_loop.sh [--baseline] [--iteration N] [--max-iterations N]
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

    # Prompt for learning phase (manual for now)
    echo ""
    echo "Learning phase: Review $OUTPUT_DIR/iteration_$current_iteration/ and propose changes"
    echo "Press Enter to continue to next iteration..."
    read -r

    current_iteration=$((current_iteration + 1))
done

echo ""
echo "=== VDD Loop Complete ==="
echo "Total iterations: $((current_iteration - 1))"
echo "Progress log: $PROGRESS_FILE"
