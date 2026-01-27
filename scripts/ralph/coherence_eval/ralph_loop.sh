#!/bin/bash

# Ralph loop for coherence improvements.
# Iterates: eval -> Claude changes -> eval, until score target or max iterations.

set -euo pipefail

MAX_ITERATIONS=${1:-8}
PYTHON_BIN=${PYTHON_BIN:-}
TARGET_SCORE=${TARGET_SCORE:-0.6}
MAX_OVER_MERGE=${MAX_OVER_MERGE:-0}
MIN_IMPROVEMENT=${MIN_IMPROVEMENT:-0.05}
MIN_GROUPS_SCORED=${MIN_GROUPS_SCORED:-6}
MIN_PACK_RECALL=${MIN_PACK_RECALL:-0.10}
SECOND_MANIFEST=${SECOND_MANIFEST:-}
SECOND_MIN_SCORE_DELTA=${SECOND_MIN_SCORE_DELTA:--0.05}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DATA_DIR="${ROOT_DIR}/data/coherence_eval"
OUTPUT_DIR="${DATA_DIR}/outputs"
SECOND_OUTPUT_DIR="${OUTPUT_DIR}/secondary"
MANIFEST="${SCRIPT_DIR}/manifest.json"
SECOND_BASELINE="${SECOND_OUTPUT_DIR}/baseline.json"

if [ -z "${PYTHON_BIN}" ]; then
  if command -v python3.10 >/dev/null 2>&1; then
    PYTHON_BIN=python3.10
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  else
    echo "Missing required tool: python3 (or python3.10)" >&2
    exit 1
  fi
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "Missing required tool: claude" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
if [ -n "${SECOND_MANIFEST}" ]; then
  mkdir -p "${SECOND_OUTPUT_DIR}"
fi

echo "Ralph coherence loop"
echo "  iterations: ${MAX_ITERATIONS}"
echo "  target_score: ${TARGET_SCORE}"
echo "  max_over_merge: ${MAX_OVER_MERGE}"
echo "  min_improvement: ${MIN_IMPROVEMENT}"
echo "  min_groups_scored: ${MIN_GROUPS_SCORED}"
echo "  min_pack_recall: ${MIN_PACK_RECALL}"
if [ -n "${SECOND_MANIFEST}" ]; then
  echo "  second_manifest: ${SECOND_MANIFEST}"
  echo "  second_min_score_delta: ${SECOND_MIN_SCORE_DELTA}"
fi
echo ""

best_score=-999
best_over_merge=999
best_second_score=-999
secondary_baseline_score=-999

if [ -f "${OUTPUT_DIR}/baseline.json" ]; then
  baseline_score=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/baseline.json").read_text())
summary = data.get("summary", {})
print(summary.get("score", -999))
EOF
)
  baseline_over_merge=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/baseline.json").read_text())
summary = data.get("summary", {})
print(summary.get("over_merge_count", 999))
EOF
)
  best_score=${baseline_score}
  best_over_merge=${baseline_over_merge}
fi
if [ -n "${SECOND_MANIFEST}" ] && [ -f "${SECOND_BASELINE}" ]; then
  secondary_baseline_score=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${SECOND_BASELINE}").read_text())
summary = data.get("summary", {})
print(summary.get("score", -999))
EOF
)
  best_second_score=${secondary_baseline_score}
fi

if [ -n "$(git diff --name-only)" ] || [ -n "$(git diff --cached --name-only)" ]; then
  echo "Working tree has tracked changes. Commit/stash before running the loop." >&2
  exit 1
fi

for iteration in $(seq 1 "${MAX_ITERATIONS}"); do
  echo ""
  echo "=== Iteration ${iteration} ==="

  ${PYTHON_BIN} "${SCRIPT_DIR}/run_eval.py" \
    --manifest "${MANIFEST}" \
    --data-dir "${DATA_DIR}" \
    --output-dir "${OUTPUT_DIR}"

  if [ ! -f "${OUTPUT_DIR}/baseline.json" ]; then
    cp "${OUTPUT_DIR}/metrics.json" "${OUTPUT_DIR}/baseline.json"
    best_score=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/baseline.json").read_text())
summary = data.get("summary", {})
print(summary.get("score", -999))
EOF
)
    best_over_merge=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/baseline.json").read_text())
summary = data.get("summary", {})
print(summary.get("over_merge_count", 999))
EOF
)
  fi

  current_summary=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
