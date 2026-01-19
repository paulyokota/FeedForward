# Ralph V2 Dual-Mode Evaluation Design

**Problem**: We optimize with expensive processes but deploy with cheap patterns. We never validate the cheap path works.

**Solution**: Run both modes every iteration, optimize for minimal gap.

---

## TL;DR

| Current State                                | Target State                                 |
| -------------------------------------------- | -------------------------------------------- |
| Expensive mode (LLM judge) optimizes stories | Both modes run every iteration               |
| Cheap mode (patterns) exists but untested    | Gap between modes tracked and minimized      |
| Completion = expensive score ≥ 4.0           | Completion = cheap score ≥ 4.0 AND gap ≤ 0.5 |
| 471 patterns accumulated, unused for scoring | Patterns power cheap mode evaluation         |

**Key insight**: If the cheap path can't match expensive path quality, the patterns we're learning aren't actually useful for production.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DUAL-MODE ITERATION                               │
│                                                                      │
│  ┌──────────────┐                      ┌──────────────┐             │
│  │  Test Data   │                      │  Test Data   │             │
│  └──────┬───────┘                      └──────┬───────┘             │
│         │                                     │                      │
│         ▼                                     ▼                      │
│  ┌──────────────┐                      ┌──────────────┐             │
│  │   EXPENSIVE  │                      │    CHEAP     │             │
│  │    MODE      │                      │    MODE      │             │
│  │              │                      │              │             │
│  │ - LLM Judge  │                      │ - Patterns   │             │
│  │ - Full eval  │                      │   only       │             │
│  │              │                      │ - Heuristics │             │
│  └──────┬───────┘                      └──────┬───────┘             │
│         │                                     │                      │
│         ▼                                     ▼                      │
│  ┌──────────────┐                      ┌──────────────┐             │
│  │  Score A     │                      │  Score B     │             │
│  │  (ground     │                      │  (practical  │             │
│  │   truth)     │                      │   mode)      │             │
│  └──────┬───────┘                      └──────┬───────┘             │
│         │                                     │                      │
│         └─────────────┬───────────────────────┘                      │
│                       │                                              │
│                       ▼                                              │
│              ┌─────────────────┐                                     │
│              │   GAP = A - B   │                                     │
│              └────────┬────────┘                                     │
│                       │                                              │
│         ┌─────────────┴─────────────┐                               │
│         ▼                           ▼                               │
│  ┌─────────────┐            ┌─────────────┐                         │
│  │ Gap > 0.5?  │───YES────▶ │ Analyze why │                         │
│  │             │            │ patterns    │                         │
│  └─────────────┘            │ missed      │                         │
│         │ NO                └──────┬──────┘                         │
│         ▼                          │                                │
│  ┌─────────────┐                   │                                │
│  │ B >= 4.0?   │                   │                                │
│  └──────┬──────┘                   │                                │
│         │ YES                      │                                │
│         ▼                          ▼                                │
│  ┌─────────────┐           ┌─────────────┐                          │
│  │  SUCCESS    │           │ Update      │                          │
│  │  (if stable │           │ patterns    │                          │
│  │   2+ iters) │           │ & continue  │                          │
│  └─────────────┘           └─────────────┘                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Completion Criteria (Revised)

OLD:

```
- Gestalt >= 4.0 (expensive mode only)
- No validation of pattern-based scoring
```

NEW:

```
- Score B >= 4.0 (CHEAP mode must be good enough alone)
- Gap (A - B) <= 0.5 (cheap tracks expensive)
- Stable for 2 consecutive iterations
- Min iterations still enforced
```

---

## Interface Contracts

All interfaces use Pydantic models for validation and documentation.

### Core Models

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime

# --- Pattern Models ---

class PatternV1(BaseModel):
    """Legacy pattern format (existing 471 patterns)."""
    type: Literal["good_pattern", "bad_pattern"]
    description: str
    example: str
    discovered_at: datetime
    source: str = "scoping_validation"


class PatternV2(BaseModel):
    """New pattern format for cheap mode evaluation."""
    id: str = Field(..., description="Unique pattern ID, e.g., 'p_001'")
    type: Literal["good", "bad"]
    description: str
    keywords: list[str] = Field(..., description="Extracted keywords for matching")
    weight: float = Field(default=1.0, ge=0.0, le=2.0)
    source: str
    discovered_at: datetime
    accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    times_fired: int = Field(default=0, ge=0)
    status: Literal["active", "provisional", "rejected", "pruned"] = "active"


# --- Story Models ---

class Story(BaseModel):
    """Input story structure for evaluation."""
    id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    technical_area: str | None = None
    services: list[str] = []
    source_conversations: list[str] = []


# --- Result Models ---

class CheapModeResult(BaseModel):
    """Output from cheap mode evaluation of a single story."""
    story_id: str
    gestalt: float = Field(..., ge=1.0, le=5.0)
    raw_score: float = Field(..., ge=0.0, le=5.0)
    reasons: list[str]
    patterns_matched: list[str] = Field(..., description="Pattern IDs that fired")
    patterns_missed: list[str] = Field(default=[], description="Patterns that should have fired")


class ExpensiveModeResult(BaseModel):
    """Output from expensive (LLM) mode evaluation of a single story."""
    story_id: str
    gestalt: float = Field(..., ge=1.0, le=5.0)
    reasoning: str
    strengths: list[str]
    weaknesses: list[str]


class DualModeResult(BaseModel):
    """Combined result from dual-mode evaluation."""
    story_id: str
    expensive: ExpensiveModeResult
    cheap: CheapModeResult
    gap: float = Field(..., description="expensive.gestalt - cheap.gestalt")


# --- Iteration Models ---

