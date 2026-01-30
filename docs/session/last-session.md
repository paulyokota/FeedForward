# Last Session Notes

## Date: 2026-01-30

## Session: Post-Milestone 10 Pipeline Validation

### Objective

Run full 30-day pipeline to validate Milestone 10 (Evidence Bundle Improvements) changes in production-like conditions.

### What Happened

1. **Started servers fresh** - Killed stale Next.js (running since Jan 22), restarted both API (8000) and frontend (3000)

2. **Ran pipeline** - `./scripts/dev-pipeline-run.sh --days 30`
   - Pre-flight checks passed
   - Cleanup removed 402 orphans, 15 stories, 543 themes from previous run

3. **Pipeline completed** (~55 min):
   - ✅ 1,530 conversations classified
   - ✅ 593 themes extracted
   - ✅ 12 appropriately filtered as `unclassified_needs_review` (Dutch content, vague follow-ups, general feedback)
   - ❌ 0 stories created
   - ❌ 0 orphans created

4. **Discovered cascade failure** in story creation phase:
   - First error: duplicate key violation on `story_orphans.signature`
   - Orphan graduated to story, then code tried to re-insert with same signature
   - Transaction not rolled back → all subsequent operations failed

### Issues Filed

| Issue | Title                                                                             | Priority      |
| ----- | --------------------------------------------------------------------------------- | ------------- |
| #175  | API `/api/stories` returns fewer stories than exist in database                   | Bug           |
| #176  | Story creation fails: duplicate orphan signature causes cascade transaction abort | Bug (Blocker) |

### Root Cause Analysis (#176)

```
Sequence:
1. Orphan created with signature X
2. Conversations added (1, 2, 3)
3. Orphan graduated to story ✅
4. Code tried to insert ANOTHER orphan with signature X → BOOM
5. No rollback → cascade failure
```

### Suggested Fixes

1. **Use upsert**: `ON CONFLICT (signature) DO UPDATE`
2. **Clean up after graduation**: Don't re-insert; attach to existing orphan if needed
3. **Add savepoints**: Isolate cluster processing failures

### Key Observations

- Theme extraction working well (593 themes from 1,530 conversations)
- `unclassified_needs_review` filter correctly catching ambiguous content (~2%)
- Pipeline status API counters don't update during Intercom fetch phase (minor bug)
- Story creation is the critical path blocker

### Next Session

1. Fix #176 (story creation cascade failure)
2. Re-run pipeline validation
3. Review story quality and grouping results

### Files Changed

- `docs/status.md` - Updated blockers, what's next, session notes
- `docs/session/last-session.md` - This file
