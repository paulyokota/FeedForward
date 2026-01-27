#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Running coherence loop preflight..."
SECOND_MANIFEST="${SECOND_MANIFEST:-}" PYTHON_BIN="${PYTHON_BIN:-}" \
  bash "${SCRIPT_DIR}/preflight.sh"

echo "Preflight OK. Starting loop."
SECOND_MANIFEST="${SECOND_MANIFEST:-}" PYTHON_BIN="${PYTHON_BIN:-}" \
  bash "${SCRIPT_DIR}/ralph_loop.sh" "$@"
