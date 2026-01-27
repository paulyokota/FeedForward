# Coherence Eval (Ralph Loop)

This folder provides a coherence-focused evaluation loop for clustering and
PM review. It uses **frozen artifacts** (conversations, themes, embeddings,
facets) and computes coherence metrics against curated "issue packs".

## Overview
- Build a fixed evaluation dataset from the DB (no full pipeline runs).
- Run hybrid clustering + optional PM review on frozen artifacts.
- Compute coherence metrics and compare to a baseline score.

## Files
- `manifest.example.json` - template for curated issue packs
- `build_dataset.py` - export frozen artifacts from DB for the manifest
- `run_eval.py` - run clustering + scoring against frozen artifacts
- `ralph_loop.sh` - autonomous loop (eval -> Claude changes -> eval)

## 1) Create a manifest
Copy the example and fill in conversation IDs:
```
cp scripts/ralph/coherence_eval/manifest.example.json \
   scripts/ralph/coherence_eval/manifest.json
```

Each pack should include:
- `pack_id`
- `description`
- `conversation_ids` (6-15 per pack)
- `shared_error` (optional string to check for error consistency)

## 2) Build the dataset (frozen artifacts)
```
python3 scripts/ralph/coherence_eval/build_dataset.py \
  --run-id 91 \
  --manifest scripts/ralph/coherence_eval/manifest.json \
  --output-dir data/coherence_eval
```

This writes:
- `data/coherence_eval/conversations.jsonl`
- `data/coherence_eval/themes.jsonl`
- `data/coherence_eval/embeddings.jsonl`
- `data/coherence_eval/facets.jsonl`

## 3) Run the coherence evaluation
```
python3 scripts/ralph/coherence_eval/run_eval.py \
  --manifest scripts/ralph/coherence_eval/manifest.json \
  --data-dir data/coherence_eval \
  --output-dir data/coherence_eval/outputs
```

## 4) Run the Ralph loop
```
scripts/ralph/coherence_eval/ralph_loop.sh 8
```

Optional overrides:
```
TARGET_SCORE=0.6 MAX_OVER_MERGE=0 MIN_IMPROVEMENT=0.05 \
  scripts/ralph/coherence_eval/ralph_loop.sh 8
```

Optional: enable PM review (costly, uses OpenAI):
```
python3 scripts/ralph/coherence_eval/run_eval.py \
  --manifest scripts/ralph/coherence_eval/manifest.json \
  --data-dir data/coherence_eval \
  --output-dir data/coherence_eval/outputs \
  --pm-review
```

Compare against a baseline:
```
python3 scripts/ralph/coherence_eval/run_eval.py \
  --manifest scripts/ralph/coherence_eval/manifest.json \
  --data-dir data/coherence_eval \
  --output-dir data/coherence_eval/outputs \
  --baseline data/coherence_eval/outputs/baseline.json
```

## Metrics (summary)
- `over_merge_count`: groups containing >1 pack
- `pack_purity_avg`: dominant pack share per group
- `pack_recall_avg`: max share of each pack captured by a single group
- `error_match_rate`: for packs with `shared_error`
- `score`: weighted sum with over-merge penalty

The evaluation produces:
- `groups.json` (group assignments)
- `stories.json` (story-eligible groups, size >= 3)
- `metrics.json` (summary + per-pack metrics)
