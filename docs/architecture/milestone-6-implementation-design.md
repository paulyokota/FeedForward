# Milestone 6: Canonical Pipeline Consolidation - Implementation Design

**Status**: Ready for Implementation
**Architect**: Priya
**Date**: 2026-01-21
**Scope**: Issues #82, #83, #85

---

## Overview

Wire quality gates (EvidenceValidator, ConfidenceScorer) into `StoryCreationService.process_theme_groups()`, retire unused `PipelineIntegrationService`, and align docs with the canonical pipeline.

**Key Architectural Decisions (Pre-Approved)**:
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Q1: Failure behavior | **Block** (route to orphans) | Keep reversible, maintain data quality |
| Q2: Gate ordering | **Parallel** (validation + scoring) | Independent operations, faster execution |
| Q3: Orphan path | **Via OrphanIntegrationService** | Unified orphan logic across all paths |
| Q4: Code location | **Filter at top of `process_theme_groups()`** | Early rejection, cleaner control flow |

---

## Component Architecture

### Data Flow (Updated)

```
Theme Groups (Dict[str, List[Dict]])
         │
         ▼
┌─────────────────────────────────────────────────────┐
│         StoryCreationService.process_theme_groups() │
│                                                     │
│  1. FOR EACH theme_group:                           │
│     ┌─────────────────────────────────────────┐     │
│     │ PARALLEL QUALITY GATES (new)            │     │
│     │                                         │     │
│     │ ├── EvidenceValidator.validate_samples()│     │
│     │ └── ConfidenceScorer.score_groups()     │     │
│     └─────────────────────────────────────────┘     │
│                      │                              │
│          ┌───────────┴───────────┐                  │
│          ▼                       ▼                  │
│   validation.is_valid?    score < threshold?        │
│          │                       │                  │
│          │ NO                    │ YES              │
│          ▼                       ▼                  │
│   ┌─────────────────┐   ┌─────────────────────┐    │
│   │ ORPHAN PATH     │   │ ORPHAN PATH         │    │
│   │ (failed valid)  │   │ (low confidence)    │    │
│   └───────┬─────────┘   └──────────┬──────────┘    │
│           │                        │                │
│           └────────┬───────────────┘                │
│                    ▼                                │
│     OrphanIntegrationService.process_theme_object() │
│                                                     │
│  2. VALID GROUPS continue to:                       │
│     _create_story_with_evidence()                   │
│     - story.confidence_score = scored_group.score   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Interface Contracts

#### QualityGateResult (New Type)

```python
from dataclasses import dataclass
from typing import Optional
from src.evidence_validator import EvidenceQuality
from src.confidence_scorer import ScoredGroup

@dataclass
class QualityGateResult:
    """Result of running quality gates on a theme group."""

    signature: str
    passed: bool

    # Validation results
    evidence_quality: Optional[EvidenceQuality] = None
    validation_passed: bool = True

    # Scoring results
    scored_group: Optional[ScoredGroup] = None
    confidence_score: float = 0.0
    scoring_passed: bool = True

    # Failure details for logging/debugging
    failure_reason: Optional[str] = None
```

#### Quality Gate Thresholds (Configuration)

```python
# In StoryCreationService.__init__ or as class constants
CONFIDENCE_THRESHOLD = 50.0  # Groups below this go to orphans
VALIDATION_ENABLED = True     # Can disable for migration period
```

#### OrphanIntegrationService Integration

The existing `OrphanIntegrationService.process_theme_object()` method accepts `Theme` objects. We'll use `process_theme()` which accepts dict format:

```python
# Existing interface (no changes needed)
def process_theme(
    self,
    conversation_id: str,
    theme_data: Dict[str, Any],
) -> MatchResult:
    """Process a single extracted theme through orphan matching."""
```

For batch processing of failed groups:

```python
# New method to add to StoryCreationService
def _route_to_orphan_integration(
    self,
    signature: str,
    conversations: List[ConversationData],
    failure_reason: str,
    result: ProcessingResult,
) -> None:
    """Route a failed group to OrphanIntegrationService."""
