---
name: issue-runner
description: Process a single GitHub issue through the full dev lifecycle. When running under the orchestrator, you receive one issue at a time with a fresh session.
---

# Issue Runner

Process a single GitHub issue through the full development lifecycle: branch, plan, implement, test, review, PR, and merge.

## issue-progress.json

Create or update `issue-progress.json` at the path in `$AGENTERMINAL_PROGRESS_PATH` (absolute). Falls back to `./issue-progress.json` if the env var is not set. The orchestrator reads this file to determine success or failure, so **you must update it after every phase transition**.

```json
{
  "issues": {
    "<number>": {
      "phase": "pending",
      "error": null,
      "updatedAt": null
    }
  }
}
```

Valid phases: `pending`, `branched`, `planned`, `implemented`, `tested`, `reviewed`, `merged`, `complete`, `skipped`.

## Per-Issue Workflow

### Phase 1: Read & Branch

1. Read issue details: `gh issue view <number>`
2. Verify you are on the correct branch (`git branch`). The orchestrator pre-creates your branch via git worktree. Do not run `git checkout -b`.
   - If the env var `$AGENTERMINAL_PROGRESS_PATH` is **not** set, you are running standalone — create a branch yourself: `git checkout -b fix/<number>-<slug>` (prefix `fix/<number>-`, slug: lowercase, non-alphanumeric → hyphens, max 40 chars).
3. Update issue-progress.json: `phase: "branched"`

### Phase 2: Plan

1. Analyze the issue and the codebase
2. Write a plan file: `plan-issue-<number>.md`
3. Submit for plan review (the tool blocks until review completes):

```
agenterminal.request {
  type: "plan_review",
  description: "Implementation plan for issue #<number>: <title>",
  plan_path: "plan-issue-<number>.md",
  auto_dispatch: true
}
```

4. The tool returns `{ "review_approved": true/false, "feedback": "..." }`.
5. If `review_approved` is false: revise the plan based on feedback, then submit a **new** `agenterminal.request` with the same `conversation_id` and `auto_dispatch: true`.
6. Max 3 review rounds
7. When `review_approved` is true, update issue-progress.json: `phase: "planned"`
8. Do NOT use `agenterminal.conversation` tools — review results are returned inline.

### Phase 3: Implement

1. Implement the fix according to the approved plan
2. Update issue-progress.json: `phase: "implemented"`

### Phase 4: Test

1. Run the project's test suite (detect test command from package.json scripts, Makefile, etc.)
2. If tests fail, attempt to fix (max 2 attempts)
3. If tests pass, update issue-progress.json: `phase: "tested"`

### Phase 5: Code Review

1. Commit all changes with a descriptive message referencing the issue number
2. Submit for code review (the tool blocks until review completes):

```
agenterminal.request {
  type: "code_review",
  description: "Fix for issue #<number>: <title>",
  ref: "main..HEAD",
  auto_dispatch: true
}
```

3. The tool returns `{ "review_approved": true/false, "feedback": "..." }`.
4. If `review_approved` is false: fix the MUST-FIX items, commit, then submit a **new** `agenterminal.request` with the same `conversation_id` and `auto_dispatch: true`.
5. Max 3 review rounds
6. When `review_approved` is true, update issue-progress.json: `phase: "reviewed"`
7. Do NOT use `agenterminal.conversation` tools — review results are returned inline.

### Phase 6: Create PR & Merge

1. Push branch: `git push -u origin HEAD`
2. Create PR: `gh pr create --title "Fix #<number>: <title>" --body "<description>"`
3. Poll for CI completion (check every 30s, max 10 min):

```
agenterminal.github.poll { pr_number: <pr_number> }
```

4. Merge with gated tool:

```
agenterminal.merge {
  conversation_id: "<reviewConversationId>",
  pr_number: <pr_number>,
  merge_method: "squash"
}
```

5. If merge blocked, address blockers (update branch, wait for CI, etc.)
6. Update issue-progress.json: `phase: "merged"`
7. If not running under the orchestrator, switch back to main: `git checkout main && git pull`

### Phase 7: Cleanup

1. Close the issue if not auto-closed: `gh issue close <number> --comment "Fixed in PR #<pr>"`
2. Delete the plan file: `rm -f plan-issue-<number>.md` (development artifact, not a deliverable)
3. Update issue-progress.json: `phase: "complete"`

## Error Handling

### Retry Limits

- Plan review rejection: max 3 attempts, then set `phase: "skipped"`, `error: "plan_rejected"`
- Test failure: max 2 fix attempts, then set `phase: "skipped"`, `error: "tests_failing"`
- Code review rejection: max 3 revision rounds, then set `phase: "skipped"`, `error: "review_rejected"`
- Merge failure: 1 retry after addressing blockers, then set `phase: "skipped"`, `error: "merge_failed"`

### Recovery

- On any unrecoverable error, update `issue-progress.json` with `phase: "skipped"` and `error: "<reason>"`
- If not running under the orchestrator (no `$AGENTERMINAL_PROGRESS_PATH`), switch back to main branch: `git checkout main && git pull`

## Tips

- Always ensure you are on the correct branch before making changes
- Commit frequently with descriptive messages referencing the issue number
- Do NOT commit plan files (`plan-issue-*.md`) — they are gitignored development artifacts
- If the issue is ambiguous, use `agenterminal.ask` to clarify with the user before planning
- For the CI polling in Phase 6, use `agenterminal.github.poll` to also catch any new review comments that arrive during the wait
- Update issue-progress.json after EVERY phase transition — the orchestrator depends on it
