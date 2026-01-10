# FeedForward

> **When in doubt, do it by the book.**
>
> Feeling tempted to skip a step? Don't. The Critical Path Checklist and Tech Lead Gates exist because we learned the hard way. Check the boxes. Every time.

LLM-powered Intercom conversation analysis pipeline for extracting product insights.

**Start here**: Read `PLAN.md` for full project context, methodology, and phased implementation plan.

## Tech Stack

- **Language**: Python 3.11, **Framework**: FastAPI + Streamlit
- **LLM**: OpenAI (gpt-4o-mini for cost efficiency)
- **Database**: PostgreSQL for data, **pytest** for testing
- Key commands: `pytest tests/ -v`, `uvicorn src.api.main:app --reload --port 8000`

## Project Structure

| Path                     | Purpose                     |
| ------------------------ | --------------------------- |
| `src/`                   | Core pipeline code          |
| `src/api/`               | FastAPI backend (19 routes) |
| `frontend/`              | Streamlit UI                |
| `tests/`                 | pytest test suite           |
| `config/`                | Theme vocabulary, settings  |
| `docs/`                  | Project documentation       |
| `docs/process-playbook/` | Process gates and patterns  |

## Project Context

FeedForward extracts product insights from Intercom support conversations. The pipeline classifies conversations, extracts actionable themes, groups them into implementation-ready stories, and creates Shortcut tickets.

**Current Phase**: Story Grouping Architecture (baseline established)

See `docs/architecture.md` for complete system design and `docs/status.md` for current progress.

---

## Critical Path Checklist (Every PR)

```
[ ] Tests exist (see docs/process-playbook/gates/test-gate.md)
[ ] Build passes: pytest tests/ -v
[ ] Tests pass: pytest tests/ -v
[ ] Pipeline PRs: Functional test evidence attached (see docs/process-playbook/gates/functional-testing-gate.md)
[ ] Review converged: 5-personality, 2+ rounds
[ ] Dev fixes own code (see docs/process-playbook/gates/learning-loop.md)
[ ] CONVERGED comment posted
[ ] Post-merge: Theo (Docs Agent) deployed for reflections
```

**PRs that skip tests will be reverted.**
**Pipeline PRs without functional test evidence will be blocked.**

---

## Tech Lead Gates (Self-Check)

BEFORE these actions, STOP and answer:

| Action                              | Gate Question                         | If "No"                     |
| ----------------------------------- | ------------------------------------- | --------------------------- |
| **Creating task list**              | Are tests in the list?                | Add now                     |
| **Deploying complex agent**         | Loaded required context?              | See context-loading-gate.md |
| **Deploying 2+ agents**             | Did architect define boundaries?      | Deploy architect first      |
| **Launching reviewers**             | Do tests exist for new code?          | Write tests first           |
| **After Round 1 review**            | Who wrote the code I'm fixing?        | Route to original dev       |
| **Creating PR**                     | Build + tests pass?                   | Fix before PR               |
| **PR with prompt/pipeline changes** | Functional test run and verified?     | Run test, attach evidence   |
| **Session ending**                  | BACKLOG_FLAGs to file? TODOs in code? | Review and file issues      |

---

## Agent Deployment

You (Claude Code) are the **Tech Lead**. Deploy specialists via the Task tool.

### Quick Decision Tree

| Situation                    | Action                                   |
| ---------------------------- | ---------------------------------------- |
| 2+ agents needed             | **Architect first** to define boundaries |
| <30 min, single file         | Do it yourself                           |
| Single agent, clear contract | Skip architect                           |
| Unsure?                      | Use architect                            |

**Full coordination patterns**: `docs/process-playbook/agents/coordination-patterns.md`

### The Team

**Development Agents:**

| Agent      | Role           | Domain                                    | Profile                                  |
| ---------- | -------------- | ----------------------------------------- | ---------------------------------------- |
| **Marcus** | Backend        | `src/`, database, API                     | `docs/process-playbook/agents/marcus.md` |
| **Sophia** | Frontend       | `frontend/`, `webapp/`, UI                | `docs/process-playbook/agents/sophia.md` |
| **Kai**    | AI/Prompts     | Theme extraction, classification, prompts | `docs/process-playbook/agents/kai.md`    |
| **Kenji**  | Test/QA        | Tests, edge cases                         | `docs/process-playbook/agents/kenji.md`  |
| **Priya**  | Architecture   | Upfront design + conflict resolution      | `docs/process-playbook/agents/priya.md`  |
| **Theo**   | Docs/Historian | Post-merge: docs + reflections            | `docs/process-playbook/agents/theo.md`   |

**Review Agents (5-Personality Review):**

| Agent        | Personality      | Focus                           |
| ------------ | ---------------- | ------------------------------- |
| **Reginald** | Architect        | Correctness, performance        |
| **Sanjay**   | Security Auditor | Security, validation            |
| **Quinn**    | Quality Champion | Output quality, coherence       |
| **Dmitri**   | Pragmatist       | Simplicity, YAGNI               |
| **Maya**     | Maintainer       | Clarity, future maintainability |

Agent profiles: `docs/process-playbook/review/reviewer-profiles.md`

### Agent Count Guidance

- **2-3 agents**: Easy, minimal overhead
- **4-5 agents**: Sweet spot for complex features
- **6+ agents**: Danger zone - coordination cost explodes

---

## Code Review Protocol

**5-Personality Review = 5 SEPARATE AGENTS + MINIMUM 2 ROUNDS**

```
Round 1: Launch 5 agents in parallel -> Collect issues -> Dev fixes own code
Round 2: Launch 5 agents again -> Verify fixes -> Repeat until 0 new issues
         -> Post "CONVERGED" -> Merge immediately
```

