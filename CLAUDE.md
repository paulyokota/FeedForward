# FeedForward

LLM-powered Intercom conversation analysis pipeline for extracting product insights.

**Start here**: Read `PLAN.md` for full project context, methodology, and phased implementation plan.

## Methodology: Validation-Driven Development (VDD)

This project follows VDD principles from `reference/UAT-Agentic-Coding-Research.md`:
- **Define acceptance criteria BEFORE writing code**
- **Write failing tests first**, then implement to pass them
- **Max 3-5 autonomous iterations** before human review
- **Measure success objectively** (accuracy thresholds, not "looks good")

## Tech Stack

- **LLM Classification**: OpenAI (gpt-4o-mini for cost efficiency)
- **Database**: PostgreSQL (structured output, SQL aggregation for reporting)
- **Integrations**: Intercom API, Shortcut (issue tracking), Slack (alerts)

## Architecture

Batch processing pattern (scheduled daily/weekly):
1. Fetch conversations from Intercom API
2. Classify via LLM (issue type, priority, sentiment, churn risk)
3. Store insights in database
4. Apply escalation rules
5. Generate reports

See `reference/intercom-llm-guide.md` for detailed implementation specs.

## Development Constraints

- Define acceptance criteria before implementing features
- Limit autonomous iteration (3-5 cycles max before human review)
- Be explicit about non-functional requirements (no implicit assumptions)
- Never push directly to `main` - use feature branches and PRs

## Commands

```bash
# TBD - build/test commands will be added as project develops
```

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/update-docs` | Update all project docs after making changes |
| `/session-end [summary]` | End-of-session cleanup, status update, and commit |
| `/create-issues [source]` | Generate GitHub issues from spec, file, or prompt |
| `/prompt-iteration [version]` | Log new classification prompt version with metrics |

## Subagents

Auto-invoked agents that handle specialized tasks. Claude decides when to use them based on context.

| Agent | Purpose | Trigger |
|-------|---------|---------|
| `changelog` | Updates docs/changelog.md with user-facing entries | After features complete |
| `retro` | Post-session retrospective, captures learnings | After significant sessions |
| `prompt-tester` | Tests classification prompts, measures accuracy | When iterating on prompts |
| `schema-validator` | Validates Pydantic/DB/LLM schema consistency | When models change |
| `escalation-validator` | Validates escalation rules and edge cases | When rules change |

## Project Docs

- `docs/architecture.md` - System design and components
- `docs/status.md` - Current progress and next steps
- `docs/changelog.md` - What's shipped
- `docs/prompts.md` - Classification prompts and accuracy metrics
- `docs/escalation-rules.md` - Routing rules and thresholds

## Reference Docs

- `reference/intercom-llm-guide.md` - Technical implementation guide
- `reference/UAT-Agentic-Coding-Research.md` - Development methodology
- `reference/setup.md` - Project setup approach (PSB system)
