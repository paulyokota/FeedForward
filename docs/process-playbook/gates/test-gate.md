# Test Gate: Mandatory Test Requirement

> Tests are a prerequisite for code review. No tests = review cannot start.

This is a PROCESS GATE, not a suggestion.

---

## The Rule

**Tests must exist for new/changed code before code review begins.**

This is non-negotiable. We've learned this the hard way - multiple times.

---

## Why Tests Are Mandatory

| Without Tests | With Tests |
|---------------|------------|
| Bugs caught in review (expensive) | Bugs caught in testing (cheap) |
| No documentation of expected behavior | Tests ARE documentation |
| Refactoring is scary | Refactoring is safe |
| Technical debt compounds | Technical debt is controlled |

**Tests catch bugs before review catches them.** Review is for design, clarity, and edge cases - not for catching basic correctness issues.

---

## Enforcement Points

### 1. At Task Planning Time

When creating a todo list or implementation plan, **tests MUST appear as an explicit item**.

Not "maybe tests later" - tests must be in the list.

**Good:**
```
1. Design API contract
2. Implement backend
3. Implement frontend
4. Write tests           <-- EXPLICIT
5. Code review
```

**Bad:**
```
1. Design API contract
2. Implement backend
3. Implement frontend
4. Code review
// Tests? What tests?
```

### 2. Before Launching Review

Ask yourself: **"Do tests exist for the new code?"**

If NO -> write tests first. Do not proceed to review.

```
// WRONG
Build feature -> Launch reviewers

// RIGHT
Build feature -> Write tests -> Tests pass -> Launch reviewers
```

### 3. Definition of Done Checklist

The Definition of Done includes "Tests exist". This is a hard gate.

```
[ ] Build passes: [command] succeeds
[ ] Tests exist: New/changed code has corresponding tests  <-- HARD GATE
[ ] Tests pass: [command] succeeds
[ ] Review converged: Multiple rounds until 0 new issues
```

**PRs without tests will be reverted.** Document this in your team's workflow.

---

## When to Deploy a Test Specialist vs Writing Tests Yourself

| Deploy Test Specialist | Write Tests Yourself |
|------------------------|---------------------|
| Complex feature with many code paths | Simple single-function change |
| Multiple agents contributed code | You wrote the code yourself |
| Need thorough edge case coverage | Obvious happy path only |
| Want second perspective on test design | Clear what to test |

**When in doubt, use a test specialist.** Test quality matters. Bad tests are worse than no tests (false confidence).

---

## What Good Test Coverage Looks Like

For the code you're adding/changing:

1. **Happy path**: Does it work when given valid input?
2. **Edge cases**: What about empty, null, max, min, boundary values?
3. **Error cases**: Does it fail gracefully with invalid input?
4. **Integration**: Does it work with the rest of the system?

---

## Pre-Review Checklist

Before starting code review (copy this):

```
[ ] Tests exist for new/changed code
    - What's covered? [describe]
[ ] Tests pass: [test command] succeeds
[ ] Build passes: [build command] succeeds
```

If first checkbox is unchecked, **STOP**. Go back and add tests.

---

## For Tech Lead (Claude Code)

This is a coordination checkpoint:

1. **When planning work**: Add tests explicitly to the task list
2. **Before review**: Verify tests exist, ask "who wrote tests?"
3. **If no tests**: Deploy test agent or write them yourself - do NOT proceed to review
4. **If user pushes back**: Tests are not optional. Explain the repeat offender history.

The user might say "skip tests for now." The answer is "no" unless they explicitly override. Document the override if they do.

---

## Customization

Replace these placeholders:

- `[command]` - Your build command (e.g., `npm run build`, `cargo build`)
- `[test command]` - Your test command (e.g., `npm test`, `pytest`)
- Consider adding your own "Repeat Offender History" section documenting past incidents

---

## Summary

| Checkpoint | Action |
|------------|--------|
| Task planning | Add "Write tests" to list |
| Before review | Verify tests exist |
| Tests missing | Write tests or deploy test specialist |
| User says "skip tests" | Push back; document if overridden |
| Tests fail | Fix tests before review |

**The rule is simple: Tests BEFORE review. No exceptions.**
