"""
Pattern Learning Loop for Ralph V2 Dual-Mode Evaluation.

Implements the provisional pattern system:
1. Propose new patterns from expensive mode feedback
2. Track pattern accuracy over multiple stories
3. Commit patterns that prove themselves (>=70% accuracy over 10+ stories)
4. Reject patterns that don't help (<30% accuracy over 5+ stories)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import (
    DualModeResult,
    ExpensiveModeResult,
    LearnedPatternsV2,
    PatternProposal,
    PatternV2,
)
from pattern_migrator import extract_keywords

# Import shared configuration
from ralph_config import (
    MIN_STORIES_TO_COMMIT,
    MIN_ACCURACY_TO_COMMIT,
    MIN_STORIES_TO_REJECT,
    MAX_ACCURACY_TO_REJECT,
    GOOD_PATTERN_THRESHOLD,
    BAD_PATTERN_THRESHOLD,
    DUPLICATE_OVERLAP_THRESHOLD,
)


class PatternLearner:
    """
    Learns patterns from expensive mode feedback and calibrates cheap mode.

    The learning loop:
    1. After each dual-mode evaluation, analyze gaps
    2. If expensive mode found issues that cheap mode missed, propose patterns
    3. Track provisional patterns over multiple iterations
    4. Commit patterns that prove accurate, reject those that don't
    """

    def __init__(self, patterns_path: Path):
        self.patterns_path = patterns_path
        self.proposals_path = patterns_path.with_suffix(".proposals.json")
        self.patterns = self._load_patterns()
        self.proposals = self._load_proposals()

    def _load_patterns(self) -> LearnedPatternsV2:
        """Load current v2 patterns."""
        if not self.patterns_path.exists():
            return LearnedPatternsV2(
                version="2.0",
                last_updated=datetime.now(),
                patterns=[],
                calibration_history=[],
            )

        with open(self.patterns_path) as f:
            data = json.load(f)

        return LearnedPatternsV2(**data)

    def _load_proposals(self) -> list[PatternProposal]:
        """Load provisional pattern proposals."""
        if not self.proposals_path.exists():
            return []

        with open(self.proposals_path) as f:
            data = json.load(f)

        return [PatternProposal(**p) for p in data.get("proposals", [])]

    def _save_patterns(self):
        """Save patterns to file."""
        self.patterns.last_updated = datetime.now()
        with open(self.patterns_path, "w") as f:
            json.dump(self.patterns.model_dump(mode="json"), f, indent=2, default=str)

    def _save_proposals(self):
        """Save provisional proposals to file."""
        with open(self.proposals_path, "w") as f:
            json.dump(
                {
                    "last_updated": datetime.now().isoformat(),
                    "proposals": [p.model_dump(mode="json") for p in self.proposals],
                },
                f,
                indent=2,
                default=str,
            )

    def propose_patterns_from_feedback(
        self,
        dual_results: list[DualModeResult],
        iteration: int,
    ) -> list[PatternProposal]:
        """
        Analyze dual-mode results and propose new patterns.

        Patterns are proposed when:
        1. There's a significant gap (expensive >> cheap or expensive << cheap)
        2. Expensive mode identified specific strengths/weaknesses
        3. The feedback contains actionable keywords
        """
        new_proposals = []

        for result in dual_results:
            gap = result.gap

            # Only analyze significant gaps
            if abs(gap) < 0.5:
                continue

            expensive = result.expensive

            if gap > 0:
                # Expensive rated higher than cheap - cheap missed good patterns
                # Extract from strengths
                for strength in expensive.strengths:
                    pattern = self._create_pattern_from_feedback(
                        feedback=strength,
                        pattern_type="good",
                        story_id=result.story_id,
                        iteration=iteration,
                    )
                    if pattern:
                        new_proposals.append(pattern)
            else:
                # Expensive rated lower than cheap - cheap missed bad patterns
                # Extract from weaknesses
                for weakness in expensive.weaknesses:
                    pattern = self._create_pattern_from_feedback(
                        feedback=weakness,
                        pattern_type="bad",
                        story_id=result.story_id,
                        iteration=iteration,
                    )
                    if pattern:
                        new_proposals.append(pattern)

        # Add to proposals list (deduplicated)
        for proposal in new_proposals:
            if not self._is_duplicate_proposal(proposal):
                self.proposals.append(proposal)

        self._save_proposals()
        return new_proposals

    def _create_pattern_from_feedback(
        self,
        feedback: str,
        pattern_type: str,
        story_id: str,
        iteration: int,
    ) -> Optional[PatternProposal]:
        """Create a pattern proposal from feedback text."""
        # Extract keywords from feedback
        keywords = extract_keywords(feedback)

        # Filter out very generic keywords
        keywords = [k for k in keywords if len(k) >= 3 and k not in {"the", "and", "for"}]

        # Need at least 2 meaningful keywords
        if len(keywords) < 2:
            return None

        # Generate unique ID
        pattern_id = f"prop_{iteration:03d}_{len(self.proposals):03d}"

        pattern = PatternV2(
            id=pattern_id,
            type=pattern_type,
            description=feedback[:200],  # Truncate if too long
            keywords=keywords[:10],  # Max 10 keywords
            weight=1.0,
            source=f"learning_loop:story_{story_id}",
            discovered_at=datetime.now(),
            status="provisional",
        )

        return PatternProposal(
            id=pattern_id,
            status="provisional",
            pattern=pattern,
            proposed_at=iteration,
            stories_tested=0,
            correct_predictions=0,
        )

    def _is_duplicate_proposal(self, new_proposal: PatternProposal) -> bool:
        """Check if a similar proposal already exists."""
        new_keywords = set(new_proposal.pattern.keywords)

        for existing in self.proposals:
            existing_keywords = set(existing.pattern.keywords)
            # Consider duplicate if keyword overlap exceeds threshold
            overlap = len(new_keywords & existing_keywords)
            if overlap / max(len(new_keywords), 1) > DUPLICATE_OVERLAP_THRESHOLD:
                return True

        # Also check against committed patterns
        for pattern in self.patterns.patterns:
            existing_keywords = set(pattern.keywords)
            overlap = len(new_keywords & existing_keywords)
            if overlap / max(len(new_keywords), 1) > DUPLICATE_OVERLAP_THRESHOLD:
                return True

        return False

    def _is_pattern_duplicate_of_active(self, pattern: PatternV2) -> bool:
        """Check if a pattern duplicates an already committed active pattern."""
        pattern_keywords = set(pattern.keywords)

        for existing in self.patterns.patterns:
            if existing.status != "active":
                continue
            existing_keywords = set(existing.keywords)
            # Consider duplicate if keyword overlap exceeds threshold
            overlap = len(pattern_keywords & existing_keywords)
            if overlap / max(len(pattern_keywords), 1) > DUPLICATE_OVERLAP_THRESHOLD:
                return True

        return False

    def evaluate_proposals(
        self,
        dual_results: list[DualModeResult],
    ) -> dict:
        """
        Evaluate provisional proposals against new dual-mode results.

        For each proposal:
        1. Check if its keywords match the story
        2. If matched, check if the prediction was correct (gap direction)
        3. Update accuracy metrics
        """
        evaluation_stats = {
            "proposals_evaluated": 0,
            "correct_predictions": 0,
            "incorrect_predictions": 0,
        }

        for proposal in self.proposals:
            if proposal.status != "provisional":
                continue

            for result in dual_results:
                # Check if proposal keywords match story
                story_text = self._get_story_text(result)
                if not self._pattern_matches_text(proposal.pattern, story_text):
                    continue

                proposal.stories_tested += 1
                evaluation_stats["proposals_evaluated"] += 1

                # Check if prediction was correct
                # Good pattern should fire when expensive rates high
                # Bad pattern should fire when expensive rates low
                is_correct = self._check_prediction_correct(
                    proposal.pattern.type,
                    result.expensive.gestalt,
                    result.gap,
                )

                if is_correct:
                    proposal.correct_predictions += 1
                    evaluation_stats["correct_predictions"] += 1
                else:
                    evaluation_stats["incorrect_predictions"] += 1

        self._save_proposals()
        return evaluation_stats

    def _get_story_text(self, result: DualModeResult) -> str:
        """Extract text from dual mode result for pattern matching."""
        expensive = result.expensive
        return " ".join([
            expensive.reasoning,
            " ".join(expensive.strengths),
            " ".join(expensive.weaknesses),
        ]).lower()

    def _pattern_matches_text(self, pattern: PatternV2, text: str) -> bool:
        """Check if pattern keywords match text."""
        if not pattern.keywords:
            return False

        keywords_present = sum(1 for kw in pattern.keywords if kw.lower() in text)
        threshold = max(2, len(pattern.keywords) // 2)
        return keywords_present >= threshold

    def _check_prediction_correct(
        self,
        pattern_type: str,
        expensive_gestalt: float,
        gap: float,
    ) -> bool:
        """
        Check if the pattern's prediction was correct.

        For good patterns: should correlate with high expensive gestalt (>= threshold)
        For bad patterns: should correlate with low expensive gestalt (<= threshold)

        Thresholds are on a 1-5 gestalt scale.
        """
        if pattern_type == "good":
            # Good pattern is correct if expensive rated high
            return expensive_gestalt >= GOOD_PATTERN_THRESHOLD
        else:
            # Bad pattern is correct if expensive rated low
            return expensive_gestalt <= BAD_PATTERN_THRESHOLD

    def process_proposals(self, iteration: int) -> dict:
        """
        Process proposals: commit proven ones, reject failed ones.

        Returns stats on what was committed/rejected.
        """
        stats = {
            "committed": [],
            "rejected": [],
            "still_provisional": 0,
        }

        remaining_proposals = []

        for proposal in self.proposals:
            if proposal.status != "provisional":
                remaining_proposals.append(proposal)
                continue

            if proposal.should_commit():
                # Check for duplicates before committing (pattern may now overlap with recently committed)
                if self._is_pattern_duplicate_of_active(proposal.pattern):
                    # Skip commitment, treat as redundant
                    proposal.status = "rejected"
                    stats["rejected"].append(proposal.id)
                    continue

                # Pattern has proven itself - commit to main patterns
                proposal.pattern.status = "active"
                proposal.pattern.accuracy = proposal.accuracy
                proposal.pattern.times_fired = proposal.stories_tested
                self.patterns.patterns.append(proposal.pattern)
                proposal.status = "validated"
                stats["committed"].append(proposal.id)

            elif proposal.should_reject():
                # Pattern is not helping - reject it
                proposal.status = "rejected"
                stats["rejected"].append(proposal.id)

            else:
                # Still provisional - keep tracking
                stats["still_provisional"] += 1
                remaining_proposals.append(proposal)

        self.proposals = remaining_proposals
        self._save_proposals()
        self._save_patterns()

        # Log to calibration history
        self.patterns.calibration_history.append({
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "committed": stats["committed"],
            "rejected": stats["rejected"],
            "still_provisional": stats["still_provisional"],
            "total_patterns": len(self.patterns.patterns),
        })
        self._save_patterns()

        return stats

    def get_status(self) -> dict:
        """Get current learner status."""
        active_patterns = [p for p in self.patterns.patterns if p.status == "active"]
        provisional = [p for p in self.proposals if p.status == "provisional"]

        return {
            "total_patterns": len(self.patterns.patterns),
            "active_patterns": len(active_patterns),
            "provisional_proposals": len(provisional),
            "good_patterns": sum(1 for p in active_patterns if p.type == "good"),
            "bad_patterns": sum(1 for p in active_patterns if p.type == "bad"),
            "calibration_iterations": len(self.patterns.calibration_history),
        }


def run_learning_iteration(
    patterns_path: Path,
    dual_results: list[DualModeResult],
    iteration: int,
) -> dict:
    """
    Run a complete learning iteration.

    1. Evaluate existing proposals against new results
    2. Propose new patterns from feedback
    3. Process proposals (commit/reject)
    4. Return stats

    Returns dict with learning stats.
    """
    learner = PatternLearner(patterns_path)

    # 1. Evaluate existing proposals
    eval_stats = learner.evaluate_proposals(dual_results)

    # 2. Propose new patterns from feedback
    new_proposals = learner.propose_patterns_from_feedback(dual_results, iteration)

    # 3. Process proposals (commit/reject proven patterns)
    process_stats = learner.process_proposals(iteration)

    # 4. Get overall status
    status = learner.get_status()

    return {
        "iteration": iteration,
        "evaluation": eval_stats,
        "new_proposals": len(new_proposals),
        "committed": process_stats["committed"],
        "rejected": process_stats["rejected"],
        "still_provisional": process_stats["still_provisional"],
        "status": status,
    }
