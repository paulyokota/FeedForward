# Streaming Batch Pipeline Runbook

**Issue**: #209
**Status**: Available behind feature flag

## Overview

The streaming batch pipeline transforms classification from "fetch-all-then-classify" to a streaming architecture where each batch is processed and checkpointed before moving to the next.

**Key guarantees:**

- Max rework on crash = 1 batch (~50 conversations)
- Memory bounded to 1 batch
- Cursor resume skips already-fetched pages

## Enabling Streaming Batch Mode

```bash
# Enable streaming batch mode
export PIPELINE_STREAMING_BATCH=true

# Optional: Configure batch size (default: 50, range: 10-500)
export PIPELINE_STREAMING_BATCH_SIZE=50
```

## Counter Semantics

> ⚠️ **Important**: Counter semantics differ between streaming and legacy modes.

| Counter      | Legacy Mode                                 | Streaming Mode                       |
| ------------ | ------------------------------------------- | ------------------------------------ |
| `fetched`    | Raw API fetch count (includes filtered)     | Quality conversations entering batch |
| `filtered`   | Conversations filtered during normalization | Always 0 (filtering at page level)   |
| `classified` | Same                                        | Same                                 |
| `stored`     | Same                                        | Same                                 |

**Interpretation:**

- **Legacy**: `fetched` = total API calls, `fetched - filtered` = quality conversations
- **Streaming**: `fetched` = quality conversations directly (no separate filtered count)

When comparing metrics across modes, use `classified` or `stored` for consistent comparisons.

## Resume Behavior

On resume from checkpoint:

1. Stats are seeded from checkpoint counts (cumulative totals)
2. Cursor resumes from last checkpointed position
3. Max rework = conversations in the last incomplete batch

### Cursor Fallback

If the Intercom cursor is invalid on resume (e.g., expired):

- Pipeline restarts from beginning of date range
- Warning logged: "Cursor invalid on resume, restarted from beginning"
- Already-stored conversations are upserted (no duplicates)
- LLM classification re-runs (cost implication)

## Monitoring

### Status API

```bash
curl http://localhost:8000/api/pipeline/{run_id}
```

Response includes checkpoint data:

```json
{
  "checkpoint": {
    "phase": "classification",
    "intercom_cursor": "...",
    "counts": {
      "fetched": 150,
      "classified": 145,
      "stored": 140
    }
  }
}
```

### Log Messages

Key log messages to watch:

- `Starting streaming batch pipeline (Issue #209)` - Mode enabled
- `Processing batch N: X conversations` - Batch in progress
- `Batch N complete: classified=X, stored=Y` - Batch finished
- `Stop signal at batch boundary` - Graceful shutdown
- `Cursor fallback: invalid cursor` - Resume cursor expired

## Troubleshooting

### "Stopped during fetch with N buffered"

This warning appears when pipeline is stopped mid-batch. The buffered conversations will be refetched on next run - no data loss.

### Low `fetched` counts

In streaming mode, `fetched` only counts quality conversations. This is expected to be lower than legacy mode's raw fetch count.

### Resume shows 0 counts initially

Verify checkpoint structure includes `counts` dict:

```json
{
  "phase": "classification",
  "counts": { "fetched": N, "classified": N, "stored": N }
}
```

## Rollback

To disable streaming batch mode and use legacy pipeline:

```bash
unset PIPELINE_STREAMING_BATCH
# or
export PIPELINE_STREAMING_BATCH=false
```

The legacy path remains unchanged and will be used when the flag is off.
