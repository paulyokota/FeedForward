"""
Equivalence classes for conversation grouping.

This module provides equivalence class mapping for grouping conversations
that may have different classifications but represent the same underlying issue.

Usage:
    from src.equivalence import get_equivalence_class, is_short_ambiguous

    # Get equivalence class for grouping
    equiv = get_equivalence_class('bug_report', text)  # Returns 'technical'

    # Check if message should be skipped in accuracy calculations
    skip = is_short_ambiguous(text, 'other')  # Returns True for short "other" messages
"""

# Base equivalence mapping
# bug_report and product_question are often the same underlying issue
EQUIVALENCE_CLASSES = {
    'bug_report': 'technical',
    'product_question': 'technical',
}

# Patterns indicating a plan_question is actually describing a bug
BUG_INDICATORS = [
    "not letting",
    "won't let",
    "can't",
    "cannot",
    "not working",
    "doesn't work",
    "not able to",
    "unable to",
    "failing",
    "error",
    "broken",
    "stuck",
]


def get_equivalence_class(category: str, text: str = "") -> str:
    """
    Map a category to its equivalence class for grouping purposes.

    Args:
        category: The original classification category
        text: The conversation text (used for context-aware refinement)

    Returns:
        The equivalence class (e.g., 'technical', 'billing', etc.)

    Examples:
        >>> get_equivalence_class('bug_report')
        'technical'
        >>> get_equivalence_class('product_question')
        'technical'
        >>> get_equivalence_class('plan_question', "it's not letting me add an account")
        'technical'  # Refined due to bug indicator
        >>> get_equivalence_class('billing')
        'billing'
    """
    # Direct mapping for common cases
    if category in EQUIVALENCE_CLASSES:
        return EQUIVALENCE_CLASSES[category]

    # Context-aware refinement for plan_question
    # When a plan question contains bug indicators, treat as technical
    if category == 'plan_question' and text:
        text_lower = text.lower()
        if any(indicator in text_lower for indicator in BUG_INDICATORS):
            return 'technical'

    # All other categories map to themselves
    return category


def is_short_ambiguous(text: str, category: str) -> bool:
    """
    Check if a message is too short and ambiguous to classify meaningfully.

    Short messages classified as 'other' are considered ambiguous and should
    be excluded from accuracy calculations.

    Args:
        text: The conversation text
        category: The classification category

    Returns:
        True if the message should be skipped in accuracy calculations

    Examples:
        >>> is_short_ambiguous('hello', 'other')
        True
        >>> is_short_ambiguous('My pins are not posting', 'other')
        False  # Not short
        >>> is_short_ambiguous('hello', 'bug_report')
        False  # Not 'other' category
    """
    word_count = len(text.split())
    return word_count < 5 and category == 'other'


def are_equivalent(category1: str, category2: str,
                   text1: str = "", text2: str = "") -> bool:
    """
    Check if two categories are equivalent for grouping purposes.

    Args:
        category1: First classification category
        category2: Second classification category
        text1: Text for first conversation (optional, for context-aware comparison)
        text2: Text for second conversation (optional)

    Returns:
        True if the categories should be treated as the same for grouping

    Examples:
        >>> are_equivalent('bug_report', 'product_question')
        True
        >>> are_equivalent('bug_report', 'billing')
        False
    """
    equiv1 = get_equivalence_class(category1, text1)
    equiv2 = get_equivalence_class(category2, text2)
    return equiv1 == equiv2


# All valid equivalence classes
VALID_EQUIVALENCE_CLASSES = {
    'technical',      # bug_report, product_question, refined plan_question
    'feature_request',
    'plan_question',
    'marketing_question',
    'billing',
    'account_access',
    'feedback',
    'other',
}
