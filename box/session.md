# Last Session

**Date**: 2026-02-12 (session 4)
**Branch**: main

## Goal

Meta-session: tooling improvements for investigation quality and data access.

## What Happened

- **Verified explore prompt designed and A/B tested.** Created `box/verified-explore-prompt.md`: a custom-prompted general-purpose subagent with mandatory file:line citations, [INFERRED] markers, and structured claims arrays. Tested against built-in Explore agent on AI language handling. Verified agent found the `franc` language detection mechanism the Explore agent missed (false negative). Provisional direction: quality > velocity.

- **Intercom full-text search index designed.** Problem: DB is stale/filtered, API search only hits opening messages. Designed a PostgreSQL full-text search index of complete conversation threads. Two-phase sync (list metadata, then fetch threads). Reuses existing `IntercomClient` and `build_full_conversation_text()`. Schema went through two rounds of Codex review (advisory locks, failed state tracking, NULL semantics, partial indexes). GitHub issue #284 created for issue-runner implementation.

- **Issue backlog cleanup.** Closed 40 pre-pivot issues (pipeline/discovery engine era). Only #284 remains open. Clean issue tracker for targeted build-from-issue work.

- **Science communicator output style updated.** Added two new canonical examples (crane/chair tooling mismatch, mine detector test design).

- **Core principle codified: reasoning over pattern matching.** Decision trees and string matching are never a real substitute for actual reasoning. Applies at every level: keyword search, theme classifiers, explore agents. Saved to MEMORY.md as top-level principle.

## Key Decisions

- Verified explore prompt is provisional direction for broad architecture mapping. Built-in Explore still fine for narrow "where is X?" questions. Claims going on cards still require direct file reads (belt and suspenders).
- Intercom search index: lightweight (ID, dates, email, full text), not a data warehouse. No classification, no pipeline changes. Manual sync for now.
- Issue tracker reset: old issues are closed history, not active backlog.

## Carried Forward

- Issue #284: Intercom full-text search index implementation (issue-runner candidate)
- Quality gate evaluation continues: SC-97, SC-108, remaining ~15 cards
- SC-150, SC-117, SC-46 still need Architecture Context revision passes
- Observe verified explore prompt across more runs, tune if patterns emerge
