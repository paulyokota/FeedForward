# Discovery Quality Contracts

This document defines the stage-by-stage quality contract pattern for the
Discovery Engine. The goal is to preserve creative reasoning while preventing
low-quality artifacts from propagating through the pipeline.

## Principle

The **receiving stage** validates its input using domain expertise. Each
consuming agent evaluates upstream artifacts against stage-specific acceptance
criteria before processing them. If items fail validation, the producing agent
revises them and the consuming agent re-validates — up to a maximum retry
limit.

This is **not** about rigid formatting. Pydantic already enforces structure.
These contracts focus on **semantic quality**: actionability, coherence, and
traceability.

## Pattern: Validate-Retry-Process

```
1. Consuming agent calls validate_input(items)
   → Returns InputValidationResult: accepted_items + rejected_items
2. If rejections exist:
   a. Producing agent calls revise_rejected(items, rejections, context)
   b. Consuming agent re-validates ONLY revised items
   c. Repeat up to MAX_VALIDATION_RETRIES (2) times
3. Items still rejected after retries → pass through with validation_warnings
4. Final items = accepted (original order) + warned (appended)
5. Stage processes final items through its normal logic
```

Key properties:

- **Conservative fallback**: if `validate_input()` throws, all items are
  accepted (graceful degradation — pipeline never blocks on validation failure)
- **Deterministic ordering**: accepted items preserve original input order;
  warned items are appended at the end
- **Token tracking**: every validation and revision LLM call records token
  usage via `_record_invocation()`
- **Audit trail**: `INPUT_VALIDATION` events posted to the conversation for
  each validation cycle

## Stage-by-Stage Criteria

| Boundary | Consuming Agent     | Producing Agent     | Item ID Field                       | Quality Check                                                                                   |
| -------- | ------------------- | ------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------- |
| 1 → 2    | SolutionDesigner    | OpportunityPM       | `affected_area`                     | Actionability: can a developer identify a concrete surface? Coherence: single underlying issue? |
| 2 → 3    | FeasibilityDesigner | SolutionDesigner    | `affected_area` (from parent brief) | Concrete approach + measurable success criteria?                                                |
| 3 → 4    | TPMAgent            | FeasibilityDesigner | `opportunity_id`                    | Constraints and risks explicit and non-empty?                                                   |

Stage 0 → 1 (explorer findings → opportunity framing) does not have receiving-
stage validation — the OpportunityPM is the first to frame raw findings, so
there is no typed upstream artifact to validate against.

## Quality Flags (Metadata Convention)

Each checkpoint metadata may include a `quality_flags` object:

```json
{
  "quality_flags": {
    "briefs_produced": 10,
    "validation_rejections": 2,
    "validation_retries": 1
  }
}
```

These counters track how much validation activity occurred at each stage
boundary. High `validation_rejections` relative to `briefs_produced` indicates
the upstream stage may need prompt tuning.

## Warning Pass-Through

When an item fails validation after `MAX_VALIDATION_RETRIES` (2) retries:

1. A `validation_warnings` list is attached to the artifact (OpportunityBrief,
   SolutionBrief, or TechnicalSpec)
2. The warning includes the rejection reason:
   `"Rejected after 2 retries: <reason>"`
3. The item is appended to the end of the final items list
4. The stage processes it normally — warnings are informational, not blocking

This ensures the pipeline never drops items due to validation disagreements.
Human reviewers can use `validation_warnings` to flag items for closer
inspection in Stage 5 (human review).

## Agent Methods

Each boundary involves two methods:

**Consuming agent** — `validate_input(items, context) → InputValidationResult`

- Single LLM call batching all items
- Returns accepted/rejected split with rejection reasons
- Empty input → no LLM call, empty result
- Malformed LLM response → accept all (conservative)
- Partial parse → unmentioned items accepted

**Producing agent** — `revise_rejected(items, rejections, context) → revised results`

- One LLM call per rejected item
- Passes rejection reason + original context for targeted revision
- JSONDecodeError → skip item (logged with wasted token count)

## Rollout Status

All three boundaries are implemented:

1. **1 → 2** (SolutionDesigner validates briefs): Issue #276 + #277 + #278
2. **2 → 3** (FeasibilityDesigner validates solutions): Issue #276 + #277 + #278
3. **3 → 4** (TPMAgent validates specs): Issue #276 + #277 + #278

Foundation models (`InputRejection`, `InputValidationResult`,
`validation_warnings` field) established in Issue #275.

Orchestrator integration (validate-retry-process loop) in Issue #278.

## Motivation (Runs 1-3)

Recent runs showed broad findings ("Glitches and Performance Issues") flowing
through the pipeline without decomposition, and some stages producing output
that downstream agents couldn't meaningfully act on. The receiving-stage
validation pattern addresses this by letting domain-expert agents gate their
own input — the agent that will use the artifact is best positioned to judge
whether it's actionable.
