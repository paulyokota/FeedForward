"""Storage layer for Discovery Engine runs, stages, and agent invocations.

Follows the existing FeedForward pattern: service class takes a db_connection,
uses cursors for queries, and relies on the caller to manage commits.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg2.extras import RealDictCursor

from src.discovery.models.enums import (
    AgentStatus,
    RunStatus,
    StageStatus,
    StageType,
)
from src.discovery.models.run import (
    AgentInvocation,
    DiscoveryRun,
    RunConfig,
    RunMetadata,
    StageExecution,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class DiscoveryStorage:
    """CRUD operations for discovery runs, stage executions, and agent invocations.

    Requires a psycopg2 connection with RealDictCursor (all row mappers access by key).
    The standard FeedForward get_db() dependency provides this automatically.
    """

    def __init__(self, db_connection):
        self.db = db_connection

    def _cursor(self):
        """Get a cursor with RealDictCursor to ensure dict-style row access."""
        return self.db.cursor(cursor_factory=RealDictCursor)

    # ========================================================================
    # Discovery Runs
    # ========================================================================

    def create_run(self, run: DiscoveryRun) -> DiscoveryRun:
        """Create a new discovery run. Returns the created run with generated ID."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO discovery_runs (parent_run_id, status, current_stage, config, metadata, errors, warnings)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, parent_run_id, status, current_stage, config, metadata,
                          started_at, completed_at, errors, warnings
                """,
                (
                    str(run.parent_run_id) if run.parent_run_id else None,
                    run.status.value,
                    run.current_stage.value if run.current_stage else None,
                    json.dumps(run.config.model_dump()),
                    json.dumps(run.metadata.model_dump()),
                    json.dumps(run.errors),
                    json.dumps(run.warnings),
                ),
            )
            row = cur.fetchone()
            return self._row_to_run(row)

    def get_run(self, run_id: UUID) -> Optional[DiscoveryRun]:
        """Get a discovery run by ID."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, parent_run_id, status, current_stage, config, metadata,
                       started_at, completed_at, errors, warnings
                FROM discovery_runs
                WHERE id = %s
                """,
                (str(run_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_run(row)

    _UNSET = object()

    def update_run_status(
        self,
        run_id: UUID,
        status: RunStatus,
        current_stage=_UNSET,
        completed_at: Optional[datetime] = None,
    ) -> Optional[DiscoveryRun]:
        """Update run status. current_stage is preserved unless explicitly passed.

        Pass current_stage=StageType.X to set it. Pass current_stage=None to clear it.
        Omit current_stage to preserve the existing value.
        """
        with self._cursor() as cur:
            if current_stage is self._UNSET:
                # Preserve existing current_stage
                cur.execute(
                    """
                    UPDATE discovery_runs
                    SET status = %s, completed_at = COALESCE(%s, completed_at)
                    WHERE id = %s
                    RETURNING id, parent_run_id, status, current_stage, config, metadata,
                              started_at, completed_at, errors, warnings
                    """,
                    (status.value, completed_at, str(run_id)),
                )
            else:
                cur.execute(
                    """
                    UPDATE discovery_runs
                    SET status = %s,
                        current_stage = %s,
                        completed_at = COALESCE(%s, completed_at)
                    WHERE id = %s
                    RETURNING id, parent_run_id, status, current_stage, config, metadata,
                              started_at, completed_at, errors, warnings
                    """,
                    (
                        status.value,
                        current_stage.value if current_stage else None,
                        completed_at,
                        str(run_id),
                    ),
                )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_run(row)

    def update_run_metadata(self, run_id: UUID, metadata: RunMetadata) -> Optional[DiscoveryRun]:
        """Update run metadata."""
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE discovery_runs
                SET metadata = %s
                WHERE id = %s
                RETURNING id, status, current_stage, config, metadata,
                          started_at, completed_at, errors, warnings
                """,
                (json.dumps(metadata.model_dump()), str(run_id)),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_run(row)

    def append_run_error(self, run_id: UUID, error: Dict[str, Any]) -> None:
        """Append an error to the run's error list."""
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE discovery_runs
                SET errors = errors || %s::jsonb
                WHERE id = %s
                """,
                (json.dumps([error]), str(run_id)),
            )

    def list_runs(
        self, status: Optional[RunStatus] = None, limit: int = 50
    ) -> List[DiscoveryRun]:
        """List discovery runs, optionally filtered by status."""
        with self._cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT id, parent_run_id, status, current_stage, config, metadata,
                           started_at, completed_at, errors, warnings
                    FROM discovery_runs
                    WHERE status = %s
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (status.value, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, parent_run_id, status, current_stage, config, metadata,
                           started_at, completed_at, errors, warnings
                    FROM discovery_runs
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            return [self._row_to_run(row) for row in cur.fetchall()]

    def get_child_runs(self, parent_run_id: UUID) -> List[DiscoveryRun]:
        """Get all re-entry runs that have the given run as their parent."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, parent_run_id, status, current_stage, config, metadata,
                       started_at, completed_at, errors, warnings
                FROM discovery_runs
                WHERE parent_run_id = %s
                ORDER BY started_at ASC NULLS LAST
                """,
                (str(parent_run_id),),
            )
            return [self._row_to_run(row) for row in cur.fetchall()]

    # ========================================================================
    # Stage Executions
    # ========================================================================

    def create_stage_execution(self, stage_exec: StageExecution) -> StageExecution:
        """Create a new stage execution record."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO stage_executions (
                    run_id, stage, status, attempt_number, participating_agents,
                    artifacts, artifact_schema_version,
                    conversation_id, sent_back_from, send_back_reason, started_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, run_id, stage, status, attempt_number,
                          participating_agents, artifacts, artifact_schema_version,
                          conversation_id, sent_back_from, send_back_reason,
                          started_at, completed_at
                """,
                (
                    str(stage_exec.run_id),
                    stage_exec.stage.value,
                    stage_exec.status.value,
                    stage_exec.attempt_number,
                    stage_exec.participating_agents,
                    json.dumps(stage_exec.artifacts) if stage_exec.artifacts is not None else None,
                    stage_exec.artifact_schema_version,
                    stage_exec.conversation_id,
                    stage_exec.sent_back_from.value if stage_exec.sent_back_from else None,
                    stage_exec.send_back_reason,
                    stage_exec.started_at,
                ),
            )
            row = cur.fetchone()
            return self._row_to_stage_execution(row)

    def get_stage_execution(self, execution_id: int) -> Optional[StageExecution]:
        """Get a stage execution by ID."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, run_id, stage, status, attempt_number,
                       participating_agents, artifacts, artifact_schema_version,
                       conversation_id, sent_back_from, send_back_reason,
                       started_at, completed_at
                FROM stage_executions
                WHERE id = %s
                """,
                (execution_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_stage_execution(row)

    def get_stage_executions_for_run(
        self, run_id: UUID, stage: Optional[StageType] = None
    ) -> List[StageExecution]:
        """Get all stage executions for a run, ordered by started_at with id as tie-breaker."""
        with self._cursor() as cur:
            if stage:
                cur.execute(
                    """
                    SELECT id, run_id, stage, status, attempt_number,
                           participating_agents, artifacts, artifact_schema_version,
                           sent_back_from, send_back_reason, started_at, completed_at
                    FROM stage_executions
                    WHERE run_id = %s AND stage = %s
                    ORDER BY started_at ASC NULLS LAST, id ASC
                    """,
                    (str(run_id), stage.value),
                )
            else:
                cur.execute(
                    """
                    SELECT id, run_id, stage, status, attempt_number,
                           participating_agents, artifacts, artifact_schema_version,
                           sent_back_from, send_back_reason, started_at, completed_at
                    FROM stage_executions
                    WHERE run_id = %s
                    ORDER BY started_at ASC NULLS LAST, id ASC
                    """,
                    (str(run_id),),
                )
            return [self._row_to_stage_execution(row) for row in cur.fetchall()]

    def get_active_stage(self, run_id: UUID) -> Optional[StageExecution]:
        """Get the currently active stage execution for a run (in_progress or checkpoint_reached)."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, run_id, stage, status, attempt_number,
                       participating_agents, artifacts, artifact_schema_version,
                       conversation_id, sent_back_from, send_back_reason,
                       started_at, completed_at
                FROM stage_executions
                WHERE run_id = %s AND status IN ('in_progress', 'checkpoint_reached')
                LIMIT 1
                """,
                (str(run_id),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_stage_execution(row)

    def update_stage_status(
        self,
        execution_id: int,
        status: StageStatus,
        artifacts: Optional[Dict[str, Any]] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[StageExecution]:
        """Update stage execution status and optionally artifacts/completed_at."""
        with self._cursor() as cur:
            if artifacts is not None:
                cur.execute(
                    """
                    UPDATE stage_executions
                    SET status = %s, artifacts = %s, completed_at = %s
                    WHERE id = %s
                    RETURNING id, run_id, stage, status, attempt_number,
                              participating_agents, artifacts, artifact_schema_version,
                              conversation_id, sent_back_from, send_back_reason,
                              started_at, completed_at
                    """,
                    (status.value, json.dumps(artifacts), completed_at, execution_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE stage_executions
                    SET status = %s, completed_at = %s
                    WHERE id = %s
                    RETURNING id, run_id, stage, status, attempt_number,
                              participating_agents, artifacts, artifact_schema_version,
                              conversation_id, sent_back_from, send_back_reason,
                              started_at, completed_at
                    """,
                    (status.value, completed_at, execution_id),
                )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_stage_execution(row)

    def get_latest_attempt_number(self, run_id: UUID, stage: StageType) -> int:
        """Get the latest attempt number for a stage in a run. Returns 0 if no attempts."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0)
                FROM stage_executions
                WHERE run_id = %s AND stage = %s
                """,
                (str(run_id), stage.value),
            )
            row = cur.fetchone()
            return row["coalesce"]

    def update_stage_conversation_id(
        self, execution_id: int, conversation_id: str
    ) -> Optional[StageExecution]:
        """Link a conversation to a stage execution."""
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE stage_executions
                SET conversation_id = %s
                WHERE id = %s
                RETURNING id, run_id, stage, status, attempt_number,
                          participating_agents, artifacts, artifact_schema_version,
                          conversation_id, sent_back_from, send_back_reason,
                          started_at, completed_at
                """,
                (conversation_id, execution_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_stage_execution(row)

    def get_stage_conversation_id(
        self, run_id: UUID, stage: StageType
    ) -> Optional[str]:
        """Get the conversation_id for the latest attempt of a stage in a run."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT conversation_id
                FROM stage_executions
                WHERE run_id = %s AND stage = %s AND conversation_id IS NOT NULL
                ORDER BY attempt_number DESC
                LIMIT 1
                """,
                (str(run_id), stage.value),
            )
            row = cur.fetchone()
            if not row:
                return None
            return row["conversation_id"]

    # ========================================================================
    # Agent Invocations
    # ========================================================================

    def create_agent_invocation(self, invocation: AgentInvocation) -> AgentInvocation:
        """Create a new agent invocation record."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_invocations (
                    stage_execution_id, run_id, agent_name, status,
                    retry_count, output, error, token_usage, started_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, stage_execution_id, run_id, agent_name, status,
                          retry_count, output, error, token_usage,
                          started_at, completed_at
                """,
                (
                    invocation.stage_execution_id,
                    str(invocation.run_id),
                    invocation.agent_name,
                    invocation.status.value,
                    invocation.retry_count,
                    json.dumps(invocation.output) if invocation.output is not None else None,
                    invocation.error,
                    json.dumps(invocation.token_usage.model_dump())
                    if invocation.token_usage
                    else None,
                    invocation.started_at,
                ),
            )
            row = cur.fetchone()
            return self._row_to_agent_invocation(row)

    def get_agent_invocation(self, invocation_id: int) -> Optional[AgentInvocation]:
        """Get an agent invocation by ID."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, stage_execution_id, run_id, agent_name, status,
                       retry_count, output, error, token_usage,
                       started_at, completed_at
                FROM agent_invocations
                WHERE id = %s
                """,
                (invocation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_agent_invocation(row)

    def get_invocations_for_stage(self, stage_execution_id: int) -> List[AgentInvocation]:
        """Get all agent invocations for a stage execution."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, stage_execution_id, run_id, agent_name, status,
                       retry_count, output, error, token_usage,
                       started_at, completed_at
                FROM agent_invocations
                WHERE stage_execution_id = %s
                ORDER BY started_at ASC NULLS LAST, id ASC
                """,
                (stage_execution_id,),
            )
            return [self._row_to_agent_invocation(row) for row in cur.fetchall()]

    def get_invocations_for_run(self, run_id: UUID) -> List[AgentInvocation]:
        """Get all agent invocations for a run (uses denormalized run_id)."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, stage_execution_id, run_id, agent_name, status,
                       retry_count, output, error, token_usage,
                       started_at, completed_at
                FROM agent_invocations
                WHERE run_id = %s
                ORDER BY started_at ASC NULLS LAST, id ASC
                """,
                (str(run_id),),
            )
            return [self._row_to_agent_invocation(row) for row in cur.fetchall()]

    def update_agent_status(
        self,
        invocation_id: int,
        status: AgentStatus,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        token_usage: Optional[TokenUsage] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[AgentInvocation]:
        """Update agent invocation status and results."""
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE agent_invocations
                SET status = %s,
                    output = COALESCE(%s, output),
                    error = COALESCE(%s, error),
                    token_usage = COALESCE(%s, token_usage),
                    completed_at = %s
                WHERE id = %s
                RETURNING id, stage_execution_id, run_id, agent_name, status,
                          retry_count, output, error, token_usage,
                          started_at, completed_at
                """,
                (
                    status.value,
                    json.dumps(output) if output is not None else None,
                    error,
                    json.dumps(token_usage.model_dump()) if token_usage is not None else None,
                    completed_at,
                    invocation_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_agent_invocation(row)

    def increment_agent_retry(self, invocation_id: int) -> Optional[AgentInvocation]:
        """Increment retry count and reset status to pending."""
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE agent_invocations
                SET retry_count = retry_count + 1,
                    status = 'pending',
                    error = NULL,
                    started_at = NULL,
                    completed_at = NULL
                WHERE id = %s
                RETURNING id, stage_execution_id, run_id, agent_name, status,
                          retry_count, output, error, token_usage,
                          started_at, completed_at
                """,
                (invocation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_agent_invocation(row)

    # ========================================================================
    # Row mapping helpers
    # ========================================================================

    def _row_to_run(self, row: dict) -> DiscoveryRun:
        """Convert a database row to a DiscoveryRun model."""
        config_data = row["config"] if isinstance(row["config"], dict) else {}
        metadata_data = row["metadata"] if isinstance(row["metadata"], dict) else {}
        parent_run_id = UUID(str(row["parent_run_id"])) if row.get("parent_run_id") else None

        return DiscoveryRun(
            id=UUID(str(row["id"])),
            parent_run_id=parent_run_id,
            status=RunStatus(row["status"]),
            current_stage=StageType(row["current_stage"]) if row["current_stage"] else None,
            config=RunConfig(**config_data),
            metadata=RunMetadata(**metadata_data),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            errors=row["errors"] if isinstance(row["errors"], list) else [],
            warnings=row["warnings"] if isinstance(row["warnings"], list) else [],
        )

    def _row_to_stage_execution(self, row: dict) -> StageExecution:
        """Convert a database row to a StageExecution model."""
        return StageExecution(
            id=row["id"],
            run_id=UUID(str(row["run_id"])),
            stage=StageType(row["stage"]),
            status=StageStatus(row["status"]),
            attempt_number=row["attempt_number"],
            participating_agents=row["participating_agents"] or [],
            artifacts=row["artifacts"] if isinstance(row["artifacts"], dict) else None,
            artifact_schema_version=row.get("artifact_schema_version", 1),
            conversation_id=row.get("conversation_id"),
            sent_back_from=StageType(row["sent_back_from"]) if row["sent_back_from"] else None,
            send_back_reason=row["send_back_reason"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def _row_to_agent_invocation(self, row: dict) -> AgentInvocation:
        """Convert a database row to an AgentInvocation model."""
        token_data = row["token_usage"]
        token_usage = None
        if token_data and isinstance(token_data, dict):
            token_usage = TokenUsage(**token_data)

        return AgentInvocation(
            id=row["id"],
            stage_execution_id=row["stage_execution_id"],
            run_id=UUID(str(row["run_id"])),
            agent_name=row["agent_name"],
            status=AgentStatus(row["status"]),
            retry_count=row["retry_count"],
            output=row["output"] if isinstance(row["output"], dict) else None,
            error=row["error"],
            token_usage=token_usage,
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
