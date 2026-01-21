# Architecture Decision: ThemeTracker, ClassificationManager, and ResolutionAnalyzer

**Date**: 2025-01-21
**Author**: Priya (Architecture)
**Issues**: #78, #79
**Status**: DECISION MADE

---

## Context

During Milestone 5, we identified several modules that exist but are not used by the current UI pipeline (`src/api/routers/pipeline.py`):

| Module                  | Location                        | Used By                      | Not Used By          |
| ----------------------- | ------------------------------- | ---------------------------- | -------------------- |
| `ThemeTracker`          | `src/theme_tracker.py`          | CLI (`src/cli.py`), scripts  | UI pipeline          |
| `ClassificationManager` | `src/classification_manager.py` | Demo/test tools only         | UI pipeline, CLI     |
| `ResolutionAnalyzer`    | `src/resolution_analyzer.py`    | `ClassificationManager` only | UI pipeline directly |
| `KnowledgeExtractor`    | `src/knowledge_extractor.py`    | `ClassificationManager` only | UI pipeline directly |

The recent PR #86 deleted the legacy `src/pipeline.py` and `src/classifier.py` because the current pipeline uses `src/two_stage_pipeline.py`. This raises the question: should these other modules also be retired or integrated?

---

## Analysis

### ThemeTracker (`src/theme_tracker.py`)

**What it provides:**

1. Theme aggregation across conversations (occurrence counts, first/last seen)
2. Excerpt scoring for ticket quality (specificity patterns, repro steps, media links)
3. Shortcut ticket templates (bug vs. trend formats)
4. Ticket lifecycle management (create, update, close stale, reopen)
5. Source tracking (Intercom vs Coda counts)

**Current usage:**

- CLI: `themes`, `trending`, `ticket`, `pending`, `extract` commands
- Scripts: `backfill_historical.py`, `process_historical.py`, `reextract_catchall.py`
- Tests: `test_communities_bug_store.py`

**NOT used by:**

- UI pipeline (`src/api/routers/pipeline.py`)
- Story creation flow (uses `StoryService`, not `ThemeTracker`)

**Key insight:** The UI pipeline has its own story creation path via `StoryCreationService` which:

- Groups themes by signature
- Creates stories via `StoryService`
- Handles orphans via `OrphanService`
- Manages evidence via `EvidenceService`

ThemeTracker's ticket creation is a **parallel, alternative path** to Shortcut tickets that bypasses the story workflow entirely.

### ClassificationManager (`src/classification_manager.py`)

**What it provides:**

- Orchestration wrapper around Stage 1 + Stage 2 classifiers
- Integration with `ResolutionAnalyzer` and `KnowledgeExtractor`
- Convenience methods: `classify_new_conversation`, `refine_with_support_context`, `classify_complete_conversation`

**Current usage:**

- Demo tools only: `tools/demo_integrated_system.py`
- Test tools only: `tools/test_phase1_*.py`

**NOT used by:**

- UI pipeline (uses `two_stage_pipeline.py` directly)
- CLI (uses classifier functions directly)

**Key insight:** The UI pipeline (`two_stage_pipeline.py`) already does what `ClassificationManager` does:

- Calls `classify_stage1_async` and `classify_stage2_async`
- Uses `detect_resolution_signal` (a simpler version of `ResolutionAnalyzer`)
- Stores results via `store_classification_results_batch`

`ClassificationManager` is essentially a **synchronous orchestration wrapper** that was created for testing/demo purposes but never integrated into the main pipeline.

### ResolutionAnalyzer (`src/resolution_analyzer.py`)

**What it provides:**

- Pattern-based detection of support actions (refund, ticket created, docs link, etc.)
- Maps actions to conversation types
- Confidence boost calculation when resolution agrees with prediction

**Current usage:**

- Only via `ClassificationManager`

**Key insight:** `two_stage_pipeline.py` has its own `detect_resolution_signal()` function that does a simpler version of this. The UI pipeline doesn't use the full `ResolutionAnalyzer` at all.

### KnowledgeExtractor (`src/knowledge_extractor.py`)

**What it provides:**

- Extracts root cause, solution, product mentions from support responses
- Detects self-service gaps (manual support work that could be automated)
- Terminology extraction for vocabulary learning

**Current usage:**

- Only via `ClassificationManager`

**Key insight:** This is designed for "continuous learning" feedback loops. The current pipeline doesn't implement this feedback system - knowledge is extracted but never stored or acted upon.

