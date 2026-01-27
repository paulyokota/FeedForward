#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DATA_DIR="${ROOT_DIR}/data/coherence_eval"
MANIFEST="${SCRIPT_DIR}/manifest.json"
SECOND_MANIFEST="${SECOND_MANIFEST:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

fail() {
  echo "Preflight failed: $1" >&2
  exit 1
}

command -v "${PYTHON_BIN}" >/dev/null 2>&1 || fail "python3 not found (set PYTHON_BIN if needed)"
command -v rg >/dev/null 2>&1 || fail "rg not found"
command -v claude >/dev/null 2>&1 || fail "claude not found"
claude --version >/dev/null 2>&1 || fail "claude not functional"

if [ -n "$(git diff --name-only)" ] || [ -n "$(git diff --cached --name-only)" ]; then
  fail "working tree has tracked changes; commit/stash first"
fi
if [ -n "$(git ls-files --others --exclude-standard)" ]; then
  fail "working tree has untracked files; commit/stash/clean first"
fi

[ -f "${MANIFEST}" ] || fail "missing manifest: ${MANIFEST}"
[ -s "${MANIFEST}" ] || fail "manifest is empty: ${MANIFEST}"
if [ -n "${SECOND_MANIFEST}" ]; then
  [ -f "${SECOND_MANIFEST}" ] || fail "missing second manifest: ${SECOND_MANIFEST}"
  [ -s "${SECOND_MANIFEST}" ] || fail "second manifest is empty: ${SECOND_MANIFEST}"
fi

for f in conversations.jsonl themes.jsonl embeddings.jsonl facets.jsonl; do
  [ -f "${DATA_DIR}/${f}" ] || fail "missing ${DATA_DIR}/${f}"
  [ -s "${DATA_DIR}/${f}" ] || fail "empty ${DATA_DIR}/${f}"
done

${PYTHON_BIN} - <<'EOF'
import importlib.util
spec = importlib.util.find_spec("sklearn")
if spec is None:
    raise SystemExit("sklearn is required for this loop")
EOF

${PYTHON_BIN} - <<EOF
import json
from pathlib import Path

data_dir = Path("${DATA_DIR}")
manifest = Path("${MANIFEST}")
second_manifest = Path("${SECOND_MANIFEST}") if "${SECOND_MANIFEST}" else None

def load_jsonl_ids(path):
    ids = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = json.loads(line.replace('\\\\\"', '\\\"'))
        ids.add(str(row.get("conversation_id")))
    return ids

def load_manifest_ids(path):
    data = json.loads(path.read_text())
    ids = set()
    for pack in data.get("packs", []):
        convos = pack.get("conversation_ids", [])
        if len(convos) < 3:
            raise SystemExit(f"pack {pack.get('pack_id')} has <3 conversations")
        for cid in convos:
            ids.add(str(cid))
    return ids

conv_ids = load_jsonl_ids(data_dir / "conversations.jsonl")
theme_ids = load_jsonl_ids(data_dir / "themes.jsonl")
embed_ids = load_jsonl_ids(data_dir / "embeddings.jsonl")
facet_ids = load_jsonl_ids(data_dir / "facets.jsonl")

# Fail fast if any JSONL line is still invalid after escape fix
for fname in ["conversations.jsonl", "themes.jsonl", "embeddings.jsonl", "facets.jsonl"]:
    for i, line in enumerate((data_dir / fname).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            try:
                json.loads(line.replace('\\\\\"', '\\\"'))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{fname} has invalid JSON on line {i}: {e}")

manifest_ids = load_manifest_ids(manifest)
for name, ids in [
    ("conversations.jsonl", conv_ids),
    ("themes.jsonl", theme_ids),
    ("embeddings.jsonl", embed_ids),
    ("facets.jsonl", facet_ids),
]:
    missing = sorted(manifest_ids - ids)
    if missing:
        raise SystemExit(f"manifest has {len(missing)} ids missing from {name}")

if second_manifest and second_manifest.exists():
    second_ids = load_manifest_ids(second_manifest)
    for name, ids in [
        ("conversations.jsonl", conv_ids),
        ("themes.jsonl", theme_ids),
        ("embeddings.jsonl", embed_ids),
        ("facets.jsonl", facet_ids),
    ]:
        missing = sorted(second_ids - ids)
        if missing:
            raise SystemExit(f"second manifest has {len(missing)} ids missing from {name}")
EOF

echo "Preflight OK"
