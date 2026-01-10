# Multi-Agent Claude Code Process Playbook

> A portable process framework for bootstrapping multi-agent Claude Code codebases.

This playbook contains battle-tested patterns for coordinating AI agents in software development. It was extracted from real production experience with multi-cycle evaluation, code review, and iterative improvement loops.

## What This Is

A reusable set of process documentation for any team using Claude Code with multiple specialized agents. These patterns are technology-agnostic and can be adapted to any codebase.

## Quick Start

1. **Copy this directory** into your project as `.claude/` or `process-playbook/`
2. **Customize `templates/CLAUDE.md.template`** for your tech stack
3. **Create agent profiles** using `agents/agent-profile-template.md`
4. **Set up memory system** following `memory/README.md`
5. **Adopt gates incrementally** - start with the test gate, add others as needed

## Directory Structure

```
process-playbook/
├── README.md                      # This file
├── gates/                         # Process gates - hard requirements
│   ├── test-gate.md               # Tests before review
│   ├── learning-loop.md           # Dev fixes own code + Session Touch Log
│   ├── context-loading-gate.md    # Declarative context for complex agents
│   ├── functional-testing-gate.md # Evidence for pipeline/LLM PRs (NEW)
│   └── backlog-hygiene.md         # Capture issues before session ends (NEW)
├── review/                        # Code review process
│   ├── five-personality-review.md # Multi-perspective review system
│   └── reviewer-profiles.md       # The 5 reviewer archetypes
├── agents/                        # Agent patterns
│   ├── agent-profile-template.md  # Blank template for new agents
│   └── coordination-patterns.md   # Multi-agent coordination
├── philosophy/                    # Quality philosophy
│   ├── gold-standard-alignment.md # Source of truth principle
│   └── proxy-metrics.md           # When measurements fail
├── memory/                        # Agent memory system
│   ├── README.md                  # Setup and schema
│   └── retrieve.sh                # Memory retrieval script
└── templates/
    └── CLAUDE.md.template         # Starting point for new repos
```

## Core Concepts

### Process Gates

Gates are hard stops - requirements that must be met before proceeding. They exist because we've learned the hard way that skipping them leads to rework.

| Gate                   | Purpose                                    | Why It Exists                                           |
| ---------------------- | ------------------------------------------ | ------------------------------------------------------- |
| **Test Gate**          | Tests exist before code review             | We've shipped bugs. Multiple times.                     |
| **Learning Loop**      | Original dev fixes their own review issues | Agents don't learn if someone else fixes their mistakes |
| **Context Loading**    | Required docs injected for complex agents  | Agents without context repeat past mistakes             |
| **Functional Testing** | Evidence required for pipeline/LLM PRs     | Unit tests can't catch real LLM output issues           |
| **Backlog Hygiene**    | Capture issues before session ends         | Context resets lose undocumented issues                 |

### Five-Personality Review

Code review using five separate reviewer agents, each with a distinct perspective:

1. **The Architect** - Correctness, performance, integration
2. **The Security Auditor** - Security, validation, paranoia
3. **The Quality Champion** - Output quality, system coherence
4. **The Pragmatist** - Simplicity, YAGNI, no bloat
5. **The Maintainer** - Clarity, docs, future maintainability

Why separate agents? Single-agent reviews are too lenient - the agent rubber-stamps its own reasoning.

### Gold Standard Alignment

When authoritative documentation exists, implementation must match. If your code says `25` but your design doc says `6-10`, that's a bug, not a judgment call.

Evaluators and metrics are proxies for quality. When the proxy fails, question the measurement before lowering the bar.

## Adoption Path

### Week 1: Foundation

- [ ] Set up `CLAUDE.md` from template
- [ ] Implement Test Gate (tests before review)
- [ ] Create profiles for 2-3 dev agents

### Week 2: Review

- [ ] Adopt 5-personality review for major PRs
- [ ] Set up learning loop (dev fixes own code)
- [ ] Add reviewer agent profiles

### Week 3: Memory

- [ ] Set up memory directory structure
- [ ] Create first memory files for major learnings
- [ ] Integrate `retrieve.sh` into agent deployment

### Week 4: Polish

- [ ] Add context loading for complex agents
- [ ] Document project-specific gold standards
- [ ] Review and refine agent profiles

## Key Principles

### From Anthropic Research

Multi-agent systems excel for breadth-first work requiring parallel exploration. Key findings:

- **Orchestrator-worker pattern**: Lead agent coordinates, subagents execute
- **Model mixing**: Use stronger models for orchestration, efficient models for execution
- **Token awareness**: Multi-agent uses ~15x more tokens than single-agent chat
- **Tracing is essential**: Non-deterministic agents require full observability

### From Real-World Experience

1. **Prevention beats resolution** - Vague specs cause conflicts. Be specific upfront.
2. **4-5 agents is the sweet spot** - Below 4, solo is faster. Above 5, coordination explodes.
3. **Sessions have amnesia** - Issues not filed are issues lost. Maintain progress files.
4. **Proxy metrics drift** - What you measure is not what you care about. Validate regularly.
5. **Learning loops matter** - If the dev doesn't fix their own bug, they won't learn from it.

## Customization Points

Throughout these docs, you'll see placeholders:

| Placeholder      | Replace With                   |
| ---------------- | ------------------------------ |
| `[PROJECT_NAME]` | Your project name              |
| `[path/to/...]`  | Your actual file paths         |
| `[PR #XXX]`      | Your PR references (or remove) |
| `[command]`      | Your build/test commands       |

Each doc has a "Customization" section explaining what to adapt.

## License

These processes are intended to be freely adapted. No attribution required.

---

## Sources

This playbook incorporates learnings from:

- [Claude Code: Best practices for agentic coding](https://www.anthropic.com/engineering/claude-code-best-practices) - Anthropic's official guidance
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) - Multi-agent architecture patterns
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Session continuity solutions
- [Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md) - CLAUDE.md best practices
- [CLAUDE.md: Best Practices Learned from Optimizing Claude Code](https://arize.com/blog/claude-md-best-practices-learned-from-optimizing-claude-code-with-prompt-learning/) - Prompt optimization techniques
