# Last Session

**Date**: 2026-02-11
**Branch**: main

## Goal

Fill-cards play: SC-150 (multi-language AI generation), plus process improvements.

## What Happened

- Completed SC-150 card: "Allow users to set a language for all AI generation"
  - Gathered fresh Intercom API evidence (111 conversations, 104 contacts)
  - Refreshed PostHog reach numbers (~4,270 non-English AI feature users)
  - Discovered `user_accounts.language` does NOT exist (corrected from earlier investigation)
  - Iterated through three drafts before arriving at approved content
  - Card is in "In Definition" on Shortcut with CSV evidence attached
- Process improvements from SC-150 lessons:
  - Reframed fill-cards play goal: "approved draft" not "pushed card"
  - Added verification bar to fill-cards play (schema reads, file checks, write path traces)
  - Added "Shortcut as Production Surface" rules to MEMORY.md
  - Added "respond before acting" as first communication rule
  - Revised subagent usage: broad mapping only, direct reads for card claims
- Fixed MEMORY.md: removed incorrect `user_accounts.language`/`.locale` claim
- Added v2 settings page location to MEMORY.md
- Extensive log entries for SC-150 investigation

## Key Decisions

- Language preference should be explicit (not auto-detected) due to bidirectional intent
- UI location: rename Ghostwriter tab to "AI Settings" in v2 settings page
- Fill-cards play goal is an approved draft, pushing is a separate step
- Explore subagents for orientation, direct file reads for claims on cards
- Process improvements are justified by repeated failures, but Skills/automation can wait until patterns stabilize

## Carried Forward

- Fill-cards play continues with remaining cards from the ranked list
- AgenTerminal session to resume (crashed during this session, fixed)
