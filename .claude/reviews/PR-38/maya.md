# Maya Maintainability Review - PR #38 Round 1

**Verdict**: APPROVE (with suggestions)
**Date**: 2026-01-19

## Summary

This PR adds substantial VDD (Validation-Driven Development) infrastructure with generally good documentation at the module level. However, several maintainability concerns emerged during review: magic numbers without explanation, inconsistent terminology across files, missing docstrings on helper functions, and implicit assumptions about data formats. The code is functional but would benefit from better in-line context for future maintainers debugging issues at 2am.

---

## M1: Magic Numbers for Thresholds in cheap_mode_evaluator.py

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Isolated

**File**: `scripts/ralph/cheap_mode_evaluator.py:36-52`

### The Problem

Multiple hardcoded thresholds appear without comments explaining their derivation or significance. The values 0.5, 0.1, 0.2, 3, 7, 10, 100, 1000, 2000 all have specific meanings but no explanation.

### The Maintainer's Test

- Can I understand without author? No - why these specific values?
- Can I debug at 2am? No - if scoring seems wrong, how do I know which threshold to adjust?
- Can I change without fear? No - changing 0.73 to 0.75 might break things unexpectedly
- Will this make sense in 6 months? No

### Current Code

```python
TITLE_LENGTH_WEIGHT = 0.5  # Bonus for titles <= 80 chars
TITLE_ACTION_WEIGHT = 0.5  # Bonus for action-oriented titles

PATTERN_GOOD_BONUS = 0.1  # Small bonus per good pattern match
PATTERN_BAD_PENALTY = 0.2  # Larger penalty to discourage anti-patterns

AC_IDEAL_MIN, AC_IDEAL_MAX = 3, 7
AC_ACCEPTABLE_MAX = 10

SCOPE_DESC_MIN, SCOPE_DESC_MAX = 100, 1000
SCOPE_DESC_TOO_LARGE = 2000
```

### Suggested Improvement

```python
# =============================================================================
# Scoring Configuration
#
# These weights were calibrated through VDD iterations on 2024-XX-XX.
# The gestalt scoring aims to match LLM evaluation within +/- 0.3 points.
# Adjust via calibration runs if gap exceeds target.
# =============================================================================

# Title scoring - sums to 1.0 for a "perfect" title
TITLE_LENGTH_WEIGHT = 0.5  # Bonus for titles <= 80 chars (matches INVEST guidance)
TITLE_ACTION_WEIGHT = 0.5  # Bonus for action verbs (add/fix/update/improve)

# Pattern scoring - asymmetric to be conservative (penalize bad > reward good)
PATTERN_GOOD_BONUS = 0.1   # Small bonus per good pattern (avoid over-rewarding)
PATTERN_BAD_PENALTY = 0.2  # 2x penalty to discourage anti-patterns

# AC count thresholds - derived from INVEST story standard
AC_IDEAL_MIN, AC_IDEAL_MAX = 3, 7  # Per Agile best practices
AC_ACCEPTABLE_MAX = 10             # Beyond this, story is likely too big

# Description length thresholds (character counts)
SCOPE_DESC_MIN = 100    # Below this: too vague to be actionable
SCOPE_DESC_MAX = 1000   # Above this: may need splitting
SCOPE_DESC_TOO_LARGE = 2000  # Definite red flag for scope creep
```

### Why This Matters

When the cheap mode evaluator disagrees with LLM evaluation, maintainers need to understand which thresholds to tune. Without derivation context, any adjustment is guesswork.

---

## M2: Undocumented "gestalt" Terminology

**Severity**: MEDIUM | **Confidence**: High | **Scope**: Systemic

**File**: Multiple files in `scripts/ralph/`

### The Problem

The term "gestalt" is used throughout the Ralph scripts to mean an overall quality score, but this isn't standard terminology. A glossary comment exists in `cheap_mode_evaluator.py` but the same term appears in `convergence_monitor.py` without explanation.

### The Maintainer's Test

- Can I understand without author? No - "gestalt" is domain-specific jargon
- Can I debug at 2am? Partially - need to grep to find definition
- Can I change without fear? Yes - name is consistent once understood
- Will this make sense in 6 months? Maybe - if I find the glossary

### Current Code

In `convergence_monitor.py`, gestalt is used without definition:

```python
# No glossary or definition comment
def get_status(self) -> dict:
    # Uses gestalt without explaining what it means
```

### Suggested Improvement

Add a shared glossary import or duplicate the definition in key files:

