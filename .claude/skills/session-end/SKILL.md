---
name: session-end
triggers:
  slash_command: /session-end
dependencies:
  tools:
    - Read
    - Edit
    - Write
    - Bash
---

# /session-end [summary]

End-of-session cleanup, documentation, and commit.

## Steps

1. **Update `box/session.md`** with what happened this session: goal, what was done,
   key decisions, carried forward items. Overwrite previous content.

2. **Update `box/log.md`** with investigation observations: what was slow, what was
   manual, what was repeated, what worked well, what almost didn't happen, data source
   quirks. Date-stamped section header.

3. **Update MEMORY.md** with durable learnings: data source shortcuts, codebase
   navigation patterns, methodology insights. Remove anything that turned out to be
   wrong.

4. **Delete temp files.** Clean up investigation artifacts in `/tmp/`:

   ```bash
   rm /tmp/slack_* /tmp/needs_shipped* /tmp/sc_payload* 2>/dev/null
   ```

   Also delete any other temp files created during this session. Stale temp files
   from previous sessions cause silent errors when consumed as if current.

5. **Stage and commit.** Stage changed files (`box/session.md`, `box/log.md`,
   memory files, any other changes). Commit with a descriptive message.

## What NOT to do

- Don't push. Pushing creates pressure to skip review.
- Don't update `docs/session/last-session.md`. That file gets overwritten by the
  Developer Kit Stop hook.
- Don't update `docs/status.md`. Duplicative with `box/session.md`.
