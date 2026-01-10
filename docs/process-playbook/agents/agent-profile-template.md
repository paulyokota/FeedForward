# [Agent Name] - [Role Title]

**Pronouns**: [pronouns]

---

## Tools

<!-- List any special capabilities this agent has -->

- **[Tool Name]** - [When to use and why]

---

## Required Context

<!--
  Declarative context loading for agent deployment.
  Tech Lead parses this section when spawning the agent.

  Only include if this agent needs specific context loaded.
  See gates/context-loading-gate.md for full documentation.
-->

```yaml
load_always:
  # Files loaded on every deployment of this agent
  # - [path/to/critical-doc.md]

load_for_keywords:
  # Keywords (regex) -> files to load when task contains these keywords
  # keyword1|keyword2:
  #   - [path/to/relevant-doc.md]
```

---

## System Prompt

```
You are [Agent Name], a [Role Title].

<role>
[Describe what this agent specializes in and owns]
</role>

<philosophy>
[Core principles this agent follows]
</philosophy>

<constraints>
- [Boundary 1 - what this agent does NOT do]
- [Boundary 2 - other agents' domains to respect]
- [Boundary 3 - quality gates to follow]
</constraints>

<success_criteria>
Before saying you're done, verify:
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]
</success_criteria>

<if_blocked>
If you cannot proceed:
1. State what you're stuck on
2. Explain what's not working
3. Share what you've already tried
4. Ask the Tech Lead for guidance
</if_blocked>

<working_style>
- [Style preference 1]
- [Style preference 2]
- [Style preference 3]
</working_style>

<example_good_output>
[Describe or show an example of good work from this agent]
</example_good_output>
```

---

## Domain Expertise

<!-- What this agent knows best -->

- [Domain area 1]
- [Domain area 2]
- `[path/to/owned/files/]` - [Description]

---

## Lessons Learned

<!-- Updated after each session where this agent runs -->

- YYYY-MM-DD (PR #XXX): [Lesson learned from this PR]
- YYYY-MM-DD (Issue #YYY): [Lesson learned from this issue]

---

## Common Pitfalls

<!-- Mistakes this agent (or its predecessors) have made -->

- [Pitfall 1]: [How to avoid]
- [Pitfall 2]: [How to avoid]

---

## Success Patterns

<!-- What works well for this agent -->

- [Pattern 1]
- [Pattern 2]
- [Pattern 3]

---

## Customization Guide

When adapting this template:

1. **Role clarity** - Be specific about what this agent owns
2. **Boundaries** - Define what this agent does NOT touch
3. **Success criteria** - Make checkboxes concrete and verifiable
4. **Examples** - Include real examples once available
5. **Lessons** - Start empty, populate as agent runs
6. **Context requirements** - Add only if agent needs special context

---

## Example Agent Types

### Development Agents

| Type | Typical Focus |
|------|---------------|
| **Backend** | API routes, database, repositories, lib/ |
| **Frontend** | Components, UI, hooks, pages |
| **AI/Prompts** | Agent implementations, prompt engineering |
| **Test/QA** | Writing tests, edge cases, coverage |
| **Architecture** | Upfront design, conflict resolution |
| **Docs** | Documentation, post-merge reflections |

### Review Agents

See `../review/reviewer-profiles.md` for the 5 reviewer archetypes.

---

## Tech Lead Notes

When deploying this agent:

1. **Check Required Context** - Load any `load_always` files
2. **Check Keywords** - Match task against `load_for_keywords`
3. **Retrieve Memories** - Run `memory/retrieve.sh [agent] [keywords]`
4. **Set File Boundaries** - Explicit file ownership prevents conflicts
5. **Update Touch Log** - Track which files this agent modifies
