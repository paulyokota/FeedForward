"""
Theme extractor for identifying and canonicalizing conversation themes.

Uses product context to extract structured themes that can be aggregated,
tracked over time, and turned into actionable tickets.
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .research.unified_search import UnifiedSearchService

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from openai import OpenAI
import numpy as np

# Handle both module and script execution
try:
    from .db.models import Conversation
except ImportError:
    from db.models import Conversation

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def validate_signature_specificity(
    signature: str,
    symptoms: Optional[List[str]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Validate that a signature is specific enough for the SAME_FIX test.

    The SAME_FIX test: Two conversations should ONLY share a signature if:
    1. One code change would fix BOTH
    2. One developer could own the fix
    3. One acceptance test verifies both are fixed

    Returns:
        (is_valid, suggestion) - suggestion is a more specific signature hint if invalid

    Examples:
        >>> validate_signature_specificity("pinterest_publishing_failure")
        (False, "Consider more specific: pinterest_[specific_symptom]")

        >>> validate_signature_specificity("pinterest_duplicate_pins")
        (True, None)
    """
    # BANNED PATTERNS - These are ALWAYS too broad (no exceptions)
    BANNED_SUFFIXES = [
        '_question',      # feature_question, analytics_question
        '_guidance',      # settings_guidance, usage_guidance
    ]
    BANNED_CONTAINS = [
        '_interpretation_',  # analytics_interpretation_question
        'general_',          # general_product_question
    ]

    # Check banned patterns first (hard reject)
    for suffix in BANNED_SUFFIXES:
        if signature.endswith(suffix):
            base = signature[:-len(suffix)]
            suggestion = f"BANNED pattern: {suffix}. Use specific signature like {base}_[specific_action]"
            logger.warning(f"Signature '{signature}' uses banned pattern '{suffix}'. {suggestion}")
            return False, suggestion

    for pattern in BANNED_CONTAINS:
        if pattern in signature:
            suggestion = f"BANNED pattern: {pattern}. Create a specific signature for the actual issue."
            logger.warning(f"Signature '{signature}' uses banned pattern '{pattern}'. {suggestion}")
            return False, suggestion

    # Broad failure indicators that suggest over-generalization
    BROAD_SUFFIXES = [
        '_failure',   # pinterest_publishing_failure
        '_issue',     # scheduling_issue
        '_problem',   # oauth_problem
        '_error',     # api_error (unless specific like timeout_error)
    ]

    # Specific symptom indicators that are acceptable even with broad suffixes
    # NOTE: Keep this list focused on patterns with real usage evidence (YAGNI)
    SPECIFIC_PATTERNS = [
        # Core symptom patterns (high-frequency issues)
        '_duplicate_',    # duplicate_pins - idempotency issues
        '_missing_',      # missing_pins - data sync issues
        '_timeout_',      # timeout_error - retry/timeout config
        '_permission_',   # permission_denied - auth/access issues
        '_encoding_',     # encoding_error - data format issues
        # Component-specific patterns (tested in theme_extractor_specificity tests)
        '_sync_',         # sync_failure - sync operations
        '_oauth_',        # oauth_failure - auth flows
        '_connection_',   # connection_failure - connectivity
        '_upload_',       # upload_failure - file uploads
        '_loading_',      # loading_failure - UI loading states
        '_video_',        # video_upload - media type specific
        '_image_',        # image_loading - media type specific
    ]

    # Check if signature ends with a broad suffix
    for suffix in BROAD_SUFFIXES:
        if signature.endswith(suffix):
            # Check if it has a specific pattern that makes it acceptable
            has_specific = any(p in signature for p in SPECIFIC_PATTERNS)
            if not has_specific:
                # Extract the base (e.g., "pinterest_publishing" from "pinterest_publishing_failure")
                base = signature[:-len(suffix)]
                suggestion = f"Consider more specific: {base}_[specific_symptom]"
                logger.warning(
                    f"Signature '{signature}' may be too broad. "
                    f"SAME_FIX test: Would one code change fix ALL conversations with this signature? "
                    f"{suggestion}"
                )
                return False, suggestion

    return True, None


# Load product context
PRODUCT_CONTEXT_PATH = Path(__file__).parent.parent / "context" / "product"


def load_product_context() -> str:
    """
    Load product documentation for context.

    Priority order (Issue #144 - Smart Digest Phase 2):
    1. pipeline-disambiguation.md - FIRST (helps disambiguate similar features)
    2. support-knowledge.md - Common issues and troubleshooting
    3. tailwind-taxonomy.md - Product structure overview
    4. Other .md files

    Context limits increased from 15K to 30K per file to support richer analysis.
    """
    context_parts = []

    # Priority-ordered files (load these first)
    priority_files = [
        "pipeline-disambiguation.md",  # Feature disambiguation (most important)
        "support-knowledge.md",         # Common issues and solutions
        "tailwind-taxonomy.md",         # Product structure
    ]

    if not PRODUCT_CONTEXT_PATH.exists():
        return ""

    # Load priority files first
    for filename in priority_files:
        filepath = PRODUCT_CONTEXT_PATH / filename
        if filepath.exists():
            content = filepath.read_text()
            # Increased limit from 15K to 30K for richer context
            if len(content) > 30000:
                content = content[:30000] + "\n\n[truncated for length]"
            context_parts.append(f"# {filepath.stem}\n\n{content}")

    # Load remaining .md files (not in priority list)
    priority_set = set(priority_files)
    for file in PRODUCT_CONTEXT_PATH.glob("*.md"):
        if file.name not in priority_set:
            content = file.read_text()
            if len(content) > 30000:
                content = content[:30000] + "\n\n[truncated for length]"
            context_parts.append(f"# {file.stem}\n\n{content}")

    return "\n\n---\n\n".join(context_parts)


