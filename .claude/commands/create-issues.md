---
description: Generate issues from a spec, file, or prompt
argument-hint: [source-file-or-description]
---

# Create Issues

Parse the provided source and add well-structured issues to the backlog.

## Input

Source: $ARGUMENTS

If a file path is provided, read the file. Otherwise, treat the argument as a description of work to break down.

## Steps

1. **Analyze the source**:
   - If it's a spec/requirements doc, extract discrete tasks
   - If it's a prompt, break down into actionable items
   - If it's code with TODOs, extract each TODO as an issue

2. **For each issue, determine**:
   - Clear, actionable title
   - Phase (from PLAN.md)
   - Priority: high/medium/low
   - Type: feature/bug/task
   - Subtasks if applicable

3. **Get next issue number**:
   - Check `issues/backlog.md` for highest existing ISSUE-XXX
   - Increment for new issues

4. **Add to backlog**:
   - Append each issue to the Backlog section of `issues/backlog.md`
   - Use the standard format from `issues/README.md`

5. **Report created issues**:
   - List all created issue numbers and titles
   - Note any items that couldn't be converted to issues

## Issue Format

```markdown
### [ISSUE-XXX] Title
**Phase**: N | **Priority**: high/medium/low | **Type**: feature/bug/task
Description of what needs to be done.
- [ ] Subtask 1
- [ ] Subtask 2
```

## Guidelines

- Keep issues atomic - one task per issue
- Reference related issues where applicable (e.g., "Depends on ISSUE-001")
- Link to relevant phase in PLAN.md
- Subtasks are optional but helpful for larger issues
