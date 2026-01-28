# FeedForward

> **When in doubt, do it by the book.**
>
> Feeling tempted to skip a step? Don't. The Critical Path Checklist and Tech Lead Gates exist because we learned the hard way. Check the boxes. Every time.

LLM-powered Intercom conversation analysis pipeline for extracting product insights.

**Start here**: Read `PLAN.md` for full project context, methodology, and phased implementation plan.

## Tech Stack

- **Language**: Python 3.11, **Framework**: FastAPI + Next.js
- **LLM**: OpenAI (gpt-4o-mini for cost efficiency)
- **Database**: PostgreSQL for data, **pytest** for testing
- Key commands: `pytest tests/ -v`, `uvicorn src.api.main:app --reload --port 8000`

## Project Structure

| Path                     | Purpose                     |
| ------------------------ | --------------------------- |
| `src/`                   | Core pipeline code          |
| `src/api/`               | FastAPI backend (19 routes) |
| `webapp/`                | Next.js frontend            |
| `tests/`                 | pytest test suite           |
| `config/`                | Theme vocabulary, settings  |
| `docs/`                  | Project documentation       |
| `docs/process-playbook/` | Process gates and patterns  |

## Project Context

FeedForward extracts product insights from Intercom support conversations. The pipeline classifies conversations, extracts actionable themes, groups them into implementation-ready stories, and creates Shortcut tickets.

**Current Phase**: Story Grouping Architecture (baseline established)

See `docs/architecture.md` for complete system design and `docs/status.md` for current progress.

### Smart Digest (Issue #144)

Theme extraction now receives **full conversation context** instead of truncated snippets. Key fields:

| Field                | Location                                 | Purpose                                    |
| -------------------- | ---------------------------------------- | ------------------------------------------ |
| `full_conversation`  | `conversations.support_insights` (JSONB) | Complete conversation text passed to LLM   |
| `diagnostic_summary` | `themes` table                           | LLM-generated issue summary with context   |
| `key_excerpts`       | `themes` table (JSONB)                   | Verbatim quotes with relevance annotations |

PM Review uses `diagnostic_summary` for story validation (previously used `source_body[:500]`).

---

## Critical Path Checklist (Every PR)

```
[ ] Tests exist (see docs/process-playbook/gates/test-gate.md)
[ ] Build passes: pytest tests/ -v
[ ] Tests pass: pytest tests/ -v
[ ] Cross-component PRs: Integration test verifies full data path (see docs/process-playbook/gates/integration-testing-gate.md)
[ ] Pipeline PRs: Functional test evidence attached (see docs/process-playbook/gates/functional-testing-gate.md)
[ ] Review converged: 5-personality, 2+ rounds
[ ] Dev fixes own code (see docs/process-playbook/gates/learning-loop.md)
[ ] CONVERGED comment posted
[ ] Post-merge: Theo (Docs Skill) deployed for reflections
```

**PRs that skip tests will be reverted.**
**Pipeline PRs without functional test evidence will be blocked.**

---

## Tech Lead Gates (Self-Check)

BEFORE these actions, STOP and answer:

| Action                                     | Gate Question                         | If "No"                     |
| ------------------------------------------ | ------------------------------------- | --------------------------- |
| **Creating task list**                     | Are tests in the list?                | Add now                     |
| **Deploying complex agent**                | Loaded required context?              | See context-loading-gate.md |
| **Deploying 2+ agents**                    | Did architect define boundaries?      | Deploy architect first      |
| **Launching reviewers**                    | Do tests exist for new code?          | Write tests first           |
| **After Round 1 review**                   | Who wrote the code I'm fixing?        | Route to original dev       |
| **Creating PR**                            | Build + tests pass?                   | Fix before PR               |
| **PR with prompt/pipeline changes**        | Functional test run and verified?     | Run test, attach evidence   |
| **Feature with cross-component data flow** | Integration test verifies full path?  | Add integration test first  |
| **Executing architect output**             | Is it deleting code not in scope?     | Flag for user approval      |
| **Session ending**                         | BACKLOG_FLAGs to file? TODOs in code? | Review and file issues      |
| **Running pipeline**                       | Pre-flight passed? (see below)        | Run pre-flight first        |

