# Last Session Summary

**Date**: 2026-02-10 17:15
**Branch**: main

## Goal

Second discovery run against aero product repo, human review of opportunity quality, architecture direction for pipeline flexibility.

## What Happened

### Second Real Run (Aero Product Repo)

- Run ID: `2a9d5cb3-7477-4375-8854-86dceca4ae82`
- Added target repo support: `--target-repo`, `--scope-dirs`, `--doc-paths`, `--no-auto-pull`
- RepoSyncer service: auto-pull with stash/restore for dirty working trees
- ArtifactChain.tsx rewritten with structured stage views (evidence chips, risk teasers, solution components)

### Quality Evaluation (Agenterminal: session-210-disc)

- Reviewed opportunities #1 and #6 in detail via UI
- #1: Over-grouping — 8 unrelated findings bundled into single "User Experience" opportunity
- #6: Forced user-facing framing — internal instrumentation work got user feedback mechanisms bolted on
- source_type mislabeling bug: research documents labeled as "intercom" in OpportunityPM evidence

### Architecture Direction (3-way: Paul, Claude, Codex)

- Paul's thesis: pipeline over-constrains agents, forcing conforming-but-nonsensical output
- Direction: descriptive schemas + adaptive routing (more agent freedom)
- Rejected: prescriptive enums, more guardrails, problem-type routing
- Filed #260 (surface-specificity) and #261 (adaptive routing)

## Issues Filed

- #260: Surface-specificity constraint for explorer and OpportunityPM prompts
- #261: Adaptive pipeline routing with descriptive opportunity schemas

## Key Decisions

- "Descriptive over prescriptive" — let agents describe what they found, pipeline adapts
- #260 first (surgical), #261 second (fundamental)
- Pause opportunity evaluation until both land

## Agenterminal Conversations

- `session-210-disc`: Discovery run review and architecture discussion

## Next

1. #260 — Surface-specificity constraint
2. #261 — Adaptive pipeline routing with descriptive schemas
3. Re-run discovery against aero with improved pipeline
4. source_type mislabeling bug (file as separate issue)
