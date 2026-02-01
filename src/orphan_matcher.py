"""
Orphan Matcher

Matches incoming conversations to existing orphans and handles graduation.
Part of Phase 5 Story Grouping.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from signature_utils import SignatureRegistry, get_registry
from story_tracking.models.orphan import MIN_GROUP_SIZE, Orphan, OrphanCreate, OrphanGraduationResult
from story_tracking.services.orphan_service import OrphanService
from story_tracking.services.story_service import StoryService

if TYPE_CHECKING:
    from story_tracking.services.evidence_service import EvidenceService

logger = logging.getLogger(__name__)


@dataclass
class ExtractedTheme:
    """Theme data extracted from a conversation."""

    signature: str
    user_intent: Optional[str] = None
    symptoms: List[str] = None
    product_area: Optional[str] = None
    component: Optional[str] = None
    affected_flow: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    excerpt: Optional[str] = None

    def __post_init__(self):
        if self.symptoms is None:
            self.symptoms = []

    def to_theme_data(self) -> Dict[str, Any]:
        """Convert to theme_data dict for orphan storage."""
        data = {}
        if self.user_intent:
            data["user_intent"] = self.user_intent
        if self.symptoms:
            data["symptoms"] = self.symptoms
        if self.product_area:
            data["product_area"] = self.product_area
        if self.component:
            data["component"] = self.component
        if self.affected_flow:
            data["affected_flow"] = self.affected_flow
        if self.root_cause_hypothesis:
            data["root_cause_hypothesis"] = self.root_cause_hypothesis
        if self.excerpt:
            data["excerpts"] = [{"text": self.excerpt[:500]}]
        return data


@dataclass
class MatchResult:
    """
    Result of matching a conversation to an orphan.

    Attributes:
        matched: True if the operation succeeded (orphan created/updated/graduated)
        orphan_id: UUID of the orphan that was created or matched
        orphan_signature: The canonical signature of the orphan
        action: The action taken. One of:
            - "created": New orphan was created for this conversation
            - "updated": Conversation was added to an existing orphan
            - "graduated": Orphan reached MIN_GROUP_SIZE and became a story
            - "already_exists": Conversation was already in the orphan (no-op)
            - "graduation_failed": Graduation was attempted but failed
            - "added_to_story": Conversation added to story (orphan was graduated)
            - "no_evidence_service": Could not add to story (no EvidenceService)
        story_id: UUID of the created story (set when action="graduated" or "added_to_story")
        conversation_ids: List of conversation IDs (set when action="graduated" for evidence creation)
    """

    matched: bool
    orphan_id: Optional[str] = None
    orphan_signature: Optional[str] = None
    action: Optional[str] = None
    story_id: Optional[str] = None
    conversation_ids: Optional[List[str]] = None  # Issue #197: For evidence creation after graduation


class OrphanMatcher:
    """
    Matches incoming conversations to existing orphans.

    Responsibilities:
    - Match conversations to existing orphans by signature
    - Create new orphans for unmatched conversations
    - Accumulate conversations into matching orphans
    - Auto-graduate orphans when they reach MIN_GROUP_SIZE
    - Route post-graduation conversations to their stories
    """

    def __init__(
        self,
        orphan_service: OrphanService,
        story_service: StoryService,
        signature_registry: Optional[SignatureRegistry] = None,
        auto_graduate: bool = True,
        evidence_service: Optional["EvidenceService"] = None,
    ):
        """
        Initialize the orphan matcher.

        Args:
            orphan_service: Service for orphan CRUD operations
            story_service: Service for creating stories (used during graduation)
            signature_registry: Registry for normalizing signatures to canonical form.
                              If None, uses the default global registry.
            auto_graduate: If True (default), orphans are automatically graduated
                          to stories when they reach MIN_GROUP_SIZE conversations.
                          Set to False to accumulate orphans without auto-graduation,
                          useful for batch processing where you want to control
                          graduation timing via graduate_all_ready().
            evidence_service: Service for adding conversations to stories.
                            Required for routing post-graduation conversations
                            to their stories. If None, graduated orphans will
                            return action="no_evidence_service".
        """
        self.orphan_service = orphan_service
        self.story_service = story_service
        self.signature_registry = signature_registry or get_registry()
        self.auto_graduate = auto_graduate
        self.evidence_service = evidence_service

    def match_and_accumulate(
        self,
        conversation_id: str,
        extracted_theme: ExtractedTheme,
    ) -> MatchResult:
        """
        Match a conversation to an existing orphan or create a new one.

        If the orphan reaches MIN_GROUP_SIZE, it will be automatically
        graduated to a story (if auto_graduate is enabled).

        If the orphan has already graduated, the conversation flows to
        the story (requires evidence_service to be set).

        Args:
            conversation_id: The Intercom conversation ID
            extracted_theme: Theme data extracted from the conversation

        Returns:
            MatchResult with action taken
        """
        # Normalize signature for consistent matching
        canonical_signature = self.signature_registry.get_canonical(
            extracted_theme.signature
        )

        # Check for existing orphan with this signature (active OR graduated)
        existing_orphan = self.orphan_service.get_by_signature(canonical_signature)

        if existing_orphan:
            # Branch on whether orphan has graduated
            if existing_orphan.graduated_at and existing_orphan.story_id:
                # Graduated → flow conversation to story
                return self._add_to_graduated_story(
                    existing_orphan,
                    conversation_id,
                    extracted_theme,
                )
            else:
                # Active → add conversation to orphan
                return self._update_existing_orphan(
                    existing_orphan,
                    conversation_id,
                    extracted_theme,
                )
        else:
            return self._create_new_orphan(
                canonical_signature,
                conversation_id,
                extracted_theme,
            )

    def _update_existing_orphan(
        self,
        orphan: Orphan,
        conversation_id: str,
        extracted_theme: ExtractedTheme,
    ) -> MatchResult:
        """Add conversation to existing orphan and check for graduation."""
        # Check if conversation already exists in orphan
        if conversation_id in orphan.conversation_ids:
            logger.debug(
                f"Conversation {conversation_id} already in orphan {orphan.id}"
            )
            return MatchResult(
                matched=True,
                orphan_id=str(orphan.id),
                orphan_signature=orphan.signature,
                action="already_exists",
            )

        # Add conversation to orphan
        theme_data = extracted_theme.to_theme_data()
        updated_orphan = self.orphan_service.add_conversations(
            orphan.id,
            [conversation_id],
            theme_data,
        )

        if not updated_orphan:
            logger.error(f"Failed to update orphan {orphan.id}")
            return MatchResult(matched=False)

        logger.info(
            f"Added conversation {conversation_id} to orphan {orphan.id} "
            f"(now has {updated_orphan.conversation_count} conversations)"
        )

        # Check if should graduate
        if self.auto_graduate and self._should_graduate(updated_orphan):
            return self._graduate_orphan(updated_orphan)

        return MatchResult(
            matched=True,
            orphan_id=str(updated_orphan.id),
            orphan_signature=updated_orphan.signature,
            action="updated",
        )

    def _add_to_graduated_story(
        self,
        orphan: Orphan,
        conversation_id: str,
        extracted_theme: ExtractedTheme,
    ) -> MatchResult:
        """Add conversation to the story that this orphan graduated into."""
        if not self.evidence_service:
            logger.warning(
                f"No evidence_service - cannot add conversation {conversation_id} "
                f"to graduated story {orphan.story_id}"
            )
            return MatchResult(
                matched=False,
                orphan_id=str(orphan.id),
                orphan_signature=orphan.signature,
                action="no_evidence_service",
                story_id=str(orphan.story_id),
            )

        excerpt = extracted_theme.excerpt[:500] if extracted_theme.excerpt else None
        # Issue #197: Pass theme_signature to populate theme_signatures in evidence bundle
        self.evidence_service.add_conversation(
            story_id=orphan.story_id,
            conversation_id=conversation_id,
            source="intercom",
            excerpt=excerpt,
            theme_signature=orphan.signature,
        )

        logger.info(
            f"Added conversation {conversation_id} to graduated story {orphan.story_id} "
            f"(orphan signature: '{orphan.signature}')"
        )

        return MatchResult(
            matched=True,
            orphan_id=str(orphan.id),
            orphan_signature=orphan.signature,
            action="added_to_story",
            story_id=str(orphan.story_id),
        )

    def _create_new_orphan(
        self,
        signature: str,
        conversation_id: str,
        extracted_theme: ExtractedTheme,
    ) -> MatchResult:
        """Create a new orphan for this conversation (idempotent).

        Uses create_or_get() which handles race conditions via ON CONFLICT.
        If another process created an orphan with the same signature between
        our get_by_signature() check and this insert, we route appropriately.
        """
        theme_data = extracted_theme.to_theme_data()

        orphan, created = self.orphan_service.create_or_get(OrphanCreate(
            signature=signature,
            original_signature=(
                extracted_theme.signature
                if extracted_theme.signature != signature
                else None
            ),
            conversation_ids=[conversation_id],
            theme_data=theme_data,
        ))

        if created:
            logger.info(
                f"Created new orphan {orphan.id} with signature '{signature}' "
                f"for conversation {conversation_id}"
            )
            return MatchResult(
                matched=True,
                orphan_id=str(orphan.id),
                orphan_signature=signature,
                action="created",
            )
        else:
            # Race condition handling (Issue #176):
            # Between our get_by_signature() check returning None and create_or_get()
            # executing, another pipeline worker may have created an orphan with this
            # signature. This is expected under concurrent runs - create_or_get() uses
            # ON CONFLICT DO NOTHING to avoid transaction abort, then returns the
            # existing orphan. We route based on that orphan's current state.
            logger.debug(
                f"Race condition: orphan {orphan.id} created by another process "
                f"for signature '{signature}'"
            )
            if orphan.graduated_at and orphan.story_id:
                # Graduated → flow to story
                return self._add_to_graduated_story(orphan, conversation_id, extracted_theme)
            else:
                # Active → update orphan
                return self._update_existing_orphan(orphan, conversation_id, extracted_theme)

    def _should_graduate(self, orphan: Orphan) -> bool:
        """Check if an orphan should graduate to a story."""
        return orphan.can_graduate and orphan.is_active

    def _graduate_orphan(self, orphan: Orphan) -> MatchResult:
        """Graduate an orphan to a story."""
        result = self.orphan_service.graduate(orphan.id, self.story_service)

        if not result:
            logger.error(f"Failed to graduate orphan {orphan.id}")
            return MatchResult(
                matched=True,
                orphan_id=str(orphan.id),
                orphan_signature=orphan.signature,
                action="graduation_failed",
            )

        logger.info(
            f"Graduated orphan {orphan.id} to story {result.story_id} "
            f"({result.conversation_count} conversations)"
        )

        return MatchResult(
            matched=True,
            orphan_id=str(orphan.id),
            orphan_signature=orphan.signature,
            action="graduated",
            story_id=str(result.story_id),
            conversation_ids=list(orphan.conversation_ids),  # Issue #197: For evidence creation
        )

    def batch_match(
        self,
        conversations: List[Dict[str, Any]],
    ) -> List[MatchResult]:
        """
        Match multiple conversations in batch.

        Args:
            conversations: List of dicts with 'id' and theme fields

        Returns:
            List of MatchResults for each conversation
        """
        results = []

        for conv in conversations:
            theme = ExtractedTheme(
                signature=conv.get("issue_signature", "unknown"),
                user_intent=conv.get("user_intent"),
                symptoms=conv.get("symptoms", []),
                product_area=conv.get("product_area"),
                component=conv.get("component"),
                affected_flow=conv.get("affected_flow"),
                root_cause_hypothesis=conv.get("root_cause_hypothesis"),
                excerpt=conv.get("excerpt"),
            )

            result = self.match_and_accumulate(
                conversation_id=str(conv.get("id", "")),
                extracted_theme=theme,
            )
            results.append(result)

        # Summary logging
        created = sum(1 for r in results if r.action == "created")
        updated = sum(1 for r in results if r.action == "updated")
        graduated = sum(1 for r in results if r.action == "graduated")

        logger.info(
            f"Batch match complete: {len(results)} conversations processed "
            f"({created} new orphans, {updated} updates, {graduated} graduations)"
        )

        return results

    def graduate_all_ready(self) -> List[OrphanGraduationResult]:
        """
        Graduate all orphans that are ready.

        Useful for batch processing or scheduled jobs.

        Returns:
            List of graduation results
        """
        return self.orphan_service.check_and_graduate_ready(self.story_service)
