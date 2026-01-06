"""Pydantic models for database entities."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# Classification output (matches classifier.py)
IssueType = Literal[
    "bug_report", "feature_request", "product_question",
    "plan_question", "marketing_question", "billing",
    "account_access", "feedback", "other"
]

Sentiment = Literal["frustrated", "neutral", "satisfied"]

Priority = Literal["urgent", "high", "normal", "low"]


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
    contact_email: Optional[str] = None
    contact_id: Optional[str] = None

    # Classification output
    issue_type: IssueType
    sentiment: Sentiment
    churn_risk: bool
    priority: Priority

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
