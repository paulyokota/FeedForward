---
name: learning-loop
triggers:
  keywords:
    - fix
    - review issue
    - code issue
    - route fix
dependencies:
  tools:
    - Read
---

# Learning Loop Skill

Route code fixes back to the original developer agent for learning continuity.

## Purpose

When reviewers find issues, route fixes to the original developer who wrote the code. This creates a learning loop where agents improve from fixing their own mistakes.

## The Rule

**WHEN REVIEWERS FIND ISSUES, ROUTE FIXES BACK TO THE ORIGINAL DEV AGENT.**

## Why This Matters

| When Tech Lead fixes directly | When original dev fixes own code |
| ----------------------------- | -------------------------------- |
| Agent never sees the mistake  | Agent learns from the mistake    |
| No memory created             | Memory created with context      |
| Same mistake next time        | Pattern avoided in future        |
| 30 seconds saved              | Institutional knowledge gained   |

**The learning loop matters more than the 30 seconds saved.**

## Workflow

### Phase 1: Track Authorship (During Session)

**Session Touch Log** - Maintain in working memory during session:

```markdown
## Session Touch Log - [Date]

| File                   | Last Agent | Task Ref |
| ---------------------- | ---------- | -------- |
| src/lib/foo.ts         | Agent A    | #123     |
| src/components/Bar.tsx | Agent B    | #124     |
```

**Update when:**

- An agent creates a new file
- An agent modifies an existing file
- You (Tech Lead) modify a file (mark "Tech Lead")

### Phase 2: Route Fixes (After Review)

**When a fix is needed:**

1. **Check Touch Log**: Who touched this file?

2. **If agent found**: Route with this template:

   ```markdown
   ## Fix Required (Learning Loop)

   You previously modified [file] for [task].
   Review found: [issue description]
   Required change: [specific fix]

   You wrote the code, you fix it.
   ```

3. **If Tech Lead**: Fix it yourself

4. **If no entry**: Legacy code, Tech Lead can fix

### Phase 3: Update Memories (Post-Fix)

After agent fixes their own code:

1. **Immediate**: Agent sees fix in context, understands why wrong
2. **Post-merge**: Update agent's "Lessons Learned" section
3. **Memory system**: Create memory file if significant lesson

## Exception Protocol

Exceptions require documentation in Touch Log:

| Allowed Exception            | Required Documentation      |
| ---------------------------- | --------------------------- |
| Agent context exhausted      | "Session X, agent expired"  |
| 3+ round trips on same issue | "Trips: [list], escalating" |

**Disallowed rationalizations:**

- "It's just 1 line" → NOT an exception
- "I can do it faster" → NOT an exception
- "The fix is trivial" → NOT an exception

## Integration with Review

This skill is invoked automatically during code review:

1. Review finds issues
2. Learning Loop identifies original developer
3. Issues routed to that developer
4. Developer fixes own code
5. Review Round 2 verifies fixes

## Success Criteria

- [ ] Session Touch Log maintained during session
- [ ] Fixes routed to original developer (not Tech Lead)
- [ ] Exceptions documented with rationale
- [ ] Agent profiles updated post-merge with lessons

## Common Pitfalls

- **"I'll just fix it" instinct**: Always faster short-term, wrong long-term
- **Forgetting to track**: Session Touch Log must be maintained
- **Rationalizing exceptions**: Most "exceptions" aren't valid
- **Not updating lessons**: Post-merge memory updates are part of the loop

## For Tech Lead

This is one of your most important coordination responsibilities:

1. **Track who wrote what** - Use Session Touch Log
2. **Resist the fix instinct** - Route to original dev
3. **Budget time for learning** - It's not overhead, it's the point
4. **Document violations** - If you skip the loop, document why

## Summary Table

| Situation                                  | Action                     |
| ------------------------------------------ | -------------------------- |
| Review found issues in Agent A's code      | Route fixes to Agent A     |
| Review found issues in Agent B's code      | Route fixes to Agent B     |
| Review found issues in Tech Lead's code    | Fix it yourself            |
| Multi-session work, original agent expired | Fix yourself, document why |
| "It's faster if I just fix it"             | NO. Route to original dev. |
