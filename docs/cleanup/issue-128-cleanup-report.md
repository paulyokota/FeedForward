# Issue #128: Clean Slate - Delete Data from Broken Pipeline Runs

**Date**: 2026-01-23
**Status**: Analysis Complete - DELETION SCRIPT READY (NOT EXECUTED)

## Executive Summary

Pipeline runs where `HYBRID_CLUSTERING_ENABLED=true` (the default) had a bug where PM Review was never initialized. This analysis identifies affected data and provides deletion queries.

**Key Finding**: The bug prevented story creation entirely. There are **0 stories** with `grouping_method = 'hybrid_cluster'` in the database. The main artifacts to clean up are:

- 19 orphans created without proper PM review
- 22 themes from affected runs
- 5 failed/incomplete pipeline run records

## Affected Pipeline Runs

| Run ID | Status    | Phase          | Started          | Themes | Stories | Orphans | Issue                                   |
| ------ | --------- | -------------- | ---------------- | ------ | ------- | ------- | --------------------------------------- |
| 72     | completed | completed      | 2026-01-23 07:49 | 21     | 0       | 19      | PM review skipped, only orphans created |
| 71     | failed    | story_creation | 2026-01-23 07:44 | 21     | 0       | 0       | code_context column missing             |
| 70     | failed    | story_creation | 2026-01-23 07:37 | 22     | 0       | 0       | code_context column missing             |
| 69     | failed    | story_creation | 2026-01-23 07:32 | 22     | 0       | 0       | code_context column missing             |
| 67     | completed | completed      | 2026-01-23 07:17 | 36     | 0       | 13      | PM review skipped, only orphans created |

**Affected Run IDs**: `[72, 71, 70, 69, 67]`

## Records to Delete

| Table                 | Count | Notes                                       |
| --------------------- | ----- | ------------------------------------------- |
| `stories`             | 0     | No hybrid_cluster stories exist             |
| `story_evidence`      | 0     | No evidence records to delete               |
| `story_comments`      | 0     | No comments to delete                       |
| `story_sync_metadata` | 0     | No sync metadata to delete                  |
| `story_orphans`       | 19    | All active orphans created since 2026-01-22 |
| `themes`              | 22    | Themes from affected runs (run_ids 70, 72)  |

## Records to Update (Not Delete)

| Table           | Count | Action                                                    |
| --------------- | ----- | --------------------------------------------------------- |
| `conversations` | 2     | Set `pipeline_run_id = NULL` (preserve conversation data) |
| `pipeline_runs` | 5     | Keep for audit trail, update status to indicate cleanup   |

## Orphans to Delete (19 total)

All orphans were created on 2026-01-23 without PM review validation:

| Signature                                     | Conversations |
| --------------------------------------------- | ------------- |
| account_email_sender_error                    | 1             |
| account_settings_guidance                     | 1             |
| analytics_counter_bug                         | 1             |
| analytics_interpretation_question             | 1             |
| analytics_keyword_usage_question              | 1             |
| billing_credits_usage_query                   | 2             |
| create_image_loading_failure                  | 1             |
| csv_import_description_corruption             | 1             |
| ghostwriter_generation_failure                | 1             |
| ghostwriter_pin_readdition_error              | 1             |
| multi_network_scheduling_tiktok_not_available | 1             |
| pinterest_connection_status_query             | 1             |
| pinterest_missing_image                       | 2             |
| pinterest_missing_pins                        | 1             |
| scheduling_bulk_cancel_request                | 1             |
| scheduling_feature_question                   | 1             |
| scheduling_pin_title_not_carrying_over        | 1             |
| smartpins_deletion_guidance                   | 1             |
| tailwind_create_image_import_guidance         | 1             |

---

## SQL Deletion Script

**WARNING**: Review carefully before executing. Run in a transaction for safety.