def prepare_conversation_for_extraction(
    full_conversation: str,
    max_chars: int = 400_000,  # ~100K tokens, leaves headroom for prompt
) -> str:
    """
    Prepare conversation text for theme extraction with smart truncation.

    For the vast majority of conversations, this returns the input unchanged.
    Truncation is only applied for edge cases exceeding the token limit.

    Truncation strategy (if needed):
    1. Always keep first 2 messages (problem statement + initial context)
    2. Always keep last 3 messages (most recent context with error details)
    3. Truncate middle if necessary, adding "[... N messages omitted ...]"

    Args:
        full_conversation: Complete conversation text with all messages
        max_chars: Maximum character limit (~100K tokens = 400K chars)

    Returns:
        Conversation text safe for LLM context window

    Note:
        This function assumes messages are separated by double newlines.
        The 60/40 split prioritizes early context (problem statement) while
        preserving recent details (error codes, symptoms discovered later).
    """
    if not full_conversation:
        return ""

    # Fast path: most conversations are well under the limit
    if len(full_conversation) <= max_chars:
        return full_conversation

    logger.warning(
        f"Conversation exceeds {max_chars} chars ({len(full_conversation)} chars), "
        "applying smart truncation"
    )

    # Split by message boundaries (double newline is common separator)
    messages = full_conversation.split("\n\n")

    if len(messages) <= 5:
        # Can't meaningfully truncate, just hard-truncate
        return full_conversation[:max_chars] + "\n\n[... truncated for length ...]"

    # Keep first 2 messages (problem statement + initial context)
    first_messages = messages[:2]
    first_text = "\n\n".join(first_messages)

    # Keep last 3 messages (most recent context)
    last_messages = messages[-3:]
    last_text = "\n\n".join(last_messages)

    # Middle messages to potentially truncate
    middle_messages = messages[2:-3]

    # Calculate available space for middle section
    # Account for omission marker
    omission_marker = "\n\n[... {} messages omitted for length ...]\n\n"
    overhead = len(first_text) + len(last_text) + len(omission_marker.format(999))
    available_for_middle = max_chars - overhead

    if available_for_middle <= 0:
        # Edge case: first + last already exceed limit
        # Keep first 60%, last 40% with marker in between
        split_point = int(max_chars * 0.6)
        first_portion = full_conversation[:split_point].rsplit("\n\n", 1)[0]
        last_portion = full_conversation[-(max_chars - split_point - 50):].split("\n\n", 1)[-1]
        return f"{first_portion}\n\n[... content truncated ...]\n\n{last_portion}"

    # Include as many middle messages as fit
    included_middle = []
    current_length = 0

    for msg in middle_messages:
        msg_length = len(msg) + 2  # +2 for "\n\n" separator
        if current_length + msg_length <= available_for_middle:
            included_middle.append(msg)
            current_length += msg_length
        else:
            break

    omitted_count = len(middle_messages) - len(included_middle)

    if omitted_count > 0:
        middle_text = "\n\n".join(included_middle) if included_middle else ""
        marker = omission_marker.format(omitted_count)
        return f"{first_text}\n\n{middle_text}{marker}{last_text}"
    else:
        # All middle messages fit
        middle_text = "\n\n".join(middle_messages)
        return f"{first_text}\n\n{middle_text}\n\n{last_text}"


THEME_EXTRACTION_PROMPT = """You are a product analyst for Tailwind, a social media scheduling tool focused on Pinterest, Instagram, and Facebook.

Your job is to extract a structured "theme" from a customer support conversation. Themes help us:
1. Detect when multiple customers have the same issue
2. Track trends over time
3. Create actionable tickets for engineering/product

## Product Context

{product_context}

{url_context_hint}

{research_context}

## KNOWN THEMES

{known_themes}

{signature_quality_examples}

{strict_mode_instructions}

## Theme Structure

Extract these fields:

1. **product_area**: The main product area (one of):
   - scheduling (Pin Scheduler, SmartSchedule, Pin Spacing, Multi-Network Scheduler)
   - ai_creation (SmartPin, Ghostwriter, Tailwind Create)
   - pinterest_publishing (pins, boards, Pinterest API issues)
   - instagram_publishing (posts, stories, reels)
   - facebook_publishing (pages, posts)
   - communities (Tailwind Communities)
   - analytics (keyword research, performance tracking)
   - billing (plans, credits, payments, subscriptions)
   - account (login, connections, OAuth, profile management)
   - integrations (Canva, browser extension, CSV import, e-commerce)
   - other

2. **component**: The specific feature or sub-component (e.g., "smartschedule", "pin_spacing", "ghostwriter", "csv_import")

3. **issue_signature**: {signature_instructions}

4. **matched_existing**: true if you matched a known theme, false if proposing new

5. **match_reasoning**: Brief explanation of why you chose this theme{new_theme_reasoning}

6. **match_confidence**: How confident are you in this match? (high, medium, low)

7. **user_intent**: What the user was trying to accomplish (in plain English)

8. **symptoms**: List of observable symptoms the user described (2-4 items)

9. **affected_flow**: The user journey or flow that's broken (e.g., "Pin Scheduler → Pinterest API")

10. **root_cause_hypothesis**: Your best guess at the technical root cause based on product knowledge

11. **diagnostic_summary**: A 2-4 sentence developer-focused summary capturing:
    - Specific error messages (quote VERBATIM from conversation if present)
    - Pattern: is this intermittent or always happening?
    - What the user already tried (troubleshooting steps taken)
    - Any hints about root cause from the conversation

    Write this for a developer trying to reproduce and diagnose the issue.

12. **key_excerpts**: Array of important quotes from the conversation (include up to 5 most important; more if truly essential):
    ```json
    [
      {{
        "text": "Copy exact text VERBATIM from conversation - no paraphrasing",
        "relevance": "Why this excerpt matters for understanding/reproducing the issue"
      }}
    ]
    ```

    Prioritize excerpts that contain:
    - Error messages or codes
    - Specific reproduction steps
    - Timing/frequency information
    - User environment details (browser, device, account type)

13. **context_used**: List of product documentation sections you referenced when making this extraction (e.g., ["Pinterest Publishing Issues", "SmartSchedule Feature"])

14. **context_gaps**: List of information that would have helped but wasn't available in the product docs (e.g., ["API rate limits for Pinterest", "SmartSchedule algorithm details"])

15. **resolution_action**: What action did support take to resolve this? (pick ONE)
    - escalated_to_engineering: Created ticket, reported to dev team
    - provided_workaround: Gave temporary solution
    - user_education: Explained how to use feature correctly
    - manual_intervention: Support did something user couldn't (cancelled, refunded, etc.)
    - no_resolution: Issue unresolved or conversation ongoing

16. **root_cause**: Your hypothesis for WHY this happened (1 sentence max)
    - Technical: bug, integration failure, API change, performance issue
    - UX: confusing interface, unclear documentation, hidden feature
    - User error: misunderstanding, wrong expectations
    - null if insufficient information

17. **solution_provided**: If resolved, what was the solution? (1-2 sentences max)
    - Include specific steps if a workaround was given
    - null if unresolved or no clear solution

18. **resolution_category**: Category for analytics (pick ONE)
    - escalation: Required engineering involvement
    - workaround: Temporary fix provided
    - education: User needed guidance
    - self_service_gap: Manual support for something that could be automated
    - unresolved: No resolution achieved

## Example Outputs for New Fields

**Good diagnostic_summary:**
"User reports 'Error 403: Board access denied' when attempting to schedule pins to group board 'Recipe Ideas'. Issue is consistent (happens every time, not intermittent). User verified they are still a collaborator on the board via Pinterest.com. Suggests possible OAuth token scope issue or board permission change not synced to Tailwind."

**Good key_excerpts:**
```json
[
  {{
    "text": "Error 403: Board access denied",
    "relevance": "Exact error code - indicates Pinterest API permission rejection"
  }},
  {{
    "text": "I checked Pinterest and I'm still listed as a collaborator",
    "relevance": "User verified board access externally - suggests Tailwind-side sync issue"
  }},
  {{
    "text": "This started happening after I changed my Pinterest password last week",
    "relevance": "Temporal correlation with password change suggests OAuth token invalidation"
  }}
]
```

**Good resolution fields:**
- **resolution_action**: "provided_workaround"
- **root_cause**: "OAuth token invalidated after Pinterest password change, causing board permission sync failure."
- **solution_provided**: "User reconnected their Pinterest account via Settings > Connections, which refreshed the OAuth token and restored board access."
- **resolution_category**: "workaround"

## Conversation

Issue Type: {issue_type}
Sentiment: {sentiment}
Priority: {priority}
Churn Risk: {churn_risk}

Message:
{source_body}

## Instructions

1. {match_instruction}
2. Use your product knowledge to map user language to actual features
3. Be specific in symptoms - these help engineers reproduce
4. If unsure about a field, make your best inference

Respond with valid JSON only:
"""

