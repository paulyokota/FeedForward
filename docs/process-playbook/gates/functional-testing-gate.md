# Functional Testing Gate: Evidence for Pipeline PRs

> When unit tests aren't enough: real output validation before merge.

This is a PROCESS GATE for PRs that change pipelines, prompts, or LLM-dependent code.

---

## The Rule

**PRs that change LLM-dependent code require functional test evidence BEFORE merge.**

Unit tests mock LLM responses. Functional tests run real outputs. Some bugs only surface with real outputs.

---

## Why This Gate Exists

| Unit Tests                          | Functional Tests                   |
| ----------------------------------- | ---------------------------------- |
| Mock LLM responses                  | Real LLM responses                 |
| Fast, deterministic                 | Slower, variable                   |
| Catch logic errors                  | Catch integration errors           |
| Can't validate prompt effectiveness | Can validate actual output quality |

**Unit tests tell you the code works. Functional tests tell you the system works.**

This gate exists because we've merged PRs where:

- Code passed unit tests
- Code review looked clean
- Runtime failed due to real LLM output variations

---

## When Functional Tests Are Required

| PR Type                        | Why Functional Test                                                            |
| ------------------------------ | ------------------------------------------------------------------------------ |
| **New pipeline or phase**      | Static review can't catch schema failures, token limits, threshold calibration |
| **Major agent changes**        | LLM behavior can't be predicted from code review alone                         |
| **Multi-agent coordination**   | Integration issues only surface at runtime                                     |
| **Prompt restructuring**       | Output format changes may break downstream parsing                             |
| **Detection regex changes**    | Patterns depend on actual generated content                                    |
| **Evaluator criteria updates** | Pass/fail thresholds need real content validation                              |

### Not Required For

- Pure frontend changes (no LLM interaction)
- Infrastructure/config changes (no behavior change)
- Documentation updates
- Test-only changes (no production code)

---

## Evidence Format

Include this block in the PR description:

```markdown
## Functional Test Evidence

**Test Type**: [Full pipeline run / Single phase / Regression test]
**Test Date**: YYYY-MM-DD

### Execution Log

- Task/Run ID: `[id]`
- Steps completed: [list]
- Total runtime: X minutes

### Key Metrics

- [Relevant metrics for this PR, e.g., "0 errors", "all phases passed"]

### Issues Discovered During Testing

- [Any issues found and how they were addressed, or "None"]

**Result**: PASS/FAIL - [Brief explanation]
```

**PRs without this evidence block for pipeline changes will be blocked.**

---

## Functional Test Timing

### Consider Testing BEFORE Code Review

For pipeline/LLM changes, running the functional test BEFORE code review can catch issues earlier:

| Timing            | Pros                                                                | Cons                                                      |
| ----------------- | ------------------------------------------------------------------- | --------------------------------------------------------- |
| **Before review** | Catches dead code/wiring bugs early; reviewers see evidence upfront | Longer cycle if code changes significantly in review      |
| **After review**  | Code is "clean" before testing                                      | May discover fundamental issues late (Issue #144 pattern) |

**Recommendation**: For features where the core value depends on data flowing through the pipeline correctly, run a quick functional validation BEFORE review. This catches "silently disabled" patterns where code looks correct but isn't actually wired up.

**Issue #144 Case Study**: Feature passed code review twice before functional testing revealed the `full_conversation` parameter was never actually wired through the pipeline. Earlier functional testing would have caught this immediately.

---

## Running Functional Tests

### General Pattern

```bash
# 1. Trigger the operation that uses LLM
[your-run-command]

# 2. Monitor until complete
[your-status-command]

# 3. Verify results meet expectations
[your-verification-command]
```

### What to Verify

| Component      | What to Check                               |
| -------------- | ------------------------------------------- |
| **Prompts**    | Output format matches expected structure    |
| **Parsers**    | Regex/parsing handles real variations       |
| **Evaluators** | Scores reflect actual quality               |
| **Pipelines**  | All phases complete without blocking errors |
| **Thresholds** | Pass/fail rates are reasonable              |

---

## Reviewer's Role

Reviewers can flag PRs that need functional testing:

```markdown
## FUNCTIONAL_TEST_REQUIRED

This PR modifies [component] which affects LLM output processing.
Please run a functional test and attach evidence before merge.
```

If reviewer flags this, the PR is blocked until evidence is attached.

---

## Regression Testing for Prompt Changes

When modifying prompts or evaluator logic:

1. **Baseline**: Run with current code, record key metrics
2. **Change**: Apply modifications
3. **Compare**: Run same task, compare metrics

### Acceptable vs Concerning Changes

| Metric          | Acceptable        | Red Flag                |
| --------------- | ----------------- | ----------------------- |
| Output quality  | Same or better    | Significant degradation |
| Pass rate       | Similar or higher | Drop >10%               |
| Processing time | Within 20%        | >2x increase            |
| Error rate      | Same or lower     | New errors appear       |

---

## For Tech Lead (Claude Code)

### Pre-Merge Checklist

Before merging any PR that touches LLM-dependent code:

```
[ ] Is this PR type in the "required" list above?
    If YES:
    [ ] Functional test evidence attached?
    [ ] Evidence shows PASS result?
    [ ] Any issues discovered were addressed?
```

### What to Do If Evidence Is Missing

1. **Comment**: Ask for functional test evidence with specific guidance
2. **Block**: Do not approve until evidence is provided
3. **Help**: If needed, guide the developer on how to run the test

---

## Customization

Replace these for your project:

- `[your-run-command]` - How to trigger the LLM operation
- `[your-status-command]` - How to check progress
- `[your-verification-command]` - How to validate results

### Extend the Required List

Add project-specific triggers:

```markdown
| **[Component X] changes** | [Why it needs functional testing] |
```

---

## Summary

| Checkpoint                              | Action                            |
| --------------------------------------- | --------------------------------- |
| PR touches prompts/pipelines            | Check if functional test required |
| Test required, no evidence              | Block PR, request evidence        |
| Evidence attached                       | Verify PASS result before approve |
| Reviewer flags FUNCTIONAL_TEST_REQUIRED | Evidence becomes mandatory        |
| Running functional test                 | Use evidence format template      |

**The rule: Pipeline changes need proof they work. Real outputs, not mocks.**
