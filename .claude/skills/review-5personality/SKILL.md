---
name: review-5personality
personalities:
  - ./personalities/reginald.md
  - ./personalities/sanjay.md
  - ./personalities/quinn.md
  - ./personalities/dmitri.md
  - ./personalities/maya.md
triggers:
  keywords:
    - review
    - code review
    - critique
    - convergence
    - round
dependencies:
  skills:
    - learning-loop
---

# 5-Personality Code Review Skill

Multi-round code review using 5 distinct reviewer perspectives to achieve convergence.

## Overview

This skill deploys 5 separate reviewers, each with a unique focus area. Reviews continue for multiple rounds until convergence (no new issues found).

**CRITICAL**: Deploy as 5 SEPARATE agents, not 1 agent playing 5 roles.

## The 5 Reviewers

| Reviewer                 | Focus                     | Key Concerns                               |
| ------------------------ | ------------------------- | ------------------------------------------ |
| **Reginald** (Architect) | Correctness, performance  | Type safety, N+1 queries, logic bugs       |
| **Sanjay** (Security)    | Security, validation      | Injection, auth bypasses, secrets          |
| **Quinn** (Quality)      | Output quality, coherence | System consistency, quality degradation    |
| **Dmitri** (Pragmatist)  | Simplicity, YAGNI         | Over-engineering, unnecessary abstractions |
| **Maya** (Maintainer)    | Clarity, maintainability  | Confusing code, missing docs, naming       |

## Review Protocol

### Round 1: Initial Review

1. **Launch 5 Reviewers in Parallel**
   - Deploy each reviewer as a separate agent
   - Provide code changes to each
   - Collect findings from all 5

2. **Aggregate Issues**
   - Group by severity
   - De-duplicate similar issues
   - Identify ownership (which developer wrote the code)

3. **Route to Original Developer**
   - Use Learning Loop - dev fixes own code
   - Provide consolidated list of issues
   - Dev implements fixes

### Round 2+: Verification Rounds

1. **Launch Same 5 Reviewers Again**
   - Review the fixes from Round 1
   - Look for new issues introduced
   - Verify original issues resolved

2. **Check for Convergence**
   - **Converged**: 0 new issues from all 5 reviewers
   - **Not Converged**: New issues found, repeat from step 3 of Round 1

3. **Post "CONVERGED" and Merge**
   - Document convergence in PR
   - Merge immediately
   - No further review needed

## Workflow

### Phase 1: Pre-Review Setup

1. **Ensure Code is Ready**
   - All tests pass
   - Build succeeds
   - Functional test evidence attached (if required)

2. **Prepare Review Context**
   - What changed and why?
   - What files were modified?
   - Who wrote each file? (Session Touch Log)

### Phase 2: Deploy Reviewers

1. **Create Review Directory**

   ```
   mkdir -p .claude/reviews/PR-{N}
   ```

2. **Launch in Parallel**

   ```
   Agent("Reginald", personality + code + "PR #{N} Round {R}")
   Agent("Sanjay", personality + code + "PR #{N} Round {R}")
   Agent("Quinn", personality + code + "PR #{N} Round {R}")
   Agent("Dmitri", personality + code + "PR #{N} Round {R}")
   Agent("Maya", personality + code + "PR #{N} Round {R}")
   ```

3. **Wait for All to Complete**
   - Each writes to `.claude/reviews/PR-{N}/{name}.md` and `.json`
   - Returns short summary (5-10 lines)
   - Don't aggregate until all 5 finish

### Phase 3: Process Findings

1. **Read JSON Files** (context-efficient)
   - Read `.claude/reviews/PR-{N}/*.json` (~2-5KB each)
   - HIGH/CRITICAL issues first
   - Check `scope` field for systemic vs isolated
   - Only read `.md` files if `see_verbose: true`

2. **Validate Assumptions**
   - Check `verify` field on each issue
   - Tech Lead confirms or dismisses based on verification
   - Don't fix issues with unverified assumptions

3. **Route to Developers**
   - Use Session Touch Log to identify who wrote what
   - Route issues to original developer
   - Invoke Learning Loop skill

4. **Dev Implements Fixes**
   - Original developer addresses their issues
   - Commits fixes
   - Notifies Tech Lead when complete

### Phase 4: Iterate to Convergence

