---
description: End-of-session cleanup and documentation
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

3. **Stage and commit changes**:
   - Group related changes into logical commits
   - Use clear commit messages

4. **Push to remote branch**:
   - Push all commits to the feature branch
   - Do NOT push directly to main

5. **Summary**: Provide a brief summary of what was accomplished

Session summary from user: $ARGUMENTS
