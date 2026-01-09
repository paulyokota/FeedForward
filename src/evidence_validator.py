"""
Evidence validation for Shortcut story creation.

This module ensures that samples captured during theme extraction contain
the metadata required for actionable evidence in stories.

REQUIRED FIELDS (stories won't be created without these):
- id: Conversation ID for Intercom link
- excerpt: Conversation text for context

RECOMMENDED FIELDS (warning if missing):
- email: Customer email for display
- intercom_url: Direct link to conversation

OPTIONAL FIELDS (nice to have for Jarvis links):
- org_id: Tailwind org ID
- user_id: Tailwind user ID
- contact_id: Intercom contact ID

Usage:
    from evidence_validator import validate_samples, EvidenceQuality

    quality = validate_samples(samples)
    if quality.is_valid:
        create_story(samples)
    else:
        print(f"Cannot create story: {quality.errors}")
"""

from dataclasses import dataclass, field
from typing import Optional


# Required fields - stories MUST have these
REQUIRED_FIELDS = ["id", "excerpt"]

# Recommended fields - warn if missing
RECOMMENDED_FIELDS = ["email", "intercom_url"]

# Optional fields - nice to have
OPTIONAL_FIELDS = ["org_id", "user_id", "contact_id"]

# All evidence fields
ALL_EVIDENCE_FIELDS = REQUIRED_FIELDS + RECOMMENDED_FIELDS + OPTIONAL_FIELDS


@dataclass
class EvidenceQuality:
    """Result of evidence validation."""

    is_valid: bool
    """Whether the samples meet minimum requirements for story creation."""

    sample_count: int
    """Number of samples checked."""

    errors: list[str] = field(default_factory=list)
    """Critical issues that prevent story creation."""

    warnings: list[str] = field(default_factory=list)
    """Non-critical issues that reduce evidence quality."""

    coverage: dict[str, float] = field(default_factory=dict)
    """Percentage of samples with each field populated."""

    def __str__(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"
        parts = [f"EvidenceQuality({status}, {self.sample_count} samples)"]
        if self.errors:
            parts.append(f"  Errors: {', '.join(self.errors)}")
        if self.warnings:
            parts.append(f"  Warnings: {', '.join(self.warnings)}")
        return "\n".join(parts)


def validate_samples(samples: list[dict], min_samples: int = 1) -> EvidenceQuality:
    """
    Validate that samples contain required evidence fields.

    Args:
        samples: List of sample dicts from theme extraction
        min_samples: Minimum number of samples required

    Returns:
        EvidenceQuality with validation results
    """
    errors = []
    warnings = []

    if not samples:
        return EvidenceQuality(
            is_valid=False,
            sample_count=0,
            errors=["No samples provided"],
        )

    if len(samples) < min_samples:
        errors.append(f"Need at least {min_samples} samples, got {len(samples)}")

    # Calculate field coverage
    coverage = {}
    for field_name in ALL_EVIDENCE_FIELDS:
        count = sum(1 for s in samples if s.get(field_name))
        coverage[field_name] = count / len(samples) * 100

    # Check required fields
    for field_name in REQUIRED_FIELDS:
        if coverage[field_name] < 100:
            missing = len(samples) - int(coverage[field_name] * len(samples) / 100)
            errors.append(f"Required field '{field_name}' missing in {missing} samples")

    # Check recommended fields
    for field_name in RECOMMENDED_FIELDS:
        if coverage[field_name] < 80:
            warnings.append(
                f"Recommended field '{field_name}' only {coverage[field_name]:.0f}% coverage"
            )

    # Check for placeholder excerpts
    placeholder_patterns = [
        "not captured during batch processing",
        "to gather evidence",
        "search intercom for",
    ]
    placeholder_count = 0
    for sample in samples:
        excerpt = (sample.get("excerpt") or "").lower()
        if any(p in excerpt for p in placeholder_patterns):
            placeholder_count += 1

    if placeholder_count > 0:
        errors.append(
            f"{placeholder_count} samples have placeholder excerpts instead of real content"
        )

    return EvidenceQuality(
        is_valid=len(errors) == 0,
        sample_count=len(samples),
        errors=errors,
        warnings=warnings,
        coverage=coverage,
    )


def validate_sample(sample: dict) -> tuple[bool, list[str]]:
    """
    Validate a single sample dict.

    Returns:
        (is_valid, list of issues)
    """
    issues = []

    for field_name in REQUIRED_FIELDS:
        if not sample.get(field_name):
            issues.append(f"Missing required field: {field_name}")

    # Check excerpt quality
    excerpt = sample.get("excerpt", "")
    if len(excerpt) < 20:
        issues.append(f"Excerpt too short ({len(excerpt)} chars)")

    return len(issues) == 0, issues


def build_evidence_report(samples: list[dict]) -> str:
    """
    Build a human-readable evidence quality report.

    Useful for debugging when stories have poor evidence.
    """
    quality = validate_samples(samples)

    lines = [
        "=" * 50,
        "EVIDENCE QUALITY REPORT",
        "=" * 50,
        f"Samples: {quality.sample_count}",
        f"Valid: {quality.is_valid}",
        "",
        "Field Coverage:",
    ]

    for field_name, pct in sorted(quality.coverage.items(), key=lambda x: -x[1]):
        status = "✓" if pct >= 80 else "⚠" if pct >= 50 else "✗"
        lines.append(f"  {status} {field_name}: {pct:.0f}%")

    if quality.errors:
        lines.extend(["", "ERRORS:"])
        for e in quality.errors:
            lines.append(f"  ✗ {e}")

    if quality.warnings:
        lines.extend(["", "WARNINGS:"])
        for w in quality.warnings:
            lines.append(f"  ⚠ {w}")

    lines.append("=" * 50)
    return "\n".join(lines)


# Quick self-test
if __name__ == "__main__":
    # Test with good samples
    good_samples = [
        {
            "id": "123",
            "excerpt": "I'm having trouble connecting my Instagram account",
            "email": "user@example.com",
            "intercom_url": "https://app.intercom.com/...",
            "org_id": "org_123",
            "user_id": "user_456",
        },
        {
            "id": "124",
            "excerpt": "The scheduler is not working properly",
            "email": "another@example.com",
            "intercom_url": "https://app.intercom.com/...",
        },
    ]

    print("Good samples:")
    print(build_evidence_report(good_samples))
    print()

    # Test with bad samples
    bad_samples = [
        {"id": "123"},  # Missing excerpt
        {"excerpt": "short"},  # Missing id, short excerpt
    ]

    print("Bad samples:")
    print(build_evidence_report(bad_samples))
