---
name: functional-testing
triggers:
  keywords:
    - functional test
    - pipeline test
    - llm test
    - prompt test
    - evidence
dependencies:
  tools:
    - Bash
    - Read
---

# Functional Testing Skill

Validate LLM-dependent code with real outputs before merge (evidence required for PRs).

## Purpose

PRs that change LLM-dependent code require functional test evidence BEFORE merge. Unit tests mock LLM responses; functional tests run real outputs.

## The Rule

**PRs that change LLM-dependent code require functional test evidence BEFORE merge.**

## Why This Gate Exists

| Unit Tests                          | Functional Tests                   |
| ----------------------------------- | ---------------------------------- |
| Mock LLM responses                  | Real LLM responses                 |
| Fast, deterministic                 | Slower, variable                   |
| Catch logic errors                  | Catch integration errors           |
| Can't validate prompt effectiveness | Can validate actual output quality |

**Unit tests tell you the code works. Functional tests tell you the system works.**

## When Required

| PR Type                        | Why Functional Test                                  |
| ------------------------------ | ---------------------------------------------------- |
| **New pipeline or phase**      | Schema failures, token limits, threshold calibration |
| **Major agent changes**        | LLM behavior can't be predicted from code alone      |
| **Multi-agent coordination**   | Integration issues only surface at runtime           |
| **Prompt restructuring**       | Output format changes may break downstream parsing   |
| **Detection regex changes**    | Patterns depend on actual generated content          |
| **Evaluator criteria updates** | Pass/fail thresholds need real content validation    |

### Not Required For

- Pure frontend changes (no LLM interaction)
- Infrastructure/config changes (no behavior change)
- Documentation updates
- Test-only changes (no production code)

## Workflow

### Phase 1: Determine if Required

1. **Check PR Type**
   - Does this modify prompts?
   - Does this change classification logic?
   - Does this alter pipeline flow?
   - Does this modify LLM-dependent code?

2. **If YES**: Functional test required

### Phase 2: Run Functional Test

#### General Pattern

```bash
# 1. Trigger the operation that uses LLM
python -m src.pipeline --days 1 --max 10

# 2. Monitor until complete
# (watch logs or check status)

# 3. Verify results meet expectations
python src/cli.py themes  # Check output
```

#### What to Verify

| Component      | What to Check                            |
| -------------- | ---------------------------------------- |
| **Prompts**    | Output format matches expected structure |
| **Parsers**    | Regex/parsing handles real variations    |
| **Evaluators** | Scores reflect actual quality            |
| **Pipelines**  | All phases complete without errors       |
| **Thresholds** | Pass/fail rates are reasonable           |

### Phase 3: Document Evidence

Include this block in PR description:

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

### Phase 4: Regression Testing (for Prompt Changes)

When modifying prompts or evaluator logic:

1. **Baseline**: Run with current code, record metrics
2. **Change**: Apply modifications
3. **Compare**: Run same task, compare metrics

#### Acceptable vs Concerning Changes

| Metric          | Acceptable        | Red Flag                |
| --------------- | ----------------- | ----------------------- |
| Output quality  | Same or better    | Significant degradation |
| Pass rate       | Similar or higher | Drop >10%               |
| Processing time | Within 20%        | >2x increase            |
| Error rate      | Same or lower     | New errors appear       |

## Success Criteria

- [ ] Functional test executed with real LLM calls
- [ ] Evidence formatted per template
- [ ] Key metrics captured
- [ ] Result is PASS (or issues addressed)
- [ ] Evidence attached to PR before merge

## Integration with Review

Quinn (Quality Champion reviewer) can flag PRs requiring functional testing:

```markdown
## FUNCTIONAL_TEST_REQUIRED

This PR modifies [component] which affects LLM output processing.
Please run a functional test and attach evidence before merge.
```

When flagged, PR is blocked until evidence is attached.

## For Tech Lead

### Pre-Merge Checklist

Before merging any PR that touches LLM-dependent code:

```
[ ] Is this PR type in the "required" list?
    If YES:
    [ ] Functional test evidence attached?
    [ ] Evidence shows PASS result?
    [ ] Any issues discovered were addressed?
```

### If Evidence Missing

1. **Comment**: Ask for functional test evidence with specific guidance
2. **Block**: Do not approve until evidence is provided
3. **Help**: Guide developer on how to run the test if needed

## Common Pitfalls

- **Skipping for "small" changes**: Small prompt tweaks can have big impacts
- **Trusting unit tests alone**: Mocks hide real LLM behavior
- **Not documenting evidence**: "I tested it" without evidence doesn't count
- **Ignoring Quinn's flag**: When Quinn flags, evidence is mandatory

## Summary

| Checkpoint                              | Action                            |
| --------------------------------------- | --------------------------------- |
| PR touches prompts/pipelines            | Check if functional test required |
| Test required, no evidence              | Block PR, request evidence        |
| Evidence attached                       | Verify PASS result before approve |
| Reviewer flags FUNCTIONAL_TEST_REQUIRED | Evidence becomes mandatory        |
| Running functional test                 | Use evidence format template      |
