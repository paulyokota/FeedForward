"""Pydantic models for database entities."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Embedding dimensions for text-embedding-3-small
EMBEDDING_DIMENSIONS = 1536


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
# ActionType: What kind of interaction this conversation represents
ActionType = Literal[
    "inquiry",          # Information request
    "complaint",        # Dissatisfaction report
    "bug_report",       # Technical issue
    "how_to_question",  # Usage guidance needed
    "feature_request",  # Capability request
    "account_change",   # Account modification
    "delete_request",   # Deletion request
    "unknown",          # Unclassified
]

# Direction: The directional aspect of the user's issue or goal
Direction = Literal[
    "excess",       # Too much of something (duplicates, spam)
    "deficit",      # Too little (missing items, features not working)
    "creation",     # Create new entity
    "deletion",     # Remove entity
    "modification", # Change existing entity
    "performance",  # Speed/efficiency issue
    "neutral",      # No directional aspect
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
    current_phase: str = "classification"  # classification, embedding_generation, theme_extraction, pm_review, story_creation, completed

    # Results - Classification phase
    conversations_fetched: int = 0
    conversations_filtered: int = 0
    conversations_classified: int = 0
    conversations_stored: int = 0

    # Results - Embedding generation phase (#106)
    embeddings_generated: int = 0
    embeddings_failed: int = 0

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

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    conversation_id: str
    pipeline_run_id: Optional[int] = None  # References pipeline_runs.id (INTEGER)

    # Embedding data - must be exactly EMBEDDING_DIMENSIONS for text-embedding-3-small
    embedding: List[float]
    model_version: str = "text-embedding-3-small"

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimension(cls, v: List[float]) -> List[float]:
        """Validate embedding has correct dimensions for the model."""
        if len(v) != EMBEDDING_DIMENSIONS:
            raise ValueError(f"Embedding must be exactly {EMBEDDING_DIMENSIONS} dimensions, got {len(v)}")
        return v


class ConversationFacet(BaseModel):
    """Extracted facets for fine-grained sub-clustering (T-006 hybrid clustering)."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = None
    conversation_id: str
    pipeline_run_id: Optional[int] = None  # References pipeline_runs.id (INTEGER)

    # Facet data
    action_type: ActionType = "unknown"
    direction: Direction = "neutral"
    symptom: Optional[str] = Field(default=None, max_length=200)
    user_goal: Optional[str] = Field(default=None, max_length=200)

    # Extraction metadata
    model_version: str = "gpt-4o-mini"
    extraction_confidence: Optional[Confidence] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("symptom", "user_goal")
    @classmethod
    def validate_word_count(cls, v: Optional[str]) -> Optional[str]:
        """Validate symptom/user_goal is 10 words or less."""
        if v is not None:
            word_count = len(v.split())
            if word_count > 10:
                raise ValueError(f"Must be 10 words or less, got {word_count}")
        return v
