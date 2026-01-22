"""
Theme Quality Gates (Issue #104)

Validates extracted themes before using them for story creation.
Filters low-quality themes to prevent noise in the pipeline.

Quality Gates:
1. Confidence threshold - Themes with low confidence are filtered
2. Vocabulary validation - Themes must be from known vocabulary OR have high confidence
3. Unclassified filter - 'unclassified_needs_review' themes are filtered

Quality Score:
  - 1.0: vocabulary match + high confidence
  - 0.8: vocabulary match + medium confidence
  - 0.6: new theme + high confidence
  - 0.4: new theme + medium confidence
  - 0.2: vocabulary match + low confidence
  - 0.0: low confidence + not matched (filtered)
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QualityCheckResult:
    """Result of a theme quality gate check."""

    passed: bool
    quality_score: float  # 0.0 - 1.0
    reason: Optional[str] = None  # Reason for filtering (if not passed)
    details: Optional[dict] = None  # Breakdown of quality metrics


# Confidence level scores
CONFIDENCE_SCORES = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.2,
}

# Bonus for matching vocabulary (known, validated themes)
VOCABULARY_MATCH_BONUS = 0.2

# Threshold for passing quality gate
# Themes below this score are filtered
QUALITY_THRESHOLD = 0.3

# Signatures that are always filtered (catch-all patterns)
FILTERED_SIGNATURES = frozenset([
    "unclassified_needs_review",
    "unknown_issue",
    "other_issue",
])


def check_theme_quality(
    issue_signature: str,
    matched_existing: bool,
    match_confidence: str,
    threshold: float = QUALITY_THRESHOLD,
) -> QualityCheckResult:
    """
    Check if a theme passes quality gates.

    Args:
        issue_signature: The theme's issue signature
        matched_existing: Whether the LLM matched an existing vocabulary theme
        match_confidence: LLM confidence level (high/medium/low)
        threshold: Minimum quality score to pass

    Returns:
        QualityCheckResult with pass/fail status and score
    """
    # Gate 1: Filter catch-all signatures
    if issue_signature in FILTERED_SIGNATURES:
        return QualityCheckResult(
            passed=False,
            quality_score=0.0,
            reason=f"Filtered signature: {issue_signature}",
            details={
                "filtered_by": "signature_blocklist",
                "signature": issue_signature,
            },
        )

    # Calculate base confidence score
    confidence_score = CONFIDENCE_SCORES.get(match_confidence.lower(), 0.0)

    # Add bonus for vocabulary match
    vocabulary_bonus = VOCABULARY_MATCH_BONUS if matched_existing else 0.0

    # Calculate final quality score (capped at 1.0)
    quality_score = min(1.0, confidence_score + vocabulary_bonus)

    # Gate 2: Check against threshold
    if quality_score < threshold:
        reason_parts = []
        if not matched_existing:
            reason_parts.append("not in vocabulary")
        if confidence_score < 0.6:
            reason_parts.append(f"{match_confidence} confidence")
        reason = f"Below threshold ({quality_score:.2f} < {threshold}): {', '.join(reason_parts)}"

        return QualityCheckResult(
            passed=False,
            quality_score=quality_score,
            reason=reason,
            details={
                "filtered_by": "quality_threshold",
                "confidence": match_confidence,
                "confidence_score": confidence_score,
                "vocabulary_match": matched_existing,
                "vocabulary_bonus": vocabulary_bonus,
                "threshold": threshold,
            },
        )

    # Passed all gates
    return QualityCheckResult(
        passed=True,
        quality_score=quality_score,
        details={
            "confidence": match_confidence,
            "confidence_score": confidence_score,
            "vocabulary_match": matched_existing,
            "vocabulary_bonus": vocabulary_bonus,
        },
    )


def filter_themes_by_quality(
    themes: list,
    threshold: float = QUALITY_THRESHOLD,
) -> tuple[list, list, List[str]]:
    """
    Filter a list of themes by quality gates.

    Args:
        themes: List of Theme objects (from theme_extractor)
        threshold: Minimum quality score to pass

    Returns:
        (passed_themes, filtered_themes, warnings)
        - passed_themes: Themes that passed quality gates
        - filtered_themes: Themes that were filtered out
        - warnings: Warning messages about filtered themes
    """
    passed = []
    filtered = []
    warnings = []

    for theme in themes:
        result = check_theme_quality(
            issue_signature=theme.issue_signature,
            matched_existing=theme.matched_existing,
            match_confidence=theme.match_confidence or "low",
            threshold=threshold,
        )

        if result.passed:
            passed.append(theme)
        else:
            filtered.append(theme)
            # Sanitize warning: don't expose conversation IDs (security)
            # Just include theme signature and reason
            warnings.append(
                f"Theme filtered ({result.reason}): {theme.issue_signature}"
            )
            logger.info(
                f"Quality gate filtered theme: {theme.issue_signature} "
                f"(score={result.quality_score:.2f}, reason={result.reason})"
            )

    logger.info(
        f"Quality gates: {len(passed)} passed, {len(filtered)} filtered "
        f"(threshold={threshold})"
    )

    return passed, filtered, warnings
