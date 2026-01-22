#!/usr/bin/env bash
set -euo pipefail

PROMPT_FILE="${PROMPT_FILE:-ralph/PROMPT.md}"
OUTPUT_FILE="${OUTPUT_FILE:-ralph/ralph-once.log}"
TIMEOUT_MINUTES="${TIMEOUT_MINUTES:-30}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-ralph/checkpoints}"
PROGRESS_FILE="${PROGRESS_FILE:-ralph/progress.txt}"

if ! command -v claude >/dev/null 2>&1; then
  echo "Error: 'claude' CLI not found on PATH."
  exit 1
fi

if command -v timeout >/dev/null 2>&1; then
  echo "Starting Claude run (timeout: ${TIMEOUT_MINUTES}m, log: $OUTPUT_FILE)"
  mkdir -p "$CHECKPOINT_DIR"
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  CHECKPOINT_FILE="$CHECKPOINT_DIR/pre_${STAMP}.patch"
  git diff > "$CHECKPOINT_FILE"

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
    echo "Ralph running..."
    sleep 30
  done
  wait "$RUN_PID"
  EXIT_CODE=$?
  set -e
else
  echo "Starting Claude run (no timeout, log: $OUTPUT_FILE)"
  mkdir -p "$CHECKPOINT_DIR"
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  CHECKPOINT_FILE="$CHECKPOINT_DIR/pre_${STAMP}.patch"
  git diff > "$CHECKPOINT_FILE"

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
    echo "Ralph running..."
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
  echo "❌ Ralph output indicates tests were not run."
  exit 1
fi

if [ -f "$PROGRESS_FILE" ] && tail -n 20 "$PROGRESS_FILE" | rg -qi "blocked"; then
  echo "❌ Ralph output indicates BLOCKED state in $PROGRESS_FILE"
  exit 1
fi

if grep -qi "issue #[0-9].*complete" "$OUTPUT_FILE" && ! grep -qi "PR URL:" "$OUTPUT_FILE"; then
  echo "❌ Issue marked complete but no PR URL found."
  exit 1
fi

if grep -qF "<promise>COMPLETE</promise>" "$OUTPUT_FILE"; then
  echo "✅ Completion promise found."
fi

echo "Output written to $OUTPUT_FILE"