class IterationMetrics(BaseModel):
    """Metrics for a single iteration."""
    iteration: int
    timestamp: datetime
    expensive_avg: float
    cheap_avg: float
    gap: float
    gap_delta: float = Field(..., description="Change from previous iteration")
    pattern_count: int
    provisional_patterns: int
    patterns_committed: int
    patterns_rejected: int


class ComponentHealthStatus(BaseModel):
    """Health status for a single component."""
    healthy: bool
    flags: list[str] = []
    details: dict = {}


class IterationLog(BaseModel):
    """Complete log for a single iteration."""
    iteration: int
    timestamp: datetime
    component_health: dict[str, ComponentHealthStatus]
    metrics: IterationMetrics
    divergence_check: dict
    per_story_results: list[DualModeResult]
    actions_taken: list[dict]
    convergence_check: dict
```

---

## Execution Model

### Concurrent vs Sequential

Expensive and cheap modes run **sequentially**, not in parallel:

```
1. Load test stories
2. Run EXPENSIVE mode (LLM judge) → expensive_results
3. Run CHEAP mode (patterns) → cheap_results
4. Calculate gap using both results
5. If gap > threshold: propose new patterns using expensive_results reasoning
6. Validate provisional patterns against expensive_results
7. Log iteration, check convergence
```

**Rationale**: Cheap mode validation requires expensive mode's reasoning to determine if patterns matched correctly. Parallel execution would require a second pass.

### Stability Definition

"Stable for 2 consecutive iterations" means:

```python
def is_stable(history: list[IterationMetrics]) -> bool:
    """
    Stability requires:
    1. Same test data (story IDs match)
    2. Both metrics within threshold for 2 iterations
    3. Pattern set changes < 10 between iterations
    """
    if len(history) < 2:
        return False

    last_two = history[-2:]

    return (
        # Same test data
        last_two[0].story_ids == last_two[1].story_ids and
        # Cheap mode meets threshold both times
        all(m.cheap_avg >= 4.0 for m in last_two) and
        # Gap meets threshold both times
        all(m.gap <= 0.5 for m in last_two) and
        # Pattern set relatively stable
        abs(last_two[0].pattern_count - last_two[1].pattern_count) < 10
    )
```

---

## Error Handling

### LLM Rate Limits

```python
async def run_expensive_evaluation_with_retry(
    stories: list[Story],
    max_retries: int = 3,
    backoff_base: float = 2.0
) -> list[ExpensiveModeResult]:
    """Run expensive mode with exponential backoff on rate limits."""
    results = []

    for story in stories:
        for attempt in range(max_retries):
            try:
                result = await evaluate_with_llm(story)
                results.append(result)
                break
            except RateLimitError:
                if attempt == max_retries - 1:
                    # Log failure, use fallback score
                    results.append(ExpensiveModeResult(
                        story_id=story.id,
                        gestalt=0.0,  # Signals failure
                        reasoning="RATE_LIMIT_EXCEEDED",
                        strengths=[],
                        weaknesses=["evaluation_failed"]
                    ))
                else:
                    wait_time = backoff_base ** attempt
                    await asyncio.sleep(wait_time)

    # Check if too many failures
    failures = sum(1 for r in results if r.gestalt == 0.0)
    if failures > len(stories) * 0.2:  # >20% failed
        raise EvaluationUnreliableError(f"{failures}/{len(stories)} evaluations failed")

    return results
```

### Pattern File Corruption

```python
def save_patterns_safely(patterns: list[PatternV2], path: str) -> None:
    """Save patterns with backup and validation."""
    backup_path = f"{path}.backup"
    temp_path = f"{path}.tmp"

    # Write to temp file first
    with open(temp_path, 'w') as f:
        json.dump([p.model_dump() for p in patterns], f, indent=2, default=str)

    # Validate temp file is readable
    try:
        with open(temp_path) as f:
            loaded = json.load(f)
            [PatternV2(**p) for p in loaded]  # Validate schema
    except Exception as e:
        os.remove(temp_path)
        raise PatternSaveError(f"Validation failed: {e}")

    # Backup existing file
    if os.path.exists(path):
        shutil.copy(path, backup_path)

    # Atomic rename
    os.rename(temp_path, path)


def load_patterns_safely(path: str) -> list[PatternV2]:
    """Load patterns with fallback to backup."""
    try:
        with open(path) as f:
            data = json.load(f)
            return [PatternV2(**p) for p in data]
    except (json.JSONDecodeError, ValidationError) as e:
        # Try backup
        backup_path = f"{path}.backup"
        if os.path.exists(backup_path):
            log(f"Primary pattern file corrupted, loading backup: {e}")
            with open(backup_path) as f:
                data = json.load(f)
                return [PatternV2(**p) for p in data]
        raise PatternLoadError(f"Both primary and backup corrupted: {e}")
```

### Calibration History Retention

```python
MAX_CALIBRATION_HISTORY = 50  # Keep last 50 iterations

def update_calibration_history(
    history: list[dict],
    new_entry: IterationMetrics
) -> list[dict]:
    """Add new entry, prune old entries."""
    history.append(new_entry.model_dump())

    if len(history) > MAX_CALIBRATION_HISTORY:
        # Keep first entry (baseline) + last N-1 entries
        history = [history[0]] + history[-(MAX_CALIBRATION_HISTORY - 1):]

    return history
