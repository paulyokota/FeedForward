"""
Story Creation Service

Processes PM review results to create stories and orphans.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..models import (
    MIN_GROUP_SIZE,
    OrphanCreate,
    StoryCreate,
    EvidenceExcerpt,
)
from .orphan_service import OrphanService
from .story_service import StoryService
from .evidence_service import EvidenceService
from src.utils.normalize import (
    normalize_component,
    normalize_product_area,
    canonicalize_component,
)

# Quality gate imports (optional dependencies - graceful degradation if unavailable)
try:
    from src.evidence_validator import validate_samples, EvidenceQuality
    EVIDENCE_VALIDATOR_AVAILABLE = True
except ImportError:
    validate_samples = None
    EvidenceQuality = None
    EVIDENCE_VALIDATOR_AVAILABLE = False

try:
    from src.confidence_scorer import ConfidenceScorer, ScoredGroup
    CONFIDENCE_SCORER_AVAILABLE = True
except ImportError:
    ConfidenceScorer = None
    ScoredGroup = None
    CONFIDENCE_SCORER_AVAILABLE = False

# OrphanIntegrationService for unified orphan routing
try:
    from .orphan_integration import OrphanIntegrationService
    ORPHAN_INTEGRATION_AVAILABLE = True
except ImportError:
    OrphanIntegrationService = None
    ORPHAN_INTEGRATION_AVAILABLE = False

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

# PM Review Service (optional - graceful degradation if unavailable)
try:
    from .pm_review_service import (
        PMReviewService,
        PMReviewResult as PMReviewResultType,
        ReviewDecision,
        ConversationContext as PMConversationContext,
        SubGroupSuggestion,
    )
    PM_REVIEW_SERVICE_AVAILABLE = True
except ImportError:
    PMReviewService = None
    PMReviewResultType = None
    ReviewDecision = None
    PMConversationContext = None
    SubGroupSuggestion = None
    PM_REVIEW_SERVICE_AVAILABLE = False

# StoryContentGenerator for LLM-generated story content (optional)
try:
    from .story_content_generator import StoryContentGenerator, GeneratedStoryContent
    from src.prompts.story_content import StoryContentInput
    STORY_CONTENT_GENERATOR_AVAILABLE = True
except ImportError:
    StoryContentGenerator = None
    GeneratedStoryContent = None
    StoryContentInput = None
    STORY_CONTENT_GENERATOR_AVAILABLE = False

logger = logging.getLogger(__name__)

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
class FallbackPMReviewResult:
    """Fallback PM review result when PMReviewService is unavailable.

    Note: This is distinct from pm_review_service.PMReviewResult which is
    imported as PMReviewResultType. This simpler class is used for default
    keep_together decisions when PM review is disabled or encounters errors.
    """

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
    classification_category: Optional[str] = None  # Q2: Track actual category
    # Smart Digest fields (Issue #144) - used for PM Review when available
    diagnostic_summary: Optional[str] = None
    # Format: [{"text": "...", "relevance": "Why this matters"}, ...]
    key_excerpts: List[dict] = field(default_factory=list)

    # Issue #146: LLM-extracted resolution context
    resolution_action: Optional[str] = None
    root_cause: Optional[str] = None
    solution_provided: Optional[str] = None
    resolution_category: Optional[str] = None


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
    quality_gate_rejections: int = 0  # Track groups rejected by quality gates
    orphan_fallbacks: int = 0  # Track orphan integration failures that fell back to direct creation
    # PM Review metrics (Improvement 2: PM Review Before Story Creation)
    pm_review_splits: int = 0  # Groups that were split into sub-groups by PM review
    pm_review_rejects: int = 0  # Groups where all conversations rejected (routed to orphans)
    pm_review_kept: int = 0  # Groups kept together by PM review
    pm_review_skipped: int = 0  # Groups that bypassed PM review (disabled, timeout, or single-conv)


@dataclass
class QualityGateResult:
    """
    Result of running quality gates on a theme group.

    Used to determine whether a group should become a story or be routed
    to orphan integration for accumulation.

    Primary fields (used for routing decisions):
    - passed: Final pass/fail decision for story creation
    - confidence_score: Score used for story.confidence_score
    - failure_reason: Human-readable explanation when passed=False

    Diagnostic fields (for debugging and testing which specific gate failed):
    - validation_passed: True if evidence validation passed (or was skipped)
    - scoring_passed: True if confidence scoring passed (or was skipped)
    - evidence_quality: Full EvidenceQuality object for detailed validation diagnostics
    - scored_group: Full ScoredGroup object for detailed scoring diagnostics
    """

    signature: str
    passed: bool

    # Diagnostic fields (for testing/debugging which specific gate failed)
    evidence_quality: Optional[Any] = None  # EvidenceQuality if available
    validation_passed: bool = True  # True if validation gate passed or skipped

    scored_group: Optional[Any] = None  # ScoredGroup if available
    confidence_score: float = 0.0
    scoring_passed: bool = True  # True if scoring gate passed or skipped

    # Failure details for logging/debugging
    failure_reason: Optional[str] = None


# Default quality gate configuration
DEFAULT_CONFIDENCE_THRESHOLD = 50.0
DEFAULT_VALIDATION_ENABLED = True


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
        evidence_service: Optional[EvidenceService] = None,
        orphan_integration_service: Optional["OrphanIntegrationService"] = None,
        confidence_scorer: Optional["ConfidenceScorer"] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        validation_enabled: bool = DEFAULT_VALIDATION_ENABLED,
        dual_format_enabled: bool = False,
        target_repo: Optional[str] = None,
        pm_review_service: Optional["PMReviewService"] = None,
        pm_review_enabled: bool = False,
    ):
        """
        Initialize the story creation service.

        Args:
            story_service: Service for story CRUD operations
            orphan_service: Service for orphan CRUD operations
            evidence_service: Service for evidence bundle operations (optional)
            orphan_integration_service: Service for unified orphan routing (optional).
                                       Falls back to orphan_service.create() if not provided.
            confidence_scorer: Scorer for evaluating group coherence (optional).
                              Scoring is skipped if not provided.
            confidence_threshold: Minimum confidence score for story creation (default: 50.0).
                                 Groups below this threshold are routed to orphans.
            validation_enabled: If True, enforce evidence validation (default: True).
                               Set to False to disable validation during migration.
            dual_format_enabled: If True, generate dual-format stories (v2) with
                                codebase context. Default False for backward compatibility.
            target_repo: Repository name for codebase exploration (required if dual_format_enabled)
            pm_review_service: Service for PM review of theme groups (optional).
                              Required if pm_review_enabled=True.
            pm_review_enabled: If True, run PM review before story creation (default: False).
                              Feature flag for controlled rollout.
        """
        self.story_service = story_service
        self.orphan_service = orphan_service
        self.evidence_service = evidence_service
        self.dual_format_enabled = dual_format_enabled
        self.target_repo = target_repo

        # Quality gate configuration
        self.orphan_integration_service = orphan_integration_service
        self.confidence_scorer = confidence_scorer
        self.confidence_threshold = confidence_threshold
        self.validation_enabled = validation_enabled

        # PM Review configuration (Improvement 2)
        self.pm_review_service = pm_review_service
        self.pm_review_enabled = pm_review_enabled

        # Log quality gate configuration
        if confidence_scorer:
            logger.info(
                f"Quality gates enabled: confidence_threshold={confidence_threshold}, "
                f"validation_enabled={validation_enabled}"
            )
        else:
            logger.debug("ConfidenceScorer not provided, scoring will be skipped")

        if orphan_integration_service:
            logger.debug("OrphanIntegrationService provided for unified orphan routing")

        # Log PM review configuration
        if pm_review_enabled:
            if pm_review_service and PM_REVIEW_SERVICE_AVAILABLE:
                logger.info("PM review enabled for theme group coherence validation")
            else:
                logger.warning(
                    "PM review enabled but service not available. "
                    "PM review will be skipped."
                )
                self.pm_review_enabled = False

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

        # Initialize story content generator (optional - LLM-generated content)
        if STORY_CONTENT_GENERATOR_AVAILABLE:
            self.content_generator = StoryContentGenerator()
            logger.debug("StoryContentGenerator initialized for LLM-based story content")
        else:
            self.content_generator = None
            logger.debug("StoryContentGenerator not available, using mechanical fallbacks")

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

    def process_theme_groups(
        self,
        theme_groups: Dict[str, List[Dict[str, Any]]],
        pipeline_run_id: Optional[int] = None,
    ) -> ProcessingResult:
        """
        Process theme groups from pipeline directly (in-memory).

        This is the UI pipeline entry point for story creation. Converts
        the pipeline's theme data format into stories and orphans.

        Quality gates are applied at the top of the processing loop:
        1. EvidenceValidator checks for required fields (id, excerpt)
        2. ConfidenceScorer evaluates group coherence
        3. Groups failing either gate are routed to orphan integration

        Args:
            theme_groups: Dict mapping signature -> list of conversation dicts.
                Each conversation dict should have:
                - id: str (conversation_id)
                - product_area: Optional[str]
                - component: Optional[str]
                - user_intent: Optional[str]
                - symptoms: List[str]
                - affected_flow: Optional[str]
                - excerpt: Optional[str]

            pipeline_run_id: Optional pipeline run ID to link stories to

        Returns:
            ProcessingResult with counts and any errors
        """
        result = ProcessingResult()

        for signature, conv_dicts in theme_groups.items():
            try:
                # Convert dicts to ConversationData objects
                conversations = [
                    self._dict_to_conversation_data(d, signature)
                    for d in conv_dicts
                ]

                # QUALITY GATES: Apply validation and scoring BEFORE deciding story vs orphan
                gate_result = self._apply_quality_gates(signature, conversations, conv_dicts)

                if not gate_result.passed:
                    # Route to orphan integration (unified orphan logic)
                    self._route_to_orphan_integration(
                        signature=signature,
                        conversations=conversations,
                        failure_reason=gate_result.failure_reason or "Quality gate failed",
                        result=result,
                    )
                    result.quality_gate_rejections += 1
                    continue

                # PM REVIEW GATE: Evaluate group coherence (after quality gates pass)
                if self.pm_review_enabled and self.pm_review_service:
                    pm_review_result = self._run_pm_review(signature, conversations)

                    if pm_review_result.decision == ReviewDecision.SPLIT:
                        # Handle split: process sub-groups and orphans
                        self._handle_pm_split(
                            pm_review_result,
                            conversations,
                            result,
                            pipeline_run_id,
                            gate_result.confidence_score,
                        )
                        result.pm_review_splits += 1
                        continue
                    elif pm_review_result.decision == ReviewDecision.REJECT:
                        # All conversations are too different - route all to orphans
                        self._route_to_orphan_integration(
                            signature=signature,
                            conversations=conversations,
                            failure_reason=f"PM review rejected: {pm_review_result.reasoning}",
                            result=result,
                        )
                        result.pm_review_rejects += 1
                        continue
                    else:
                        # Keep together - continue to story creation
                        result.pm_review_kept += 1
                else:
                    # PM review disabled or not available
                    result.pm_review_skipped += 1

                # Generate default PM result (keep_together)
                pm_result = self._generate_pm_result(signature, len(conversations))

                # Process using existing logic, passing confidence score from gates
                self._process_single_result_with_pipeline_run(
                    pm_result=pm_result,
                    conversations=conversations,
                    result=result,
                    pipeline_run_id=pipeline_run_id,
                    confidence_score=gate_result.confidence_score,
                )

            except (KeyboardInterrupt, SystemExit):
                raise  # Never swallow these - let user/system interrupt
            except Exception as e:
                error_msg = f"Error processing theme group '{signature}': {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        logger.info(
            f"Processed theme groups: {result.stories_created} stories created, "
            f"{result.orphans_created} orphans created, "
            f"{result.orphans_updated} orphans updated, "
            f"{result.quality_gate_rejections} quality gate rejections, "
            f"PM review: {result.pm_review_kept} kept, {result.pm_review_splits} split, "
            f"{result.pm_review_rejects} rejected, {result.pm_review_skipped} skipped"
        )

        return result

    def process_hybrid_clusters(
        self,
        clustering_result: Any,  # ClusteringResult from hybrid_clustering_service
        conversation_data: Dict[str, Dict[str, Any]],
        pipeline_run_id: Optional[int] = None,
    ) -> ProcessingResult:
        """
        Process hybrid cluster output to create stories and orphans.

        This is the new entry point for #109 hybrid clustering integration.
        Replaces signature-based grouping with embedding + facet clustering.

        Args:
            clustering_result: ClusteringResult from HybridClusteringService containing:
                - clusters: List[HybridCluster] with cluster_id, action_type,
                  direction, and conversation_ids
                - fallback_conversations: List of conversation IDs missing data
            conversation_data: Dict mapping conversation_id -> conversation dict
                with fields: product_area, component, user_intent, symptoms,
                affected_flow, excerpt
            pipeline_run_id: Optional pipeline run ID to link stories to

        Returns:
            ProcessingResult with counts and any errors
        """
        result = ProcessingResult()

        if not clustering_result.success:
            for error in clustering_result.errors:
                result.errors.append(f"Clustering error: {error}")
            logger.error(
                f"Hybrid clustering failed with {len(clustering_result.errors)} errors"
            )
            return result

        logger.info(
            f"Processing {len(clustering_result.clusters)} hybrid clusters "
            f"({clustering_result.total_conversations} conversations)"
        )

        # Process each hybrid cluster
        for cluster in clustering_result.clusters:
            try:
                self._process_hybrid_cluster(
                    cluster=cluster,
                    conversation_data=conversation_data,
                    result=result,
                    pipeline_run_id=pipeline_run_id,
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                error_msg = f"Error processing cluster '{cluster.cluster_id}': {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        # Handle fallback conversations (missing embeddings/facets)
        if clustering_result.fallback_conversations:
            logger.info(
                f"Processing {len(clustering_result.fallback_conversations)} "
                "fallback conversations"
            )
            self._process_fallback_conversations(
                conversation_ids=clustering_result.fallback_conversations,
                conversation_data=conversation_data,
                result=result,
                pipeline_run_id=pipeline_run_id,
            )

        logger.info(
            f"Processed hybrid clusters: {result.stories_created} stories created, "
            f"{result.orphans_created} orphans created, "
            f"{result.orphans_updated} orphans updated"
        )

        return result

    def _process_hybrid_cluster(
        self,
        cluster: Any,  # HybridCluster from hybrid_clustering_service
        conversation_data: Dict[str, Dict[str, Any]],
        result: ProcessingResult,
        pipeline_run_id: Optional[int] = None,
    ) -> None:
        """
        Process a single hybrid cluster to create story or orphan.

        Args:
            cluster: HybridCluster with cluster_id, action_type, direction,
                    embedding_cluster, and conversation_ids
            conversation_data: Dict mapping conversation_id -> conversation dict
            result: ProcessingResult to update
            pipeline_run_id: Optional pipeline run ID
        """
        # Build conversation list for this cluster
        conversations = []
        conv_dicts = []
        for conv_id in cluster.conversation_ids:
            conv_dict = conversation_data.get(conv_id)
            if conv_dict:
                conv_dicts.append(conv_dict)
                conversations.append(
                    self._dict_to_conversation_data(conv_dict, cluster.cluster_id)
                )
            else:
                logger.warning(
                    f"Conversation {conv_id} not found in conversation_data "
                    f"for cluster {cluster.cluster_id}"
                )

        if not conversations:
            logger.warning(f"No valid conversations for cluster {cluster.cluster_id}")
            return

        # Compute stable signature for orphan accumulation (cross-run deterministic)
        # This replaces run-local emb_X_facet_Y_Z with semantic-based signature
        stable_signature = self._compute_stable_hybrid_signature(cluster, conversations)
        logger.debug(
            f"Hybrid cluster stable signature: {stable_signature} "
            f"(cluster_id={cluster.cluster_id})"
        )

        # Apply quality gates (same as signature-based flow)
        gate_result = self._apply_quality_gates(
            cluster.cluster_id, conversations, conv_dicts
        )

        if not gate_result.passed:
            # Route to orphan integration with stable signature for cross-run accumulation
            logger.info(
                f"Routing hybrid cluster to orphan (quality gate): "
                f"stable={stable_signature}, cluster_id={cluster.cluster_id}"
            )
            self._route_to_orphan_integration(
                signature=stable_signature,
                conversations=conversations,
                failure_reason=gate_result.failure_reason or "Quality gate failed",
                result=result,
            )
            result.quality_gate_rejections += 1
            return

        # Check minimum group size before PM review
        if len(conversations) < MIN_GROUP_SIZE:
            logger.info(
                f"Routing hybrid cluster to orphan (below MIN_GROUP_SIZE): "
                f"stable={stable_signature}, cluster_id={cluster.cluster_id}, "
                f"count={len(conversations)}"
            )
            self._route_to_orphan_integration(
                signature=stable_signature,
                conversations=conversations,
                failure_reason=f"Cluster has {len(conversations)} conversations (min: {MIN_GROUP_SIZE})",
                result=result,
            )
            return

        # PM REVIEW GATE: Validate hybrid cluster coherence
        # Even though clustering groups by embeddings + facets, PM review
        # catches edge cases where semantically similar conversations need
        # different implementations (e.g., DB query vs network latency issues)
        if self.pm_review_enabled and self.pm_review_service:
            pm_review_result = self._run_pm_review(cluster.cluster_id, conversations)

            if pm_review_result.decision == ReviewDecision.SPLIT:
                # Handle split: process sub-groups and orphans
                self._handle_pm_split(
                    pm_review_result,
                    conversations,
                    result,
                    pipeline_run_id,
                    gate_result.confidence_score,
                )
                result.pm_review_splits += 1
                return
            elif pm_review_result.decision == ReviewDecision.REJECT:
                # All conversations are too different - route all to orphans
                logger.info(
                    f"Routing hybrid cluster to orphan (PM rejected): "
                    f"stable={stable_signature}, cluster_id={cluster.cluster_id}"
                )
                self._route_to_orphan_integration(
                    signature=stable_signature,
                    conversations=conversations,
                    failure_reason=f"PM review rejected: {pm_review_result.reasoning}",
                    result=result,
                )
                result.pm_review_rejects += 1
                return
            else:
                # PM review approved - continue to story creation
                result.pm_review_kept += 1
        else:
            # PM review disabled - skip check
            result.pm_review_skipped += 1

        # Create story from hybrid cluster (after PM review approval or skip)
        self._create_story_from_hybrid_cluster(
            cluster=cluster,
            conversations=conversations,
            result=result,
            pipeline_run_id=pipeline_run_id,
            confidence_score=gate_result.confidence_score,
        )

    def _create_story_from_hybrid_cluster(
        self,
        cluster: Any,  # HybridCluster
        conversations: List["ConversationData"],
        result: ProcessingResult,
        pipeline_run_id: Optional[int] = None,
        confidence_score: Optional[float] = None,
    ) -> None:
        """
        Create a story from a hybrid cluster.

        Generates title from facet data and sample conversations.
        Stores cluster metadata for audit/tracing.

        Args:
            cluster: HybridCluster with action_type, direction, etc.
            conversations: List of ConversationData objects
            result: ProcessingResult to update
            pipeline_run_id: Optional pipeline run ID
            confidence_score: Optional confidence score from quality gates
        """
        # Build theme data from conversations
        theme_data = self._build_theme_data(conversations)

        # Generate title from cluster facets + theme data
        title = self._generate_hybrid_cluster_title(cluster, theme_data)

        # Build cluster metadata for storage
        cluster_metadata = {
            "embedding_cluster": cluster.embedding_cluster,
            "action_type": cluster.action_type,
            "direction": cluster.direction,
            "conversation_count": len(conversations),
        }

        # Generate description
        description = self._generate_hybrid_cluster_description(
            cluster=cluster,
            theme_data=theme_data,
        )

        # Explore codebase with classification (Issue #44)
        code_context = None
        if self.dual_format_enabled:
            code_context = self._explore_codebase_with_classification(theme_data)

        # Create story with hybrid cluster metadata
        story = self.story_service.create(StoryCreate(
            title=title,
            description=description,
            labels=[],
            confidence_score=confidence_score,
            product_area=theme_data.get("product_area"),
            technical_area=theme_data.get("component"),
            status="candidate",
            code_context=code_context,
            # Hybrid clustering fields (#109)
            grouping_method="hybrid_cluster",
            cluster_id=cluster.cluster_id,
            cluster_metadata=cluster_metadata,
        ))

        result.stories_created += 1
        result.created_story_ids.append(story.id)

        # Link to pipeline run if provided
        if pipeline_run_id is not None:
            if not self._link_story_to_pipeline_run(story.id, pipeline_run_id):
                result.errors.append(
                    f"Story {story.id} created but failed to link to pipeline run {pipeline_run_id}"
                )

        # Create evidence bundle
        if self.evidence_service:
            if not self._create_evidence_for_story(
                story_id=story.id,
                signature=cluster.cluster_id,
                conversations=conversations,
                theme_data=theme_data,
            ):
                result.errors.append(
                    f"Story {story.id} created but failed to create evidence bundle"
                )

        logger.info(
            f"Created hybrid cluster story {story.id}: '{title}' "
            f"(cluster={cluster.cluster_id}, {len(conversations)} conversations)"
        )

    def _generate_hybrid_cluster_title(
        self,
        cluster: Any,  # HybridCluster
        theme_data: Dict[str, Any],
    ) -> str:
        """
        Generate story title from hybrid cluster data.

        Strategy:
        1. If user_intent available and meaningful, use it
        2. Otherwise, generate from action_type + direction + symptoms

        Args:
            cluster: HybridCluster with action_type, direction
            theme_data: Aggregated theme data from conversations

        Returns:
            Human-readable story title
        """
        # Try user_intent first
        user_intent = theme_data.get("user_intent")
        if user_intent and len(user_intent.strip()) > MIN_USER_INTENT_LENGTH:
            return _truncate_at_word_boundary(user_intent.strip(), MAX_TITLE_LENGTH)

        # Build title from facets
        action_type = cluster.action_type.replace("_", " ").title()
        direction = cluster.direction.replace("_", " ")

        # Add symptom context if available
        symptoms = theme_data.get("symptoms", [])
        if symptoms:
            symptom_hint = symptoms[0][:50]  # First symptom, truncated
            title = f"{action_type}: {symptom_hint}"
        else:
            # Fallback to action + direction
            if direction and direction != "neutral":
                title = f"{action_type} ({direction})"
            else:
                title = action_type

        return _truncate_at_word_boundary(title, MAX_TITLE_LENGTH)

    def _generate_hybrid_cluster_description(
        self,
        cluster: Any,  # HybridCluster
        theme_data: Dict[str, Any],
    ) -> str:
        """
        Generate story description from hybrid cluster data.

        Includes facet information and aggregated conversation data.

        Args:
            cluster: HybridCluster with action_type, direction
            theme_data: Aggregated theme data from conversations

        Returns:
            Markdown-formatted story description
        """
        parts = []

        # Cluster facet info
        parts.append(f"**Action Type**: {cluster.action_type}")
        parts.append(f"**Direction**: {cluster.direction}")

        # Theme data
        if user_intent := theme_data.get("user_intent"):
            parts.append(f"\n**User Intent**: {user_intent}")

        if symptoms := theme_data.get("symptoms"):
            parts.append(f"**Symptoms**: {', '.join(symptoms[:MAX_SYMPTOMS_IN_DESCRIPTION])}")

        if product_area := theme_data.get("product_area"):
            parts.append(f"**Product Area**: {product_area}")

        if component := theme_data.get("component"):
            parts.append(f"**Component**: {component}")

        if affected_flow := theme_data.get("affected_flow"):
            parts.append(f"**Affected Flow**: {affected_flow}")

        # Cluster metadata
        parts.append(f"\n*Cluster ID*: `{cluster.cluster_id}`")
        parts.append(f"*Grouping Method*: `hybrid_cluster`")

        return "\n\n".join(parts)

    def _compute_stable_hybrid_signature(
        self,
        cluster: Any,  # HybridCluster
        conversations: List["ConversationData"],
    ) -> str:
        """
        Compute a stable semantic signature for hybrid cluster orphans.

        Unlike cluster_id (emb_X_facet_Y_Z) which is run-local, this signature
        is deterministic based on semantic content, enabling cross-run accumulation.

        Format: hybrid_{action_type}_{direction}_{product_area}_{component}_{issue_part}

        Priority for issue_part (most stable to least stable):
        1. issue_signature (from theme extraction) - most stable
        2. symptoms fallback - only if issue_signature unavailable

        IMPORTANT: issue_signature in hybrid clusters is often set to cluster_id
        (emb_*), which is run-local. We must skip those to maintain stability.

        Args:
            cluster: HybridCluster with action_type and direction
            conversations: List of ConversationData with product_area, component, etc.

        Returns:
            Stable signature string for orphan matching
        """
        from collections import Counter

        def most_common_deterministic(values: list, fallback: str) -> str:
            """Pick most common value with deterministic tie-breaking (alphabetical)."""
            if not values:
                return fallback
            counts = Counter(values)
            top = counts.most_common()
            max_count = top[0][1]
            # Sort tied values alphabetically for determinism
            tied = sorted([v for v, c in top if c == max_count])
            return tied[0]

        action_type = cluster.action_type or "unknown"
        direction = cluster.direction or "neutral"

        # Get most common product_area (deterministic on ties)
        # Normalize before counting to ensure "performance tracking" == "performance_tracking"
        product_areas = [
            normalize_product_area(c.product_area)
            for c in conversations if c.product_area
        ]
        product_area = most_common_deterministic(product_areas, "general")

        # Get most common component (deterministic on ties)
        # Canonicalize before counting to ensure:
        # - Format normalization: "performance tracking" == "performance_tracking"
        # - Semantic canonicalization: "smartschedule" == "smart_schedule" (via alias map)
        components = [
            canonicalize_component(c.component, product_area)
            for c in conversations if c.component
        ]
        component = most_common_deterministic(components, "unknown")

        # Prefer issue_signature over symptoms (more stable across runs)
        # Skip:
        # - "unclassified" signatures (not meaningful)
        # - "emb_*" signatures (run-local cluster IDs, NOT stable)
        issue_sig = next(
            (
                c.issue_signature
                for c in conversations
                if c.issue_signature
                and "unclassified" not in c.issue_signature.lower()
                and not c.issue_signature.startswith("emb_")  # skip run-local IDs
            ),
            None,
        )

        if issue_sig:
            # Use issue_signature (most stable)
            issue_part = issue_sig.lower().replace(" ", "_").replace("-", "_")[:40]
        else:
            # Fallback to symptoms (less stable, but better than nothing)
            all_symptoms = []
            for c in conversations:
                if c.symptoms:
                    all_symptoms.extend(c.symptoms)

            if all_symptoms:
                top_symptoms = [s for s, _ in Counter(all_symptoms).most_common(2)]
                top_symptoms.sort()
                issue_part = "_".join(
                    s.lower().replace(" ", "_").replace("-", "_")[:20]
                    for s in top_symptoms
                )
            else:
                issue_part = "unspecified"

        return f"hybrid_{action_type}_{direction}_{product_area}_{component}_{issue_part}"

    def _process_fallback_conversations(
        self,
        conversation_ids: List[str],
        conversation_data: Dict[str, Dict[str, Any]],
        result: ProcessingResult,
        pipeline_run_id: Optional[int] = None,
    ) -> None:
        """
        Process fallback conversations (missing embeddings/facets).

        Routes these to orphan integration since they couldn't be clustered.

        Args:
            conversation_ids: List of conversation IDs without embeddings/facets
            conversation_data: Dict mapping conversation_id -> conversation dict
            result: ProcessingResult to update
            pipeline_run_id: Optional pipeline run ID
        """
        for conv_id in conversation_ids:
            conv_dict = conversation_data.get(conv_id)
            if not conv_dict:
                logger.warning(f"Fallback conversation {conv_id} not found in data")
                continue

            # Use the issue_signature from theme extraction as the orphan signature
            signature = conv_dict.get("issue_signature", f"fallback_{conv_id}")

            try:
                conversation = self._dict_to_conversation_data(conv_dict, signature)
                self._route_to_orphan_integration(
                    signature=signature,
                    conversations=[conversation],
                    failure_reason="Missing embeddings/facets for clustering",
                    result=result,
                )
            except Exception as e:
                logger.warning(f"Failed to process fallback conversation {conv_id}: {e}")
                result.errors.append(f"Fallback conversation {conv_id} error: {e}")

    def _apply_quality_gates(
        self,
        signature: str,
        conversations: List[ConversationData],
        conv_dicts: List[Dict[str, Any]],
    ) -> QualityGateResult:
        """
        Apply validation and confidence scoring to a theme group.

        This method runs both quality gates and combines results into a single
        pass/fail decision. Gates run in order (validation fast, scoring may call API).

        Args:
            signature: Issue signature for the group
            conversations: List of ConversationData objects
            conv_dicts: Original conversation dicts (for ConfidenceScorer which expects dicts)

        Returns:
            QualityGateResult with pass/fail and details
        """
        # Start with a passing result
        result = QualityGateResult(
            signature=signature,
            passed=True,
            validation_passed=True,
            scoring_passed=True,
        )

        # Early exit: groups with < MIN_GROUP_SIZE always fail (preserves existing behavior)
        # Note: This check is also in _process_single_result_with_pipeline_run, but we
        # duplicate it here to give a clear failure reason in quality gate results.
        if len(conversations) < MIN_GROUP_SIZE:
            result.passed = False
            result.failure_reason = f"Group has {len(conversations)} conversations, minimum is {MIN_GROUP_SIZE}"
            logger.debug(f"Quality gate FAIL for '{signature}': {result.failure_reason}")
            return result

        # GATE 1: Evidence Validation (if enabled)
        if self.validation_enabled and EVIDENCE_VALIDATOR_AVAILABLE and validate_samples:
            try:
                evidence_quality = validate_samples(conv_dicts)
                result.evidence_quality = evidence_quality

                if not evidence_quality.is_valid:
                    result.passed = False
                    result.validation_passed = False
                    result.failure_reason = f"Evidence validation failed: {'; '.join(evidence_quality.errors)}"
                    logger.info(
                        f"Quality gate FAIL (validation) for '{signature}': "
                        f"{result.failure_reason}"
                    )
                    return result
                else:
                    logger.debug(
                        f"Evidence validation PASS for '{signature}': "
                        f"{evidence_quality.sample_count} samples"
                    )
            except Exception as e:
                # Conservative: treat validation errors as failures
                result.passed = False
                result.validation_passed = False
                result.failure_reason = f"Evidence validation error: {e}"
                logger.warning(
                    f"Quality gate FAIL (validation error) for '{signature}': {e}"
                )
                return result

        # GATE 2: Confidence Scoring (if scorer available)
        if self.confidence_scorer:
            try:
                # ConfidenceScorer expects {signature: [dicts]} format
                scored_groups = self.confidence_scorer.score_groups(
                    {signature: conv_dicts},
                    verbose=False,
                )

                if scored_groups:
                    scored_group = scored_groups[0]
                    result.scored_group = scored_group
                    result.confidence_score = scored_group.confidence_score

                    if scored_group.confidence_score < self.confidence_threshold:
                        result.passed = False
                        result.scoring_passed = False
                        result.failure_reason = (
                            f"Confidence score {scored_group.confidence_score:.1f} "
                            f"below threshold {self.confidence_threshold:.1f}"
                        )
                        logger.info(
                            f"Quality gate FAIL (confidence) for '{signature}': "
                            f"{result.failure_reason}"
                        )
                        return result
                    else:
                        logger.debug(
                            f"Confidence scoring PASS for '{signature}': "
                            f"score={scored_group.confidence_score:.1f}"
                        )
            except Exception as e:
                # Conservative: treat scoring errors as failures (API rate limit, etc.)
                result.passed = False
                result.scoring_passed = False
                result.failure_reason = f"Confidence scoring error: {e}"
                logger.warning(
                    f"Quality gate FAIL (scoring error) for '{signature}': {e}"
                )
                return result
        else:
            # No scorer configured - skip scoring, treat as passed
            logger.debug(f"Confidence scoring skipped for '{signature}' (no scorer configured)")
            # Set a default confidence score for groups without scoring
            result.confidence_score = 0.0

        logger.debug(f"Quality gates PASS for '{signature}'")
        return result

    def _route_to_orphan_integration(
        self,
        signature: str,
        conversations: List[ConversationData],
        failure_reason: str,
        result: ProcessingResult,
    ) -> None:
        """
        Route a failed group to OrphanIntegrationService for accumulation.

        Uses OrphanIntegrationService if available, otherwise falls back to
        direct OrphanService.create() via _create_or_update_orphan().

        Args:
            signature: Issue signature for the group
            conversations: List of ConversationData objects
            failure_reason: Why the group failed quality gates
            result: ProcessingResult to update
        """
        logger.info(
            f"Routing '{signature}' to orphan integration: {failure_reason} "
            f"({len(conversations)} conversations)"
        )

        # Try OrphanIntegrationService first (unified orphan logic)
        if self.orphan_integration_service:
            # Track successfully processed conversations in case of mid-loop failure
            processed_conv_ids: set[str] = set()
            # Track actions to update metrics correctly (Issue #155 PR feedback)
            actions_seen: dict[str, int] = {"created": 0, "updated": 0, "graduated": 0}
            graduated_story_ids: list[str] = []
            try:
                for conv in conversations:
                    # Build theme data dict for orphan integration
                    theme_data = {
                        "conversation_id": conv.id,
                        "id": conv.id,
                        "issue_signature": signature,
                        "user_intent": conv.user_intent,
                        "symptoms": conv.symptoms,
                        "product_area": conv.product_area,
                        "component": conv.component,
                        "affected_flow": conv.affected_flow,
                        "excerpt": conv.excerpt,
                    }
                    match_result = self.orphan_integration_service.process_theme(conv.id, theme_data)
                    processed_conv_ids.add(conv.id)

                    # Track action for accurate metrics
                    if match_result and match_result.action:
                        if match_result.action in actions_seen:
                            actions_seen[match_result.action] += 1
                        if match_result.action == "graduated" and match_result.story_id:
                            graduated_story_ids.append(match_result.story_id)

                # Update metrics based on actual actions (not just orphans_updated)
                if actions_seen["graduated"] > 0:
                    result.stories_created += actions_seen["graduated"]
                    for story_id in graduated_story_ids:
                        try:
                            result.created_story_ids.append(UUID(story_id))
                        except (ValueError, TypeError):
                            pass  # Invalid UUID, skip
                    logger.info(
                        f"OrphanIntegrationService graduated {actions_seen['graduated']} orphans to stories"
                    )
                if actions_seen["created"] > 0:
                    result.orphans_created += actions_seen["created"]
                if actions_seen["updated"] > 0:
                    result.orphans_updated += actions_seen["updated"]

                logger.debug(
                    f"Routed {len(conversations)} conversations to OrphanIntegrationService: "
                    f"created={actions_seen['created']}, updated={actions_seen['updated']}, "
                    f"graduated={actions_seen['graduated']}"
                )
                return

            except Exception as e:
                logger.warning(
                    f"OrphanIntegrationService failed for '{signature}': {e}, "
                    f"falling back to direct orphan creation for remaining conversations"
                )
                # Track the fallback occurrence
                result.orphan_fallbacks += 1
                # Filter out already-processed conversations to avoid duplicates
                remaining_conversations = [
                    c for c in conversations if c.id not in processed_conv_ids
                ]
                if not remaining_conversations:
                    # All conversations were processed before the failure
                    # Use actions tracked so far
                    if actions_seen["graduated"] > 0:
                        result.stories_created += actions_seen["graduated"]
                    if actions_seen["created"] > 0:
                        result.orphans_created += actions_seen["created"]
                    if actions_seen["updated"] > 0:
                        result.orphans_updated += actions_seen["updated"]
                    return
                # Fall through to fallback path with only remaining conversations
                conversations = remaining_conversations

        # Fallback: Use existing _create_or_update_orphan method
        self._create_or_update_orphan(
            signature=signature,
            original_signature=None,
            conversations=conversations,
            result=result,
        )

    def _run_pm_review(
        self,
        signature: str,
        conversations: List[ConversationData],
    ) -> "PMReviewResultType":
        """
        Run PM review on a theme group.

        Converts ConversationData to PMConversationContext and calls
        PMReviewService.review_group().

        Args:
            signature: Issue signature for the group
            conversations: List of ConversationData objects

        Returns:
            PMReviewResult from the PM review service
        """
        if not PM_REVIEW_SERVICE_AVAILABLE or not self.pm_review_service:
            # Return a default keep_together result
            logger.warning(f"PM review not available for '{signature}', defaulting to keep_together")
            return PMReviewResultType(
                original_signature=signature,
                conversation_count=len(conversations),
                decision=ReviewDecision.KEEP_TOGETHER,
                reasoning="PM review service not available",
            )

        # Convert ConversationData to PMConversationContext
        # Issue #144: Include Smart Digest fields for richer PM Review context
        # Issue #146: Include resolution fields for richer PM Review context
        pm_contexts = []
        for conv in conversations:
            pm_context = PMConversationContext(
                conversation_id=conv.id,
                user_intent=conv.user_intent or "",
                symptoms=conv.symptoms or [],
                affected_flow=conv.affected_flow or "",
                excerpt=conv.excerpt or "",
                product_area=conv.product_area or "",
                component=conv.component or "",
                # Smart Digest fields (Issue #144)
                diagnostic_summary=conv.diagnostic_summary or "",
                key_excerpts=conv.key_excerpts or [],
                # Issue #146: LLM-extracted resolution context
                resolution_action=conv.resolution_action or "",
                root_cause=conv.root_cause or "",
                solution_provided=conv.solution_provided or "",
                resolution_category=conv.resolution_category or "",
            )
            pm_contexts.append(pm_context)

        try:
            return self.pm_review_service.review_group(signature, pm_contexts)
        except Exception as e:
            # Edge case: Timeout or error during PM review -> mark as skipped
            logger.warning(f"PM review error for '{signature}': {e}")
            return PMReviewResultType(
                original_signature=signature,
                conversation_count=len(conversations),
                decision=ReviewDecision.KEEP_TOGETHER,
                reasoning=f"PM review error (defaulting to keep_together): {str(e)}",
            )

    def _handle_pm_split(
        self,
        pm_review_result: "PMReviewResultType",
        conversations: List[ConversationData],
        result: ProcessingResult,
        pipeline_run_id: Optional[int] = None,
        confidence_score: Optional[float] = None,
    ) -> None:
        """
        Handle PM review split decision by creating sub-group stories and orphans.

        Sub-groups with >= MIN_GROUP_SIZE conversations become stories.
        Sub-groups with < MIN_GROUP_SIZE conversations become orphans.

        Args:
            pm_review_result: Result from PM review with sub_groups and orphans
            conversations: Original list of ConversationData objects
            result: ProcessingResult to update
            pipeline_run_id: Optional pipeline run ID to link stories to
            confidence_score: Optional confidence score from quality gates
        """
        # Build conversation lookup by ID
        conv_by_id: Dict[str, ConversationData] = {c.id: c for c in conversations}

        # Process each sub-group
        for sub_group in pm_review_result.sub_groups:
            # Get conversations for this sub-group
            sub_convs = []
            for conv_id in sub_group.conversation_ids:
                # Use pop() to get-and-remove, preventing duplicate assignments
                conv = conv_by_id.pop(conv_id, None)
                if conv is not None:
                    sub_convs.append(conv)
                else:
                    # Conversation not found - either already assigned or invalid ID
                    logger.warning(
                        f"Sub-group conversation ID '{conv_id}' not found in original group "
                        f"(already assigned to another sub-group or invalid ID)"
                    )

            if len(sub_convs) >= MIN_GROUP_SIZE:
                # Create story for this sub-group
                self._create_story_with_evidence(
                    signature=sub_group.suggested_signature,
                    conversations=sub_convs,
                    reasoning=sub_group.rationale,
                    result=result,
                    pipeline_run_id=pipeline_run_id,
                    original_signature=pm_review_result.original_signature,
                    confidence_score=confidence_score,
                )
                logger.info(
                    f"Created story from PM split sub-group: '{sub_group.suggested_signature}' "
                    f"({len(sub_convs)} conversations)"
                )
            else:
                # Route to orphan integration (sub-group too small)
                self._route_to_orphan_integration(
                    signature=sub_group.suggested_signature,
                    conversations=sub_convs,
                    failure_reason=f"PM split sub-group has {len(sub_convs)} conversations (min: {MIN_GROUP_SIZE})",
                    result=result,
                )
                logger.info(
                    f"Routed PM split sub-group to orphans: '{sub_group.suggested_signature}' "
                    f"({len(sub_convs)} conversations)"
                )

        # Handle orphan conversations (don't fit any sub-group)
        if pm_review_result.orphan_conversation_ids:
            orphan_convs = []
            for cid in pm_review_result.orphan_conversation_ids:
                # Use pop() to prevent duplicate assignments
                conv = conv_by_id.pop(cid, None)
                if conv is not None:
                    orphan_convs.append(conv)
                else:
                    logger.warning(
                        f"Orphan conversation ID '{cid}' not found in original group "
                        f"(already assigned to a sub-group or invalid ID)"
                    )
            if orphan_convs:
                self._route_to_orphan_integration(
                    signature=pm_review_result.original_signature,
                    conversations=orphan_convs,
                    failure_reason="PM review classified as orphan (no matching sub-group)",
                    result=result,
                )
                logger.info(
                    f"Routed {len(orphan_convs)} orphan conversations from PM split"
                )

        # Edge case: All conversations become orphans after split
        # (handled by REJECT decision in process_theme_groups)

    def _dict_to_conversation_data(
        self,
        conv_dict: Dict[str, Any],
        signature: str,
    ) -> ConversationData:
        """
        Convert pipeline dict to ConversationData.

        Issue #144: Also extracts Smart Digest fields (diagnostic_summary, key_excerpts)
        for PM Review context.
        """
        # Validate conversation ID (S1: prevent empty IDs from propagating)
        conv_id = str(conv_dict.get("id", "")).strip()
        if not conv_id:
            raise ValueError(f"Empty conversation ID in theme group '{signature}'")

        return ConversationData(
            id=conv_id,
            issue_signature=signature,
            product_area=conv_dict.get("product_area"),
            component=conv_dict.get("component"),
            user_intent=conv_dict.get("user_intent"),
            symptoms=conv_dict.get("symptoms", []),
            affected_flow=conv_dict.get("affected_flow"),
            root_cause_hypothesis=None,  # Not in pipeline data
            excerpt=conv_dict.get("excerpt"),
            # Smart Digest fields (Issue #144)
            diagnostic_summary=conv_dict.get("diagnostic_summary"),
            key_excerpts=conv_dict.get("key_excerpts", []),
            # Issue #146: LLM-extracted resolution context
            resolution_action=conv_dict.get("resolution_action"),
            root_cause=conv_dict.get("root_cause"),
            solution_provided=conv_dict.get("solution_provided"),
            resolution_category=conv_dict.get("resolution_category"),
        )

    def _generate_pm_result(
        self,
        signature: str,
        conversation_count: int,
    ) -> FallbackPMReviewResult:
        """Generate default PM result (keep_together)."""
        return FallbackPMReviewResult(
            signature=signature,
            decision="keep_together",
            reasoning="Auto-generated from pipeline (no PM review)",
            sub_groups=[],
            conversation_count=conversation_count,
        )

    def _process_single_result_with_pipeline_run(
        self,
        pm_result: FallbackPMReviewResult,
        conversations: List[ConversationData],
        result: ProcessingResult,
        pipeline_run_id: Optional[int] = None,
        confidence_score: Optional[float] = None,
    ) -> None:
        """
        Process a single PM review decision with pipeline run linking.

        Similar to _process_single_result but:
        1. Takes conversations directly (not by signature lookup)
        2. Links created stories to pipeline_run_id
        3. Creates evidence bundles if evidence_service is available
        4. Passes confidence_score from quality gates to story creation

        Args:
            pm_result: PM review decision
            conversations: List of ConversationData objects
            result: ProcessingResult to update
            pipeline_run_id: Optional pipeline run ID to link story to
            confidence_score: Optional confidence score from quality gates
        """
        if pm_result.decision == "error":
            result.errors.append(f"PM review failed for {pm_result.signature}")
            return

        conversation_count = len(conversations) or pm_result.conversation_count or 0

        if pm_result.decision in ("keep_together", "split"):
            # Note: "split" falls through to keep_together for pipeline path.
            # Future PM review integration would process sub_groups differently.
            if pm_result.decision == "split":
                logger.debug(
                    f"Split decision for {pm_result.signature} - "
                    f"treating as keep_together (PM review not yet integrated)"
                )

            if conversation_count < MIN_GROUP_SIZE:
                # Create orphan for small groups
                self._create_or_update_orphan(
                    signature=pm_result.signature,
                    original_signature=None,
                    conversations=conversations,
                    result=result,
                )
            else:
                # Create story for valid groups
                self._create_story_with_evidence(
                    signature=pm_result.signature,
                    conversations=conversations,
                    reasoning=pm_result.reasoning,
                    result=result,
                    pipeline_run_id=pipeline_run_id,
                    confidence_score=confidence_score,
                )
        else:
            result.errors.append(
                f"Unknown decision '{pm_result.decision}' for {pm_result.signature}"
            )

    def _create_story_with_evidence(
        self,
        signature: str,
        conversations: List[ConversationData],
        reasoning: str,
        result: ProcessingResult,
        pipeline_run_id: Optional[int] = None,
        original_signature: Optional[str] = None,
        confidence_score: Optional[float] = None,
    ) -> None:
        """
        Create a story with evidence bundle and pipeline run linking.

        This is the main story creation path for pipeline-generated stories.

        Args:
            signature: Issue signature for the story
            conversations: List of ConversationData objects
            reasoning: PM review reasoning
            result: ProcessingResult to update
            pipeline_run_id: Optional pipeline run ID to link story to
            original_signature: Original signature if split from larger group
            confidence_score: Optional confidence score from quality gates
        """
        # Build theme data from conversations
        theme_data = self._build_theme_data(conversations)

        # Generate LLM-based story content (title, user story, AI goal)
        # Q2: Pass actual classification_category for correct action verb
        classification = theme_data.get("classification_category") or "product_issue"
        generated_content = self._generate_story_content(signature, theme_data, classification)

        # Explore codebase with classification (Issue #44)
        code_context = None
        if self.dual_format_enabled:
            code_context = self._explore_codebase_with_classification(theme_data)

        # Create story with confidence_score from quality gates
        story = self.story_service.create(StoryCreate(
            title=self._generate_title(signature, theme_data, generated_content),
            description=self._generate_description(
                signature,
                theme_data,
                reasoning,
                original_signature,
                generated_content,
            ),
            labels=[],
            confidence_score=confidence_score,
            product_area=theme_data.get("product_area"),
            technical_area=theme_data.get("component"),
            status="candidate",
            code_context=code_context,
        ))

        result.stories_created += 1
        result.created_story_ids.append(story.id)

        # Link to pipeline run if provided (S2: track linking failures)
        if pipeline_run_id is not None:
            if not self._link_story_to_pipeline_run(story.id, pipeline_run_id):
                result.errors.append(
                    f"Story {story.id} created but failed to link to pipeline run {pipeline_run_id}"
                )

        # Create evidence bundle if evidence_service is available (S3: track failures)
        if self.evidence_service:
            if not self._create_evidence_for_story(
                story_id=story.id,
                signature=signature,
                conversations=conversations,
                theme_data=theme_data,
            ):
                result.errors.append(
                    f"Story {story.id} created but failed to create evidence bundle"
                )

        code_context_info = ""
        if code_context and code_context.get("success"):
            files_count = len(code_context.get("relevant_files", []))
            code_context_info = f", {files_count} code files"

        logger.info(
            f"Created story {story.id} for '{signature}' "
            f"({len(conversations)} conversations{code_context_info})"
        )

    def _link_story_to_pipeline_run(
        self,
        story_id: UUID,
        pipeline_run_id: int,
    ) -> bool:
        """
        Link a story to a pipeline run.

        Uses the shared connection from story_service. The UPDATE will be
        committed when the outer connection context manager exits.

        Returns:
            True if successful, False if failed
        """
        try:
            with self.story_service.db.cursor() as cur:
                cur.execute("""
                    UPDATE stories SET pipeline_run_id = %s WHERE id = %s
                """, (pipeline_run_id, str(story_id)))
            return True
        except Exception as e:
            logger.warning(f"Failed to link story {story_id} to pipeline run {pipeline_run_id}: {e}")
            return False

    def _create_evidence_for_story(
        self,
        story_id: UUID,
        signature: str,
        conversations: List[ConversationData],
        theme_data: Dict[str, Any],
    ) -> bool:
        """
        Create evidence bundle for a story.

        Returns:
            True if successful or no evidence_service configured, False if failed
        """
        if not self.evidence_service:
            return True  # No-op success when service not configured

        try:
            # Build conversation IDs
            conversation_ids = [c.id for c in conversations]

            # Build excerpts
            excerpts = []
            for conv in conversations[:MAX_EXCERPTS_IN_THEME]:
                if conv.excerpt:
                    excerpts.append(EvidenceExcerpt(
                        text=conv.excerpt[:MAX_EXCERPT_LENGTH],
                        source="intercom",  # Default source
                        conversation_id=conv.id,
                    ))

            # Calculate source stats (default to intercom)
            source_stats = {"intercom": len(conversations)}

            # Create evidence bundle
            self.evidence_service.create_or_update(
                story_id=story_id,
                conversation_ids=conversation_ids,
                theme_signatures=[signature],
                source_stats=source_stats,
                excerpts=excerpts,
            )

            logger.debug(f"Created evidence bundle for story {story_id}")
            return True

        except Exception as e:
            logger.warning(f"Failed to create evidence for story {story_id}: {e}")
            return False

    def _process_single_result(
        self,
        pm_result: FallbackPMReviewResult,
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
        pm_result: FallbackPMReviewResult,
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

        # Generate LLM-based story content (title, user story, AI goal)
        # Q2: Pass actual classification_category for correct action verb
        classification = theme_data.get("classification_category") or "product_issue"
        generated_content = self._generate_story_content(pm_result.signature, theme_data, classification)

        # Explore codebase with classification (Issue #44)
        code_context = None
        if self.dual_format_enabled:
            code_context = self._explore_codebase_with_classification(theme_data)

        # Create story
        story = self.story_service.create(StoryCreate(
            title=self._generate_title(pm_result.signature, theme_data, generated_content),
            description=self._generate_description(
                pm_result.signature,
                theme_data,
                pm_result.reasoning,
                generated_content=generated_content,
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
        pm_result: FallbackPMReviewResult,
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

        # Generate LLM-based story content (title, user story, AI goal)
        # Q2: Pass actual classification_category for correct action verb
        classification = theme_data.get("classification_category") or "product_issue"
        generated_content = self._generate_story_content(signature, theme_data, classification)

        # Explore codebase with classification (Issue #44)
        code_context = None
        if self.dual_format_enabled:
            code_context = self._explore_codebase_with_classification(theme_data)

        story = self.story_service.create(StoryCreate(
            title=self._generate_title(signature, theme_data, generated_content),
            description=self._generate_description(
                signature,
                theme_data,
                rationale,
                original_signature,
                generated_content,
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

    def _load_pm_results(self, path: Path) -> List[FallbackPMReviewResult]:
        """Load PM review results from JSON file."""
        with open(path) as f:
            data = json.load(f)

        results = []
        for item in data:
            results.append(FallbackPMReviewResult(
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
                    # Q2: Load classification from extraction data if available
                    classification_category=item.get("classification_category") or item.get("action_category"),
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

        # Use first non-null values for scalars (iterate to find non-null)
        def first_non_null(attr: str) -> Any:
            for conv in conversations:
                val = getattr(conv, attr, None)
                if val is not None:
                    return val
            return None

        return {
            "user_intent": first_non_null("user_intent"),
            "symptoms": unique_symptoms[:MAX_SYMPTOMS_IN_THEME],
            "product_area": first_non_null("product_area"),
            "component": first_non_null("component"),
            "affected_flow": first_non_null("affected_flow"),
            "root_cause_hypothesis": first_non_null("root_cause_hypothesis"),
            "excerpts": excerpts[:MAX_EXCERPTS_IN_THEME],
            # Q2: Include classification for proper action verb selection
            "classification_category": first_non_null("classification_category"),
            # Issue #146: LLM-extracted resolution context for story content
            "root_cause": first_non_null("root_cause"),
            "solution_provided": first_non_null("solution_provided"),
        }

    def _generate_story_content(
        self,
        signature: str,
        theme_data: Dict[str, Any],
        classification_category: str = "product_issue",
    ) -> Optional["GeneratedStoryContent"]:
        """
        Generate LLM-based story content for title, user story, and AI goal.

        Uses StoryContentGenerator to produce:
        - Outcome-focused title
        - Context-specific user type for user story
        - User story "I want" and "So that" clauses
        - AI agent goal with success criteria

        Args:
            signature: Issue signature
            theme_data: Aggregated theme data from conversations
            classification_category: Classification category for title verb selection

        Returns:
            GeneratedStoryContent if generator available, None otherwise.
            Callers should fall back to mechanical generation when None.
        """
        if not self.content_generator or not STORY_CONTENT_GENERATOR_AVAILABLE:
            return None

        # Build StoryContentInput from theme_data
        content_input = self._build_story_content_input(
            signature, theme_data, classification_category
        )

        try:
            generated_content = self.content_generator.generate(content_input)
            logger.debug(
                f"Generated story content for '{signature}': title='{generated_content.title[:50]}...'"
            )
            return generated_content
        except Exception as e:
            logger.warning(
                f"Story content generation failed for '{signature}': {e}. "
                f"Falling back to mechanical generation."
            )
            return None

    def _build_story_content_input(
        self,
        signature: str,
        theme_data: Dict[str, Any],
        classification_category: str = "product_issue",
    ) -> "StoryContentInput":
        """
        Build StoryContentInput from theme_data for content generation.

        Args:
            signature: Issue signature
            theme_data: Aggregated theme data
            classification_category: Classification category

        Returns:
            StoryContentInput ready for StoryContentGenerator
        """
        # Collect user_intents (may be single value or list in future)
        user_intent = theme_data.get("user_intent")
        user_intents = [user_intent] if user_intent else []

        # Get symptoms
        symptoms = theme_data.get("symptoms", [])

        # Get excerpts as text list
        excerpts_data = theme_data.get("excerpts", [])
        excerpts = []
        for exc in excerpts_data:
            if isinstance(exc, dict) and "text" in exc:
                excerpts.append(exc["text"])
            elif isinstance(exc, str):
                excerpts.append(exc)

        return StoryContentInput(
            user_intents=user_intents,
            symptoms=symptoms,
            issue_signature=signature,
            classification_category=classification_category,
            product_area=theme_data.get("product_area", "Unknown"),
            component=theme_data.get("component", "Unknown"),
            root_cause_hypothesis=theme_data.get("root_cause_hypothesis"),
            affected_flow=theme_data.get("affected_flow"),
            excerpts=excerpts[:3] if excerpts else None,  # Limit to 3 for prompt length
            # Issue #146: LLM-extracted resolution context for richer story content
            root_cause=theme_data.get("root_cause"),
            solution_provided=theme_data.get("solution_provided"),
        )

    def _generate_title(
        self,
        signature: str,
        theme_data: Dict[str, Any],
        generated_content: Optional["GeneratedStoryContent"] = None,
    ) -> str:
        """
        Generate a story title from signature and theme data.

        Args:
            signature: Issue signature
            theme_data: Aggregated theme data
            generated_content: Optional LLM-generated content with title.
                             If provided, uses the generated title.
                             Falls back to mechanical generation otherwise.

        Returns:
            Story title string
        """
        # Use LLM-generated title if available
        if generated_content and generated_content.title:
            return _truncate_at_word_boundary(generated_content.title, MAX_TITLE_LENGTH)

        # Fall back to mechanical generation
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
        generated_content: Optional["GeneratedStoryContent"] = None,
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
            generated_content: Optional LLM-generated content for user story and AI goal.
                             If provided, includes user_type, user_story_want,
                             user_story_benefit, and ai_agent_goal in formatted output.

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

        # Build formatter-compatible theme data with generated content
        formatter_theme_data = self._build_formatter_theme_data(
            signature, theme_data, reasoning, original_signature, generated_content
        )

        # Generate dual-format output with generated content
        dual_output = self.dual_formatter.format_story(
            theme_data=formatter_theme_data,
            exploration_result=exploration_result,
            generated_content=generated_content,
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
        generated_content: Optional["GeneratedStoryContent"] = None,
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
            generated_content: Optional LLM-generated content for user story fields

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

        # Use generated content for title and user story fields if available
        title = theme_data.get("user_intent") or signature.replace("_", " ").title()
        user_type = "Tailwind user"
        benefit = "achieve my goals without friction"

        if generated_content:
            if generated_content.title:
                title = generated_content.title
            if generated_content.user_type:
                user_type = generated_content.user_type
            if generated_content.user_story_benefit:
                benefit = generated_content.user_story_benefit

        return {
            "title": title,
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
            # Generated content fields for user story (from LLM)
            "user_type": user_type,
            "benefit": benefit,
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
