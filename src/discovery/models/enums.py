"""Enums for the Discovery Engine state machine and artifact contracts."""

from enum import Enum


class RunStatus(str, Enum):
    """Discovery run lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class StageType(str, Enum):
    """The 6 stages of the discovery pipeline."""

    EXPLORATION = "exploration"
    OPPORTUNITY_FRAMING = "opportunity_framing"
    SOLUTION_VALIDATION = "solution_validation"
    FEASIBILITY_RISK = "feasibility_risk"
    PRIORITIZATION = "prioritization"
    HUMAN_REVIEW = "human_review"


# Ordered list for forward progression
STAGE_ORDER = [
    StageType.EXPLORATION,
    StageType.OPPORTUNITY_FRAMING,
    StageType.SOLUTION_VALIDATION,
    StageType.FEASIBILITY_RISK,
    StageType.PRIORITIZATION,
    StageType.HUMAN_REVIEW,
]


class StageStatus(str, Enum):
    """Stage execution lifecycle status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CHECKPOINT_REACHED = "checkpoint_reached"
    COMPLETED = "completed"
    FAILED = "failed"
    SENT_BACK = "sent_back"


class AgentStatus(str, Enum):
    """Agent invocation lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, Enum):
    """Evidence source types from #212."""

    INTERCOM = "intercom"
    POSTHOG = "posthog"
    GITHUB = "github"
    CODEBASE = "codebase"
    RESEARCH = "research"
    OTHER = "other"


class ConfidenceLevel(str, Enum):
    """Evidence confidence levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_raw(cls, raw) -> str:
        """Map LLM confidence strings to ConfidenceLevel enum values.

        Handles case-insensitive matching and defaults to MEDIUM for
        unknown strings or non-string inputs.

        Extracted per 'third use = extract' rule — previously duplicated
        as _map_confidence() in customer_voice.py, codebase_explorer.py,
        and opportunity_pm.py.
        """
        if not isinstance(raw, str):
            return cls.MEDIUM.value
        return cls._value2member_map_.get(raw.lower(), cls.MEDIUM).value


class BuildExperimentDecision(str, Enum):
    """Stage 2 Build/Experiment Decision gate from #212."""

    EXPERIMENT_FIRST = "experiment_first"
    BUILD_SLICE_AND_EXPERIMENT = "build_slice_and_experiment"
    BUILD_WITH_METRICS = "build_with_metrics"
    BUILD_DIRECT = "build_direct"