```

---

## What is "Cheap Mode"?

Cheap mode uses ONLY the accumulated patterns and heuristics, NO:

- LLM-as-judge calls
- External API calls

### Cheap Mode Evaluation Components

| Component      | Expensive Mode    | Cheap Mode                    |
| -------------- | ----------------- | ----------------------------- |
| Story quality  | LLM gestalt judge | Pattern matching + heuristics |
| Tech accuracy  | LLM assessment    | Regex path validation         |
| Actionability  | LLM assessment    | Keyword/structure checks      |
| INVEST scoring | LLM dimensional   | Rule-based scoring            |

### Pattern Types to Capture

```python
learned_patterns = {
    # Quality patterns
    "good_story_indicators": [
        "has_clear_user_problem",      # Contains "user wants/needs/expects"
        "has_acceptance_criteria",      # Has numbered AC list
        "has_technical_area",           # References specific code location
        "reasonable_scope",             # Not too broad, not too narrow
    ],

    # Anti-patterns
    "bad_story_indicators": [
        "too_vague",                    # Missing specifics
        "kitchen_sink",                 # Combines unrelated issues
        "missing_user_value",           # No clear benefit stated
    ],

    # Technical validation patterns
    "valid_tech_paths": {
        "aero": ["packages/", "infra/", "apps/"],
        "tack": ["service/", "client/"],
        # ... learned from scoping validation
    },

    # Scoring heuristics
    "gestalt_heuristics": {
        "title_quality": "1 point if < 80 chars and action-oriented",
        "ac_count": "1 point if 3-7 acceptance criteria",
        "tech_specificity": "1 point if mentions file/component",
        "user_focus": "1 point if mentions user benefit",
        "scope_check": "1 point if estimable in 1-3 days",
    }
}
```

---

## Implementation Changes

### 1. New File: `cheap_mode_evaluator.py`

```python
"""
Cheap mode evaluation using patterns only - no LLM calls.
"""

from pathlib import Path
import json
import re

class CheapModeEvaluator:
    def __init__(self, patterns_path: str = "learned_patterns.json"):
        self.patterns = self._load_patterns(patterns_path)

    def evaluate_story(self, story: dict) -> dict:
        """Score a story using only patterns and heuristics."""
        score = 0.0
        reasons = []

        # Title quality (0-1)
        if self._check_title_quality(story.get("title", "")):
            score += 1.0
            reasons.append("good_title")

        # Acceptance criteria (0-1)
        ac_score = self._check_acceptance_criteria(story.get("acceptance_criteria", []))
        score += ac_score
        if ac_score > 0.5:
            reasons.append("good_ac")

        # Technical specificity (0-1)
        tech_score = self._check_technical_area(story.get("technical_area", ""))
        score += tech_score
        if tech_score > 0.5:
            reasons.append("good_tech")

        # User value (0-1)
        if self._check_user_value(story.get("description", "")):
            score += 1.0
            reasons.append("clear_user_value")

        # Scope check (0-1)
        if self._check_scope(story):
            score += 1.0
            reasons.append("appropriate_scope")

        # Normalize to 1-5 scale
        gestalt = 1.0 + (score / 5.0) * 4.0

        return {
            "gestalt": round(gestalt, 2),
            "reasons": reasons,
            "raw_score": score,
        }

    def _check_title_quality(self, title: str) -> bool:
        """Title should be < 80 chars, action-oriented."""
        if not title or len(title) > 80:
            return False
        action_words = ["add", "fix", "update", "improve", "enable", "implement"]
        return any(title.lower().startswith(w) for w in action_words)

    def _check_acceptance_criteria(self, acs: list) -> float:
        """3-7 ACs is ideal, each should be testable."""
        if not acs:
            return 0.0
        count = len(acs)
        if count < 2:
            return 0.2
        if count > 10:
            return 0.3
        if 3 <= count <= 7:
            return 1.0
        return 0.6

    def _check_technical_area(self, tech_area: str) -> float:
        """Validate tech area against known patterns."""
        if not tech_area:
            return 0.0

        # Check against learned valid paths
        valid_paths = self.patterns.get("valid_tech_paths", {})
        for repo, prefixes in valid_paths.items():
            if repo in tech_area:
                if any(prefix in tech_area for prefix in prefixes):
                    return 1.0
                return 0.5  # Right repo, unknown path

        # Fallback: any file-like pattern
        if re.search(r'\w+/\w+\.(py|ts|tsx|js|jsx)', tech_area):
            return 0.7

        return 0.2

    def _check_user_value(self, description: str) -> bool:
        """Description should mention user benefit."""
        if not description:
            return False
        value_phrases = [
            "user can", "users will", "allows", "enables",
            "improves", "reduces", "saves", "prevents"
        ]
        desc_lower = description.lower()
        return any(phrase in desc_lower for phrase in value_phrases)

    def _check_scope(self, story: dict) -> bool:
        """Check if scope seems appropriate (not too big/small)."""
        # Heuristic: description length correlates with scope
        desc = story.get("description", "")
        acs = story.get("acceptance_criteria", [])

        # Too small: very short description, < 2 ACs
        if len(desc) < 50 or len(acs) < 2:
            return False

        # Too big: very long description, > 10 ACs
        if len(desc) > 2000 or len(acs) > 10:
            return False

        return True

    def _load_patterns(self, path: str) -> dict:
        """Load learned patterns from JSON."""
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {"valid_tech_paths": {}}


def evaluate_cheap(stories: list, patterns_path: str = "learned_patterns.json") -> dict:
    """
    Evaluate stories using cheap mode only.
    Returns metrics comparable to expensive mode.
    """
    evaluator = CheapModeEvaluator(patterns_path)

    results = []
    for story in stories:
        result = evaluator.evaluate_story(story)
        results.append(result)

    # Aggregate
    gestalts = [r["gestalt"] for r in results]
    avg_gestalt = sum(gestalts) / len(gestalts) if gestalts else 0

    return {
        "mode": "cheap",
        "gestalt_avg": round(avg_gestalt, 2),
        "story_count": len(stories),
        "individual_scores": results,
    }
