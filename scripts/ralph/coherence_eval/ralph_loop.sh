#!/bin/bash

# Ralph loop for coherence improvements.
# Iterates: eval -> Claude changes -> eval, until score target or max iterations.

set -euo pipefail

MAX_ITERATIONS=${1:-8}
PYTHON_BIN=${PYTHON_BIN:-}
TARGET_SCORE=${TARGET_SCORE:-0.6}
MAX_OVER_MERGE=${MAX_OVER_MERGE:-1}
MIN_IMPROVEMENT=${MIN_IMPROVEMENT:-0.02}
MIN_GROUPS_SCORED=${MIN_GROUPS_SCORED:-6}
MIN_PACK_RECALL=${MIN_PACK_RECALL:-0.20}
MIN_PACK_RECALL_COVERAGE=${MIN_PACK_RECALL_COVERAGE:-0.50}
MIN_PACK_RECALL_PER_PACK=${MIN_PACK_RECALL_PER_PACK:-0.15}
EVIDENCE_WEIGHT=${EVIDENCE_WEIGHT:-0.10}
SECOND_MANIFEST=${SECOND_MANIFEST:-}
SECOND_MIN_SCORE_DELTA=${SECOND_MIN_SCORE_DELTA:--0.05}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DATA_DIR="${ROOT_DIR}/data/coherence_eval"
OUTPUT_DIR="${DATA_DIR}/outputs"
SECOND_OUTPUT_DIR="${OUTPUT_DIR}/secondary"
MANIFEST="${SCRIPT_DIR}/manifest.json"
SECOND_BASELINE="${SECOND_OUTPUT_DIR}/baseline.json"
BEST_PATCH_FILE="${OUTPUT_DIR}/best.patch"

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
if ! command -v rg >/dev/null 2>&1; then
  echo "Missing required tool: rg (ripgrep)" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
if [ -n "${SECOND_MANIFEST}" ]; then
  mkdir -p "${SECOND_OUTPUT_DIR}"
fi

if [ ! -f "${MANIFEST}" ]; then
  echo "Missing manifest: ${MANIFEST}" >&2
  exit 1
fi
if [ ! -s "${MANIFEST}" ]; then
  echo "Manifest is empty: ${MANIFEST}" >&2
  exit 1
fi
if [ ! -f "${DATA_DIR}/conversations.jsonl" ] || [ ! -s "${DATA_DIR}/conversations.jsonl" ]; then
  echo "Missing or empty conversations.jsonl in ${DATA_DIR}" >&2
  exit 1
fi
if [ ! -f "${DATA_DIR}/themes.jsonl" ] || [ ! -s "${DATA_DIR}/themes.jsonl" ]; then
  echo "Missing or empty themes.jsonl in ${DATA_DIR}" >&2
  exit 1
fi
if [ ! -f "${DATA_DIR}/embeddings.jsonl" ] || [ ! -s "${DATA_DIR}/embeddings.jsonl" ]; then
  echo "Missing or empty embeddings.jsonl in ${DATA_DIR}" >&2
  exit 1
fi
if [ ! -f "${DATA_DIR}/facets.jsonl" ] || [ ! -s "${DATA_DIR}/facets.jsonl" ]; then
  echo "Missing or empty facets.jsonl in ${DATA_DIR}" >&2
  exit 1
fi
if [ -n "${SECOND_MANIFEST}" ] && [ ! -s "${SECOND_MANIFEST}" ]; then
  echo "Second manifest is missing or empty: ${SECOND_MANIFEST}" >&2
  exit 1
fi
${PYTHON_BIN} - <<'EOF'
import importlib.util
spec = importlib.util.find_spec("sklearn")
if spec is None:
    raise SystemExit("sklearn is required for this loop; aborting.")
EOF

