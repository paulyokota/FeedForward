# Context Loading Gate: Declarative Context for Complex Agents

> Complex agents require specific context to be loaded before deployment. This gate ensures that context is loaded consistently.

---

## The Problem

Some agents need specific documentation, memories, or guidelines to do their job correctly. Without this context:

- Agents repeat past mistakes
- Agents ignore established patterns
- Output quality suffers
- Review cycles increase

---

## The Solution: Declarative Context

Agents that require context declare it explicitly in their profile. The Tech Lead loads this context before deployment.

### Agent Profile Schema

In the agent's profile (e.g., `.claude/agents/[agent].md`):

```yaml
# Required Context

load_always:
  # Files loaded on every deployment of this agent
  - [path/to/critical-doc-1.md]
  - [path/to/critical-doc-2.md]

load_for_keywords:
  # Keyword patterns (regex) -> files to load when task contains these keywords
  keyword1|keyword2|keyword3:
    - [path/to/relevant-doc.md]
    - [path/to/memory/*.md]  # Globs supported

  another-keyword:
    - [path/to/another-doc.md]
```

---

## The Gate

**Every deployment of an agent with declared context MUST include a verification block.**

### Verification Block Format

At the top of the agent's Task prompt:

```markdown
## Context Verification
- [ ] load_always: [doc-1.md] loaded
- [ ] load_always: [doc-2.md] loaded
- [ ] Keyword matches: [list matched keywords or "none"]
- [ ] Keyword files loaded: [list files or "none"]

## Loaded Context
### From: [path/to/doc-1.md]
[paste first 10-20 lines or summary]
---
### From: [path/to/doc-2.md]
[paste first 10-20 lines or summary]
---
[any keyword-matched files]
---

## Your Task
[actual task prompt]
```

### Quick Loading Commands

```bash
# Load first 20 lines of required docs
head -20 [path/to/doc-1.md]
head -20 [path/to/doc-2.md]

# Check if task contains keywords
grep -E "keyword1|keyword2" <<< "YOUR_TASK_DESCRIPTION"

# If keywords match, load memory files
cat [path/to/memory/relevant*.md]
```

---

## Violation Handling

If the verification block is missing, the deployment is invalid.

### What to Do

1. **Stop** - Don't proceed without context
2. **Log** - Document the violation in a gate violation log
3. **Fix** - Add the verification block
4. **Continue** - Proceed with proper context

### Gate Violation Log

Maintain a log at `.claude/memory/[tech-lead]/gate-violation-log.md`:

```markdown
## Gate Violations

| Date | Gate | Agent | Task | Resolution |
|------|------|-------|------|------------|
| YYYY-MM-DD | Context Loading | Agent A | Task description | Fixed and re-deployed |
```

---

## Example: Complex Agent Profile

```yaml
# Required Context

load_always:
  # Core quality philosophy - never operate without this
  - .claude/docs/quality-philosophy.md
  - .claude/docs/testing-guidelines.md

load_for_keywords:
  # Evaluation-related work
  evaluator|evaluation|scoring|quality:
    - .claude/memory/kai/*quality*.md

  # Database work
  schema|migration|database:
    - .claude/memory/marcus/*schema*.md
    - .claude/docs/database-conventions.md

  # Security-adjacent work
  auth|security|validation:
    - .claude/docs/security-checklist.md
```

---

## When to Use This Gate

| Scenario | Use Context Loading? |
|----------|---------------------|
| Agent has project-specific knowledge requirements | YES |
| Agent has made past mistakes we've documented | YES |
| Agent works on security-critical code | YES |
| Agent is doing routine, well-understood work | OPTIONAL |
| Task is simple and isolated | SKIP |

### Complexity Indicators

Consider context loading for agents that:

1. **Have accumulated lessons** - Past mistakes documented in memories
2. **Work on sensitive areas** - Security, quality, architecture
3. **Need domain knowledge** - Project-specific patterns or conventions
4. **Touch critical paths** - Core business logic, user-facing features

---

## Customization

### Setting Up for Your Project

1. **Identify complex agents** - Which agents need special context?
2. **Document required context** - Add `load_always` and `load_for_keywords` to profiles
3. **Create the verification template** - Standardize the block format
4. **Set up the violation log** - Track when the gate is skipped
5. **Train the team** - Ensure everyone knows to check before deploying

### Adapting the Schema

The YAML schema can be extended:

```yaml
load_always:
  - path: [file.md]
    lines: 1-50  # Only load specific lines

load_for_keywords:
  pattern:
    - path: [file.md]
      required: true  # Fail if file not found
```

---

## Related Concepts

- **Memory Retrieval** - Context loading uses the memory system (`memory/retrieve.sh`)
- **Agent Profiles** - Context requirements are declared in agent profiles
- **Learning Loop** - Memories are created when agents fix their own mistakes

---

## Summary

| Checkpoint | Action |
|------------|--------|
| Deploying complex agent | Check for `load_always` in profile |
| Task contains keywords | Check `load_for_keywords` matches |
| Required context found | Add verification block to prompt |
| Verification block missing | Stop, log violation, fix, continue |
| Context files not found | Check paths, update profile if needed |

**The rule: Agents with declared context requirements get that context. Every time.**