```

### 2. Update: `run_pipeline_test.py`

Add a `--mode` flag:

```python
# Add to argument parser
parser.add_argument(
    "--mode",
    choices=["expensive", "cheap", "dual"],
    default="dual",
    help="Evaluation mode: expensive (LLM judge), cheap (patterns only), or dual (both)"
)

# In main evaluation logic
if args.mode in ["expensive", "dual"]:
    expensive_results = run_expensive_evaluation(stories)

if args.mode in ["cheap", "dual"]:
    cheap_results = evaluate_cheap(stories, "learned_patterns.json")

if args.mode == "dual":
    gap = expensive_results["gestalt_avg"] - cheap_results["gestalt_avg"]
    results["gap"] = round(gap, 2)
    results["expensive"] = expensive_results
    results["cheap"] = cheap_results
```

### 3. Update: `ralph_v2.sh`

Change completion criteria:

```bash
# After evaluation, check dual-mode results
CHEAP_GESTALT=$(jq -r '.cheap.gestalt_avg' "$RESULTS_FILE")
GAP=$(jq -r '.gap' "$RESULTS_FILE")

echo "  Expensive mode gestalt: $EXPENSIVE_GESTALT"
echo "  Cheap mode gestalt: $CHEAP_GESTALT"
echo "  Gap: $GAP"

# New completion check
CHEAP_OK=$(echo "$CHEAP_GESTALT >= 4.0" | bc -l)
GAP_OK=$(echo "$GAP <= 0.5" | bc -l)

if [ "$CHEAP_OK" -eq 1 ] && [ "$GAP_OK" -eq 1 ]; then
    echo "Both cheap mode and gap criteria met!"
    # Check stability (need 2 consecutive passing iterations)
    ...
fi
```

### 4. Update: `PROMPT_V2.md`

Add instructions for dual-mode awareness:

```markdown
## Evaluation Protocol

Run evaluation in DUAL MODE:

1. **Expensive mode**: Full LLM judge evaluation
2. **Cheap mode**: Patterns and heuristics only (no API calls)

Your goal is to minimize the GAP between these modes.

When the gap is large, analyze WHY:

- What did the expensive evaluation catch that cheap mode missed?
- Can you add a pattern/heuristic to catch it?
- Update `learned_patterns.json` with new patterns

Completion requires:

- Cheap mode gestalt >= 4.0 (patterns work standalone)
- Gap <= 0.5 (cheap mode tracks expensive mode)
- Stable for 2 iterations
```

### 5. Pattern Learning Loop

After each iteration, if gap is large:

```python
def learn_from_gap(expensive_results, cheap_results, patterns):
    """
    Analyze where cheap mode failed and update patterns.
    """
    for i, (exp, cheap) in enumerate(zip(expensive_results, cheap_results)):
        exp_gestalt = exp["gestalt"]
        cheap_gestalt = cheap["gestalt"]

        if exp_gestalt - cheap_gestalt > 0.5:
            # Cheap mode missed something
            story = stories[i]

            # What did expensive mode like that cheap mode missed?
            exp_reasons = exp.get("reasoning", "")
            cheap_reasons = cheap.get("reasons", [])

            # Log for analysis
            print(f"Story {i}: Gap of {exp_gestalt - cheap_gestalt}")
            print(f"  Expensive said: {exp_reasons}")
            print(f"  Cheap caught: {cheap_reasons}")

            # TODO: Auto-generate new pattern based on analysis
            # This is where Ralph proposes pattern updates
```

---

## Metrics Dashboard

Each iteration should output:

```
=== Iteration 5 Results ===

EXPENSIVE MODE:
  Gestalt avg: 4.2

CHEAP MODE:
  Gestalt avg: 3.8
  Pattern match: 92%

GAP ANALYSIS:
  Gap: 0.4 (target: <= 0.5) ✓

  Stories with large gap (> 0.5):
    - Story 3: exp=4.5, cheap=3.2 (gap=1.3)
      Issue: Cheap mode missed nuanced user value
      Action: Add pattern for "solves [problem] for [user type]"

DECISION: Gap improving, continuing optimization...
```

---

## Migration Path

1. **Phase 1**: Implement `cheap_mode_evaluator.py` (standalone)
2. **Phase 2**: Add `--mode dual` to `run_pipeline_test.py`
3. **Phase 3**: Update `ralph_v2.sh` completion criteria
4. **Phase 4**: Update `PROMPT_V2.md` with dual-mode instructions
5. **Phase 5**: Run and validate

---

## Pattern Learning Mechanism

### How Patterns Get Created

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PATTERN LEARNING FLOW                             │
│                                                                      │
│  1. Expensive mode scores story highly (4.5)                        │
│  2. Cheap mode scores same story low (3.0)                          │
│  3. Gap = 1.5 (above threshold)                                     │
│                       │                                              │
│                       ▼                                              │
│  4. Analyze: What did expensive mode see that cheap missed?         │
│     - LLM reasoning: "Story has clear user pain point expressed     │
│       as 'frustrated when X happens'"                               │
│     - Cheap mode only checked for "user can/will" phrases           │
│                       │                                              │
│                       ▼                                              │
│  5. Propose pattern: Add "frustrated when" to value_phrases         │
│                       │                                              │
│                       ▼                                              │
│  6. Validate: Re-run cheap mode with new pattern                    │
│     - If gap closes → commit pattern                                │
│     - If gap persists → try different pattern                       │
│                       │                                              │
│                       ▼                                              │
│  7. Update learned_patterns.json                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Pattern Proposal Prompt

When gap is large, Ralph uses this prompt to propose patterns:

```markdown
The expensive LLM judge gave this story a score of {exp_score}.
The cheap pattern-based evaluator gave it {cheap_score}.
Gap: {gap}

