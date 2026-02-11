# Claude in a Box: From Discovery Engine to Direct Investigation

> **Decision Record — 2026-02-11**
>
> This document captures the architectural pivot from the Discovery Engine (a 13-agent
> pipeline using gpt-4o-mini) to the "Claude in a Box" approach (one Claude Code instance
> with direct tool access). It preserves the original conversation, reasoning, and first
> validation test while context is still fresh.

---

## Background: What the Discovery Engine Was

Between 2026-02-07 and 2026-02-11, FeedForward built an AI-orchestrated discovery engine
designed to find product opportunities across multiple data sources — Intercom conversations,
PostHog analytics, the target product codebase, and research documents.

The architecture was ambitious:

- **6 stages**: Exploration → Opportunity Framing → Solution Design → Feasibility → Ranking → Human Review
- **13 agent classes** across 19 files
- **Checkpoint system** with typed artifacts at every stage boundary
- **Validation loops** where consuming agents could reject and request revisions from producing agents
- **Adaptive routing** that modified pipeline behavior based on opportunity characteristics
- **700+ tests** covering unit, integration, and end-to-end scenarios

Three real runs were completed against a target product repository (aero). The pipeline
processed findings into ranked, validated product opportunities with evidence chains.

Architecture reference: GitHub Issue #212. Agent conversations: 9UUF048, 8TRY089.

### What the Runs Showed

| Run           | Findings | Briefs | Final Output        | Time    | Cost  |
| ------------- | -------- | ------ | ------------------- | ------- | ----- |
| #1 (6548f72d) | 18       | 18     | 17 specs, 17 ranked | ~43 min | ~$1-2 |
| #2 (2a9d5cb3) | 46       | 18     | First aero repo run | ~43 min | ~$1-2 |
| #3 (9fca9aa8) | 21       | 10     | 9 specs, 9 ranked   | ~29 min | ~$1-2 |

Run costs were low because every LLM call used gpt-4o-mini.

---

## The Realization

On 2026-02-11, after completing the validation loop infrastructure (issues #275-#279,
658 tests passing), the following exchange occurred. These are verbatim excerpts from
the session transcript.

### The Question

> **User:** we're only using gpt-4o-mini for minor tasks, right? this is still largely
> powered by Claude Code instances?

### The Discovery

> **Claude:** So, actually — I need to correct my framing here. **The discovery engine
> is entirely OpenAI / gpt-4o-mini.** Every single agent — explorers, OpportunityPM,
> SolutionDesigner, FeasibilityDesigner, TPMAgent, ValidationAgent, ExperienceAgent,
> TechLeadAgent, RiskAgent — they all use `self.client.chat.completions.create()` with
> `model: str = "gpt-4o-mini"`.
>
> There are no Claude calls in the discovery pipeline at all. Claude Code (me) _writes
> and orchestrates_ the code, reviews PRs, designs the architecture. But at runtime,
> when the pipeline actually processes data, every LLM call goes to OpenAI's gpt-4o-mini.

### The Misalignment

> **User:** Yes. I want to spawn claude code instances for every agent. That was the
> point of the discovery engine. to leverage the power of that level of reasoning,
> access to code and context. I thought that's what we were building from the start
> this is why we DID this discovery engine

### Claude's Analysis

> **Claude:** You're right. And I need to sit with that for a second because — yeah,
> that's a fundamental misalignment between what was designed and what was built.
>
> Let me think about this honestly. The whole architecture discussion back in `9UUF048`
> and `8TRY089` — the insight was that the existing FeedForward pipeline was the extraction
> model the discovery engine moves _past_. The point was to leverage Claude-level reasoning
> with actual tool access — reading code, searching repos, understanding context deeply.
> Not to replicate the same "send a prompt to a cheap model and parse the JSON" pattern
> that the conversation pipeline already does.
>
> And yet... that's exactly what every agent does right now.
> `self.client.chat.completions.create(model="gpt-4o-mini")`. Stateless prompt-in,
> JSON-out. No tool use, no code reading, no iterative reasoning. The codebase explorer
> doesn't actually _explore_ code — it gets a dump of file contents in its prompt and
> writes a summary. The research explorer doesn't _search_ anything — it gets docs
> pasted in.

