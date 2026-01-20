"""
Story Creation Service

Processes PM review results to create stories and orphans.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..models import (
    MIN_GROUP_SIZE,
    OrphanCreate,
    StoryCreate,
)
from .orphan_service import OrphanService
from .story_service import StoryService

# Optional dual-format components (graceful degradation if unavailable)
try:
    from src.story_formatter import DualStoryFormatter, DualFormatOutput
    from src.story_tracking.services.codebase_context_provider import (
        CodebaseContextProvider,
        ExplorationResult,
    )
    from src.story_tracking.services.domain_classifier import ClassificationResult
    DUAL_FORMAT_AVAILABLE = True
except ImportError:
    DualStoryFormatter = None
    DualFormatOutput = None
    CodebaseContextProvider = None
    ExplorationResult = None
    ClassificationResult = None
    DUAL_FORMAT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Import datetime for code context timestamps
from datetime import datetime, timezone

# Constants for data limits (used in theme data building and story generation)
MAX_SYMPTOMS_IN_THEME = 10
MAX_EXCERPTS_IN_THEME = 5
MAX_SYMPTOMS_IN_DESCRIPTION = 5
MAX_TITLE_LENGTH = 200
MAX_EXCERPT_LENGTH = 500
MIN_USER_INTENT_LENGTH = 10  # Minimum meaningful length for user_intent

# Constants for code context limits
MAX_CODE_SNIPPET_LENGTH = 5000  # 5KB per snippet to prevent bloat
MAX_CODE_CONTEXT_SIZE = 1_000_000  # 1MB total code_context limit


def _truncate_at_word_boundary(text: str, max_length: int) -> str:
    """
    Truncate text at word boundary to avoid cutting words mid-way.

    Args:
        text: Text to truncate
        max_length: Maximum length of result

    Returns:
        Truncated text with ellipsis if truncated, or original if short enough
    """
    if len(text) <= max_length:
        return text

    # Find last space before max_length (leave room for ellipsis)
    truncated = text[:max_length - 3]
    last_space = truncated.rfind(" ")

    if last_space > max_length // 2:
        # Found a reasonable word boundary
        return truncated[:last_space] + "..."
    else:
        # No good boundary found, just truncate
        return truncated + "..."


@dataclass
class PMReviewResult:
    """A single PM review decision."""

    signature: str
    decision: str  # "keep_together" or "split"
    reasoning: str
    sub_groups: List[Dict[str, Any]] = field(default_factory=list)
    conversation_count: Optional[int] = None


@dataclass
class ConversationData:
    """Conversation data from theme extraction."""

    id: str
    issue_signature: str
    product_area: Optional[str] = None
    component: Optional[str] = None
    user_intent: Optional[str] = None
    symptoms: List[str] = field(default_factory=list)
    affected_flow: Optional[str] = None
    root_cause_hypothesis: Optional[str] = None
    excerpt: Optional[str] = None


@dataclass
class ProcessingResult:
    """Result of processing PM review results."""

    stories_created: int = 0
    orphans_created: int = 0
    stories_updated: int = 0
    orphans_updated: int = 0
    errors: List[str] = field(default_factory=list)
    created_story_ids: List[UUID] = field(default_factory=list)
    created_orphan_ids: List[UUID] = field(default_factory=list)


class StoryCreationService:
    """
    Processes PM review results to create stories and orphans.

    Responsibilities:
    - Load and parse PM review JSON results
    - Create stories for "keep_together" decisions
    - Create stories for "split" sub-groups with ≥MIN_GROUP_SIZE conversations
    - Create orphans for "split" sub-groups with <MIN_GROUP_SIZE conversations
    - Accumulate conversations into existing orphans by signature
    - Optionally generate dual-format stories with codebase context (v2)
    """

    def __init__(
        self,
        story_service: StoryService,
        orphan_service: OrphanService,
        dual_format_enabled: bool = False,
        target_repo: Optional[str] = None,
    ):
        """
        Initialize the story creation service.

        Args:
            story_service: Service for story CRUD operations
            orphan_service: Service for orphan CRUD operations
            dual_format_enabled: If True, generate dual-format stories (v2) with
                                codebase context. Default False for backward compatibility.
            target_repo: Repository name for codebase exploration (required if dual_format_enabled)
        """
        self.story_service = story_service
        self.orphan_service = orphan_service
        self.dual_format_enabled = dual_format_enabled
        self.target_repo = target_repo

        # Initialize optional dual-format components
        if dual_format_enabled:
            if not DUAL_FORMAT_AVAILABLE:
                logger.warning(
                    "Dual format requested but dependencies not available. "
                    "Falling back to simple format."
                )
                self.dual_format_enabled = False
                self.dual_formatter = None
                self.codebase_provider = None
            else:
                self.dual_formatter = DualStoryFormatter()
                self.codebase_provider = CodebaseContextProvider()
                logger.info(
                    f"Dual format enabled with target repo: {target_repo or 'none'}"
                )
        else:
            self.dual_formatter = None
            self.codebase_provider = None

    def process_pm_review_results(
        self,
        results_path: Path,
        extraction_path: Optional[Path] = None,
    ) -> ProcessingResult:
        """
        Process PM review results and create stories/orphans.

        Args:
            results_path: Path to PM review results JSON file
            extraction_path: Path to theme extraction JSONL file (optional,
                           for enriching conversation data)

        Returns:
            ProcessingResult with counts and any errors
        """
        result = ProcessingResult()

        # Load PM review results
        try:
            pm_results = self._load_pm_results(results_path)
        except Exception as e:
            result.errors.append(f"Failed to load PM results: {e}")
            return result

        # Optionally load extraction data for enrichment
        conversations_by_signature: Dict[str, List[ConversationData]] = {}
        if extraction_path and extraction_path.exists():
            try:
                conversations_by_signature = self._load_extraction_data(extraction_path)
            except Exception as e:
                logger.warning(f"Could not load extraction data: {e}")

        # Process each PM review decision
        for pm_result in pm_results:
            try:
                self._process_single_result(
                    pm_result,
                    conversations_by_signature,
                    result,
                )
            except Exception as e:
                error_msg = f"Error processing {pm_result.signature}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        logger.info(
            f"Processed PM results: {result.stories_created} stories created, "
            f"{result.orphans_created} orphans created, "
            f"{result.stories_updated} stories updated, "
            f"{result.orphans_updated} orphans updated"
        )

        return result

    def _process_single_result(
        self,
        pm_result: PMReviewResult,
        conversations_by_signature: Dict[str, List[ConversationData]],
        result: ProcessingResult,
    ) -> None:
        """Process a single PM review decision."""
        if pm_result.decision == "error":
            result.errors.append(f"PM review failed for {pm_result.signature}")
            return

        # Get conversations for this signature
        conversations = conversations_by_signature.get(pm_result.signature, [])

        if pm_result.decision == "keep_together":
            self._handle_keep_together(pm_result, conversations, result)
        elif pm_result.decision == "split":
            self._handle_split(pm_result, conversations, result)
        else:
            result.errors.append(
                f"Unknown decision '{pm_result.decision}' for {pm_result.signature}"
            )

    def _handle_keep_together(
        self,
        pm_result: PMReviewResult,
        conversations: List[ConversationData],
        result: ProcessingResult,
    ) -> None:
        """Handle a keep_together decision - create a story."""
        conversation_ids = [c.id for c in conversations]
        conversation_count = len(conversations) or pm_result.conversation_count or 0

        if conversation_count < MIN_GROUP_SIZE:
            # Not enough conversations for a story, create orphan instead
            self._create_or_update_orphan(
                signature=pm_result.signature,
                original_signature=None,
                conversations=conversations,
                result=result,
            )
            return

        # Build theme data from conversations
        theme_data = self._build_theme_data(conversations)

        # Explore codebase with classification (Issue #44)
        code_context = None
        if self.dual_format_enabled:
            code_context = self._explore_codebase_with_classification(theme_data)

        # Create story
        story = self.story_service.create(StoryCreate(
            title=self._generate_title(pm_result.signature, theme_data),
            description=self._generate_description(
                pm_result.signature,
                theme_data,
                pm_result.reasoning,
            ),
            labels=[],
            product_area=theme_data.get("product_area"),
            technical_area=theme_data.get("component"),
            status="candidate",
            code_context=code_context,
        ))

        result.stories_created += 1
        result.created_story_ids.append(story.id)

        code_context_info = ""
        if code_context and code_context.get("success"):
            files_count = len(code_context.get("relevant_files", []))
            code_context_info = f", {files_count} code files"

        logger.info(
            f"Created story {story.id} for '{pm_result.signature}' "
            f"({len(conversation_ids)} conversations{code_context_info})"
        )

    def _handle_split(
        self,
        pm_result: PMReviewResult,
        conversations: List[ConversationData],
        result: ProcessingResult,
    ) -> None:
        """Handle a split decision - create stories/orphans for each sub-group."""
        for sub_group in pm_result.sub_groups:
            suggested_signature = sub_group.get("suggested_signature", "unknown")
            conv_indices = sub_group.get("conversation_ids", [])
            rationale = sub_group.get("rationale", "")

            # Get conversations for this sub-group
            # Note: conv_indices are indices into the original conversation list
            sub_conversations = []
            for idx in conv_indices:
                if isinstance(idx, int) and 0 <= idx < len(conversations):
                    sub_conversations.append(conversations[idx])

            if len(sub_conversations) >= MIN_GROUP_SIZE:
                # Create story
                self._create_story_from_subgroup(
                    suggested_signature,
                    pm_result.signature,
                    sub_conversations,
                    rationale,
                    result,
                )
            else:
                # Create or update orphan
                self._create_or_update_orphan(
                    signature=suggested_signature,
                    original_signature=pm_result.signature,
                    conversations=sub_conversations,
                    result=result,
                )

    def _create_story_from_subgroup(
        self,
        signature: str,
        original_signature: str,
        conversations: List[ConversationData],
        rationale: str,
        result: ProcessingResult,
    ) -> None:
        """Create a story from a split sub-group."""
        theme_data = self._build_theme_data(conversations)

        # Explore codebase with classification (Issue #44)
        code_context = None
        if self.dual_format_enabled:
            code_context = self._explore_codebase_with_classification(theme_data)

        story = self.story_service.create(StoryCreate(
            title=self._generate_title(signature, theme_data),
            description=self._generate_description(
                signature,
                theme_data,
                rationale,
                original_signature,
            ),
            labels=[],
            product_area=theme_data.get("product_area"),
            technical_area=theme_data.get("component"),
            status="candidate",
            code_context=code_context,
        ))

        result.stories_created += 1
        result.created_story_ids.append(story.id)

        code_context_info = ""
        if code_context and code_context.get("success"):
            files_count = len(code_context.get("relevant_files", []))
            code_context_info = f", {files_count} code files"

        logger.info(
            f"Created story {story.id} for split sub-group '{signature}' "
            f"(from {original_signature}, {len(conversations)} conversations{code_context_info})"
        )

    def _create_or_update_orphan(
        self,
        signature: str,
        original_signature: Optional[str],
        conversations: List[ConversationData],
        result: ProcessingResult,
    ) -> None:
        """Create a new orphan or add to existing one."""
        conversation_ids = [c.id for c in conversations]
        theme_data = self._build_theme_data(conversations)

        # Check if orphan already exists for this signature
        existing = self.orphan_service.get_by_signature(signature)

        if existing:
            # Add conversations to existing orphan
            self.orphan_service.add_conversations(
                existing.id,
                conversation_ids,
                theme_data,
            )
            result.orphans_updated += 1
            logger.info(
                f"Updated orphan {existing.id} for '{signature}' "
                f"(added {len(conversation_ids)} conversations)"
            )
        else:
            # Create new orphan
            orphan = self.orphan_service.create(OrphanCreate(
                signature=signature,
                original_signature=original_signature,
                conversation_ids=conversation_ids,
                theme_data=theme_data,
            ))
            result.orphans_created += 1
            result.created_orphan_ids.append(orphan.id)
            logger.info(
                f"Created orphan {orphan.id} for '{signature}' "
                f"({len(conversation_ids)} conversations)"
            )

    def _load_pm_results(self, path: Path) -> List[PMReviewResult]:
        """Load PM review results from JSON file."""
        with open(path) as f:
            data = json.load(f)

        results = []
        for item in data:
            results.append(PMReviewResult(
                signature=item.get("signature", "unknown"),
                decision=item.get("decision", "error"),
                reasoning=item.get("reasoning", ""),
                sub_groups=item.get("sub_groups", []),
                conversation_count=item.get("conversation_count"),
            ))

        return results

    def _load_extraction_data(
        self,
        path: Path,
    ) -> Dict[str, List[ConversationData]]:
        """Load theme extraction results grouped by signature."""
        conversations: Dict[str, List[ConversationData]] = {}

        with open(path) as f:
            for line in f:
                item = json.loads(line)
                signature = item.get("issue_signature", "unknown")

                conv = ConversationData(
                    id=str(item.get("id", "")),
                    issue_signature=signature,
                    product_area=item.get("product_area"),
                    component=item.get("component"),
                    user_intent=item.get("user_intent"),
                    symptoms=item.get("symptoms", []),
                    affected_flow=item.get("affected_flow"),
                    root_cause_hypothesis=item.get("root_cause_hypothesis"),
                    excerpt=item.get("excerpt"),
                )

                if signature not in conversations:
                    conversations[signature] = []
                conversations[signature].append(conv)

        return conversations

    def _build_theme_data(
        self,
        conversations: List[ConversationData],
    ) -> Dict[str, Any]:
        """Build aggregated theme data from conversations."""
        if not conversations:
            return {}

        # Collect all symptoms
        all_symptoms = []
        for conv in conversations:
            all_symptoms.extend(conv.symptoms)
        unique_symptoms = list(dict.fromkeys(all_symptoms))  # Preserve order

        # Collect excerpts
        excerpts = []
        for conv in conversations:
            if conv.excerpt:
                excerpts.append({
                    "text": conv.excerpt[:MAX_EXCERPT_LENGTH],
                    "conversation_id": conv.id,
                })

        # Use first non-null values for scalars
        first = conversations[0]

        return {
            "user_intent": first.user_intent,
            "symptoms": unique_symptoms[:MAX_SYMPTOMS_IN_THEME],
            "product_area": first.product_area,
            "component": first.component,
            "affected_flow": first.affected_flow,
            "root_cause_hypothesis": first.root_cause_hypothesis,
            "excerpts": excerpts[:MAX_EXCERPTS_IN_THEME],
        }

    def _generate_title(
        self,
        signature: str,
        theme_data: Dict[str, Any],
    ) -> str:
        """Generate a story title from signature and theme data."""
        # Use user_intent if available and has meaningful content
        user_intent = theme_data.get("user_intent")
        if user_intent:
            stripped = user_intent.strip()
            if len(stripped) > MIN_USER_INTENT_LENGTH:
                return _truncate_at_word_boundary(stripped, MAX_TITLE_LENGTH)

        # Format signature into readable title
        title = signature.replace("_", " ").title()
        return _truncate_at_word_boundary(title, MAX_TITLE_LENGTH)

    def _generate_description(
        self,
        signature: str,
        theme_data: Dict[str, Any],
        reasoning: str,
        original_signature: Optional[str] = None,
    ) -> str:
        """
        Generate story description, optionally with dual format.

        Routes to either dual-format (v2) or simple format (v1) based on
        dual_format_enabled flag.

        Args:
            signature: Issue signature
            theme_data: Aggregated theme data from conversations
            reasoning: PM review reasoning
            original_signature: Original signature if split from a larger group

        Returns:
            Formatted story description (markdown)
        """
        if not self.dual_format_enabled:
            # Use existing simple format (v1)
            return self._generate_simple_description(
                signature, theme_data, reasoning, original_signature
            )

        # Use DualStoryFormatter for v2 format
        exploration_result = None
        if self.target_repo and self.codebase_provider:
            try:
                logger.debug(f"Exploring codebase for {signature}")
                exploration_result = self.codebase_provider.explore_for_theme(
                    theme_data,
                    self.target_repo,
                )
                logger.info(
                    f"Codebase exploration complete for {signature}: "
                    f"{len(exploration_result.relevant_files)} files, "
                    f"{len(exploration_result.code_snippets)} snippets"
                )
            except Exception as e:
                logger.warning(
                    f"Codebase exploration failed for {signature}: {e}",
                    exc_info=True,
                )
                # Continue with None exploration_result

        # Build formatter-compatible theme data
        formatter_theme_data = self._build_formatter_theme_data(
            signature, theme_data, reasoning, original_signature
        )

        # Generate dual-format output
        dual_output = self.dual_formatter.format_story(
            theme_data=formatter_theme_data,
            exploration_result=exploration_result,
        )

        logger.info(
            f"Generated dual-format story for {signature} "
            f"(format_version: {dual_output.format_version})"
        )

        return dual_output.combined

    def _generate_simple_description(
        self,
        signature: str,
        theme_data: Dict[str, Any],
        reasoning: str,
        original_signature: Optional[str] = None,
    ) -> str:
        """
        Generate simple story description (v1 format).

        This is the original format used before dual-format support.

        Args:
            signature: Issue signature
            theme_data: Aggregated theme data
            reasoning: PM review reasoning
            original_signature: Original signature if split

        Returns:
            Formatted markdown description
        """
        parts = []

        if user_intent := theme_data.get("user_intent"):
            parts.append(f"**User Intent**: {user_intent}")

        if symptoms := theme_data.get("symptoms"):
            parts.append(f"**Symptoms**: {', '.join(symptoms[:MAX_SYMPTOMS_IN_DESCRIPTION])}")

        if product_area := theme_data.get("product_area"):
            parts.append(f"**Product Area**: {product_area}")

        if component := theme_data.get("component"):
            parts.append(f"**Component**: {component}")

        if affected_flow := theme_data.get("affected_flow"):
            parts.append(f"**Affected Flow**: {affected_flow}")

        if root_cause := theme_data.get("root_cause_hypothesis"):
            parts.append(f"**Root Cause Hypothesis**: {root_cause}")

        if reasoning:
            parts.append(f"\n**PM Review Reasoning**: {reasoning}")

        parts.append(f"\n*Signature*: `{signature}`")

        if original_signature:
            parts.append(f"*Split from*: `{original_signature}`")

        return "\n\n".join(parts)

    def _build_formatter_theme_data(
        self,
        signature: str,
        theme_data: Dict[str, Any],
        reasoning: str,
        original_signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transform internal theme data to DualStoryFormatter format.

        Bridges the gap between our internal theme data structure and
        the format expected by DualStoryFormatter.

        Args:
            signature: Issue signature
            theme_data: Internal theme data dict
            reasoning: PM review reasoning
            original_signature: Original signature if split

        Returns:
            Theme data dict compatible with DualStoryFormatter.format_story()
        """
        # Extract excerpts for evidence
        excerpts_data = theme_data.get("excerpts", [])

        # Build customer messages from excerpts
        customer_messages = []
        for excerpt in excerpts_data[:5]:  # Top 5
            if isinstance(excerpt, dict) and "text" in excerpt:
                customer_messages.append(excerpt["text"])
            elif isinstance(excerpt, str):
                customer_messages.append(excerpt)

        return {
            "title": theme_data.get("user_intent") or signature.replace("_", " ").title(),
            "issue_signature": signature,
            "product_area": theme_data.get("product_area") or "Unknown",
            "component": theme_data.get("component") or "Unknown",
            "user_intent": theme_data.get("user_intent", ""),
            "symptoms": theme_data.get("symptoms", []),
            "root_cause_hypothesis": theme_data.get("root_cause_hypothesis", ""),
            "affected_flow": theme_data.get("affected_flow"),
            "pm_reasoning": reasoning,
            "occurrences": len(excerpts_data),
            "excerpts": excerpts_data,
            # Additional fields for dual format
            "original_signature": original_signature,
            "customer_messages": customer_messages,
            # Repository for codebase exploration
            "target_repo": self.target_repo,
        }

    def _explore_codebase_with_classification(
        self,
        theme_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Explore codebase using classification-guided exploration.

        Uses CodebaseContextProvider.explore_with_classification() to:
        1. Classify the issue into a product category (via Haiku)
        2. Use category-specific search paths for exploration
        3. Return structured code context for storage

        Args:
            theme_data: Aggregated theme data from conversations

        Returns:
            One of three possible states:
            - None: Provider not configured or no issue text available
            - Dict with success=False and error message: Exploration attempted but failed
            - Dict with success=True and code context: Successful exploration

            Callers should check: `code_context and code_context.get("success")`
            to determine if exploration produced usable results.
        """
        if not self.codebase_provider:
            logger.debug("Codebase provider not available, skipping exploration")
            return None

        # Build issue text from theme data for classification
        issue_text = self._build_issue_text_for_classification(theme_data)
        if not issue_text:
            logger.debug("No issue text available for classification")
            return None

        try:
            logger.info("Starting classification-guided codebase exploration")

            # Use classification-guided exploration
            exploration_result, classification_result = (
                self.codebase_provider.explore_with_classification(
                    issue_text=issue_text,
                    target_repo=self.target_repo,
                )
            )

            # Build code_context dict for storage
            code_context = self._build_code_context_dict(
                exploration_result, classification_result
            )

            if exploration_result.success:
                logger.info(
                    f"Classification-guided exploration complete: "
                    f"{len(exploration_result.relevant_files)} files, "
                    f"{len(exploration_result.code_snippets)} snippets, "
                    f"category={classification_result.category if classification_result else 'unknown'}"
                )
            else:
                logger.warning(
                    f"Exploration completed with errors: {exploration_result.error}"
                )

            return code_context

        except Exception as e:
            import traceback
            error_details = f"{type(e).__name__}: {str(e)}"
            logger.warning(
                f"Classification-guided exploration failed: {error_details}",
                exc_info=True,
                extra={
                    "theme_signature": theme_data.get("signature"),
                    "target_repo": self.target_repo,
                },
            )
            # Return error context with diagnostic details for debugging
            return {
                "classification": None,
                "relevant_files": [],
                "code_snippets": [],
                "exploration_duration_ms": 0,
                "classification_duration_ms": 0,
                "explored_at": datetime.now(timezone.utc).isoformat(),
                "success": False,
                "error": error_details,
            }

    def _build_issue_text_for_classification(
        self,
        theme_data: Dict[str, Any],
    ) -> str:
        """
        Build issue text from theme data for classification.

        Combines user_intent, symptoms, and excerpts into a coherent
        text that the classifier can analyze.

        Args:
            theme_data: Aggregated theme data

        Returns:
            Combined issue text for classification
        """
        parts = []

        # User intent is the primary signal
        if user_intent := theme_data.get("user_intent"):
            parts.append(f"Issue: {user_intent}")

        # Add symptoms as context
        if symptoms := theme_data.get("symptoms"):
            symptoms_text = ", ".join(symptoms[:5])  # Top 5
            parts.append(f"Symptoms: {symptoms_text}")

        # Add product area and component if available
        if product_area := theme_data.get("product_area"):
            parts.append(f"Product Area: {product_area}")

        if component := theme_data.get("component"):
            parts.append(f"Component: {component}")

        # Add excerpt text if available
        excerpts = theme_data.get("excerpts", [])
        if excerpts:
            # Get first excerpt text
            first_excerpt = excerpts[0]
            if isinstance(first_excerpt, dict):
                excerpt_text = first_excerpt.get("text", "")
            else:
                excerpt_text = str(first_excerpt)
            if excerpt_text:
                parts.append(f"Customer message: {excerpt_text[:500]}")

        return "\n".join(parts)

    def _build_code_context_dict(
        self,
        exploration_result,  # ExplorationResult
        classification_result,  # Optional[ClassificationResult]
    ) -> Dict[str, Any]:
        """
        Build code_context dict from exploration and classification results.

        This dict is stored as JSONB in stories.code_context column.

        Args:
            exploration_result: Result from codebase exploration
            classification_result: Result from issue classification (may be None)

        Returns:
            Dict ready for JSON serialization and storage
        """
        # Build classification sub-dict
        classification_dict = None
        classification_duration = 0

        if classification_result:
            classification_dict = {
                "category": classification_result.category,
                "confidence": classification_result.confidence,
                "reasoning": classification_result.reasoning,
                "keywords_matched": classification_result.keywords_matched,
            }
            classification_duration = classification_result.classification_duration_ms

        # Build relevant_files list
        relevant_files = []
        for file_ref in exploration_result.relevant_files:
            relevant_files.append({
                "path": file_ref.path,
                "line_start": file_ref.line_start,
                "line_end": file_ref.line_end,
                "relevance": file_ref.relevance,
            })

        # Build code_snippets list with length limits
        code_snippets = []
        for snippet in exploration_result.code_snippets:
            content = snippet.content
            if len(content) > MAX_CODE_SNIPPET_LENGTH:
                logger.debug(
                    f"Truncating code snippet from {snippet.file_path} "
                    f"({len(content)} -> {MAX_CODE_SNIPPET_LENGTH} chars)"
                )
                content = content[:MAX_CODE_SNIPPET_LENGTH] + "\n... (truncated)"
            code_snippets.append({
                "file_path": snippet.file_path,
                "line_start": snippet.line_start,
                "line_end": snippet.line_end,
                "content": content,
                "language": snippet.language,
                "context": snippet.context,
            })

        return {
            "classification": classification_dict,
            "relevant_files": relevant_files,
            "code_snippets": code_snippets,
            "exploration_duration_ms": exploration_result.exploration_duration_ms,
            "classification_duration_ms": classification_duration,
            "explored_at": datetime.now(timezone.utc).isoformat(),
            "success": exploration_result.success,
            "error": exploration_result.error,
        }
