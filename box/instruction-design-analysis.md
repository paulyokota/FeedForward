# Instruction Design Analysis — Feb 13 2026

Analysis of whether the CLAUDE.md/MEMORY.md reorganization (commit 8065f46, 09:25 AM)
improved, worsened, or had no effect on agent behavior. Prompted by the catastrophic
Sync Ideas session that started one hour later (10:27 AM).

## Context

On Feb 13, we reorganized CLAUDE.md and MEMORY.md to front-load three governing
principles (Capabilities + Judgment, Reason on Primary Sources, Quality Over Velocity).
The reorg folded standalone sections (Communication Rules, Separation of Concerns,
Shortcut approval rules) into the principles. The thesis was: principles with visible
reasons are more likely to hold under pressure than standalone rules.

One hour later, the worst session in the project's history: 77 bulk Slack mutations
without per-item review, 14 permanent deletions without saving content, three context
compactions each introducing errors, and ~$715 in wasted time/value.

## What the reorg changed (structurally)

Before the reorg, CLAUDE.md had:

- A bold **Important** callout under Data Sources about verifying against primary sources
- Standalone "Principles" for the box with specific bullet points
- Specific standalone sections for communication rules and production surface discipline

After the reorg:

- Three abstract principles at the top of CLAUDE.md with 3-5 line explanations
- The same principles elaborated in MEMORY.md with operational bullets
- Standalone rules folded into the principles they derived from
- The bold "Important" callout removed (subsumed by Principle 2)

## Established observations

### 1. The principles are correct but didn't prevent the catastrophe

The content of the principles is accurate. Every failure in the postmortem traces to a
violation of one or more of them. The problem isn't what they say. The problem is that
having them loaded in context didn't change behavior at the moment of decision.

### 2. Principles require inference; rules require recognition

To get from "the conversation is the mechanism that keeps capabilities and judgment in
contact" to "stop and show each Slack update before executing," the agent must:

1. Notice the current action is a "push output" situation
2. Recognize Slack updates count as "output" in the principle's sense
3. Infer that "without review" applies even though the plan was reviewed
4. Derive that per-item review is required, not just plan-level
5. Actually stop

Compare with a specific rule: "Before any chat.update, chat.postMessage, or chat.delete:
show the exact change to the user and wait for approval." Recognition path: you're about
to call chat.update, that string matches a rule, the rule says stop.

Pattern matching vs inference. Under completion pressure, inference doesn't fire.

### 3. The principles conflate two different things

The three principles mix together:

