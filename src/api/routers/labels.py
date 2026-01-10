"""
Label Registry API Endpoints

Label taxonomy management for Shortcut integration.
Reference: docs/story-tracking-web-app-architecture.md
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db
from src.shortcut_client import ShortcutClient
from src.story_tracking.models import (
    ImportResult,
    LabelCreate,
    LabelListResponse,
    LabelRegistryEntry,
)
from src.story_tracking.services import LabelRegistryService


router = APIRouter(prefix="/api/labels", tags=["labels"])


def get_shortcut_client() -> ShortcutClient:
    """Dependency for ShortcutClient."""
    return ShortcutClient(
        api_token=os.getenv("SHORTCUT_API_TOKEN"),
        dry_run=os.getenv("SHORTCUT_DRY_RUN", "false").lower() == "true",
    )


def get_label_service(
    db=Depends(get_db),
    shortcut_client: ShortcutClient = Depends(get_shortcut_client),
) -> LabelRegistryService:
    """Dependency for LabelRegistryService."""
    return LabelRegistryService(db, shortcut_client)


@router.get("", response_model=LabelListResponse)
def list_labels(
    source: Optional[str] = Query(
        default=None,
        description="Filter by source: 'shortcut' or 'internal'",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    service: LabelRegistryService = Depends(get_label_service),
):
    """
    List all labels in the registry.

    Returns labels with their source (shortcut or internal) and usage stats.
    """
    return service.list_labels(source=source, limit=limit)


@router.get("/{label_name}", response_model=LabelRegistryEntry)
def get_label(
    label_name: str,
    service: LabelRegistryService = Depends(get_label_service),
):
    """
    Get a specific label by name.
    """
    label = service.get_label(label_name)
    if not label:
        raise HTTPException(status_code=404, detail=f"Label '{label_name}' not found")
    return label


@router.post("", response_model=LabelRegistryEntry)
def create_label(
    label: LabelCreate,
    service: LabelRegistryService = Depends(get_label_service),
):
    """
    Create a new internal label.

    Internal labels are created in the local registry and can be
    synced to Shortcut when used on a story.
    """
    # Check if label already exists
    existing = service.get_label(label.label_name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Label '{label.label_name}' already exists",
        )

    return service.create_label(label)


@router.delete("/{label_name}")
def delete_label(
    label_name: str,
    service: LabelRegistryService = Depends(get_label_service),
):
    """
    Delete a label from the registry.

    Note: This only removes the label from the local registry,
    not from Shortcut if it exists there.
    """
    success = service.delete_label(label_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Label '{label_name}' not found")
    return {"status": "deleted", "label_name": label_name}


@router.post("/import", response_model=ImportResult)
def import_from_shortcut(
    service: LabelRegistryService = Depends(get_label_service),
):
    """
    Import labels from Shortcut.

    Fetches all labels from the Shortcut API and adds them to the
    local registry. Existing labels are updated with fresh last_seen_at.
    """
    result = service.import_from_shortcut()

    if result.errors:
        # Return result with errors but don't fail the request
        # since some imports may have succeeded
        return result

    return result


@router.post("/ensure/{label_name}")
def ensure_label_in_shortcut(
    label_name: str,
    service: LabelRegistryService = Depends(get_label_service),
):
    """
    Ensure a label exists in Shortcut.

    If the label is internal-only, creates it in Shortcut.
    Returns success if the label already exists in Shortcut.
    """
    success = service.ensure_label_in_shortcut(label_name)

    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to ensure label '{label_name}' in Shortcut",
        )

    return {"status": "ensured", "label_name": label_name}
