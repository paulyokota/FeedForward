"""
Cheap mode evaluation using patterns only - no LLM calls.

Evaluates stories against learned patterns to produce a gestalt score
comparable to expensive (LLM) mode evaluation.

Glossary:
    gestalt (float): Overall story quality score on 1-5 scale.
                     Combines multiple scoring dimensions into a single rating.
                     1=Poor, 5=Excellent, comparable to LLM evaluation.

Example usage:
    evaluator = CheapModeEvaluator("patterns_v2.json")
    result = evaluator.evaluate_story(story)
    print(f"Gestalt: {result.gestalt}, Reasons: {result.reasons}")
"""

import json
import re
from pathlib import Path

from models import (
    CheapModeResult,
    ComponentHealthStatus,
    LearnedPatternsV2,
    PatternV2,
    Story,
)

# =============================================================================
# Scoring Configuration
# =============================================================================
# These weights were chosen empirically. Adjust via calibration if needed.

# Title scoring
TITLE_LENGTH_WEIGHT = 0.5  # Bonus for titles <= 80 chars
TITLE_ACTION_WEIGHT = 0.5  # Bonus for action-oriented titles

# Pattern scoring
PATTERN_GOOD_BONUS = 0.1  # Small bonus per good pattern match
PATTERN_BAD_PENALTY = 0.2  # Larger penalty to discourage anti-patterns

# AC count thresholds (based on INVEST story standard)
AC_IDEAL_MIN, AC_IDEAL_MAX = 3, 7
AC_ACCEPTABLE_MAX = 10

# Scope thresholds
SCOPE_DESC_MIN, SCOPE_DESC_MAX = 100, 1000
SCOPE_DESC_TOO_LARGE = 2000

# Known repositories for technical area validation
KNOWN_REPOS = ["aero", "tack", "charlotte", "ghostwriter", "zuck", "gandalf"]


