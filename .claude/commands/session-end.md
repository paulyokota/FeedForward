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

3. **Update changelog** (use developer-kit):
   - Run `/developer-kit:changelog` to generate entries from git history
   - Review and add to `docs/changelog.md` under [Unreleased]

4. **Session reflection** (use developer-kit):
   - Run `/developer-kit:reflect --summary --decisions`
   - Captures what was accomplished, key decisions, and learnings
   - Optionally save with `--save docs/session/[date].md`

5. **Stage and commit changes**:
   - Group related changes into logical commits
   - Use clear commit messages

6. **Push to remote branch**:
   - Push all commits to the feature branch
   - Do NOT push directly to main

7. **Summary**: Provide a brief summary of what was accomplished

Session summary from user: $ARGUMENTS

## Developer-Kit Integration

This command leverages the Claudebase Developer Kit:
- `/developer-kit:changelog` - Parses git history, generates formatted changelog
- `/developer-kit:reflect` - Structured session reflection with decisions/learnings
