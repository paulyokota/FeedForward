# Codebase Structure Review (Quality & Maintainability)

**Purpose**: Summarize current structure, identify maintainability risks, and outline high-leverage architectural improvements.
**Scope**: Backend + UI pipeline, story tracking services, supporting helpers.
**Last updated**: 2026-01-21

> **Note**: This analysis led to Milestone 6 (Canonical Pipeline Consolidation), which has been completed.
> Issues identified here have been addressed:
>
> - Quality gates wired into `StoryCreationService.process_theme_groups()` (#82)
> - `PipelineIntegrationService` retired (#83)
> - Documentation aligned with canonical pipeline (#85)
> - See `docs/architecture/milestone-6-canonical-pipeline.md` for resolution details.

---

## 1) Where We Are Today (Pre-Milestone 6)

The system has grown into multiple pipeline entry points and parallel story-creation paths. It works, but the architecture now favors short-term iteration over cohesion. A few key themes:

- **Multiple pipeline paths**
  - UI pipeline: `src/api/routers/pipeline.py` -> `src/two_stage_pipeline.py`
  - Legacy single-stage pipeline: `src/pipeline.py`
  - CLI helpers: `src/cli.py` / `src/theme_tracker.py`

- **Story creation path exists, but legacy service remains**
  - UI pipeline already uses `StoryCreationService` for theme groups.
  - `PipelineIntegrationService` remains exported but appears unused in production.

- **Quality helpers are implemented but not used by the UI pipeline**
  - Confidence scoring: `src/confidence_scorer.py`
  - Orphan lifecycle / auto-graduation: `src/orphan_matcher.py`, `src/story_tracking/services/orphan_integration.py`
  - Evidence validation: `src/evidence_validator.py`
  - Aggregation + ticket helpers: `src/theme_tracker.py`

- **Module boundaries are blurred**
  - Domain logic is split between `src/` and `src/story_tracking/`.
  - The same concepts appear in multiple layers (themes, evidence, orphans, confidence).

Net: functionality exists, but orchestration is fragmented. The UI pipeline path is not the canonical source of truth for story quality.

---

## 2) Top Risks & Maintainability Drag

1. **Canonical flow ambiguity**
   - Engineers can change one pipeline path and see no effect in UI runs.
   - New features can be "done" but still unused.

2. **Feature drift and inconsistent outputs**
   - Two story-creation paths produce different quality/fields.
   - No shared quality gates (confidence, evidence validation) across flows.

3. **Implicit coupling across layers**
   - Story tracking services consume pipeline artifacts with assumptions that aren’t enforced.
   - Shared concepts (themes, confidence, orphans) lack a single owning module.

4. **Hidden behavior**
   - Helpers exist but only CLI routes call them.
   - UI pipeline lacks visibility into this quality tooling.

---

## 3) Highest-Leverage Opportunities

### A) Define one canonical pipeline

**Goal**: All UI runs and production runs follow the same orchestration path.

- Choose a single entry point and deprecate others.
- UI pipeline should call the same internal orchestration used for batch runs.
- Write this down as "the" pipeline in docs.

### B) Retire legacy story creation service

**Goal**: Only one story-creation path remains.

- Keep `StoryCreationService` as the single interface (already used by UI pipeline).
- Retire `PipelineIntegrationService` and migrate/remove its tests/docs if no hidden callers exist.
- Ensure PM review split/keep, dual-format, code context, and evidence validation are consistently applied.

### C) Wire in quality gates

**Goal**: Output quality is consistent and measurable.

- Integrate `ConfidenceScorer` to compute `stories.confidence_score`.
- Use `OrphanIntegrationService` to accumulate low-signal groups and auto-graduate.
- Apply `EvidenceValidator` before story creation; route failures to orphans or hold.

### D) Clarify module boundaries

**Goal**: Reduce cognitive load and make ownership obvious.

- **Ingestion/classification** lives in `src/`.
- **Story/evidence/orphan** lifecycle lives in `src/story_tracking/`.
- API routers remain orchestration glue only.

---

## 4) Proposed Architecture Direction (Concise)

**Single pipeline flow** (canonical):

1. Classification + theme extraction (existing two-stage path)
2. Grouping + confidence scoring
3. Orphan integration (accumulate + auto-graduate)
4. Story creation via `StoryCreationService`
5. Evidence validation gates
6. Optional dual-format + code context

**Outcome**: The UI pipeline becomes the canonical implementation of story-quality logic rather than a simplified subset.

---

## 5) Concrete Next Steps (Sequenced)

1. **Decide canonical pipeline entry path**
   - Keep `src/two_stage_pipeline.py` + `src/api/routers/pipeline.py` as canonical, or fold into a new orchestrator module.

2. **Retire `PipelineIntegrationService`**
   - Remove or deprecate the legacy service and update exports/tests/docs.

3. **Add quality gates in pipeline orchestration**
   - Confidence scoring + orphan integration + evidence validation.

4. **Deprecate/retire unused pipeline paths**
   - `src/pipeline.py` or other legacy entry points.

---

## 6) Appendix: Key File Inventory

- UI pipeline: `src/api/routers/pipeline.py`
- Two-stage pipeline: `src/two_stage_pipeline.py`
- Legacy pipeline: `src/pipeline.py`
- Story creation: `src/story_tracking/services/story_creation_service.py`
- Pipeline integration: `src/story_tracking/services/pipeline_integration.py`
- Confidence scoring: `src/confidence_scorer.py`
- Orphan lifecycle: `src/orphan_matcher.py`, `src/story_tracking/services/orphan_integration.py`
- Evidence validation: `src/evidence_validator.py`
- Aggregation/ticket helpers: `src/theme_tracker.py`
