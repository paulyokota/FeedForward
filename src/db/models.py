"""Pydantic models for database entities."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

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

# Facet types for hybrid clustering (T-006)
ActionType = Literal[
    "inquiry", "complaint", "bug_report", "how_to_question",
    "feature_request", "account_change", "delete_request", "unknown"
]

Direction = Literal[
    "excess", "deficit", "creation", "deletion",
    "modification", "performance", "neutral"
]


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


class HelpArticleReference(BaseModel):
    """Help article referenced in a conversation (Phase 4a)."""

    id: Optional[int] = None
    conversation_id: str  # FK to conversations
    article_id: str
    article_url: str
    article_title: Optional[str] = None
    article_category: Optional[str] = None
    referenced_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class ShortcutStoryLink(BaseModel):
    """Shortcut story linked to a conversation (Phase 4b)."""

    id: Optional[int] = None
    conversation_id: str  # FK to conversations
    story_id: str
    story_name: Optional[str] = None
    story_labels: list[str] = Field(default_factory=list)  # JSON array
    story_epic: Optional[str] = None
    story_state: Optional[str] = None
    linked_at: datetime = Field(default_factory=datetime.utcnow)

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
    auto_create_stories: bool = False

    # Phase tracking
    current_phase: str = "classification"  # classification, theme_extraction, pm_review, story_creation, completed

    # Results - Classification phase
    conversations_fetched: int = 0
    conversations_filtered: int = 0
    conversations_classified: int = 0
    conversations_stored: int = 0

    # Results - Theme extraction phase
    themes_extracted: int = 0
    themes_new: int = 0
    themes_filtered: int = 0  # Themes rejected by quality gates (#104)

    # Results - Story creation phase
    stories_created: int = 0
    orphans_created: int = 0

    # Story creation readiness
    # True only when themes_extracted > 0 (Fix #104)
    stories_ready: bool = False

    # Status
    status: Literal["running", "stopping", "stopped", "completed", "failed"] = "running"
    error_message: Optional[str] = None

    # Structured error tracking (#104)
    errors: List[dict] = Field(default_factory=list)  # [{phase, message, details}, ...]
    warnings: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ConversationEmbedding(BaseModel):
    """Vector embedding for a conversation (T-006 hybrid clustering)."""

    id: Optional[UUID] = None
    conversation_id: str
    pipeline_run_id: Optional[UUID] = None

    # Embedding data - stored as list of floats (1536 dimensions for text-embedding-3-small)
    embedding: List[float] = Field(default_factory=list)
    model_version: str = "text-embedding-3-small"

    # Content hash for change detection
    content_hash: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class ConversationFacets(BaseModel):
    """Extracted facets for fine-grained sub-clustering (T-006 hybrid clustering)."""

    id: Optional[UUID] = None
    conversation_id: str
    pipeline_run_id: Optional[UUID] = None

    # Facet data
    action_type: ActionType = "unknown"
    direction: Direction = "neutral"
    symptom: Optional[str] = None  # 10 words max
    user_goal: Optional[str] = None  # 10 words max

    # Extraction metadata
    model_version: str = "gpt-4o-mini"
    extraction_confidence: Optional[Confidence] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True
