#!/usr/bin/env bash
set -euo pipefail

PROMPT_FILE="${PROMPT_FILE:-ralph/PROMPT.md}"
MAX_ITERATIONS="${MAX_ITERATIONS:-40}"
COMPLETION_PROMISE="${COMPLETION_PROMISE:-<promise>COMPLETE</promise>}"
TIMEOUT_MINUTES="${TIMEOUT_MINUTES:-30}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-ralph/checkpoints}"
PROGRESS_FILE="${PROGRESS_FILE:-ralph/progress.txt}"
REBASE_STATE_FILE="${REBASE_STATE_FILE:-ralph/checkpoints/rebase_fail.count}"

if ! command -v claude >/dev/null 2>&1; then
  echo "Error: 'claude' CLI not found on PATH."
  exit 1
fi

for ((i=1; i<=MAX_ITERATIONS; i++)); do
  echo "=== Ralph iteration $i/$MAX_ITERATIONS ==="

  OUTPUT_FILE="ralph/ralph-out-$i.log"
  echo "Starting Claude run (timeout: ${TIMEOUT_MINUTES}m, log: $OUTPUT_FILE)"

  mkdir -p "$CHECKPOINT_DIR"
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  CHECKPOINT_FILE="$CHECKPOINT_DIR/pre_${STAMP}.patch"
  git diff > "$CHECKPOINT_FILE"

  if command -v timeout >/dev/null 2>&1; then
    set +e
    timeout "${TIMEOUT_MINUTES}m" \
      claude \
        --print \
        --no-session-persistence \
        --verbose \
        --output-format stream-json \
        --include-partial-messages \
        --permission-mode bypassPermissions \
        "@${PROMPT_FILE}" \
      > "$OUTPUT_FILE" &
    RUN_PID=$!
    while kill -0 "$RUN_PID" >/dev/null 2>&1; do
      echo "Ralph running... (iter $i)"
      sleep 30
    done
    wait "$RUN_PID"
    EXIT_CODE=$?
    set -e
  else
    set +e
    claude \
      --print \
      --no-session-persistence \
      --verbose \
      --output-format stream-json \
      --include-partial-messages \
      --permission-mode bypassPermissions \
      "@${PROMPT_FILE}" \
    > "$OUTPUT_FILE" &
    RUN_PID=$!
    while kill -0 "$RUN_PID" >/dev/null 2>&1; do
      echo "Ralph running... (iter $i)"
      sleep 30
    done
    wait "$RUN_PID"
    EXIT_CODE=$?
    set -e
  fi

  if [ "${EXIT_CODE:-0}" -eq 124 ]; then
    echo "⚠️ Timeout. Reverting working tree to pre-run checkpoint: $CHECKPOINT_FILE"
    git checkout -- .
    exit 1
  elif [ "${EXIT_CODE:-0}" -ne 0 ]; then
    echo "❌ Claude run failed with exit code $EXIT_CODE. Check $OUTPUT_FILE"
    exit 1
  fi

  if grep -qi "awaiting test run approval" "$OUTPUT_FILE"; then
    echo "❌ Ralph output indicates tests were not run. Stopping iteration."
    exit 1
  fi

  if grep -qiE "Rebasing|CONFLICT|not possible to fast-forward|could not apply" "$OUTPUT_FILE"; then
    PREV_COUNT=0
    if [ -f "$REBASE_STATE_FILE" ]; then
      PREV_COUNT="$(cat "$REBASE_STATE_FILE" 2>/dev/null || echo 0)"
    fi
    COUNT=$((PREV_COUNT + 1))
    echo "$COUNT" > "$REBASE_STATE_FILE"
    if [ "$COUNT" -ge 2 ]; then
      echo "❌ Rebase/pull failed in consecutive iterations. Stopping to avoid loop."
      exit 1
    fi
  else
    rm -f "$REBASE_STATE_FILE"
  fi

  if [ -f "$PROGRESS_FILE" ] && tail -n 20 "$PROGRESS_FILE" | grep -qi "blocked"; then
    echo "❌ Ralph output indicates BLOCKED state in $PROGRESS_FILE. Stopping iteration."
    exit 1
  fi

  if grep -qi "issue #[0-9].*complete" "$OUTPUT_FILE" && ! grep -qi "PR URL:" "$OUTPUT_FILE"; then
    echo "❌ Issue marked complete but no PR URL found. Stopping iteration."
    exit 1
  fi

  if grep -qF "$COMPLETION_PROMISE" "$OUTPUT_FILE"; then
    echo "✅ Completion promise found on iteration $i"
    exit 0
  fi

  sleep 5
 done

echo "⚠️ Max iterations ($MAX_ITERATIONS) reached without completion."
exit 1
