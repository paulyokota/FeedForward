"""
Pipeline Integration Service

Bridges theme extraction pipeline output to story creation.
Converts PM-validated theme groups into candidate stories.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import UUID

from ..models import StoryCreate, StoryWithEvidence, EvidenceExcerpt

logger = logging.getLogger(__name__)


@dataclass
class ValidatedGroup:
    """
    Input from PM Review / Theme Extraction Pipeline.

    Represents a group of conversations that PM has validated
    as belonging to the same implementation ticket.
    """
    signature: str  # issue_signature from theme extraction
    conversation_ids: List[str]
    theme_signatures: List[str]
    title: str  # PM-approved title
    description: str
    product_area: Optional[str] = None
    technical_area: Optional[str] = None
    confidence_score: Optional[float] = None
    excerpts: Optional[List[Dict]] = None  # conversation excerpts as evidence


class PipelineIntegrationService:
    """
    Creates candidate stories from validated pipeline output.

    Responsibilities:
    - Convert PM-validated theme groups to candidate stories
    - Handle deduplication via signature matching
    - Create evidence bundles with conversation links
    - Update story counts

    This is the bridge between the theme extraction pipeline
    and the Story Tracking Web App.
    """

    def __init__(self, story_service, evidence_service):
        """
        Initialize with existing services.

        Args:
            story_service: StoryService instance for story CRUD
            evidence_service: EvidenceService instance for evidence management
        """
        self.story_service = story_service
        self.evidence_service = evidence_service

    def create_candidate_story(self, group: ValidatedGroup) -> StoryWithEvidence:
        """
        Create a candidate story from a validated theme group.

        Flow:
        1. Check for existing story with same signature (deduplication)
        2. Create story with status='candidate'
        3. Create evidence bundle with conversation_ids, excerpts
        4. Update story counts
        5. Return complete story with evidence

        Args:
            group: ValidatedGroup from PM review

        Returns:
            StoryWithEvidence: Complete story with evidence bundle

        Raises:
            ValueError: If group validation fails
        """
        # Validate input
        if not group.title:
            raise ValueError("Story title is required")
        if not group.conversation_ids:
            raise ValueError("At least one conversation_id is required")

        # Check for existing story with same signature
        existing = self.find_existing_story(group.signature)
        if existing:
            logger.info(
                f"Story already exists for signature '{group.signature}': {existing.id}"
            )
            return existing

        # Create story with candidate status
        labels = ["auto-generated"]
        if group.product_area:
            labels.append(group.product_area.lower().replace(" ", "-"))

        story_create = StoryCreate(
            title=group.title,
            description=group.description,
            labels=labels,
            product_area=group.product_area,
            technical_area=group.technical_area,
            status="candidate",
            confidence_score=group.confidence_score,
        )

        story = self.story_service.create(story_create)
        logger.info(f"Created candidate story {story.id}: {story.title}")

        # Create evidence bundle
        excerpts = self._prepare_excerpts(group.excerpts or [])
        source_stats = self._calculate_source_stats(group.excerpts or [])

        evidence = self.evidence_service.create_or_update(
            story_id=story.id,
            conversation_ids=group.conversation_ids,
            theme_signatures=group.theme_signatures,
            source_stats=source_stats,
            excerpts=excerpts,
        )

        logger.info(
            f"Created evidence for story {story.id}: "
            f"{len(group.conversation_ids)} conversations, "
            f"{len(group.theme_signatures)} themes"
        )

        # Get full story with evidence
        return self.story_service.get(story.id)

    def bulk_create_candidates(
        self, groups: List[ValidatedGroup]
    ) -> List[StoryWithEvidence]:
        """
        Create multiple candidate stories from validated groups.

        Skips duplicates (stories with same signature already exist).
        Logs progress for monitoring long-running imports.

        Args:
            groups: List of ValidatedGroup from PM review

        Returns:
            List[StoryWithEvidence]: Created stories (duplicates excluded)
        """
        created_stories = []
        skipped_count = 0

        for i, group in enumerate(groups, 1):
            try:
                # Check if already exists
                existing = self.find_existing_story(group.signature)
                if existing:
                    logger.info(
                        f"[{i}/{len(groups)}] Skipping duplicate: {group.signature}"
                    )
                    skipped_count += 1
                    continue

                # Create story
                story = self.create_candidate_story(group)
                created_stories.append(story)
                logger.info(
                    f"[{i}/{len(groups)}] Created story {story.id}: {story.title}"
                )

            except Exception as e:
                logger.error(
                    f"[{i}/{len(groups)}] Failed to create story for "
                    f"signature '{group.signature}': {e}"
                )
                continue

        logger.info(
            f"Bulk import complete: {len(created_stories)} created, "
            f"{skipped_count} skipped (duplicates)"
        )

        return created_stories

    def find_existing_story(self, signature: str) -> Optional[StoryWithEvidence]:
        """
        Check if a story already exists for this signature.

        Uses title matching as proxy for signature matching.
        In production, this should use a dedicated signature field
        or label-based lookup.

        Args:
            signature: issue_signature from theme extraction

        Returns:
            Optional[StoryWithEvidence]: Existing story or None
        """
        # Search by signature in title or labels
        # This is a simple implementation - in production, consider:
        # 1. Adding a signature field to stories table
        # 2. Using PostgreSQL full-text search
        # 3. Maintaining a signature -> story_id index

        results = self.story_service.search(signature, limit=5)

        # Check if any result is an exact signature match
        # (stored in labels or title)
        for story in results:
            if signature in story.title or signature in story.labels:
                return self.story_service.get(story.id)

        return None

    def _prepare_excerpts(self, excerpts_data: List[Dict]) -> List[EvidenceExcerpt]:
        """
        Convert raw excerpt dicts to EvidenceExcerpt models.

        Args:
            excerpts_data: List of dicts with text, source, conversation_id

        Returns:
            List[EvidenceExcerpt]: Validated excerpt models
        """
        excerpts = []
        for data in excerpts_data:
            try:
                excerpt = EvidenceExcerpt(
                    text=data.get("text", ""),
                    source=data.get("source", "unknown"),
                    conversation_id=data.get("conversation_id"),
                )
                excerpts.append(excerpt)
            except Exception as e:
                logger.warning(f"Failed to parse excerpt: {e}")
                continue

        return excerpts

    def _calculate_source_stats(self, excerpts_data: List[Dict]) -> Dict[str, int]:
        """
        Calculate source statistics from excerpts.

        Args:
            excerpts_data: List of excerpt dicts

        Returns:
            Dict[str, int]: Source counts (e.g., {"intercom": 5, "coda": 2})
        """
        source_stats: Dict[str, int] = {}

        for data in excerpts_data:
            source = data.get("source", "unknown")
            source_stats[source] = source_stats.get(source, 0) + 1

        return source_stats
