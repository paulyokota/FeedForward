# Last Session

**Date**: 2026-02-13
**Branch**: main

## Goal

Quality gate audit of all Ready to Build cards. Fix failures, push corrected
descriptions to Shortcut.

## What Happened

- **Triaged all 23 Ready to Build stories.** Categorized into Tier 1 (13 cards,
  sections filled), Tier 2 (8 cards, partially empty), Tier 3 (2 cards, basically
  empty: SC-37 and SC-38, probably subsumed by SC-39).

- **Ran quality gate on all 13 Tier 1 cards.** 9 passed, 4 failed:
  - SC-44: empty Monetization, prescriptive Architecture Context, "Create flow" phrasing,
    implementation-step Release Strategy
  - SC-32: unlinked PostHog numbers, unverified toggle claim
  - SC-39: Open Questions section (implementation decisions, not product decisions)
  - SC-161: Open Questions section, "Create flow" phrasing, unresolved UI options

- **Fixed and pushed all 4 failures:**
  - SC-44: Rewrote Architecture Context from prescriptive to descriptive ("What needs to
    change" became "Current limitations"). Filled Monetization (credit velocity + retention
    - support burden). Fixed phrasing. Replaced implementation Release Strategy with
      rollout/enablement.
  - SC-32: Created PostHog saved insight NHG2HzFV for Turbo events. Updated evidence
    with linked numbers. Verified turboQueueAutoAddPublishedPins claim against code
    (column exists, UI toggle exists, no server-side consumer). Added 8 Turbo events to
    PostHog catalog.
  - SC-39: Removed Open Questions (feature flag strategy + ID swap timeline are
    implementation decisions).
  - SC-161: Answered 3 product decisions (paste feed URL directly, daily polling on
    existing cron, no credit cap). Selected UI Option A. Fixed phrasing. Removed Open
    Questions.

- **Extended to Tier 2 card SC-108 (EU invoice information):**
  - User flagged evidence volume numbers were from old pipeline DB, not search index
  - Re-queried search index: ~30-40/month was actually ~4-12/month, 62 total was actually
    795, November "53 spike" was actually 10
  - Answered 4 Open Questions: free-text VAT (no VIES), separate billing company name
    field, forward-only statements, Shopify out of scope
  - Removed prescriptive "Implementation path" from Architecture Context
  - Pushed revised card

## Key Decisions

- Architecture Context standard: descriptive (landscape + gaps), not prescriptive
  (implementation steps). This was caught by the user on SC-44 and applied consistently
  to SC-108.
- Open Questions: product questions must be answered and baked into card sections.
  Implementation questions are the dev's domain and don't belong on cards. Applied to
  SC-39, SC-161, SC-108.
- Evidence volume corrections on SC-108: search index is the authoritative source, not
  pipeline DB. Corrected numbers down significantly but the signal remained clear.
- "No Intercom signal" vs "padded evidence": SC-32 honestly states it's product-initiated
  with no direct user requests for queue automation.

## Carried Forward

- Fill-cards play on remaining Tier 2 cards: SC-90, SC-68, SC-118, SC-131, SC-135,
  SC-132, SC-51
- Tier 3 cards SC-37, SC-38: probably subsumed by SC-39, need archival decision
- Hook coverage gap: MCP tool mutations not gated by PreToolUse hook
- GIN index on conversation_search_index.full_text still needed