class CheapModeEvaluator:
    """
    Evaluates stories using only patterns and heuristics.

    No LLM calls, no external APIs - pure pattern matching.
    """

    def __init__(self, patterns_path: str | Path):
        self.patterns_path = Path(patterns_path)
        self.patterns = self._load_patterns()
        self.good_patterns = [p for p in self.patterns if p.type == "good"]
        self.bad_patterns = [p for p in self.patterns if p.type == "bad"]

    def _load_patterns(self) -> list[PatternV2]:
        """Load patterns from JSON file."""
        if not self.patterns_path.exists():
            return []

        with open(self.patterns_path) as f:
            data = json.load(f)

        # Handle both v1 and v2 formats
        if data.get("version", "1.0").startswith("2"):
            parsed = LearnedPatternsV2(**data)
            # Filter to active patterns with at least one keyword
            return [
                p for p in parsed.patterns
                if p.status == "active" and len(p.keywords) > 0
            ]
        else:
            # V1 format - return empty, need migration first
            return []

    def evaluate_story(self, story: Story) -> CheapModeResult:
        """
        Score a story using only patterns and heuristics.

        Scoring components (0-1 each, normalized to 1-5 gestalt):
        1. Title quality
        2. Acceptance criteria quality
        3. Technical specificity
        4. User value
        5. Scope appropriateness
        6. Pattern matching (good patterns matched, bad patterns avoided)
        """
        score = 0.0
        reasons = []
        patterns_matched = []
        patterns_violated = []

        # 1. Title quality (0-1)
        title_score, title_reasons = self._check_title_quality(story.title)
        score += title_score
        reasons.extend(title_reasons)

        # 2. Acceptance criteria (0-1)
        ac_score, ac_reasons = self._check_acceptance_criteria(
            story.acceptance_criteria
        )
        score += ac_score
        reasons.extend(ac_reasons)

        # 3. Technical specificity (0-1)
        tech_score, tech_reasons = self._check_technical_area(story.technical_area)
        score += tech_score
        reasons.extend(tech_reasons)

        # 4. User value (0-1)
        value_score, value_reasons = self._check_user_value(story.description)
        score += value_score
        reasons.extend(value_reasons)

        # 5. Scope check (0-1)
        scope_score, scope_reasons = self._check_scope(story)
        score += scope_score
        reasons.extend(scope_reasons)

        # 6. Pattern matching (bonus/penalty)
        pattern_score, matched, violated = self._check_patterns(story)
        score += pattern_score
        patterns_matched = matched
        patterns_violated = violated
        if matched:
            reasons.append(f"matched_{len(matched)}_good_patterns")
        if violated:
            reasons.append(f"violated_{len(violated)}_bad_patterns")

        # Clamp raw score to 0-5
        raw_score = max(0.0, min(5.0, score))

        # Normalize to 1-5 gestalt scale
        gestalt = 1.0 + (raw_score / 5.0) * 4.0
        gestalt = max(1.0, min(5.0, gestalt))

        return CheapModeResult(
            story_id=story.id,
            gestalt=round(gestalt, 2),
            raw_score=round(raw_score, 2),
            reasons=reasons,
            patterns_matched=patterns_matched,
            patterns_violated=patterns_violated,
        )

    def _check_title_quality(self, title: str) -> tuple[float, list[str]]:
        """
        Title should be < 80 chars, action-oriented.

        Returns (score 0-1, reasons).
        """
        if not title:
            return 0.0, ["missing_title"]

        reasons = []
        score = 0.0

        # Length check
        if len(title) <= 80:
            score += 0.5
            reasons.append("good_title_length")
        else:
            reasons.append("title_too_long")

        # Action-oriented check
        action_words = [
            "add",
            "fix",
            "update",
            "improve",
            "enable",
            "implement",
            "create",
            "remove",
            "refactor",
            "optimize",
        ]
        if any(title.lower().startswith(w) for w in action_words):
            score += 0.5
            reasons.append("action_oriented_title")

        return score, reasons

    def _check_acceptance_criteria(
        self, acs: list[str]
    ) -> tuple[float, list[str]]:
        """
        3-7 ACs is ideal, each should be testable.

        Returns (score 0-1, reasons).
        """
        if not acs:
            return 0.0, ["no_acceptance_criteria"]

        reasons = []
        count = len(acs)

        # Count scoring
        if count < 2:
            score = 0.2
            reasons.append("too_few_acs")
        elif count > 10:
            score = 0.3
            reasons.append("too_many_acs")
        elif 3 <= count <= 7:
            score = 1.0
            reasons.append("ideal_ac_count")
        else:
            score = 0.6
            reasons.append("acceptable_ac_count")

        # Check for testability keywords
        testable_keywords = [
            "should",
            "must",
            "when",
            "given",
            "then",
            "verify",
            "confirm",
            "displays",
            "returns",
        ]
        testable_count = sum(
            1
            for ac in acs
            if any(kw in ac.lower() for kw in testable_keywords)
        )
        if testable_count >= len(acs) * 0.5:
            reasons.append("testable_acs")

        return score, reasons

    def _check_technical_area(
        self, tech_area: str | None
    ) -> tuple[float, list[str]]:
        """
        Validate tech area mentions specific code locations.

        Returns (score 0-1, reasons).
        """
        if not tech_area:
            return 0.0, ["no_technical_area"]

        reasons = []
        score = 0.0

        # Check for known repo prefixes
        if any(repo in tech_area.lower() for repo in KNOWN_REPOS):
            score += 0.5
            reasons.append("known_repo_mentioned")

        # Check for file-like patterns
        if re.search(r"\w+/\w+\.\w{2,4}", tech_area):
            score += 0.3
            reasons.append("file_path_mentioned")

        # Check for service/component mentions
        component_patterns = [
            r"service",
            r"handler",
            r"component",
            r"controller",
            r"model",
            r"api",
        ]
        if any(re.search(p, tech_area, re.IGNORECASE) for p in component_patterns):
            score += 0.2
            reasons.append("component_mentioned")

        return min(1.0, score), reasons

    def _check_user_value(self, description: str) -> tuple[float, list[str]]:
        """
        Description should mention user benefit.

        Returns (score 0-1, reasons).
        """
        if not description:
            return 0.0, ["no_description"]

        reasons = []
        score = 0.0

        # User-focused phrases
        value_phrases = [
            "user can",
            "users will",
            "allows",
            "enables",
            "improves",
            "reduces",
            "saves",
            "prevents",
            "customers",
            "when a user",
            "so that",
            "frustrated",
            "pain point",
        ]
        desc_lower = description.lower()
        matched_phrases = [p for p in value_phrases if p in desc_lower]

        if matched_phrases:
            score = min(1.0, len(matched_phrases) * 0.3)
            reasons.append("user_value_stated")

        return score, reasons

    def _check_scope(self, story: Story) -> tuple[float, list[str]]:
        """
        Check if scope seems appropriate (not too big/small).

        Returns (score 0-1, reasons).
        """
        reasons = []
        score = 0.0

        desc_len = len(story.description) if story.description else 0
        ac_count = len(story.acceptance_criteria)

        # Too small
        if desc_len < 50 or ac_count < 2:
            reasons.append("scope_too_small")
            return 0.3, reasons

        # Too big
        if desc_len > 2000 or ac_count > 10:
            reasons.append("scope_too_large")
            return 0.3, reasons

        # Goldilocks zone
        if 100 <= desc_len <= 1000 and 3 <= ac_count <= 7:
            score = 1.0
            reasons.append("appropriate_scope")
        else:
            score = 0.7
            reasons.append("acceptable_scope")

        return score, reasons

    def _check_patterns(
        self, story: Story
    ) -> tuple[float, list[str], list[str]]:
        """
        Check story against learned patterns.

        Returns (score adjustment, matched good patterns, violated bad patterns).
        """
        matched = []
        violated = []
        score_adjustment = 0.0

        # Combine all story text for matching
        story_text = " ".join(
            [
                story.title,
                story.description,
                " ".join(story.acceptance_criteria),
                story.technical_area or "",
            ]
        ).lower()

        # Check good patterns
        for pattern in self.good_patterns:
            if self._pattern_matches(pattern, story_text):
                matched.append(pattern.id)
                score_adjustment += pattern.weight * PATTERN_GOOD_BONUS

        # Check bad patterns
        for pattern in self.bad_patterns:
            if self._pattern_matches(pattern, story_text):
                violated.append(pattern.id)
                score_adjustment -= pattern.weight * PATTERN_BAD_PENALTY

        return score_adjustment, matched, violated

    def _pattern_matches(self, pattern: PatternV2, text: str) -> bool:
        """
        Check if a pattern matches the given text.

        Matching strategy:
        - Require at least 2 keywords to avoid false positives from single-word matches
        - OR require 50% of pattern keywords for patterns with many keywords
        - Keywords are already lowercase from migration, text is lowercased by caller
        """
        if not pattern.keywords:
            return False  # Empty keywords can never match

        # Check if any keyword is present (keywords already lowercase from migration)
        keywords_present = sum(1 for kw in pattern.keywords if kw in text)

        # Require at least 2 keywords or 50% of keywords to match
        # Use integer division to avoid float comparison issues
        threshold = max(2, len(pattern.keywords) // 2)
        return keywords_present >= threshold

    def get_health_status(self) -> ComponentHealthStatus:
        """Report health status of the evaluator."""
        flags = []

        if not self.patterns:
            flags.append("no_patterns_loaded")

        if len(self.good_patterns) == 0:
            flags.append("no_good_patterns")

        if len(self.bad_patterns) == 0:
            flags.append("no_bad_patterns")

        return ComponentHealthStatus(
            healthy=len(flags) == 0,
            flags=flags,
            details={
                "total_patterns": len(self.patterns),
                "good_patterns": len(self.good_patterns),
                "bad_patterns": len(self.bad_patterns),
                "patterns_path": str(self.patterns_path),
            },
        )


def evaluate_stories_cheap(
    stories: list[Story], patterns_path: str | Path
) -> tuple[list[CheapModeResult], ComponentHealthStatus]:
    """
    Evaluate multiple stories using cheap mode.

    Returns (results, health_status).
    """
    evaluator = CheapModeEvaluator(patterns_path)
    health = evaluator.get_health_status()

    results = [evaluator.evaluate_story(story) for story in stories]

    return results, health


def compute_cheap_metrics(results: list[CheapModeResult]) -> dict:
    """Compute aggregate metrics from cheap mode results."""
    if not results:
        return {
            "gestalt_avg": 0.0,
            "story_count": 0,
        }

    gestalts = [r.gestalt for r in results]

    return {
        "gestalt_avg": round(sum(gestalts) / len(gestalts), 2),
        "gestalt_min": min(gestalts),
        "gestalt_max": max(gestalts),
        "story_count": len(results),
        "patterns_matched_total": sum(len(r.patterns_matched) for r in results),
        "patterns_violated_total": sum(len(r.patterns_violated) for r in results),
    }