Expensive mode reasoning:
{exp_reasoning}

Cheap mode detected these signals:
{cheap_signals}

Current cheap mode patterns:
{current_patterns}

What pattern is the cheap mode MISSING that would catch what the expensive mode saw?

Propose a specific, testable pattern in this format:
{
"category": "good_story_indicators | bad_story_indicators | value_phrases | ...",
"pattern": "the exact string or regex to add",
"rationale": "why this captures the signal"
}
```

---

## Pattern Schema (learned_patterns.json)

```json
{
  "version": "2.0",
  "last_updated": "2026-01-16T12:00:00Z",
  "iteration_learned": 5,

  "quality_signals": {
    "good_indicators": [
      { "pattern": "has_clear_user_problem", "weight": 1.0, "learned_iter": 0 },
      {
        "pattern": "has_acceptance_criteria",
        "weight": 1.0,
        "learned_iter": 0
      },
      { "pattern": "has_technical_area", "weight": 1.0, "learned_iter": 0 }
    ],
    "bad_indicators": [
      { "pattern": "too_vague", "weight": -0.5, "learned_iter": 0 },
      { "pattern": "kitchen_sink", "weight": -1.0, "learned_iter": 2 }
    ]
  },

  "value_phrases": [
    { "phrase": "user can", "weight": 1.0, "learned_iter": 0 },
    { "phrase": "frustrated when", "weight": 0.8, "learned_iter": 3 },
    { "phrase": "saves time", "weight": 0.7, "learned_iter": 5 }
  ],

  "tech_validation": {
    "valid_repo_paths": {
      "aero": ["packages/", "infra/", "apps/"],
      "tack": ["service/", "client/"],
      "charlotte": ["packages/"],
      "ghostwriter": ["stack/"],
      "zuck": ["service/"]
    },
    "valid_extensions": [".ts", ".tsx", ".js", ".jsx", ".py", ".php"],
    "learned_iter": 1
  },

  "scoring_weights": {
    "title_quality": 1.0,
    "ac_count": 1.0,
    "tech_specificity": 1.2,
    "user_focus": 1.0,
    "scope_check": 0.8
  },

  "calibration_history": [
    { "iteration": 1, "expensive_avg": 3.2, "cheap_avg": 2.1, "gap": 1.1 },
    { "iteration": 2, "expensive_avg": 3.5, "cheap_avg": 2.8, "gap": 0.7 },
    { "iteration": 3, "expensive_avg": 3.8, "cheap_avg": 3.4, "gap": 0.4 }
  ]
}
```

---

## Existing Patterns Asset

We already have **471 learned patterns** from previous Ralph runs in `learned_patterns.json` (262KB):

```
Pattern breakdown:
├── good_pattern: Quality signals that indicate well-scoped stories
├── bad_pattern: Anti-patterns that indicate poor scoping
└── Sources: scoping_validation (from LLM verification)
```

### Current Pattern Structure

```json
{
  "version": "1.0",
  "last_updated": "2026-01-14T03:50:41.218897",
  "patterns": [
    {
      "type": "good_pattern",
      "description": "Keep OAuth flow for a single platform in one story",
      "example": "This story covers Pinterest OAuth only (tack service)",
      "discovered_at": "2026-01-13T21:33:54.436502",
      "source": "scoping_validation"
    },
    {
      "type": "bad_pattern",
      "description": "Do not group Pinterest OAuth with Facebook OAuth in same story",
      "example": "They use different services (tack vs zuck)",
      "discovered_at": "2026-01-13T21:11:48.132107",
      "source": "scoping_validation"
    }
  ],
  "service_insights": { ... },
  "scoping_rules": { ... }
}
```

### Pattern Migration Strategy

The existing patterns use a narrative format. For cheap mode evaluation, we'll:

1. **Parse existing patterns** into evaluation rules
2. **Extract keywords** from descriptions for pattern matching
3. **Build tech validation rules** from `service_insights`
4. **Create scoring weights** based on pattern frequency

```python
def migrate_existing_patterns(legacy_patterns: dict) -> dict:
    """Convert v1.0 patterns to v2.0 cheap mode format."""
    good_patterns = []
    bad_patterns = []

    for p in legacy_patterns.get("patterns", []):
        entry = {
            "description": p["description"],
            "keywords": extract_keywords(p["description"]),
            "weight": 1.0,
            "source": p.get("source", "unknown"),
        }
        if p["type"] == "good_pattern":
            good_patterns.append(entry)
        else:
            bad_patterns.append(entry)

    return {
        "version": "2.0",
        "quality_signals": {
            "good_indicators": good_patterns,
            "bad_indicators": bad_patterns,
        },
        "tech_validation": extract_from_service_insights(
            legacy_patterns.get("service_insights", {})
        ),
    }
```

---

## Regression Detection

```python
def check_for_regression(current_results, previous_results, patterns_changed):
    """
    Detect if a pattern change made things worse.
    """
    current_gap = current_results["gap"]
    previous_gap = previous_results["gap"]

    current_cheap = current_results["cheap"]["gestalt_avg"]
    previous_cheap = previous_results["cheap"]["gestalt_avg"]

    # Regression conditions:
    # 1. Gap increased by more than 0.2
    # 2. Cheap score dropped by more than 0.3
    # 3. Correlation with expensive score decreased

    if current_gap > previous_gap + 0.2:
        return {
            "regression": True,
            "type": "gap_increased",
            "delta": current_gap - previous_gap,
            "action": "revert_pattern_change",
            "pattern_changed": patterns_changed
        }

    if current_cheap < previous_cheap - 0.3:
        return {
            "regression": True,
            "type": "cheap_score_dropped",
            "delta": current_cheap - previous_cheap,
            "action": "revert_pattern_change"
        }

    return {"regression": False}
