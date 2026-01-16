"""
Convergence Monitor for Ralph V2 Dual-Mode Evaluation.

Implements:
1. Divergence detection - identifies when gap is increasing
2. Automatic recovery actions - suggests or takes corrective steps
3. Convergence proof - confirms when gap is consistently within target
"""

import json
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

from models import (
    ConvergenceCheck,
    DivergenceCheck,
    IterationMetrics,
)


# Import shared configuration
from ralph_config import (
    GAP_TARGET,
    CONVERGENCE_WINDOW,
    DIVERGENCE_THRESHOLD,
    MIN_ITERATIONS_FOR_CONVERGENCE,
)


class ConvergenceMonitor:
    """
    Monitors gap trends and detects convergence/divergence.

    The monitor tracks:
    1. Gap history over iterations
    2. Gap trend (improving, stable, diverging)
    3. Convergence criteria fulfillment
    """

    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.history = self._load_history()

    def _load_history(self) -> list[IterationMetrics]:
        """Load iteration history."""
        if not self.history_path.exists():
            return []

        with open(self.history_path) as f:
            data = json.load(f)

        return [IterationMetrics(**m) for m in data.get("iterations", [])]

    def _save_history(self):
        """Save iteration history."""
        with open(self.history_path, "w") as f:
            json.dump(
                {
                    "last_updated": datetime.now().isoformat(),
                    "iterations": [m.model_dump(mode="json") for m in self.history],
                },
                f,
                indent=2,
                default=str,
            )

    def record_iteration(
        self,
        iteration: int,
        expensive_avg: float,
        cheap_avg: float,
        pattern_count: int,
        provisional_patterns: int,
        patterns_committed: int,
        patterns_rejected: int,
        story_ids: list[str],
    ) -> IterationMetrics:
        """
        Record metrics for an iteration.

        Calculates gap and gap_delta from previous iteration.
        """
        gap = expensive_avg - cheap_avg

        # Calculate gap_delta from previous iteration
        gap_delta = 0.0
        if self.history:
            prev_gap = self.history[-1].gap
            gap_delta = gap - prev_gap

        metrics = IterationMetrics(
            iteration=iteration,
            timestamp=datetime.now(),
            expensive_avg=round(expensive_avg, 2),
            cheap_avg=round(cheap_avg, 2),
            gap=round(gap, 2),
            gap_delta=round(gap_delta, 2),
            pattern_count=pattern_count,
            provisional_patterns=provisional_patterns,
            patterns_committed=patterns_committed,
            patterns_rejected=patterns_rejected,
            story_ids=story_ids,
        )

        self.history.append(metrics)
        self._save_history()

        return metrics

    def check_divergence(self) -> DivergenceCheck:
        """
        Check if the gap is diverging (getting worse).

        Divergence is detected when:
        1. Gap has increased for 2+ consecutive iterations
        2. Gap increase exceeds threshold
        """
        if len(self.history) < 2:
            return DivergenceCheck(diverging=False)

        recent = self.history[-3:] if len(self.history) >= 3 else self.history

        # Check for consecutive increases
        consecutive_increases = 0
        total_increase = 0.0

        for i in range(1, len(recent)):
            if recent[i].gap > recent[i - 1].gap:
                consecutive_increases += 1
                total_increase += recent[i].gap - recent[i - 1].gap
            else:
                consecutive_increases = 0
                total_increase = 0.0

        if consecutive_increases >= 2 and total_increase > DIVERGENCE_THRESHOLD:
            # Diagnose the problem
            diagnosis, action = self._diagnose_divergence()

            return DivergenceCheck(
                diverging=True,
                reason=f"Gap increased by {total_increase:.2f} over {consecutive_increases} iterations",
                diagnosis=diagnosis,
                action=action,
            )

        # Check for single large increase
        if self.history[-1].gap_delta > DIVERGENCE_THRESHOLD:
            diagnosis, action = self._diagnose_divergence()

            return DivergenceCheck(
                diverging=True,
                reason=f"Gap spiked by {self.history[-1].gap_delta:.2f} in last iteration",
                diagnosis=diagnosis,
                action=action,
            )

        return DivergenceCheck(diverging=False)

    def _diagnose_divergence(self) -> tuple[str, str]:
        """
        Diagnose why divergence is happening and suggest action.

        Returns (diagnosis, recommended_action).
        """
        if not self.history:
            return "Insufficient data", "Continue iterations"

        latest = self.history[-1]

        # Check if cheap is over-predicting (cheap > expensive)
        if latest.cheap_avg > latest.expensive_avg:
            return (
                "Cheap mode is over-predicting quality (rating stories higher than LLM)",
                "Prune overly permissive good patterns or add more bad patterns",
            )

        # Check if cheap is under-predicting (expensive >> cheap)
        if latest.expensive_avg - latest.cheap_avg > 1.0:
            return (
                "Cheap mode is under-predicting quality (missing good patterns)",
                "Review expensive mode feedback for good patterns to add",
            )

        # Check pattern churn
        if latest.patterns_committed > 5 or latest.patterns_rejected > 5:
            return (
                "High pattern churn may be causing instability",
                "Increase pattern validation thresholds or reduce proposal rate",
            )

        # Default
        return (
            "Gap is increasing without clear cause",
            "Review recent pattern changes and revert if necessary",
        )

    def check_convergence(self) -> ConvergenceCheck:
        """
        Check if the gap has converged (consistently within target).

        Convergence criteria:
        1. At least MIN_ITERATIONS_FOR_CONVERGENCE iterations completed
        2. Last CONVERGENCE_WINDOW iterations all have gap <= GAP_TARGET
        3. Gap is stable (low variance in last CONVERGENCE_WINDOW)
        """
        checks = {
            "min_iterations": False,
            "all_within_target": False,
            "stable_gap": False,
        }

        if len(self.history) < MIN_ITERATIONS_FOR_CONVERGENCE:
            return ConvergenceCheck(
                converged=False,
                checks=checks,
                proof={
                    "reason": f"Only {len(self.history)} iterations (need {MIN_ITERATIONS_FOR_CONVERGENCE})"
                },
            )

        checks["min_iterations"] = True

        # Check last CONVERGENCE_WINDOW iterations
        window = self.history[-CONVERGENCE_WINDOW:]
        window_gaps = [m.gap for m in window]

        # All within target?
        all_within = all(abs(g) <= GAP_TARGET for g in window_gaps)
        checks["all_within_target"] = all_within

        # Stable gap? (low variance)
        if len(window_gaps) >= 2:
            gap_stdev = stdev(window_gaps)
            stable = gap_stdev < 0.2  # Low variance threshold
            checks["stable_gap"] = stable
        else:
            checks["stable_gap"] = True  # Can't compute stdev with 1 value

        converged = all(checks.values())

        proof = {
            "window_size": CONVERGENCE_WINDOW,
            "window_gaps": window_gaps,
            "avg_gap": round(mean(window_gaps), 2),
            "gap_stdev": round(stdev(window_gaps), 2) if len(window_gaps) >= 2 else 0,
            "gap_target": GAP_TARGET,
        }

        return ConvergenceCheck(
            converged=converged,
            checks=checks,
            proof=proof,
        )

    def get_trend(self) -> str:
        """
        Get the current gap trend.

        Returns one of: "improving", "stable", "diverging", "insufficient_data"
        """
        if len(self.history) < 3:
            return "insufficient_data"

        recent_deltas = [m.gap_delta for m in self.history[-3:]]
        avg_delta = mean(recent_deltas)

        if avg_delta < -0.1:
            return "improving"
        elif avg_delta > 0.1:
            return "diverging"
        else:
            return "stable"

    def get_status(self) -> dict:
        """Get current monitor status."""
        if not self.history:
            return {
                "iterations": 0,
                "current_gap": None,
                "trend": "insufficient_data",
                "converged": False,
            }

        latest = self.history[-1]

        return {
            "iterations": len(self.history),
            "current_gap": latest.gap,
            "expensive_avg": latest.expensive_avg,
            "cheap_avg": latest.cheap_avg,
            "trend": self.get_trend(),
            "converged": self.check_convergence().converged,
        }

    def suggest_action(self) -> Optional[str]:
        """
        Suggest next action based on current state.

        Returns action string or None if no action needed.
        """
        divergence = self.check_divergence()
        if divergence.diverging:
            return f"DIVERGENCE DETECTED: {divergence.action}"

        convergence = self.check_convergence()
        if convergence.converged:
            return "CONVERGENCE ACHIEVED: Gap is stable within target. Optimization complete."

        trend = self.get_trend()
        if trend == "improving":
            return None  # Keep going, things are working

        if trend == "stable" and len(self.history) >= MIN_ITERATIONS_FOR_CONVERGENCE:
            latest = self.history[-1]
            if abs(latest.gap) > GAP_TARGET:
                return "Gap is stable but above target. Consider adjusting pattern weights or adding new patterns."

        return None