---

## Decision

### Option B: RETIRE ClassificationManager, ResolutionAnalyzer, KnowledgeExtractor

**Rationale:**

1. **ClassificationManager is redundant**: `two_stage_pipeline.py` provides the same functionality with async support and tighter integration with the storage layer. The manager adds an unnecessary abstraction layer.

2. **ResolutionAnalyzer adds marginal value**: The simple `detect_resolution_signal()` in `two_stage_pipeline.py` covers the main use case. The full pattern-based analyzer was designed for a feature (confidence boost) that isn't used.

3. **KnowledgeExtractor is orphaned infrastructure**: It extracts knowledge but there's no system that stores or uses this knowledge. It's premature optimization for a feedback loop that doesn't exist.

4. **Demo/test tools can be updated or removed**: The `tools/` scripts that use these modules are not part of production.

**Files to delete:**

- `src/classification_manager.py`
- `src/resolution_analyzer.py`
- `src/knowledge_extractor.py`
- `config/resolution_patterns.json` (used by ResolutionAnalyzer)
- `tools/demo_integrated_system.py`
- `tools/test_phase1_*.py` (5 files)
- `tools/test_integrated_system.py`

### Option C: KEEP ThemeTracker for CLI-only use

**Rationale:**

1. **CLI is a legitimate use case**: The CLI provides operational visibility for debugging and monitoring that the UI doesn't cover:
   - `python src/cli.py trending` - quick trending report
   - `python src/cli.py ticket <sig>` - preview ticket content
   - `python src/cli.py pending` - what's ready for tickets

2. **Distinct from UI story creation**: ThemeTracker creates Shortcut tickets directly, while the UI creates Stories that later sync to external systems. These are **different workflows for different use cases**.

3. **Scripts depend on it**: Historical data processing scripts use ThemeTracker for backfill operations.

4. **Low maintenance cost**: ThemeTracker is stable, well-tested, and doesn't conflict with the UI pipeline.

**Recommendation**: Keep ThemeTracker but **document clearly** that it's CLI-only and not part of the UI pipeline flow.

---

## Summary

| Module                  | Decision   | Rationale                                       |
| ----------------------- | ---------- | ----------------------------------------------- |
| `ClassificationManager` | **DELETE** | Redundant with `two_stage_pipeline.py`          |
| `ResolutionAnalyzer`    | **DELETE** | Marginal value, simpler version in pipeline     |
| `KnowledgeExtractor`    | **DELETE** | Orphaned infrastructure, no downstream consumer |
| `ThemeTracker`          | **KEEP**   | Legitimate CLI use case, distinct from UI flow  |

---

## Implementation Plan

### PR 3A: Delete ClassificationManager ecosystem

- [ ] Delete `src/classification_manager.py`
- [ ] Delete `src/resolution_analyzer.py`
- [ ] Delete `src/knowledge_extractor.py`
- [ ] Delete `config/resolution_patterns.json`
- [ ] Delete `tools/demo_integrated_system.py`
- [ ] Delete `tools/test_phase1_live.py`
- [ ] Delete `tools/test_phase1_quick.py`
- [ ] Delete `tools/test_phase1_system.py`
- [ ] Delete `tools/test_phase1_realdata.py`
- [ ] Delete `tools/test_integrated_system.py`
- [ ] Update CLAUDE.md if any references exist

### PR 3B: Document ThemeTracker CLI-only scope

- [ ] Add docstring clarifying ThemeTracker is CLI-only, not used by UI
- [ ] Update any docs that might suggest ThemeTracker is part of main pipeline

---

## Alternatives Considered

### Alternative A: Integrate into UI pipeline

**Rejected because:**

- ResolutionAnalyzer provides marginal accuracy improvement over simple detection
- KnowledgeExtractor would require building a feedback system that doesn't exist
- ClassificationManager is literally redundant with existing async pipeline

### Alternative B: Full delete including ThemeTracker

**Rejected because:**

- CLI provides operational value for debugging
- Historical scripts would break
- Different use case (direct Shortcut tickets) from UI (Stories)

---

## References

- Issue #78: ThemeTracker aggregation helpers
- Issue #79: ClassificationManager + ResolutionAnalyzer
- PR #86: Deleted legacy pipeline.py and classifier.py
- `src/two_stage_pipeline.py` - Current pipeline implementation
- `src/api/routers/pipeline.py` - UI pipeline endpoints