metrics = json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text())
print(json.dumps(metrics, indent=2))
EOF
)
  one_line_summary=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
summary = json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text()).get("summary", {})
print(
    f"score={summary.get('score', -999)} "
    f"over_merge={summary.get('over_merge_count', 999)} "
    f"groups_scored={summary.get('groups_scored', 0)} "
    f"pack_recall={summary.get('pack_recall_avg', 0.0)}"
)
EOF
)
  echo "Metrics: ${one_line_summary}"
  cat > "${OUTPUT_DIR}/status.txt" <<EOF
iteration=${iteration}
${one_line_summary}
EOF
  if [ -n "${SECOND_MANIFEST}" ]; then
    ${PYTHON_BIN} "${SCRIPT_DIR}/run_eval.py" \
      --manifest "${SECOND_MANIFEST}" \
      --data-dir "${DATA_DIR}" \
      --output-dir "${SECOND_OUTPUT_DIR}"
    if [ ! -f "${SECOND_BASELINE}" ]; then
      cp "${SECOND_OUTPUT_DIR}/metrics.json" "${SECOND_BASELINE}"
      secondary_baseline_score=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${SECOND_BASELINE}").read_text())
summary = data.get("summary", {})
print(summary.get("score", -999))
EOF
)
      best_second_score=${secondary_baseline_score}
    fi
    second_summary=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
summary = json.loads(Path("${SECOND_OUTPUT_DIR}/metrics.json").read_text()).get("summary", {})
print(
    f"score={summary.get('score', -999)} "
    f"over_merge={summary.get('over_merge_count', 999)} "
    f"groups_scored={summary.get('groups_scored', 0)} "
    f"pack_recall={summary.get('pack_recall_avg', 0.0)}"
)
EOF
)
    echo "Second metrics: ${second_summary}"
    cat >> "${OUTPUT_DIR}/status.txt" <<EOF
second_${second_summary}
EOF
  fi

  mixed_groups=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path

manifest = json.loads(Path("${MANIFEST}").read_text())
groups = json.loads(Path("${OUTPUT_DIR}/groups.json").read_text())

pack_by_conv = {}
for pack in manifest.get("packs", []):
    pid = pack.get("pack_id")
    for cid in pack.get("conversation_ids", []):
        pack_by_conv[str(cid)] = pid

rows = []
for gid, convs in groups.items():
    if len(convs) < 3:
        continue
    counts = {}
    for cid in convs:
        pack = pack_by_conv.get(str(cid), "unassigned")
        counts[pack] = counts.get(pack, 0) + 1
    if len(counts) > 1:
        rows.append((len(convs), gid, counts))

rows.sort(reverse=True)
for size, gid, counts in rows[:10]:
    print(f"- {gid} size={size} packs={counts}")
EOF
)

  prompt_path="${OUTPUT_DIR}/iteration_${iteration}_prompt.md"
  cat > "${prompt_path}" <<EOF
You are running the Ralph coherence loop. Your goal is to improve coherence metrics
on the frozen dataset. You may change code under src/services or src/story_tracking
that affects clustering or PM review. Do NOT change the dataset files, manifest, or
evaluation scripts. Keep changes minimal and explain them.

Current metrics (latest run):
${current_summary}

Top mixed groups (size>=3):
${mixed_groups}

Constraints:
- Preserve feature behavior outside clustering where possible.
- Avoid changes that hard-code to this dataset.
- Coverage guardrails: groups_scored >= ${MIN_GROUPS_SCORED}, pack_recall_avg >= ${MIN_PACK_RECALL}.
- Do not add issue_signature as a merge step (splits or diagnostics are ok).
- Allowed levers include (but are not limited to): product_area/component keys, error strings,
  embedding thresholds (with coverage constraints), and theme/facet metadata.
- After changes, re-run the loop and check for improved score + reduced over-merge.