### Pipeline Execution (DEV MODE)

**Pipeline runs are EXPENSIVE.** Use the dev-mode script which handles all safety checks:

```bash
# DEV MODE: Use this script - it does pre-flight checks AND auto-cleanup
./scripts/dev-pipeline-run.sh

# Options:
./scripts/dev-pipeline-run.sh --days 7        # Process 7 days of conversations
./scripts/dev-pipeline-run.sh --skip-cleanup  # Skip cleanup (NOT recommended in dev)
./scripts/dev-pipeline-run.sh --help          # Show all options
```

**The script automatically:**

1. Checks server is running with current code
2. Verifies no active pipeline run
3. Cleans stale data (orphans, themes, stories)
4. Triggers full pipeline via API
5. Monitors progress until completion

**DO NOT run pipeline any other way during development.**

**Lesson learned (2026-01-23):** Many wasted runs over 2 days from wrong commands and stale code.

---

## Skill Deployment

You (Claude Code) are the **Tech Lead**. Deploy skills via the Task tool.

### Quick Decision Tree

| Situation                    | Action                                   |
| ---------------------------- | ---------------------------------------- |
| 2+ skills needed             | **Architect first** to define boundaries |
| <30 min, single file         | Do it yourself                           |
| Single skill, clear contract | Skip architect                           |
| Unsure?                      | Use architect                            |

**Full coordination patterns**: `docs/process-playbook/agents/coordination-patterns.md`

### The Team

**Development Skills:**

| Skill                    | Identity   | Domain                                    | Location                                 |
| ------------------------ | ---------- | ----------------------------------------- | ---------------------------------------- |
| `marcus-backend`         | **Marcus** | `src/`, database, API                     | `.claude/skills/marcus-backend/`         |
| `sophia-frontend`        | **Sophia** | `webapp/`, UI                             | `.claude/skills/sophia-frontend/`        |
| `kai-prompt-engineering` | **Kai**    | Theme extraction, classification, prompts | `.claude/skills/kai-prompt-engineering/` |
| `kenji-testing`          | **Kenji**  | Tests, edge cases                         | `.claude/skills/kenji-testing/`          |
| `priya-architecture`     | **Priya**  | Upfront design + conflict resolution      | `.claude/skills/priya-architecture/`     |
| `theo-documentation`     | **Theo**   | Post-merge: docs + reflections            | `.claude/skills/theo-documentation/`     |

**Review Skill (5-Personality):**

| Personality  | Focus                           | Location                                            |
| ------------ | ------------------------------- | --------------------------------------------------- |
| **Reginald** | Correctness, performance        | `.claude/skills/review-5personality/personalities/` |
| **Sanjay**   | Security, validation            | `.claude/skills/review-5personality/personalities/` |
| **Quinn**    | Output quality, coherence       | `.claude/skills/review-5personality/personalities/` |
| **Dmitri**   | Simplicity, YAGNI               | `.claude/skills/review-5personality/personalities/` |
| **Maya**     | Clarity, future maintainability | `.claude/skills/review-5personality/personalities/` |

Review protocol: `.claude/skills/review-5personality/SKILL.md`

### Skill Count Guidance

- **2-3 skills**: Easy, minimal overhead
- **4-5 skills**: Sweet spot for complex features
- **6+ skills**: Danger zone - coordination cost explodes

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
| **Integration Testing**  | Cross-component features need full-path tests     | `docs/process-playbook/gates/integration-testing-gate.md` |
| **Learning Loop**        | Original dev fixes their own review issues        | `docs/process-playbook/gates/learning-loop.md`            |
| **5-Personality Review** | 2+ rounds, 5 separate agents                      | `docs/process-playbook/review/five-personality-review.md` |
| **Functional Testing**   | Evidence required for pipeline/LLM PRs            | `docs/process-playbook/gates/functional-testing-gate.md`  |
| **Backlog Hygiene**      | File issues before session ends, use BACKLOG_FLAG | `docs/process-playbook/gates/backlog-hygiene.md`          |

