# Last Session

**Date**: 2026-02-13
**Branch**: main

## Goal

Fill-cards play: evaluate 7 quality-gate failure cards (SC-15, SC-51, SC-68, SC-90,
SC-118, SC-131, SC-132) against the card quality gate and bring them up to standard.

## What Happened

- **Evaluated all 7 cards at surface level.** Pulled titles, types, description
  lengths, product areas. Identified SC-118 and SC-131 as most likely quality-gate
  failures at a glance (prescriptive title, thin evidence respectively).

- **Deep investigation on SC-15 (Keyword Plan for Customer's Website).** Quality gate
  results: problem before solution FAIL (all solution, no problem statement),
  scoping-ready SOFT FAIL (no Architecture Context), verifiable evidence FAIL (empty
  section), observable done state PASS.

- **Filled SC-15 with investigation findings:**
  - Added problem statement to What section (scaling gap for URL-based keyword search)
  - Filled Evidence with PostHog data: 15.4% of keyword searches are URL-based (8,314
    from 2,501 orgs in 90d). Honest "no Intercom signal" note: internally originated,
    not user-requested.
  - Filled Architecture Context with verified codebase findings: URL extraction
    pipeline (`PinterestKeywordsCollector`, `PINTEREST_KEYWORDS_FROM_URL` at 0 credits),
    data model (`org_keywords`/`org_urls`/`keyword_url_associations`), gaps (no sitemap
    parsing, no bulk orchestration, no job tracking, no admin review workflow).
  - Created PostHog saved insight: [SC-15: URL vs Keyword Search Split](https://us.posthog.com/project/161414/insights/py2jrdGj)

- **Added 4 story links to SC-15:**
  - SC-45 blocks SC-15 (sitemap discovery is a prerequisite)
  - SC-118 relates to SC-15 (URL search speed)
  - SC-85 relates to SC-15 (domain page discovery)
  - SC-101 relates to SC-15 (keyword-URL automation)

- **Updated tooling and process docs:**
  - PostHog events catalog: added 8 newly discovered keyword events
  - MEMORY.md: added "absence of signal is a finding" principle, added product
    documentation reference to Knowledge Areas
  - shortcut-ops.md: added story link verb guidance table to fill-cards play
  - box/log.md: 7 entries covering GIN index gap, Bash escaping, evidence absence,
    PostHog query property, explore agent output, story link directionality, product docs

## Key Decisions

- "No Intercom signal" is stated honestly in Evidence rather than padded. Internally
  originated features get a different evidence treatment than user-requested ones.
- SC-45 (sitemap discovery) genuinely blocks SC-15, not just "relates to." The test:
  "could SC-15 ship without SC-45?" No, the page discovery flow depends on it.
- SC-118 (speed up URL search) relates to but doesn't block SC-15, because SC-15's
  async + admin review design accommodates slowness.
- Explore subagent used for architecture mapping only. All codebase claims on the card
  were verified by reading the actual files.

## Carried Forward

- Fill-cards play on remaining 6 quality-gate cards: SC-51, SC-68, SC-90, SC-118,
  SC-131, SC-132
- Hook coverage gap: MCP tool mutations not gated by PreToolUse hook
- GIN index on `conversation_search_index.full_text`: full-text search is unusable
  without it (341k rows, to_tsvector queries hang). ILIKE works as fallback but proper
  index needed for routine use.
- Test the primer in practice (this session did read it; subjective assessment: it
  oriented the session well)
