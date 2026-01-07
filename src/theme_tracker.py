"""
Theme tracker for storing, aggregating, and querying themes.

Manages the themes and theme_aggregates tables, tracks trending issues,
and generates tickets when thresholds are met.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Load .env file if present
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Handle both module and script execution
try:
    from .db.connection import get_connection
    from .theme_extractor import Theme, format_theme_for_ticket
    from .shortcut_client import ShortcutClient
except ImportError:
    from db.connection import get_connection
    from theme_extractor import Theme, format_theme_for_ticket
    from shortcut_client import ShortcutClient

logger = logging.getLogger(__name__)


# Patterns that indicate specific/actionable excerpts
SPECIFICITY_PATTERNS = [
    r'\berror\b',           # Error mentions
    r'\b\d{3,}\b',          # Error codes, IDs
    r'https?://',           # URLs
    r'\bfailed\b',          # Failure mentions
    r'\bcrash',             # Crash mentions
    r'\bbug\b',             # Bug mentions
    r'\bversion\b',         # Version mentions
    r'\bchrome\b|\bsafari\b|\bfirefox\b',  # Browser mentions
    r'\bios\b|\bandroid\b|\bmobile\b',     # Platform mentions
    r'\bstep\s*\d',         # Steps to reproduce
    r'"[^"]{5,}"',          # Quoted text (specific values)
    r"'[^']{5,}'",          # Single-quoted text
]

# Patterns that indicate reproduction steps (high value for debugging)
REPRO_STEP_PATTERNS = [
    r'\b\d+\.\s+\w',                    # Numbered list: "1. Click..."
    r'\bfirst\b.*\bthen\b',             # Sequential: "first... then..."
    r'\bafter\s+(i|that|this)\b',       # "after I...", "after that..."
    r'\bwhen\s+i\b',                    # "when I..."
    r'\bif\s+i\b',                      # "if I..."
    r'\b(click|tap|press|select|choose|open|go to|navigate)\b',  # UI actions
    r'\b(enter|type|input|fill|submit)\b',  # Form actions
    r'\b(try|tried|attempt)\b.*\b(to|and)\b',  # "tried to...", "try and..."
    r'\breproduce\b|\brepro\b',         # Explicit repro mention
]

# Non-actionable themes to exclude from ticketing
# These represent normal support volume or unclassified data, not actionable issues
NON_ACTIONABLE_THEMES = {
    'general_product_question',  # Track for product insights, but no auto-tickets
    'unclassified_needs_review',  # Needs manual review, not auto-ticketing
    'misdirected_inquiry',  # Wrong channel, not actionable
    'professional_services_inquiry',  # Sales leads, route to sales not engineering
    'engagement_decline_feedback',  # NPS feedback, route to customer success not engineering
}

# Patterns for media links (screenshots, screen recordings, etc.)
MEDIA_LINK_PATTERNS = [
    (r'https?://(?:www\.)?loom\.com/share/[a-zA-Z0-9]+', 'Loom'),
    (r'https?://(?:www\.)?jam\.dev/c/[a-zA-Z0-9-]+', 'Jam'),
    (r'https?://(?:www\.)?jamdev\.io/[a-zA-Z0-9-]+', 'Jam'),
    (r'https?://(?:www\.)?screencast\.com/[^\s]+', 'Screencast'),
    (r'https?://(?:www\.)?share\.cleanshot\.com/[a-zA-Z0-9]+', 'CleanShot'),
    (r'https?://(?:www\.)?cl\.ly/[a-zA-Z0-9]+', 'CloudApp'),
    (r'https?://(?:www\.)?droplr\.com/[^\s]+', 'Droplr'),
    (r'https?://(?:www\.)?gyazo\.com/[a-zA-Z0-9]+', 'Gyazo'),
    (r'https?://(?:www\.)?snipboard\.io/[a-zA-Z0-9]+', 'Snipboard'),
    (r'https?://(?:i\.)?imgur\.com/[a-zA-Z0-9]+', 'Imgur'),
    (r'https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp|mp4|mov|webm)(?:\?[^\s]*)?', 'Image/Video'),
    (r'https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+', 'YouTube'),
    (r'https?://youtu\.be/[a-zA-Z0-9_-]+', 'YouTube'),
]


def extract_media_links(text: str) -> list[tuple[str, str]]:
    """
    Extract media links (screenshots, Looms, etc.) from text.

    Returns list of (url, type) tuples.
    """
    if not text:
        return []

    links = []
    for pattern, link_type in MEDIA_LINK_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            links.append((match, link_type))

    return links


def score_excerpt_specificity(text: str) -> int:
    """
    Score an excerpt by specificity (higher = more useful for debugging).

    Prefers excerpts with:
    - Error codes/messages
    - URLs
    - Specific feature names
    - Steps to reproduce
    - Platform/browser info

    Over generic complaints.
    """
    if not text:
        return 0

    text_lower = text.lower()
    score = 0

    # Check for specificity patterns
    for pattern in SPECIFICITY_PATTERNS:
        if re.search(pattern, text_lower):
            score += 10

    # Check for reproduction steps (higher value - these are gold for debugging)
    repro_matches = 0
    for pattern in REPRO_STEP_PATTERNS:
        if re.search(pattern, text_lower):
            repro_matches += 1
    if repro_matches > 0:
        # Bonus scales with number of repro indicators (max +50)
        score += min(15 * repro_matches, 50)

    # Check for media links (screenshots, Looms, etc. - very high value)
    media_links = extract_media_links(text)
    if media_links:
        # Big bonus for visual evidence
        score += 30 * len(media_links)

    # Slight bonus for medium length (not too short, not too long)
    length = len(text)
    if 50 <= length <= 500:
        score += 5
    elif 500 < length <= 1000:
        score += 3

    # Penalty for very short or very long
    if length < 30:
        score -= 10
    elif length > 2000:
        score -= 5

    return score


@dataclass
class ThemeAggregate:
    """Aggregated theme data across multiple conversations."""

    issue_signature: str
    product_area: str
    component: str
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    sample_user_intent: str
    sample_symptoms: list[str]
    sample_affected_flow: str
    sample_root_cause_hypothesis: str
    ticket_created: bool = False
    ticket_id: Optional[str] = None
    ticket_excerpts: list[str] = None  # Excerpts already in ticket
    affected_conversations: list[str] = None

    def to_theme(self) -> Theme:
        """Convert aggregate to Theme for formatting."""
        return Theme(
            conversation_id=f"aggregate_{self.issue_signature}",
            product_area=self.product_area,
            component=self.component,
            issue_signature=self.issue_signature,
            user_intent=self.sample_user_intent,
            symptoms=self.sample_symptoms or [],
            affected_flow=self.sample_affected_flow,
            root_cause_hypothesis=self.sample_root_cause_hypothesis,
            extracted_at=self.last_seen_at,
        )


class ThemeTracker:
    """Tracks and aggregates themes from conversations."""

    def __init__(self, ticket_threshold: int = 3):
        """
        Initialize the theme tracker.

        Args:
            ticket_threshold: Number of occurrences before auto-creating a ticket
        """
        self.ticket_threshold = ticket_threshold

    def store_theme(self, theme: Theme) -> bool:
        """
        Store a theme and update aggregates.

        Returns True if this is a new occurrence, False if duplicate.
        Uses the conversation's created_at date for first_seen_at/last_seen_at
        to track actual occurrence times, not processing times.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Get the conversation's actual created_at date
                    cur.execute(
                        "SELECT created_at FROM conversations WHERE id = %s",
                        (theme.conversation_id,)
                    )
                    conv_row = cur.fetchone()
                    conversation_date = conv_row[0] if conv_row else theme.extracted_at

                    # Insert theme (ignore if already exists for this conversation)
                    # Default component to 'unknown' if None (LLM sometimes returns null)
                    component = theme.component or "unknown"
                    product_area = theme.product_area or "other"

                    cur.execute(
                        """
                        INSERT INTO themes (
                            conversation_id, product_area, component, issue_signature,
                            user_intent, symptoms, affected_flow, root_cause_hypothesis,
                            extracted_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (conversation_id) DO NOTHING
                        RETURNING id
                        """,
                        (
                            theme.conversation_id,
                            product_area,
                            component,
                            theme.issue_signature,
                            theme.user_intent,
                            json.dumps(theme.symptoms),
                            theme.affected_flow,
                            theme.root_cause_hypothesis,
                            theme.extracted_at,
                        )
                    )
                    result = cur.fetchone()

                    if result is None:
                        # Already exists
                        return False

                    # Update or insert aggregate
                    # Uses LEAST/GREATEST to track actual first/last conversation dates
                    # Reuse the same component/product_area defaults from above
                    cur.execute(
                        """
                        INSERT INTO theme_aggregates (
                            issue_signature, product_area, component,
                            occurrence_count, first_seen_at, last_seen_at,
                            sample_user_intent, sample_symptoms,
                            sample_affected_flow, sample_root_cause_hypothesis
                        ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (issue_signature) DO UPDATE SET
                            occurrence_count = theme_aggregates.occurrence_count + 1,
                            first_seen_at = LEAST(theme_aggregates.first_seen_at, EXCLUDED.first_seen_at),
                            last_seen_at = GREATEST(theme_aggregates.last_seen_at, EXCLUDED.last_seen_at),
                            sample_user_intent = EXCLUDED.sample_user_intent,
                            sample_symptoms = EXCLUDED.sample_symptoms,
                            sample_affected_flow = EXCLUDED.sample_affected_flow,
                            sample_root_cause_hypothesis = EXCLUDED.sample_root_cause_hypothesis
                        """,
                        (
                            theme.issue_signature,
                            product_area,
                            component,
                            conversation_date,
                            conversation_date,
                            theme.user_intent,
                            json.dumps(theme.symptoms),
                            theme.affected_flow,
                            theme.root_cause_hypothesis,
                        )
                    )

                    logger.info(f"Stored theme: {theme.issue_signature}")
                    return True

        except Exception as e:
            logger.error(f"Failed to store theme: {e}")
            raise

    def store_batch(self, themes: list[Theme]) -> int:
        """Store multiple themes. Returns count of new themes stored."""
        count = 0
        for theme in themes:
            if self.store_theme(theme):
                count += 1
        return count

    def get_aggregate(self, issue_signature: str) -> Optional[ThemeAggregate]:
        """Get aggregate data for a specific issue signature."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            issue_signature, product_area, component,
                            occurrence_count, first_seen_at, last_seen_at,
                            sample_user_intent, sample_symptoms,
                            sample_affected_flow, sample_root_cause_hypothesis,
                            ticket_created, ticket_id, ticket_excerpts
                        FROM theme_aggregates
                        WHERE issue_signature = %s
                        """,
                        (issue_signature,)
                    )
                    row = cur.fetchone()

                    if row is None:
                        return None

                    # Get affected conversation IDs
                    cur.execute(
                        """
                        SELECT conversation_id FROM themes
                        WHERE issue_signature = %s
                        ORDER BY extracted_at DESC
                        """,
                        (issue_signature,)
                    )
                    conv_ids = [r[0] for r in cur.fetchall()]

                    symptoms = row[7]
                    if isinstance(symptoms, str):
                        symptoms = json.loads(symptoms)

                    excerpts = row[12]
                    if isinstance(excerpts, str):
                        excerpts = json.loads(excerpts)

                    return ThemeAggregate(
                        issue_signature=row[0],
                        product_area=row[1],
                        component=row[2],
                        occurrence_count=row[3],
                        first_seen_at=row[4],
                        last_seen_at=row[5],
                        sample_user_intent=row[6],
                        sample_symptoms=symptoms,
                        sample_affected_flow=row[8],
                        sample_root_cause_hypothesis=row[9],
                        ticket_created=row[10],
                        ticket_id=row[11],
                        ticket_excerpts=excerpts,
                        affected_conversations=conv_ids,
                    )

        except Exception as e:
            logger.error(f"Failed to get aggregate: {e}")
            return None

    def get_trending_themes(
        self,
        days: int = 7,
        min_occurrences: int = 2,
        limit: int = 20,
    ) -> list[ThemeAggregate]:
        """Get trending themes (multiple occurrences in time window)."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            ta.issue_signature, ta.product_area, ta.component,
                            ta.occurrence_count, ta.first_seen_at, ta.last_seen_at,
                            ta.sample_user_intent, ta.sample_symptoms,
                            ta.sample_affected_flow, ta.sample_root_cause_hypothesis,
                            ta.ticket_created, ta.ticket_id
                        FROM theme_aggregates ta
                        WHERE ta.last_seen_at > NOW() - INTERVAL '%s days'
                          AND ta.occurrence_count >= %s
                        ORDER BY ta.occurrence_count DESC, ta.last_seen_at DESC
                        LIMIT %s
                        """,
                        (days, min_occurrences, limit)
                    )
                    rows = cur.fetchall()

                    aggregates = []
                    for row in rows:
                        symptoms = row[7]
                        if isinstance(symptoms, str):
                            symptoms = json.loads(symptoms)

                        aggregates.append(ThemeAggregate(
                            issue_signature=row[0],
                            product_area=row[1],
                            component=row[2],
                            occurrence_count=row[3],
                            first_seen_at=row[4],
                            last_seen_at=row[5],
                            sample_user_intent=row[6],
                            sample_symptoms=symptoms,
                            sample_affected_flow=row[8],
                            sample_root_cause_hypothesis=row[9],
                            ticket_created=row[10],
                            ticket_id=row[11],
                        ))

                    return aggregates

        except Exception as e:
            logger.error(f"Failed to get trending themes: {e}")
            return []

    def get_themes_needing_tickets(
        self,
        recency_days: int = 30,
    ) -> list[ThemeAggregate]:
        """
        Get themes that have reached ticket threshold but no ticket created.

        Only returns themes with recent activity (within recency_days) to avoid
        creating tickets for old/resolved issues in historical data.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Convert set to tuple for SQL IN clause
                    excluded = tuple(NON_ACTIONABLE_THEMES)
                    cur.execute(
                        """
                        SELECT
                            issue_signature, product_area, component,
                            occurrence_count, first_seen_at, last_seen_at,
                            sample_user_intent, sample_symptoms,
                            sample_affected_flow, sample_root_cause_hypothesis,
                            ticket_created, ticket_id
                        FROM theme_aggregates
                        WHERE occurrence_count >= %s
                          AND ticket_created = FALSE
                          AND last_seen_at >= NOW() - INTERVAL '%s days'
                          AND issue_signature NOT IN %s
                        ORDER BY occurrence_count DESC
                        """,
                        (self.ticket_threshold, recency_days, excluded)
                    )
                    rows = cur.fetchall()

                    aggregates = []
                    for row in rows:
                        symptoms = row[7]
                        if isinstance(symptoms, str):
                            symptoms = json.loads(symptoms)

                        aggregates.append(ThemeAggregate(
                            issue_signature=row[0],
                            product_area=row[1],
                            component=row[2],
                            occurrence_count=row[3],
                            first_seen_at=row[4],
                            last_seen_at=row[5],
                            sample_user_intent=row[6],
                            sample_symptoms=symptoms,
                            sample_affected_flow=row[8],
                            sample_root_cause_hypothesis=row[9],
                            ticket_created=row[10],
                            ticket_id=row[11],
                        ))

                    return aggregates

        except Exception as e:
            logger.error(f"Failed to get themes needing tickets: {e}")
            return []

    def mark_ticket_created(
        self,
        issue_signature: str,
        ticket_id: str,
        initial_excerpts: Optional[list[str]] = None,
    ) -> None:
        """Mark that a ticket was created for this theme."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE theme_aggregates
                        SET ticket_created = TRUE,
                            ticket_id = %s,
                            ticket_excerpts = %s
                        WHERE issue_signature = %s
                        """,
                        (ticket_id, json.dumps(initial_excerpts or []), issue_signature)
                    )
                    logger.info(f"Marked ticket created for {issue_signature}: {ticket_id}")

        except Exception as e:
            logger.error(f"Failed to mark ticket created: {e}")

    @staticmethod
    def get_theme_type(issue_signature: str) -> str:
        """
        Categorize theme as 'bug' (technical) or 'trend' (support/ops pattern).

        Used to select the appropriate ticket template.
        """
        sig_lower = issue_signature.lower()

        # Patterns that indicate technical/engineering issues
        bug_patterns = [
            '_error',
            '_failure',
            '_bug',
            '_broken',
            '_not_working',
            '_crash',
            '_timeout',
            '_slow',
            '_missing',
            '_stuck',
            '_drop',
            '_issue',
            'not_publishing',
            'not_loading',
            'not_showing',
        ]

        for pattern in bug_patterns:
            if pattern in sig_lower:
                return 'bug'

        # Default to trend (support/ops pattern)
        return 'trend'

    @staticmethod
    def _format_title(issue_signature: str) -> str:
        """Convert issue_signature to human-readable title."""
        # billing_cancellation_request -> Billing Cancellation Request
        return issue_signature.replace('_', ' ').title()

    def _format_excerpts(self, issue_signature: str, max_excerpts: int = 5) -> str:
        """
        Get and format customer excerpts for ticket description.

        Selects the most specific/useful excerpts based on scoring,
        and includes Intercom conversation links, Jarvis links, and media links.
        """
        messages_with_metadata = self._get_sample_messages_with_metadata(issue_signature, limit=20)
        if not messages_with_metadata:
            return ""

        # Score and sort by specificity
        scored = [
            (msg, conv_id, email, user_id, org_id, score_excerpt_specificity(msg))
            for msg, conv_id, email, user_id, org_id in messages_with_metadata
        ]
        scored.sort(key=lambda x: x[5], reverse=True)

        # Take top excerpts
        best = scored[:max_excerpts]

        intercom_app_id = os.getenv("INTERCOM_APP_ID", "2t3d8az2")
        lines = ["## Customer Reports\n"]

        for i, (msg, conv_id, email, user_id, org_id, score) in enumerate(best, 1):
            # Truncate long messages
            excerpt = msg[:500] + "..." if len(msg) > 500 else msg

            # Build user info line with links (same format as update_ticket_for_theme)
            user_info_parts = []

            # Intercom conversation link with email as label
            convo_url = f"https://app.intercom.com/a/apps/{intercom_app_id}/inbox/inbox/conversation/{conv_id}"
            label = email if email else f"Conversation {conv_id}"
            user_info_parts.append(f"[{label}]({convo_url})")

            # Jarvis org link
            if org_id:
                org_url = f"https://jarvis.tailwind.ai/organizations/{org_id}"
                user_info_parts.append(f"[Org]({org_url})")

            # Jarvis user link (requires org_id)
            if user_id and org_id:
                user_url = f"https://jarvis.tailwind.ai/organizations/{org_id}/users/{user_id}"
                user_info_parts.append(f"[User]({user_url})")

            user_info = " | ".join(user_info_parts)

            # Extract media links (Loom, Jam, screenshots, etc.)
            media_links = extract_media_links(msg)
            media_section = ""
            if media_links:
                media_items = [f"[{link_type}]({url})" for url, link_type in media_links]
                media_section = f"\n📎 {', '.join(media_items)}"

            lines.append(f"**Report {i}:** {user_info}{media_section}\n> {excerpt}\n")

        return "\n".join(lines)

    def _get_sample_messages_with_metadata(
        self,
        issue_signature: str,
        limit: int = 5,
    ) -> list[tuple[str, str, str, str, str]]:
        """Get sample messages with user metadata for ticket formatting.

        Returns list of (message, conversation_id, email, user_id, org_id) tuples.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT c.source_body, c.id, c.contact_email, c.user_id, c.org_id
                        FROM themes t
                        JOIN conversations c ON t.conversation_id = c.id
                        WHERE t.issue_signature = %s
                          AND c.source_body IS NOT NULL
                        ORDER BY t.extracted_at DESC
                        LIMIT %s
                        """,
                        (issue_signature, limit)
                    )
                    return [
                        (row[0], row[1], row[2], row[3], row[4])
                        for row in cur.fetchall()
                    ]

        except Exception as e:
            logger.error(f"Failed to get sample messages with metadata: {e}")
            return []

    def _build_bug_description(self, agg: ThemeAggregate, excerpts: str = "") -> str:
        """Build ticket description for bug/technical issues."""
        symptoms_list = "\n".join(f"{i+1}. {s}" for i, s in enumerate(agg.sample_symptoms or []))

        return f"""## Problem

