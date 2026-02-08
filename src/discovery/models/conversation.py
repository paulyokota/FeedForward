"""Conversation event models for the Discovery Engine.

Structured events are encoded as JSON envelopes in Agenterminal turn text.
If the entire turn text is valid JSON with a `_event` field, it's a structured
event. Otherwise it's a plain text message. This is unambiguous — agents
writing free-form text won't produce valid JSON with `_event` by accident.

Example structured event (the entire text field):
    {"_event": "checkpoint:submit", "agent": "customer_voice", "artifacts": {...}}

Example plain text:
    "I found 3 billing-related themes in the last 7 days of conversations..."
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of structured events in stage conversations."""

    MESSAGE = "message"  # Plain text (default for non-JSON turns)
    EXPLORER_REQUEST = "explorer:request"
    EXPLORER_RESPONSE = "explorer:response"
    CHECKPOINT_SUBMIT = "checkpoint:submit"
    STAGE_TRANSITION = "stage:transition"


class ConversationTurn(BaseModel):
    """A single turn in a conversation, as returned by Agenterminal."""

    id: str
    role: str  # "human", "agent", "system"
    text: str
    mode: Optional[str] = None  # "claude", "codex"
    created_at: Optional[datetime] = Field(None, alias="createdAt")

    model_config = {"populate_by_name": True}


class ConversationEvent(BaseModel):
    """A parsed conversation event — either a structured event or plain text.

    Created by parsing a ConversationTurn. If the turn text is a JSON envelope
    with `_event`, we extract the event type and payload. Otherwise it's a
    plain text message.
    """

    turn_id: str
    role: str
    event_type: EventType
    text: str  # Original text (for messages) or JSON string (for events)
    payload: Optional[Dict[str, Any]] = None  # Parsed JSON payload for structured events
    agent_name: Optional[str] = None  # Extracted from payload if present
    created_at: Optional[datetime] = None


class CheckpointSubmission(BaseModel):
    """A checkpoint artifact submission extracted from a checkpoint:submit event."""

    agent_name: str
    artifacts: Dict[str, Any]
    stage: Optional[str] = None  # Stage name, if included by the agent


def parse_turn(turn: ConversationTurn) -> ConversationEvent:
    """Parse a conversation turn into a ConversationEvent.

    If the turn text is valid JSON with a `_event` field, it's a structured
    event. Otherwise it's a plain text message.
    """
    try:
        data = json.loads(turn.text)
        if isinstance(data, dict) and "_event" in data:
            event_type_str = data["_event"]
            try:
                event_type = EventType(event_type_str)
            except ValueError:
                # Unknown event type — treat as message, log it
                logger.warning("Unknown event type: %s", event_type_str)
                return ConversationEvent(
                    turn_id=turn.id,
                    role=turn.role,
                    event_type=EventType.MESSAGE,
                    text=turn.text,
                    created_at=turn.created_at,
                )

            return ConversationEvent(
                turn_id=turn.id,
                role=turn.role,
                event_type=event_type,
                text=turn.text,
                payload=data,
                agent_name=data.get("agent"),
                created_at=turn.created_at,
            )
    except (json.JSONDecodeError, TypeError):
        pass

    # Plain text message
    return ConversationEvent(
        turn_id=turn.id,
        role=turn.role,
        event_type=EventType.MESSAGE,
        text=turn.text,
        created_at=turn.created_at,
    )


def parse_checkpoint_submission(event: ConversationEvent) -> CheckpointSubmission:
    """Extract a CheckpointSubmission from a checkpoint:submit event.

    Raises ValueError if the event is not a checkpoint:submit or missing required fields.
    """
    if event.event_type != EventType.CHECKPOINT_SUBMIT:
        raise ValueError(
            f"Expected checkpoint:submit event, got {event.event_type.value}"
        )

    if not event.payload:
        raise ValueError("checkpoint:submit event has no payload")

    agent_name = event.payload.get("agent")
    if not agent_name:
        raise ValueError("checkpoint:submit event missing 'agent' field")

    artifacts = event.payload.get("artifacts")
    if not artifacts or not isinstance(artifacts, dict):
        raise ValueError("checkpoint:submit event missing or invalid 'artifacts' field")

    return CheckpointSubmission(
        agent_name=agent_name,
        artifacts=artifacts,
        stage=event.payload.get("stage"),
    )


def build_event_text(event_type: EventType, payload: Dict[str, Any]) -> str:
    """Build the JSON envelope text for a structured event.

    The returned string is what gets posted as the turn text.
    """
    envelope = {"_event": event_type.value, **payload}
    return json.dumps(envelope)
