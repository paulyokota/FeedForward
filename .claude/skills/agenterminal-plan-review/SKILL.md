---
name: agenterminal-plan-review
description: Use when you want to submit an implementation plan for review or approval through AgenTerminal. For full reviews, use type plan_review (spawns Codex analysis). For simple plan approval (replacing ExitPlanMode), use type plan_approval — shows the plan content directly to the user.
---

# Agenterminal Plan Review (Requester)

Use this workflow when you have written an implementation plan and want it reviewed before proceeding.

## 1. Write the plan

Write your plan to a file. This can be any path readable from the working directory (e.g. `plan.md`, or the Claude Code plan file).

## 2. Submit for review

Call the `agenterminal.request` MCP tool:

```
agenterminal.request
type: plan_review
description: <brief summary of the plan's goal>
plan_path: <path to the plan file>
auto_dispatch: true
```

The tool blocks until the user accepts or auto-dispatches (up to 5 minutes).

- If **accepted**, returns `{ accepted: true, conversation_id: "<id>" }`. This means the review process started — it does NOT mean the plan passed review.
- If **declined**, returns `{ accepted: false, feedback: "<user's feedback>" }`. Revise the plan and resubmit.
- If **timed out**, returns `{ accepted: false, reason: "timeout" }`.

## 3. Wait for reviewer feedback

A fresh Codex reviewer will be spawned to analyze your plan. Wait for the `[Conversation notification]` or `[Review completed]` message.

When notified, read the conversation:

```
agenterminal.conversation.read
conversation_id: <id>
since_id: <last_seen_id or omit on first read>
```

Check for `PLAN_APPROVED` in a turn from the reviewer (mode: codex) — this means the plan passed with no blocking concerns. Proceed to implementation.

## 4. Handle reviewer feedback (re-review cycle)

If the reviewer has MUST-FIX items (no `PLAN_APPROVED`):

1. Revise your plan file to address the blocking concerns
2. Post an update to the conversation summarizing your revisions:

```
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: <summary of revisions made>
mode: claude
```

3. **Submit a NEW `agenterminal.request`** to spawn a fresh reviewer for re-review:

```
agenterminal.request
type: plan_review
description: Re-review after addressing feedback for <original description>
plan_path: <path to the plan file>
conversation_id: <same conversation_id>
auto_dispatch: true
```

**IMPORTANT: Do NOT poll or wait for the original reviewer to respond. The reviewer has already exited. You MUST submit a new `agenterminal.request` to get a fresh reviewer.**

4. Wait for the new `[Conversation notification]` and repeat from step 3.

The conversation ID persists across all review rounds so each fresh reviewer reads the full history.

## 5. Proceed

Once you see `PLAN_APPROVED` from the reviewer, proceed with implementation.

## Plan Approval (ExitPlanMode replacement)

When you are in plan mode and want user approval to proceed (replacing the built-in ExitPlanMode), use `plan_approval` instead of `plan_review`:

```
agenterminal.request
type: plan_approval
description: <brief summary of the plan's goal>
plan_path: <path to the plan file>
```

This shows the rendered plan content directly to the user for accept/decline. No Codex reviewer is spawned. Use this for lightweight plan approval where you just need a go/no-go from the user.

- If **accepted**, returns `{ accepted: true }`. Proceed with implementation.
- If **declined**, returns `{ accepted: false, feedback: "<user's feedback>" }`. Revise and resubmit.

## Auto-Dispatch (Synchronous)

When using `auto_dispatch: true`, the `agenterminal.request` tool **blocks** until the reviewer completes and returns the result inline:

```json
{ "review_approved": true, "feedback": "..." }
```

- If `review_approved` is `true`: proceed to implementation.
- If `review_approved` is `false`: read the `feedback`, revise the plan, then submit a **NEW** `agenterminal.request` with the same `conversation_id` for re-review.
- Max 3 review rounds.
- Do NOT use `agenterminal.conversation` tools for auto-dispatch reviews — results are inline.

## Tips

- Keep the plan description concise — the reviewer reads the full plan file.
- If you revise the plan after feedback, update the plan file in place so the path stays the same.
- Use `plan_review` when you want Codex analysis alongside user acceptance. Use `plan_approval` when you just need user sign-off (e.g., replacing ExitPlanMode).
- For manual reviews (no auto_dispatch): use conversation tools as described in the main flow.
- For auto-dispatch reviews: the tool blocks and returns results inline — no conversation needed.
