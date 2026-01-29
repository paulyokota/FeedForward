---
name: process-primer
triggers:
  slash_command: /process-primer
dependencies:
  tools:
    - Read
---

# Process Primer Skill

Quickly rebuild context on the gold standard philosophy and process playbook. Use at session start or after compaction when you need to remember "how we do things here."

## When to Use

Invoke `/process-primer` when:

- Starting a new session and need project context
- After compaction recovery
- Before deploying agents or starting multi-step work
- When uncertain about process gates or coordination patterns

## Core Philosophies

### Gold Standard Philosophy

**Core principle**: The gold standard document is the source of truth. Evaluators are proxies that should measure what the gold standard defines, not substitute heuristics.

**Goodhart's Law**: When a measure becomes a target, it ceases to be a good measure.

**Key behaviors**:

- Define success criteria BEFORE implementation
- When proxies fail, fix the proxy—never lower the bar
- Watch for gaming: keyword matching instead of purpose detection
- Separate what samples show (evidence) from what we infer (extrapolation)

**Warning signs of drift**:

1. Evaluator diverges from gold standard definition
2. Metrics improve but quality doesn't
3. Thresholds quietly lower without rationale
4. Conditional logic hides failures

### Process Playbook Philosophy

**Core principles**:

- Prevention beats resolution (vague specs cause conflicts)
- 4-5 agents is the sweet spot (6+ explodes in complexity)
- Sessions have amnesia (undocumented issues are lost)
- Learning loops matter (agents must fix their own mistakes)

## Six Process Gates

| Gate                    | Rule                                        | Enforcement                    |
| ----------------------- | ------------------------------------------- | ------------------------------ |
| **Test Gate**           | Tests BEFORE review                         | PRs without tests get reverted |
| **Integration Testing** | Cross-component flows need full-path tests  | Mocks can hide real bugs       |
| **Learning Loop**       | Original dev fixes their own issues         | Route via Session Touch Log    |
| **Functional Testing**  | LLM/pipeline PRs need real output evidence  | Quinn can flag BLOCKING        |
| **Context Loading**     | Complex agents declare context requirements | Load via keywords.yaml         |
| **Backlog Hygiene**     | Capture issues before session ends          | Use BACKLOG_FLAG convention    |

## Five-Personality Review

**5 SEPARATE agents, minimum 2 rounds**:

| Reviewer | Focus                                                         |
| -------- | ------------------------------------------------------------- |
| Reginald | Correctness, performance, integration                         |
| Sanjay   | Security, OWASP, validation                                   |
| Quinn    | Output quality, coherence (can flag FUNCTIONAL_TEST_REQUIRED) |
| Dmitri   | Simplicity, YAGNI, no bloat                                   |
| Maya     | Maintainability, clarity, future devs                         |

**Flow**: Round 1 → Route issues to original dev → Dev fixes → Round 2 → Repeat until 0 new issues → Post "CONVERGED" → Merge

## Agent Coordination

**Default pattern**: Architect-first for multi-agent work

1. Deploy architect to define boundaries and contracts
2. Deploy implementers in parallel with those specs
3. Test agent (mandatory)
4. 5-personality review (2+ rounds)
5. Docs agent for reflections

**Architect-skip criteria** (only times you can skip):

- Single-agent task
- Contract already crystal clear
- Identical to previous task
- Time-critical hotfix

## Tech Lead Gates (Self-Check)

| Action               | Gate Question                        |
| -------------------- | ------------------------------------ |
| Creating task list   | Are tests in the list?               |
| Deploying 2+ agents  | Did architect define boundaries?     |
| Launching reviewers  | Do tests exist?                      |
| After Round 1 review | Who wrote the code I'm fixing?       |
| Creating PR          | Build + tests pass?                  |
| Pipeline PR          | Functional test evidence attached?   |
| Cross-component flow | Integration test verifies full path? |
| Session ending       | BACKLOG_FLAGs filed? TODOs reviewed? |

## Key Files

**Philosophy**:

- `docs/process-playbook/philosophy/gold-standard-alignment.md`
- `docs/process-playbook/philosophy/proxy-metrics.md`

**Gates**:

- `docs/process-playbook/gates/test-gate.md`
- `docs/process-playbook/gates/integration-testing-gate.md`
- `docs/process-playbook/gates/learning-loop.md`
- `docs/process-playbook/gates/functional-testing-gate.md`
- `docs/process-playbook/gates/context-loading-gate.md`
- `docs/process-playbook/gates/backlog-hygiene.md`

**Coordination**:

- `docs/process-playbook/agents/coordination-patterns.md`
- `docs/process-playbook/review/five-personality-review.md`

## Procedure

When this skill is invoked, you MUST read the following files to load full context:

### Required Reads (Always)

Use the Read tool to load these files in parallel:

1. `docs/process-playbook/philosophy/gold-standard-alignment.md` - Core principle
2. `docs/process-playbook/philosophy/proxy-metrics.md` - Goodhart's Law guidance
3. `docs/process-playbook/gates/test-gate.md` - Test requirements
4. `docs/process-playbook/review/five-personality-review.md` - Review process
5. `docs/process-playbook/agents/coordination-patterns.md` - Agent coordination

### After Reading

Confirm context was loaded by stating:

```
Process Primer: Full context loaded.

Files read:
- gold-standard-alignment.md ✓
- proxy-metrics.md ✓
- test-gate.md ✓
- five-personality-review.md ✓
- coordination-patterns.md ✓

Key reminders:
1. GOLD STANDARD: Define success first, measure against it, never lower the bar
2. TESTS: Mandatory before review, no exceptions
3. MULTI-AGENT: Architect-first unless skip criteria met
4. REVIEW: 5 separate agents, minimum 2 rounds, route fixes to original dev
5. BACKLOG: Capture issues before session ends

Ready to proceed. What are we working on?
```

### Optional Deep Dives

If the user mentions specific topics, also read:

| Topic mentioned                    | Read additionally                                                                                           |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| gate, gates, enforcement           | `docs/process-playbook/gates/integration-testing-gate.md`, `learning-loop.md`, `functional-testing-gate.md` |
| backlog, issues, session end       | `docs/process-playbook/gates/backlog-hygiene.md`                                                            |
| baseline, ground truth, evaluation | `scripts/signature_ground_truth.py`, `scripts/baseline_evaluation.py`                                       |
| memory, learning                   | `docs/process-playbook/agents/memory-system.md`                                                             |
