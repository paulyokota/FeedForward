# Last Session

**Date**: 2026-02-14 (morning)
**Branch**: main

## Goal

Day 4 tooling review: step back from investigation work, review the log for
recurring friction, and decide what (if anything) to build.

## What Happened

- Read the full investigation log (1,714 lines, 7 Read calls).
- Identified 7 candidate friction patterns. Verified current state of each
  against live data (DB schema, file contents, MEMORY.md). Found 3 were
  already solved (GIN index exists, .env is clean, Shortcut recipes documented).
- Built 3 things:
  1. **API recipe interception notes**: added "check tooling-logistics.md"
     pointers to the fill-cards pre-flight checklist, Play 4 Phase 1, and
     Play 5 Phase 1. Also added inline-Python-via-Bash gotcha to
     tooling-logistics.md. Sharpened MEMORY.md reference from passive to active.
  2. **Session-scoped temp directory**: `/tmp/ff-YYYYMMDD/` pattern documented
     in tooling-logistics.md, session-end skill updated, MEMORY.md cleanup
     command updated.
  3. **Log index**: table of contents at top of box/log.md mapping 28 sections
     across 3 days to line numbers with one-line key lessons. Original entries
     untouched.
- Captured "note in the right place" as a durable meta-pattern (Process
  Intervention Spectrum in MEMORY.md): three categories of intervention from
  advisory instructions through well-placed notes to deterministic hooks.

## Key Decisions

- "Note in the right place" is a distinct intervention category. Not as strong
  as hooks, but cheaper and sufficient for non-catastrophic tendencies like
  re-deriving documented patterns.
- Log entries are historical snapshots. They don't get updated when the gap
  they describe is filled. The index helps navigate; verifying current state
  before acting on old entries is the instance's job.

## Carried Forward

- SC-175 still needs its fill-cards investigation.
- The session temp directory convention needs to be used in practice to see if
  it actually sticks (new convention, not yet battle-tested).
