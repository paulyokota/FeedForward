# Issue #152: Signature Canonicalization - Session Handoff

**Date**: 2026-01-29
**Branch**: main
**Resume from**: Step 3 (Build embedding clustering prototype)

---

## Context

Issue #152 proposes replacing LLM-based signature canonicalization with embedding+clustering. The hypothesis: embeddings capture semantic meaning better than string matching, and clustering avoids the race condition in parallel extraction.

**Read Issue #152 for full rationale.** This doc covers what we learned empirically.

---

## Completed: Ground Truth + Baselines

### Ground Truth Dataset (30 pairs)

Human-labeled pairs from Run 95 signatures. File: `data/signature_ground_truth.json`

Distribution: 11 same, 8 different, 11 ambiguous

**Key labeling insight**: String similarity is misleading. `pinterest_connection_failure` vs `pinterest_connection_issue` has 89% string similarity but is labeled DIFFERENT because:

- One: boards not showing up AFTER reconnecting
- Other: error DURING reconnection that blocks it

The diagnostic context (not the signature string) reveals they're different issues. This suggests **embedding the diagnostic_summary** may help.

### Baseline Results

| Metric    | Embedding (0.85) | LLM |
| --------- | ---------------- | --- |
| Precision | 100%             | 45% |
| Recall    | 27%              | 45% |
| F1        | 43%              | 45% |
| Accuracy  | 58%              | 37% |

**Interpretation**:

- **Embedding**: Never wrong when it merges (0 false positives), but misses 8 of 11 true duplicates. Too conservative.
- **LLM**: Catches more duplicates but also merges 6 pairs that should be different. Too aggressive.

Both approaches fail below 50% accuracy. This validates the need for something better.

### Critical Failure Cases

These pairs reveal where current approaches break:

**False negatives (Embedding missed, should merge):**

- `scheduling_bulk_delete_pins` ↔ `scheduling_bulk_delete_request` — same intent, different wording
- `scheduling_turbo_autofill_failure` ↔ `scheduling_turbo_queue_automatic_failure` — same feature, naming variance
- `pins_not_supporting_carousel_pins` ↔ `pins_not_supporting_multiple_images` — identical issue

**False positives (LLM merged, should NOT merge):**

- `pinterest_connection_failure` ↔ `pinterest_connection_issue` — different failure points
- `smartpin_image_fetch_failure` ↔ `smartpin_image_import_failure` — different pipeline stages
- `scheduling_bulk_delete_drafts` ↔ `scheduling_bulk_delete_pins` — drafts vs scheduled pins

**Pattern**: LLM over-indexes on surface similarity. Embedding under-indexes on semantic equivalence.

---

## Next: Build Prototype (Step 3)

### Recommended Approach

Based on failure analysis, try embedding **richer context**, not just signatures:

```
Option A (signature only): "scheduling_bulk_delete_pins"
Option B (+ symptoms): "scheduling_bulk_delete_pins | bulk actions, delete, scheduled"
Option C (+ diagnostic): "scheduling_bulk_delete_pins | User wants to delete multiple scheduled pins at once"
```

Option C should help distinguish pinterest_connection cases (different diagnostic summaries despite similar signatures).

### What to Build

Standalone script: `scripts/signature_embedding_prototype.py`

1. Load Run 95 themes with their diagnostic_summary and symptoms
2. Embed using different text combinations (A, B, C above)
3. Cluster embeddings (try DBSCAN or agglomerative with cosine distance)
4. For each ground truth pair, check if they land in same cluster
5. Compute precision/recall/F1 against ground truth
6. Compare to baselines

### Existing Infrastructure

- `src/services/embedding_service.py` — Production embedding with batching
- `src/theme_extractor.py:canonicalize_via_embedding()` — Existing approach (uses 0.85 threshold)
- `scripts/embedding_cluster_prototype.py` — Prior clustering experiment (can reference)

### Parameters to Tune

- **Embedding input**: signature only vs +symptoms vs +diagnostic_summary
- **Similarity threshold**: 0.80, 0.85, 0.90
- **Clustering algorithm**: DBSCAN (density-based) vs agglomerative (hierarchical)

---

## Files

**Scripts (untracked, need commit):**

- `scripts/signature_ground_truth.py` — Interactive labeling tool
- `scripts/signature_baseline.py` — Baseline measurement

**Data (gitignored, on disk):**

- `data/signature_ground_truth.json` — 30 labeled pairs
- `data/signature_candidates.json` — 1404 candidate pairs with similarity scores
- `data/signature_baseline_results.json` — Full baseline results with per-pair details

---

## Success Criteria

From Issue #152:

- F1 > 58% (beat both baselines)
- No false positives on the 6 LLM failure cases
- Higher recall than embedding baseline (>27%)

Only integrate into pipeline if prototype demonstrates clear improvement.

---

## Do NOT

- Don't integrate into pipeline before validating on ground truth
- Don't run full pipeline to test — use existing Run 95 data
- Don't assume signature string similarity predicts semantic similarity (pinterest case proves otherwise)
