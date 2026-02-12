# Last Session

**Date**: 2026-02-12 (session 3)
**Branch**: main

## Goal

Continue quality gate evaluation of Ready to Build cards. Session started post-compaction from session 2.

## What Happened

- **SC-42 (SmartPin text overlay): full investigation completed post-compaction.**
  Restarted from scratch using durable artifacts. Key finding: user's title field saved to DB but never passed to generation pipeline (`MadeForYouSmartPinRequest` schema has no `title` field). 22 verified Intercom conversations (from 50 search matches). Card pushed with orient-not-prescribe Architecture Context.

- **SC-135 (toast covers pause/active indicator): quick quality gate fix.**
  Added done state, changed type from `feature` to `bug`, cleaned up description. No architecture context needed for small UI bug.

- **Dropped Open Questions from card template.** Not a formally defined section. Product questions should be answered and baked in. Implementation questions are the dev's domain. Updated `box/shortcut-ops.md` template and MEMORY.md.

- **Intercom API 401 debugging:** User challenged the pre-compaction assumption that the token was expired. Tested with curl: token works fine (200). The 401 was from a bad API call format, not a bad token. Logged as anti-pattern.

- **PostHog events catalog updated:** 5 new SmartPin events added from SC-42 investigation.

## Key Decisions

- Open Questions section removed from card template. Product decisions baked in; implementation decisions left to dev.
- Architecture Context prescription check: "plumbing exists but doesn't include title" → "keywords flow through schema to generator." Same info, no editorial.
- Bug cards don't need architecture context when the fix is obvious from the description alone (SC-135).

## Carried Forward

- Quality gate evaluation continues: SC-97 next, then SC-108 (needs implementation path prescription fix), then remaining ~15 cards
- SC-150 still needs Architecture Context revised (Bill's original example)
- SC-117 needs orientation-vs-prescription revision pass
- SC-46 Architecture Context may also need revision