Claude proposed grafting Claude instances onto the existing pipeline architecture.
The user rejected this.

---

## The Pivot

> **User:** no. I reject that as the only path here. we don't have to graft tons of
> claude code instances onto what we've already built, that's would be wasteful in more
> ways than one. Based on what I now understand, the discovery engine is NOT the right
> path and yes, that will mean the single biggest architectural shift since the discovery
> engine was designed. But what if the architecture was.... no architecture. The product
> becomes YOU. One instance of Claude Code, using access to the same data sources,
> Intercom, Posthog, the codebase, etc etc. to do the same task: create quality actionable
> stories. The rest of the product just becomes your toolset things to make you better
> at doing that task: skills, subagents, scripts, data storage. Call it the Claude in
> a Box approach.

### Claude's Response

> **Claude:** Let me make sure I understand the thesis. The discovery engine — the stages,
> the checkpoints, the orchestrator, the 13 agents, the state machine, the validation
> loops we literally just shipped — all of that was an attempt to _simulate_ what I
> already do naturally when you ask me a question. Like, we built this elaborate pipeline
> where a "codebase explorer" agent gets files pasted into a prompt and summarizes
> them... when I can just _read the files myself_. We built a "customer voice explorer"
> that gets Intercom conversations dumped into gpt-4o-mini... when I have the Intercom
> MCP server right here and can query it directly.
>
> The discovery engine is a Rube Goldberg machine that does a worse version of what
> one Claude Code instance with tools already does.

### The Iterative Tooling Philosophy

Claude asked whether the approach should be (a) ad-hoc investigation sessions or
(b) structured with defined skills and inputs/outputs. The user chose something in between:

> **User:** I think something between a and b. and I think it can be built iteratively.
> some will literally be tools, like a script you run, but process might be part of the
> toolset too. The great thing is, we can start with basically nothing, decide what we
> want to raid from the old pipeline and discovery engine, and iteratevely build the
> other tools, whether those are skillss, processes, reusable code, etc. etc. as we
> discover the need for them

---

## The First Test

Immediately after the pivot conversation, the user assigned the first real task:

> **User:** let's begin. Find an explicit feature request that at least 3 different
> users have requested in Intercom. Use codebase access to figure out roughly where
> it might go and to confirm it hasn't been built already. Use posthog access to
> estimate how many users it might reach if implemented. Provide me with a full
> draft Story

### How It Went

Claude used direct tool access to investigate across all three data sources:

**Intercom data** (via FeedForward PostgreSQL database):

- Queried the themes table for recurring user requests
- Found `ai_language_mismatch`: 24 distinct users, 28 conversations, spanning 14 months
- All requesting non-English language support for AI features (SmartPin, Ghostwriter, Keyword Research)

During the investigation, the user provided real-time course corrections (paraphrased
from session summary — original messages lost to context compaction):

- "ensure the requests are clearly talking about the same thing"
- "API not mcp for intercom" — correcting Claude's attempt to find Intercom MCP tools
- "don't rely on old classification. primary sources only" — pushing Claude to verify
  against actual conversation text, not pipeline-generated classifications

That last correction is worth highlighting. Claude initially relied on theme classifications
from the old FeedForward pipeline. The user insisted on reading primary source
conversation text — the actual words customers wrote. This revealed richer signal:
actual customer quotes, specific language requests, feature surfaces named by users.

**Codebase exploration** (aero repository, direct file access):

- Read SmartPin, Ghostwriter, Keyword Research, and Made for You prompt files
- Confirmed: all AI prompts hardcode English, no language parameter in any request schema
- Discovered existing infrastructure that's almost-but-not-wired: `user_accounts.language`
  and `locale` fields exist in DB, a `LanguageDetector` service exists but only serves
  Pinterest interest classification, one prompt says "match the language of the page_scrape"
  but it's a hint not a contract
