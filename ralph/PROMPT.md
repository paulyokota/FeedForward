# Task: FeedForward Roadmap (Hybrid Plan)

## Scope
- This loop is scoped to Milestone 8: Embedding-Based Story Clustering.
- Each iteration completes one issue-sized slice (not the entire milestone).
- The run should advance slice-by-slice across iterations until blocked or the milestone is complete.
- ONLY DO ONE TASK AT A TIME.
- Prefer small, shippable increments.
- Use parallelization where appropriate (e.g., run independent tasks in parallel, or batch compatible work) without expanding scope beyond the current slice.

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

## Success Criteria (Slice-Based)
A slice is complete only when:
- All requirements below are met.
- All tests pass (unit + integration, if they exist).
- No linter or type-checker errors remain.
- Any relevant docs are updated.

## Success Criteria (Loop Completion)
The Milestone 8 loop is complete only when:
- All items in `ralph/SLICE.md` are checked complete.
- You print `<promise>COMPLETE</promise>` in your final summary.

## Completion and Stop Rules
- Completion is defined per slice (single Milestone 8 issue only).
- After completing a slice, prepare the next slice and continue to the next iteration.
- The bash loop max-iterations cap is a safety net; if it triggers, stop and mark
  the iteration BLOCKED in `ralph/progress.txt` with the next steps.
- Project-level completion is a human decision; do not declare the whole project done.
- After completing a slice, stop the loop and start a new cycle only after you:
  - Update `ralph/SLICE.md` to select the next single issue.
  - Add a new "Slice Start" entry in `ralph/progress.txt` for traceability.
  - If no slices remain, mark the loop complete and exit.

## Slice Definition (Authoritative)
Use `ralph/SLICE.md` as the source of truth for the current slice. Each cycle
must select exactly one Milestone 8 issue in the "Current Slice" section and
work until it is complete. Do not add new scope outside that file without
explicit instruction.

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
3. Read `ralph/SLICE.md` and pick the next unchecked item.
4. Inspect relevant parts of the codebase.
5. Plan the smallest next step that moves toward completion.
6. Execute that step (edit files, run tests, update docs).
7. Append a new entry in `ralph/progress.txt` describing:
   - What changed.
   - Test results.
   - Remaining work.
8. If and only if all success criteria are met:
   - Summarize the work.
   - If the entire milestone is complete, print `<promise>COMPLETE</promise>`.
9. When a slice is complete:
   - Mark the issue complete in `ralph/SLICE.md`.
   - Select the next issue as "Current Slice" (or note none remain).
   - Add a new "Slice Start" entry in `ralph/progress.txt`.
   - Continue to the next iteration unless blocked.

ONLY DO ONE TASK AT A TIME.
Prefer multiple small commits over one large commit.
