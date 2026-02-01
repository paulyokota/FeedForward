# Last Session Summary

**Date**: 2026-02-01
**Issue**: #205 - Full Historical Backfill Blockers

## Accomplishments

### Merged PRs

| PR   | Blockers | Summary                                            |
| ---- | -------- | -------------------------------------------------- |
| #207 | 5+6      | `/history` endpoint parity + schema sync           |
| #208 | 2        | 429 rate limiting with Retry-After + runtime knobs |

### Key Changes

**Rate Limit Handling (Blocker 2):**

- Added 429 to `RETRYABLE_STATUS_CODES`
- Retry-After parsing (seconds and HTTP-date formats)
- Jitter (0-50%) to prevent thundering herd
- Runtime knobs now enforced (not just declared)

**Observability (Blockers 5+6):**

- Added `embeddings_failed`, `facets_failed` to `/history`
- Regenerated `schema.sql` from live database

## Key Decisions

1. **PR Split**: Original PR #206 split into focused PRs per Codex review
2. **Blocker 1 Deferred**: Cursor-based resume needs streaming batch architecture
3. **Knobs Enforced**: FETCH_CONCURRENCY, PER_PAGE, MAX_RPS now actually used

## Lessons Learned

- **Codex review adds value**: Caught that runtime knobs were declared but not enforced
- **Split PRs when advised**: Separating concerns makes review and merge easier
- **Don't implement half-measures**: Blocker 1's cursor logic was unsafe with fetch-all architecture

## Deferred Work

**Blocker 1 (True Batch-Level Resume):**

- Current architecture fetches ALL conversations before classification
- Cursor saved at end-of-fetch is unsafe for resume
- Needs full streaming batch loop: fetch batch → classify → store → checkpoint → repeat
- Filed as follow-on work for Issue #205

## Next Steps

1. Blocker 1 implementation (streaming batch architecture)
2. Or move to other priorities - pipeline is now rate-limit safe for backfills

---

_Session completed: 2026-02-01_
