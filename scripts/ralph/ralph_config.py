"""
Shared configuration constants for Ralph V2 Dual-Mode Evaluation.

Consolidates configuration to avoid duplication across modules.
"""

# Gap evaluation thresholds
# The gap measures (expensive_mode_score - cheap_mode_score) on a 1-5 scale.
# A gap of 0 means perfect calibration between expensive (LLM) and cheap (pattern) modes.
GAP_TARGET = 0.5  # Maximum acceptable gap for convergence (0.5 = 10% of 5-point scale)

# Convergence detection parameters
CONVERGENCE_WINDOW = 3  # Number of recent iterations to check for convergence
DIVERGENCE_THRESHOLD = 0.3  # Gap increase that triggers divergence warning
MIN_ITERATIONS_FOR_CONVERGENCE = 5  # Minimum iterations before declaring convergence

# Pattern learning thresholds
# Patterns are validated over multiple stories before committing to the pattern library
MIN_STORIES_TO_COMMIT = 10  # Minimum stories a pattern must match before commitment
MIN_ACCURACY_TO_COMMIT = 0.7  # Minimum accuracy (70%) required to commit a pattern
MIN_STORIES_TO_REJECT = 5  # Minimum stories before rejecting a pattern
MAX_ACCURACY_TO_REJECT = 0.3  # Maximum accuracy (30%) to reject a pattern

# Pattern matching thresholds
# Prediction correctness thresholds on 1-5 gestalt scale
GOOD_PATTERN_THRESHOLD = 4.0  # Good patterns should predict high scores (>=4)
BAD_PATTERN_THRESHOLD = 3.0  # Bad patterns should predict low scores (<=3)
DUPLICATE_OVERLAP_THRESHOLD = 0.7  # 70% keyword overlap to consider patterns duplicate
