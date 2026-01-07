"""Pydantic models for database entities."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# Classification output (matches classifier.py - legacy)
IssueType = Literal[
    "bug_report", "feature_request", "product_question",
    "plan_question", "marketing_question", "billing",
    "account_access", "feedback", "other"
]

Sentiment = Literal["frustrated", "neutral", "satisfied"]

Priority = Literal["urgent", "high", "normal", "low"]

# Two-Stage Classification System (Phase 1)
ConversationType = Literal[
    "product_issue", "how_to_question", "feature_request",
    "account_issue", "billing_question", "configuration_help",
    "general_inquiry", "spam"
]

Confidence = Literal["high", "medium", "low"]

RoutingPriority = Literal["urgent", "high", "normal", "low"]

Urgency = Literal["critical", "high", "normal", "low"]

DisambiguationLevel = Literal["high", "medium", "low", "none"]


class ClassificationResult(BaseModel):
    """Output from the classifier."""

    issue_type: IssueType
    sentiment: Sentiment
    churn_risk: bool
    priority: Priority


class Conversation(BaseModel):
    """A classified Intercom conversation."""

    # Primary key
    id: str

    # Timestamps
    created_at: datetime
    classified_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw input from Intercom
    source_body: Optional[str] = None
    source_type: Optional[str] = None
    source_subject: Optional[str] = None
    source_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_id: Optional[str] = None

    # Legacy classification output (Phase 1 original)
    issue_type: IssueType
    sentiment: Sentiment
    churn_risk: bool
    priority: Priority

    # Two-Stage Classification System (Phase 1 new)
    # Stage 1: Fast Routing
    stage1_type: Optional[ConversationType] = None
    stage1_confidence: Optional[Confidence] = None
    stage1_routing_priority: Optional[RoutingPriority] = None
    stage1_urgency: Optional[Urgency] = None
    stage1_auto_response_eligible: bool = False
    stage1_routing_team: Optional[str] = None

    # Stage 2: Refined Analysis
    stage2_type: Optional[ConversationType] = None
    stage2_confidence: Optional[Confidence] = None
    classification_changed: bool = False
    disambiguation_level: Optional[DisambiguationLevel] = None
    stage2_reasoning: Optional[str] = None

    # Support context
    has_support_response: bool = False
    support_response_count: int = 0

    # Resolution analysis
    resolution_action: Optional[str] = None
    resolution_detected: bool = False

    # Support insights (JSON structure)
    support_insights: Optional[dict] = None

    # Metadata
    classifier_version: str = "v1"
    raw_response: Optional[dict] = None

    class Config:
        from_attributes = True


class PipelineRun(BaseModel):
    """A batch pipeline execution record."""

    id: Optional[int] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Configuration
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

    # Results
    conversations_fetched: int = 0
    conversations_filtered: int = 0
    conversations_classified: int = 0
    conversations_stored: int = 0

    # Status
    status: Literal["running", "completed", "failed"] = "running"
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
