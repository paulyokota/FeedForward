# FeedForward

One Claude Code instance with direct access to data sources, doing product discovery
investigations and producing actionable stories. Tools, skills, and scripts accumulate
in `box/` as needs emerge.

**Why this approach**: See `reference/claude-in-a-box.md` for the full decision record,
including the pivot from the discovery engine, the reasoning, and the first validation test.

## What You Are

You are a Claude Code instance doing product discovery for the aero product (Tailwind).
You investigate across multiple data sources, reason about what you find, and produce
stories that are ready for a product team to act on.

Your job is not to run a pipeline. Your job is to think.

## Data Sources

| Source                     | Access Method                               | What's There                                                                                  |
| -------------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **Intercom conversations** | FeedForward PostgreSQL database (`src/db/`) | 16,000+ classified support conversations with themes, diagnostic summaries, verbatim excerpts |
| **PostHog analytics**      | PostHog MCP server                          | Product usage events, user properties, country/geo data                                       |
| **Target codebase**        | Direct file access (`../aero/`)             | The product codebase — read files, trace code, understand architecture                        |
| **Research docs**          | Local files                                 | Product docs, architecture docs, reference material                                           |

**Important**: When investigating Intercom data, verify against primary sources (actual
conversation text in `source_body` / `support_insights`). Don't rely solely on
pipeline-generated classifications — they may be incomplete or wrong.

## The Box

`box/` is where tooling accumulates. It starts nearly empty and grows as investigations
reveal the need for reusable tools, scripts, processes, and reference material.

**Principles:**

- Add tooling when a real need emerges, not speculatively
- Keep what does a good job, discard what doesn't
- Raid from the old pipeline/discovery engine code when useful, don't rebuild from scratch
- The box is the intelligence layer (what makes you good at discovery). Infrastructure
  (database, API, frontend) stays in its existing locations.

## Project Structure

| Path               | Purpose                                | Status                                                 |
| ------------------ | -------------------------------------- | ------------------------------------------------------ |
| `box/`             | Claude-in-a-Box toolset                | Active — accumulates as needs emerge                   |
| `src/`             | Conversation pipeline code             | Active infrastructure — data source for investigations |
| `src/api/`         | FastAPI backend (19 routes)            | Active infrastructure                                  |
| `src/discovery/`   | Discovery engine (13 agents, 6 stages) | Dormant — preserved, not used. Available for raiding.  |
| `webapp/`          | Next.js frontend                       | Active infrastructure                                  |
| `tests/`           | pytest test suite (~2,492 tests)       | Active for infrastructure code                         |
| `tests/discovery/` | Discovery engine tests (700+)          | Dormant — preserved, not running                       |
| `config/`          | Theme vocabulary, settings             | Active infrastructure                                  |
| `docs/`            | Project documentation                  | Active                                                 |
| `reference/`       | Decision records, methodology          | Active                                                 |

## Infrastructure

The existing FeedForward infrastructure is still active and useful. The conversation
pipeline (classification, themes, stories) produces data that investigations draw on.
The API and frontend are used to view results.

**Tech stack**: Python 3.11, FastAPI + Next.js, PostgreSQL

```bash
# Start the frontend stack (requires two terminals)
uvicorn src.api.main:app --reload --port 8000  # Terminal 1: API
cd webapp && npm run dev                        # Terminal 2: UI

# Then open http://localhost:3000

# CLI commands
python src/cli.py themes           # List all themes
python src/cli.py trending         # Trending themes
python src/cli.py pending          # Preview pending tickets
```

## When Writing Code

Most sessions will be investigation work, not code writing. But when the user asks
you to write code — new tools for the box, infrastructure changes, bug fixes — use
the existing development process:

```bash
# Tests
pytest -m "fast"               # Pure unit tests (~1,726 tests) - quick gate
pytest -m "fast or medium"     # Pre-merge gate (~2,200 tests)
pytest tests/ -v               # Full suite (~2,492 tests)
```

**Development process docs** (use when the user requests code work):

- Skills team and deployment: `.claude/skills/` (Marcus, Sophia, Kai, Kenji, Priya, Theo)
- Code review protocol: `docs/process-playbook/review/five-personality-review.md`
- Process gates: `docs/process-playbook/gates/`
- Coordination patterns: `docs/process-playbook/agents/coordination-patterns.md`
- Pipeline execution: `./scripts/dev-pipeline-run.sh` (for conversation pipeline only)

## Issue Tracking

GitHub Issues: https://github.com/paulyokota/FeedForward/issues

- Use `gh issue list` to view open issues
- Use `gh issue create` to create new issues
- Reference issues in commits: `Fixes #N` or `Closes #N`
- **Push with `git push`** (not `git push origin main`)

## After Investigations

When the user says **"update the log"**, do the following:

1. **`box/log.md`** — Add entries for this investigation: what was slow, what was
   manual, what was repeated, what worked surprisingly well, what almost didn't happen,
   what data source quirks were encountered. Include the date and investigation topic.
2. **Auto memory (`MEMORY.md`)** — Update with any durable learnings: data source
   shortcuts, codebase navigation patterns, methodology insights that will help
   future investigations. Remove anything that turned out to be wrong.

Don't wait to be asked twice. Don't over-think what's "worthy" of logging — if it
caught your attention during the investigation, write it down.

## Slash Commands

| Command                   | Purpose                                           |
| ------------------------- | ------------------------------------------------- |
| `/checkpoint`             | Four-question verification before action          |
| `/session-end [summary]`  | End-of-session cleanup, status update, and commit |
| `/create-issues [source]` | Generate GitHub Issues from spec, file, or prompt |
| `/update-docs`            | Update all project docs after making changes      |
| `/voice [message]`        | Start voice mode                                  |
| `/voice-stop`             | End voice mode                                    |

## Key Documentation

| Document                                   | Purpose                                          |
| ------------------------------------------ | ------------------------------------------------ |
| `reference/claude-in-a-box.md`             | Decision record for the Claude-in-a-Box approach |
| `reference/UAT-Agentic-Coding-Research.md` | Development methodology (VDD)                    |
| `docs/architecture.md`                     | System design and components                     |
| `docs/status.md`                           | Current progress and next steps                  |
| `docs/process-playbook/`                   | Process gates and coordination patterns          |
| `docs/tailwind-codebase-map.md`            | URL to Service mapping for the target product    |

## MCP Configuration

HTTP-type MCP servers need tokens in the `env` block of `.mcp.json`, not just `.env`:

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

<!-- agenterminal:start -->

## AgenTerminal Headless Mode

This project is configured for AgenTerminal headless agent sessions.
The agenterminal MCP server provides tools for conversation, code review,
plan review, and user interaction. Use the agenterminal-\* skills for
structured workflows.

<!-- agenterminal:end -->
