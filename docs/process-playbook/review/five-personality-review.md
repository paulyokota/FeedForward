# Five-Personality Code Review

> Code review using five separate reviewer agents, each with a distinct perspective.

This document is the authoritative reference for the multi-personality review process.

---

## The Golden Rule

```
MINIMUM 2 ROUNDS. NO EXCEPTIONS.

Round 1: Find issues -> Fix them -> Commit
Round 2: Verify fixes -> Find new issues -> Repeat until 0 new issues
         |
Post "CONVERGED" -> Merge immediately
```

**If you haven't run Round 2, you haven't done the review.**

---

## Why 5 Separate Agents?

**DO NOT** use a single agent playing all 5 personalities.

Testing has shown single-agent reviews are too lenient - the agent rubber-stamps its own reasoning across personalities.

**DO** launch 5 separate agents, one per personality, running in parallel.

**Why separate agents matter:**
- Each agent does independent investigation without cross-contamination
- Agents can't unconsciously validate each other's reasoning
- Deeper analysis: separate agents use 3-10x more tool calls per review
- Catches real bugs: 5-agent review finds issues that 1-agent misses

---

## The 5 Reviewer Personalities

| Agent | Name | Focus | Personality |
|-------|------|-------|-------------|
| **Reginald** | The Architect | Correctness, performance, integration | Detailed, severity-based, methodical |
| **Sanjay** | The Security Auditor | Security, validation, OWASP | Paranoid, assumes malicious input |
| **Quinn** | The Quality Champion | Output quality, system coherence | Output-obsessed, traces implications |
| **Dmitri** | The Pragmatist | Simplicity, YAGNI, no bloat | Blunt, questions necessity |
| **Maya** | The Maintainer | Clarity, docs, future maintainability | Future-focused, advocates for next dev |

Each reviewer has a profile with accumulated learnings. See `reviewer-profiles.md` for full prompts.

---

## Execution Flow

```
Round 1: Launch 5 SEPARATE agents in parallel:
         Agent(Reginald) | Agent(Sanjay) | Agent(Quinn) | Agent(Dmitri) | Agent(Maya)
         |
         Collect all results
         |
         Route issues back to ORIGINAL dev agent (see learning-loop.md)
         Dev fixes own code and commits
         |
Round 2: Launch 5 SEPARATE agents again (same pattern)
         |
         Any issues? Route back to original dev -> fix -> commit
         |
Round N: Continue until a round produces 0 new issues
         |
         Post "CONVERGED" comment to PR -> Merge immediately
```

---

## Pre-Review Checklist

**BEFORE starting code review:**

```
[ ] Tests exist for new/changed code
[ ] Tests pass: [test command] succeeds
[ ] Build passes: [build command] succeeds
```

**NO REVIEW WITHOUT TESTS.** Don't start review until tests exist. See `gates/test-gate.md`.

---

## Adversarial Protocol

The reviewer and the code author are often the same person (Claude). This creates a conflict of interest. To counter this:

1. **Your job is to FIND PROBLEMS, not validate the code.** Assume bugs exist. Find them.
2. **Minimum findings requirement.** Each reviewer must identify at least 2 issues or improvement areas.
3. **No "acceptable" or "by design" dismissals.** If something is problematic, flag it.
4. **Ignore author context.** Review the diff as if you've never seen this code before.

---

## Finding Dispositions

Every finding MUST have a clear disposition:

| Disposition | Symbol | When to Use |
|-------------|--------|-------------|
| **Fixed** | CHECK | Issue was addressed in code |
| **Deferred** | LATER | Issue tracked for later (MUST include issue link) |
| **Won't Fix** | NO | Acknowledged but not worth doing (explain why) |

**Key distinction**: "Deferred" means we WILL do it later and it's tracked. If we're not going to track it, call it "Won't Fix" with a clear reason.

---

## PR Documentation (Mandatory)

Every round MUST be documented in the PR. This creates an audit trail.

### Per-Round Summary

After each round, post a consolidated summary:

```markdown
## 5-Personality Review - Round 1

### Summary Table

| Reviewer | Status | Issues Found |
|----------|--------|--------------|
| Architect | Warning 2 Issues | Type safety, missing error handling |
| Security | LGTM | No new concerns |
| Quality | Warning 1 Issue | Missing success feedback |
| Pragmatist | LGTM | No bloat detected |
| Maintainer | Warning 1 Issue | Unclear variable naming |

---

### Issue #1: Type Safety (Architect)

**Severity**: High
**File**: [path/to/file.ts] (line 45)

**Problem**: Response type bypasses type checking.

**Fix**: Add explicit type annotation.

---

[Additional issues...]

### Applying Fixes...
```

