"""Run, stage execution, and agent invocation models for the Discovery Engine."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.discovery.models.enums import (
    AgentStatus,
    RunStatus,
    StageStatus,
    StageType,
)


class TokenUsage(BaseModel):
    """Token usage tracking for agent invocations."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: Optional[float] = None


class RunMetadata(BaseModel):
    """Run metadata captured per discovery cycle for auditability.

    Phase 1: recorded for auditability, not used for replay.
    """

    agent_versions: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of agent_name → prompt_version_hash",
    )
    toolset_versions: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of agent_name → tool_config_hash",
    )
    input_snapshot_ref: Optional[str] = Field(
        default=None,
        description="Reference to frozen input data, e.g. 'intercom conversations 2026-01-25 to 2026-02-07'",
    )


class RunConfig(BaseModel):
    """Run configuration — scope boundaries and resource constraints."""

    target_domain: Optional[str] = Field(
        default=None,
        description="Focus domain, e.g. 'scheduling', 'billing'",
    )
    time_window_days: int = Field(
        default=14,
        ge=1,
        description="How far back explorers should look",
    )
    max_explorer_iterations: Optional[int] = Field(
        default=None,
        description="Resource ceiling for Stage 0 exploration",
    )


class AgentInvocation(BaseModel):
    """A single agent invocation within a stage execution."""

    id: Optional[int] = None
    stage_execution_id: Optional[int] = None
    run_id: Optional[UUID] = None
    agent_name: str
    status: AgentStatus = AgentStatus.PENDING
    retry_count: int = 0
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    token_usage: Optional[TokenUsage] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StageExecution(BaseModel):
    """A single stage execution within a discovery run."""

    id: Optional[int] = None
    run_id: Optional[UUID] = None
    stage: StageType
    status: StageStatus = StageStatus.PENDING
    attempt_number: int = 1
    participating_agents: List[str] = Field(default_factory=list)
    artifacts: Optional[Dict[str, Any]] = None
    artifact_schema_version: int = 1
    conversation_id: Optional[str] = None
    sent_back_from: Optional[StageType] = None
    send_back_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DiscoveryRun(BaseModel):
    """Top-level discovery cycle run."""

    id: Optional[UUID] = None
    status: RunStatus = RunStatus.PENDING
    current_stage: Optional[StageType] = None
    config: RunConfig = Field(default_factory=RunConfig)
    metadata: RunMetadata = Field(default_factory=RunMetadata)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