echo "Ralph coherence loop"
echo "  iterations: ${MAX_ITERATIONS}"
echo "  target_score: ${TARGET_SCORE}"
echo "  max_over_merge: ${MAX_OVER_MERGE}"
echo "  min_improvement: ${MIN_IMPROVEMENT}"
echo "  min_groups_scored: ${MIN_GROUPS_SCORED}"
echo "  min_pack_recall: ${MIN_PACK_RECALL}"
echo "  min_pack_recall_coverage: ${MIN_PACK_RECALL_COVERAGE}"
echo "  min_pack_recall_per_pack: ${MIN_PACK_RECALL_PER_PACK}"
echo "  evidence_weight: ${EVIDENCE_WEIGHT}"
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
if [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "Working tree has untracked files. Commit/stash/clean before running the loop." >&2
  exit 1
fi

# Avoid carrying over patches from prior runs.
rm -f "${BEST_PATCH_FILE}"

DATA_DIR="${DATA_DIR}" MANIFEST="${MANIFEST}" SECOND_MANIFEST="${SECOND_MANIFEST}" \
  ${PYTHON_BIN} - <<'EOF'
import json
import os
from pathlib import Path

def load_jsonl_ids(path):
    ids = set()
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = json.loads(line.replace('\\\\\"', '\\\"'))
        ids.add(str(row.get("conversation_id")))
    return ids

def load_manifest_ids(path):
    data = json.loads(Path(path).read_text())
    ids = set()
    for pack in data.get("packs", []):
        for cid in pack.get("conversation_ids", []):
            ids.add(str(cid))
    return ids

data_dir = Path(os.environ["DATA_DIR"])
manifest = Path(os.environ["MANIFEST"])
conv_ids = load_jsonl_ids(data_dir / "conversations.jsonl")
theme_ids = load_jsonl_ids(data_dir / "themes.jsonl")
embed_ids = load_jsonl_ids(data_dir / "embeddings.jsonl")
facet_ids = load_jsonl_ids(data_dir / "facets.jsonl")
manifest_ids = load_manifest_ids(manifest)
for name, ids in [
    ("conversations.jsonl", conv_ids),
    ("themes.jsonl", theme_ids),
    ("embeddings.jsonl", embed_ids),
    ("facets.jsonl", facet_ids),
]:
    missing = sorted(manifest_ids - ids)
    if missing:
        raise SystemExit(f"Manifest contains {len(missing)} conversation_ids not in {name}")

second_manifest = os.environ.get("SECOND_MANIFEST")
if second_manifest:
    second_path = Path(second_manifest)
    if second_path.exists():
        second_ids = load_manifest_ids(second_path)
        for name, ids in [
            ("conversations.jsonl", conv_ids),
            ("themes.jsonl", theme_ids),
            ("embeddings.jsonl", embed_ids),
            ("facets.jsonl", facet_ids),
        ]:
            missing_second = sorted(second_ids - ids)
            if missing_second:
                raise SystemExit(f"Second manifest contains {len(missing_second)} conversation_ids not in {name}")
EOF

for iteration in $(seq 1 "${MAX_ITERATIONS}"); do
  echo ""
  echo "=== Iteration ${iteration} ==="

  CHECKPOINT_FILE="${OUTPUT_DIR}/iteration_${iteration}_checkpoint.patch"
  git diff > "${CHECKPOINT_FILE}"

  COHERENCE_EVAL_STRICT=1 EVIDENCE_WEIGHT="${EVIDENCE_WEIGHT}" ${PYTHON_BIN} "${SCRIPT_DIR}/run_eval.py" \
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
    COHERENCE_EVAL_STRICT=1 EVIDENCE_WEIGHT="${EVIDENCE_WEIGHT}" ${PYTHON_BIN} "${SCRIPT_DIR}/run_eval.py" \
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
- Avoid modifying tests/docs unless strictly necessary. Do not touch docs/session/last-session.md.
- If over_merge_count is already 0, prioritize improving groups_scored and pack_recall without increasing over_merge.
- Consider evidence_overlap_avg (intent/flow/symptom overlap) across bugs, info queries, and feature requests.
- Do not skip proposing a change. If you believe no improvement is possible, still propose the smallest safe adjustment and explain the tradeoff.
- Exploration mode: take a bigger swing than last iteration and avoid repeating the same lever category.
- Rotate across levers: (1) threshold/linkage, (2) facet grouping keys, (3) product_area/component heuristics, (4) evidence overlap use.
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

  allowed_diff_files=$(git diff --name-only --diff-filter=AMR -- src/services src/story_tracking tests docs || true)
  disallowed_files=$(git diff --name-only --diff-filter=AMR -- . | rg -v "^(src/(services|story_tracking)/|tests/|docs/)" || true)
  if [ -n "${disallowed_files}" ]; then
    echo "❌ Disallowed changes detected:" >&2
    echo "${disallowed_files}" >&2
    git checkout -- .
    git clean -fd -- src/services src/story_tracking tests docs
    exit 1
  fi
  if [ -z "${allowed_diff_files}" ]; then
    echo "No allowed changes detected; continuing without improvement."
  fi

  if git diff --unified=0 -- src/services src/story_tracking | rg -n "^[+-].*issue_signature" >/dev/null 2>&1; then
    echo "❌ Detected issue_signature added as merge logic. Rejecting iteration." >&2
    git checkout -- .
    git clean -fd -- src/services src/story_tracking tests docs
    exit 1
  fi

  COHERENCE_EVAL_STRICT=1 EVIDENCE_WEIGHT="${EVIDENCE_WEIGHT}" ${PYTHON_BIN} "${SCRIPT_DIR}/run_eval.py" \
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
pack_coverage_ok=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path
data = json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text())
pack_recall = data.get("pack_recall", {})
threshold = float("${MIN_PACK_RECALL_PER_PACK}")
coverage = float("${MIN_PACK_RECALL_COVERAGE}")
if not pack_recall:
    print("0")
