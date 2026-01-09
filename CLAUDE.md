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

**Current Phase**: Story Grouping Architecture (baseline established)

Batch processing pattern (scheduled daily/weekly):

1. Fetch conversations from Intercom API (with quality filtering ~50% pass rate)
2. Extract source.url for URL context boosting
3. Theme extraction via LLM (vocabulary-guided, URL context aware)
4. Story grouping with PM review layer
5. Store themes in database with aggregation
6. Apply escalation rules (future)

**Key Architectural Decisions**:

1. **Two-Stage Classification System** (Phase 1 ✅)
   - **Stage 1**: Fast routing (<1s) with customer message only
   - **Stage 2**: Accurate analysis with full conversation context
   - Enables both real-time routing AND high-quality analytics
   - 100% high confidence on test data
   - See `docs/session/phase1-results.md` for complete results

2. **URL Context System**
   - Uses `source.url` to disambiguate product areas
   - Matches URL against 27 patterns in vocabulary
   - Boosts LLM prompt to prefer themes from that area
   - Solves three-scheduler disambiguation problem

3. **Story Grouping Pipeline** (baseline ✅)
   - PM review layer validates: "Same implementation ticket?"
   - INVEST criteria for implementation-ready groupings
   - Confidence scoring for prioritization (not auto-approval)
   - 45% group purity baseline, targeting 70%+
   - See `docs/story-grouping-architecture.md` for full design

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
# Start the frontend stack (requires two terminals)
uvicorn src.api.main:app --reload --port 8000  # Terminal 1: API
streamlit run frontend/app.py                   # Terminal 2: UI

# Then open http://localhost:8501

# Run the classification pipeline directly
python -m src.pipeline --days 7             # Last 7 days
python -m src.pipeline --days 1 --max 10    # Test with 10 conversations
python -m src.pipeline --dry-run            # No DB writes

# CLI commands
python src/cli.py themes           # List all themes
python src/cli.py trending         # Trending themes
python src/cli.py pending          # Preview pending tickets

# Tests
pytest tests/ -v
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

## Frontend Design Plugin

`frontend-design` plugin from `@anthropics/claude-code-plugins` for UI development:

- Use for Story Tracking Web App UI (board views, detail pages, forms)
- Provides design system guidance and component patterns
- Installed via: `npx claude-plugins install @anthropics/claude-code-plugins/frontend-design`

## Project Docs

- `docs/architecture.md` - System design and components
- `docs/status.md` - Current progress and next steps
- `docs/changelog.md` - What's shipped
- `docs/prompts.md` - Classification prompts and accuracy metrics
- `docs/escalation-rules.md` - Routing rules and thresholds
- `docs/story-grouping-architecture.md` - Story grouping pipeline design
- `docs/story-granularity-standard.md` - INVEST-based grouping criteria

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