**Critical**: Use 5 separate agents, not 1 agent playing all 5 personalities.

**Full protocol**: `docs/process-playbook/review/five-personality-review.md`

---

## Key Process Gates

| Gate                     | Enforcement                                       | Reference                                                 |
| ------------------------ | ------------------------------------------------- | --------------------------------------------------------- |
| **Test Gate**            | Tests before review, no exceptions                | `docs/process-playbook/gates/test-gate.md`                |
| **Learning Loop**        | Original dev fixes their own review issues        | `docs/process-playbook/gates/learning-loop.md`            |
| **5-Personality Review** | 2+ rounds, 5 separate agents                      | `docs/process-playbook/review/five-personality-review.md` |
| **Functional Testing**   | Evidence required for pipeline/LLM PRs            | `docs/process-playbook/gates/functional-testing-gate.md`  |
| **Backlog Hygiene**      | File issues before session ends, use BACKLOG_FLAG | `docs/process-playbook/gates/backlog-hygiene.md`          |

---

## Agent Memory System

Poor man's RAG for agent learning continuity.

```
.claude/memory/
├── tech-lead/     # Tech Lead meta-decisions
├── backend/       # Backend agent experiences
├── frontend/      # Frontend patterns
└── ...
```

When deploying an agent, retrieve relevant memories:

```bash
MEMORIES=$(docs/process-playbook/memory/retrieve.sh [agent] keyword1 keyword2)
```

Schema details: `docs/process-playbook/memory/README.md`

---

## Backlog Hygiene (Session End)

**Don't lose issues at session boundaries.** Two mechanisms:

1. **Tech Lead Triggers** - Check after functional tests, review convergence, and session end:
   - Functional test revealed out-of-scope issue?
   - Fix exposed adjacent problem?
   - Workaround instead of proper fix?
   - TODO/FIXME added to code?

2. **BACKLOG_FLAG Convention** - Any agent can flag potential issues:

   ```markdown
   ## BACKLOG_FLAG

   title: [Concise issue title]
   reason: [Why this matters, how it was discovered]
   suggested_labels: [priority, type, component]
   ```

Tech Lead reviews at checkpoints, decides: file, merge with existing, or dismiss.

**Full guide**: `docs/process-playbook/gates/backlog-hygiene.md`

---

## Methodology: Validation-Driven Development (VDD)

This project follows VDD principles from `reference/UAT-Agentic-Coding-Research.md`:

- **Define acceptance criteria BEFORE writing code**
- **Write failing tests first**, then implement to pass them
- **Max 3-5 autonomous iterations** before human review
- **Measure success objectively** (accuracy thresholds, not "looks good")

VDD integrates with our process gates: Test Gate enforces tests-first, Functional Testing Gate validates LLM changes.

---

## Issue Tracking

GitHub Issues: https://github.com/paulyokota/FeedForward/issues

- Use `gh issue list` to view open issues
- Use `gh issue create` to create new issues
- Reference issues in commits: `Fixes #N` or `Closes #N`

---

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

---

## Slash Commands

| Command                       | Purpose                                            |
| ----------------------------- | -------------------------------------------------- |
| `/update-docs`                | Update all project docs after making changes       |
| `/session-end [summary]`      | End-of-session cleanup, status update, and commit  |
| `/create-issues [source]`     | Generate GitHub Issues from spec, file, or prompt  |
| `/prompt-iteration [version]` | Log new classification prompt version with metrics |

---

## Project-Specific Subagents

Auto-invoked agents that handle FeedForward-specific tasks. Claude decides when to use them based on context.

| Agent                  | Purpose                                         | Trigger                   |
| ---------------------- | ----------------------------------------------- | ------------------------- |
| `prompt-tester`        | Tests classification prompts, measures accuracy | When iterating on prompts |
| `schema-validator`     | Validates Pydantic/DB/LLM schema consistency    | When models change        |
| `escalation-validator` | Validates escalation rules and edge cases       | When rules change         |

---

## Developer Kit (Plugin)

Claudebase Developer Kit (`developer-kit@claudebase`) provides general-purpose development capabilities:

| Type     | Examples                                                                           |
| -------- | ---------------------------------------------------------------------------------- |
| Agents   | `architect`, `code-reviewer`, `database-admin`, `security-expert`, `python-expert` |
| Skills   | `analyze`, `debug`, `design`, `implement`, `test`, `security`, `quality`           |
| Commands | `/developer-kit:changelog`, `/developer-kit:reflect`, `/developer-kit:code-review` |

Use these for general development tasks. Our custom subagents above are FeedForward-specific.

---

## Frontend Design Plugin

`frontend-design` plugin from `@anthropics/claude-code-plugins` for UI development:

- Use for Story Tracking Web App UI (board views, detail pages, forms)
- Provides design system guidance and component patterns
- Installed via: `npx claude-plugins install @anthropics/claude-code-plugins/frontend-design`

---

## Key Documentation

| Document                              | Purpose                                 |
| ------------------------------------- | --------------------------------------- |
| `docs/architecture.md`                | System design and components            |
| `docs/status.md`                      | Current progress and next steps         |
| `docs/changelog.md`                   | What's shipped                          |
| `docs/story-grouping-architecture.md` | Story grouping pipeline design          |
| `docs/story-granularity-standard.md`  | INVEST-based grouping criteria          |
| `docs/process-playbook/`              | Process gates and coordination patterns |

---

## Reference Docs

- `reference/intercom-llm-guide.md` - Technical implementation guide
- `reference/UAT-Agentic-Coding-Research.md` - Development methodology
- `reference/setup.md` - Project setup approach (PSB system)

---

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