else:
    good = sum(1 for v in pack_recall.values() if v >= threshold)
    total = len(pack_recall)
    print("1" if (good / max(1, total)) >= coverage else "0")
EOF
)
  max_over_ok=$(${PYTHON_BIN} - <<EOF
current_over = int("${current_over_merge}")
max_over = int("${MAX_OVER_MERGE}")
print("1" if current_over <= max_over else "0")
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
max_over_ok = int("${max_over_ok}")
best_second = float("${best_second_score}")
current_second = float("${second_score:- -999}")
pack_coverage_ok = int("${pack_coverage_ok}")

score_ok = current_score >= best_score + min_improvement
over_ok = current_over <= best_over
coverage_ok = (current_groups >= min_groups and current_recall >= min_recall)
second_best_ok = 1 if current_second >= best_second else 0
print("1" if (score_ok and over_ok and coverage_ok and second_ok == 1 and max_over_ok == 1 and second_best_ok == 1 and pack_coverage_ok == 1) else "0")
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
    git diff > "${BEST_PATCH_FILE}"
    echo "Improved score to ${best_score} (over_merge=${best_over_merge}, groups_scored=${current_groups_scored}, pack_recall=${current_pack_recall})."
  else
    echo "No improvement (score=${current_score}, over_merge=${current_over_merge}, groups_scored=${current_groups_scored}, pack_recall=${current_pack_recall})."
    echo "Reverting changes from iteration ${iteration}."
    git checkout -- .
    git clean -fd -- src/services src/story_tracking tests docs
    if [ -s "${BEST_PATCH_FILE}" ]; then
      git apply "${BEST_PATCH_FILE}" || {
        echo "❌ Failed to re-apply best patch; stopping loop." >&2
        exit 1
      }
    fi
  fi

  done=$(${PYTHON_BIN} - <<EOF
import json
from pathlib import Path

best_path = Path("${OUTPUT_DIR}/best.json")
best = json.loads(best_path.read_text()) if best_path.exists() else json.loads(Path("${OUTPUT_DIR}/metrics.json").read_text())
best_summary = best.get("summary", {})

score = float(best_summary.get("score", -999))
over = int(best_summary.get("over_merge_count", 999))
groups_scored = int(best_summary.get("groups_scored", 0))
pack_recall = float(best_summary.get("pack_recall_avg", 0.0))

target = float("${TARGET_SCORE}")
max_over = int("${MAX_OVER_MERGE}")
min_groups = int("${MIN_GROUPS_SCORED}")
min_recall = float("${MIN_PACK_RECALL}")
min_cov = float("${MIN_PACK_RECALL_COVERAGE}")
min_pack = float("${MIN_PACK_RECALL_PER_PACK}")

coverage_ok = (groups_scored >= min_groups and pack_recall >= min_recall)

def pack_coverage_ok(metrics):
    pack_recall = metrics.get("pack_recall", {})
    if not pack_recall:
        return False
    good = sum(1 for v in pack_recall.values() if v >= min_pack)
    return (good / max(1, len(pack_recall))) >= min_cov

primary_cov_ok = pack_coverage_ok(best)

sec_ok = True
if "${SECOND_MANIFEST}":
    sec_best_path = Path("${SECOND_OUTPUT_DIR}/best.json")
    if not sec_best_path.exists():
        sec_ok = False
    else:
        sec = json.loads(sec_best_path.read_text())
        sec_summary = sec.get("summary", {})
        sec_score = float(sec_summary.get("score", -999))
        sec_over = int(sec_summary.get("over_merge_count", 999))
        sec_groups = int(sec_summary.get("groups_scored", 0))
        sec_recall = float(sec_summary.get("pack_recall_avg", 0.0))
        sec_cov = pack_coverage_ok(sec)
        baseline = json.loads(Path("${SECOND_BASELINE}").read_text()).get("summary", {})
        baseline_score = float(baseline.get("score", -999))
        min_delta = float("${SECOND_MIN_SCORE_DELTA}")
        sec_ok = (
            sec_score >= baseline_score + min_delta
            and sec_over <= max_over
            and sec_groups >= min_groups
            and sec_recall >= min_recall
            and sec_cov
        )

print("1" if (score >= target and over <= max_over and coverage_ok and primary_cov_ok and sec_ok) else "0")
EOF
)
  if [ "${done}" = "1" ]; then
    echo "Target reached. Stopping loop."
    exit 0
  fi
done

echo "Max iterations reached. See ${OUTPUT_DIR} for logs and metrics."
exit 1
