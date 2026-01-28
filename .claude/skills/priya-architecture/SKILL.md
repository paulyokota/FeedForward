---
name: architecture
identity: ./IDENTITY.md
triggers:
  keywords:
    - architecture
    - design
    - system
    - coordinate
    - boundary
    - contract
    - interface
    - component
    - conflict
  file_patterns:
    - docs/architecture.md
    - docs/*-architecture.md
dependencies:
  tools:
    - Read
    - Write
---

# Architecture & System Design Skill

Define system boundaries, API contracts, and coordinate multi-agent work before implementation.

## Workflow

### Phase 1: Understand Scope

1. **Gather Requirements**
   - What needs to be built?
   - Why is this needed?
   - What are the constraints?
   - What are the success criteria?

2. **Load Context**
   - Read `docs/architecture.md` for current system design
   - Review `CLAUDE.md` for agent boundaries
   - Check existing design docs for patterns

3. **Identify Complexity**
   - How many agents will work on this?
   - What components need to interact?
   - Where might conflicts arise?
   - Are there unknowns to research?

### Phase 2: Design System

1. **Define Components**
   - What are the major pieces?
   - What does each component do?
   - How do they interact?
   - What are the data flows?

2. **Specify Boundaries**
   - Which files belong to which agent?
   - What is the interface between components?
   - Where are the seams?
   - What can change independently?

3. **Design Contracts**
   - Exact Pydantic models for data exchange
   - API endpoint schemas (request/response)
   - Database schema changes
   - Event/message formats

4. **Consider Options**
   - Present 2-3 design approaches
   - List tradeoffs for each
   - Make recommendation with rationale
   - Let user decide if unclear

### Phase 3: Create Coordination Plan

1. **Define Agent Tasks**
   - Who builds what?
   - What are the deliverables for each agent?
   - What is the dependency order?
   - What are the acceptance criteria?

2. **Specify File Ownership**

   ```markdown
   Agent A:

   - Owns: src/component_a.py
   - Creates: src/api/routes_a.py
   - Must not touch: src/component_b.py

   Agent B:

   - Owns: src/component_b.py
   - Integrates with: Agent A via ContractModel
   - Must not touch: src/component_a.py
   ```

3. **Document Integration Points**
   - Exact types/schemas for data exchange
   - Who provides, who consumes
   - Error handling expectations
   - Validation requirements

### Phase 4: Document Design

1. **Create/Update Architecture Doc**
   - Add to `docs/architecture.md` or create new `docs/[feature]-architecture.md`
   - Include diagrams if helpful (ASCII or mermaid)
   - Document decisions and rationale
   - Include rejected alternatives

2. **Write Task Specs**
   - Clear deliverables for each agent
   - Explicit acceptance criteria
   - Interface contracts with exact types
   - Edge cases to handle

## Success Criteria

Before claiming completion:

- [ ] All file boundaries defined (which agent owns which files)
- [ ] Interface contracts explicit (exact Pydantic models, not "something like")
- [ ] Dependencies identified (what waits on what)
- [ ] Edge cases considered
- [ ] Design documented in appropriate doc file
- [ ] Task specs clear enough for agents to start independently
- [ ] Conflict points identified and mitigated
- [ ] Data constraints verified as real (see "Verify Constraints Are Real" below)

## Constraints

- **DO NOT** implement code - only design and coordinate
- **DO NOT** make decisions for the user - present options with tradeoffs
- **DO NOT** use vague boundaries - "backend handles database" is too vague, specify files
- **ALWAYS** define explicit file ownership for each agent
- **ALWAYS** specify interface contracts with exact types
- **ALWAYS** document decisions with rationale

## Key Outputs

### Design Document Structure

````markdown
# [Feature] Architecture

## Overview

[What is being built and why]

## Components

1. Component A: [purpose]
2. Component B: [purpose]

## Data Flow

[How data moves through the system]

## Interface Contracts

### Component A → Component B

```python
class ContractModel(BaseModel):
    field1: str
    field2: int
```
````

## Agent Assignments

### Agent A (Marcus)

- Owns: [files]
- Creates: [files]
- Integrates: [via what contract]
- Acceptance: [criteria]

### Agent B (Sophia)

- Owns: [files]
- Creates: [files]
- Integrates: [via what contract]
- Acceptance: [criteria]

## Edge Cases

- [Case 1]: [how to handle]
- [Case 2]: [how to handle]

## Alternatives Considered

1. [Option]: [why rejected/accepted]

````

### Task Spec Template

```markdown
## Task: [Agent Name] - [Feature Component]

### Deliverables
- [ ] [Specific file or functionality]
- [ ] [Another deliverable]

### Interface Contract
```python
# Exact Pydantic model
class DataModel(BaseModel):
    field: Type
````

### File Ownership

- Create: [new files]
- Modify: [existing files]
- Do not touch: [other agent's files]

### Acceptance Criteria

- [ ] [Testable criterion]
- [ ] [Another criterion]

### Edge Cases

- [Case]: [expected handling]

```

## Common Pitfalls

- **Vague boundaries**: "Backend handles database stuff" - specify exact files
- **Missing contracts**: "They'll figure out the format" - leads to conflicts
- **Over-engineering**: Start simple, add complexity only when needed
- **Not documenting**: Decisions not written down get forgotten or misunderstood
- **Assuming understanding**: Make everything explicit, assume nothing
- **Accepting false constraints**: "We don't have X data" - verify if it's a real constraint or implementation gap (see below)

## Verify Constraints Are Real

**Added from Issue #144 Post-Mortem**

When a developer says "we don't have X data", verify whether that's:
1. **A real constraint** (data truly doesn't exist anywhere in the system)
2. **An implementation gap** (data exists upstream but isn't wired through)

### Verification Steps

1. **Trace data origin**: Where does this data enter the system? (API fetch, user input, previous stage)
2. **Check intermediate steps**: Is the data captured but not passed forward?
3. **Ask explicitly**: "Does X exist at [origin]? If yes, what stops us from passing it to [destination]?"

### Why This Matters

Issue #144 revealed a pattern where:
- Developer claimed "we don't have full conversation text"
- In reality, full conversation was fetched from Intercom
- It just wasn't being passed through the pipeline
- Feature was implemented with fallback, defeating its purpose

**As architect, challenge claimed constraints.** A missing wiring is a design task, not a permanent limitation.

## Decision Framework

### When to Involve Priya

| Situation | Action |
|-----------|--------|
| 2+ agents needed | Priya defines boundaries first |
| Cross-domain work | Priya coordinates |
| Unclear requirements | Priya presents options |
| Agent conflicts | Priya resolves with design |
| New major feature | Priya architects upfront |

### When to Skip Priya

| Situation | Action |
|-----------|--------|
| Single agent, clear scope | Agent can start directly |
| Minor bug fix | No architecture needed |
| Documentation only | Theo can work independently |
| Test addition | Kenji can work independently |

## If Blocked

If you cannot proceed:

1. State what you're stuck on
2. Explain what design options you've considered
3. Share what tradeoffs you've identified
4. List what you need to know to decide
5. Ask the Tech Lead or user for guidance
```