Users are experiencing issues with **{agg.component}** in the **{agg.product_area}** area. This has been reported {agg.occurrence_count} times.

**User Goal:** {agg.sample_user_intent or 'Not specified'}

## Steps to Reproduce

{symptoms_list or '1. (No specific reproduction steps captured)'}

## Affected Flow

{agg.sample_affected_flow or 'Not specified'}

## Technical Context

**Root Cause Hypothesis:** {agg.sample_root_cause_hypothesis or 'Not yet analyzed'}

**Frequency:** {agg.occurrence_count} reports between {agg.first_seen_at.strftime('%Y-%m-%d') if agg.first_seen_at else 'N/A'} and {agg.last_seen_at.strftime('%Y-%m-%d') if agg.last_seen_at else 'N/A'}

{excerpts}

## Acceptance Criteria

- [ ] Root cause identified and documented
- [ ] Fix implemented that addresses the symptoms above
- [ ] No regression in related {agg.product_area} functionality

---
*Auto-generated by FeedForward from {agg.occurrence_count} customer reports*
"""

    def _build_trend_description(self, agg: ThemeAggregate, excerpts: str = "") -> str:
        """Build ticket description for support/ops trends."""
        symptoms_list = "\n".join(f"- {s}" for s in (agg.sample_symptoms or []))

        return f"""## Summary

