# Intercom Backfill Runbook

This document describes how to run and recover from long-running Intercom conversation backfills.

## Pre-flight Checks

Before starting a backfill:

- [ ] `INTERCOM_ACCESS_TOKEN` present in `.env`
- [ ] Database connectivity verified
- [ ] No active pipeline run (check `/api/pipeline/active`)

```bash
# Verify token is set
grep INTERCOM_ACCESS_TOKEN .env

# Check for active runs
curl http://localhost:8000/api/pipeline/active
```

## Starting a Backfill

```bash
# Start a 90-day backfill with automatic story creation
curl -X POST "http://localhost:8000/api/pipeline/run" \
  -H "Content-Type: application/json" \
  -d '{"days": 90, "auto_create_stories": true}'

# Response includes run_id for monitoring
# {"run_id": 42, "status": "started", "message": "..."}
```

## Monitoring Progress

Poll the status endpoint to track progress:

```bash
curl "http://localhost:8000/api/pipeline/status/{run_id}"
```

The response includes:

- `current_phase`: Current pipeline phase (classification, embedding_generation, facet_extraction, theme_extraction, story_creation)
- `conversations_fetched`: Conversations retrieved from Intercom
- `conversations_classified`: Conversations processed by classifier
- `conversations_stored`: Conversations written to database
- `checkpoint`: Current checkpoint data (for observability)

## Resuming After Interruption

If a run is interrupted (stop signal, crash, network failure), you can resume from the last checkpoint.

### Option 1: By date range (same-day resume)

```bash
curl -X POST "http://localhost:8000/api/pipeline/run" \
  -H "Content-Type: application/json" \
  -d '{"days": 90, "resume": true}'
```

### Option 2: By explicit run ID (cross-day resume)

Use this when resuming a run that was started on a previous day:

```bash
# First find the interrupted run ID
curl "http://localhost:8000/api/pipeline/history?limit=5"

# Then resume by ID
curl -X POST "http://localhost:8000/api/pipeline/run" \
  -H "Content-Type: application/json" \
  -d '{"resume": true, "resume_run_id": 42}'
```

**WARNING:**

- `resume=true` only works for runs in `stopped`/`failed`/`stopping` status with a non-empty checkpoint
- **Resume uses the ORIGINAL run_id** - monitor the same run_id, not a new one
- When `resume=true` without `resume_run_id`, the `days` parameter is used to find a matching run by date range
- When `resume_run_id` is provided, it bypasses date matching (useful for cross-day resume)
- The run uses the original `date_from`/`date_to` from the interrupted run
- Only classification phase is resumable; runs past classification cannot be resumed (400 error)
- If no matching run found, you'll get a 400 error

## Expected Behavior After Interruption

| Interrupted During                    | On Resume/Restart                                    |
| ------------------------------------- | ---------------------------------------------------- |
| Fetch (before any storage)            | No checkpoint saved → restart from beginning         |
| Storage (has checkpoint)              | Re-fetches from beginning, upsert handles duplicates |
| Between classification and embeddings | Embeddings restart from scratch (expected per MVP)   |
| Embeddings/facets/themes              | Phase restarts from scratch (fast, idempotent)       |

**Important:** Checkpoint is saved AFTER storage batches complete, not during fetch. This prevents data loss: if the process crashes during fetch, no checkpoint exists, so you restart from the beginning (correct). If it crashes during storage, some data is stored and you can resume - the re-fetch will upsert and skip already-stored conversations.

**Note:** Only classification phase is resumable. All later phases are designed to be fast and idempotent.

## Stopping a Run

To gracefully stop an active run:

```bash
curl -X POST "http://localhost:8000/api/pipeline/stop"
```

The run will stop after completing any in-flight operations. A checkpoint is saved for potential resume.

## Recovery

If resume fails, check the checkpoint in the database:

```sql
SELECT id, status, checkpoint, date_from, date_to
FROM pipeline_runs
ORDER BY id DESC
LIMIT 1;
```

Common issues:

- **No checkpoint**: Run completed or never saved a checkpoint (can't resume)
- **Empty checkpoint `{}`**: Classification completed, nothing to resume
- **Phase not classification**: Run progressed past resumable phase
- **Date mismatch**: `days` parameter produces different date range than original run

## Troubleshooting

### "No resumable run found"

This means either:

1. No stopped/failed run exists with matching date range
2. The checkpoint is empty (classification already completed)
3. The checkpoint phase is not "classification"

**Solutions:**

- Use `resume_run_id` to specify the exact run ID (bypasses date matching)
- Or start a fresh run instead of resuming

### Duplicate conversations after resume

This shouldn't happen - conversations are upserted by ID. If you see duplicates:

1. Check that `conversation_id` is unique in the database
2. Verify upsert logic in `store_classification_result`

### Pipeline stuck at 0 conversations

Check:

1. `INTERCOM_ACCESS_TOKEN` is valid and not expired
2. Date range includes conversations (Intercom Search API is date-bounded)
3. No API rate limiting (check logs for 429 errors)
