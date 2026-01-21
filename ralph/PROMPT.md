# Task: FeedForward Roadmap (Hybrid Plan)

## Scope
- Execute the roadmap tasks in milestone order (Hybrid Week 1 → Week 4).
- ONLY DO ONE TASK AT A TIME.
- Prefer small, shippable increments.

## Environment & Permissions
You are running as an autonomous Claude Code agent via a bash loop.
You have permission to:
- Read and edit files in this repository.
- Run tests and linters.
- Update `ralph/progress.txt` with each iteration.
- Make small, frequent commits.

Do NOT:
- Access files outside this repo.
- Call external services unless explicitly instructed in this document.

## Success Criteria
The task is complete only when:
- All requirements below are met.
- All tests pass (unit + integration, if they exist).
- No linter or type-checker errors remain.
- Any relevant docs are updated.
- You print `<promise>COMPLETE</promise>` in your final summary.

## Roadmap Order (Authoritative)
Use the milestones and issues below. Complete in order.

### Hybrid Week 1
- #62 fix(research): coda_page adapter fails with "no such column: name"
- #46 Implement repo sync + static codebase fallback

### Hybrid Week 2
- #53 Webapp pipeline control page + graceful stop
- #44 Wire classification-guided exploration into story creation

### Hybrid Week 3
- #54 Run summary: new stories after pipeline run
- #56 Story detail implementation context section

### Hybrid Week 4
- #55 Suggested evidence accept/reject workflow

## Quality Gates (MANDATORY)
Before committing, run ALL applicable checks for the touched area.
If you cannot run them, DO NOT COMMIT. Mark the iteration as BLOCKED in `ralph/progress.txt` with the reason.

Backend (Python):
- `pytest tests/ -v`

Webapp (Next.js):
- `npm test`
- `npm run lint`
- `npm run typecheck`

If any check fails, fix the issue before committing.

## PR Workflow Gate (MANDATORY)
After completing an issue:
1. Open a PR for the issue.
2. Trigger 5‑personality review (per process playbook).
3. Wait for a `CONVERGED` comment in the PR thread.
4. Merge the PR.

Do NOT proceed to the next issue until steps 1–4 are complete.
If you cannot open a PR or merge it, mark the iteration as BLOCKED in `ralph/progress.txt`
and stop.

PR creation requirement:
- Use `gh pr create` to open the PR.
- Include a line in your summary: `PR URL: <url>`.

## Hard Rules (Non‑Negotiable)
- You must not commit if tests were not run.
- You must not write “awaiting test run approval.” Instead, mark the iteration as BLOCKED and exit.
- If you touch only backend files, you only need the backend tests.
- If you touch webapp files, run the webapp checks.

## Process Gates (from docs/process-playbook)
- Test Gate: tests required before review.
- Functional Testing Gate for pipeline/LLM changes: capture evidence.
- Backlog Hygiene: file TODO/FIXME as issues or mark BACKLOG_FLAG.

## Loop Contract
On **every** run:
1. Re-read this `ralph/PROMPT.md`.
2. Read `ralph/progress.txt` to understand history and current state.
3. Inspect relevant parts of the codebase.
4. Plan the smallest next step that moves toward completion.
5. Execute that step (edit files, run tests, update docs).
6. Append a new entry in `ralph/progress.txt` describing:
   - What changed.
   - Test results.
   - Remaining work.
7. If and only if all success criteria are met:
   - Summarize the work.
   - Print `<promise>COMPLETE</promise>` in the summary.

ONLY DO ONE TASK AT A TIME.
Prefer multiple small commits over one large commit.
