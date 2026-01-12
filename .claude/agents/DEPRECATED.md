# DEPRECATED

This directory has been superseded by the v2 skills architecture.

**New location**: `.claude/skills/`

## Migration Mapping

| Old File (v1)             | New Location (v2)                              |
| ------------------------- | ---------------------------------------------- |
| `prompt-tester.md`        | `.claude/skills/prompt-tester/SKILL.md`        |
| `schema-validator.md`     | `.claude/skills/schema-validator/SKILL.md`     |
| `escalation-validator.md` | `.claude/skills/escalation-validator/SKILL.md` |

## Why the Change?

- **Declarative context loading** via `keywords.yaml`
- **Collocated memories** with each skill
- **Explicit triggers** in YAML frontmatter
- **Better discoverability** for the Tech Lead

## What to Do

Use skills from `.claude/skills/` - this directory will be removed in a future cleanup.

See `docs/skills-migration-diff.md` for full migration details.