```

---

## Agent Assignments

### Task 1: Marcus - Wire Quality Gates (#82)

**Owns**: `src/story_tracking/services/story_creation_service.py`

**Deliverables**:

1. Add quality gate imports and dependencies:

   ```python
   from src.evidence_validator import validate_samples, EvidenceQuality
   from src.confidence_scorer import ConfidenceScorer, ScoredGroup
   from .orphan_integration import OrphanIntegrationService
   ```

2. Add `__init__` parameters:

   ```python
   def __init__(
       self,
       story_service: StoryService,
       orphan_service: OrphanService,
       evidence_service: Optional[EvidenceService] = None,
       orphan_integration_service: Optional[OrphanIntegrationService] = None,  # NEW
       confidence_scorer: Optional[ConfidenceScorer] = None,  # NEW
       confidence_threshold: float = 50.0,  # NEW
       validation_enabled: bool = True,  # NEW
       dual_format_enabled: bool = False,
       target_repo: Optional[str] = None,
   ):
   ```

3. Add quality gate check at top of `process_theme_groups()` loop (lines 264-280):

   ```python
   def process_theme_groups(
       self,
       theme_groups: Dict[str, List[Dict[str, Any]]],
       pipeline_run_id: Optional[int] = None,
   ) -> ProcessingResult:
       result = ProcessingResult()

       for signature, conv_dicts in theme_groups.items():
           try:
               # Convert dicts to ConversationData
               conversations = [
                   self._dict_to_conversation_data(d, signature)
                   for d in conv_dicts
               ]

               # NEW: Apply quality gates BEFORE deciding story vs orphan
               gate_result = self._apply_quality_gates(signature, conversations)

               if not gate_result.passed:
                   # Route to orphan integration
                   self._route_to_orphan_integration(
                       signature, conversations, gate_result.failure_reason, result
                   )
                   continue

               # Existing logic: generate PM result and process
               pm_result = self._generate_pm_result(signature, len(conversations))
               # ... (pass gate_result.confidence_score to story creation)
   ```

4. Implement `_apply_quality_gates()` method:

   ```python
   def _apply_quality_gates(
       self,
       signature: str,
       conversations: List[ConversationData],
   ) -> QualityGateResult:
       """
       Apply validation and confidence scoring in parallel.
       Returns QualityGateResult with pass/fail and details.
       """
   ```

5. Implement `_route_to_orphan_integration()` method:

   ```python
   def _route_to_orphan_integration(
       self,
       signature: str,
       conversations: List[ConversationData],
       failure_reason: str,
       result: ProcessingResult,
   ) -> None:
       """Route failed groups to OrphanIntegrationService."""
   ```

6. Pass confidence_score to story creation in `_create_story_with_evidence()`:
   ```python
   story = self.story_service.create(StoryCreate(
       # ... existing fields
       confidence_score=confidence_score,  # NEW: from gate_result
   ))
   ```

**Acceptance Criteria**:

- [ ] Stories include `confidence_score` from ConfidenceScorer
- [ ] Low-confidence groups (< 50.0) routed to orphan accumulation
- [ ] Evidence validation enforced (validation failures go to orphans)
- [ ] Groups with <3 conversations go to orphans (existing behavior preserved)
- [ ] OrphanIntegrationService used for orphan routing (unified logic)
- [ ] All existing tests pass
- [ ] Quality gates can be disabled via constructor flags

**File Ownership**:

- Modify: `src/story_tracking/services/story_creation_service.py`
- Create: `src/story_tracking/services/quality_gate.py` (optional, for QualityGateResult type)
- Do not touch: `src/evidence_validator.py`, `src/confidence_scorer.py`, `src/story_tracking/services/orphan_integration.py`

---

### Task 2: Kenji - Quality Gate Tests + Test Migration (#82)

**Owns**: `tests/test_story_creation_service.py`

**Deliverables**:

1. Add tests for quality gate integration:

   ```python
   class TestQualityGates:
       """Tests for quality gate integration in process_theme_groups."""

       def test_low_confidence_group_routes_to_orphan(self):
           """Groups with confidence < threshold should become orphans."""

       def test_failed_validation_routes_to_orphan(self):
           """Groups failing evidence validation should become orphans."""

       def test_confidence_score_persisted_to_story(self):
           """Stories should have confidence_score from scorer."""

       def test_quality_gates_run_in_parallel(self):
           """Validation and scoring should not block each other."""

       def test_quality_gates_can_be_disabled(self):
           """Flags should allow disabling gates for migration."""
   ```

2. Migrate useful patterns from `test_pipeline_integration.py`:
   - **Keep**: `sample_validated_group` fixture pattern (adapt for StoryCreationService)
   - **Keep**: Excerpt preparation and source stats tests (if not already covered)
   - **Adapt**: Deduplication tests (if relevant)
   - **Drop**: Tests for deleted `PipelineIntegrationService` methods

3. Add tests for orphan routing:

   ```python
   class TestOrphanRouting:
       """Tests for routing failed groups to OrphanIntegrationService."""

       def test_orphan_integration_service_called_for_failed_groups(self):
           """OrphanIntegrationService should be called for failed quality gates."""

       def test_orphan_routing_logs_failure_reason(self):
           """Failure reason should be logged for debugging."""
   ```

**Acceptance Criteria**:

- [ ] Quality gate integration has test coverage
- [ ] Confidence threshold behavior tested (boundary cases: 49.9, 50.0, 50.1)
- [ ] Validation failure behavior tested
- [ ] Orphan routing behavior tested
- [ ] No test coverage lost from pipeline_integration deletion
- [ ] All new tests pass

**File Ownership**:

- Modify: `tests/test_story_creation_service.py`
- Delete: `tests/test_pipeline_integration.py` (after migration)
- Do not touch: `src/` files (test-only)

---

### Task 3: Marcus - Retire PipelineIntegrationService (#83)

**Depends On**: Task 1, Task 2 (quality gates work and tests pass)

**Deliverables**:

1. Remove export from `__init__.py`:

   ```python
   # Remove these lines from src/story_tracking/services/__init__.py:
   # from .pipeline_integration import PipelineIntegrationService, ValidatedGroup
   # And from __all__:
   # "PipelineIntegrationService",
   # "ValidatedGroup",
   ```

2. Delete files:
   - `src/story_tracking/services/pipeline_integration.py` (466 lines)
   - `tests/test_pipeline_integration.py` (507 lines)

3. Verify no remaining references:
   ```bash
   grep -r "PipelineIntegrationService" --include="*.py" src/ tests/
   grep -r "ValidatedGroup" --include="*.py" src/ tests/
   ```

**Acceptance Criteria**:

- [ ] No references to `PipelineIntegrationService` in production code
- [ ] No references to `ValidatedGroup` in production code
- [ ] `__init__.py` exports updated
- [ ] Files deleted: `pipeline_integration.py`, `test_pipeline_integration.py`
- [ ] All remaining tests pass
- [ ] No import errors when importing from `story_tracking.services`

**File Ownership**:

- Modify: `src/story_tracking/services/__init__.py`
- Delete: `src/story_tracking/services/pipeline_integration.py`
- Delete: `tests/test_pipeline_integration.py` (Task 2 completes migration first)

---

### Task 4: Theo - Documentation Alignment (#85)

**Depends On**: Task 1, Task 3 (implementation complete)

**Deliverables**:

1. Update `docs/architecture.md`:
   - Remove references to `PipelineIntegrationService`
   - Document canonical pipeline: `two_stage_pipeline.py` -> `StoryCreationService.process_theme_groups()`
   - Add quality gates section describing validation + scoring

2. Update `docs/status.md`:
   - Mark Milestone 6 issues as complete
   - Update "Next Steps" section

3. Update `CLAUDE.md` if needed:
   - Ensure CLI instructions reference `two_stage_pipeline.py`
   - Update any obsolete pipeline references

4. Update `docs/architecture/milestone-6-canonical-pipeline.md`:
   - Mark architectural questions as resolved
   - Add "Implementation Complete" status
   - Document final interface contracts

5. Archive decision document:
   - Ensure `docs/agent-conversation-archive/2026-01-21_T-002.md` is preserved

**Acceptance Criteria**:

- [ ] Single canonical pipeline path documented clearly
- [ ] CLI instructions reference `two_stage_pipeline.py`
- [ ] Story creation path references `StoryCreationService.process_theme_groups`
- [ ] No references to deprecated `PipelineIntegrationService`
- [ ] Quality gates documented with thresholds
- [ ] Decision rationale preserved

**File Ownership**:

- Modify: `docs/architecture.md`
- Modify: `docs/status.md`
- Modify: `CLAUDE.md` (if needed)
- Modify: `docs/architecture/milestone-6-canonical-pipeline.md`
- Do not touch: `src/` files (docs-only)

---

## Dependency Order

```
        ┌─────────────────────────────────────┐
        │ Task 1: Marcus - Wire Quality Gates │
        │ (Core implementation)               │
        └───────────────┬─────────────────────┘
                        │
           ┌────────────┴────────────┐
           │                         │
           ▼                         ▼