# Prompt variations for strict vs flexible mode
STRICT_MODE_INSTRUCTIONS = """## STRICT MODE: You MUST select from the known themes above.

If the conversation doesn't fit any theme well, use `unclassified_needs_review`.
Do NOT create new theme signatures. Pick the closest match or unclassified."""

FLEXIBLE_MODE_INSTRUCTIONS = """## Match First!

Try to match to one of these existing themes before proposing a new one.
Only create a new theme if the issue is genuinely different from all known themes."""

STRICT_SIGNATURE_INSTRUCTIONS = """You MUST use one of the known theme signatures above. Pick the closest match. If nothing fits, use `unclassified_needs_review`."""

FLEXIBLE_SIGNATURE_INSTRUCTIONS = """IMPORTANT - Create SPECIFIC, ACTIONABLE signatures:

**Decision Process**:
   a) First, check if this matches any KNOWN THEME above (same root issue, even if worded differently)
   b) If yes, use that exact signature
   c) If no match, create a new canonical signature following these rules:

## CRITICAL: The SAME_FIX Test

**Before assigning ANY signature, ask yourself: "Would ONE implementation fix ALL conversations with this signature?"**

Two conversations should ONLY share a signature if:
1. **One code change** would fix BOTH issues
2. **One developer** could own the fix
3. **One acceptance test** verifies both are fixed

**Signature Granularity**:
- Level 1 (TOO BROAD): `[platform]_[failure_category]`
  - Example: `pinterest_publishing_failure` ← WRONG
  - Problem: Groups duplicate pins, missing pins, and upload failures together

- Level 2 (CORRECT): `[platform]_[specific_symptom]`
  - Example: `pinterest_duplicate_pins` ← CORRECT
  - Example: `pinterest_missing_pins` ← CORRECT
  - Example: `pinterest_video_upload_failure` ← CORRECT

**Disambiguation Questions**:
Before assigning a signature, ask yourself:
1. "If two users report this, would the SAME code change fix both?"
2. "Would I need to look at DIFFERENT code paths to fix different reports?"

If answer to #2 is YES → Create more specific signature

**Signature Quality Rules**:
   ✅ DO: Be specific about the SYMPTOM
      - "csv_import_encoding_error" (specific error type)
      - "ghostwriter_timeout_error" (specific failure mode)
      - "pinterest_board_permission_denied" (specific error and action)
      - "pinterest_duplicate_pins" (specific symptom)
      - "pinterest_missing_pins" (specific symptom)

   ❌ DON'T: Use broad failure categories
      - NOT "pinterest_publishing_failure" → use specific symptom like "pinterest_duplicate_pins"
      - NOT "scheduling_issue" → use "scheduling_timezone_mismatch" or "scheduling_ui_drag_drop_failure"
      - NOT "account_settings_guidance" → "account_email_change_failure"
      - NOT "general_product_question" → identify specific product first

   **Format**: [feature]_[specific_symptom] (lowercase, underscores)
   **Avoid**: Generic suffixes like "_failure", "_issue", "_problem", "_error" without specific symptom
   **Include**: Actual symptom, specific error type, or observable behavior

## BANNED SIGNATURE PATTERNS (Never create these):
   ❌ `*_question` - e.g., "feature_question", "analytics_question" → TOO BROAD
   ❌ `*_guidance` - e.g., "settings_guidance", "usage_guidance" → TOO BROAD
   ❌ `*_interpretation_*` - e.g., "analytics_interpretation_question" → TOO BROAD
   ❌ `general_*` or `*_general` - e.g., "general_product_question" → TOO BROAD

   These patterns group unrelated issues. Instead, identify the SPECIFIC action or symptom:
   - NOT "analytics_question" → "pin_history_date_lookup" or "ui_color_legend_unclear"
   - NOT "settings_guidance" → "credit_card_update_flow" or "invoice_download_location"
   - NOT "feature_question" → "[feature]_[specific_aspect]_unclear" or "[feature]_[specific_action]_how_to"

   When in doubt, prefer `unclassified_needs_review` over a broad catch-all."""


