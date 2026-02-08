# Implementation Plan: Issue #219 — Opportunity PM Agent (Stage 1: Opportunity Framing)

## Context

This is the second agent in the Discovery Engine (after the Customer Voice Explorer, Issue #215). It implements Stage 1 of the 6-stage pipeline: Opportunity Framing.

**Issue**: https://github.com/paulyokota/FeedForward/issues/219
**Dependencies**: #213 (state machine + artifacts), #214 (conversation protocol), #215 (explorer agent)
**Branch**: `feature/219-opportunity-pm`

## What the Agent Does

The Opportunity PM reads Stage 0 explorer findings and synthesizes them into **OpportunityBrief** artifacts. Each brief captures:

- A problem statement (what's wrong, who's affected)
- Typed evidence pointers aggregated from explorer findings
- A mandatory counterfactual ("if we solved X, we'd expect Y measurable change")
- Affected product area
- Explorer coverage metadata

**Critical constraint**: No solution direction. The Opportunity Brief is problem-focused only — solutions emerge in Stage 2.

**Multiple briefs per run**: A single discovery cycle may produce multiple distinct OpportunityBriefs, each proceeding independently through later stages.

## Architecture Decisions

### 1. Single-Pass LLM (Not Two-Pass Like Explorer)

The Explorer uses a two-pass strategy (batch analysis → synthesis) because it processes raw conversation text in batches. The Opportunity PM receives pre-synthesized findings from Stage 0, which are already structured JSON — typically 3-10 findings, each a few hundred bytes. This fits comfortably in a single LLM context window.

**Decision**: Single-pass LLM call that receives all explorer findings and produces OpportunityBriefs.

### 2. Re-Query Via Conversation Protocol

The issue specifies the Opportunity PM can trigger `explorer:request` events when findings need more context. Implementation:

1. After initial LLM pass, check if any opportunity needs additional evidence
2. Post `explorer:request` event to the EXPLORATION stage conversation
3. Read `explorer:response` event back
4. Incorporate into final briefs

For Phase 1, re-query support will be implemented as a method but the initial LLM pass will produce briefs without re-querying. Re-query can be triggered explicitly or by future orchestration logic.

**Re-query integration point**: The `OpportunityPM.requery_explorer()` method is a pure LLM function (same pattern as `CustomerVoiceExplorer.requery()`). The orchestration layer (not yet built) would handle posting `explorer:request` events via `ConversationService.post_event()` and reading `explorer:response` events via `ConversationService.read_history()`. The integration test demonstrates this event flow directly through `ConversationService`, proving protocol compatibility without requiring the orchestrator. The agent itself does NOT post/read events — it receives request text and returns a response dict.

### 3. Input: Read Prior Checkpoints

The agent reads Stage 0 artifacts via `ConversationService.get_prior_checkpoints(run_id)`. This returns the validated `ExplorerCheckpoint` from the completed EXPLORATION stage. The agent parses the checkpoint to extract findings and coverage metadata.

### 4. Output: OpportunityBrief Artifacts

Each brief must conform to the existing `OpportunityBrief` Pydantic model (already defined in `src/discovery/models/artifacts.py`). The checkpoint submission wraps multiple briefs in a dict:

```python
{
    "schema_version": 1,
    "briefs": [
        {... OpportunityBrief fields ...},
        {... OpportunityBrief fields ...},
    ],
    "framing_metadata": {
        "explorer_findings_count": 5,
        "opportunities_identified": 2,
        "model": "gpt-4o-mini",
    }
}
```

**Wait — there's a subtlety here.** The `STAGE_ARTIFACT_MODELS` maps `OPPORTUNITY_FRAMING` to `OpportunityBrief`, which validates a single brief. But we need to submit multiple briefs. Two options:

- **Option A**: Submit one checkpoint per brief (multiple `submit_checkpoint` calls). Problem: `submit_checkpoint` advances the stage, so only the first would work.
- **Option B**: Create a wrapper model that contains a list of briefs. This is cleaner — a single checkpoint submission with all briefs.

**Decision**: Option B. Create an `OpportunityFramingCheckpoint` model (analogous to `ExplorerCheckpoint`) that wraps a list of `OpportunityBrief` objects plus framing metadata. Update `STAGE_ARTIFACT_MODELS` to point to this wrapper.

**Downstream compatibility note**: No Stage 2+ agents exist yet. The only consumer of prior checkpoints is `ConversationService.get_prior_checkpoints()`, which returns raw dicts — callers parse what they need. Future Stage 2 agents will be built knowing the wrapper exists. No existing code breaks from this change.

### 5. Prompt Design

The prompt must enforce:

- NO solution direction (structural, not just "please don't")
- Quantitative counterfactuals where evidence supports it
- Distinct opportunities (don't merge everything into one)
- Evidence traceability back to explorer findings

## Files to Create/Modify

### New Files

| File                                                 | Purpose              |
| ---------------------------------------------------- | -------------------- |
| `src/discovery/agents/opportunity_pm.py`             | Agent implementation |
| `tests/discovery/test_opportunity_pm.py`             | Unit tests           |
| `tests/discovery/test_opportunity_pm_integration.py` | Integration tests    |

### Modified Files

| File                                     | Change                                                                                                         |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `src/discovery/agents/prompts.py`        | Add OPPORTUNITY_FRAMING_SYSTEM, OPPORTUNITY_FRAMING_USER, OPPORTUNITY_REQUERY_SYSTEM, OPPORTUNITY_REQUERY_USER |
| `src/discovery/models/artifacts.py`      | Add `OpportunityFramingCheckpoint` wrapper model                                                               |
| `src/discovery/services/conversation.py` | Update STAGE_ARTIFACT_MODELS to use `OpportunityFramingCheckpoint`                                             |

### Files NOT Touched

- `src/discovery/models/enums.py` — StageType.OPPORTUNITY_FRAMING already exists
- `src/discovery/db/storage.py` — No schema changes needed
- `src/discovery/services/state_machine.py` — Already handles OPPORTUNITY_FRAMING transitions
- `src/discovery/agents/customer_voice.py` — Not modified
- `src/discovery/agents/data_access.py` — Not modified

## Implementation Steps

### Step 1: OpportunityFramingCheckpoint Model

Add to `src/discovery/models/artifacts.py`:

```python
class OpportunityFramingCheckpoint(BaseModel):
    """Stage 1 checkpoint artifact wrapping multiple OpportunityBriefs.

    A single discovery run may identify multiple distinct opportunities.
    Each proceeds independently through Stages 2-5.
    """
    model_config = {"extra": "allow"}

    schema_version: int = 1
    briefs: List[OpportunityBrief] = Field(default_factory=list)  # Empty OK when explorer found nothing
    framing_metadata: FramingMetadata  # See below

class FramingMetadata(BaseModel):
    """Stable metadata fields for downstream consumers."""
    model_config = {"extra": "allow"}

    explorer_findings_count: int = Field(ge=0)
    opportunities_identified: int = Field(ge=0)
    model: str = Field(min_length=1)
```

Update `STAGE_ARTIFACT_MODELS` in `conversation.py` to map `OPPORTUNITY_FRAMING → OpportunityFramingCheckpoint`.

### Step 2: Prompt Templates

Add to `src/discovery/agents/prompts.py`:

**OPPORTUNITY_FRAMING_SYSTEM**: Instruct the LLM to:

- Read explorer findings and identify distinct product/process opportunities
- Frame each as a problem (NOT a solution)
- Include quantitative counterfactuals where evidence supports it
- Aggregate evidence pointers from findings
- Produce multiple distinct briefs when the data supports it

**OPPORTUNITY_FRAMING_USER**: Template with placeholders for:

- `{explorer_findings_json}` — the explorer checkpoint findings
- `{coverage_summary}` — what data the explorers reviewed
- `{num_findings}` — count of explorer findings

**OPPORTUNITY_REQUERY_SYSTEM / USER**: For re-query follow-ups.

### Step 3: OpportunityPM Agent

Create `src/discovery/agents/opportunity_pm.py`:

```python
class OpportunityPMConfig:
    model: str = "gpt-4o-mini"
    temperature: float = 0.5  # Slightly lower than explorer — more structured output

class OpportunityPM:
    def __init__(self, openai_client=None, config=None):
        ...

    def frame_opportunities(self, explorer_checkpoint: Dict[str, Any]) -> FramingResult:
        # 1. Extract findings and coverage from explorer checkpoint
        # 2. LLM call: synthesize into OpportunityBriefs
        # 3. Parse LLM response into typed structures
        # 4. Return FramingResult with briefs + metadata

    def requery_explorer(self, request_text: str, previous_briefs: List[Dict],
                          explorer_findings: List[Dict]) -> Dict:
        # Handle follow-up queries to explorer

    def build_checkpoint_artifacts(self, result: FramingResult) -> Dict[str, Any]:
        # Convert FramingResult into OpportunityFramingCheckpoint schema
```

Key design choices:

- Agent does NOT take ConversationService as a dependency — it's a pure function from findings → briefs
- Checkpoint building is a separate method (same pattern as CustomerVoiceExplorer)
- The orchestration layer handles conversation protocol (reading checkpoints, submitting results)

### Step 4: Unit Tests

`tests/discovery/test_opportunity_pm.py`:

1. **Happy path**: 3 explorer findings → 2 distinct OpportunityBriefs
2. **Single finding → single brief**: Minimal input case
3. **No solution leakage**: Verify LLM output JSON has no `proposed_solution` or `recommendation` keys (structural check, not keyword-based — avoids false positives from benign phrases)
4. **Counterfactual present and actionable**: Every brief has a non-empty counterfactual; qualitative counterfactuals are acceptable when evidence lacks numbers (test checks for non-empty string, not for numeric content)
5. **Evidence traceability**: Every brief's evidence pointers trace back to explorer findings
6. **LLM error handling**: Graceful failure on malformed LLM response
7. **Empty findings**: Explorer found nothing → agent should still produce a valid response (possibly empty checkpoint)
8. **Requery method**: Mock LLM call, verify structured response
9. **Checkpoint building**: FramingResult → OpportunityFramingCheckpoint validation

### Step 5: Integration Tests

`tests/discovery/test_opportunity_pm_integration.py`:

1. **Full stage flow**: EXPLORATION checkpoint → OPPORTUNITY_FRAMING agent → checkpoint validates → advances to next stage (verified against `STAGE_ORDER` enum, not hardcoded)
2. **OpportunityFramingCheckpoint validation**: Artifacts pass Pydantic validation
3. **Conversation audit trail**: checkpoint:submit and stage:transition events appear in conversation
4. **Prior checkpoints readable**: Opportunity PM can read Stage 0 artifacts via `get_prior_checkpoints`

### Step 6: Verify Full Test Suite

- Run `pytest -m "not slow"` (quick check)
- Run `pytest tests/discovery/ -v` (all discovery tests)
- Verify existing 226 discovery tests still pass
- Verify new tests pass

## Acceptance Criteria Mapping

| Issue #219 Criterion                                        | Implementation                                                       |
| ----------------------------------------------------------- | -------------------------------------------------------------------- |
| Agent reads Stage 0 findings from conversation protocol     | `get_prior_checkpoints(run_id)` returns EXPLORATION checkpoint       |
| Produces Opportunity Briefs conforming to artifact contract | `OpportunityBrief` Pydantic validation on each brief                 |
| Counterfactual framing present and quantitative             | Prompt enforces this; test verifies non-empty counterfactual         |
| No solution direction in output                             | Prompt structurally prevents this; test checks for solution keywords |
| Can trigger explorer re-queries                             | `requery_explorer()` method + `explorer:request` event support       |
| Multiple distinct opportunities identified                  | LLM produces list; test verifies count > 1 when evidence supports it |
| Stage transition event fired after briefs submitted         | `submit_checkpoint()` handles this automatically                     |

## Risk Assessment

| Risk                                                             | Mitigation                                                                          |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| LLM produces solution-direction despite instructions             | Prompt structural constraint + post-hoc keyword check in tests                      |
| Single massive brief instead of distinct opportunities           | Prompt explicitly requests identification of distinct problems                      |
| OpportunityFramingCheckpoint breaks existing artifact validation | Careful: only change STAGE_ARTIFACT_MODELS mapping, not the OpportunityBrief itself |
| Re-query adds complexity without clear Phase 1 value             | Implement method but don't force re-query in initial flow                           |

## Estimated Scope

- **New code**: ~300-400 lines (agent + prompts)
- **New tests**: ~200-300 lines (unit + integration)
- **Modified code**: ~20 lines (artifact model + stage mapping)
- **Total**: ~550-700 lines
