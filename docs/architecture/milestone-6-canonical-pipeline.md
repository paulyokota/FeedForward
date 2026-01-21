# Milestone 6: Canonical Pipeline Consolidation

**Last Updated**: 2026-01-21
**Status**: Implementation Complete
**Milestone**: [GitHub Milestone 6](https://github.com/paulyokota/FeedForward/milestone/6)

---

## Overview

**Goal**: Wire quality gates into `StoryCreationService`, retire legacy pipeline/services, and align docs/tests with the canonical UI path.

**Issues**:

| Issue | Title                                        | Effort | Status   |
| ----- | -------------------------------------------- | ------ | -------- |
| #82   | Wire quality gates into StoryCreationService | M      | Complete |
| #83   | Retire PipelineIntegrationService            | S      | Complete |
| #85   | Align docs with canonical pipeline           | S      | Complete |
| #80   | Remove legacy single-stage pipeline          | S      | Complete |

**T-002 Decision Reference**: See `docs/agent-conversation-archive/2026-01-21_T-002.md` for the approved 4-step consolidation sequence.

---

## Technical Readiness Assessment

### Quality Gate Helpers (for #82)

| Helper                       | Interface                                | DB Ready                          | Integration Status   |
| ---------------------------- | ---------------------------------------- | --------------------------------- | -------------------- |
| **ConfidenceScorer**         | `score_groups()` → `List[ScoredGroup]`   | `stories.confidence_score` exists | NOT integrated       |
| **EvidenceValidator**        | `validate_samples()` → `EvidenceQuality` | No new columns needed             | NOT integrated       |
| **OrphanIntegrationService** | `process_theme_object()` → `MatchResult` | Full schema exists                | Parallel path exists |

**Key finding**: No schema migrations required. All DB columns already exist from migrations 004-009.

### PipelineIntegrationService (for #83)

| Aspect             | Finding                                              |
| ------------------ | ---------------------------------------------------- |
| Production callers | **ZERO** - completely unused                         |
| Test coverage      | 18 tests (can migrate to StoryCreationService tests) |
| Functionality lost | None - all replicated in StoryCreationService        |
| Risk level         | **Very low**                                         |

**Retirement action**:

1. Migrate useful test patterns to `test_story_creation_service.py`
2. Delete `src/story_tracking/services/pipeline_integration.py`
3. Delete `tests/test_pipeline_integration.py`
4. Update `__init__.py` exports

---

## Resolved Architectural Questions

### Q1: Quality Gate Failure Behavior - RESOLVED

**Decision**: **A. Block** - Skip story creation, route to orphan accumulation

**Rationale**: Stricter quality ensures data quality. Routing to orphans is reversible - groups can accumulate more evidence and be promoted later.

**Implementation**: `_route_to_orphan_integration()` method routes failed groups to `OrphanIntegrationService`.

### Q2: Quality Gate Ordering - RESOLVED

**Decision**: **A. Validate → Score → Create** (sequential, fast-fail)

**Rationale**: Validation is fast and fails quickly on bad data. Scoring requires API call (ConfidenceScorer), so skip it if validation fails. Sequential is simpler than parallel for debugging.

**Implementation**: `_apply_quality_gates()` runs validation first, returns early on failure, then runs scoring.

### Q3: Orphan Architecture Path - RESOLVED

**Decision**: **Via OrphanIntegrationService** for unified orphan logic

**Rationale**: Consistent orphan handling across all paths. OrphanIntegrationService has richer matching logic.

**Implementation**: `_route_to_orphan_integration()` uses `OrphanIntegrationService.process_theme()` with fallback to direct `OrphanService.create()` if unavailable.

### Q4: Integration Pattern - RESOLVED

**Decision**: **C. Before processing** - Filter at top of `process_theme_groups()` loop

**Rationale**: Early rejection keeps the rest of the processing loop clean. Clear control flow: gate first, then decide story vs orphan.

**Implementation**:

- `_apply_quality_gates()` method runs at top of processing loop
- Returns `QualityGateResult` with pass/fail and details
- Failed groups routed to orphan integration before story logic

---

## Completed Sequencing

Based on T-002 decision, all steps completed:

```
1. #85: Declare canonical pipeline (docs update)      ✅ COMPLETE
2. #82: Wire quality gates into StoryCreationService  ✅ COMPLETE
3. #83: Retire PipelineIntegrationService             ✅ COMPLETE
4. #80: Deprecate/remove src/pipeline.py              ✅ COMPLETE
```

**Execution Order**:

1. #82 completed first (core implementation)
2. #83 completed second (cleanup after implementation)
3. #85 completed third (docs alignment)
4. #80 was already complete before milestone started

---

## Key Files

### Canonical Pipeline Entry Point

- `src/two_stage_pipeline.py` - Canonical pipeline for CLI and API use

### Primary Integration Point

- `src/story_tracking/services/story_creation_service.py:321` - `process_theme_groups()`
- `src/story_tracking/services/story_creation_service.py:405` - `_apply_quality_gates()`
- `src/story_tracking/services/story_creation_service.py:521` - `_route_to_orphan_integration()`
- `src/story_tracking/services/story_creation_service.py:684` - `_create_story_with_evidence()`

### Quality Gate Helpers

- `src/confidence_scorer.py` - `score_groups()` method
- `src/evidence_validator.py` - `validate_samples()` method
- `src/story_tracking/services/orphan_integration.py` - `process_theme()` method

### Retired Files (Deleted)

- ~~`src/story_tracking/services/pipeline_integration.py`~~ - Deleted (466 lines, 0 production callers)
- ~~`tests/test_pipeline_integration.py`~~ - Deleted (507 lines, tests migrated)
- ~~`src/pipeline.py`~~ - Removed (single-stage CLI, handled by #80)

---

## Acceptance Criteria - ALL MET

### #82: Wire Quality Gates

- [x] Stories include `confidence_score` from ConfidenceScorer
- [x] Low-volume groups (<3 conversations) go to orphan accumulation
- [x] Evidence validation enforced before story creation
- [x] Validation failures have deterministic outcome (orphan/skip)

### #83: Retire PipelineIntegrationService

- [x] No references to `PipelineIntegrationService` in production code
- [x] Test coverage migrated or equivalent exists in StoryCreationService tests
- [x] `__init__.py` exports updated
- [x] All tests pass

### #85: Align Docs

- [x] Single canonical pipeline path documented
- [x] CLI instructions reference `two_stage_pipeline.py`
- [x] Story creation path references `StoryCreationService.process_theme_groups`

---

## References

- T-002 Resolution: `docs/agent-conversation-archive/2026-01-21_T-002.md`
- Architecture Review: `docs/architecture/codebase-structure-review.md`
- Confidence Scorer: `src/confidence_scorer.py`
- Evidence Validator: `src/evidence_validator.py`
- Story Creation Service: `src/story_tracking/services/story_creation_service.py`
