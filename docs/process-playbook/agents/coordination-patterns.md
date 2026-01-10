# Agent Coordination Patterns

> How to deploy, coordinate, and integrate work from multiple agents.

---

## Pre-flight Checklist

Ask these questions before parallelizing ANY work:

- [ ] **Did an architect define the task boundaries?** (If no, define them first)
- [ ] Can tasks complete **fully independently** without waiting on each other?
- [ ] Is the **interface/contract stable** before work starts?
- [ ] Is each task **large enough** (3+ story points) to justify overhead?
- [ ] Will agents **avoid touching the same files**?

**If any answer is NO** -> do it yourself, get architecture help, or sequence the work.

---

## How to Deploy Agents

**Sequential with handoff:**
```
// Architect designs first
Agent(Architect): "Design the API contract for [feature]..."
// Wait for result
// Then developer implements the contract
Agent(Developer): "Implement the API that Architect designed: [paste contract]"
```

**Parallel deployment:**
```
// Launch multiple agents in parallel
Agent(Backend, run_in_background=true)
Agent(Frontend, run_in_background=true)
// Wait for both
```

---

## Scaling Guidance

| Task Complexity | Agents | Example |
|-----------------|--------|---------|
| Simple fix | 0-1 | Fix typo, add field |
| Single feature | 1-2 | Add button + API endpoint |
| Cross-cutting feature | 2-4 | New workflow with UI + backend + tests |
| Major refactor | 3-5 | Restructure module boundaries |

**The 2x Rule**: If parallelization won't save at least 2x the coordination overhead, do it yourself.

**Agent Count Sweet Spots**:
- **2-3 agents**: Easy, minimal overhead
- **4-5 agents**: Sweet spot for complex features
- **6+ agents**: Danger zone - coordination cost explodes

---

## Task Spec Checklist

**PREVENTION > RESOLUTION.** Vague specs cause conflicts. Be specific.

Include ALL of these when briefing an agent:

