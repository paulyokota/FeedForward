# Backlog Hygiene: Don't Lose Issues at Session Boundaries

> Issues discovered but not filed are issues lost. Capture them before context resets.

This is a PROCESS GATE that triggers at session end and other checkpoints.

---

## The Problem

Multi-session work has a critical failure mode: **issues discovered late in a session vanish when context resets.**

Signs of this problem:

- "Didn't we talk about that bug last week?"
- "I thought we were going to fix that"
- Recurring issues that keep getting rediscovered

---

## Two Capture Mechanisms

### 1. Tech Lead Triggers

The Tech Lead (Claude Code) actively checks for potential backlog items at specific moments:

| Trigger                                          | What Happened                              | Example                                               |
| ------------------------------------------------ | ------------------------------------------ | ----------------------------------------------------- |
| **Functional test reveals out-of-scope issue**   | Test passed but exposed adjacent problem   | "Parser works, but formatter ignores edge case"       |
| **Fix exposes adjacent problem**                 | Fixed X, but now Y is visible              | "Fixed validation, now seeing inconsistent defaults"  |
| **Reviewers flag valid-but-out-of-scope**        | Legitimate concern, not in this PR's scope | "This config should be environment-specific - defer?" |
| **Architecture discussion surfaces future work** | Design revealed something needed later     | "This approach won't scale past 1000 items"           |
| **Workaround implemented instead of proper fix** | Pragmatic choice, but tech debt            | "Hardcoded value instead of proper config"            |
| **TODO/FIXME added to code**                     | Developer left a breadcrumb                | `// TODO: Handle rate limiting`                       |

### 2. Agent BACKLOG_FLAG Convention

Any agent can flag a potential backlog item for Tech Lead review:

```markdown
## BACKLOG_FLAG

title: [Concise issue title]
reason: [Why this matters, how it was discovered]
suggested_labels: [priority: high/medium/low, type: bug/enhancement/tech-debt]
```

**Rules:**

- Any agent can raise BACKLOG_FLAG
- Tech Lead makes final call: file, merge with existing, or dismiss
- Flag early - better to flag something dismissable than lose something important
- Keep it brief - just enough for Tech Lead to decide

---

## Trigger Checkpoints

Check for backlog items at these natural boundaries:

1. **After functional tests complete** - Before declaring success
2. **After review converges** - Before merging
3. **Session wrap-up** - Before losing context

---

## Quick Decision Tree

```
Is this a real issue that someone will care about?
├── No → Dismiss, don't clutter the backlog
└── Yes → Will it be fixed in THIS PR/session?
    ├── Yes → Fix it, no backlog item needed
    └── No → FILE IT. Include:
        - Clear title
        - Why it matters (what breaks/degrades)
        - How it was discovered
        - Suggested priority/labels
```

---

## Filing Good Issues

When creating an issue from a backlog item:

```markdown
## Problem

[What's broken or missing]

## Discovery

[How/when this was found - PR number, test, review round]

## Impact

[What breaks/degrades without this fix]

## Suggested Approach

[If known - otherwise leave blank]

---

Found via backlog hygiene during [context]
```

---

## Session End Checklist

Before wrapping up ANY session:

```
[ ] Review all BACKLOG_FLAG items raised this session
[ ] Check functional test results for adjacent issues
[ ] Scan TODO/FIXME comments added this session
[ ] File any new issues (or confirm existing ones cover it)
[ ] Update progress file if continuing next session
```

---

## Anti-Patterns

| Anti-Pattern             | Why It's Bad                       | Do Instead                             |
| ------------------------ | ---------------------------------- | -------------------------------------- |
| **"I'll remember this"** | You won't. Context resets.         | File it NOW                            |
| **Silent dismissal**     | Agent raised concern that vanished | Acknowledge dismissals explicitly      |
| **Issue inflation**      | Every minor thing becomes a ticket | Use judgment - is this worth tracking? |
| **Backlog as graveyard** | Issues filed but never reviewed    | Regular backlog grooming               |
| **Duplicate issues**     | Same problem filed multiple ways   | Search before filing                   |

---

## When Agents Use BACKLOG_FLAG

| Agent Type                    | Typical Scenarios                                          |
| ----------------------------- | ---------------------------------------------------------- |
| **Dev agents**                | Schema changes needing migration, cascading prompt changes |
| **Test agents**               | Coverage gaps outside current PR scope                     |
| **Quality reviewers**         | Quality issues in adjacent code                            |
| **Pragmatist reviewers**      | Tech debt observations during review                       |
| **Maintainability reviewers** | Concerns for future work                                   |

---

## For Tech Lead (Claude Code)

### During Session

When you see a BACKLOG_FLAG or hit a trigger:

1. **Capture immediately** - Don't trust yourself to remember later
2. **Quick triage**:
   - Duplicate of existing issue? → Add comment to existing
   - New issue? → File with proper labels
   - Not worth tracking? → Acknowledge and dismiss
3. **Acknowledge the flag** - So the agent knows it was seen

### Integration Points

Backlog hygiene integrates with other gates:

```
Implementation
    ↓
Tests (Test Gate) ← BACKLOG_FLAG: coverage gaps
    ↓
Functional Test ← Trigger: out-of-scope issues
    ↓
Code Review ← BACKLOG_FLAG: valid-but-deferred concerns
    ↓
Convergence & Merge
    ↓
Session End ← Final backlog hygiene check
```

---

## Customization

Adapt these for your project:

- Add project-specific trigger scenarios
- Extend the BACKLOG_FLAG format with custom fields
- Define your issue filing template
- Set up regular backlog grooming cadence (weekly? monthly?)

---

## Summary

| Checkpoint                   | Action                          |
| ---------------------------- | ------------------------------- |
| See BACKLOG_FLAG             | Triage: file, merge, or dismiss |
| Hit a trigger                | Check if issue should be filed  |
| Session ending               | Run session end checklist       |
| About to say "I'll remember" | File it instead                 |
| Uncertain if worth tracking  | When in doubt, file it          |

**The rule: Issues not filed are issues lost. Capture before context resets.**