**Volume:** {agg.occurrence_count} conversations
**Product Area:** {agg.product_area}
**Component:** {agg.component}
**Period:** {agg.first_seen_at.strftime('%Y-%m-%d') if agg.first_seen_at else 'N/A'} to {agg.last_seen_at.strftime('%Y-%m-%d') if agg.last_seen_at else 'N/A'}

## What Users Are Asking

{agg.sample_user_intent or 'Not specified'}

## Common Patterns

{symptoms_list or '- No specific patterns captured'}

{excerpts}

## Suggested Actions

- [ ] Review if FAQ/docs need updating for this topic
- [ ] Consider if self-service options could reduce volume
- [ ] Evaluate if product changes could address root cause

---
*Auto-generated by FeedForward from {agg.occurrence_count} customer conversations*
"""

    def create_tickets_for_themes(
        self,
        recency_days: int = 30,
        dry_run: bool = False,
    ) -> list[str]:
        """
        Create Shortcut tickets for all themes that have reached threshold.

        Uses different templates based on theme type:
        - 'bug': Technical issues with steps to reproduce, acceptance criteria
        - 'trend': Support patterns with volume analysis, suggested actions

        Returns list of created ticket IDs.
        """
        themes = self.get_themes_needing_tickets(recency_days=recency_days)
        if not themes:
            logger.info("No themes need tickets")
            return []

        shortcut = ShortcutClient(dry_run=dry_run)

        if not shortcut.backlog_state_id:
            logger.error("SHORTCUT_BACKLOG_STATE_ID not set - cannot create tickets")
            return []

        created_ids = []

        for agg in themes:
            # Determine theme type and build appropriate description
            theme_type = self.get_theme_type(agg.issue_signature)

            # Get formatted excerpts with media links
            excerpts = self._format_excerpts(agg.issue_signature)

            if theme_type == 'bug':
                description = self._build_bug_description(agg, excerpts=excerpts)
                story_type = "bug"
            else:
                description = self._build_trend_description(agg, excerpts=excerpts)
                story_type = "chore"  # Trends are chores, not bugs

            # Create the story with readable title
            readable_title = self._format_title(agg.issue_signature)
            title = f"[{agg.occurrence_count}] {readable_title}"
            story_id = shortcut.create_story(
                name=title,
                description=description,
                story_type=story_type,
                workflow_state_id=shortcut.backlog_state_id,
            )

            if story_id:
                created_ids.append(story_id)
                self.mark_ticket_created(agg.issue_signature, story_id)
                logger.info(f"Created ticket {story_id} for {agg.issue_signature}")
            else:
                logger.error(f"Failed to create ticket for {agg.issue_signature}")

        return created_ids

    def update_ticket_for_theme(
        self,
        issue_signature: str,
        new_excerpt: Optional[str] = None,
        max_excerpts: int = 10,
        dry_run: bool = False,
        # User metadata for context
        email: Optional[str] = None,
        org_id: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,  # Intercom conversation ID
    ) -> bool:
        """
        Update an existing ticket with new count and optionally add excerpt.

        Called when a new conversation is added to a theme that already has a ticket.
        Updates the ticket title to reflect new count [N] and adds excerpt if:
        - We have fewer than max_excerpts
        - The new excerpt is specific enough (scores above threshold)

        Args:
            issue_signature: The theme's canonical signature
            new_excerpt: Customer message excerpt to add
            max_excerpts: Maximum excerpts per ticket (default 10)
            dry_run: If True, don't actually update Shortcut
            email: Customer email address
            org_id: Customer's organization ID
            user_id: Customer's user ID

        Returns True if ticket was updated.
        """
        agg = self.get_aggregate(issue_signature)
        if not agg or not agg.ticket_created or not agg.ticket_id:
            return False

        shortcut = ShortcutClient(dry_run=dry_run)

        # Update count in title
        shortcut.update_story_count(agg.ticket_id, agg.occurrence_count)

        # Check if we should add the excerpt
        if new_excerpt:
            current_excerpts = agg.ticket_excerpts or []

            if len(current_excerpts) < max_excerpts:
                # Check if excerpt is specific enough
                score = score_excerpt_specificity(new_excerpt)
                if score >= 5:  # Minimum threshold
                    # Check it's not a duplicate (simple substring check)
                    excerpt_preview = new_excerpt[:100]
                    is_duplicate = any(
                        excerpt_preview in existing or existing[:100] in new_excerpt
                        for existing in current_excerpts
                    )

                    if not is_duplicate:
                        # Build user info line with links
                        user_info_parts = []

                        # Intercom conversation link
                        if conversation_id:
                            intercom_app_id = os.getenv("INTERCOM_APP_ID", "2t3d8az2")
                            convo_url = f"https://app.intercom.com/a/apps/{intercom_app_id}/inbox/inbox/conversation/{conversation_id}"
                            label = email if email else f"Conversation {conversation_id}"
                            user_info_parts.append(f"[{label}]({convo_url})")
                        elif email:
                            user_info_parts.append(f"Email: {email}")

                        # Jarvis org link
                        if org_id:
                            org_url = f"https://jarvis.tailwind.ai/organizations/{org_id}"
                            user_info_parts.append(f"[Org: {org_id}]({org_url})")

                        # Jarvis user link (requires org_id)
                        if user_id and org_id:
                            user_url = f"https://jarvis.tailwind.ai/organizations/{org_id}/users/{user_id}"
                            user_info_parts.append(f"[User: {user_id}]({user_url})")
                        elif user_id:
                            user_info_parts.append(f"User ID: {user_id}")

                        user_info = " | ".join(user_info_parts) if user_info_parts else "Unknown user"

                        # Extract media links (screenshots, Looms, etc.)
                        media_links = extract_media_links(new_excerpt)
                        media_section = ""
                        if media_links:
                            media_items = [f"- [{link_type}]({url})" for url, link_type in media_links]
                            media_section = "\n📎 **Attachments:**\n" + "\n".join(media_items) + "\n"

                        # Add to ticket
                        formatted = f"**Customer report:**\n{user_info}\n> {new_excerpt[:500]}{media_section}"
                        if shortcut.append_to_description(agg.ticket_id, formatted):
                            # Update stored excerpts
                            self._add_ticket_excerpt(issue_signature, new_excerpt)
                            logger.info(
                                f"Added excerpt to ticket {agg.ticket_id} "
                                f"(score: {score}, total: {len(current_excerpts) + 1})"
                            )

        return True

    def _add_ticket_excerpt(self, issue_signature: str, excerpt: str) -> None:
        """Add an excerpt to the stored list for a theme."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE theme_aggregates
                        SET ticket_excerpts = ticket_excerpts || %s::jsonb
                        WHERE issue_signature = %s
                        """,
                        (json.dumps([excerpt]), issue_signature)
                    )
        except Exception as e:
            logger.error(f"Failed to add ticket excerpt: {e}")

    def get_ticket_excerpts(self, issue_signature: str) -> list[str]:
        """Get the excerpts already added to a theme's ticket."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT ticket_excerpts
                        FROM theme_aggregates
                        WHERE issue_signature = %s
                        """,
                        (issue_signature,)
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        return row[0] if isinstance(row[0], list) else json.loads(row[0])
                    return []
        except Exception as e:
            logger.error(f"Failed to get ticket excerpts: {e}")
            return []

    def get_stale_tickets(self, stale_days: int = 30) -> list[ThemeAggregate]:
        """
        Get themes with tickets that haven't had activity in stale_days.

        These are candidates for auto-closing.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            issue_signature, product_area, component,
                            occurrence_count, first_seen_at, last_seen_at,
                            sample_user_intent, sample_symptoms,
                            sample_affected_flow, sample_root_cause_hypothesis,
                            ticket_created, ticket_id, ticket_excerpts
                        FROM theme_aggregates
                        WHERE ticket_created = TRUE
                          AND ticket_id IS NOT NULL
                          AND last_seen_at < NOW() - INTERVAL '%s days'
                        ORDER BY last_seen_at ASC
                        """,
                        (stale_days,)
                    )
                    rows = cur.fetchall()

                    aggregates = []
                    for row in rows:
                        symptoms = row[7]
                        if isinstance(symptoms, str):
                            symptoms = json.loads(symptoms)
                        excerpts = row[12]
                        if isinstance(excerpts, str):
                            excerpts = json.loads(excerpts)

                        aggregates.append(ThemeAggregate(
                            issue_signature=row[0],
                            product_area=row[1],
                            component=row[2],
                            occurrence_count=row[3],
                            first_seen_at=row[4],
                            last_seen_at=row[5],
                            sample_user_intent=row[6],
                            sample_symptoms=symptoms,
                            sample_affected_flow=row[8],
                            sample_root_cause_hypothesis=row[9],
                            ticket_created=row[10],
                            ticket_id=row[11],
                            ticket_excerpts=excerpts,
                        ))

                    return aggregates

        except Exception as e:
            logger.error(f"Failed to get stale tickets: {e}")
            return []

    def close_stale_tickets(
        self,
        stale_days: int = 30,
        dry_run: bool = False,
    ) -> list[str]:
        """
        Close tickets for themes that haven't had activity in stale_days.

        Returns list of closed ticket IDs.
        """
        stale = self.get_stale_tickets(stale_days)
        if not stale:
            return []

        shortcut = ShortcutClient(dry_run=dry_run)
        closed = []

        for agg in stale:
            # Add comment explaining auto-close
            days_inactive = (datetime.utcnow() - agg.last_seen_at).days
            comment = (
                f"🤖 Auto-closed: No new reports in {days_inactive} days.\n\n"
                f"Last seen: {agg.last_seen_at.strftime('%Y-%m-%d')}\n"
                f"Total reports: {agg.occurrence_count}\n\n"
                f"This ticket will be reopened if the issue is reported again."
            )
            shortcut.add_comment(agg.ticket_id, comment)

            # Move to done
            if shortcut.move_to_done(agg.ticket_id):
                closed.append(agg.ticket_id)
                logger.info(
                    f"Closed stale ticket {agg.ticket_id} for {agg.issue_signature} "
                    f"(inactive {days_inactive} days)"
                )

        return closed

    def reopen_ticket_for_theme(
        self,
        issue_signature: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Reopen a closed ticket when a theme resurfaces.

        Called when update_ticket_for_theme detects the issue was previously closed.
        Adds a comment noting the reopening.
        """
        agg = self.get_aggregate(issue_signature)
        if not agg or not agg.ticket_id:
            return False

        shortcut = ShortcutClient(dry_run=dry_run)

        # Add comment about reopening
        comment = (
            f"🔄 Reopened: Issue reported again.\n\n"
            f"New report count: {agg.occurrence_count}\n"
            f"This issue was previously auto-closed but has resurfaced."
        )
        shortcut.add_comment(agg.ticket_id, comment)

        # Note: Moving back to active state would require knowing the workflow
        # For now, the comment alerts the team. They can manually move it back.
        logger.info(f"Added reopen comment to ticket {agg.ticket_id} for {issue_signature}")

        return True

    def get_sample_messages(
        self,
        issue_signature: str,
        limit: int = 5,
    ) -> list[str]:
        """Get sample customer messages for a theme."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT c.source_body
                        FROM themes t
                        JOIN conversations c ON t.conversation_id = c.id
                        WHERE t.issue_signature = %s
                          AND c.source_body IS NOT NULL
                        ORDER BY t.extracted_at DESC
                        LIMIT %s
                        """,
                        (issue_signature, limit)
                    )
                    return [row[0] for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get sample messages: {e}")
            return []

    def get_sample_messages_with_ids(
        self,
        issue_signature: str,
        limit: int = 5,
    ) -> list[tuple[str, str]]:
        """Get sample customer messages with conversation IDs for a theme.

        Returns list of (message, conversation_id) tuples.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT c.source_body, c.id
                        FROM themes t
                        JOIN conversations c ON t.conversation_id = c.id
                        WHERE t.issue_signature = %s
                          AND c.source_body IS NOT NULL
                        ORDER BY t.extracted_at DESC
                        LIMIT %s
                        """,
                        (issue_signature, limit)
                    )
                    return [(row[0], row[1]) for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get sample messages with IDs: {e}")
            return []

    def format_trending_report(self, days: int = 7) -> str:
        """Generate a report of trending themes."""
        themes = self.get_trending_themes(days=days)

        if not themes:
            return f"No trending themes in the last {days} days."

        lines = [
            f"# Trending Themes (Last {days} Days)",
            "",
            f"Found {len(themes)} themes with 2+ occurrences:",
            "",
        ]

        for agg in themes:
            ticket_status = f" [Ticket: {agg.ticket_id}]" if agg.ticket_created else ""
            lines.append(
                f"- **{agg.issue_signature}** ({agg.occurrence_count}x) "
                f"[{agg.product_area}/{agg.component}]{ticket_status}"
            )

        return "\n".join(lines)


def generate_ticket_content(tracker: ThemeTracker, issue_signature: str) -> str:
    """Generate full ticket content for an issue signature."""
    agg = tracker.get_aggregate(issue_signature)
    if agg is None:
        return f"Theme not found: {issue_signature}"

    samples = tracker.get_sample_messages(issue_signature, limit=3)
    theme = agg.to_theme()

    return format_theme_for_ticket(
        theme,
        similar_count=agg.occurrence_count,
        sample_messages=samples,
    )


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    tracker = ThemeTracker(ticket_threshold=3)

    print("=" * 60)
    print("TRENDING THEMES REPORT")
    print("=" * 60)
    print(tracker.format_trending_report())

    print("\n" + "=" * 60)
    print("THEMES NEEDING TICKETS")
    print("=" * 60)
    needing_tickets = tracker.get_themes_needing_tickets()
    if needing_tickets:
        for agg in needing_tickets:
            print(f"- {agg.issue_signature} ({agg.occurrence_count}x)")
    else:
        print("No themes have reached the ticket threshold yet.")
