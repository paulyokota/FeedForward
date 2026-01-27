#!/bin/bash

# Build expanded manifest + export eval dataset + run eval.
set -euo pipefail

RUN_ID=${RUN_ID:-91}
PACK_COUNT=${PACK_COUNT:-20}
PACK_SIZE=${PACK_SIZE:-8}
PYTHON_BIN=${PYTHON_BIN:-}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MANIFEST="${ROOT_DIR}/scripts/ralph/coherence_eval/manifest.json"
DATA_DIR="${ROOT_DIR}/data/coherence_eval"
OUTPUT_DIR="${DATA_DIR}/outputs"
OUTPUT_METRICS="${OUTPUT_DIR}/metrics.json"

for tool in psql jq python3; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Missing required tool: ${tool}" >&2
    exit 1
  fi
done

if [ -z "${PYTHON_BIN}" ]; then
  if command -v python3.10 >/dev/null 2>&1; then
    PYTHON_BIN=python3.10
  else
    PYTHON_BIN=python3
  fi
fi

set -a
source "${ROOT_DIR}/.env"
set +a

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is not set. Check your .env file." >&2
  exit 1
fi

mkdir -p "${DATA_DIR}" "${OUTPUT_DIR}"

psql "$DATABASE_URL" -At -F $'\t' -c "
WITH ranked AS (
  SELECT
    issue_signature,
    conversation_id,
    row_number() OVER (PARTITION BY issue_signature ORDER BY conversation_id) AS rn
  FROM themes
  WHERE pipeline_run_id = ${RUN_ID}
),
sigs AS (
  SELECT issue_signature, COUNT(*) AS cnt
  FROM ranked
  GROUP BY issue_signature
  HAVING COUNT(*) >= ${PACK_SIZE}
  ORDER BY cnt DESC
  LIMIT ${PACK_COUNT}
)
SELECT issue_signature,
       json_agg(conversation_id ORDER BY conversation_id) FILTER (WHERE rn <= ${PACK_SIZE})
FROM ranked r
JOIN sigs s USING (issue_signature)
WHERE rn <= ${PACK_SIZE}
GROUP BY issue_signature;
" | python3 - > "${MANIFEST}" <<'PY'
import sys, json
packs = []
for line in sys.stdin:
    if not line.strip():
        continue
    sig, convs = line.strip().split("\t", 1)
    conv_ids = json.loads(convs)
    packs.append({
        "pack_id": sig,
        "description": sig.replace("_", " "),
        "shared_error": "",
        "conversation_ids": [str(c) for c in conv_ids],
    })
print(json.dumps({"packs": packs}, indent=2, ensure_ascii=True))
PY

PACKS_COUNT=$(jq '.packs | length' "${MANIFEST}")
if [ "${PACKS_COUNT}" -lt 15 ]; then
  echo "Only ${PACKS_COUNT} packs available with PACK_SIZE=${PACK_SIZE}. Increase PACK_SIZE or lower threshold." >&2
  exit 1
fi

ids=$(jq -r '.packs[].conversation_ids[]' "${MANIFEST}" | sort -u | awk '{printf "%s'\''%s'\''", (NR==1?"":","), $0}')
if [ -z "${ids}" ]; then
  echo "No conversation IDs found in manifest. Aborting." >&2
  exit 1
fi

psql "$DATABASE_URL" -c "COPY (
  SELECT row_to_json(t)
  FROM (
    SELECT
      id AS conversation_id,
      created_at,
      source_body,
      source_subject,
      support_insights->>'customer_digest' AS customer_digest
    FROM conversations
    WHERE id IN (${ids})
  ) t
) TO STDOUT" > "${DATA_DIR}/conversations.jsonl"

psql "$DATABASE_URL" -c "COPY (
  SELECT row_to_json(t)
  FROM (
    SELECT
      conversation_id,
      issue_signature,
      product_area,
      component,
      user_intent,
      symptoms,
      affected_flow
    FROM themes
    WHERE pipeline_run_id = ${RUN_ID} AND conversation_id IN (${ids})
  ) t
) TO STDOUT" > "${DATA_DIR}/themes.jsonl"

psql "$DATABASE_URL" -c "COPY (
  SELECT row_to_json(t)
  FROM (
    SELECT
      conversation_id,
      embedding::text AS embedding
    FROM conversation_embeddings
    WHERE pipeline_run_id = ${RUN_ID} AND conversation_id IN (${ids})
  ) t
) TO STDOUT" > "${DATA_DIR}/embeddings.jsonl"

psql "$DATABASE_URL" -c "COPY (
  SELECT row_to_json(t)
  FROM (
    SELECT
      conversation_id,
      action_type,
      direction,
      symptom,
      user_goal
    FROM conversation_facet
    WHERE pipeline_run_id = ${RUN_ID} AND conversation_id IN (${ids})
  ) t
) TO STDOUT" > "${DATA_DIR}/facets.jsonl"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/ralph/coherence_eval/run_eval.py" \
  --manifest "${MANIFEST}" \
  --data-dir "${DATA_DIR}" \
  --output-dir "${OUTPUT_DIR}"

python3 - <<PY
import json
m = json.load(open("${OUTPUT_METRICS}"))
print(m["summary"])
print("groups_scored>", m["summary"]["groups_scored"] > 14)
PY
