"""
Customer Digest Extractor for improved embedding/facet/theme quality.

WHAT IS A CUSTOMER DIGEST?
A customer digest combines two key messages from a conversation:
1. The FIRST customer message (source_body) - provides initial context
2. The MOST SPECIFIC customer message - contains actionable error details

WHY USE DIGESTS?
First messages are often vague ("Help please", "Something's wrong"). Error details,
error codes, and specific symptoms typically appear later in the conversation.
The digest captures both the initial context AND the diagnostic details.

SPECIFICITY SCORING:
Messages are scored using fast heuristics (no LLM):
- Typical ranges: -2 to 0 (generic), 1-4 (moderate specificity), 5+ (high specificity)
- High scores indicate messages with error codes, specific keywords, or quoted errors

Issue #139: Use customer-only digest for embeddings/facets/themes
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# Error keywords for specificity scoring (+2 points)
ERROR_KEYWORDS = {
    "error", "failed", "cannot", "can't", "doesn't work", "won't",
    "broken", "not working", "not posting", "not showing", "not appearing",
    "stuck", "crash", "bug", "issue", "problem", "wrong"
}

# Feature nouns for specificity scoring (+1 point)
FEATURE_NOUNS = {
    "drafts", "draft", "scheduler", "schedule", "scheduling",
    "upload", "uploads", "pin", "pins", "pinterest",
    "instagram", "facebook", "twitter", "linkedin", "tiktok",
    "analytics", "stats", "statistics", "report", "reports",
    "queue", "calendar", "post", "posts", "media", "image", "video",
    "hashtag", "hashtags", "caption", "captions", "link", "links",
    "account", "accounts", "profile", "profiles", "team", "workspace",
    "bulk", "batch", "import", "export", "csv", "rss", "feed",
    "notification", "notifications", "email", "emails",
    "ai", "ghostwriter", "smart", "auto", "autopilot"
}

# Generic/short message patterns that reduce score (-2 points)
GENERIC_PATTERNS = {
    "thanks", "thank you", "ok", "okay", "hello", "hi", "hey",
    "got it", "great", "awesome", "perfect", "sounds good",
    "yes", "no", "sure", "please", "help"
}

# Regex patterns for scoring
# ReDoS protection: Use bounded quantifiers to prevent catastrophic backtracking
QUOTED_ERROR_PATTERN = re.compile(r'["\'][^"\']{5,500}["\']')  # Bounded to 500 chars
ERROR_CODE_PATTERN = re.compile(r'\b(E?\d{3,5}|ERR[_-]?\w{1,50}|[A-Z]{1,30}_ERROR)\b', re.IGNORECASE)
URL_PATTERN = re.compile(r'https?://\S{1,500}|www\.\S{1,500}', re.IGNORECASE)  # Bounded URLs

# Maximum input size to prevent memory exhaustion (100KB per message)
MAX_INPUT_SIZE = 100_000
SCREENSHOT_MARKERS = {"screenshot", "attached", "attachment", "image", "see below", "showing"}


def extract_customer_messages(raw_conversation: dict) -> List[str]:
    """
    Extract customer messages from conversation_parts.

    Filters by author_type in ('user', 'lead', 'contact') and part_type = 'comment'.
    Returns list of message bodies in chronological order.

    Args:
        raw_conversation: Full Intercom conversation dict with conversation_parts

    Returns:
        List of customer message strings (empty if no customer messages)
    """
    customer_messages = []

    conversation_parts = raw_conversation.get("conversation_parts", {})
    parts = conversation_parts.get("conversation_parts", []) if isinstance(conversation_parts, dict) else []

    for part in parts:
        part_type = part.get("part_type")
        author = part.get("author", {})
        author_type = author.get("type")

        # Customer messages are from users, leads, or contacts
        if author_type in ("user", "lead", "contact") and part_type == "comment":
            body = part.get("body", "")
            if body and body.strip():
                # Strip HTML tags if present
                clean_body = _strip_html(body)
                if clean_body:
                    customer_messages.append(clean_body)

    return customer_messages


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    # Simple HTML tag removal
    clean = re.sub(r'<[^>]+>', ' ', text)
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def score_message_specificity(message: str) -> int:
    """
    Score a message for specificity using fast heuristic (no LLM).

    Scoring rules:
    - +3: quoted error text (regex: r'"[^"]{5,}"' or r"'[^']{5,}'")
    - +2: error keywords (error, failed, cannot, doesn't work, won't, broken)
    - +2: error codes/numbers (regex: r'\\b(E?\\d{3,5}|ERR_\\w+)\\b')
    - +1: feature nouns (from predefined list: drafts, scheduler, upload, pin, etc.)
    - +1: URL/screenshot marker (regex: url patterns, "screenshot", "attached")
    - -2: very short (<20 chars) or generic ("thanks", "ok", "hello")

    Args:
        message: Single customer message text

    Returns:
        Integer specificity score (can be negative)
    """
    if not message:
        return -2

    score = 0
    message_lower = message.lower()

    # -2: Very short or generic
    if len(message) < 20:
        score -= 2

    # Check for generic patterns (case-insensitive word match)
    words = set(message_lower.split())
    if words & GENERIC_PATTERNS and len(message) < 50:
        score -= 2

    # +3: Quoted error text
    if QUOTED_ERROR_PATTERN.search(message):
        score += 3

    # +2: Error keywords
    for keyword in ERROR_KEYWORDS:
        if keyword in message_lower:
            score += 2
            break  # Only count once

    # +2: Error codes/numbers
    if ERROR_CODE_PATTERN.search(message):
        score += 2

    # +1: Feature nouns
    if words & FEATURE_NOUNS:
        score += 1

    # +1: URL or screenshot marker
    if URL_PATTERN.search(message):
        score += 1
    elif any(marker in message_lower for marker in SCREENSHOT_MARKERS):
        score += 1

    return score


def build_customer_digest(
    source_body: str,
    customer_messages: List[str],
    max_length: int = 2000
) -> str:
    """
    Build digest from first message + most specific message.

    Logic:
    1. If no additional customer messages, return source_body
    2. Score all customer messages
    3. Find message with highest specificity score
    4. If best message is same as source_body, return source_body only
    5. Otherwise, concatenate: source_body + "\\n\\n---\\n\\n" + best_message
    6. Truncate to max_length

    Args:
        source_body: First customer message (already in conversations.source_body)
        customer_messages: All customer messages from conversation_parts
        max_length: Maximum digest length for embedding compatibility

    Returns:
        Digest string for use in embeddings/facets/themes
    """
    # Input validation and size limits to prevent memory exhaustion
    if not source_body:
        source_body = ""
    else:
        source_body = source_body[:MAX_INPUT_SIZE]  # Truncate early

    # Validate and filter customer_messages
    if customer_messages:
        if not all(isinstance(msg, str) for msg in customer_messages):
            logger.warning("customer_messages contains non-string values, filtering")
            customer_messages = [m for m in customer_messages if isinstance(m, str)]
        # Limit count and size per message
        customer_messages = [msg[:MAX_INPUT_SIZE] for msg in customer_messages[:100]]

    source_body = source_body.strip()

    # If no additional messages, return source_body
    if not customer_messages:
        return source_body[:max_length] if source_body else ""

    # Score all customer messages
    scored_messages = [(msg, score_message_specificity(msg)) for msg in customer_messages]

    # Find the highest scoring message
    if not scored_messages:
        return source_body[:max_length] if source_body else ""

    best_message, best_score = max(scored_messages, key=lambda x: x[1])

    # Also score the source_body
    source_score = score_message_specificity(source_body)

    # If source_body is the most specific or tied, just return it
    if source_score >= best_score:
        return source_body[:max_length]

    # Check if best_message is essentially the same as source_body
    # (could happen if source_body appears in conversation_parts too)
    if _messages_are_similar(source_body, best_message):
        return source_body[:max_length]

    # Combine source_body with most specific message
    separator = "\n\n---\n\n"

    # Calculate available space for each part
    separator_len = len(separator)
    available = max_length - separator_len

    if available <= 0:
        return source_body[:max_length]

    # Give 60% to source_body, 40% to best_message
    # Rationale: source_body provides essential initial context (who the user is,
    # what they're trying to do). best_message adds diagnostic details (error codes,
    # symptoms). 60/40 prioritizes context while preserving room for specifics.
    source_limit = int(available * 0.6)
    best_limit = available - source_limit

    truncated_source = source_body[:source_limit].strip()
    truncated_best = best_message[:best_limit].strip()

    if not truncated_best:
        return truncated_source

    digest = f"{truncated_source}{separator}{truncated_best}"

    return digest[:max_length]


def _messages_are_similar(msg1: str, msg2: str, threshold: float = 0.9) -> bool:
    """
    Check if two messages are substantially similar.

    Uses simple length and overlap heuristic for speed.
    """
    if not msg1 or not msg2:
        return False

    # Normalize
    m1 = msg1.lower().strip()
    m2 = msg2.lower().strip()

    # Exact match
    if m1 == m2:
        return True

    # One contains the other
    if m1 in m2 or m2 in m1:
        return True

    # Length difference check
    len_ratio = min(len(m1), len(m2)) / max(len(m1), len(m2)) if max(len(m1), len(m2)) > 0 else 0
    if len_ratio < 0.5:
        return False  # Too different in length

    # Word overlap check
    words1 = set(m1.split())
    words2 = set(m2.split())

    if not words1 or not words2:
        return False

    overlap = len(words1 & words2) / max(len(words1), len(words2))

    return overlap >= threshold


def build_full_conversation_text(
    raw_conversation: dict,
    max_length: int = 15000
) -> str:
    """
    Build formatted full conversation text from Intercom conversation parts.

    Issue #144 - Smart Digest: Provides the complete conversation thread
    for theme extraction, including all customer and support messages.

    Format:
        [Customer]: First message here...
        [Support]: Response here...
        [Customer]: Follow-up here...

    Args:
        raw_conversation: Full Intercom conversation dict with source and conversation_parts
        max_length: Maximum output length (default 15K chars, ~3750 tokens)

    Returns:
        Formatted conversation string, empty string if no content available.
    """
    if not raw_conversation:
        return ""

    parts = []

    # Add the initial source message (the first customer message)
    source = raw_conversation.get("source", {})
    source_body = source.get("body", "")
    if source_body:
        clean_body = _strip_html(source_body)
        if clean_body:
            parts.append(f"[Customer]: {clean_body}")

    # Add conversation parts in chronological order
    conv_parts_container = raw_conversation.get("conversation_parts", {})
    conv_parts = (
        conv_parts_container.get("conversation_parts", [])
        if isinstance(conv_parts_container, dict)
        else []
    )

    for part in conv_parts:
        body = part.get("body", "")
        part_type = part.get("part_type", "")

        # Skip non-comment parts (assignments, notes, state changes)
        if part_type != "comment" or not body:
            continue

        clean_body = _strip_html(body)
        if not clean_body:
            continue

        # Determine author label
        author = part.get("author", {})
        author_type = author.get("type", "unknown")

        if author_type in ("user", "lead", "contact"):
            label = "Customer"
        elif author_type in ("admin", "bot"):
            label = "Support"
        else:
            label = author_type.capitalize()

        parts.append(f"[{label}]: {clean_body}")

    if not parts:
        return ""

    # Join with double newlines for readability
    full_text = "\n\n".join(parts)

    # Truncate if needed, preserving complete messages where possible
    if len(full_text) > max_length:
        # Simple truncation - prioritize beginning of conversation
        # Future: Could implement smart truncation keeping first + last messages
        full_text = full_text[:max_length]
        # Try to end at a message boundary
        last_bracket = full_text.rfind("\n\n[")
        if last_bracket > max_length * 0.5:  # Don't cut too much
            full_text = full_text[:last_bracket]

    return full_text
