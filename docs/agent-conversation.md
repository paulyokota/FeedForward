# Agent Conversation Log

Protocol version: v1.0
Source roadmaps:

- `/docs/proposed_roadmap_jan_20_claude.md`
- `/docs/proposed_roadmap_jan_20_codex.md`

Purpose: Claude Code ↔ Codex async discussion on roadmap questions, grounded in their existing roadmap drafts.

---

## How to Use This File

1. **Create a new Topic** when you have a roadmap question. Use the template below.
2. **Tag agents** with `Respond Requested: Yes (Claude Code)` or `Yes (Codex)`.
3. **Agents append messages** (never edit). Each message is a complete block.
4. **Humans close Topics** with a resolution and archive the thread.

---

## Topic Template (Copy-Paste)

```markdown
---

### Message
- **Timestamp:** [ISO 8601 UTC]
- **Agent:** Human
- **Topic:** T-001 (Short topic name)
- **Intent:** exploration
- **Respond Requested:** Yes (Claude Code, then Codex) / Yes (Codex) / No
- **Decision Impact:** High / Medium / Low

#### Question
[What decision are you trying to make?]

#### Context
- Claude roadmap: `/docs/proposed_roadmap_jan_20_claude.md` (section: [heading])
- Codex roadmap: `/docs/proposed_roadmap_jan_20_codex.md` (section: [heading])
- Additional context: [timing, constraints, customer signal, etc.]

#### What We Need
- Claude Code: [e.g. "Compare how each roadmap sequences X and Y, propose reconciled order."]
- Codex: [e.g. "Sanity-check this sequence for effort and risk."]

#### Turn Status
Complete – awaiting Claude Code
---
```

---

## Archived Topics

### [ARCHIVED] T-001 – Implementation Context vs PM UX Sequencing

- **Decision:** Option A (Claude hybrid) – Parallel tracks with #62 in Week 1 (2026-01-20)
- **Key insight:** Parallel tracks deliver both PM UX spine and implementation context in 4 weeks instead of 6+ sequential
- **Archive:** `/docs/agent-conversation-archive/2026-01-20_T-001.md`

### [ARCHIVED] T-002 – Architecture: Canonical pipeline + story creation unification

- **Decision:** Approve 4-step sequence; retire `src/pipeline.py` (2026-01-21)
- **Key insight:** UI pipeline already uses `StoryCreationService`; focus on quality gates + legacy cleanup
- **Archive:** `/docs/agent-conversation-archive/2026-01-21_T-002.md`

### [ARCHIVED] T-003 – Architecture: Top opportunities after milestone 5/6

- **Decision:** Converged top 3: pipeline-critical tests, giant file decomposition, configuration consolidation (2026-01-21)
- **Key insight:** Tests on the canonical flow enable safe decomposition; config consolidation is a small reliability win
- **Archive:** `/docs/agent-conversation-archive/2026-01-21_T-003.md`

---

## Active Topics

- (No active topics)
