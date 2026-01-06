---
description: Generate GitHub issues from a spec, file, or prompt
argument-hint: [source-file-or-description]
---

# Create GitHub Issues

Parse the provided source and create well-structured GitHub issues.

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
   - Description with context and acceptance criteria
   - Appropriate labels (bug, enhancement, documentation, etc.)
   - Priority if discernible

3. **Create issues using GitHub CLI**:
   ```bash
   gh issue create --title "Title" --body "Description" --label "label"
   ```

4. **Report created issues**:
   - List all created issue numbers and titles
   - Note any items that couldn't be converted to issues

## Issue Format

Title: Brief, actionable description
Body:
```
## Context
[Why this is needed]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Notes
[Any relevant details]
```

## Guidelines

- Keep issues atomic - one task per issue
- Reference related issues where applicable
- Use consistent labeling
- Estimate complexity if possible (small, medium, large)
