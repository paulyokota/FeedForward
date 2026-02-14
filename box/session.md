# Last Session

**Date**: 2026-02-13 (evening)
**Branch**: main

## Goal

Complete Tier 2 quality gate pass on all 7 remaining Ready to Build cards. Two
Claude instances running in parallel, coordinating via agenterminal conversation
thread 8WJC695.

## What Happened

**Setup**: Split 7 cards by product area:

- Claude 1 (SmartPin cluster): SC-135, SC-51, SC-68, SC-132
- Claude 2 (mixed bag): SC-90, SC-118, SC-131

All 7 cards shipped. Both instances completed their assignments.

### Claude 1 Cards (SmartPin cluster)

- **SC-135** (Bug: toast covers pause/resume indicator): Lean bug template. Traced
  the z-index conflict: Chakra toast portal at ~1300 vs Header at document flow.
  Pause/Resume button sits in Header `right` slot, toast renders in top-right
  portal on top. No story links needed (standalone bug).

- **SC-51** (Save default Premium style): Full feature template. Hardcoded
  `designTier: "basic"` in create.tsx, no account-level preference storage. Card
  had claimed "follow default images pattern" but no such pattern exists: corrected.
  Zero Intercom demand (product-initiated, SmartPin v2 not live). Added 3 story
  links: SC-130, SC-132, SC-99.

- **SC-68** (Bulk SmartPin activation): Full feature template. Single-URL creation
  via Scooby scraper. Bulk generation endpoint exists (queue-smartpins-mfy) but
  no bulk creation. Charlotte blog import is separate infrastructure. Zero Intercom
  demand. Added 2 story links: SC-45, SC-85.

- **SC-132** (Logos/watermarks in SmartPins): Full feature template. Brand
  preferences exist in Create product (logo upload, picker, discriminated union
  BrandingOption) but zero connection to SmartPin generation pipeline. Premium
  canvas compositing via Jimp exists and could be extended. Found Fin AI
  hallucination: conversation 215472992737269 where Fin told a user SmartPins use
  brand logos. They don't. Documented as evidence.

### Claude 2 Cards

- **SC-90** (Create Pin from URL experience): Full feature template. Mapped URL
  scraper, Scooby V2, image selector, Ghostwriter, keywords. Saved domain/sitemap
  identified as only genuinely new infrastructure needed.

- **SC-118** (Speed up keyword search for URLs): Full feature template. 5-stage
  pipeline breakdown with timing estimates. Bottleneck: 74-111 typeahead requests
  in get-suggested-search-phrases.ts.

- **SC-131** (Clarify that Title is Pin Title, not text overlay): Full feature
  template. Label in title-field.tsx:16 vs pin-title-field.tsx:32. Found hook
  urllib bypass (production mutation gate wasn't catching urllib.request patterns).
  Fixed the hook.

## Key Decisions

- Two-instance parallel pattern works. Product-area clustering is the right split
  axis: shared architecture knowledge compounds within each instance.
- SmartPin v2 features have no Intercom signal because they're not shipped yet.
  Stated honestly on all 4 SmartPin feature cards rather than padding evidence.
- Fin AI hallucination (telling users logos apply to SmartPins) is a new evidence
  category: not demand, but active damage from the feature gap.
- Brainstorming/In Definition cards keep owners assigned (learned from SC-118
  when Paul denied unassigning owners).

## Carried Forward

(none)
