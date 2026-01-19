"""
Migrate patterns from v1 (narrative) format to v2 (keyword-based) format.

V1 patterns are narrative descriptions like:
  "Keep OAuth flow for a single platform in one story"

V2 patterns extract keywords for cheap mode matching:
  keywords: ["oauth", "flow", "single", "platform", "story"]
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

from models import (
    LearnedPatternsV1,
    LearnedPatternsV2,
    PatternV1,
    PatternV2,
)


# Stop words to exclude from keyword extraction
STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "are",
    "were",
    "been",
    "be",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "dare",
    "ought",
    "used",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "what",
    "which",
    "who",
    "whom",
    "when",
    "where",
    "why",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "also",
}

# Domain-specific keywords to always include if present
DOMAIN_KEYWORDS = {
    # Services
    "aero",
    "tack",
    "charlotte",
    "ghostwriter",
    "zuck",
    "gandalf",
    "pablo",
    "bach",
    # Features
    "oauth",
    "auth",
    "authentication",
    "api",
    "endpoint",
    "handler",
    "service",
    "component",
    "scheduler",
    "queue",
    "webhook",
    "callback",
    # Platforms
    "pinterest",
    "instagram",
    "facebook",
    "twitter",
    "linkedin",
    "tiktok",
    # Concepts
    "token",
    "refresh",
    "scope",
    "story",
    "acceptance",
    "criteria",
    "user",
    "customer",
    "error",
    "failure",
    "retry",
    "timeout",
}


def extract_keywords(text: str) -> list[str]:
    """
    Extract meaningful keywords from a pattern description.

    Strategy:
    1. Tokenize by word boundaries
    2. Lowercase everything
    3. Remove stop words
    4. Keep domain-specific keywords
    5. Keep words >= 3 chars
    """
    # Tokenize
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())

    keywords = set()

    for word in words:
        # Always keep domain keywords
        if word in DOMAIN_KEYWORDS:
            keywords.add(word)
            continue

        # Skip stop words
        if word in STOP_WORDS:
            continue

        # Keep words >= 3 chars
        if len(word) >= 3:
            keywords.add(word)

    return sorted(keywords)


def migrate_pattern(pattern: PatternV1, index: int) -> PatternV2:
    """Convert a single v1 pattern to v2 format."""
    # Extract keywords from description and example
    combined_text = f"{pattern.description} {pattern.example}"
    keywords = extract_keywords(combined_text)

    # Defensive: ensure at least one keyword exists
    if not keywords:
        # Fallback: extract ANY alphanumeric tokens as keywords (first 5)
        keywords = sorted(set(re.findall(r"\b[a-z]{3,}\b", combined_text.lower())))[:5]

    # Map type with proper Literal typing
    pattern_type: Literal["good", "bad"] = (
        "good" if pattern.type == "good_pattern" else "bad"
    )

    return PatternV2(
        id=f"p_{index:04d}",
        type=pattern_type,
        description=pattern.description,
        keywords=keywords,
        weight=1.0,
        source=pattern.source,
        discovered_at=pattern.discovered_at,
        accuracy=0.0,  # Will be calibrated during dual-mode runs
        times_fired=0,
        status="active",
    )


def migrate_patterns_file(
    input_path: str | Path,
    output_path: str | Path,
    backup: bool = True,
) -> dict:
    """
    Migrate a v1 patterns file to v2 format.

    Args:
        input_path: Path to v1 learned_patterns.json
        output_path: Path for v2 output file
        backup: Whether to backup input file before migration

    Returns:
        Migration stats dict
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # Load v1 data
    with open(input_path) as f:
        raw_data = json.load(f)

    # Check if already v2
    if raw_data.get("version", "1.0").startswith("2"):
        return {
            "status": "skipped",
            "reason": "already_v2",
            "pattern_count": len(raw_data.get("patterns", [])),
        }

    # Parse v1 format
    v1_data = LearnedPatternsV1(**raw_data)

    # Backup if requested
    if backup:
        backup_path = input_path.with_suffix(".json.v1_backup")
        shutil.copy(input_path, backup_path)

    # Migrate patterns
    v2_patterns = []
    for i, pattern in enumerate(v1_data.patterns):
        v2_pattern = migrate_pattern(pattern, i)
        v2_patterns.append(v2_pattern)

    # Create v2 structure
    v2_data = LearnedPatternsV2(
        version="2.0",
        last_updated=datetime.now(),
        patterns=v2_patterns,
        calibration_history=[],
    )

    # Write v2 file
    with open(output_path, "w") as f:
        json.dump(v2_data.model_dump(mode="json"), f, indent=2, default=str)

    # Compute stats
    good_count = sum(1 for p in v2_patterns if p.type == "good")
    bad_count = sum(1 for p in v2_patterns if p.type == "bad")
    avg_keywords = (
        sum(len(p.keywords) for p in v2_patterns) / len(v2_patterns)
        if v2_patterns
        else 0
    )

    return {
        "status": "success",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "total_patterns": len(v2_patterns),
        "good_patterns": good_count,
        "bad_patterns": bad_count,
        "avg_keywords_per_pattern": round(avg_keywords, 1),
        "backup_created": backup,
    }


def validate_migration(v1_path: str | Path, v2_path: str | Path) -> dict:
    """
    Validate that migration preserved all patterns correctly.

    Returns validation report.
    """
    with open(v1_path) as f:
        v1_data = json.load(f)

    with open(v2_path) as f:
        v2_data = json.load(f)

    issues = []

    # Check counts match
    v1_count = len(v1_data.get("patterns", []))
    v2_count = len(v2_data.get("patterns", []))

    if v1_count != v2_count:
        issues.append(f"Pattern count mismatch: v1={v1_count}, v2={v2_count}")

    # Check each pattern has keywords
    empty_keywords = []
    for p in v2_data.get("patterns", []):
        if not p.get("keywords"):
            empty_keywords.append(p.get("id"))

    if empty_keywords:
        issues.append(f"Patterns with no keywords: {empty_keywords[:5]}...")

    # Check type mapping
    type_mismatches = []
    for v1_p, v2_p in zip(
        v1_data.get("patterns", []), v2_data.get("patterns", [])
    ):
        v1_type = v1_p.get("type", "")
        v2_type = v2_p.get("type", "")

        expected_v2 = "good" if v1_type == "good_pattern" else "bad"
        if v2_type != expected_v2:
            type_mismatches.append(v2_p.get("id"))

    if type_mismatches:
        issues.append(f"Type mismatches: {type_mismatches[:5]}...")

    return {
        "valid": len(issues) == 0,
        "v1_count": v1_count,
        "v2_count": v2_count,
        "issues": issues,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pattern_migrator.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(
        ".json", "_v2.json"
    )

    print(f"Migrating {input_file} -> {output_file}")
    result = migrate_patterns_file(input_file, output_file)
    print(json.dumps(result, indent=2))

    if result["status"] == "success":
        print("\nValidating migration...")
        validation = validate_migration(input_file, output_file)
        print(json.dumps(validation, indent=2))
