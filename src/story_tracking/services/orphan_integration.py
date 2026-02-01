"""
Orphan Integration Service

Pipeline integration hook for Phase 5 Story Grouping.
Processes theme extraction output through the orphan matching system.

Issue #197: Added evidence creation for graduated stories.
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

from psycopg2.extras import RealDictCursor

# Add src to path for imports (lazy loading to avoid circular imports)
_src_path = Path(__file__).parent.parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

# Use TYPE_CHECKING for type hints only to avoid circular imports
if TYPE_CHECKING:
    from orphan_matcher import ExtractedTheme, MatchResult, OrphanMatcher

from .orphan_service import OrphanService
from .story_service import StoryService

logger = logging.getLogger(__name__)

# Issue #197: Intercom URL generation for evidence excerpts
# Default "2t3d8az2" is Tailwind's production Intercom app ID (from story_formatter.py)
INTERCOM_APP_ID = os.getenv("INTERCOM_APP_ID", "2t3d8az2")
INTERCOM_URL_TEMPLATE = "https://app.intercom.com/a/apps/{app_id}/inbox/inbox/conversation/{conversation_id}"


@dataclass
class OrphanIntegrationResult:
    """Result of processing conversations through orphan integration."""

    total_processed: int = 0
    orphans_created: int = 0
    orphans_updated: int = 0
    stories_graduated: int = 0
    # stories_appended (Issue #176): When an orphan graduates to a story, its signature
    # row remains in story_orphans (UNIQUE constraint). New conversations matching that
    # signature are routed directly to the story via EvidenceService.add_conversation().
    # This counter tracks those post-graduation additions (distinct from stories_graduated
    # which counts the graduation events themselves).
    stories_appended: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class OrphanIntegrationService:
    """
    Pipeline integration for orphan matching and graduation.

    This service acts as a hook after theme extraction to:
    1. Match extracted themes to existing orphans
    2. Create new orphans for unmatched themes
    3. Auto-graduate orphans when they reach MIN_GROUP_SIZE

    Usage in pipeline:
        extractor = ThemeExtractor()
        theme = extractor.extract(conversation)

        # Hook into orphan system
        integration = OrphanIntegrationService(db_connection)
        result = integration.process_theme(conversation.id, theme)

    Or for batch processing:
        themes = extractor.extract_batch(conversations)
        result = integration.process_themes(themes)
    """

    def __init__(
        self,
        db_connection,
        auto_graduate: bool = True,
    ):
        """
        Initialize orphan integration.

        Args:
            db_connection: Database connection for services
            auto_graduate: Whether to auto-graduate orphans when they reach threshold
        """
        # Lazy imports to avoid circular import issues
        from orphan_matcher import OrphanMatcher
        from signature_utils import get_registry
        from .evidence_service import EvidenceService

        self.db = db_connection
        self.story_service = StoryService(db_connection)
        self.orphan_service = OrphanService(db_connection)
        self.evidence_service = EvidenceService(db_connection)
        self.signature_registry = get_registry()

        self.matcher = OrphanMatcher(
            orphan_service=self.orphan_service,
            story_service=self.story_service,
            signature_registry=self.signature_registry,
            auto_graduate=auto_graduate,
            evidence_service=self.evidence_service,
        )

    def _build_intercom_url(self, conversation_id: str) -> str:
        """Build Intercom conversation URL from conversation ID."""
        return INTERCOM_URL_TEMPLATE.format(
            app_id=INTERCOM_APP_ID,
            conversation_id=conversation_id,
        )

    def _create_evidence_for_graduated_story(
        self,
        story_id: UUID,
        orphan_signature: str,
        conversation_ids: List[str],
    ) -> bool:
        """
        Create evidence bundle for a newly graduated story.

        Issue #197: Queries themes + conversations tables to get diagnostic_summary,
        key_excerpts, and metadata for evidence excerpts.

        Args:
            story_id: The story UUID that was created during graduation
            orphan_signature: The canonical signature of the orphan
            conversation_ids: List of conversation IDs in the orphan

        Returns:
            True if successful, False if failed
        """
        from ..models import EvidenceExcerpt

        if not conversation_ids:
            logger.warning(f"No conversation_ids for story {story_id}, skipping evidence creation")
            return False

        try:
            with self.db.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT t.issue_signature, t.conversation_id,
                           t.diagnostic_summary, t.key_excerpts,
                           c.source_body, c.contact_email, c.contact_id, c.user_id, c.org_id
                    FROM themes t
                    JOIN conversations c ON t.conversation_id = c.id
                    WHERE t.conversation_id = ANY(%s)
                """, (conversation_ids,))
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    f"No theme data found for story {story_id} conversations {conversation_ids}"
                )
                return False

            # Collect all unique theme signatures (for multi-signature stories)
            # Collect all unique theme signatures
            theme_signatures = set([orphan_signature])
            for row in rows:
                sig = row.get("issue_signature")
                if sig:
                    theme_signatures.add(sig)

            # Build excerpts from conversation data
            # Note: Uses RealDictCursor so rows are always dicts
            MAX_EXCERPT_LENGTH = 2000  # Limit to prevent JSONB bloat
            excerpts = []
            for row in rows:
                conv_id = row.get("conversation_id")
                diagnostic_summary = row.get("diagnostic_summary")
                key_excerpts_data = row.get("key_excerpts") or []
                contact_email = row.get("contact_email")
                org_id = row.get("org_id")
                user_id = row.get("user_id")
                contact_id = row.get("contact_id")

                intercom_url = self._build_intercom_url(conv_id) if conv_id else None

                # Primary: diagnostic_summary
                if diagnostic_summary:
                    excerpts.append(EvidenceExcerpt(
                        text=str(diagnostic_summary)[:MAX_EXCERPT_LENGTH],
                        source="intercom",
                        conversation_id=conv_id,
                        email=contact_email,
                        intercom_url=intercom_url,
                        org_id=org_id,
                        user_id=user_id,
                        contact_id=contact_id,
                    ))

                # Secondary: key_excerpts (with consistent metadata)
                for ke in key_excerpts_data:
                    if isinstance(ke, dict) and ke.get("text"):
                        excerpts.append(EvidenceExcerpt(
                            text=str(ke["text"])[:MAX_EXCERPT_LENGTH],
                            source="intercom",
                            conversation_id=conv_id,
                            email=contact_email,
                            intercom_url=intercom_url,
                            org_id=org_id,
                            user_id=user_id,
                            contact_id=contact_id,
                        ))

            # Create evidence bundle with all theme signatures
            self.evidence_service.create_or_update(
                story_id=story_id,
                conversation_ids=conversation_ids,
                theme_signatures=list(theme_signatures),
                source_stats={"intercom": len(conversation_ids)},
                excerpts=excerpts,
            )

            logger.info(
                f"Created evidence bundle for story {story_id}: "
                f"{len(excerpts)} excerpts, {len(theme_signatures)} signatures"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to create evidence for story {story_id}: {e}")
            return False

    def process_theme(
        self,
        conversation_id: str,
        theme_data: Dict[str, Any],
    ):
        """
        Process a single extracted theme through orphan matching.

        This is the primary hook to call after theme extraction.

        Args:
            conversation_id: The Intercom conversation ID
            theme_data: Theme data dict from ThemeExtractor
                       (issue_signature, user_intent, symptoms, etc.)

        Returns:
            MatchResult with action taken
        """
        from orphan_matcher import ExtractedTheme

        extracted_theme = ExtractedTheme(
            signature=theme_data.get("issue_signature", "unknown"),
            user_intent=theme_data.get("user_intent"),
            symptoms=theme_data.get("symptoms", []),
            product_area=theme_data.get("product_area"),
            component=theme_data.get("component"),
            affected_flow=theme_data.get("affected_flow"),
            root_cause_hypothesis=theme_data.get("root_cause_hypothesis"),
            excerpt=theme_data.get("excerpt"),
        )

        match_result = self.matcher.match_and_accumulate(conversation_id, extracted_theme)

        # Issue #197: If graduated, create evidence bundle for the new story
        # Use match_result data directly (more reliable than re-fetching orphan)
        if match_result.action == "graduated" and match_result.story_id:
            if match_result.orphan_signature and match_result.conversation_ids:
                self._create_evidence_for_graduated_story(
                    story_id=UUID(match_result.story_id),
                    orphan_signature=match_result.orphan_signature,
                    conversation_ids=match_result.conversation_ids,
                )
            else:
                logger.warning(
                    f"Graduated story {match_result.story_id} but missing data for evidence creation: "
                    f"signature={match_result.orphan_signature}, conv_ids={match_result.conversation_ids}"
                )

        return match_result

    def process_theme_object(self, theme):
        """
        Process a Theme object directly (from ThemeExtractor).

        Args:
            theme: Theme dataclass from theme_extractor.py

        Returns:
            MatchResult with action taken
        """
        from orphan_matcher import ExtractedTheme

        extracted = ExtractedTheme(
            signature=theme.issue_signature,
            user_intent=theme.user_intent,
            symptoms=theme.symptoms,
            product_area=theme.product_area,
            component=theme.component,
            affected_flow=theme.affected_flow,
            root_cause_hypothesis=theme.root_cause_hypothesis,
        )

        match_result = self.matcher.match_and_accumulate(theme.conversation_id, extracted)

        # Issue #197: If graduated, create evidence bundle for the new story
        if match_result.action == "graduated" and match_result.story_id:
            if match_result.orphan_signature and match_result.conversation_ids:
                self._create_evidence_for_graduated_story(
                    story_id=UUID(match_result.story_id),
                    orphan_signature=match_result.orphan_signature,
                    conversation_ids=match_result.conversation_ids,
                )

        return match_result

    def process_themes(
        self,
        themes: List[Dict[str, Any]],
    ) -> OrphanIntegrationResult:
        """
        Process multiple extracted themes in batch.

        Args:
            themes: List of theme dicts, each with:
                   - conversation_id (or id)
                   - issue_signature
                   - user_intent, symptoms, product_area, etc.

        Returns:
            OrphanIntegrationResult with counts
        """
        result = OrphanIntegrationResult()

        for theme in themes:
            try:
                conversation_id = str(
                    theme.get("conversation_id") or theme.get("id", "")
                )

                if not conversation_id:
                    result.errors.append("Theme missing conversation_id")
                    continue

                match_result = self.process_theme(conversation_id, theme)
                result.total_processed += 1

                if match_result.action == "created":
                    result.orphans_created += 1
                elif match_result.action == "updated":
                    result.orphans_updated += 1
                elif match_result.action == "graduated":
                    result.stories_graduated += 1
                elif match_result.action == "added_to_story":
                    result.stories_appended += 1

            except Exception as e:
                error_msg = f"Error processing theme: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        logger.info(
            f"Orphan integration complete: {result.total_processed} processed, "
            f"{result.orphans_created} orphans created, "
            f"{result.orphans_updated} updated, "
            f"{result.stories_graduated} graduated, "
            f"{result.stories_appended} appended to stories"
        )

        return result

    def graduate_pending(self) -> int:
        """
        Graduate all orphans that have reached threshold.

        Useful for manual or scheduled graduation runs.

        Returns:
            Number of orphans graduated
        """
        results = self.matcher.graduate_all_ready()
        return len(results)


def create_orphan_integration_hook(db_connection, auto_graduate: bool = True):
    """
    Factory function to create an orphan integration hook.

    Usage:
        from story_tracking.services.orphan_integration import create_orphan_integration_hook

        # In your pipeline
        orphan_hook = create_orphan_integration_hook(db_connection)

        for conv in conversations:
            theme = extractor.extract(conv)
            orphan_hook(conv.id, theme.to_dict())

    Args:
        db_connection: Database connection
        auto_graduate: Whether to auto-graduate orphans

    Returns:
        Callable that processes a conversation through orphan matching
    """
    service = OrphanIntegrationService(db_connection, auto_graduate)

    def hook(conversation_id: str, theme_data: Dict[str, Any]) -> MatchResult:
        return service.process_theme(conversation_id, theme_data)

    return hook
