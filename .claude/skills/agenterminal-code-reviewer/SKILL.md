---
name: agenterminal-code-reviewer
description: Use when acting as a reviewer in an AgenTerminal review conversation. Handles both code reviews (REVIEW_APPROVED) and plan reviews (PLAN_APPROVED).
---

# Agenterminal Code Reviewer

Use this workflow when you are assigned as a code reviewer in an AgenTerminal conversation.

## 1. Inspect the changes

Use the git reference and description provided in your initial prompt to examine the code:

```bash
git diff <ref>
git log --oneline <ref>
```

Read the relevant files to understand context beyond the diff.

## 2. Post your review

Use the conversation tool to post structured feedback:

```
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: <your review>
mode: codex
```

### Review format

Structure each review with these sections:

**MUST-FIX** (blocking issues that must be resolved):

- Security vulnerabilities, logic errors, data loss risks
- Breaking changes without migration path

**Suggestions** (non-blocking improvements):

- Code style, naming, performance, readability
- Alternative approaches worth considering

**Positives** (what's done well):

- Good patterns, thorough tests, clear documentation

## 3. Wait for author response

After posting your review, wait for a `[Conversation notification]` message indicating the author has responded. Then read new turns:

```
agenterminal.conversation.read
conversation_id: <id>
since_id: <last_seen_id>
```

When the author posts updates, re-inspect the changes and provide a follow-up review.

## 4. Approve

When no MUST-FIX issues remain, post the approval token:

```
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: REVIEW_APPROVED - All blocking issues resolved. <optional summary>
mode: codex
```

## Plan Reviews

When assigned as a plan reviewer (your initial prompt will mention "plan reviewer" and a plan file path):

### 1. Read the plan

Read the plan file at the provided path. Understand the full scope.

### 2. Analyze

Focus on different concerns than code review:

- **Feasibility**: Can this be implemented as described? Are there technical blockers?
- **Completeness**: Are requirements covered? Missing edge cases?
- **Risks**: Architecture concerns, security implications, performance bottlenecks?
- **Scope**: Is the plan appropriately scoped, or is it over/under-engineered?

### 3. Post analysis

Use the same structured format (MUST-FIX / Suggestions / Strengths) but with plan-appropriate concerns.

### 4. Approve

When no blocking concerns remain, use `PLAN_APPROVED` (not `REVIEW_APPROVED`):

```
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: PLAN_APPROVED - Plan is feasible with no blocking concerns. <optional summary>
mode: codex
```

## Single-Pass Mode (Auto-Dispatch)

When your initial prompt says "single-pass review", your output is relayed directly to the author — no conversation tools needed:

1. Inspect the changes (code review) or read the plan file (plan review)
2. Provide structured feedback: MUST-FIX (blocking), Suggestions, Positives/Strengths
3. If no MUST-FIX blocking issues remain, output a line containing ONLY:
   `REVIEW_APPROVED` (for code reviews) or `PLAN_APPROVED` (for plan reviews)
   This must be on its own line with no other text on that line.
4. Do NOT use `agenterminal.conversation` tools — your output is captured and relayed automatically
5. If prior review feedback is included in your prompt, the author has addressed those issues — re-review the current state

Do NOT wait for author response in single-pass mode. A fresh reviewer will be spawned for re-reviews if needed.

## Rules

- Only emit `REVIEW_APPROVED` (code) or `PLAN_APPROVED` (plan) when there are genuinely no blocking issues.
- Be specific in feedback — reference file paths and line numbers.
- Distinguish clearly between blocking (MUST-FIX) and non-blocking (suggestion) feedback.
- When re-reviewing, focus on whether previous MUST-FIX items were addressed.
- Ignore your own turns when reading (role=agent, mode=codex).
