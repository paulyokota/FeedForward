# Issue #153: Vocabulary Enhancement Architecture

**Date**: 2026-01-29
**Status**: Architecture Review Complete - Revised

---

## Summary

Three-phase pipeline to systematically identify domain-specific distinctions from conversation data, validate them against the Tailwind codebase, and codify as vocabulary entries. This is a repeatable process for ongoing vocabulary maintenance.

---

## Architecture Review Revisions

**From Quinn (Quality Champion)**:

- Added confidence scoring with explicit thresholds
- Added facet extraction validation checkpoint
- Clarified state machine for validation to patch

**From Dmitri (Pragmatist)**:

- Merged Phases 1 & 2 into single "Extract & Cluster" script
- Phase 3 starts with existing codebase map (defer full search to v2)
- Folded Phase 4 into orchestrator (it's glue, not a phase)
- Defined explicit human review triggers

---

## Key Design Decision: Automated Codebase Validation

Phase 2 uses **codebase map lookup** plus **targeted searches** when needed.

**Rationale**: Start simple with `docs/tailwind-codebase-map.md` (existing mappings). Only search repos when map lookup fails.

**Byproduct**: `codebase_map_recommendations.json` suggests new mappings (human approves separately).

---

## Simplified Architecture (3 Phases)

```
PostgreSQL (themes from Run 95)
         |
         v
Phase 1: Extract & Cluster
    - Query 323 unique signatures
    - LLM extracts: object_type, action, stage, timing
    - Validate facet quality on 20-sample checkpoint
    - Compute embeddings + cluster (Strategy B, t=0.25)
    - Identify distinction candidates
    - Output: phase1_results.json
         |
         v
[Facet Quality Checkpoint - 20 samples]
         |
         v
Phase 2: Validate Against Codebase
    - For each distinction: lookup in tailwind-codebase-map.md
    - If not in map: targeted Grep search in relevant repo
    - Score confidence (0-1)
    - Apply SAME_FIX test
    - Auto-approve if confidence >= 0.85
    - Flag for human if confidence < 0.85
    - Output: phase2_validations.json, needs_review.json
         |
         v
[Human Review - only for low-confidence items]
         |
         v
Phase 3 (Orchestrator): Apply Vocabulary Patch
    - Merge validated items into vocabulary
    - Create merge directives for same_fix verdicts
    - Add signature_quality_guidelines examples
    - Output: git diff of theme_vocabulary.json
```

---

## File Structure

### New Files

| File                                        | Purpose                                  |
| ------------------------------------------- | ---------------------------------------- |
| `scripts/vocabulary_extract_and_cluster.py` | Phase 1: Facets + clustering in one pass |
| `scripts/vocabulary_validate.py`            | Phase 2: Codebase validation             |
| `scripts/vocabulary_enhance.py`             | Orchestrator + patch application         |
| `tests/test_vocabulary_enhancement.py`      | Integration tests                        |
| `docs/vocabulary-maintenance.md`            | Runbook                                  |
| `data/vocabulary_enhancement/`              | JSON artifacts                           |

### Modified Files

| File                           | Change                        |
| ------------------------------ | ----------------------------- |
| `config/theme_vocabulary.json` | New entries, merge directives |

### Codebase Map Updates (Separate Workflow)

`codebase_map_recommendations.json` outputs suggestions. Human reviews and applies separately to `docs/tailwind-codebase-map.md` to avoid coupling pipelines.

---

## Data Structures

### Phase 1 Output: ExtractedSignature

```python
@dataclass
class ExtractedSignature:
    signature: str
    product_area: str
    component: str
    count: int

    # LLM-extracted facets
    object_type: str    # drafts, pins, boards, accounts
    action: str         # create, delete, schedule, unschedule
    stage: str          # selection, generation, publishing
    timing: str         # during, after, before

    # Context
    sample_diagnostic_summary: str
    sample_symptoms: List[str]

    # Embedding for clustering
    embedding: List[float]
```

### Phase 1 Output: DistinctionCandidate

```python
@dataclass
class DistinctionCandidate:
    sig_a: str
    sig_b: str
    similarity: float

    distinguishing_facet: str
    facet_a_value: str
    facet_b_value: str
```

### Phase 2 Output: Validation

```python
@dataclass
class Validation:
    sig_a: str
    sig_b: str

    # Codebase lookup results
    map_entry_a: Optional[str]  # Entry from tailwind-codebase-map.md
    map_entry_b: Optional[str]
    grep_results_a: List[str]   # Files found if not in map
    grep_results_b: List[str]

    # Confidence scoring (0-1)
    confidence: float
    # Based on:
    #   1.0: Both found in codebase map, different entries
    #   0.9: Both found in codebase map, same entry
    #   0.7: One in map, one found via grep
    #   0.5: Both found via grep only
    #   0.3: One found, one not found
    #   0.0: Neither found

    # SAME_FIX test
    same_storage_backend: bool
    same_api_endpoint: bool
    verdict: str  # same_fix, different_fix

    # Decision
    auto_approved: bool  # True if confidence >= 0.85
    reasoning: str

    # Side output
    codebase_map_recommendation: Optional[Dict]
```

### State Machine: Validation to Vocabulary

```
confidence >= 0.85 AND verdict == "different_fix"
    => Auto-create two separate vocabulary entries

confidence >= 0.85 AND verdict == "same_fix"
    => Auto-create merge directive (sig_a canonical, sig_b alias)

confidence < 0.85
    => Write to needs_review.json
    => Human decides, updates validation, re-run Phase 3
```

---

## Phase 2 Codebase Lookup Strategy

1. **Lookup in existing map** (`tailwind-codebase-map.md`)
   - Parse map into dict: user_term -> {repo, path, description}
   - Direct lookup for both signatures

2. **If not in map**: targeted Grep
   - Extract key nouns from signature (e.g., "scheduling_bulk_delete_drafts" -> ["drafts", "bulk", "delete"])
   - Search only relevant repo based on product_area:
     - scheduling -> tack, aero
     - pinterest -> aero, tack
     - instagram -> aero
   - Limit to 3 grep calls per signature

3. **Confidence scoring**
   - Both in map, different locations: 1.0
   - Both in map, same location: 0.9 (likely same_fix)
   - One in map: 0.7
   - Both via grep only: 0.5
   - Partial/ambiguous: 0.3
   - Not found: 0.0

4. **Human review triggers** (explicit rules)
   - confidence < 0.85
   - Both found in same file but different functions
   - Grep found 5+ matches (too ambiguous)
   - Product_area unknown

---

## Facet Quality Checkpoint (After Phase 1)

Before proceeding to Phase 2:

1. Sample 20 random signatures from `phase1_results.json`
2. Display extracted facets
3. Check for consistency issues:
   - All `action` fields use consistent tense (present: "delete" not "deleting")
   - All `object_type` fields use singular nouns ("pin" not "pins")
   - No empty facet values
4. If >10% inconsistency: refine prompt, re-run Phase 1
5. If consistent: proceed to Phase 2

---

## Human Review Interface

`data/vocabulary_enhancement/needs_review.json`:

```json
{
  "items": [
    {
      "sig_a": "pinterest_connection_failure",
      "sig_b": "pinterest_connection_issue",
      "confidence": 0.45,
      "reason_for_review": "Both found via grep but in 5+ different files",
      "grep_results_a": ["file1.ts:45", "file2.ts:100"],
      "grep_results_b": ["file1.ts:80", "file3.ts:20"],
      "suggested_verdict": "different_fix",
      "human_verdict": null,
      "human_notes": null
    }
  ],
  "priority_sort": "confidence_asc"
}
```

Human fills in `human_verdict` and `human_notes`, then re-runs Phase 3.

---

## Estimated Costs

| Phase                         | API Calls  | Estimated Cost |
| ----------------------------- | ---------- | -------------- |
| Phase 1 (facets + embeddings) | ~323 + 323 | ~$0.70         |
| Phase 2 (no LLM)              | 0          | $0             |
| Phase 3 (no LLM)              | 0          | $0             |
| **Total**                     |            | **~$0.70**     |

---

## Success Criteria

| Metric                       | Current     | Target          | How to Measure                 |
| ---------------------------- | ----------- | --------------- | ------------------------------ |
| Functional test pass rate    | 5/8 (62.5%) | 7/8 (87.5%)     | Re-run #152 test cases         |
| Ground truth false positives | 7 at t=0.25 | <4              | Evaluate on 30 labeled pairs   |
| Process documented           | No          | Runbook exists  | docs/vocabulary-maintenance.md |
| Facet extraction quality     | Unknown     | >90% consistent | 20-sample checkpoint           |

---

## Process Gates

| Gate                 | When                     | What                           |
| -------------------- | ------------------------ | ------------------------------ |
| Architecture Review  | Before Phase 1           | Quality + Pragmatist (DONE)    |
| Facet Checkpoint     | After Phase 1 extraction | 20-sample quality check        |
| Functional Testing   | After Phase 1 complete   | Verify facet + cluster quality |
| Integration Testing  | After Phase 2            | Verify full pipeline path      |
| Test Gate            | Before review            | Unit tests exist and pass      |
| 5-Personality Review | Before merge             | 2+ rounds until convergence    |

---

## Not In Scope (Deferred)

- Full automated codebase search across all repos (Phase 2 v2)
- Shortcut integration for PR-to-card mapping
- Automatic codebase map enrichment (recommendations only)
- Real-time vocabulary updates during pipeline runs

---

## Next Steps

1. ~~Architecture Review Gate~~ DONE
2. Implement Phase 1: Extract & Cluster (Kai)
3. Facet quality checkpoint (20 samples)
4. Functional testing
5. Implement Phase 2: Validate
6. Integration testing
7. Implement Phase 3: Apply patch
8. Unit tests + 5-personality review
9. Create runbook
