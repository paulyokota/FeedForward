# Post-Compaction Recovery

This command helps recover context after automatic context compaction.

## What to do

1. **Acknowledge the compaction** - Tell the user: "Context was compacted. Let me recover the key information."

2. **Check for active work** - Look for:
   - Open PRs: `gh pr list --state open --author @me`
   - Current branch: `git branch --show-current`
   - Uncommitted changes: `git status`
   - Recent commits: `git log --oneline -5`

3. **Check todo list** - Read current todos to understand what was in progress

4. **Check for background tasks** - Look for any running or completed tasks that may have outputs

5. **Read key status files**:
   - `docs/status.md` - Current project state
   - `docs/session/last-session.md` - Last session notes (if exists)

6. **Summarize for user** - Present a brief summary:

   ```
   ## Post-Compaction Recovery

   **Branch**: [branch name]
   **Uncommitted changes**: [yes/no, brief description]
   **In-progress todos**: [list]
   **Background tasks**: [any pending outputs]

   What would you like me to focus on?
   ```

7. **Wait for user direction** - Do NOT auto-continue any previous work. Ask what they want.

## Key rules

- Do NOT claim to remember things from before compaction
- Do NOT assume the previous task should continue
- Do NOT make changes without explicit user approval
- BE HONEST about what context was lost
