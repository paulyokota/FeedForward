---
description: Update all project documentation with recent changes
---

# Update Documentation

Review recent changes and update project documentation accordingly.

## Steps

1. **Check what changed**: Review `git diff` and recent commits to understand modifications

2. **Update docs/architecture.md** if:
   - New components were added
   - Data flow changed
   - Dependencies were added/removed

3. **Update docs/status.md**:
   - Mark completed items as done
   - Add any new blockers
   - Update "What's Next" section

4. **Update docs/changelog.md**:
   - Use `/developer-kit:changelog` to generate entries from git history
   - Review generated entries for accuracy
   - Add under [Unreleased] section with proper categorization (Added/Changed/Fixed/Removed)

5. **Update docs/prompts.md** if:
   - Classification prompts were modified
   - New accuracy metrics are available
   - Use `prompt-tester` agent to validate changes

6. **Update docs/escalation-rules.md** if:
   - Rules were added or modified
   - Thresholds changed
   - Use `escalation-validator` agent to check consistency

7. **Update CLAUDE.md** if:
   - Major architectural decisions were made
   - New commands or workflows were added

Keep documentation concise and consistent with existing style.

## Related Tools

- `/developer-kit:changelog` - Generates changelog from git history
- `prompt-tester` agent - Validates prompt changes against test data
- `escalation-validator` agent - Validates rule consistency
- `schema-validator` agent - Checks Pydantic/DB/LLM schema alignment
