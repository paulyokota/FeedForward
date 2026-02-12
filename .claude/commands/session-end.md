---
description: End-of-session cleanup, documentation, and commit
argument-hint: [session-summary]
---

# End Session

Complete the current work session with proper documentation and staged commits.

## Steps

1. **Update `box/session.md`**:
   - Replace with current session: date, goal, what happened, key decisions, carried forward items
   - Carried forward = anything in progress or agreed-upon but not yet done

2. **Update `MEMORY.md`** (if durable learnings emerged):
   - Methodology insights, data source quirks, principles
   - Remove anything that turned out to be wrong
   - Keep it under 200 lines

3. **Update `box/log.md`** (if investigation work happened):
   - What was slow, what worked, data source discoveries, tooling friction
   - Date and topic for each entry

4. **Review and stage changes**:

   ```bash
   git status
   git diff --stat
   ```

   - Group related changes into logical commits
   - Use clear commit messages

5. **Summary**: Provide a brief summary of what was accomplished and what's staged

Session summary from user: $ARGUMENTS