---

## Skill Memory System

Memories are collocated with each skill for portability.

```
.claude/skills/
├── kai-prompt-engineering/
│   ├── SKILL.md           # Procedures
│   ├── IDENTITY.md        # Personality + lessons learned
│   ├── memories/          # Skill-specific learnings
│   └── context/
│       └── keywords.yaml  # Declarative context loading
└── ...
```

Context is loaded declaratively via `keywords.yaml` - no manual retrieval needed.

Legacy location (deprecated): `.claude/memory/`

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
cd webapp && npm run dev                        # Terminal 2: UI

# Then open http://localhost:3000

# Classification ONLY (NOT the full pipeline - use API for full runs)
# See "Pipeline Pre-Flight" section before running anything
python -m src.classification_pipeline --days 7              # Last 7 days
python -m src.classification_pipeline --days 1 --max 10     # Test with 10 conversations
python -m src.classification_pipeline --dry-run             # No DB writes
python -m src.classification_pipeline --async --concurrency 20  # Async mode (faster)

# FULL PIPELINE (classification → embedding → themes → stories)
# Use the API endpoint - see "Pipeline Pre-Flight" section first
curl -X POST "http://localhost:8000/api/pipeline/run" -H "Content-Type: application/json"

# CLI commands
python src/cli.py themes           # List all themes
python src/cli.py trending         # Trending themes
python src/cli.py pending          # Preview pending tickets

# Tests
pytest tests/ -v
```

---

## Slash Commands

| Command                       | Purpose                                                              |
| ----------------------------- | -------------------------------------------------------------------- |
| `/checkpoint`                 | **USE OFTEN** - Four-question verification before action (see below) |
| `/pipeline-monitor [run_id]`  | Spawn Haiku agent to monitor pipeline, alert on errors               |
| `/update-docs`                | Update all project docs after making changes                         |
| `/session-end [summary]`      | End-of-session cleanup, status update, and commit                    |
| `/create-issues [source]`     | Generate GitHub Issues from spec, file, or prompt                    |
| `/prompt-iteration [version]` | Log new classification prompt version with metrics                   |
| `/voice [message]`            | Start voice mode with relaxed silence detection                      |
| `/voice-stop`                 | End voice mode and return to text                                    |

### /checkpoint - The Four Questions

Invoke `/checkpoint` at task start, after compaction, or when sensing drift. Forces verification before action.

| Question       | What to answer                                           |
| -------------- | -------------------------------------------------------- |
| **PERMISSION** | Did user ask to DO or UNDERSTAND? If unclear, ask.       |
| **VERIFIED**   | What am I assuming? Have I checked schema/callers/files? |
| **VALUE**      | Does this help the GOAL or just move a METRIC?           |
| **RECOVERY**   | If wrong, can we recover? If not, confirm with user.     |

**This skill exists because of 17+ logged violations.** See `.claude/skills/checkpoint/SKILL.md` for full protocol.

---

## Project-Specific Skills

Auto-invoked skills that handle FeedForward-specific tasks. Claude decides when to use them based on context.

| Skill                  | Purpose                                            | Location                               |
| ---------------------- | -------------------------------------------------- | -------------------------------------- |
| `checkpoint`           | **User-invoked** - Four-question verification gate | `.claude/skills/checkpoint/`           |
| `prompt-tester`        | Tests classification prompts, measures accuracy    | `.claude/skills/prompt-tester/`        |
| `schema-validator`     | Validates Pydantic/DB/LLM schema consistency       | `.claude/skills/schema-validator/`     |
| `escalation-validator` | Validates escalation rules and edge cases          | `.claude/skills/escalation-validator/` |

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
| `docs/tailwind-codebase-map.md`       | URL → Service mapping for ticket triage |
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
