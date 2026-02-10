# Discovery Quality Contracts

This document defines a lightweight, stage-by-stage quality contract pattern
for the Discovery Engine. The goal is to preserve creative reasoning while
preventing low-quality artifacts from propagating through the pipeline.

## Principle

Each stage owns the semantic quality of its output. Before handing off to the
next stage, the producing agent must self-check its output against a small set
of acceptance criteria (typically 1–2 checks). If the criteria fail, the agent
must revise, decompose, or return a structured "needs_decomposition" signal
instead of forcing a brief forward.

This is **not** about rigid formatting. Pydantic already enforces structure.
These contracts focus on **semantic quality**: actionability, coherence, and
traceability.

## Pattern (Lightweight)

1. **Stage-specific self-checks** in the producing agent's prompt.
2. **Escape hatch** for cases that are too broad to act on (e.g. "needs_decomposition").
3. **Quality flags/metrics** in checkpoint metadata (counts + short reasons).
4. **No orchestration change** required initially; prompts do the work.

## Stage-by-Stage Criteria (v1)

| Stage | Output | Quality Contract (1–2 checks) |
| --- | --- | --- |
| 0 → 1 | Explorer findings | Specific enough to name a concrete surface/system; evidence pointers present |
| 1 → 2 | Opportunity briefs | **Actionability:** developer can identify a surface/system; **Coherence:** single underlying issue (not a grab-bag) |
| 2 → 3 | Solution briefs | Concrete approach + measurable success criteria |
| 3 → 4 | Feasibility specs | Constraints and risks are explicit and non-empty |
| 4 → 5 | Rankings | Rationale ties to evidence + feasibility inputs |

## Quality Flags (Metadata Convention)

Each checkpoint metadata may include a `quality_flags` object:

```json
{
  "quality_flags": {
    "filtered_items": 2,
    "needs_decomposition": 1,
    "revised_outputs": 1,
    "notes": [
      "Dropped one brief: too broad, no identifiable surface",
      "Split one finding into two briefs"
    ]
  }
}
```

This is intentionally lightweight: counts + short notes. It helps identify
where quality is leaking without adding heavy infrastructure.

## Escape Hatch Pattern

When an item fails the quality gate:
- **Decompose** into multiple specific items when possible, OR
- Return it in a structured `needs_decomposition` list and **do not** emit a
  brief for it.

## Rollout Plan

1. **Start with Stage 1 (OpportunityPM)**: add actionability + coherence
   checks plus `needs_decomposition` and `quality_flags`. (Issue #270)
2. **Document the pattern** (this file). (Issue #271)
3. **Expand to other stages only when evidence indicates** a quality leak.

## Motivation (Runs 1–3)

Recent runs showed broad findings ("Glitches and Performance Issues") flowing
through the pipeline without decomposition. The quality contract pattern
targets this failure mode by making the producing stage responsible for
semantic scope checks.