- [ ] **Explicit objective** (what to build)
- [ ] **File boundaries** (which files to CREATE/MODIFY - exclusive ownership)
- [ ] **Files to READ but not WRITE** (for context only)
- [ ] **Interface contract** (exact types, API shapes)
- [ ] **Patterns to follow** (specific existing files to reference)
- [ ] **What NOT to do** (explicit exclusions)
- [ ] **Dependencies** (what they're waiting on or what waits on them)
- [ ] **Acceptance criteria** (how to know it's done)

---

## Coordination Patterns

### Pattern 1: Architect-First (Default for Multi-Agent Work)

This is your default. Use it unless you meet the skip criteria below.

```
0. RETRIEVE MEMORIES for each agent you'll deploy
1. Deploy architect to design architecture + API contracts + file boundaries
2. Review architect's output, resolve open questions with user
3. Deploy implementers in parallel with architect's specs
4. Integrate their work
5. MANDATORY: Deploy test agent (see test-gate.md)
6. Deploy review agents (2+ rounds until converged)
   -> Review issues? Route back to ORIGINAL dev agent (see learning-loop.md)
7. Merge
8. Deploy docs agent -> collects reflections, updates docs if needed
```

### Pattern 2: Parallel Build (Skip Architect)

Only use this when you meet the skip criteria. If you're unsure, go back to Pattern 1.

```
0. RETRIEVE MEMORIES for each agent you'll deploy
1. Define API contract yourself - must be EXPLICIT, not "I'll figure it out"
2. Deploy agents in parallel
3. Integrate, resolve any contract mismatches
4. MANDATORY: Deploy test agent (see test-gate.md)
5. Deploy review agents (2+ rounds until converged)
   -> Review issues? Route back to ORIGINAL dev agent (see learning-loop.md)
6. Merge
7. Deploy docs agent -> collects reflections
```

### Pattern 3: Solo + Review (Single Agent or Self-Built)

For when you're doing the work yourself or deploying just one agent.

```
0. RETRIEVE MEMORIES for the agent you'll deploy (if any)
1. Build it yourself (or deploy single agent)
2. MANDATORY: Write tests yourself OR deploy test agent (see test-gate.md)
3. Deploy review agents (5 personalities, 2+ rounds)
   -> Review issues? Route back to ORIGINAL dev agent (see learning-loop.md)
4. Merge
5. Deploy docs agent -> collects reflections
```

---

## Architect-Skip Criteria

The ONLY times you can skip architecture for multi-agent work:

- **Single-agent task**: You're only deploying one agent, no coordination needed
- **Contract already crystal clear**: You defined exact types, file boundaries, and interfaces
- **Identical to previous task**: Same pattern was designed recently, nothing changed
- **Time-critical hotfix**: Production is on fire (accept the risk of conflicts)

If none of these apply, get architecture help. "I think I know what to do" is not on this list.

---

## Memory Retrieval (Mandatory)

**Step 0 of every pattern.** Before deploying any agent, retrieve their relevant memories.

### How to Retrieve

```bash
# Get memories for an agent with relevant keywords
MEMORIES=$(./memory/retrieve.sh [agent] keyword1 keyword2)

# Inject into agent prompt
"You are [Agent]...

## Relevant Past Experiences
$MEMORIES

## Your Task
..."
```

### Why This Matters

Agents repeat mistakes without memory. Memory retrieval surfaces past learnings relevant to the current task.

### Keywords by Domain

| Agent Type | Typical Keywords |
|------------|------------------|
| Prompt/AI | prompt-engineering, examples, constraints |
| Backend | schema, repository, async, database |
| Frontend | hooks, components, memoization |
| Tests | coverage, edge-cases, mocking |
| Architecture | architecture, boundaries, conflicts |
| Reviewers | proxy-metrics, quality, security |

---

## Conflict Resolution

### Simple Conflicts (Resolve Yourself)

| Conflict Type | Default Resolution |
|---------------|-------------------|
| Type/interface mismatch | Backend owns types, frontend adapts |
| Same file edited | Review both, pick best or combine |

### Complex Conflicts (Get Architecture Help)

| Conflict Type | When to Escalate |
|---------------|------------------|
| Design disagreement | Two agents solved the problem differently |
| Domain boundary unclear | Both agents think they own the file |
| Contract can't be reconciled | Components need different shapes |
| Quality vs other tradeoffs | Need judgment call |

### Always Escalate to User When:

- Conflict reveals unclear requirements
- Both solutions have major tradeoffs
- You're unsure

**What to provide**: What's conflicting, what you recommend, why, and alternatives considered.

---

## Domain Boundaries

Establish clear ownership. Example structure:

| Domain | Owner |
|--------|-------|
| `src/app/api/`, database, repositories | Backend Agent |
| `src/components/`, pages, hooks | Frontend Agent |
| `src/lib/agents/`, prompts, evaluation | AI/Prompt Agent |
| `*.test.ts`, test utilities | Test Agent |
| `docs/`, agent profiles | Docs Agent |

**Customize this for your project structure.**

---

## Failure Modes

| Failure | Prevention | Recovery |
|---------|------------|----------|
| **Duplicate work** | Define boundaries upfront | Pick better implementation |
| **Agent blocked waiting** | Identify dependencies upfront | Provide mock/stub, or sequence |
| **Silent failure** (wrong but "done") | Specific acceptance criteria | Validate before accepting |
| **Same file chaos** | Assign exclusive file ownership | Human merges carefully |
| **Context rot** | Brief agents with current state | Re-brief if specs change |
| **Skipped tests** | Test gate checklist | Revert, add tests, re-merge |
| **Skipped reflections** | Deploy docs agent after merge | Go back and run it |
| **Skipped architecture** | Default to Pattern 1 | If conflicts arise, escalate |

---

## Architecture Review Gate

**When to use**: Before executing any multi-agent implementation plan that:
- Touches critical paths (evaluators, metrics, core logic)
- Has multiple systems integrating
- Has non-obvious data flow between agents
- Has technical complexity

**Core reviewers (always)**:
| Reviewer | Lens | Why at Plan Stage |
|----------|------|-------------------|
| **Quality** | Quality/coherence | Catches system conflicts |
| **Pragmatist** | Pragmatism/YAGNI | Catches overengineering |

**Add based on plan content**:
| Reviewer | When to Add |
|----------|-------------|
| **Architect** | Technical complexity or performance concerns |
| **Security** | Security-adjacent (auth, user data, external APIs) |

**Process flow**:
```
Architect designs -> Quality + Pragmatist validate plan -> Amend if needed -> Execute
```

---

## When to Escalate to User

Stop and ask when:

- Conflict affects project scope or timeline
- No clear resolution in existing patterns
- Tradeoff between security, performance, UX
- You're unsure which agent's approach is right
- Build fails after integration and you can't figure out why

**What to provide**: What's conflicting, what you recommend, why, and alternatives considered.

---

## Customization

### Adapting for Your Project

1. **Domain boundaries** - Map to your actual directory structure
2. **Agent count limits** - Adjust based on your context window budget
3. **Skip criteria** - Tighten or loosen based on team maturity
4. **Failure modes** - Add project-specific patterns you've encountered

### Scaling Considerations

From [Anthropic's research](https://www.anthropic.com/engineering/multi-agent-research-system):

- Multi-agent uses ~15x more tokens than single-agent chat
- Best for "breadth-first" work requiring parallel exploration
- Economic viability requires tasks where value justifies token cost

---

## Summary

| Stage | Action |
|-------|--------|
| Planning | Decide: solo, sequence, or parallel |
| Pre-deployment | Retrieve memories, check context requirements |
| Briefing | Use task spec checklist - be explicit |
| Execution | Track file ownership in touch log |
| Integration | Resolve conflicts with clear rules |
| Review | Route fixes to original dev |
| Post-merge | Collect reflections, update profiles |
