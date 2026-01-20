# Agent Coordination Protocol v1.0

## Purpose

Define how Claude Code and Codex discuss the roadmap asynchronously inside this repo.

Core idea: agents leave structured, append-only messages in a shared log, grounded in their original roadmap drafts, and humans make final decisions.

---

## Source Roadmap Artifacts

All roadmap topics must treat these as primary inputs:

- Claude roadmap: `/docs/proposed_roadmap_jan_20_claude.md`
- Codex roadmap: `/docs/proposed_roadmap_jan_20_codex.md`

When responding to a roadmap Topic, agents MUST:

- State which roadmap(s) they are referencing.
- Point to specific sections/headings when relevant.
- Call out where their current recommendation differs from their own original roadmap and why.
- Never silently contradict their own roadmap.

---

## Shared Conversation Log

- Location: `/docs/agent-conversation.md`
- Behavior: append-only; no edits, no deletions.
- Each message is a complete block (see template).
- Humans and agents both write to this file.

---

## Message Template

Use this exact structure for each message:

```markdown
---

### Message
- **Timestamp:** 2026-01-20T15:42:00Z
- **Agent:** Claude Code
- **Topic:** T-001 (Async webhooks vs DB migration)
- **Intent:** [exploration | feedback | proposal | concern | resolution]
- **Respond Requested:** Yes (Codex) / Yes (Claude Code) / No
- **Decision Impact:** High / Medium / Low

#### Content
[Your analysis. Be concise and specific.]

#### Roadmap Alignment
- Claude roadmap: [Section/heading in `/docs/proposed_roadmap_jan_20_claude.md` or "N/A"]
- Codex roadmap: [Section/heading in `/docs/proposed_roadmap_jan_20_codex.md` or "N/A"]
- Changes from my original roadmap: [What differs and why, if applicable]

#### Supporting Evidence
- `/src/...` (lines X–Y)
- `/tests/...::test_name`
- Prior message: T-001 @ 2026-01-20T14:00:00Z

#### Turn Status
Complete – [ready for next agent / awaiting human decision / blocked on X]
---
```

Timestamps should be ISO 8601 UTC (e.g. `2026-01-20T15:42:00Z`).

---

## Topics

A Topic is one concrete roadmap question.

Naming convention:

- ID: `T-NNN`
- Title: `[Area] – [Specific question]`

Examples:

- `T-001 – Async webhooks vs DB migration sequencing`
- `T-002 – Webapp production spine scope`
- `T-003 – When to enable evidence automation by default`

Each Topic will have multiple messages from different agents and you.

---

## Topic Lifecycle

States (implicit):

- **Created** – initial question posted.
- **Active** – agents are responding.
- **Awaiting Decision** – agents have framed options; you must choose.
- **Decided** – you've posted a resolution message.
- **Archived** – discussion moved to `/docs/agent-conversation-archive/`.

Resolution messages:

- `Intent: resolution`
- `Respond Requested: No`
- Summarize decision, rationale, and any roadmap doc changes.

---

## Context Boundaries

To keep the log usable:

DO:

- Reference roadmap file + section names.
- Reference code by path + line range.
- Paste short code snippets (5–15 lines) when necessary.
- Paste full error messages when relevant.

DON'T:

- Paste entire roadmap files or large code files.
- Paste long stack traces; summarize, then link.
- Restate previous messages verbatim.

---

## Claude Code – Role

You are the **architect/synthesizer**.

You should respond when:

- Topic explicitly requests "Claude Code".
- Sequencing or dependencies span multiple phases/areas.
- Reconciling the two roadmap drafts is needed.

Your responsibilities:

- Compare and reconcile `/docs/proposed_roadmap_jan_20_claude.md` and `/docs/proposed_roadmap_jan_20_codex.md` where relevant.
- Make dependency/sequencing arguments explicit.
- Propose clear options with tradeoffs.
- Highlight where your current view differs from your original roadmap draft and why.

---

## Codex – Role

You are the **implementation reality check**.

You should respond when:

- Topic explicitly requests "Codex".
- Claude has proposed a sequence or change that affects effort/risk.
- You can estimate effort or highlight operational risk.

Your responsibilities:

- Validate whether proposed sequencing is realistic from a build/run perspective.
- Give honest effort ranges and risk notes.
- Highlight where your current view differs from your original roadmap draft and why.

---

## Turn-Taking

- Append-only; never edit previous messages.
- One message per agent per Topic "turn".
- Don't respond twice in a row on the same Topic unless:
  - correcting an error, or
  - explicitly requested.

Always set `Turn Status` so it's clear who is expected to act next.

---

## Disagreement & Escalation

If Claude Code and Codex disagree:

1. Each posts a message with their position and evidence.
2. One of them (usually Claude) posts a short "disagreement summary" message:
   - Summarize both positions.
   - Explicitly mark: `Turn Status: Complete – awaiting human decision`.
3. You decide and post a resolution.

---

## Archival

- Active log: `/docs/agent-conversation.md`
- Archive directory: `/docs/agent-conversation-archive/`

When a Topic is decided:

1. Copy the full Topic thread to `/docs/agent-conversation-archive/YYYY-MM-DD_T-001.md`.
2. Replace the full thread in `agent-conversation.md` with a short summary block:

```markdown
### [ARCHIVED] T-001 – Async webhooks vs DB migration

- **Decision:** [chosen option, date]
- **Key insight:** [one sentence]
- **Archive:** `/docs/agent-conversation-archive/2026-01-20_T-001.md`
```

---

## Human Responsibilities

- Create Topics when you have real roadmap questions.
- Ensure each Topic links to relevant sections of both roadmap docs.
- Close Topics with a resolution message and archive them.
- Treat agent analysis as input, not as decisions.