```sql
-- ============================================================
-- Issue #128: Clean Slate Deletion Script
-- Generated: 2026-01-23
--
-- INSTRUCTIONS:
-- 1. Review this script carefully
-- 2. Take a database backup first: pg_dump feedforward > backup.sql
-- 3. Run in a transaction (BEGIN/COMMIT) for safety
-- 4. Verify counts match expected values before COMMIT
-- ============================================================

BEGIN;

-- ============================================================
-- STEP 1: Delete story-related records (dependency order)
-- ============================================================

-- 1a. Delete story_sync_metadata for affected stories
-- (Currently 0 records, but included for completeness)
DELETE FROM story_sync_metadata
WHERE story_id IN (
    SELECT id FROM stories
    WHERE pipeline_run_id IN (72, 71, 70, 69, 67)
       OR grouping_method = 'hybrid_cluster'
);
-- Expected: 0 rows

-- 1b. Delete story_comments for affected stories
DELETE FROM story_comments
WHERE story_id IN (
    SELECT id FROM stories
    WHERE pipeline_run_id IN (72, 71, 70, 69, 67)
       OR grouping_method = 'hybrid_cluster'
);
-- Expected: 0 rows

-- 1c. Delete story_evidence for affected stories
DELETE FROM story_evidence
WHERE story_id IN (
    SELECT id FROM stories
    WHERE pipeline_run_id IN (72, 71, 70, 69, 67)
       OR grouping_method = 'hybrid_cluster'
);
-- Expected: 0 rows

-- 1d. Delete stories from affected runs or with hybrid_cluster method
DELETE FROM stories
WHERE pipeline_run_id IN (72, 71, 70, 69, 67)
   OR grouping_method = 'hybrid_cluster';
-- Expected: 0 rows

-- ============================================================
-- STEP 2: Delete orphans created during buggy period
-- ============================================================

-- Delete all orphans created since hybrid clustering was introduced
-- These were created without PM review validation
DELETE FROM story_orphans
WHERE first_seen_at >= '2026-01-22 00:00:00'
  AND graduated_at IS NULL;
-- Expected: 19 rows

-- ============================================================
-- STEP 3: Delete themes from affected runs
-- ============================================================

DELETE FROM themes
WHERE pipeline_run_id IN (72, 71, 70, 69, 67);
-- Expected: 22 rows

-- ============================================================
-- STEP 4: Unlink conversations (preserve data, remove run association)
-- ============================================================

UPDATE conversations
SET pipeline_run_id = NULL
WHERE pipeline_run_id IN (72, 71, 70, 69, 67);
-- Expected: 2 rows updated

-- ============================================================
-- STEP 5: Mark pipeline runs as cleaned (optional - for audit trail)
-- ============================================================

-- Option A: Delete the run records entirely
-- DELETE FROM pipeline_runs WHERE id IN (72, 71, 70, 69, 67);

-- Option B: Update to indicate they were cleaned (recommended)
UPDATE pipeline_runs
SET
    status = 'failed',
    error_message = COALESCE(error_message || ' | ', '') || 'CLEANED: Issue #128 - Data deleted due to hybrid clustering PM review bug'
WHERE id IN (72, 71, 70, 69, 67);
-- Expected: 5 rows updated

-- ============================================================
-- VERIFICATION QUERIES (run before COMMIT)
-- ============================================================

-- Verify no hybrid_cluster stories remain
SELECT COUNT(*) AS hybrid_stories_remaining
FROM stories
WHERE grouping_method = 'hybrid_cluster';
-- Expected: 0

-- Verify orphans deleted
SELECT COUNT(*) AS recent_orphans_remaining
FROM story_orphans
WHERE first_seen_at >= '2026-01-22 00:00:00'
  AND graduated_at IS NULL;
-- Expected: 0

-- Verify themes deleted
SELECT COUNT(*) AS affected_themes_remaining
FROM themes
WHERE pipeline_run_id IN (72, 71, 70, 69, 67);
-- Expected: 0

-- ============================================================
-- COMMIT only after verifying counts
-- ============================================================

-- If all looks good:
COMMIT;

-- If something is wrong:
-- ROLLBACK;
```

---

## Alternative: Minimal Cleanup (Orphans Only)

If you want to preserve themes and just clean up orphans that bypassed PM review:

```sql
BEGIN;

-- Delete only the orphans (least invasive)
DELETE FROM story_orphans
WHERE first_seen_at >= '2026-01-22 00:00:00'
  AND graduated_at IS NULL;
-- Expected: 19 rows

-- Verify
SELECT COUNT(*) FROM story_orphans WHERE first_seen_at >= '2026-01-22 00:00:00';
-- Expected: 0

COMMIT;
```

---

## Post-Cleanup Verification

After running the cleanup, verify with:

```sql
-- Check stories table is clean
SELECT grouping_method, COUNT(*)
FROM stories
GROUP BY grouping_method;

-- Check orphans are cleaned
SELECT COUNT(*) FROM story_orphans WHERE graduated_at IS NULL;

-- Check themes status
SELECT pipeline_run_id, COUNT(*)
FROM themes
WHERE pipeline_run_id IS NOT NULL
GROUP BY pipeline_run_id;

-- Check pipeline runs status
SELECT id, status, error_message
FROM pipeline_runs
WHERE id IN (72, 71, 70, 69, 67);
```

---

## Warnings and Considerations

1. **Backup First**: Always take a database backup before running deletion queries

   ```bash
   pg_dump feedforward > feedforward_backup_$(date +%Y%m%d).sql
   ```

2. **Conversation Data Preserved**: Conversations are NOT deleted, only unlinked from runs. This preserves the raw classification data.

3. **Themes Deletion**: Themes from affected runs will be deleted. These can be regenerated by running a new pipeline.

4. **Orphan Signatures**: The 19 orphan signatures will be lost. If these represent valid patterns, they will be recreated on the next pipeline run with proper PM review.

5. **Run Records**: Pipeline run records are marked as cleaned rather than deleted for audit purposes.

---

## Related Issues

- Issue #128: Clean slate: Delete data from broken pipeline runs
- Root cause: PM Review service not initialized when `HYBRID_CLUSTERING_ENABLED=true`