┌──────────────────────┐  ┌─────────────────────────┐
│ Task 2: Kenji        │  │ Task 3: Marcus          │
│ (Tests + Migration)  │  │ (Retire PipelineInteg.) │
│                      │  │ (After tests pass)      │
└──────────┬───────────┘  └───────────┬─────────────┘
           │                          │
           └────────────┬─────────────┘
                        │
                        ▼
           ┌─────────────────────────┐
           │ Task 4: Theo            │
           │ (Documentation)         │
           │ (After implementation)  │
           └─────────────────────────┘
```

**Parallel Execution**:

- Task 1 must complete first
- Task 2 and Task 3 can run in parallel after Task 1
- Task 4 runs after Task 2 and Task 3

---

## Edge Cases

### Quality Gate Edge Cases

| Case                                       | Expected Behavior                                     |
| ------------------------------------------ | ----------------------------------------------------- |
| Empty theme_groups                         | Return empty ProcessingResult, no errors              |
| Group with 0 conversations                 | Skip (already handled by existing logic)              |
| Group with 1-2 conversations               | Route to orphan (existing MIN_GROUP_SIZE check)       |
| Group fails validation but high confidence | Route to orphan (validation failure takes precedence) |
| Group passes validation but low confidence | Route to orphan (confidence threshold applies)        |
| ConfidenceScorer unavailable               | Log warning, skip scoring, treat as passed            |
| OrphanIntegrationService unavailable       | Fall back to existing OrphanService.create()          |
| API rate limit during scoring              | Catch exception, log, treat as failed (conservative)  |

### Migration Edge Cases

| Case                                      | Expected Behavior                                   |
| ----------------------------------------- | --------------------------------------------------- |
| Code imports ValidatedGroup               | Will fail at import time (safe - detected in tests) |
| Test file references deleted module       | Remove test or migrate pattern                      |
| Doc references PipelineIntegrationService | Update doc to reference StoryCreationService        |

---

## Rollback Plan

If issues discovered after merge:

1. **Quality gates causing too many orphans**: Set `confidence_threshold=0` and `validation_enabled=False` via constructor
2. **PipelineIntegrationService unexpectedly used**: Revert the deletion commit, investigate callers
3. **Tests failing after migration**: Revert test changes, investigate coverage gaps

---

## References

- T-002 Decision: `docs/agent-conversation-archive/2026-01-21_T-002.md`
- Architecture Analysis: `docs/architecture/milestone-6-canonical-pipeline.md`
- ConfidenceScorer: `src/confidence_scorer.py`
- EvidenceValidator: `src/evidence_validator.py`
- StoryCreationService: `src/story_tracking/services/story_creation_service.py`
- OrphanIntegrationService: `src/story_tracking/services/orphan_integration.py`
- PipelineIntegrationService (to delete): `src/story_tracking/services/pipeline_integration.py`
