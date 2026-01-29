# Issue #152: Signature Canonicalization - Session Handoff

**Date**: 2026-01-29
**Branch**: main
**Resume from**: Decide on approach (domain knowledge injection vs other options)

---

## Context

Issue #152 proposes replacing LLM-based signature canonicalization with embedding+clustering. This session built and evaluated the prototype.

**Read Issue #152 for full rationale.** This doc covers what we learned empirically.

---

## Completed This Session

### 1. Built Prototype (`scripts/signature_embedding_prototype.py`)

Tests three embedding strategies:

- **A**: Signature only
- **B**: Signature + product_area + symptoms
- **C**: Signature + product_area + symptoms + diagnostic_summary

Clusters embeddings using agglomerative clustering with cosine distance, then evaluates against ground truth pairs.

### 2. Ran Full Evaluation

Best result: **Strategy B, threshold 0.35**

- F1: 75.86% (vs 45% LLM baseline, 43% embedding baseline)
- Precision: 61.11%
- Recall: 100%
- Accuracy: 63.16%

### 3. Analyzed False Positives

7 "different" pairs incorrectly merged. Patterns:

| Pair                                                                                        | Why Different (per labeling)                 |
| ------------------------------------------------------------------------------------------- | -------------------------------------------- |
| pinterest_connection_failure / pinterest_connection_issue                                   | AFTER vs DURING reconnection                 |
| scheduling_bulk_delete_drafts / scheduling_bulk_delete_pins                                 | Drafts vs scheduled pins (different storage) |
| scheduling_bulk_editing / scheduling_bulk_editing_unavailable                               | DRAFTS info vs SCHEDULED PINS deletion       |
| smartpin_image_fetch_failure / smartpin_image_import_failure                                | Selection stage vs generation stage          |
| scheduling_smart_schedule_generation_failure / scheduling_smart_schedule_time_slot_conflict | Bug report vs feature request                |
| instagram_repost_feature_missing / instagram_repost_feature_question                        | OTHER accounts vs own posts                  |
| scheduling_bulk_schedule_stuck / scheduling_bulk_unscheduling                               | Scheduling vs unscheduling                   |

### 4. Validated Against Codebase

Explored Tailwind codebase (`/Users/paulyokota/Documents/GitHub/aero/`) to check if distinctions matter:

- **Scheduled pins**: Deleted via `tackClient.deletePosts()` in `packages/core/src/scheduler/repositories/pin.ts`
- **Drafts**: Stored in DynamoDB via `destinationless-drafts-repository.ts` (no delete method exposed)
- **Conclusion**: "Bulk delete drafts" and "bulk delete scheduled pins" ARE genuinely different implementations

This confirms the ground truth labeling was correct - the false positives represent genuinely different feature requests that would need different code paths.

---

## Key Insight

**The embedding approach captures topic relatedness but not domain-specific distinctions.**

"Scheduling bulk delete drafts" and "scheduling bulk delete pins" are semantically similar (both about bulk deleting in scheduling) but require different implementations because drafts and scheduled pins are different object types with different storage backends.

The 76% F1 is misleading - the errors conflate genuinely different feature requests, which would hurt story quality.

---

## Existing Domain Knowledge System

Found `ThemeVocabulary` in `src/vocabulary.py` that provides domain knowledge injection:

- Curated themes with product_area, component, description, keywords
- URL context mapping (page URLs → product areas)
- **Signature quality guidelines** including "SAME_FIX test":
  - "One code change would fix ALL conversations with this signature"
  - Examples of good vs bad signatures

Config file: `config/theme_vocabulary.json`

This vocabulary system already encodes domain knowledge about what constitutes "the same issue." The question is whether it can be leveraged for canonicalization.

---

## Options for Next Steps

### Option 1: Enhance Vocabulary for Canonicalization

Use the existing `ThemeVocabulary` to inject domain knowledge into the canonicalization step. The vocabulary already has:

- Known themes with explicit boundaries
- SAME_FIX test criteria
- Product area distinctions

Could we use vocabulary matching BEFORE embedding to handle known distinctions (drafts vs scheduled pins)?

### Option 2: Two-Stage Approach

1. Use embedding clustering for high-recall candidate identification
2. Add LLM verification step that applies SAME_FIX test to each cluster
3. Only merge if LLM confirms "one fix would address both"

### Option 3: Accept Current Baseline

The existing LLM canonicalization (45% F1) or embedding (43% F1) might be "good enough" given the complexity of fixing this. Focus effort elsewhere.

### Option 4: Tighten Thresholds + Accept Lower Recall

At threshold 0.20, we avoid the false positives but recall drops to 27%. Might be acceptable if precision matters more than recall for story quality.

---

## Files Created/Modified

**New this session:**

- `scripts/signature_embedding_prototype.py` - Prototype implementation

**Data (gitignored, on disk):**

- `data/signature_prototype_results.json` - Full results from all strategy/threshold combos

**From previous session:**

- `scripts/signature_ground_truth.py` - Labeling tool
- `scripts/signature_baseline.py` - Baseline measurement
- `data/signature_ground_truth.json` - 30 labeled pairs
- `data/signature_baseline_results.json` - Baseline results

---

## Ground Truth Summary

30 pairs total:

- 11 "same" (should merge)
- 8 "different" (should NOT merge)
- 11 "ambiguous"

Key labeling insight from user: Distinctions are based on whether the same code fix would address both issues. Drafts vs scheduled pins = different storage = different fix = different signatures.

---

## Do NOT

- Don't integrate into pipeline before deciding on approach
- Don't optimize for F1 metric - optimize for story quality (gold standard philosophy)
- Don't assume embedding can capture domain-specific distinctions like "drafts vs scheduled pins"

---

## Questions for Next Session

1. Should we try enhancing vocabulary with explicit object-type tagging?
2. Is two-stage (embedding + LLM verification) worth the added complexity?
3. What's the actual impact on story quality of the current approach?
