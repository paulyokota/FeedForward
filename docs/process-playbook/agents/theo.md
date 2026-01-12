# Theo - Documentation & Historian

**This profile has been migrated to the v2 skills system.**

## New Location

```
.claude/skills/theo-documentation/
├── SKILL.md      # Workflow, constraints, patterns
├── IDENTITY.md   # Philosophy, approach, lessons learned
└── context/
    └── keywords.yaml  # Declarative context loading
```

## How to Use

Load both files when deploying Theo:

- `.claude/skills/theo-documentation/SKILL.md` - Procedures and constraints
- `.claude/skills/theo-documentation/IDENTITY.md` - Personality and philosophy

The `context/keywords.yaml` specifies which project files to load based on task keywords.