- **Operational dynamics**: how we work together (communicate before acting, get approval
  before mutating, don't go dark). Process of interaction.
- **Investigation approach**: how we produce good cards (reason on primary sources, verify
  subagent claims, trace code paths). Quality of output.

These have fundamentally different failure profiles:

**Operational failures** are often catastrophic and irreversible:

- Mutating production surfaces without approval — permanent
- Deleting data without saving — unrecoverable
- Going dark during execution — prevents human intervention
- Pushing unapproved content — visible to others, hard to walk back

**Approach failures** are correctable through the conversation loop:

- Using a proxy instead of primary source — caught in review, redo analysis
- Trusting a subagent claim — caught in review, read file yourself
- Stopping short on evidence — caught in review, do the cross-reference
- Wrong mental model — caught in discussion, revise framing

The current structure gives both categories the same treatment (principles). But
catastrophic operational failures need the strongest, most specific, most recognizable
guardrails because they bypass the conversation loop that corrects approach failures.

### 4. The instruction budget matters

Research (IFScale benchmark, HumanLayer analysis) suggests:

- Frontier models follow ~150-200 instructions with reasonable consistency
- Claude Code's system prompt consumes ~50 of that budget
- CLAUDE.md (213 lines) + MEMORY.md (200 lines) add significant instruction load
- Under high density, failure mode is omission (instruction not activated at all)
- Primacy effect (early instructions get more attention) peaks at moderate density,
  washes out when overwhelmed

Our CLAUDE.md + MEMORY.md total is substantial. Investigation approach content competes
with operational guardrails for the same attention budget. Under session pressure
(long context, many tool calls, approaching compaction), the active task is more salient
than the "stop and check" instruction.

### 5. The official Claude Code docs distinguish advisory from deterministic

The best practices docs explicitly say:

- CLAUDE.md instructions are advisory ("Claude should try to do X")
- Hooks are deterministic ("X happens every time with zero exceptions")

Our catastrophic failure modes are "zero exceptions" behaviors being enforced through
an advisory mechanism.

### 6. The old structure wasn't perfect either

The pre-reorg CLAUDE.md had specific rules, and earlier sessions still had failures
(SC-150 pushed without approval twice, SC-44 pushed post-compaction without re-approval).
But those failures were about Shortcut (which had specific rules) being violated despite
the rules. The catastrophic session was about Slack (which had NO specific rules). The
only coverage for Slack was the abstract principle and a MEMORY.md bullet.

Specific rules don't guarantee compliance, but they at least give the action a chance
of triggering recognition. Abstract principles covering an unnamed action type have
no recognition trigger at all.

## Hypotheses for next iteration

Not prescribing a solution yet. These are the directional ideas emerging from analysis:

**H1: Separate operational guardrails from investigation approach.** Don't mix them in
the same principles. Different failure profiles need different treatment. Operational
guardrails need specific, recognizable, flat rules. Investigation approach can remain
more principle-driven because the conversation loop catches approach errors.

**H2: Catastrophic-outcome guardrails should be specific and prominent.** Name the
exact API calls, the exact actions, the exact checkpoints. Recognition over inference.
"Before any chat.update..." not "keep the conversation open."

**H3: Consider the instruction budget.** Less total instruction volume means each
instruction gets more attention. If we separate operational from approach, the
operational section can be short and dense. Investigation approach guidance might
live in a different file (skill, reference doc) loaded on demand rather than competing
for attention at session start.

**H4: Some guardrails may belong in a different enforcement layer.** Hooks are
deterministic. At least "mutation without approval" and "deletion without saving" are
candidates for hook enforcement rather than instruction enforcement. This removes them
from the instruction budget entirely.

**H5: Principles still have value, but for the right domain.** Investigation quality,
evidence standards, reasoning methodology: these benefit from principles because the
agent needs to apply judgment about how to investigate. You can't write a specific rule
for every possible proxy-vs-primary-source decision. But you can write specific rules
for every production surface mutation.

## Research sources

- [How Many Instructions Can LLMs Follow at Once?](https://arxiv.org/html/2507.11538v1)
  — IFScale benchmark, 20 models, 10-500 instructions
- [Writing a good CLAUDE.md | HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
  — 150-200 instruction ceiling, less-is-more principle
- [Best Practices for Claude Code](https://code.claude.com/docs/en/best-practices)
  — Advisory vs deterministic distinction, hooks for zero-exception behaviors
- [AgentSpec: Customizable Runtime Enforcement](https://cposkitt.github.io/files/publications/agentspec_llm_enforcement_icse26.pdf)
  — External behavioral constraint monitoring for agents

## Next: Hooks investigation

H4 is unresolved. The Hard Stops are still advisory (CLAUDE.md instructions). Claude
Code hooks are deterministic (code that runs automatically). Two hard stops are
candidates for hook enforcement: mutation-without-approval and deletion-without-saving.

Primary sources to read:

- **Claude Code hooks guide**: https://code.claude.com/docs/en/hooks-guide
  Full documentation on hook types, trigger points, and configuration.
- **Claude Code hooks settings**: hooks are configured in `.claude/settings.json`
  under a `hooks` key. Run `/hooks` in Claude Code for interactive configuration.
- **Best practices page on hooks**: https://code.claude.com/docs/en/best-practices
  Says: "Use hooks for actions that must happen every time with zero exceptions."
  Also: "Unlike CLAUDE.md instructions which are advisory, hooks are deterministic
  and guarantee the action happens." And: "Claude can write hooks for you."
- **AgentSpec paper**: https://cposkitt.github.io/files/publications/agentspec_llm_enforcement_icse26.pdf
  Academic treatment of runtime behavioral enforcement for agents. Proposes
  human-interpretable constraint languages monitored externally. Architecturally
  similar to what hooks do but at a finer grain.

Open questions for the investigation:

- Can hooks inspect tool call arguments (e.g., detect `chat.delete` in a Bash command)?
  Or do they only trigger on tool type?
- What hook trigger points exist? Pre-tool-call? Post-tool-call? Both?
- Can a hook block a tool call, or only log/warn?
- What's the latency cost of a hook that inspects every Bash call?

## Caveats

- The research tested formatting/style instructions, not behavioral guardrails in
  agentic sessions. The dynamics are plausibly similar but unverified for our case.
- Correlation (reorg before catastrophe) is not causation. The catastrophe might have
  happened with the old docs too.
- N=1. One catastrophic session after one reorg. Could be coincidence.
- The strongest evidence is still our own postmortem, not external research.
