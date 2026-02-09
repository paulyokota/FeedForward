---
name: agenterminal-code-review
description: Use when you want to request a code review through AgenTerminal. Submits a review request, waits for approval, then participates in a review conversation loop until the reviewer approves.
---

# Agenterminal Code Review (Requester)

Use this workflow when you want to submit code changes for review through the AgenTerminal review system.

## 1. Submit a review request

Call the `agenterminal.request` MCP tool with your change details:

```
agenterminal.request
type: code_review
description: <brief description of what changed and why>
ref: <git reference, e.g. "HEAD~1..HEAD", a branch name, or commit SHA>
```

The tool blocks until the user approves or rejects (up to 5 minutes).

- If **approved**, the tool returns `{ approved: true, conversation_id: "<id>" }`.
- If **rejected** or timed out, it returns `{ approved: false }`. Stop here.

## 2. Join the review conversation

Once approved, use the conversation ID from the response to poll for reviewer feedback.

Track `last_seen_id` (the most recent turn id you have processed).

### Poll loop

```
# Read new turns
agenterminal.conversation.read
conversation_id: <id>
since_id: <last_seen_id or omit on first read>

# Check for REVIEW_APPROVED token — if any agent turn contains
# "REVIEW_APPROVED", the review is complete. Proceed with your task.

# If there is reviewer feedback, incorporate it:
# 1. Make the requested code changes
# 2. Post an update to the conversation:

agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: <summary of changes made in response to feedback>
mode: claude

# Wait before polling again
sleep 10
```

## 3. Completion

When you see a turn containing `REVIEW_APPROVED` from the reviewer, the review is complete. Announce completion in the conversation and proceed with your original task.

## Tips

- Keep your review description concise but informative.
- Include a meaningful git ref so the reviewer can inspect the exact changes.
- When incorporating feedback, commit your changes before posting the update so the reviewer can see a clean diff.
- Only respond to new turns from the reviewer (role=agent, mode=codex). Ignore your own turns.
