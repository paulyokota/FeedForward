"""
Analytics API Schemas

Pydantic models for dashboard and analytics endpoints.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ConfidenceDistribution(BaseModel):
    """Distribution of confidence levels."""
    high: int = 0
    medium: int = 0
    low: int = 0


class TypeDistribution(BaseModel):
    """Distribution of conversation types with counts."""
    types: Dict[str, int] = Field(default_factory=dict)


class PipelineRunSummary(BaseModel):
    """Summary of a pipeline run for dashboard display."""
    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    conversations_fetched: int = 0
    conversations_classified: int = 0
    conversations_stored: int = 0


class DashboardMetrics(BaseModel):
    """
    Aggregated dashboard metrics.

    Provides a single-request overview of system state
    for the Streamlit dashboard.
    """
    # Conversation counts
    total_conversations: int = 0
    conversations_last_7_days: int = 0
    conversations_last_30_days: int = 0

    # Classification metrics
    classification_changes: int = Field(
        default=0,
        description="Count where Stage 2 differed from Stage 1"
    )
    disambiguation_high_count: int = Field(
        default=0,
        description="Count where support context highly disambiguated"
    )
    resolution_detected_count: int = 0

    # Distributions
    stage1_confidence: ConfidenceDistribution = Field(
        default_factory=ConfidenceDistribution
    )
    stage2_confidence: ConfidenceDistribution = Field(
        default_factory=ConfidenceDistribution
    )
    top_conversation_types: Dict[str, int] = Field(
        default_factory=dict,
        description="Top 5 conversation types by count"
    )

    # Theme metrics
    total_themes: int = 0
    trending_themes_count: int = Field(
        default=0,
        description="Themes with 2+ occurrences in last 7 days"
    )
    orphan_themes_count: int = Field(
        default=0,
        description="Themes with only 1 occurrence"
    )

    # Recent pipeline runs
    recent_runs: List[PipelineRunSummary] = Field(default_factory=list)
    last_run_at: Optional[datetime] = None


class ClassificationStats(BaseModel):
    """Detailed classification statistics for analysis."""
    days: int
    total_conversations: int
    stage1_confidence_distribution: Dict[str, int]
    stage2_confidence_distribution: Dict[str, int]
    classification_changes: int
    disambiguation_high_count: int
    resolution_detected_count: int
    top_stage1_types: Dict[str, int]
    top_stage2_types: Dict[str, int]
