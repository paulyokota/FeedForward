# Plan: Issue #256 — DB Persistence for Discovery Runs

## Problem Analysis

The discovery pipeline currently writes to Postgres via `DiscoveryStorage` (runs, stages, artifacts), but the `run_discovery.py` script sets `autocommit=False` and **never commits**. When the script exits, all uncommitted data is lost. The API endpoint (`POST /api/discovery/runs`) auto-commits via `get_db()`, but `run_discovery.py` doesn't use that path.

Additionally, `submit_checkpoint()` relies on the state machine's `advance_stage()` to persist artifacts. There's no explicit, dedicated method for saving stage artifacts independently.

## Solution

Three changes, all additive:

### 1. Add `save_stage_artifacts()` to `DiscoveryStorage` (storage.py)

```python
def save_stage_artifacts(
    self,
    run_id: UUID,
    stage_execution_id: int,
    artifacts: Dict[str, Any],
) -> None:
    """Persist stage artifacts to the stage_executions JSONB column.

    Overwrites the entire artifacts JSONB (not a merge). This is an
    explicit persistence call, separate from update_stage_status().
    Used by ConversationService.submit_checkpoint() to ensure artifacts
    are persisted alongside the transport write.
    """
    with self._cursor() as cur:
        cur.execute(
            """
            UPDATE stage_executions
            SET artifacts = %s
            WHERE id = %s AND run_id = %s
            """,
            (json.dumps(artifacts), stage_execution_id, str(run_id)),
        )
```

Why `run_id` in the WHERE clause: defense-in-depth — prevents accidentally writing artifacts to a stage belonging to a different run.

Also add `save_stage_artifacts()` to `InMemoryStorage` test implementations (in `test_state_machine.py` and `test_conversation_service.py`) so that `ConversationService` doesn't hit a runtime `AttributeError` when calling the method on the injected storage. The `InMemoryStorage` implementation simply sets `self.stage_executions[stage_execution_id].artifacts = artifacts` after verifying `run_id` matches.

### 2. Call `save_stage_artifacts()` from `ConversationService.submit_checkpoint()` (conversation.py)

Insert after artifact validation, before posting the checkpoint event:

```python
# Persist artifacts to storage (explicit write, separate from state machine)
self.storage.save_stage_artifacts(
    run_id, active_stage.id, artifacts
)
```

Also add the same call to `complete_with_checkpoint()` for the final stage.

### 3. Add `db.commit()` to `run_discovery.py`

After `orchestrator.run()` returns, commit the transaction. Wrap the run in try/except/finally:

```python
try:
    run = orchestrator.run(config=config)
    conn.commit()  # Persist all discovery data to Postgres
except Exception as e:
    conn.rollback()  # Don't persist inconsistent partial state
    raise
finally:
    conn.close()
```

The existing `conn.close()` call later in the script gets removed since `finally` now handles it. Default is rollback on failure — partial runs are not persisted to avoid inconsistent data. A future `--commit-partial` flag could be added if debugging needs arise.

The Postgres `save_stage_artifacts()` will check `cur.rowcount` after the UPDATE and log a warning if no row was updated (which would mean the stage_execution_id/run_id combination doesn't exist). This catches silent no-ops. The method is called after `get_active_stage()` already confirmed the stage exists, so a rowcount of 0 would indicate a bug, not a normal condition.

**Interface note:** `DiscoveryStorage` is a concrete class (not a Protocol or ABC). The `InMemoryStorage` classes in test files are duck-typed fakes — they just need the new method added. No interface definition needs updating.

**Column note:** `stage_executions` has no `updated_at`/`modified_at` column, so `save_stage_artifacts()` only touches the `artifacts` JSONB column.

## Files Modified

| File                                           | Change                                                                                  |
| ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| `src/discovery/db/storage.py`                  | Add `save_stage_artifacts()` method                                                     |
| `src/discovery/services/conversation.py`       | Call `save_stage_artifacts()` in `submit_checkpoint()` and `complete_with_checkpoint()` |
| `scripts/run_discovery.py`                     | Add `conn.commit()` with try/except/finally pattern                                     |
| `tests/discovery/test_state_machine.py`        | Add `save_stage_artifacts()` to `InMemoryStorage`                                       |
| `tests/discovery/test_conversation_service.py` | Add `save_stage_artifacts()` to `InMemoryStorage` + new persistence tests               |

## Tests

1. **Unit test: `save_stage_artifacts()` writes correct JSONB** — Verify artifacts are stored on the stage execution object via InMemoryStorage.

2. **Unit test: `save_stage_artifacts()` no-op on wrong run_id** — Call with a mismatched run_id, verify artifacts are NOT stored (defense-in-depth check). Postgres version logs a warning.

3. **Unit test: `submit_checkpoint()` persists artifacts** — Verify that submit_checkpoint calls save_stage_artifacts before advancing the state machine.

4. **Unit test: `complete_with_checkpoint()` persists artifacts** — Verify the final-stage path also persists artifacts before completing.

5. **Unit test: Two run isolation** — Call `save_stage_artifacts()` with two different run_ids, verify each run's data is independent.

6. **Existing test: `test_submit_checkpoint_advances_stage`** — Already verifies artifacts end up on completed stages. Should pass unchanged.

All tests use InMemoryStorage (no real DB needed) following existing patterns.

## What's NOT changing

- `InMemoryTransport` — untouched, continues working for conversation messages
- Transport interface — no changes
- Orchestrator stage progression logic — no changes
- DB migrations — existing columns are sufficient
- API endpoints — already work, just need data in the DB

## Risk Assessment

Low. The `save_stage_artifacts()` call is additive — artifacts were already being persisted via `advance_stage()` → `update_stage_status()`. This adds a second write (belt-and-suspenders) that happens earlier in the checkpoint flow, before the state machine transition. The commit in `run_discovery.py` is the actual fix for data loss.