```

### Automatic Rollback

```bash
# In ralph_v2.sh, after evaluation:
if [ "$REGRESSION_DETECTED" = true ]; then
    echo "REGRESSION DETECTED - Rolling back pattern change"
    git checkout HEAD~1 -- learned_patterns.json
    # Re-run evaluation to confirm rollback worked
fi
```

---

## Integration with Existing Ralph V2 Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                 RALPH V2 + DUAL MODE INTEGRATION                     │
│                                                                      │
│  EXISTING FLOW:                    NEW ADDITIONS:                   │
│  ─────────────                     ───────────────                  │
│                                                                      │
│  ┌──────────────┐                                                   │
│  │ Load Context │ ◄─── Add: Load learned_patterns.json             │
│  └──────┬───────┘                                                   │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────┐                                                   │
│  │ Run Pipeline │                                                   │
│  │ (generate    │                                                   │
│  │  stories)    │                                                   │
│  └──────┬───────┘                                                   │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────┐      ┌──────────────┐                            │
│  │ EXPENSIVE    │      │    CHEAP     │ ◄─── NEW                   │
│  │ Evaluation   │      │  Evaluation  │                            │
│  │ (LLM+PW)     │      │ (patterns)   │                            │
│  └──────┬───────┘      └──────┬───────┘                            │
│         │                     │                                     │
│         └─────────┬───────────┘                                     │
│                   ▼                                                 │
│          ┌──────────────┐                                           │
│          │ Gap Analysis │ ◄─── NEW                                  │
│          └──────┬───────┘                                           │
│                 │                                                   │
│         ┌───────┴───────┐                                          │
│         ▼               ▼                                          │
│  ┌─────────────┐ ┌─────────────┐                                   │
│  │ Gap > 0.5?  │ │ Gap <= 0.5  │                                   │
│  │ Learn new   │ │ Check       │                                   │
│  │ patterns    │ │ completion  │                                   │
│  └──────┬──────┘ └──────┬──────┘                                   │
│         │               │                                          │
│         ▼               ▼                                          │
│  ┌─────────────┐ ┌─────────────┐                                   │
│  │ Modify      │ │ Cheap >= 4? │                                   │
│  │ Pipeline    │ │ Stable 2x?  │                                   │
│  │ (existing)  │ └──────┬──────┘                                   │
│  └──────┬──────┘        │                                          │
│         │               ▼                                          │
│         │        ┌─────────────┐                                   │
│         │        │  COMPLETE   │ ◄─── Changed criteria            │
│         │        └─────────────┘                                   │
│         │                                                          │
│         ▼                                                          │
│  ┌─────────────┐                                                   │
│  │ Git Commit  │ ◄─── Now includes learned_patterns.json          │
│  └─────────────┘                                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File/Component Map

```
scripts/ralph/
├── ralph_v2.sh                    # Main loop (UPDATE: new completion criteria)
├── PROMPT_V2.md                   # Instructions (UPDATE: dual-mode awareness)
├── DUAL_MODE_DESIGN.md            # This document
│
├── run_pipeline_test.py           # Test runner (UPDATE: --mode flag)
├── cheap_mode_evaluator.py        # NEW: Pattern-based evaluation
├── pattern_learner.py             # NEW: Gap analysis and pattern proposal
│
├── learned_patterns.json          # Pattern storage (UPDATE: new schema)
├── progress.txt                   # Iteration history (UPDATE: includes gap)
│
├── test_data/
│   ├── manifest.json
│   ├── intercom/
│   ├── coda_tables/
│   └── coda_pages/
│
└── outputs/
    ├── iteration_N/
    │   ├── stories.json
    │   ├── expensive_eval.json
    │   ├── cheap_eval.json        # NEW
    │   ├── gap_analysis.json      # NEW
    │   └── pattern_proposals.json # NEW
    └── ...
```

---

## Open Questions (Resolved)

| Question                | Decision                                                 |
| ----------------------- | -------------------------------------------------------- |
| Pattern format          | JSON with version, weights, and history                  |
| Auto-pattern generation | Yes, via LLM with structured prompt                      |
| Weighting               | Start at 1.0, adjust based on correlation                |
| Stability window        | 2 consecutive iterations                                 |
| Existing patterns       | Migrate 471 v1.0 patterns to v2.0 format (no cold start) |
| Regression handling     | Automatic rollback + re-evaluation                       |

---

## Implementation Order

All phases are fully automated with no manual intervention required.

```
Phase 1: Foundation + Observability
├── Define Pydantic models (PatternV1, PatternV2, CheapModeResult)
├── Implement pattern migration with automated validation
├── Implement cheap_mode_evaluator.py with health metrics
├── Add ComponentHealth tracking from iteration 0
└── Structured iteration logs from the start

Phase 2: Dual-Mode + Divergence Detection
├── Add --mode flag to run_pipeline_test.py
├── Implement gap calculation with detect_divergence()
├── Update ralph_v2.sh with dual-mode logic
├── Add automatic recovery actions (rollback, prune, recalibrate)
└── Update completion criteria to use check_convergence()

Phase 3: Pattern Learning Loop (Full Automation)
├── Implement pattern_learner.py with LLM-based proposals
├── Implement PatternProposal with provisional → validated flow
├── Add validate_provisional_patterns() per-iteration
├── Automatic commit/reject based on accuracy thresholds
└── Automatic divergence response (no human escalation)

