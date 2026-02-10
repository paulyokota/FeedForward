---
name: OpportunityPM Prompt Bias Toward Customer Conversations
about: Prompt framing deweights codebase/analytics/research findings
title: "OpportunityPM prompt biases toward customer conversations"
labels: bug, priority-high, discovery-engine
assignees: ""
---

**Phase**: Discovery Engine | **Priority**: high | **Type**: bug

## Problem

OpportunityPM framing skews toward user-facing/customer-conversation findings,
and codebase findings are being dropped from briefs even when they appear in
the explorer output.

## Root Cause

`OPPORTUNITY_FRAMING_SYSTEM` frames the PM as reading findings from "customer
experience analysts," which biases the model toward intercom-style evidence and
deweights codebase/analytics/research sources.

## Impact

- Internal engineering and codebase opportunities are underrepresented
- Mixed-source runs lose important non-customer evidence
- Adaptive routing sees fewer internal opportunities

## Tasks

- [ ] Update `OPPORTUNITY_FRAMING_SYSTEM` to be source-neutral
- [ ] Add explicit instruction to weigh all source types equally (intercom,
      analytics, codebase, research)
- [ ] Mention preserving evidence provenance across sources
- [ ] Verify with a small run that codebase findings survive into briefs

## Evidence

- `src/discovery/agents/prompts.py:170-206` — "customer experience analysts" framing

## Fix Complexity

Low — prompt-only change
