# Issue #153: Vocabulary Enhancement - RESTART

**Date**: 2026-01-29
**Status**: Starting over - previous implementation was WRONG

---

## What Went Wrong

The first implementation operated at the **SIGNATURE level** when it should have operated at the **TERM level**.

| Phase   | Should Have Done                                      | Actually Did (WRONG)                                   |
| ------- | ----------------------------------------------------- | ------------------------------------------------------ |
| Phase 1 | Extract TERMS (drafts, pins, schedule, unschedule)    | Extracted facets from signatures, clustered signatures |
| Phase 2 | Validate "are DRAFTS and PINS different in codebase?" | Validated signature pairs                              |
| Phase 3 | Codify TERM distinctions ("drafts vs pins")           | Added signature pairs to vocabulary                    |

**Key insight from user**: "I don't know why you're trying to operate directly on signatures."

---

## Correct Approach

### Phase 1: Extract TERMS from Conversations

**Input**: Themes with diagnostic_summary from Run 95

**Extract**:

- Object types: drafts, pins, boards, posts, images, accounts
- Actions: delete, schedule, unschedule, connect, import, create
- Stages: selection, generation, publishing
- Timing: during, after, before

**Output**: Term frequency counts + candidate term pairs

**Script**: `scripts/vocabulary_extract_terms.py` (created, not run yet)

### Phase 2: Validate TERM Distinctions

For each candidate term pair (e.g., "drafts" vs "pins"):

1. Search codebase for how each term is handled
2. Are they different storage? Different APIs?
3. SAME_FIX test: Would understanding this distinction route to different fixes?

**Output**: Validated term distinctions

### Phase 3: Codify as Vocabulary Guidance

Add to `signature_quality_guidelines`:

```json
"term_distinctions": {
  "object_type": {
    "drafts_vs_pins": {
      "why_different": "Drafts are in DynamoDB, pins are in scheduled posts API",
      "guidance": "When users mention bulk delete, ask: drafts or scheduled pins?"
    }
  }
}
```

### Phase 4: Measure Impact

Re-run functional tests to verify distinctions improve classification.

---

## Files

**Keep**:

- `scripts/vocabulary_extract_terms.py` - New correct Phase 1 script
- `scripts/test_vocabulary_guidance.py` - Phase 4 functional tests

**Delete/Ignore** (wrong approach):

- `scripts/vocabulary_extract_and_cluster.py` - Clustered signatures (wrong)
- `scripts/vocabulary_enhance.py` - Added signature pairs (wrong)
- `data/vocabulary_enhancement/phase1_results.json` - Signature-level data (wrong)
- `data/vocabulary_enhancement/phase2_validations.json` - Signature pairs (wrong)

**Reverted**:

- `config/theme_vocabulary.json` - Reverted to before wrong Phase 3
- `src/vocabulary.py` - Reverted changes

---

## Next Steps

1. Run `python scripts/vocabulary_extract_terms.py --use-llm` to extract actual TERMS
2. Review term frequencies and candidate pairs
3. Build Phase 2 to validate TERM distinctions against codebase
4. Build Phase 3 to codify TERM distinctions
5. Run Phase 4 functional tests
