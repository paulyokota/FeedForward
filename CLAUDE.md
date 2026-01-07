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

**Current Phase**: Theme Extraction & Aggregation (Phase 4)

Batch processing pattern (scheduled daily/weekly):

1. Fetch conversations from Intercom API (with quality filtering ~50% pass rate)
2. Extract source.url for URL context boosting
3. Theme extraction via LLM (vocabulary-guided, URL context aware)
4. Store themes in database with aggregation
5. Apply escalation rules (future)
6. Generate reports (future)

**Key Architectural Decision**: URL Context System

The system now uses URL context to disambiguate product areas. When a conversation includes `source.url` (e.g., `/publisher/queue`), the system:

- Matches URL against 27 patterns in vocabulary
- Maps to specific product area (e.g., Legacy Publisher)
- Boosts LLM prompt to prefer themes from that area
- Solves three-scheduler disambiguation problem

See `docs/architecture.md` for complete system design and `reference/intercom-llm-guide.md` for implementation specs.

## Issue Tracking

GitHub Issues: https://github.com/paulyokota/FeedForward/issues

- Use `gh issue list` to view open issues
- Use `gh issue create` to create new issues
- Reference issues in commits: `Fixes #N` or `Closes #N`

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

| Command                       | Purpose                                            |
| ----------------------------- | -------------------------------------------------- |
| `/update-docs`                | Update all project docs after making changes       |
| `/session-end [summary]`      | End-of-session cleanup, status update, and commit  |
| `/create-issues [source]`     | Generate GitHub Issues from spec, file, or prompt  |
| `/prompt-iteration [version]` | Log new classification prompt version with metrics |

## Subagents

Auto-invoked agents that handle specialized tasks. Claude decides when to use them based on context.

| Agent                  | Purpose                                         | Trigger                   |
| ---------------------- | ----------------------------------------------- | ------------------------- |
| `prompt-tester`        | Tests classification prompts, measures accuracy | When iterating on prompts |
| `schema-validator`     | Validates Pydantic/DB/LLM schema consistency    | When models change        |
| `escalation-validator` | Validates escalation rules and edge cases       | When rules change         |

## Developer Kit (Plugin)

Claudebase Developer Kit (`developer-kit@claudebase`) provides general-purpose development capabilities:

| Type     | Examples                                                                           |
| -------- | ---------------------------------------------------------------------------------- |
| Agents   | `architect`, `code-reviewer`, `database-admin`, `security-expert`, `python-expert` |
| Skills   | `analyze`, `debug`, `design`, `implement`, `test`, `security`, `quality`           |
| Commands | `/developer-kit:changelog`, `/developer-kit:reflect`, `/developer-kit:code-review` |

Use these for general development tasks. Our custom subagents above are FeedForward-specific.

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

## MCP Configuration

HTTP-type MCP servers (like Intercom) need tokens in the `env` block of `.mcp.json`, not just `.env`:

```json
{
  "mcpServers": {
    "intercom": {
      "type": "http",
      "url": "https://mcp.intercom.com/mcp",
      "headers": {
        "Authorization": "Bearer ${INTERCOM_ACCESS_TOKEN}"
      },
      "env": {
        "INTERCOM_ACCESS_TOKEN": "your_token_here"
      }
    }
  }
}
```

After updating `.mcp.json`, restart Claude Code for changes to take effect.
