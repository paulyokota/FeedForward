# Last Session

**Date**: 2026-02-11
**Branch**: main

## Goal

Fill-cards play: investigate and flesh out Shortcut cards, moving them from In Definition to Ready to Build.

## What Happened

- **SC-44** (SmartPin frequency selector): traced schedule_rule storage (RFC 5545 RRule, hardcoded WEEKLY), SmartPin v2 UI (create.tsx, edit.tsx, neither has frequency control), cron infrastructure. User feedback mid-investigation redirected from old UI to v2 paths. Pushed, moved to Ready to Build.
- **SC-156** (SmartPin edits lost after scheduling): deep code trace across 10+ files. Identified probable root cause: `handlePinDesignChange` in `pin-grid-item.tsx` sends stale `draft` prop instead of merging form values (compare with `handleMediaChange` which does it correctly). Secondary issue: design modal's full-object PATCH overwrites autosaved changes. Card was already in Ready to Build, fleshed out and cleared owners.
- **SC-158** (Chrome Extension alt text): discovered two extension codebases (Turbo = Pinterest engagement, bookmarklet = save from web pages). Bookmarklet already reads `img.alt` but routes it to `description` field, not `altText`. Server-side `altText` plumbing exists (`NewPinterestPin`, `TackRepository.create()`) but `ExtensionDraftData` and API schema don't have the field. Pushed, moved to Ready to Build.

## Key Decisions

- Evidence sections should contain only conversations about the actual feature, not adjacent themes
- Don't mention irrelevant codebases just to say they're not relevant
- Open questions that are product calls of "no" for v1 should be dropped, not left open on Ready to Build cards
- Architectural notes that aren't questions belong in Architecture Context, not Open Questions

## Carried Forward

- Fill-cards play continues with remaining In Definition cards: SC-97, SC-101, SC-130 identified as candidates
- 25 total In Definition cards remain (minus the 2 moved this session)
