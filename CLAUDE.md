# FeedForward

LLM-powered Intercom conversation analysis pipeline for extracting product insights.

## Tech Stack

- **LLM Classification**: OpenAI (gpt-4o-mini for cost efficiency)
- **Database**: TBD (PostgreSQL or MongoDB)
- **Integrations**: Intercom API, potentially Jira/Productboard/Slack

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
# TBD - will add as project develops
```

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
