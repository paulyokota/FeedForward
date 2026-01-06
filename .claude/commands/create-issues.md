---
description: Generate issues from a spec, file, or prompt
argument-hint: [source-file-or-description]
---

# Create Issues

Parse the provided source and create well-structured GitHub Issues.

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

3. **Create GitHub Issues**:
   - Use `gh issue create --title "Title" --body "Body" --label "phase-N"`
   - Include phase, priority, and type in the body
   - Add subtasks as a checklist in the body

4. **Report created issues**:
   - List all created issue URLs and titles
   - Note any items that couldn't be converted to issues

## Issue Body Format

```markdown
**Phase**: N | **Priority**: high/medium/low | **Type**: feature/bug/task

Description of what needs to be done.

## Tasks
- [ ] Subtask 1
- [ ] Subtask 2
```

## Guidelines

- Keep issues atomic - one task per issue
- Reference related issues where applicable (e.g., "Depends on #1")
- Link to relevant phase in PLAN.md
- Subtasks are optional but helpful for larger issues
- Use labels like `phase-1`, `phase-2`, etc.
