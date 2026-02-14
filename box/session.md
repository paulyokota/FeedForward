# Last Session

**Date**: 2026-02-14 (afternoon)
**Branch**: main

## Goal

Fill-cards play: batch of 3 Keyword Research cards (SC-176, SC-175, SC-174) that
share Saved Keywords page architecture. Test the "cluster by product area" pattern
from a single instance.

## What Happened

- Pre-flight: temp dir, Intercom index refresh, PostHog event catalog review,
  architecture exploration via Explore subagent. Verified subagent claims by reading
  the actual files (keyword-table.tsx, saved/page.tsx, search/page.tsx, route.ts,
  types.ts, score-dots.tsx, score-utils.ts, generate-resonance-description.ts,
  pinterest-interests.sql.ts).
- **SC-176** (Pinterest search link-out): Internally originated, no Intercom demand.
  Architecture context: URL column already renders keyword.urls, MdOpenInNew icon
  already in codebase (27 files). Approved, pushed, story links created.
- **SC-175** (commercial intent indicator on Saved Keywords): Key finding: shopping
  intent is intrinsic to a keyword (stored in pinterest_interests.shoppingIntentScore),
  while resonance requires search-context-specific graph relevance data. This means
  shopping intent CAN be shown on Saved Keywords without the full resonance
  infrastructure. Cross-database gap: org_keywords in MySQL, pinterest_interests in
  Postgres (keyed by name varchar(255)). No Intercom demand. Approved, pushed, story
  links created.
- **SC-174** (URL tooltip on Saved Keywords): Lightest card. URL column at lines
  485-486 renders plain text count, Tooltip already imported (line 20), edit modal
  already wired. Approved, pushed, story links verified (already existed from SC-175
  and SC-176 pushes).
- Retrospective on retries: SQL NOTICE messages, shell/Python variable scope in loops,
  overly broad Intercom searches for internally originated ideas.
- Logged durable learnings: SQL notice suppression recipe in queries.md, brainstorm-
  origin evidence pattern and SQL notice tactic in MEMORY.md.

## Key Decisions

- Cluster-by-product-area fill-cards works well from a single instance. Architecture
  context from SC-176 directly fed SC-175 and SC-174. Each card took less time than
  the previous.
- "Internally originated, no user demand" is an honest evidence framing for cards
  created from a brainstorm session. Don't waste cycles searching Intercom for signal
  that won't be there.
- Shopping intent vs resonance distinction is architecturally significant: intrinsic
  properties can surface on Saved Keywords, search-context-dependent ones cannot.

## Carried Forward

- SC-173 (edit keyword modal redesign) was deferred from this batch to manage context.
  It's the largest of the four and involves modal changes.
- 19 more In Definition cards remain across SmartPin, Turbo, Pin Scheduler, Meta
  product areas.