SIGNATURE_CANONICALIZATION_PROMPT = """You are normalizing issue signatures for a support ticket system.

Given a NEW issue and a list of EXISTING signatures, decide:
1. If the new issue matches an existing signature, return that signature
2. If it's truly new, create a canonical signature

## Rules for Signatures
- Use lowercase with underscores: "csv_field_mapping_error"
- Focus on the WHAT not the HOW: "pins_not_publishing" not "pinterest_api_timeout"
- Be specific enough to group similar issues, general enough to not over-fragment
- Structure: [feature]_[problem] e.g., "csv_import_field_mapping_error", "smartschedule_wrong_times"

## Existing Signatures
{existing_signatures}

## New Issue
Product Area: {product_area}
Component: {component}
Proposed Signature: {proposed_signature}
User Intent: {user_intent}
Symptoms: {symptoms}

## Decision
If this matches an existing signature conceptually (same root issue even if worded differently), return that signature.
If it's genuinely new, return a well-formed canonical signature.

Return JSON with:
- "signature": the final canonical signature to use
- "matched_existing": true if matched an existing signature, false if new
- "reasoning": brief explanation of your decision

JSON only:
"""


@dataclass
class Theme:
    """Extracted theme from a conversation."""

    conversation_id: str
    product_area: str
    component: str
    issue_signature: str
    user_intent: str
    symptoms: list[str]
    affected_flow: str
    root_cause_hypothesis: str
    # LLM decision observability
    matched_existing: bool = False  # Did LLM match to vocabulary theme?
    match_reasoning: str = ""       # Why LLM chose this signature
    match_confidence: str = ""      # high/medium/low confidence in match
    extracted_at: datetime = None

    # Smart Digest fields (Issue #144)
    # 2-4 sentence summary optimized for developers debugging issues
    diagnostic_summary: str = ""
    # Key excerpts from conversation with relevance explanations
    # Format: [{"text": "...", "relevance": "Why this excerpt matters"}, ...]
    key_excerpts: list[dict[str, str]] = field(default_factory=list)
    # Product context sections that were used in analysis
    # Format: ["section_name", ...] - tracks which docs were relevant
    context_used: list[str] = field(default_factory=list)
    # Hints about missing context that would improve analysis
    # Format: ["missing context description", ...]
    context_gaps: list[str] = field(default_factory=list)

    # Issue #146: LLM-powered resolution extraction
    # What action did support take to resolve this?
    # Values: escalated_to_engineering | provided_workaround | user_education | manual_intervention | no_resolution
    resolution_action: str = ""
    # 1-sentence LLM hypothesis for WHY this happened
    root_cause: str = ""
    # 1-2 sentence solution description (if resolved)
    solution_provided: str = ""
    # Category for analytics
    # Values: escalation | workaround | education | self_service_gap | unresolved
    resolution_category: str = ""

    def __post_init__(self):
        if self.extracted_at is None:
            self.extracted_at = datetime.utcnow()

    def to_dict(self) -> dict:
        d = asdict(self)
        d['extracted_at'] = self.extracted_at.isoformat()
        return d