- This structural observation ("the plumbing is in the walls but nobody connected the
  faucet") shaped the implementation recommendation in the story

**PostHog analytics** (via MCP):

- Queried AI feature usage events over 90 days
- Ran country breakdowns using `$geoip_country_code` person property
- Found consistent pattern: ~12-14% of users across all AI features are in
  non-English-primary countries (DE, FR, IT, NL, ES, TR, AT)
- Noticed the 12-14% was remarkably stable across features (11.8%, 11.9%, 13.7%),
  which provided confidence to estimate the fourth without another query

**Output**: A full draft story with:

- Problem statement with verbatim customer quotes
- Evidence table with sources, signals, and strength ratings
- Reach estimates broken down by feature and geography
- Codebase analysis with specific file paths and what "done" looks like
- Risks, open questions, and a phased implementation recommendation

### What the Test Proved

The entire investigation — from "let's begin" to complete story — took roughly 15-20
minutes of wall clock time. Compared to the discovery pipeline:

| Dimension               | Discovery Pipeline (Run #3)                                             | Claude in a Box (First Test)                                                  |
| ----------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Time                    | ~29 min                                                                 | ~15-20 min                                                                    |
| Output                  | 21 findings → 10 briefs → 9 ranked                                      | 1 deep story with full evidence                                               |
| Reasoning               | Stateless per-stage, JSON in/out                                        | Continuous, cross-source, iterative                                           |
| Course correction       | Not possible mid-run                                                    | 3 user corrections incorporated in real time                                  |
| Codebase understanding  | File dump → summary                                                     | Read specific files, trace dependencies, notice structural gaps               |
| Data sources            | Pre-extracted context only                                              | Direct queries, pivot based on findings                                       |
| Judgment calls          | Pipeline-constrained                                                    | Chose to analyze country breakdown after initial reach data seemed incomplete |
| Quality issues (Run #3) | Source mislabeling, codebase findings dropped, forced conforming output | None — but only one test                                                      |

### What It Didn't Prove (Yet)

From Claude's self-assessment after the test:

> I think — probably 80% confident this is the right direction. But the approach still
> needs to prove itself at scale and across more varied tasks before I'd call it
> definitively better.

The user's response:

> **User:** I think 80% is enough to go all in. We know the other paths lead to...
> inefficiency and not great output at best.

Specific unknowns:

- **Scale**: One investigation went well. "Find me the top 10 opportunities across all of
  Intercom" would require different tooling.
- **Repeatability**: A pipeline runs the same way every time. Each Claude investigation is
  more like a consulting engagement.
- **Context limits**: The research phase exhausted the context window, requiring session
  recovery. For larger investigations, this is a real constraint.
- **Cost at scale**: Not yet measured. Likely higher per-investigation than gpt-4o-mini
  pipeline, but if output quality is 10x better, ROI may be better.

---

## The Approach Going Forward

### Core Thesis

One Claude Code instance with access to data sources (Intercom/database, PostHog, target
codebase) produces higher-quality, more nuanced product stories than a multi-agent pipeline.
The reasoning-in-the-loop capability — the ability to make judgment calls, pivot based on
findings, incorporate real-time feedback, and notice structural patterns across sources —
is not a nice-to-have, it's the whole point.

### Principles

1. **Start with nothing.** No speculative pre-population of tools or processes. Do the task
   first, build the tools second.

2. **Build from need.** When a pattern emerges that we keep repeating, that becomes a tool.
   When a process works well, that gets documented. Not before.

3. **Raid, don't rebuild.** The old FeedForward pipeline and discovery engine have useful
   pieces — database schemas, API routes, the frontend. Pull them in when there's a specific
   need, not speculatively.

4. **Non-destructive migration.** Nothing gets deleted from the existing codebase. The old
   code stays as-is. New tooling accumulates in `box/`.

5. **The box is the product.** `box/` collects the toolset — skills, scripts, processes,
   reference material — that makes Claude-in-a-Box good at its job. Eventually, once
   mature, the box becomes the new repo.

### What the "Box" Is and Isn't

**The box contains** (the intelligence layer):

- Tools and scripts built from discovered needs
- Process documentation for how investigations work
- Skills that encode reusable patterns
- Reference material
- Any reused code pulled from old systems

**The box does NOT contain** (shared infrastructure):

- Database schemas and data (lives in `src/` and the database)
- The API server (lives in `src/api/`)
- The frontend (lives in `webapp/`)
- The old pipeline code (stays where it is, untouched)

The boundary: the box is what makes Claude smart about product discovery. The infrastructure
is what Claude operates on. They're complementary, not competing.

### Relationship to Existing Code

| Component          | Status                | Rationale                                                            |
| ------------------ | --------------------- | -------------------------------------------------------------------- |
| `src/discovery/`   | Dormant, preserved    | Discovery engine code. Not deleted, not used. Available for raiding. |
| `src/` (pipeline)  | Active infrastructure | Classification, themes, stories — data the box investigates.         |
| `src/api/`         | Active infrastructure | API routes that serve the frontend and expose data.                  |
| `webapp/`          | Active infrastructure | Frontend for reviewing stories and findings.                         |
| `tests/discovery/` | Dormant, preserved    | 700+ tests for the discovery engine. Not running, not deleted.       |
| `box/`             | New, starts empty     | Accumulates tooling as needs emerge.                                 |

---

## Key Quotes for Future Context

These are verbatim from the session transcript and preserve the reasoning that
led to this decision. If future sessions need to understand _why_ this pivot happened,
these are the primary sources.

On the fundamental misalignment:

> **User:** I want to spawn claude code instances for every agent. That was the point of
> the discovery engine. to leverage the power of that level of reasoning, access to code
> and context. I thought that's what we were building from the start this is why we DID
> this discovery engine

On rejecting the "graft Claude onto the pipeline" approach:

> **User:** no. I reject that as the only path here. we don't have to graft tons of claude
> code instances onto what we've already built, that's would be wasteful in more ways than
> one.

On the core idea:

> **User:** The product becomes YOU. One instance of Claude Code, using access to the same
> data sources, Intercom, Posthog, the codebase, etc etc. to do the same task: create
> quality actionable stories. The rest of the product just becomes your toolset things to
> make you better at doing that task: skills, subagents, scripts, data storage. Call it
> the Claude in a Box approach.

On the iterative philosophy:

> **User:** we can start with basically nothing, decide what we want to raid from the old
> pipeline and discovery engine, and iteratevely build the other tools, whether those are
> skillss, processes, reusable code, etc. etc. as we discover the need for them

On committing to the direction:

> **User:** I think 80% is enough to go all in. We know the other paths lead to...
> inefficiency and not great output at best.

On the box as accumulation point:

> **User:** I don't think we'd need to be super strict about literally discarding anything
> not in the box, but I think it's a good way to collect the toolset we build along the
> way. And 100% agree starting with it basically empty. no speculatively pre-population
> of reused code. We add tooling when we identify a need for it, we keep it if it does
> a good job at what it is intended to do.

---

## Appendix: Session Metadata

- **Session date**: 2026-02-11
- **Transcript**: `dc28eb93-3a69-4be9-9e20-2b0e096e7ddb.jsonl`
- **Key lines**: Pivot conversation at lines 553-600. Research phase at lines 600-708
  (lost to context compaction, preserved in summary at line 708).
- **Prior sessions**: Discovery engine built across sessions 2026-02-07 through 2026-02-10.
  Architecture conversations: 9UUF048 (architecture debate), 8TRY089 (stage structure).
- **GitHub context**: Issues #212-#283 cover the full discovery engine lifecycle.
  Issues #275-#279 (validation loops) were the last features shipped before the pivot.
