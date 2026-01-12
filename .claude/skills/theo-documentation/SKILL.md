---
name: documentation
identity: ./IDENTITY.md
triggers:
  keywords:
    - documentation
    - docs
    - readme
    - changelog
    - reflection
    - session
    - history
    - update docs
  file_patterns:
    - docs/**/*.md
    - README.md
    - CHANGELOG.md
dependencies:
  tools:
    - Read
    - Write
---

# Documentation & Historian Skill

Maintain project documentation, capture learnings, and preserve knowledge across sessions.

## Workflow

### Phase 1: Understand Context

1. **Identify Documentation Type**
   - Status update (`docs/status.md`)
   - Changelog entry (`docs/changelog.md`)
   - Architecture doc (`docs/architecture.md`, `docs/*-architecture.md`)
   - Session summary (`docs/session/`)
   - Agent lessons learned (agent profiles)
   - README or guide

2. **Load Existing Documentation**
   - Read current state of relevant docs
   - Check for consistency with codebase
   - Identify what's outdated or missing

3. **Gather Information**
   - What was done in this session/PR?
   - What was learned?
   - What changed in the implementation vs design?
   - What patterns emerged?

### Phase 2: Extract Insights

1. **Identify Learnings**
   - What worked well?
   - What didn't work?
   - What would we do differently next time?
   - What edge cases were discovered?
   - What patterns can be reused?

2. **Update vs Create Decision**
   - Is there existing documentation to update?
   - Would a new doc be clearer than updating existing?
   - Default: update existing docs first

3. **Extract Patterns**
   - Turn specific incidents into general principles
   - Identify reusable solutions
   - Note anti-patterns to avoid

### Phase 3: Document

#### For Status Updates

1. **Update `docs/status.md`**
   - Current phase and progress
   - What's complete, what's in progress
   - Next steps
   - Blockers or open questions

#### For Changelog

1. **Update `docs/changelog.md`**
   - Use consistent format (Added, Changed, Fixed, etc.)
   - Group related changes
   - Include version/date
   - Link to relevant PRs or issues

#### For Architecture Docs

1. **Sync Docs with Implementation**
   - Does the doc reflect current code?
   - Update diagrams if needed
   - Document design decisions made during implementation
   - Note deviations from original design with rationale

#### For Session Summaries

1. **Create/Update Session Notes**
   - What was accomplished
   - What was learned
   - What issues were filed
   - What's next

#### For Agent Lessons

1. **Update Agent Profiles**
   - Add to "Lessons Learned" section
   - Include date and context
   - Make it actionable for future sessions
   - Format: `- YYYY-MM-DD: [Lesson description]`

### Phase 4: Review for Quality

1. **Consistency Check**
   - Formatting matches existing docs
   - Terminology is consistent
   - Cross-references are valid
   - No contradictions between docs

2. **Clarity Check**
   - Is it scannable?
   - Are examples clear?
   - Is jargon explained?
   - Would a new contributor understand?

3. **Completeness Check**
   - Are all questions answered?
   - Are there dangling references?
   - Is context sufficient?

## Success Criteria

Before claiming completion:

- [ ] `docs/status.md` reflects current state
- [ ] `docs/changelog.md` updated for shipped work
- [ ] Architecture docs match implementation
- [ ] Agent profiles updated with lessons learned
- [ ] No stale or contradictory documentation
- [ ] Formatting consistent with existing docs
- [ ] Cross-references are valid

## Constraints

- **DO NOT** modify production code (only `docs/` and related)
- **DO NOT** create new documentation unless requested or clearly needed
- **ALWAYS** check if existing docs need updating before creating new ones
- **ALWAYS** update agent profiles with lessons learned
- **ALWAYS** use consistent formatting

## Key Files & Formats

| File                           | Purpose                | Format                  |
| ------------------------------ | ---------------------- | ----------------------- |
| `docs/status.md`               | Current project state  | Structured sections     |
| `docs/changelog.md`            | What's shipped         | Keep-a-Changelog format |
| `docs/architecture.md`         | System design          | Components, data flow   |
| `docs/session/last-session.md` | Recent work summary    | Narrative + next steps  |
| Agent profiles                 | Agent-specific lessons | Lessons Learned section |

### Changelog Format

```markdown
## [Unreleased]

### Added

- New feature description

### Changed

- What changed and why

### Fixed

- Bug fix description

### Security

- Security improvement

## [Version] - YYYY-MM-DD

[Previous release notes]
```

### Status Format

```markdown
## Current Phase

[Phase name and description]

## Progress

### Complete ✅

- [Feature/milestone]

### In Progress 🚧

- [Active work]

### Planned 📋

- [Next steps]

## Blockers

[Any blockers or open questions]
```

### Lesson Format

```markdown
## Lessons Learned

- 2026-01-12: [Specific lesson with context and actionable insight]
- 2026-01-09: [Previous lesson]
```

## Common Pitfalls

- **Creating instead of updating**: Check existing docs first, prefer updates
- **Too verbose**: Keep docs focused and scannable, use headers and lists
- **Missing patterns**: Extract reusable insights from one-off fixes
- **Stale docs**: Update docs when code changes, keep them in sync
- **Missing context**: Future readers need to know why, not just what

## Documentation Patterns

### For Post-Merge Reflections

1. Review what was merged
2. Read PR comments and review feedback
3. Extract patterns from implementation decisions
4. Update relevant architecture docs
5. Add lessons to agent profiles
6. Update status and changelog

### For Session Summaries

1. List major accomplishments
2. Capture key decisions made
3. Note issues filed or TODOs created
4. Identify next session priorities
5. Link to relevant PRs or branches

### For Architecture Updates

1. Read implementation code
2. Compare with architecture doc
3. Update doc to match reality
4. Document why implementation differed from design (if applicable)
5. Update diagrams if needed

## If Blocked

If you cannot proceed:

1. State what documentation you're trying to create/update
2. Explain what information is missing or unclear
3. Share what you've already reviewed
4. Ask the Tech Lead for clarification
