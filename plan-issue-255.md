# Plan: Issue #255 — Shared coerce_str() utility

## Summary

Extract a shared `coerce_str()` function into `src/discovery/agents/base.py` and replace all ad-hoc inline coercion across discovery agents. This consolidates battle-tested logic from the first real run into a single utility.

## Step 1: Add `coerce_str()` to `base.py`

Add a module-level function (not a method) to `src/discovery/agents/base.py`:

```python
def coerce_str(val: Any, fallback: str = "") -> str:
    """Coerce an LLM response value to a string.

    gpt-4o-mini returns structured dicts/lists for Pydantic str fields ~30%
    of the time. This utility normalizes those to JSON strings.

    Fallback semantics: only None and empty string trigger fallback.
    Dicts and lists are ALWAYS serialized (even empty ones) because they
    represent structured data the LLM returned. Other types (int, bool,
    float) are converted via str().

    Args:
        val: The value to coerce. If str, returned as-is (unless empty).
             If dict/list, serialized via json.dumps(). If None, returns
             fallback.
        fallback: Default string when val is None or empty string.

    Returns:
        A plain string suitable for Pydantic str fields.
    """
    if isinstance(val, str):
        return val if val else fallback
    if isinstance(val, (dict, list)):
        return json.dumps(val, indent=2)
    if val is None:
        return fallback
    return str(val)
```

Requires adding `import json` to base.py and ensuring `Any` is imported from `typing`
(already present in the existing imports).

## Step 2: Add unit tests for `coerce_str()`

New file: `tests/discovery/agents/test_base.py`

Test cases:

- `coerce_str("hello")` → `"hello"` (string passthrough)
- `coerce_str({"key": "val"})` → JSON string (dict input)
- `coerce_str([1, 2, 3])` → JSON string (list input)
- `coerce_str("")` → `""` (empty string, no fallback)
- `coerce_str("", fallback="default")` → `"default"` (empty string with fallback)
- `coerce_str(None)` → `""` (None, no fallback)
- `coerce_str(None, fallback="default")` → `"default"` (None with fallback)
- `coerce_str(42)` → `"42"` (int converts via str(), NOT fallback)
- `coerce_str(0)` → `"0"` (zero converts via str(), NOT fallback)
- `coerce_str(True)` → `"True"` (bool converts via str(), NOT fallback)
- `coerce_str(False)` → `"False"` (False converts via str(), NOT fallback)
- `coerce_str({})` → `"{}"` (empty dict serialized as JSON, NOT fallback)
- `coerce_str([])` → `"[]"` (empty list serialized as JSON, NOT fallback)

All tests marked `@pytest.mark.fast`.

## Step 3: Replace inline coercion in `solution_designer.py`

In `_build_result()` (lines 594-607), replace the four `isinstance` checks:

```python
# Before:
raw_solution = proposal.get("proposed_solution", "")
if not isinstance(raw_solution, str):
    raw_solution = json.dumps(raw_solution, indent=2)
# ... (same pattern x4)

# After:
from src.discovery.agents.base import coerce_str

raw_solution = coerce_str(proposal.get("proposed_solution", ""))
raw_rationale = coerce_str(proposal.get("decision_rationale", ""))
experiment_plan = coerce_str(experiment_plan)  # already computed above
success_metrics = coerce_str(success_metrics)  # already computed above
```

The `experiment_plan` and `success_metrics` coercion happens after the validation merge logic (lines 578-592), so the coerce calls replace the existing isinstance blocks at lines 603-607.

## Step 4: Replace local `_coerce_str()` in `feasibility_designer.py`

In `_build_technical_spec()` (lines 340-353):

- Remove the local `_coerce_str()` function definition
- Import `coerce_str` from `base.py`
- Replace `_coerce_str(...)` calls with `coerce_str(...)`

In `_build_infeasible_solution()` (lines 367-380):

- Apply `coerce_str()` to `solution_summary` and `infeasibility_reason` fields (currently unguarded)

## Step 5: Apply coercion to `opportunity_pm.py`

In `build_checkpoint_artifacts()` (lines 219-227), replace `raw_opp.get("field", default)` with `coerce_str(raw_opp.get("field"), fallback=default)`:

- `problem_statement` → `coerce_str(raw_opp.get("problem_statement"), fallback="")` (original default: `""`)
- `counterfactual` → `coerce_str(raw_opp.get("counterfactual"), fallback="")` (original default: `""`)
- `affected_area` → `coerce_str(raw_opp.get("affected_area"), fallback="")` (original default: `""`)

These are string fields from LLM output that could receive dicts.

## Step 6: Apply coercion to explorer `build_checkpoint_artifacts()` methods

All four explorers share the same pattern. In each, replace `raw_finding.get("field", default)` with `coerce_str(raw_finding.get("field"), fallback=default)` — passing the fallback explicitly to `coerce_str()` so that if the key exists but the value is `None`, the fallback is applied (not `""`):

```python
# Before:
"pattern_name": raw_finding.get("pattern_name", "unnamed"),
"description": raw_finding.get("description", ""),

# After:
"pattern_name": coerce_str(raw_finding.get("pattern_name"), fallback="unnamed"),
"description": coerce_str(raw_finding.get("description")),
```

Fields to coerce (with fallback values):

- `pattern_name` → `fallback="unnamed"`
- `description` → `fallback=""` (explicitly pass for clarity)
- `severity_assessment` → `fallback="unknown"`
- `affected_users_estimate` → `fallback="unknown"`

Note: `raw_finding.get("field")` without a default returns `None` when absent, which correctly triggers `coerce_str`'s fallback logic. Using `raw_finding.get("field", "unnamed")` would bypass the fallback when the key is missing, but fail when the key exists with a `None` value. So we drop `dict.get()`'s default and let `coerce_str`'s `fallback` handle both cases.

Files:

- `customer_voice.py` (lines 241-254)
- `codebase_explorer.py` (lines 241-254)
- `analytics_explorer.py` (lines 230-243)
- `research_explorer.py` (lines 261-274)

## Step 7: Run tests

```bash
pytest tests/discovery/ -v          # Full discovery suite
pytest -m "fast"                    # Fast gate
```

## Files Changed

| File                                           | Change                                                                                   |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `src/discovery/agents/base.py`                 | Add `coerce_str()` function + json import                                                |
| `tests/discovery/agents/test_base.py`          | New: unit tests for `coerce_str()`                                                       |
| `src/discovery/agents/solution_designer.py`    | Replace 4 inline isinstance checks                                                       |
| `src/discovery/agents/feasibility_designer.py` | Remove local `_coerce_str()`, use shared; add coercion to `_build_infeasible_solution()` |
| `src/discovery/agents/opportunity_pm.py`       | Add coercion to 3 string fields                                                          |
| `src/discovery/agents/customer_voice.py`       | Add coercion to 4 string fields                                                          |
| `src/discovery/agents/codebase_explorer.py`    | Add coercion to 4 string fields                                                          |
| `src/discovery/agents/analytics_explorer.py`   | Add coercion to 4 string fields                                                          |
| `src/discovery/agents/research_explorer.py`    | Add coercion to 4 string fields                                                          |

## NOT Changed (per guardrails)

- No changes to orchestrator try/except resilience
- No changes to Pydantic model field types
- No Pydantic `field_validator` decorators added
- `tpm_agent.py` `build_checkpoint_artifacts()` — no string fields from LLM output (just wraps rankings list)
