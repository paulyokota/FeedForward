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
```

The tool blocks until the user approves or rejects (up to 5 minutes).

- If **approved**, returns `{ approved: true, conversation_id: "<id>" }`.
- If **rejected**, returns `{ approved: false, feedback: "<user's feedback>" }`. Revise the plan and resubmit.
- If **timed out**, returns `{ approved: false, reason: "timeout" }`.

## 3. Handle rejection with feedback

If rejected with feedback:

1. Read the feedback from the response
2. Revise your plan file to address the concerns
3. Resubmit by calling `agenterminal.request` again with the updated description

## 4. Monitor review conversation (optional)

Once approved, a Codex reviewer analyzes your plan and posts to the conversation. You can join to respond:

```
agenterminal.conversation.read
conversation_id: <id>
since_id: <last_seen_id or omit>
```

Look for `PLAN_APPROVED` in a turn from the reviewer — this means the plan has passed analysis with no blocking concerns.

```
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: <response to reviewer feedback>
mode: claude
```

## 5. Proceed

Once you have user approval (from the MCP tool returning `approved: true`) and optionally `PLAN_APPROVED` from the Codex reviewer, proceed with implementation.

## Plan Approval (ExitPlanMode replacement)

When you are in plan mode and want user approval to proceed (replacing the built-in ExitPlanMode), use `plan_approval` instead of `plan_review`:

```
agenterminal.request
type: plan_approval
description: <brief summary of the plan's goal>
plan_path: <path to the plan file>
```

This shows the rendered plan content directly to the user for approve/reject. No Codex reviewer is spawned. Use this for lightweight plan approval where you just need a go/no-go from the user.

- If **approved**, returns `{ approved: true }`. Proceed with implementation.
- If **rejected**, returns `{ approved: false, feedback: "<user's feedback>" }`. Revise and resubmit.

## Tips

- Keep the plan description concise — the reviewer reads the full plan file.
- If you revise the plan after feedback, update the plan file in place so the path stays the same.
- Use `plan_review` when you want Codex analysis alongside user approval. Use `plan_approval` when you just need user sign-off (e.g., replacing ExitPlanMode).
