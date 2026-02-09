---
name: agenterminal-conversation
description: Use when participating in Agenterminal conversation threads backed by the agenterminal.conversation MCP tools. Covers join, read/poll, and respond workflow for Claude Code.
---

# Agenterminal Conversation (Claude Code)

Use this workflow when you are asked to join or participate in a conversation panel in Agenterminal.

## Core loop (poll + respond)

1. Ask the user for the conversation ID or use the one in the UI header.
2. Track `last_seen_id` (the most recent turn id you have processed).
3. Poll for new turns:

```
agenterminal.conversation.read
conversation_id: <id>
since_id: <last_seen_id or omit>
```

4. If new turns are returned, update `last_seen_id` to the last item.
5. Respond with one tool call per reply:

```
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: <your response>
mode: claude
```

6. If no new turns, wait and poll again (`sleep 10` works).

## Avoid duplicate replies

- Ignore turns that you authored (role=agent and clearly your own text).
- Only respond to new user turns or messages from the other agent.

## Minimal polling pattern

```
# read
agenterminal.conversation.read
conversation_id: <id>
since_id: <last_seen_id>

# respond (if needed)
agenterminal.conversation
event: turn
conversation_id: <id>
role: agent
text: <reply>
mode: claude

# wait
sleep 10
```