```python
"""
Glossary:
    gestalt (float): Overall story quality score on 1-5 scale.
                     Combines title, ACs, technical area, user value, and scope.
                     1=Poor, 5=Excellent, comparable to LLM evaluation.
    gap (float): Difference between expensive (LLM) and cheap (pattern) gestalt.
                 Target is gap < 0.3. Positive = cheap underestimates quality.
"""
```

### Why This Matters

New team members or reviewers won't know what "gestalt" means without context. Adding a glossary at the top of files using the term prevents confusion.

---

## M3: Missing Docstrings on Key Helper Functions

**Severity**: LOW | **Confidence**: High | **Scope**: Systemic

**File**: `scripts/codebase-search-vdd/evaluate_results_v2.py:143-261`

### The Problem

The `extract_files_from_output_with_diagnostics` function is 119 lines long with multiple regex patterns and a fallback cascade, but lacks detailed docstring explaining the extraction strategy priority.

### The Maintainer's Test

- Can I understand without author? Partially - code is readable but intent unclear
- Can I debug at 2am? No - which pattern should fire for my case?
- Can I change without fear? No - unclear which patterns are fallbacks vs primary
- Will this make sense in 6 months? Needs re-reading

### Current Code

```python
def extract_files_from_output_with_diagnostics(output: str) -> tuple[list[str], dict[str, list[str]]]:
    """
    Extract file paths from Claude CLI output WITH diagnostic info.

    Prioritizes JSON extraction (more reliable), falls back to regex patterns.
    ...
    """
```

### Suggested Improvement

```python
def extract_files_from_output_with_diagnostics(output: str) -> tuple[list[str], dict[str, list[str]]]:
    """
    Extract file paths from Claude CLI output WITH diagnostic info.

    Extraction Priority (try in order, return on first success):
    1. Structured JSON with "relevant_files" key (most reliable)
    2. Regex fallbacks (for backward compatibility and edge cases):
       a. Pattern 1: Relative paths with known repo prefixes (aero/, tack/, etc.)
       b. Pattern 2: Absolute paths converted to repo-relative
       c. Pattern 3: JSON-like arrays ["file1", "file2"]
       d. Pattern 4: Markdown bullet points with file paths
       e. Pattern 5: Backtick-wrapped paths `file.ext`

    Returns:
        tuple: (list of files, dict of pattern_name -> matches for debugging)
               The diagnostics dict helps debug why files weren't extracted.

    Note:
        JSON extraction stops early if successful. Regex patterns are cumulative
        and may produce duplicates (deduplicated by caller).
    """
```

### Why This Matters

When 0 files are extracted despite Claude outputting valid paths, maintainers need to understand the extraction cascade to diagnose which pattern failed.

---

## M4: Implicit Data Format Assumptions in run_search.py

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `scripts/codebase-search-vdd/run_search.py:57-67`

### The Problem

The code builds a `theme_data` dict with specific keys assumed by `explore_for_theme`, but the expected schema isn't documented. If the upstream method signature changes, this will break silently.

### The Maintainer's Test

- Can I understand without author? Partially
- Can I debug at 2am? No - "which keys does explore_for_theme need?"
- Can I change without fear? No - might miss required keys
- Will this make sense in 6 months? Probably

### Current Code

```python
# Build theme-like data structure for existing search logic
# The existing logic expects theme_data with component, symptoms, user_intent
theme_data = {
    "component": product_area,
    "product_area": product_area,
    "symptoms": [issue_summary],
    "user_intent": issue_summary,
}
```

### Suggested Improvement

```python
# Build theme-like data structure for existing search logic.
# Required by CodebaseContextProvider.explore_for_theme():
#   - component: str - Product area for routing (maps to AREA_CONFIG)
#   - product_area: str - Same as component (redundant but expected)
#   - symptoms: list[str] - Keywords/phrases to search for
#   - user_intent: str - Natural language description of the issue
# Optional keys (not used here): priority, related_themes
theme_data = {
    "component": product_area,
    "product_area": product_area,  # TODO: Consolidate with component
    "symptoms": [issue_summary],
    "user_intent": issue_summary,
}
```

### Why This Matters

When `explore_for_theme` changes its expected input format, this is one of the callsites that will break. Documenting the contract makes maintenance easier.

---

## M5: Inconsistent Timeout Values Without Explanation

**Severity**: LOW | **Confidence**: High | **Scope**: Systemic

**File**: Multiple files

### The Problem

Different timeout values appear across files (300s, 600s, 120s, 30s) without consistent reasoning:

