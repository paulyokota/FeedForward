---
name: OpportunityPM Evidence Source Type Hardcoded
about: OpportunityPM labels all evidence as intercom, losing source provenance
title: "OpportunityPM hardcodes evidence source_type to intercom"
labels: bug, priority-high, discovery-engine
assignees: ""
---

**Phase**: Discovery Engine | **Priority**: high | **Type**: bug

## Problem

OpportunityPM evidence pointers are always labeled `intercom`, even when the
evidence originated from analytics, codebase, or research. This breaks
traceability and makes downstream review/triage unreliable.

## Root Cause

`build_checkpoint_artifacts()` hardcodes `SourceType.INTERCOM` for every
evidence pointer and only preserves `source_id` from the LLM output.

## Impact

- Mislabels evidence across all non-intercom sources
- Breaks provenance audits in Opportunity briefs
- Obscures codebase/analytics/research contributions to opportunities

## Tasks

- [ ] Build `{source_id -> source_type}` lookup from explorer findings
- [ ] Thread lookup into `build_checkpoint_artifacts()` and replace hardcoded `INTERCOM`
- [ ] Fallback to `SourceType.OTHER` (or log+skip) when source_id not found
- [ ] Add a unit test covering mixed-source evidence mapping

## Evidence

- `src/discovery/agents/opportunity_pm.py:182-222` — hardcoded `SourceType.INTERCOM`

## Fix Complexity

Low — ~10-20 lines in `opportunity_pm.py` plus a small test
