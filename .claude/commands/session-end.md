---
description: End-of-session cleanup, documentation, and commit
argument-hint: [session-summary]
---

# End Session

Complete the current work session with proper documentation and commits.

## Steps

1. **Review pending changes**:
   ```bash
   git status
   git diff --stat
   ```

2. **Update docs/status.md**:
   - Add session notes under "Recent Session Notes" with today's date
   - Update "What's Done" checklist
   - Update "What's Next" with follow-up tasks
   - Note any blockers encountered

3. **Update changelog** (delegate to `changelog` agent):
   - The `changelog` agent will review commits and add appropriate entries
   - It categorizes changes as Added/Changed/Fixed/Removed
   - Uses user-facing language, not implementation details

4. **Conduct retrospective** (optionally delegate to `retro` agent):
   - If this was a significant session, use the `retro` agent to:
     - Identify what went well and what didn't
     - Capture patterns worth codifying in CLAUDE.md
     - Suggest workflow improvements

5. **Stage and commit changes**:
   - Group related changes into logical commits
   - Use clear commit messages

6. **Push to remote branch**:
   - Push all commits to the feature branch
   - Do NOT push directly to main

7. **Summary**: Provide a brief summary of what was accomplished

Session summary from user: $ARGUMENTS

## Related Agents

- `changelog` - Automatically formats changelog entries
- `retro` - Captures learnings and improves workflows
