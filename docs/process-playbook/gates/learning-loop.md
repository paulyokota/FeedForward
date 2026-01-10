# Learning Loop: Dev Fixes Own Code

> When reviewers find issues, route fixes back to the original developer agent.

This is a PROCESS GATE. Do NOT fix review issues yourself (Tech Lead). This breaks the learning loop.

---

## The Rule

**WHEN REVIEWERS FIND ISSUES, ROUTE FIXES BACK TO THE ORIGINAL DEV AGENT.**

---

## Why This Matters

| When Tech Lead fixes directly | When original dev fixes own code |
|------------------------------|----------------------------------|
| Agent never sees the mistake | Agent learns from the mistake |
| No memory created | Memory created with context |
| Same mistake next time | Pattern avoided in future |
| 30 seconds saved | Institutional knowledge gained |

**The learning loop matters more than the 30 seconds saved.**

Agents learn from fixing their own mistakes:
- Memories and lessons learned only update if the agent experiences the fix
- The experience creates a mental model that persists across sessions
- "I got this wrong before" is powerful context for future work

---

## The Pattern (Correct)

```
Round 1 Review -> Issues found
                      |
               Route to original dev (Agent A, Agent B, etc.)
                      |
               Dev fixes own code + commits
                      |
               Round 2 Review -> Repeat if needed
```

---

## The Anti-Pattern (Broken)

```
Round 1 Review -> Issues found
                      |
               Tech Lead fixes directly (BAD!)
                      |
               Dev agent never learns (BAD!)
```

---

## Enforcement: Session Touch Log

The abstract question "Who wrote this code?" fails because it relies on memory. Instead, maintain a **Session Touch Log**.

### Touch Log Format

Keep this in your working memory during the session:

```markdown
## Session Touch Log - [Date]
| File | Last Agent | Task Ref |
|------|------------|----------|
| src/lib/foo.ts | Agent A | #123 |
| src/components/Bar.tsx | Agent B | #124 |
```

### Update Triggers

Add an entry when:
- An agent creates a new file
- An agent modifies an existing file
- You (Tech Lead) modify a file (mark "Tech Lead" as agent)

### Fix Routing Protocol

When a fix is needed for any file:

1. **Check Touch Log**: Who touched this file?
2. **If agent found**: Route with this template:
   ```
   ## Fix Required (Learning Loop)

   You previously modified [file] for [task].
   Review found: [issue description]
   Required change: [specific fix]

   You wrote the code, you fix it.
   ```
3. **If Tech Lead**: Fix it yourself
4. **If no entry**: Legacy code, Tech Lead can fix

### Exception Protocol

Exceptions require documentation in the Touch Log:

| Allowed Exception | Required Documentation |
|-------------------|------------------------|
| Agent context exhausted | "Session X, agent expired" |
| 3+ round trips same issue | "Trips: [list], escalating" |

**Disallowed rationalizations:**
- "It's just 1 line" -> NOT an exception
- "I can do it faster" -> NOT an exception
- "The fix is trivial" -> NOT an exception

If you catch yourself saying these, you're about to violate the gate.

---

## What Gets Updated

When an agent fixes their own code:

1. **Immediate**: Agent sees the fix in context, understands why it was wrong
2. **Post-merge**: Agent's profile gets updated with the lesson learned
3. **Memory system**: If significant, a memory file is created with full context

This creates a richer learning record than just "Tech Lead fixed it."

---

## For Tech Lead (Claude Code)

This is one of your most important coordination responsibilities:

1. **Track who wrote what** - Use the Session Touch Log
2. **Resist the "I'll just fix it" instinct** - It's always faster short-term, always wrong long-term
3. **Budget time for the learning loop** - It's not overhead, it's the point
4. **Document violations** - If you skip the loop, document why in the PR

---

## Customization

Adapt these aspects:
- Touch Log format can include additional columns (e.g., complexity, time spent)
- Exception protocol can be tightened or loosened based on team preferences
- Consider adding your own "Repeat Offender History" tracking

---

## Summary

| Situation | Action |
|-----------|--------|
| Review found issues in Agent A's code | Route fixes to Agent A |
| Review found issues in Agent B's code | Route fixes to Agent B |
| Review found issues in your (Tech Lead) code | Fix it yourself |
| Multi-session work, original agent context expired | Fix it yourself, document why |
| "It's faster if I just fix it" | NO. Route to original dev. |
