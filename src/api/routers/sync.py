"""
Sync API Endpoints

Bidirectional Shortcut sync operations.
Reference: docs/story-tracking-web-app-architecture.md
"""

import hashlib
import hmac
import logging
import os
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

logger = logging.getLogger(__name__)

from src.api.deps import get_db
from src.shortcut_client import ShortcutClient
from src.story_tracking.models import (
    PushRequest,
    PushResponse,
    PullRequest,
    PullResponse,
    ShortcutWebhookEvent,
    SyncResult,
    SyncStatusResponse,
)
from src.story_tracking.services import StoryService, SyncService


router = APIRouter(prefix="/api/sync", tags=["sync"])


def get_shortcut_client() -> ShortcutClient:
    """Dependency for ShortcutClient."""
    return ShortcutClient(
        api_token=os.getenv("SHORTCUT_API_TOKEN"),
        dry_run=os.getenv("SHORTCUT_DRY_RUN", "false").lower() == "true",
    )


def get_sync_service(
    db=Depends(get_db),
    shortcut_client: ShortcutClient = Depends(get_shortcut_client),
) -> SyncService:
    """Dependency for SyncService."""
    story_service = StoryService(db)
    return SyncService(db, shortcut_client, story_service)


async def verify_webhook_signature(
    request: Request,
    x_shortcut_signature: Optional[str] = Header(None, alias="X-Shortcut-Signature"),
) -> bool:
    """
    Verify Shortcut webhook signature.

    Shortcut signs webhooks with HMAC-SHA256 using the webhook secret.
    Returns True if signature is valid or if verification is disabled.

    Raises HTTPException 401 if signature is invalid.
    """
    webhook_secret = os.getenv("SHORTCUT_WEBHOOK_SECRET")

    # If no secret configured, log warning and allow (for development)
    if not webhook_secret:
        logger.warning(
            "SHORTCUT_WEBHOOK_SECRET not configured - webhook signature verification disabled"
        )
        return True

    # Require signature header when secret is configured
    if not x_shortcut_signature:
        logger.error("Missing X-Shortcut-Signature header on webhook request")
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    # Get raw request body for signature verification
    body = await request.body()

    # Compute expected signature
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    # Compare signatures using constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(x_shortcut_signature, expected_signature):
        logger.error("Invalid webhook signature - request rejected")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    return True


@router.post("/shortcut/push", response_model=PushResponse)
def push_to_shortcut(
    request: PushRequest,
    service: SyncService = Depends(get_sync_service),
):
    """
    Push internal story changes to Shortcut.

    Creates a new Shortcut story if one doesn't exist,
    or updates the existing linked story.
    """
    result = service.push_to_shortcut(request.story_id, request.snapshot)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    return PushResponse(
        shortcut_story_id=result.shortcut_story_id,
        last_synced_at=result.synced_at,
        sync_status="success",
    )


@router.post("/shortcut/pull", response_model=PullResponse)
def pull_from_shortcut(
    request: PullRequest,
    service: SyncService = Depends(get_sync_service),
    db=Depends(get_db),
):
    """
    Pull Shortcut story changes to internal.

    Updates the internal story with data from Shortcut.
    Requires the story to already be linked to a Shortcut story.
    """
    # Find the internal story by shortcut_story_id if story_id not provided
    if request.story_id:
        result = service.pull_from_shortcut(request.story_id)
    else:
        # Look up by shortcut_story_id
        story_id = service.find_story_by_shortcut_id(request.shortcut_story_id)
        if not story_id:
            raise HTTPException(
                status_code=404,
                detail=f"No internal story linked to Shortcut story {request.shortcut_story_id}",
            )
        result = service.pull_from_shortcut(story_id)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    # Get the updated story snapshot
    story_service = StoryService(db)
    story = story_service.get(result.story_id)

    from src.story_tracking.models import StorySnapshot

    snapshot = StorySnapshot(
        title=story.title,
        description=story.description,
        labels=story.labels,
        priority=story.priority,
        severity=story.severity,
        product_area=story.product_area,
        technical_area=story.technical_area,
    )

    return PullResponse(
        story_id=result.story_id,
        snapshot=snapshot,
        last_synced_at=result.synced_at,
        sync_status="success",
    )


@router.post("/shortcut/webhook", response_model=SyncResult)
async def handle_shortcut_webhook(
    event: ShortcutWebhookEvent,
    service: SyncService = Depends(get_sync_service),
    _signature_valid: bool = Depends(verify_webhook_signature),
):
    """
    Handle Shortcut webhook events.

    Processes story updates, creations, and deletions from Shortcut.
    Verifies webhook signature when SHORTCUT_WEBHOOK_SECRET is configured.
    """
    result = service.handle_webhook(event)
    return result


@router.get("/shortcut/status/{story_id}", response_model=SyncStatusResponse)
def get_sync_status(
    story_id: UUID,
    service: SyncService = Depends(get_sync_service),
):
    """
    Get sync status for a story.

    Returns current sync state including:
    - Whether sync is needed
    - Last sync timestamps
    - Any sync errors
    - Recommended sync direction
    """
    return service.get_sync_status(story_id)


@router.post("/shortcut/sync/{story_id}", response_model=SyncResult)
def sync_story(
    story_id: UUID,
    service: SyncService = Depends(get_sync_service),
):
    """
    Auto-sync a story using last-write-wins.

    Automatically determines sync direction based on timestamps
    and performs the appropriate push or pull operation.
    """
    return service.sync_story(story_id)


@router.post("/shortcut/sync-all", response_model=List[SyncResult])
def sync_all_pending(
    service: SyncService = Depends(get_sync_service),
):
    """
    Sync all stories that need syncing.

    Processes up to 100 stories that have changes pending sync.
    """
    return service.sync_all_pending()
