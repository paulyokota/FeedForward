---
name: agenterminal-code-review
description: Use when you want to request a code review through AgenTerminal. Submits a review request, waits for the user to accept, then participates in a review conversation until the reviewer approves.
---

# Agenterminal Code Review (Requester)

Use this workflow when you want to submit code changes for review through the AgenTerminal review system.

## 1. Submit a review request

Call the `agenterminal.request` MCP tool with your change details:

```
agenterminal.request
type: code_review
description: <brief description of what changed and why>
ref: <git reference, e.g. "main..HEAD", a branch name, or commit SHA>
auto_dispatch: true
```

The tool blocks until the user accepts or auto-dispatches (up to 5 minutes).

- If **accepted**, returns `{ accepted: true, conversation_id: "<id>" }`. This means the review process started — it does NOT mean the code review passed.
- If **declined** or timed out, it returns `{ accepted: false }`. Stop here.

## 2. Wait for reviewer feedback

A fresh Codex reviewer will be spawned to analyze your code. Wait for the `[Conversation notification]` or `[Review completed]` message.

When notified, read the conversation:

```
agenterminal.conversation.read
conversation_id: <id>
since_id: <last_seen_id or omit on first read>
```

Check for `REVIEW_APPROVED` in a turn from the reviewer (mode: codex) — this means the review passed with no blocking concerns. Proceed with your task.

## 3. Handle reviewer feedback (re-review cycle)

If the reviewer has MUST-FIX items (no `REVIEW_APPROVED`):

1. Make the requested code changes and commit them
2. Post an update to the conversation summarizing your fixes:

```
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: <summary of changes made in response to feedback>
mode: claude
```

3. **Submit a NEW `agenterminal.request`** to spawn a fresh reviewer for re-review:

```
agenterminal.request
type: code_review
description: Re-review after addressing feedback for <original description>
ref: main..HEAD
conversation_id: <same conversation_id>
auto_dispatch: true
```

**IMPORTANT: Do NOT poll or wait for the original reviewer to respond. The reviewer has already exited. You MUST submit a new `agenterminal.request` to get a fresh reviewer.**

4. Wait for the new `[Conversation notification]` and repeat from step 2.

The conversation ID persists across all review rounds so each fresh reviewer reads the full history.

## 4. Completion

When you see a turn containing `REVIEW_APPROVED` from the reviewer, the review is complete. Proceed with your original task.

## Auto-Dispatch (Synchronous)

When using `auto_dispatch: true`, the `agenterminal.request` tool **blocks** until the reviewer completes and returns the result inline:

```json
{ "review_approved": true, "feedback": "..." }
```

- If `review_approved` is `true`: proceed with your task.
- If `review_approved` is `false`: read the `feedback`, fix the MUST-FIX items, then submit a **NEW** `agenterminal.request` with the same `conversation_id` for re-review.
- Max 3 review rounds.
- Do NOT use `agenterminal.conversation` tools for auto-dispatch reviews — results are inline.

## Tips

- Keep your review description concise but informative.
- Include a meaningful git ref so the reviewer can inspect the exact changes.
- When incorporating feedback, commit your changes before posting the update so the reviewer can see a clean diff.
- For manual reviews (no auto_dispatch): use conversation tools as described above.
- For auto-dispatch reviews: the tool blocks and returns results inline — no conversation needed.
