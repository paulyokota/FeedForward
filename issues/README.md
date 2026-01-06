# File-Based Issue Tracking

Simple issue tracking using markdown files. Replaces GitHub Issues for browser-based Claude Code sessions.

## Structure

- `backlog.md` - All issues organized by status

## Issue Format

```markdown
### [ISSUE-XXX] Title
**Phase**: 1 | **Priority**: high/medium/low | **Type**: feature/bug/task
Description of what needs to be done.
- [ ] Subtask 1
- [ ] Subtask 2
```

## Status Sections

Issues live in one of these sections in `backlog.md`:

| Section | Meaning |
|---------|---------|
| Backlog | Not started, prioritized |
| In Progress | Currently being worked on |
| Done | Completed (move here, don't delete) |

## Workflow

1. **Add issue**: Create entry in Backlog section
2. **Start work**: Move to In Progress
3. **Complete**: Move to Done with completion date
4. **Reference**: Use `[ISSUE-XXX]` in commits

## Conventions

- Number issues sequentially: ISSUE-001, ISSUE-002, etc.
- One issue in progress at a time (per session)
- Link to phase from PLAN.md
- Keep descriptions concise - details go in code/comments
