# Agent Memory System

> Poor man's RAG for agent learning continuity.

---

## How It Works

1. **Store**: After significant experiences (reviews, fixes, discoveries), create a memory file
2. **Retrieve**: Before deploying an agent, grep for relevant memories and inject into prompt
3. **Prune**: Periodically archive old/low-value memories

---

## Directory Structure

```
.claude/memory/
├── [tech-lead]/          # Tech Lead meta-decisions, coordination patterns
│   └── YYYY-MM-DD-topic.md
├── [agent-a]/            # Domain-specific agent memories
│   └── YYYY-MM-DD-prXXX-topic.md
├── [agent-b]/
└── ...
```

Create a directory for each agent that accumulates learnings.

---

## Memory File Schema

```markdown
---
agent: [agent-name]
date: YYYY-MM-DD
type: review-feedback | discovery | mistake | pattern
pr: XXX
issue: YYY
tags: [keyword1, keyword2, keyword3]
impact: high | medium | low
---

## Context
[What was happening]

## Experience
[What happened - the actual feedback, discovery, or mistake]

## Lesson
[What to do differently - actionable takeaway]

## Raw Evidence
[Optional: paste of actual review comment, error message, etc.]
```

### Field Reference

| Field | Required | Values |
|-------|----------|--------|
| `agent` | Yes | Agent name (lowercase) |
| `date` | Yes | YYYY-MM-DD |
| `type` | Yes | review-feedback, discovery, mistake, pattern |
| `pr` | If applicable | PR number |
| `issue` | If applicable | Issue number |
| `tags` | Yes | Keywords for retrieval |
| `impact` | Yes | high, medium, low |

---

## Retrieval Logic

At agent deploy time, find and inject relevant memories:

```bash
# Find memories matching keywords
./retrieve.sh [agent] keyword1 keyword2

# Example
./retrieve.sh backend schema migration
```

The script:
1. Searches agent's memory directory
2. Matches against tags/content
3. Returns formatted memories for prompt injection

### Retrieval Injection Template

```
## Relevant Past Experiences

Before starting, review these lessons from similar past work:

### PR #282 - Topic (YYYY-MM-DD)
[Lesson content here]

### PR #280 - Topic (YYYY-MM-DD)
[Lesson content here]
```

---

## Memory Triggers

| Event | Create Memory? | Type |
|-------|---------------|------|
| Agent receives review feedback | Yes | review-feedback |
| Agent fixes own code | Yes (if lesson learned) | mistake |
| Agent discovers useful pattern | Yes | discovery |
| Routine task completion | No | - |
| Process improvement identified | Yes | pattern |

### When to Create a Memory

**DO create** when:
- Agent made a mistake that was caught in review
- Agent discovered something non-obvious
- Pattern emerged that should be reused
- Process failure that shouldn't recur

**DON'T create** when:
- Task completed without incident
- Issue was trivial/one-off
- Already documented elsewhere

---

## Pruning Policy

Memory files accumulate over time. To prevent bloat while preserving critical learnings:

### Retention Rules

| Impact Level | Retention | Rationale |
|--------------|-----------|-----------|
| `high` | Forever | Major incidents, architectural decisions, process failures |
| `medium` | 90 days | Useful patterns, may be superseded |
| `low` | 30 days | Minor learnings, likely outdated |

### Running the Pruner

```bash
# See what would be deleted (safe, no changes)
./prune.sh --dry-run

# Actually delete old low-impact files
./prune.sh --execute
```

**When to run**: Monthly or when memory count exceeds 50 per agent.

**What gets deleted**:
- Only `impact: low` files older than 30 days
- `impact: high` files are NEVER deleted, regardless of age
- `impact: medium` files are flagged for manual review but not auto-deleted

### Before Running Pruner

1. Review the dry-run output
2. Check that nothing critical was mislabeled as `low`
3. Consider promoting valuable `low` memories to `medium` before they age out

---

## Impact Level Guidelines

When creating memories, choose impact carefully:

| Level | Criteria | Examples |
|-------|----------|----------|
| **high** | Process failures, architectural discoveries, things that changed how we work | "Tests are mandatory", "Learning loop matters" |
| **medium** | Useful patterns for specific domains, reviewer catches worth remembering | "Schema migration pattern", "Hook dependency issue" |
| **low** | Minor fixes, one-off issues, context-specific details unlikely to recur | "Typo in config file", "Wrong import path" |

---

## Monitoring

Count memories by agent (run when count exceeds 50 per agent):

```bash
find .claude/memory -name "*.md" -type f | grep -v README | cut -d'/' -f3 | sort | uniq -c | sort -rn
```

---

## Example Memory File

```markdown
---
agent: backend
date: 2026-01-02
type: review-feedback
pr: 295
tags: [type-safety, interface, config]
impact: medium
---

## Context
Adding quality dimension scoring to the evaluation system. Config referenced dimension names that weren't typed in the interface.

## Experience
Reginald (Architect reviewer) caught that QualityDimension config referenced dimensions not defined in the TypeScript interface. The type system couldn't catch this because config values were typed as `string` instead of the proper enum/union.

## Lesson
When adding config that references typed values (like dimension names), ensure the config type constrains to the valid set. Use union types or enums for config values that must match code.

```typescript
// BAD: string allows any value
type Config = { dimension: string };

// GOOD: constrain to valid values
type Config = { dimension: 'clarity' | 'depth' | 'accuracy' };
```

## Raw Evidence
> 🔴 **High**: Type safety issue with `QualityDimension` - config referenced dimensions not typed in the interface
```

---

## Customization

### Setting Up for Your Project

1. **Create directory structure**:
   ```bash
   mkdir -p .claude/memory/{tech-lead,agent1,agent2}
   ```

2. **Copy retrieve.sh** from this playbook

3. **Start creating memories** after significant learnings

4. **Integrate with agent deployment** - Always retrieve before deploying

### Adapting the Schema

The YAML frontmatter can be extended:

```yaml
# Additional optional fields
severity: critical | major | minor  # If useful for your team
component: [area of codebase]
related_memories: [list of related files]
```

### Keywords by Domain

| Domain | Typical Keywords |
|--------|------------------|
| Prompt/AI | prompt-engineering, examples, constraints, temperature |
| Backend | schema, repository, async, database, migration |
| Frontend | hooks, components, memoization, state |
| Tests | coverage, edge-cases, mocking, fixtures |
| Architecture | boundaries, contracts, integration |
| Review | quality, security, performance, YAGNI |

---

## Integration with Other Processes

### With Context Loading Gate

Memory retrieval is part of context loading. See `../gates/context-loading-gate.md`.

### With Learning Loop

Memories are created when agents fix their own mistakes. See `../gates/learning-loop.md`.

### With Review Process

Reviewer learnings should become memories. See `../review/five-personality-review.md` for REVIEWER_LEARNING protocol.

---

## Summary

| Action | When |
|--------|------|
| Create memory | After significant learning |
| Retrieve memories | Before deploying agent |
| Prune memories | Monthly or when count > 50 |
| Review impact levels | When pruning |
| Update schema | As needs evolve |

**The rule: Store learnings. Retrieve before deployment. Prune regularly.**