class ThemeExtractor:
    """Extracts themes from classified conversations with signature canonicalization."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        use_vocabulary: bool = True,
        search_service: Optional["UnifiedSearchService"] = None,
    ):
        """
        Initialize the theme extractor.

        Args:
            model: OpenAI model to use for extraction
            use_vocabulary: Whether to use the theme vocabulary for matching
            search_service: Optional UnifiedSearchService for context augmentation.
                           If provided, extracts research context to enrich prompts.
        """
        self.client = OpenAI()
        self.model = model
        self._product_context = None
        self._existing_signatures = None
        self._vocabulary = None
        self.use_vocabulary = use_vocabulary
        self._search_service = search_service
        # Session-scoped signature cache for batch canonicalization
        # Tracks signatures created during this extraction session so new
        # signatures can be canonicalized against both DB and current batch
        self._session_signatures: dict[str, dict] = {}
        # Lock for thread-safe access to _session_signatures (Issue #148)
        # Issue #152: Changed to RLock (reentrant) so the same thread can acquire
        # the lock multiple times (outer canonicalization scope + inner add_session_signature)
        self._session_lock = threading.RLock()

    @property
    def vocabulary(self):
        """Lazy-load the theme vocabulary."""
        if self._vocabulary is None and self.use_vocabulary:
            try:
                from .vocabulary import ThemeVocabulary
            except ImportError:
                from vocabulary import ThemeVocabulary
            self._vocabulary = ThemeVocabulary()
        return self._vocabulary

    @property
    def product_context(self) -> str:
        if self._product_context is None:
            self._product_context = load_product_context()
            logger.info(f"Loaded {len(self._product_context)} chars of product context")
        return self._product_context

    def get_research_context(self, conversation_text: str, max_results: int = 3) -> str:
        """
        Get research context from semantic search to augment theme extraction.

        Args:
            conversation_text: Customer message text to use as search query
            max_results: Maximum research items to include

        Returns:
            Formatted research context string, or empty string if unavailable
        """
        if not self._search_service:
            return ""

        try:
            # Search for relevant research (Coda only, not Intercom)
            results = self._search_service.search_for_context(
                query=conversation_text[:500],  # Limit query length
                max_results=max_results,
            )

            if not results:
                return ""

            # Format as context for the prompt
            context_parts = ["## Related Research Insights\n"]
            for i, result in enumerate(results, 1):
                context_parts.append(
                    f"{i}. **{result.title}** ({result.source_type})\n"
                    f"   {result.snippet}\n"
                )

            logger.info(f"Added {len(results)} research context items to theme extraction")
            return "\n".join(context_parts)

        except Exception as e:
            # Graceful degradation - extraction continues without context
            logger.warning(f"Research context unavailable: {e}")
            return ""

    def get_existing_signatures(self, product_area: str = None, include_session: bool = True) -> list[dict]:
        """
        Fetch existing signatures from database + current session for canonicalization.

        Args:
            product_area: If provided, only fetch signatures from this area.
                         Falls back to all signatures for better matching.
            include_session: If True, include signatures from current extraction session.
                            This ensures new signatures can canonicalize against each other.
        """
        try:
            from .db.connection import get_connection
        except ImportError:
            from db.connection import get_connection

        signatures = []

        # Thread-safe: copy session signatures under lock (Issue #148)
        with self._session_lock:
            session_sigs_snapshot = dict(self._session_signatures)

        # Include session signatures first (higher priority for current batch)
        if include_session and session_sigs_snapshot:
            for sig, info in session_sigs_snapshot.items():
                if product_area is None or info.get("product_area") == product_area:
                    signatures.append({
                        "signature": sig,
                        "product_area": info.get("product_area", "other"),
                        "component": info.get("component", "unknown"),
                        "count": info.get("count", 1),  # Session signatures start at 1
                    })

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Fetch all signatures - no limit to avoid fragmentation
                    # Bug fix: LIMIT 50 caused 83% singleton rate by excluding
                    # most signatures from canonicalization candidates
                    if product_area:
                        # Prioritize same product area, but include all for fallback
                        cur.execute("""
                            SELECT issue_signature, product_area, component, occurrence_count
                            FROM theme_aggregates
                            ORDER BY
                                CASE WHEN product_area = %s THEN 0 ELSE 1 END,
                                occurrence_count DESC
                        """, (product_area,))
                    else:
                        cur.execute("""
                            SELECT issue_signature, product_area, component, occurrence_count
                            FROM theme_aggregates
                            ORDER BY occurrence_count DESC
                        """)

                    # Add DB signatures, avoiding duplicates with session
                    session_sig_keys = set(session_sigs_snapshot.keys())
                    for row in cur.fetchall():
                        if row[0] not in session_sig_keys:
                            signatures.append({
                                "signature": row[0],
                                "product_area": row[1],
                                "component": row[2],
                                "count": row[3]
                            })
        except Exception as e:
            logger.warning(f"Could not fetch existing signatures: {e}")

        return signatures

    def add_session_signature(self, signature: str, product_area: str, component: str) -> None:
        """
        Add a signature to the current session cache.

        Called after extracting a theme to track signatures for batch canonicalization.
        Thread-safe: uses lock for concurrent access (Issue #148).
        """
        with self._session_lock:
            if signature in self._session_signatures:
                self._session_signatures[signature]["count"] += 1
            else:
                self._session_signatures[signature] = {
                    "product_area": product_area,
                    "component": component,
                    "count": 1,
                }

    def clear_session_signatures(self) -> None:
        """Clear the session signature cache. Call at start of new extraction batch."""
        with self._session_lock:
            self._session_signatures.clear()

    def get_embedding(self, text: str) -> list[float]:
        """Get embedding for a text string."""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding

    def canonicalize_via_embedding(
        self,
        proposed_signature: str,
        user_intent: str,
        symptoms: list[str],
        product_area: str = None,
        threshold: float = 0.85,
    ) -> str:
        """
        Canonicalize signature using embedding similarity (cheaper than LLM).

        Compares the semantic meaning of the new issue against existing signatures.
        If similarity > threshold, reuses existing signature.
        """
        existing = self.get_existing_signatures(product_area=product_area)

        # If no existing signatures, return normalized proposed
        if not existing:
            return proposed_signature.lower().replace(" ", "_").replace("-", "_")

        # Create a description of the new issue for embedding
        new_description = f"{proposed_signature.replace('_', ' ')}: {user_intent}. Symptoms: {', '.join(symptoms)}"
        new_embedding = self.get_embedding(new_description)

        best_match = None
        best_similarity = 0.0

        for sig_info in existing:
            # Create description for existing signature
            existing_desc = f"{sig_info['signature'].replace('_', ' ')}: {sig_info['product_area']} {sig_info['component']}"
            existing_embedding = self.get_embedding(existing_desc)

            similarity = cosine_similarity(new_embedding, existing_embedding)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = sig_info['signature']

        if best_similarity >= threshold:
            logger.info(f"Embedding match: {best_match} (similarity={best_similarity:.3f}, was: {proposed_signature})")
            return best_match
        else:
            logger.info(f"New signature: {proposed_signature} (best match: {best_match} at {best_similarity:.3f})")
            return proposed_signature.lower().replace(" ", "_").replace("-", "_")

    def canonicalize_signature(
        self,
        proposed_signature: str,
        product_area: str,
        component: str,
        user_intent: str,
        symptoms: list[str],
        use_llm: bool = True,
    ) -> str:
        """
        Canonicalize a proposed signature against existing signatures.

        Args:
            use_llm: If True, use LLM for canonicalization (more accurate, slower).
                     If False, use embedding similarity (faster, cheaper).
        """
        existing = self.get_existing_signatures(product_area=product_area)

        # If no existing signatures, just return the proposed one (normalized)
        if not existing:
            return proposed_signature.lower().replace(" ", "_").replace("-", "_")

        # Use embedding-based approach if requested
        if not use_llm:
            return self.canonicalize_via_embedding(
                proposed_signature, user_intent, symptoms, product_area=product_area
            )

        # LLM-based canonicalization (original approach)
        sig_list = "\n".join(
            f"- {s['signature']} ({s['product_area']}/{s['component']})"
            for s in existing
        )

        prompt = SIGNATURE_CANONICALIZATION_PROMPT.format(
            existing_signatures=sig_list if sig_list else "(none yet)",
            product_area=product_area,
            component=component,
            proposed_signature=proposed_signature,
            user_intent=user_intent,
            symptoms=", ".join(symptoms) if symptoms else "none specified",
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You normalize issue signatures. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,  # Low temperature for consistency
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        final_sig = result.get("signature", proposed_signature)
        matched = result.get("matched_existing", False)
        reasoning = result.get("reasoning", "")

        if matched:
            logger.info(f"Matched existing signature: {final_sig} (was: {proposed_signature})")
        else:
            logger.info(f"New signature: {final_sig} - {reasoning}")

        return final_sig

    def extract(
        self,
        conv: Conversation,
        canonicalize: bool = True,
        use_embedding: bool = False,
        auto_add_to_vocabulary: bool = False,
        strict_mode: bool = False,
        customer_digest: Optional[str] = None,
        full_conversation: Optional[str] = None,
        use_full_conversation: bool = True,
    ) -> Theme:
        """
        Extract theme from a single conversation.

        Args:
            conv: The conversation to extract from
            canonicalize: If True and NOT using vocabulary, run signature through
                         canonicalization. Ignored when vocabulary is active since
                         vocabulary provides match-first extraction.
            use_embedding: If True, use embedding similarity instead of LLM.
                          WARNING: Experimental - testing showed lower accuracy than LLM.
            auto_add_to_vocabulary: If True, automatically add new themes to vocabulary.
            strict_mode: If True, force LLM to pick from existing vocabulary only.
                        Use this for backfill to prevent theme fragmentation.
            customer_digest: Optional digest with first + most specific customer message (Issue #139).
                           When provided and use_full_conversation=False, used instead of
                           conv.source_body for better context.
            full_conversation: Optional full conversation text including all customer and
                              support messages (Issue #144 - Smart Digest).
                              When provided and use_full_conversation=True, used for
                              richer theme extraction with diagnostic_summary and key_excerpts.
            use_full_conversation: If True (default), prefer full_conversation when available.
                                  If False, fall back to customer_digest or source_body.
                                  Set to False for backward compatibility or cost savings.
        """
        # Check for URL context to boost product area matching
        url_matched_product_area = None
        url_context_hint = ""
        if self.use_vocabulary and self.vocabulary and hasattr(conv, 'source_url'):
            url_matched_product_area = self.vocabulary.match_url_to_product_area(conv.source_url)
            if url_matched_product_area:
                url_context_hint = f"""
## URL Context

The user was on a page related to **{url_matched_product_area}** when they started this conversation.
**IMPORTANT**: Strongly prefer themes from the {url_matched_product_area} product area when matching.
"""

        # Get known themes from vocabulary (if enabled)
        known_themes = ""
        signature_quality_examples = ""
        if self.use_vocabulary and self.vocabulary:
            # If we have URL context, prioritize themes from that product area
            if url_matched_product_area:
                known_themes = self.vocabulary.format_for_prompt(
                    product_area=url_matched_product_area,
                    max_themes=50
                )
            else:
                known_themes = self.vocabulary.format_for_prompt(max_themes=50)

            # Include signature quality examples
            signature_quality_examples = self.vocabulary.format_signature_examples()

        # Select prompt variations based on strict mode
        if strict_mode:
            strict_mode_instructions = STRICT_MODE_INSTRUCTIONS
            signature_instructions = STRICT_SIGNATURE_INSTRUCTIONS
            match_instruction = "**STRICT MODE**: You MUST pick from the known themes. No new signatures allowed."
            new_theme_reasoning = ""
        else:
            strict_mode_instructions = FLEXIBLE_MODE_INSTRUCTIONS
            signature_instructions = FLEXIBLE_SIGNATURE_INSTRUCTIONS
            match_instruction = "**Match first**: Strongly prefer matching to known themes. Only create new if truly different."
            new_theme_reasoning = ". If proposing new, explain why none of the known themes fit"

        # Determine source text for extraction (Issue #144 - Smart Digest)
        # Priority order when use_full_conversation=True:
        #   1. full_conversation (all messages, richest context)
        #   2. customer_digest (first + most specific, good fallback)
        #   3. source_body (first message only, minimal context)
        # When use_full_conversation=False, skip full_conversation
        source_text = ""
        using_full_conversation = False

        if use_full_conversation and full_conversation and len(full_conversation.strip()) > 10:
            # Apply smart truncation for edge cases exceeding token limits
            source_text = prepare_conversation_for_extraction(full_conversation.strip())
            using_full_conversation = True
            logger.debug(f"Conv {conv.id}: Using full conversation ({len(source_text)} chars)")
        elif customer_digest and len(customer_digest.strip()) > 10:
            # Issue #139: Fall back to customer digest
            source_text = customer_digest.strip()
            logger.debug(f"Conv {conv.id}: Using customer_digest ({len(source_text)} chars)")
        else:
            # Minimal fallback: first message only
            source_text = conv.source_body or ""
            if customer_digest is not None or full_conversation is not None:
                logger.debug(f"Conv {conv.id}: Falling back to source_body")

        # Get research context for enrichment (if search service available)
        research_context = self.get_research_context(source_text)

        # Phase 1: Extract theme details (with vocabulary-aware prompt)
        prompt = THEME_EXTRACTION_PROMPT.format(
            product_context=self.product_context[:30000],  # Increased from 10K to 30K (Issue #144)
            url_context_hint=url_context_hint,
            research_context=research_context,
            known_themes=known_themes or "(No known themes yet - create new signatures as needed)",
            signature_quality_examples=signature_quality_examples,
            strict_mode_instructions=strict_mode_instructions,
            signature_instructions=signature_instructions,
            match_instruction=match_instruction,
            new_theme_reasoning=new_theme_reasoning,
            issue_type=conv.issue_type,
            sentiment=conv.sentiment,
            priority=conv.priority,
            churn_risk=conv.churn_risk,
            source_body=source_text,
        )

        # Token usage guard (R2): Estimate tokens and warn/truncate if needed
        # gpt-4o-mini has 128K context window; leave headroom for response
        MAX_PROMPT_CHARS = 400_000  # ~100K tokens at 4 chars/token
        if len(prompt) > MAX_PROMPT_CHARS:
            logger.warning(
                f"Prompt exceeds {MAX_PROMPT_CHARS} chars ({len(prompt)} chars), truncating source_text"
            )
            # Recalculate with truncated source_text
            # Estimate non-source overhead and leave room for it
            overhead = len(prompt) - len(source_text)
            max_source_chars = MAX_PROMPT_CHARS - overhead - 1000  # 1K buffer
            if max_source_chars > 0:
                source_text = source_text[:max_source_chars]
                prompt = THEME_EXTRACTION_PROMPT.format(
                    product_context=self.product_context[:30000],
                    url_context_hint=url_context_hint,
                    research_context=research_context,
                    known_themes=known_themes or "(No known themes yet - create new signatures as needed)",
                    signature_quality_examples=signature_quality_examples,
                    strict_mode_instructions=strict_mode_instructions,
                    signature_instructions=signature_instructions,
                    match_instruction=match_instruction,
                    new_theme_reasoning=new_theme_reasoning,
                    issue_type=conv.issue_type,
                    sentiment=conv.sentiment,
                    priority=conv.priority,
                    churn_risk=conv.churn_risk,
                    source_body=source_text,
                )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a product analyst. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        proposed_signature = result.get("issue_signature", "unknown_issue")
        product_area = result.get("product_area", "other")
        component = result.get("component", "unknown")
        user_intent = result.get("user_intent", "")
        symptoms = result.get("symptoms", [])
        matched_existing = result.get("matched_existing", False)
        match_reasoning = result.get("match_reasoning", "")

        # Get match confidence
        match_confidence = result.get("match_confidence", "")

        # OBSERVABILITY: Log LLM decision trail prominently
        logger.info(
            f"🔍 THEME EXTRACTION DECISION:\n"
            f"   Conversation: {conv.id[:20]}...\n"
            f"   User message: {source_text[:100]}...\n"
            f"   → Signature: {proposed_signature}\n"
            f"   → Matched existing: {matched_existing}\n"
            f"   → Confidence: {match_confidence}\n"
            f"   → Reasoning: {match_reasoning}"
        )

        # Log vocabulary match status and lookup vocabulary metadata
        if self.use_vocabulary:
            if matched_existing:
                # When matched, use vocabulary product_area and component instead of LLM response
                vocab_theme = self.vocabulary._themes.get(proposed_signature)
                if vocab_theme:
                    product_area = vocab_theme.product_area
                    component = vocab_theme.component
                    logger.info(f"   → Using vocab metadata: {product_area}/{component}")
            else:
                logger.info(f"   → NEW THEME (not in vocabulary)")

                # Optionally add new themes to vocabulary
                if auto_add_to_vocabulary and self.vocabulary:
                    self.vocabulary.add(
                        issue_signature=proposed_signature,
                        product_area=product_area,
                        component=component,
                        description=user_intent[:200] if user_intent else f"{product_area}/{component} issue",
                        keywords=[s.lower() for s in symptoms[:3]] if symptoms else [],
                        example_intents=[user_intent] if user_intent else [],
                    )
                    logger.info(f"Auto-added to vocabulary: {proposed_signature}")

        # Phase 2: Canonicalize signature
        # - If vocabulary matched an existing theme, use as-is (already canonical)
        # - If LLM created a new signature, canonicalize against existing signatures
        #   to prevent duplicates like analytics_stats_accuracy vs analytics_performance_accuracy
        #
        # Issue #152: Serialize canonicalization to prevent race condition where
        # concurrent extractions create near-duplicate signatures. The lock ensures
        # thread B sees thread A's signature before deciding to create a new one.
        with self._session_lock:
            if self.use_vocabulary and matched_existing:
                # Vocabulary already handled matching - use as-is
                final_signature = proposed_signature
            elif canonicalize:
                # Canonicalize new signatures against existing ones in theme_aggregates
                # This runs for both vocabulary mode (new signatures) and non-vocabulary mode
                final_signature = self.canonicalize_signature(
                    proposed_signature=proposed_signature,
                    product_area=product_area,
                    component=component,
                    user_intent=user_intent,
                    symptoms=symptoms,
                    use_llm=not use_embedding,
                )
            else:
                final_signature = proposed_signature

            # Add to session cache for batch canonicalization
            # This allows subsequent extractions to canonicalize against this signature
            self.add_session_signature(final_signature, product_area, component)

        # Extract Smart Digest fields (Issue #144)
        # These are populated when full_conversation is used and LLM returns them
        diagnostic_summary = result.get("diagnostic_summary", "")
        key_excerpts = result.get("key_excerpts", [])
        context_used = result.get("context_used", [])
        context_gaps = result.get("context_gaps", [])

        # Extract resolution fields (Issue #146)
        # These capture how support resolved the issue and why it happened
        resolution_action = result.get("resolution_action", "") or ""
        root_cause = result.get("root_cause", "") or ""
        solution_provided = result.get("solution_provided", "") or ""
        resolution_category = result.get("resolution_category", "") or ""

        # Validate resolution_action enum values
        valid_resolution_actions = {
            "escalated_to_engineering",
            "provided_workaround",
            "user_education",
            "manual_intervention",
            "no_resolution",
        }
        if resolution_action and resolution_action not in valid_resolution_actions:
            logger.warning(
                f"Invalid resolution_action '{resolution_action}', defaulting to empty string"
            )
            resolution_action = ""

        # Validate resolution_category enum values
        valid_resolution_categories = {
            "escalation",
            "workaround",
            "education",
            "self_service_gap",
            "unresolved",
        }
        if resolution_category and resolution_category not in valid_resolution_categories:
            logger.warning(
                f"Invalid resolution_category '{resolution_category}', defaulting to empty string"
            )
            resolution_category = ""

        # Validate key_excerpts structure
        if key_excerpts and isinstance(key_excerpts, list):
            # Ensure each excerpt has required fields
            validated_excerpts = []
            for excerpt in key_excerpts[:5]:  # Limit to 5 excerpts
                if isinstance(excerpt, dict) and "text" in excerpt:
                    # relevance should be a descriptive string explaining why this excerpt matters
                    # Fallback to "Relevant excerpt" if LLM didn't provide explanation
                    relevance = excerpt.get("relevance", "")
                    if not relevance or relevance in ("high", "medium", "low"):
                        # Convert enum-style values to descriptive fallback
                        relevance = "Relevant excerpt from conversation"
                    validated_excerpts.append({
                        "text": str(excerpt.get("text", ""))[:500],  # Limit text length
                        "relevance": str(relevance)[:200],  # Limit relevance explanation length
                    })
            key_excerpts = validated_excerpts
        else:
            key_excerpts = []

        return Theme(
            conversation_id=conv.id,
            product_area=product_area,
            component=component,
            issue_signature=final_signature,
            user_intent=user_intent,
            symptoms=symptoms,
            affected_flow=result.get("affected_flow", ""),
            root_cause_hypothesis=result.get("root_cause_hypothesis", ""),
            # LLM decision observability
            matched_existing=matched_existing,
            match_reasoning=match_reasoning,
            match_confidence=result.get("match_confidence", ""),
            # Smart Digest fields (Issue #144)
            diagnostic_summary=diagnostic_summary,
            key_excerpts=key_excerpts,
            context_used=context_used if isinstance(context_used, list) else [],
            context_gaps=context_gaps if isinstance(context_gaps, list) else [],
            # Resolution fields (Issue #146)
            resolution_action=resolution_action,
            root_cause=root_cause,
            solution_provided=solution_provided,
            resolution_category=resolution_category,
        )

    async def extract_async(
        self,
        conv: Conversation,
        canonicalize: bool = True,
        use_embedding: bool = False,
        auto_add_to_vocabulary: bool = False,
        strict_mode: bool = False,
        customer_digest: Optional[str] = None,
        full_conversation: Optional[str] = None,
        use_full_conversation: bool = True,
    ) -> Theme:
        """
        Async version of extract() for parallel processing (Issue #148).

        Runs the sync extract() method in a thread pool to enable concurrent
        theme extraction without blocking the event loop.

        Same parameters and behavior as extract().

        Note: This uses asyncio.to_thread rather than native async OpenAI calls
        to minimize code duplication and risk. The sync extract() method is
        well-tested; wrapping it preserves that reliability while enabling
        parallelism through semaphore-controlled concurrency.
        """
        import asyncio

        # Run sync extract in thread pool
        return await asyncio.to_thread(
            self.extract,
            conv,
            canonicalize=canonicalize,
            use_embedding=use_embedding,
            auto_add_to_vocabulary=auto_add_to_vocabulary,
            strict_mode=strict_mode,
            customer_digest=customer_digest,
            full_conversation=full_conversation,
            use_full_conversation=use_full_conversation,
        )

    def extract_batch(
        self,
        conversations: list[Conversation],
        canonicalize: bool = True,
        strict_mode: bool = False,
    ) -> list[Theme]:
        """
        Extract themes from multiple conversations.

        Args:
            conversations: List of conversations to process
            canonicalize: If True, run through canonicalization (non-vocabulary mode)
            strict_mode: If True, force vocabulary-only matching (for backfill)
        """
        # Clear session signatures at start of batch for clean canonicalization
        self.clear_session_signatures()

        themes = []
        for conv in conversations:
            try:
                theme = self.extract(conv, canonicalize=canonicalize, strict_mode=strict_mode)
                themes.append(theme)
                logger.info(f"Extracted theme: {theme.issue_signature}")
            except Exception as e:
                logger.error(f"Failed to extract theme for {conv.id}: {e}")
        return themes


def format_theme_for_ticket(theme: Theme, similar_count: int = 1, sample_messages: list[str] = None) -> str:
    """Format a theme as a ticket description for human + agentic consumption."""

    samples = ""
    if sample_messages:
        samples = "\n".join(f'> "{msg[:200]}..."' for msg in sample_messages[:3])

    trend = ""
    if similar_count > 1:
        trend = f" ({similar_count} reports)"

    return f"""## {theme.issue_signature.replace('_', ' ').title()}{trend}

**Product Area:** {theme.product_area} → {theme.component}
**Affected Flow:** {theme.affected_flow}
**User Intent:** {theme.user_intent}

### Symptoms
{chr(10).join(f'- {s}' for s in theme.symptoms)}

### Root Cause Hypothesis
{theme.root_cause_hypothesis}

### Sample Customer Messages
{samples or '_No samples available_'}

### Suggested Investigation
- Review {theme.component} code for issues matching symptoms
- Check logs for errors in {theme.affected_flow} flow
- Verify API responses and error handling
"""


# Quick test
if __name__ == "__main__":
    import sys
    # Add src to path for running as script
    sys.path.insert(0, str(Path(__file__).parent))

    logging.basicConfig(level=logging.INFO)

    # Test with a sample conversation
    test_conv = Conversation(
        id="test_123",
        created_at=datetime.utcnow(),
        source_body="My pins are showing as scheduled but they never actually post to Pinterest. I've been waiting for 3 days and nothing has shown up on my boards. This is really frustrating because I have a product launch coming up.",
        issue_type="bug_report",
        sentiment="frustrated",
        churn_risk=False,
        priority="high",
    )

    extractor = ThemeExtractor()
    theme = extractor.extract(test_conv)

    print("\n" + "="*60)
    print("EXTRACTED THEME:")
    print("="*60)
    print(json.dumps(theme.to_dict(), indent=2))

    print("\n" + "="*60)
    print("FORMATTED TICKET:")
    print("="*60)
    print(format_theme_for_ticket(theme, similar_count=5, sample_messages=[test_conv.source_body]))
