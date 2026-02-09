# Full Historical Backfill (Streaming Batch Mode)

## Preconditions
- Merged: streaming batch resume + rate‑limit handling
- `PIPELINE_STREAMING_BATCH=true` support
- DB backup/snapshot taken
- No active run: `GET /api/pipeline/active` is empty

## Safe Defaults
```
PIPELINE_STREAMING_BATCH=true
PIPELINE_STREAMING_BATCH_SIZE=50
INTERCOM_FETCH_CONCURRENCY=10
INTERCOM_PER_PAGE=50
INTERCOM_MAX_RPS=2
```

## One‑Command Run (uses .env)
```
bash -lc '
  set -euo pipefail
  set +x
  set -a
  source .env
  set +a

  export PIPELINE_STREAMING_BATCH=true
  export PIPELINE_STREAMING_BATCH_SIZE=50
  export INTERCOM_FETCH_CONCURRENCY=10
  export INTERCOM_PER_PAGE=50
  export INTERCOM_MAX_RPS=2

  pgrep -f "uvicorn src.api.main:app" >/dev/null || \
    (uvicorn src.api.main:app --port 8000 > /tmp/ff_backfill.log 2>&1 & sleep 5)

  RUN_ID=$(curl -s -X POST http://localhost:8000/api/pipeline/run \
    -H "Content-Type: application/json" \
    -d "{\"days\": 3650, \"auto_create_stories\": false}" | jq -r .run_id)

  echo "Backfill started. run_id=$RUN_ID"

  while true; do
    STATUS=$(curl -s http://localhost:8000/api/pipeline/status/$RUN_ID | jq -r .status)
    echo "$(date) status=$STATUS"
    curl -s http://localhost:8000/api/pipeline/status/$RUN_ID | \
      jq "{current_phase, conversations_fetched, conversations_classified, conversations_stored, warnings}"
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "stopped" ]; then
      break
    fi
    sleep 30
  done
'
```

## Resume
```
curl -X POST http://localhost:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"resume": true, "resume_run_id": RUN_ID}'
```

## Notes
- Streaming mode `conversations_fetched` counts quality conversations (post‑filter).
- If rate‑limited, lower `INTERCOM_MAX_RPS` or `INTERCOM_FETCH_CONCURRENCY` and resume.