Phase 4: Self-Healing & Convergence
├── Implement all RECOVERY_ACTIONS handlers
├── Add pattern deduplication (semantic similarity)
├── Add pattern pruning (unused patterns, low weights)
├── Convergence proof generation
└── End-to-end automated test suite
```

### Key Automation Guarantees

| Scenario                         | Automated Response                            |
| -------------------------------- | --------------------------------------------- |
| Gap increasing for 3 iterations  | Rollback patterns, reduce learning rate       |
| Gap plateau (no improvement)     | Increase proposal diversity, prune low-weight |
| Cheap mode scores all same       | Flag unhealthy, check pattern coverage        |
| Pattern explosion (>1.5x growth) | Deduplicate, prune by coverage                |
| Expensive mode unreliable        | Run 3x, use median, flag high variance        |
| Convergence achieved             | Generate proof, stop iterations               |

---

## Success Metrics

| Metric             | Target                   | How Measured                                     |
| ------------------ | ------------------------ | ------------------------------------------------ |
| Cheap mode gestalt | ≥ 4.0                    | Average of pattern-based story scores            |
| Mode gap           | ≤ 0.5                    | `expensive_avg - cheap_avg`                      |
| Pattern coverage   | ≥ 80%                    | Stories where patterns detect same issues as LLM |
| Stability          | 2 consecutive iterations | Both metrics hold for 2 runs                     |
| Migration success  | 471 → usable patterns    | Pattern conversion without data loss             |

### What "Done" Looks Like

```
Iteration N Results:
  EXPENSIVE: gestalt=4.2
  CHEAP:     gestalt=4.0, pattern_match=85%
  GAP:       0.2 ✓

Iteration N+1 Results:
  EXPENSIVE: gestalt=4.1
  CHEAP:     gestalt=3.9, pattern_match=84%
  GAP:       0.2 ✓

STATUS: COMPLETE - Cheap mode meets threshold, gap stable for 2 iterations
```

---

## Risks & Mitigations

| Risk                         | Impact                                  | Mitigation                                        |
| ---------------------------- | --------------------------------------- | ------------------------------------------------- |
| Patterns too specific        | Won't generalize to new stories         | Track per-pattern hit rate, prune unused patterns |
| Gap never closes             | Cheap mode fundamentally insufficient   | Automated divergence detection (see below)        |
| Expensive mode unreliable    | Bad ground truth corrupts patterns      | Cross-validate with multiple LLM runs             |
| Pattern explosion            | Too many patterns = slow/unmaintainable | Weight-based pruning, merge similar patterns      |
| Regression from new patterns | New pattern hurts existing scores       | Automatic rollback + re-evaluation                |

---

## Automated Debuggability

Since manual pattern evaluation is not an option, we solve debuggability through automated observability and staged validation.

### Component Health Metrics

Each component reports its own health score every iteration:

```python
class ComponentHealth:
    """Automated health tracking for each system component."""

    def __init__(self):
        self.metrics = {
            "pattern_migration": None,   # Did v1→v2 conversion succeed?
            "cheap_evaluator": None,     # Is cheap mode producing valid scores?
            "expensive_evaluator": None, # Is expensive mode responding?
            "gap_calculator": None,      # Is gap calculation stable?
            "pattern_learner": None,     # Are proposed patterns valid?
        }

    def check_cheap_evaluator(self, results: list) -> dict:
        """Validate cheap mode is functioning."""
        scores = [r["gestalt"] for r in results]
        return {
            "healthy": True,
            "score_range": (min(scores), max(scores)),
            "variance": statistics.variance(scores) if len(scores) > 1 else 0,
            "flags": [
                "all_same_score" if len(set(scores)) == 1 else None,
                "scores_out_of_range" if any(s < 1 or s > 5 for s in scores) else None,
                "zero_patterns_matched" if all(len(r.get("reasons", [])) == 0 for r in results) else None,
            ]
        }
```

### Divergence Detection

Automatically detect when the system is failing to converge:

```python
def detect_divergence(history: list[dict]) -> dict:
    """
    Detect if gap is growing instead of shrinking.
    Returns actionable diagnosis.
    """
    if len(history) < 3:
        return {"diverging": False, "reason": "insufficient_data"}

    recent_gaps = [h["gap"] for h in history[-3:]]

    # Gap growing for 3 consecutive iterations
    if recent_gaps[0] < recent_gaps[1] < recent_gaps[2]:
        return {
            "diverging": True,
            "reason": "gap_increasing",
            "diagnosis": analyze_gap_increase(history),
            "action": "rollback_to_iteration_N"
        }

    # Gap stuck (not improving)
    if max(recent_gaps) - min(recent_gaps) < 0.05:
        return {
            "diverging": True,
            "reason": "gap_plateau",
            "diagnosis": "patterns not capturing new signals",
            "action": "increase_pattern_proposal_temperature"
        }

    return {"diverging": False}

def analyze_gap_increase(history: list) -> str:
    """Diagnose WHY gap is increasing."""
    latest = history[-1]
    previous = history[-2]

    if latest["cheap_avg"] < previous["cheap_avg"]:
        return "cheap_mode_degraded: new patterns hurt scoring"
    if latest["expensive_avg"] > previous["expensive_avg"]:
        return "expensive_mode_shifted: LLM calibration changed"
    if latest["pattern_count"] > previous["pattern_count"] * 1.5:
        return "pattern_explosion: too many conflicting patterns"

    return "unknown: review iteration logs"