If you make changes, explain why they should improve coherence and where you changed.
When finished, print: <promise>LOOP_COMPLETE</promise>
EOF

  echo "Running Claude (iteration ${iteration})..."
  if ! claude --dangerously-skip-permissions < "${prompt_path}" > "${OUTPUT_DIR}/iteration_${iteration}.log" 2>&1; then
    echo "Claude exited with error. See ${OUTPUT_DIR}/iteration_${iteration}.log" >&2
    exit 1
  fi
  echo "Claude completed."

  if git diff --unified=0 -- src/services/hybrid_clustering_service.py | rg -n "^\\+.*issue_signature" >/dev/null 2>&1; then
    echo "❌ Detected issue_signature added as merge logic. Rejecting iteration." >&2
    exit 1
  fi

  ${PYTHON_BIN} "${SCRIPT_DIR}/run_eval.py" \
    --manifest "${MANIFEST}" \
    --data-dir "${DATA_DIR}" \
    --output-dir "${OUTPUT_DIR}"

  current_score=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text())
summary = data.get("summary", {})
print(summary.get("score", -999))
EOF
)
  current_over_merge=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text())
summary = data.get("summary", {})
print(summary.get("over_merge_count", 999))
EOF
)
  current_groups_scored=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text())
summary = data.get("summary", {})
print(summary.get("groups_scored", 0))
EOF
)
  current_pack_recall=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text())
summary = data.get("summary", {})
print(summary.get("pack_recall_avg", 0.0))
EOF
)
  second_score_delta_ok="1"
  if [ -n "${SECOND_MANIFEST}" ]; then
    second_score=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${SECOND_OUTPUT_DIR}/metrics.json").read_text())
summary = data.get("summary", {})
print(summary.get("score", -999))
EOF
)
    second_score_delta_ok=$(${PYTHON_BIN} - <<EOF
current = float("${second_score}")
baseline = float("${secondary_baseline_score}")
min_delta = float("${SECOND_MIN_SCORE_DELTA}")
print("1" if current >= (baseline + min_delta) else "0")
EOF
)
  fi

  improved=$(${PYTHON_BIN} - <<EOF
best_score = float("${best_score}")
best_over = int("${best_over_merge}")
current_score = float("${current_score}")
current_over = int("${current_over_merge}")
min_improvement = float("${MIN_IMPROVEMENT}")
min_groups = int("${MIN_GROUPS_SCORED}")
min_recall = float("${MIN_PACK_RECALL}")
current_groups = int("${current_groups_scored}")
current_recall = float("${current_pack_recall}")
second_ok = int("${second_score_delta_ok}")

score_ok = current_score >= best_score + min_improvement
over_ok = current_over <= best_over
coverage_ok = (current_groups >= min_groups and current_recall >= min_recall)
print("1" if (score_ok and over_ok and coverage_ok and second_ok == 1) else "0")
EOF
)

  if [ "${improved}" = "1" ]; then
    best_score=${current_score}
    best_over_merge=${current_over_merge}
    if [ -n "${SECOND_MANIFEST}" ]; then
      best_second_score=${second_score}
      cp "${SECOND_OUTPUT_DIR}/metrics.json" "${SECOND_OUTPUT_DIR}/best.json"
    fi
    cp "${OUTPUT_DIR}/metrics.json" "${OUTPUT_DIR}/best.json"
    echo "Improved score to ${best_score} (over_merge=${best_over_merge}, groups_scored=${current_groups_scored}, pack_recall=${current_pack_recall})."
  else
    echo "No improvement (score=${current_score}, over_merge=${current_over_merge}, groups_scored=${current_groups_scored}, pack_recall=${current_pack_recall})."
    changed_files=$(git diff --name-only)
    if [ -n "${changed_files}" ]; then
      echo "Reverting tracked changes from iteration ${iteration}."
      echo "${changed_files}" | xargs git checkout -- 2>/dev/null || true
    fi
  fi

  done=$(${PYTHON_BIN} - <<EOF
score = float("${current_score}")
over = int("${current_over_merge}")
target = float("${TARGET_SCORE}")
max_over = int("${MAX_OVER_MERGE}")
min_groups = int("${MIN_GROUPS_SCORED}")
min_recall = float("${MIN_PACK_RECALL}")
groups_scored = int("${current_groups_scored}")
pack_recall = float("${current_pack_recall}")
second_ok = int("${second_score_delta_ok}")
coverage_ok = (groups_scored >= min_groups and pack_recall >= min_recall)
print("1" if (score >= target and over <= max_over and coverage_ok and second_ok == 1) else "0")
EOF
)
  if [ "${done}" = "1" ]; then
    echo "Target reached. Stopping loop."
    exit 0
  fi
done

echo "Max iterations reached. See ${OUTPUT_DIR} for logs and metrics."
exit 1
