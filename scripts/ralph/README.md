# Ralph V2 - Dual-Mode Story Evaluation

Pattern-based story quality evaluation that converges with LLM judgment.

## Overview

Ralph evaluates story quality using two modes:

- **Cheap mode**: Pattern matching (fast, no LLM calls, ~10ms per story)
- **Expensive mode**: LLM evaluation (slow, accurate, ~2s per story)

The goal is to calibrate cheap mode until its gestalt scores match expensive mode within 0.5 points.

## Files

| File                      | Purpose                                         |
| ------------------------- | ----------------------------------------------- |
| `models.py`               | Pydantic schemas for patterns, stories, results |
| `cheap_mode_evaluator.py` | Pattern-based scoring engine                    |
| `pattern_migrator.py`     | Convert v1 patterns to v2 keyword format        |
| `tests/test_phase1.py`    | Unit tests for all components                   |

## Quick Start

```python
from models import Story
from cheap_mode_evaluator import CheapModeEvaluator

# Load evaluator with patterns
evaluator = CheapModeEvaluator("learned_patterns_v2.json")

# Evaluate a story
story = Story(
    id="story_001",
    title="Add Pinterest OAuth refresh",
    description="Enable automatic token refresh for Pinterest integration",
    acceptance_criteria=[
        "Token refreshes automatically before expiry",
        "No user action required",
        "Refresh failures are logged",
    ],
    technical_area="aero/services/oauth/pinterest.py",
)

result = evaluator.evaluate_story(story)
print(f"Gestalt: {result.gestalt}")  # 1.0-5.0 scale
print(f"Reasons: {result.reasons}")
print(f"Patterns matched: {result.patterns_matched}")
```

## Pattern Migration

Convert existing v1 patterns to v2 format:

```bash
python pattern_migrator.py learned_patterns.json learned_patterns_v2.json
```

## Scoring Components

Cheap mode scores stories on 6 dimensions (0-1 each):

1. **Title quality** - Length and action-orientation
2. **Acceptance criteria** - Count and testability
3. **Technical specificity** - Known repos and file paths
4. **User value** - Presence of value statements
5. **Scope appropriateness** - Not too big/small
6. **Pattern matching** - Good patterns matched, bad patterns avoided

Final gestalt is normalized to 1-5 scale.

## Configuration

Scoring weights are defined at the top of `cheap_mode_evaluator.py`:

```python
PATTERN_GOOD_BONUS = 0.1   # Per good pattern match
PATTERN_BAD_PENALTY = 0.2  # Per bad pattern match
AC_IDEAL_MIN, AC_IDEAL_MAX = 3, 7
```

## Testing

```bash
cd scripts/ralph
python -m pytest tests/ -v
```