### Final Summary (on Convergence)

```markdown
## 5-Personality Review - Round 2 (CONVERGED)

| Reviewer | Status | Notes |
|----------|--------|-------|
| Architect | LGTM | Round 1 fixes verified |
| Security | LGTM | No new concerns |
| Quality | LGTM | Consistency improved |
| Pragmatist | LGTM | No bloat |
| Maintainer | LGTM | Naming clarified |

**0 new issues found across all reviewers - merging immediately per review protocol**

---

## Full Issue Log

### Round 1 Issues (3 total)

| # | Issue | Reviewer | Disposition |
|---|-------|----------|-------------|
| 1 | Type safety | Architect | Fixed in commit abc123 |
| 2 | Missing toast | Quality | Fixed in commit abc123 |
| 3 | Unclear naming | Maintainer | Fixed in commit abc123 |

### Deferred Items (with linked issues)
- Replace confirm() with modal -> #241

### Won't Fix (with rationale)
- None

---

**Converged in 2 rounds. Merging.**
```

---

## Functional Test Authority (For Quality Champion)

The Quality Champion (Quinn) has special authority to demand functional tests for certain changes.

### Automatic Triggers

| File Pattern | Functional Test Required? |
|--------------|--------------------------|
| Agent implementations | **YES** |
| Evaluator logic | **YES** |
| Prompt text or LLM calls | **YES** |
| Detection regex/patterns | **YES** |
| Revision/generation flow | **YES** |

### How to Flag (BLOCKING)

```markdown
**FUNCTIONAL_TEST_REQUIRED** (BLOCKING)

This PR modifies [agent/evaluator/prompt] without functional test evidence.

**Files requiring testing:**
- [path/to/file.ts] - prompt change at line X

**What to test:**
- Run a task through the pipeline
- Verify the changed behavior produces expected output
- Attach logs/output to this PR

**CANNOT CONVERGE** until functional test results are attached.
```

---

## Convergence

Reviews continue until a round produces **zero new issues**.

| PR Complexity | Typical Rounds to Converge |
|---------------|---------------------------|
| Small/clean | 2 rounds |
| Medium | 2-3 rounds |
| Large/complex | 3-4 rounds |

---

## Post-Merge (Same Session)

**AFTER merge, don't skip reflections:**

```
[ ] Deploy documentation agent to collect reflections
[ ] Collect REVIEWER_LEARNING from each reviewer
[ ] Update agent profiles with lessons learned
[ ] Update docs if needed
```

**PRs that skip reflections lose institutional memory.** The whole point of agent profiles is continuity across sessions.

---

## Common Failure Modes

| Failure | Problem | Fix |
|---------|---------|-----|
| **Single-Round Syndrome** | Only Round 1 ran, fixes unverified | ALWAYS run Round 2, even if Round 1 found nothing |
| **Silent Fixes** | Issues fixed with no PR comment | Post findings BEFORE fixing |
| **Missing CONVERGED** | Unclear if review complete | Always post explicit convergence statement |
| **Deferred Without Tracking** | Items marked deferred with no issue link | Every deferred item MUST link to tracking issue |
| **Skipped Reflections** | No learnings collected | Deploy docs agent immediately after merge |

---

## Customization

### Adapting for Your Team

1. **Reviewer names** - Use your own names/personalities
2. **Minimum findings** - Adjust based on PR size
3. **Round requirements** - 2 is minimum; adjust based on risk tolerance
4. **Documentation format** - Adapt tables and templates to your style
5. **Functional test triggers** - Customize file patterns for your codebase

### Scaling Considerations

- **Small PRs** (< 50 lines): Consider quick review (single round)
- **Large PRs** (500+ lines): Budget for 3-4 rounds
- **Critical paths**: Add additional review rounds

---

## Summary

| Stage | Action |
|-------|--------|
| Pre-review | Verify tests exist and pass |
| Round 1 | Launch 5 separate agents in parallel |
| Fix issues | Route to original dev (learning loop) |
| Round 2+ | Repeat until 0 new issues |
| Converge | Post CONVERGED, merge immediately |
| Post-merge | Collect reflections, update profiles |

**The rule: 5 separate agents. Minimum 2 rounds. No exceptions.**