1. **Launch Round 2**
   - Same 5 reviewers
   - Review the fixes

2. **Check Results**
   - If new issues: Route to dev, repeat
   - If no new issues: CONVERGED

3. **Document Convergence**
   - Post "CONVERGED" comment
   - Merge PR

## Success Criteria

- [ ] All 5 reviewers deployed as separate agents (not 1 agent with 5 personalities)
- [ ] Minimum 2 rounds completed
- [ ] Issues routed to original developers (Learning Loop)
- [ ] Convergence achieved (0 new issues)
- [ ] "CONVERGED" comment posted
- [ ] PR merged immediately after convergence

## Constraints

- **MUST** deploy 5 separate agents, not 1 agent playing all roles
- **MUST** complete minimum 2 rounds (even if Round 1 is clean)
- **MUST** route fixes to original developer (Learning Loop)
- **MUST** continue until convergence (no new issues)
- **DO NOT** merge before convergence
- **DO NOT** fix issues yourself (Tech Lead) - route to original dev

## Review Output Format

**CRITICAL**: Reviewers output in a hybrid format to preserve context while keeping outputs compact.

### Output Structure

Each reviewer produces THREE outputs:

1. **Verbose Markdown** (`.claude/reviews/PR-{N}/{reviewer}.md`)
   - Full analysis with code snippets, traces, and reasoning
   - Used for deep dives when needed
   - ~5-50KB per reviewer

2. **Compact JSON** (`.claude/reviews/PR-{N}/{reviewer}.json`)
   - Structured findings for quick triage
   - ~2-5KB per reviewer
   - Contains: severity, confidence, category, why, fix, verify, scope

3. **Summary Message** (returned to Tech Lead)
   - 5-10 lines summarizing verdict and issue counts
   - Points to files for details

### Directory Structure

```
.claude/reviews/
├── SCHEMA.md           # Full format documentation
└── PR-38/
    ├── reginald.md     # Verbose analysis
    ├── reginald.json   # Compact findings
    ├── sanjay.md
    ├── sanjay.json
    ├── quinn.md
    ├── quinn.json
    ├── dmitri.md
    ├── dmitri.json
    ├── maya.md
    └── maya.json
```

### Issue ID Prefixes

Each reviewer uses a unique prefix for issue IDs:

- **R1, R2...** - Reginald (Architect)
- **S1, S2...** - Sanjay (Security)
- **Q1, Q2...** - Quinn (Quality)
- **D1, D2...** - Dmitri (Pragmatist)
- **M1, M2...** - Maya (Maintainer)

### Processing Review Output

1. **Read JSON files** for quick triage (~2-5KB each)
2. **Read MD files only if** `see_verbose: true` or need more context
3. **Use `verify` field** to check assumptions before acting
4. **Use `scope` field** to identify systemic vs isolated issues

See `.claude/reviews/SCHEMA.md` for full field documentation.

## Reviewer Special Authorities

### Quinn: FUNCTIONAL_TEST_REQUIRED

Quinn can flag PRs that need functional testing:

```markdown
## FUNCTIONAL_TEST_REQUIRED

This PR modifies [component] which affects LLM output processing.
Please run a functional test and attach evidence before merge.
```

When flagged, PR is blocked until evidence is attached.

## Integration with Other Skills

### Learning Loop

- Session Touch Log tracks who wrote what
- Issues routed to original developer
- Dev fixes own code to learn from mistakes

### Functional Testing Gate

- Quinn enforces functional testing for LLM changes
- Evidence must be attached before merge
- See `docs/process-playbook/gates/functional-testing-gate.md`

## Common Pitfalls

- **Single agent with 5 roles**: Deploy 5 separate agents, not 1 multi-role agent
- **Skipping rounds**: Must do minimum 2 rounds for validation
- **Tech Lead fixing issues**: Route to original dev (Learning Loop)
- **Merging before convergence**: Continue until 0 new issues
- **Ignoring Quinn's functional test flag**: Evidence is mandatory when flagged

## If Blocked

If review process stalls:

1. Check if issues are routed to correct developer
2. Verify developer has context to fix issues
3. Check if issues are contradictory (need Priya for resolution)
4. Consider if issue is out of scope (file issue for later)
5. Ask Tech Lead for guidance
