# Task: FeedForward Pipeline Optimization (Ralph V2)

## Scope
- Optimize the pipeline to generate high-quality engineering stories.
- Modify pipeline code and prompts, not individual stories.
- ONLY DO ONE TASK AT A TIME.
- Prefer small, shippable increments.

## Environment & Permissions
You are running as an autonomous Claude Code agent via a bash loop.
You have permission to:
- Read and edit files in this repository.
- Run tests and linters.
- Update `ralph_v2/progress.txt` with each iteration.
- Make small, frequent commits.

Do NOT:
- Access files outside this repo.
- Call external services unless explicitly instructed in this document.

## Success Criteria (Strict)
The task is complete only when:
- Gestalt Score >= 4.8/5.0
- Scoping Score >= 4.5/5.0
- Per-Source Minimum >= 4.5/5.0
- All required checks below pass.
- You print `<promise>COMPLETE</promise>` in your final summary.

## Binary Checklist (Required)
Maintain `ralph_v2/criteria.json` and update each item to `true` only after
verifying it. Only emit `<promise>COMPLETE</promise>` when every item is true.
Record the evidence for each item in `ralph_v2/progress.txt`.

## Required Reading (Phase 0)
Read these before any changes:
- `ralph_v2/progress.txt`
- `ralph_v2/criteria.json`
- Latest `scripts/ralph/outputs/test_results_*.json` (if present)
- `docs/story_knowledge_base.md`
- `src/theme_extractor.py`
- `src/story_formatter.py`
- `scripts/ralph/knowledge_cache.py`
- `scripts/ralph/learned_patterns.json`
- `docs/tailwind-codebase-map.md`

## Prioritization Order
1. Pipeline-level architecture or abstractions that affect all stories.
2. Integration points (data loaders, scoping validation, knowledge cache).
3. Unknown unknowns (small spikes to de-risk).
4. Standard prompt or formatting improvements.
5. Polish and cleanup.

## Quality Standard
Treat this as a production pipeline. Avoid quick hacks and preserve clarity.
Prefer small, testable changes over large refactors.

## Quality Gates (Mandatory)
Run the pipeline test harness each iteration:
```bash
cd scripts/ralph
python3 run_pipeline_test.py
```
If you cannot run it, DO NOT COMMIT. Mark the iteration as BLOCKED in `ralph_v2/progress.txt` with the reason and stop.

If you touch non-pipeline modules, run relevant tests for those areas too.

## Hard Rules (Non-Negotiable)
- Do not edit individual story outputs.
- Do not skip scoping validation for completion.
- You must not write “awaiting test run approval.” Use BLOCKED and stop.
- Keep changes focused to a single improvement per iteration.
- If you cannot meet quality gates, mark BLOCKED and stop.

## Loop Contract
On **every** run:
1. Re-read `ralph_v2/PROMPT.md`.
2. Read `ralph_v2/progress.txt` to understand history and current state.
3. Inspect relevant parts of the codebase.
4. Plan the smallest next step that moves toward completion.
5. Execute that step (edit files, run tests, update docs).
6. Append a concise entry in `ralph_v2/progress.txt` describing:
   - What changed.
   - Test results and scores.
   - Remaining work.
7. If and only if all success criteria are met:
   - Summarize the work.
   - Print `<promise>COMPLETE</promise>` in the summary.

ONLY DO ONE TASK AT A TIME.
Prefer multiple small commits over one large commit.