- `apply_learnings.py:275` - 300s (5 min) for analysis
- `evaluate_results_v2.py:338` - 600s (10 min) for exploration
- `evaluate_results_v2.py:489` - 300s (5 min) for judge
- `init_playwright_session.py:105` - 120000ms (2 min) for login wait

### The Maintainer's Test

- Can I understand without author? No - why 600s for exploration but 300s for analysis?
- Can I debug at 2am? No - if things timeout, should I increase?
- Can I change without fear? No - might cause resource issues
- Will this make sense in 6 months? No

### Current Code

```python
timeout=600,  # 10 minute timeout for interactive exploration
# ...
timeout=300,  # 5 minute timeout for judge (needs time for 100+ files)
```

### Suggested Improvement

Create a shared timeout config or add reasoning:

```python
# Timeout hierarchy (longer tasks get more time):
# - Exploration: 10 min - Model explores entire codebase, many tool calls
# - Analysis: 5 min - Single prompt/response, but complex reasoning
# - Judge: 5 min - May evaluate 100+ files, but simpler per-file logic
# - Login wait: 2 min - Human interaction, includes 2FA
EXPLORATION_TIMEOUT_SECONDS = 600
ANALYSIS_TIMEOUT_SECONDS = 300
JUDGE_TIMEOUT_SECONDS = 300
```

### Why This Matters

When operations timeout in production, maintainers need to know whether increasing the timeout is safe or if the operation itself is broken.

---

## M6: Shell Script Without Error Messages for Non-Zero Exit

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `scripts/codebase-search-vdd/run_vdd_loop.sh:360-422`

### The Problem

The validation gate section checks multiple conditions but doesn't log which specific check failed until after the generic error message. If Python syntax check fails, users see "VALIDATION FAILED" before understanding why.

### The Maintainer's Test

- Can I understand without author? Yes
- Can I debug at 2am? Partially - error type is logged but not first
- Can I change without fear? Yes
- Will this make sense in 6 months? Yes

### Current Code

```bash
if python3 -m py_compile "$SEARCH_PROVIDER" 2>/dev/null; then
    echo "      Syntax valid"
else
    echo "      SYNTAX ERROR - Code cannot be parsed"
    VALIDATION_FAILED=true
    FAILURE_TYPE="syntax"
fi
```

### Suggested Improvement

```bash
echo "[1/3] Checking Python syntax..."
# Capture stderr for better error messages
syntax_error=$(python3 -m py_compile "$SEARCH_PROVIDER" 2>&1)
if [ $? -eq 0 ]; then
    echo "      Syntax valid"
else
    echo "      SYNTAX ERROR - Code cannot be parsed"
    echo "      Error: $syntax_error"
    VALIDATION_FAILED=true
    FAILURE_TYPE="syntax"
fi
```

### Why This Matters

Developers running the VDD loop will immediately see the actual Python syntax error instead of having to re-run the command manually.

---

## M7: Config File Without Schema Validation Comment

**Severity**: LOW | **Confidence**: Medium | **Scope**: Isolated

**File**: `scripts/codebase-search-vdd/config.json:1-83`

### The Problem

The config file has many interrelated values (thresholds, batch sizes, iterations) but no comment or reference explaining valid ranges or dependencies.

### The Maintainer's Test

- Can I understand without author? Partially
- Can I debug at 2am? No - "is baseline_batch_size 5 too small?"
- Can I change without fear? No - might violate hidden constraints
- Will this make sense in 6 months? Probably

### Suggested Improvement

Add a README or schema comments (JSON5 format or adjacent .md file):

```markdown
# config.json Schema

## Iteration Control

- `min_iterations`: Minimum before checking convergence (2-5 typical)
- `max_iterations`: Hard stop (3-10, higher = more API cost)
- `baseline_batch_size`: Initial measurement sample (35 recommended for statistical significance)
- `iteration_batch_size`: Per-iteration sample (18-35, smaller = faster iterations)

## Thresholds

- `precision_threshold`: Minimum acceptable precision (0.0-1.0, default 0.8)
- `recall_threshold`: Minimum acceptable recall (0.0-1.0, default 0.7)
- `calibration_overlap_threshold`: Model agreement rate (0.7-1.0, 0.9 = 90% overlap)
```

### Why This Matters

Config files are often modified by operators who didn't write the system. Inline or adjacent documentation prevents misconfigurations.

---

## Summary Statistics

| Severity | Count |
| -------- | ----- |
| CRITICAL | 0     |
| HIGH     | 0     |
| MEDIUM   | 2     |
| LOW      | 5     |

**Total Issues**: 7

All issues are maintainability improvements, none are blocking bugs. The code will function correctly but may be harder to maintain or debug without these clarifications.
