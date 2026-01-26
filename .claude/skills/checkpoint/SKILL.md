---
name: checkpoint
triggers:
  slash_command: /checkpoint
dependencies:
  tools:
    - Read
---

# Checkpoint Skill

A meta-skill that forces a pause and verification before action. Addresses the root pattern across 17+ logged violations: **defaulting to action over verification.**

## When to Use

Invoke `/checkpoint` when:

- Starting a new task or investigation
- About to make code changes
- After compaction recovery
- Sensing drift or uncertainty
- Before any destructive/irreversible operation

## The Four Questions

Before your next action, you MUST answer these four questions honestly:

### 1. PERMISSION

**Did the user ask you to DO something, or UNDERSTAND something?**

| User said                                                     | Means      | Allowed actions                    |
| ------------------------------------------------------------- | ---------- | ---------------------------------- |
| "investigate", "look into", "understand", "trace", "find out" | UNDERSTAND | Read, Grep, Glob, Bash (read-only) |
| "fix", "implement", "add", "create", "change"                 | DO         | Write, Edit (after verification)   |
| Ends with "?" or "yes?", "right?", "correct?"                 | CONFIRM    | Answer the question, then WAIT     |
| Unclear                                                       | ASK        | Ask the user before proceeding     |

**If you're about to Write/Edit but the user asked you to understand something, STOP.**

**If the user's message ends with "?" they are asking you to CONFIRM something, not to DO it. Answer, then WAIT for explicit go-ahead.**

### 2. VERIFIED

**What are you assuming? Have you actually checked it?**

Before action, verify:

| Action                    | Required verification                                                       |
| ------------------------- | --------------------------------------------------------------------------- |
| SQL query                 | `SELECT column_name FROM information_schema.columns WHERE table_name = 'x'` |
| Change function signature | `grep -r "function_name" --include="*.py"` to find all callers              |
| Commit code               | Read every file being committed. Run tests.                                 |
| Revert changes            | Understand what EACH change does before reverting                           |
| Use a table/column        | Query schema first, don't assume                                            |

**"Probably fine" is not verification. Trace the code.**

### 3. VALUE

**Does this help the actual GOAL, or just move a METRIC?**

Ask yourself:

- Will this make the OUTPUT better, or just make a NUMBER change?
- If I achieve this, does the user actually get value?
- Am I optimizing for "task complete" or "problem solved"?

Examples:

- "6 stories created" is meaningless if stories are incoherent garbage
- "Tests pass" is meaningless if tests don't cover the change
- "Code committed" is meaningless if code wasn't read

**Metrics serve goals. Goals don't serve metrics.**

### 4. RECOVERY

**If you're wrong, what breaks? Can we recover?**

| Risk level                                          | Action required                 |
| --------------------------------------------------- | ------------------------------- |
| Easily reversible (git tracked, can undo)           | Proceed with normal caution     |
| Hard to reverse (untracked file, destructive)       | Backup first, confirm with user |
| Expensive to reverse (pipeline run, API credits)    | Get explicit user approval      |
| Irreversible (push to main, delete production data) | STOP. Confirm with user.        |

**When in doubt, ask.**

## Post-Compaction Protocol

If this skill is invoked after compaction:

1. **TALK before DOING** - Explain what you understand about current state
2. **Don't trust summaries blindly** - Summaries describe intent, not correctness
3. **Read before committing** - If there's uncommitted work, READ THE FILES before committing
4. **Get alignment** - Confirm your understanding with user before taking action

## The Meta-Pattern

This skill exists because of a documented failure mode:

```
1. Claude understands the problem
2. Claude jumps to action before getting permission
3. Action is wrong (wrong entry point, wrong approach, incomplete)
4. User corrects
5. Claude acknowledges
6. Claude does the same thing again
7. Context compacts, lessons lost
8. New Claude instance repeats from step 1
```

The four questions interrupt step 2.

## Usage

User invokes: `/checkpoint`

Claude responds with answers to all four questions, then proceeds only if all checks pass.

Example response:

```
Checkpoint:
1. PERMISSION: User asked to "investigate why stories aren't grouping" → UNDERSTAND mode, no code changes
2. VERIFIED: I need to check themes table schema before querying
3. VALUE: Goal is actionable stories, not just "stories created"
4. RECOVERY: Read-only investigation, low risk

Proceeding with investigation. Will not make code changes without explicit permission.
```

## Reference

Full violation log: `.claude/memory/tech-lead/gate-violation-log.md`

Key violations this addresses:

- V1, V8, V12, V14: Action bias (jumped to doing before understanding)
- V5, V10, V13, V15: Understanding failures (acted on assumptions)
- V14: Metric vs value (optimized for number not outcome)
- V11: Failed to verify before destructive action
