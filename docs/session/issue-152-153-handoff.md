# Issue #152/#153: Signature Canonicalization & Vocabulary Enhancement - Session Handoff

**Date**: 2026-01-29
**Branch**: main
**Resume from**: Issue #153 - Systematic vocabulary enhancement

---

## Session Summary

This session continued work on Issue #152 (embedding-based signature canonicalization) and resulted in a new issue #153 (systematic vocabulary enhancement).

### Key Findings

1. **Vocabulary guidance helps but doesn't scale**: Added object-type examples to `signature_quality_guidelines` (drafts vs scheduled pins, scheduling vs unscheduling, DURING vs AFTER). Functional tests showed 5/8 pass - but the 3 failures were vocabulary coverage gaps, not guidance issues.

2. **Facet system already captures direction**: Discovered that `FacetExtractionService` already extracts `direction` (excess, deficit, creation, deletion, modification, performance, neutral) at conversation level. This is used in hybrid clustering but NOT in signature generation.

3. **Problem reframing**: The issue isn't "how do we tune embeddings" but "how do we build vocabulary that reflects real architectural distinctions." Starting from codebase is too noisy; starting from conversations filters for what users actually talk about.

### Work Products

**Committed**:

- `docs/session/issue-152-handoff.md` - Previous session's handoff
- `scripts/signature_embedding_prototype.py` - Embedding prototype (76% F1)

**Created this session**:

- Issue #153 - Documents systematic vocabulary enhancement process

**Rolled back** (waiting for systematic approach):

- Vocabulary updates to `config/theme_vocabulary.json`
- `scripts/test_vocabulary_guidance.py` - Functional test script

---

## Next Steps (Issue #153)

### Phase 1: Extract Distinctions from Conversations

- Analyze Run 95 themes (543 themes, 323 signatures)
- Extract object types (drafts, pins, boards), actions (delete, schedule, unschedule), stages (selection, generation)
- Cluster similar signatures to find near-duplicates

### Phase 2: Validate Against Codebase

- For each candidate distinction, check if it maps to different code paths
- Apply SAME_FIX test: Would one fix address both?

### Phase 3: Codify as Vocabulary Entries

- Add validated entries to `theme_vocabulary.json`
- Include keywords mapping user terminology

### Phase 4: Measure Impact

- Re-run functional tests
- Monitor pipeline orphan rates

---

## Key Context for Next Session

**Why conversations first, not codebase**: Codebase has many internal entities users never mention. Conversations filter for what's actually relevant.

**The SAME_FIX test**: Already in vocabulary guidelines but lacked object-type examples. The test: "Would ONE implementation fix ALL conversations with this signature?"

**Existing infrastructure**:

- `ThemeVocabulary` in `src/vocabulary.py` with `format_signature_examples()`
- `FacetExtractionService` with direction facet
- Hybrid clustering uses facets at story level

**False positive patterns from ground truth**:

1. Object type: drafts vs scheduled pins (3 cases)
2. Action direction: scheduling vs unscheduling (1 case)
3. Timing/stage: DURING vs AFTER (2 cases)
4. Workflow stage: selection vs generation (1 case)

---

## Do NOT

- Don't make ad-hoc vocabulary additions - follow systematic process
- Don't skip codebase validation - user terminology may map to same underlying thing
- Don't forget SAME_FIX test as the gate

---

_Auto-generated session handoff_