```

### Provisional Patterns

New patterns are NOT immediately committed. They go through automated validation:

```python
class PatternProposal:
    """A proposed pattern that must prove itself before becoming permanent."""

    status: Literal["provisional", "validated", "rejected"]
    pattern: dict
    proposed_at: int  # iteration number

    # Validation tracking
    stories_tested: int = 0
    correct_predictions: int = 0

    @property
    def accuracy(self) -> float:
        if self.stories_tested == 0:
            return 0.0
        return self.correct_predictions / self.stories_tested

    def should_commit(self) -> bool:
        """Commit only if pattern proves accurate over N stories."""
        return (
            self.stories_tested >= 10 and
            self.accuracy >= 0.7
        )

    def should_reject(self) -> bool:
        """Reject if pattern is clearly not helping."""
        return (
            self.stories_tested >= 5 and
            self.accuracy < 0.3
        )


def validate_provisional_patterns(
    patterns: list[PatternProposal],
    stories: list[dict],
    expensive_results: list[dict]
) -> list[PatternProposal]:
    """
    Test provisional patterns against new stories.
    Commit or reject based on accuracy.
    """
    for pattern in patterns:
        if pattern.status != "provisional":
            continue

        for story, exp_result in zip(stories, expensive_results):
            # Did this pattern fire?
            pattern_fired = check_pattern_match(pattern.pattern, story)
            # Did expensive mode agree with the signal?
            expensive_agreed = signal_matches_expensive(pattern, exp_result)

            pattern.stories_tested += 1
            if pattern_fired == expensive_agreed:
                pattern.correct_predictions += 1

        # Update status
        if pattern.should_commit():
            pattern.status = "validated"
            log(f"Pattern COMMITTED: {pattern.pattern['description']}")
        elif pattern.should_reject():
            pattern.status = "rejected"
            log(f"Pattern REJECTED: {pattern.pattern['description']}")

    return patterns
```

### Automated Iteration Log

Every iteration produces a structured log for automated analysis:

```json
{
  "iteration": 5,
  "timestamp": "2026-01-16T14:30:00Z",

  "component_health": {
    "cheap_evaluator": { "healthy": true, "flags": [] },
    "expensive_evaluator": { "healthy": true, "flags": [] },
    "pattern_learner": { "healthy": true, "flags": ["high_rejection_rate"] }
  },

  "metrics": {
    "expensive_avg": 4.2,
    "cheap_avg": 3.8,
    "gap": 0.4,
    "gap_delta": -0.1,
    "pattern_count": 485,
    "provisional_patterns": 12,
    "patterns_committed_this_iter": 3,
    "patterns_rejected_this_iter": 2
  },

  "divergence_check": {
    "diverging": false
  },

  "per_story_analysis": [
    {
      "story_id": "story_1",
      "expensive_score": 4.5,
      "cheap_score": 4.2,
      "gap": 0.3,
      "patterns_matched": ["has_clear_user_problem", "reasonable_scope"],
      "patterns_missed": ["specific_tech_path"]
    }
  ],

  "actions_taken": [
    { "action": "committed_pattern", "pattern_id": "p_482" },
    { "action": "rejected_pattern", "pattern_id": "p_479" }
  ],

  "next_iteration_plan": {
    "focus": "improve tech_path detection",
    "proposed_patterns": 5
  }
}
```

### Automatic Recovery Actions

When divergence is detected, the system takes corrective action without human intervention:

```python
RECOVERY_ACTIONS = {
    "gap_increasing": [
        ("rollback_patterns", "Revert to last known good pattern set"),
        ("reduce_learning_rate", "Make smaller pattern changes"),
        ("increase_validation_threshold", "Require 80% accuracy to commit"),
    ],
    "gap_plateau": [
        ("increase_proposal_diversity", "Try more varied pattern types"),
        ("prune_low_weight_patterns", "Remove patterns with < 0.3 weight"),
        ("reset_provisional", "Clear provisional patterns, start fresh proposals"),
    ],
    "cheap_mode_degraded": [
        ("rollback_patterns", "Revert pattern changes"),
        ("recalibrate_weights", "Re-run weight optimization"),
    ],
    "pattern_explosion": [
        ("deduplicate_patterns", "Merge semantically similar patterns"),
        ("prune_by_coverage", "Remove patterns that never fire"),
    ],
}

def execute_recovery(diagnosis: str) -> None:
    """Automatically execute recovery based on diagnosis."""
    actions = RECOVERY_ACTIONS.get(diagnosis, [])
    for action_id, description in actions:
        log(f"RECOVERY: Executing {action_id} - {description}")
        globals()[action_id]()  # Execute recovery function
```

### Convergence Proof

The system is considered converged when:

```python
def check_convergence(history: list[dict]) -> dict:
    """
    Automated convergence check with proof.
    """
    if len(history) < 2:
        return {"converged": False, "reason": "insufficient_iterations"}

    last_two = history[-2:]

    checks = {
        "cheap_threshold": all(h["cheap_avg"] >= 4.0 for h in last_two),
        "gap_threshold": all(h["gap"] <= 0.5 for h in last_two),
        "no_divergence": not detect_divergence(history)["diverging"],
        "patterns_stable": abs(last_two[0]["pattern_count"] - last_two[1]["pattern_count"]) < 10,
        "no_regressions": all(h.get("regression_detected", False) == False for h in last_two),
    }

    converged = all(checks.values())

    return {
        "converged": converged,
        "checks": checks,
        "proof": {
            "iterations_checked": [h["iteration"] for h in last_two],
            "cheap_scores": [h["cheap_avg"] for h in last_two],
            "gaps": [h["gap"] for h in last_two],
        }
    }
```

---

## Dependencies

- **Existing**: `learned_patterns.json` (471 patterns, v1.0 format)
- **Existing**: `run_pipeline_test.py` (expensive mode evaluation)
- **New**: `cheap_mode_evaluator.py` (pattern-based scoring)
- **New**: `pattern_learner.py` (gap analysis and proposals)
