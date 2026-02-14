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

4. **Delete session temp directory.** All session artifacts should be in
   `/tmp/ff-YYYYMMDD/`. Clean up:

   ```bash
   rm -rf /tmp/ff-$(date +%Y%m%d)
   ```

   Also check for any stray files in `/tmp/` (slack\__, sc_payload_, etc.)
   from before the session directory convention was adopted.

5. **Stage and commit.** Stage changed files (`box/session.md`, `box/log.md`,
   memory files, any other changes). Commit with a descriptive message.

## What NOT to do

- Don't push. Pushing creates pressure to skip review.
- Don't update `docs/session/last-session.md`. That file gets overwritten by the
  Developer Kit Stop hook.
- Don't update `docs/status.md`. Duplicative with `box/session.md`.
