# Theme Quality Architecture

Improving theme extraction specificity and adding PM review validation.

## Problem Statement

Theme extraction is generating signatures that are **too broad**, causing unrelated issues to be grouped together.

### Example: `pinterest_publishing_failure`

This signature grouped 4 conversations:

| Conversation                                                | Actual Issue       | Match to Signature? |
| ----------------------------------------------------------- | ------------------ | ------------------- |
| "Why my individual pins are posted twice on Pinterest"      | Duplication        | NO                  |
| "missing pins...many dozens of pins vanished"               | Missing pins       | NO                  |
| "video Pins...will not publish...issue uploading the video" | Publishing failure | YES                 |
| "video Pins keep failing to publish"                        | Publishing failure | YES                 |

**Only 2 of 4 (50%)** are actually about publishing failures. The others are completely different issues that require different fixes.

### Root Causes

1. **Theme extractor prompt allows broad signatures** - The current prompt guidance produces signatures at the wrong granularity (failure mode level vs symptom level)
2. **No validation before story creation** - Groups proceed to stories without coherence verification

## Solution Overview

Two complementary improvements:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  IMPROVEMENT 1: Tighter Theme Extraction                                     │
│  - Enhance prompt to require symptom-specific signatures                    │
│  - Add mandatory SAME_FIX test in prompt                                    │
│  - Update vocabulary with finer-grained signatures                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  IMPROVEMENT 2: PM Review Before Story Creation                              │
│  - Evaluate theme groups before creating stories                            │
│  - LLM-based coherence check: "Are these actually the same issue?"          │
│  - Suggest sub-group splits with new signatures                             │
│  - Route validated groups to story creation                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Improvement 1: Tighter Theme Extraction Signatures

### Problem Analysis

Current prompt produces signatures at the **failure mode** level:

- `pinterest_publishing_failure` (broad)

We need signatures at the **symptom** level:

- `pinterest_duplicate_pins` (specific)
- `pinterest_missing_pins` (specific)
- `pinterest_video_upload_failure` (specific)

### Design: Enhanced Signature Quality Rules

Add explicit guidance to the theme extraction prompt that enforces the SAME_FIX test.

#### New Prompt Section: Signature Specificity Rules

```markdown
## CRITICAL: Signature Specificity Rules

**The SAME_FIX Test**: Two conversations should ONLY share a signature if:

1. One code change would fix BOTH
2. One developer could own the fix
3. One acceptance test verifies both are fixed

**Signature Granularity**:

- Level 1 (TOO BROAD): `[platform]_[failure_category]`
  - Example: `pinterest_publishing_failure` ← WRONG
  - Problem: Groups duplicate pins, missing pins, and upload failures together

- Level 2 (CORRECT): `[platform]_[specific_symptom]`
  - Example: `pinterest_duplicate_pins` ← CORRECT
  - Example: `pinterest_missing_pins` ← CORRECT
  - Example: `pinterest_video_upload_failure` ← CORRECT

**Disambiguation Questions**:
Before assigning a signature, ask yourself:

1. "If two users report this, would the SAME code change fix both?"
2. "Would I need to look at DIFFERENT code paths to fix different reports?"

If answer to #2 is YES → Create more specific signature
```

#### Updated Signature Quality Examples

Add to `config/theme_vocabulary.json` under `signature_quality_guidelines`:

```json
{
  "signature_quality_guidelines": {
    "same_fix_test": {
      "description": "Signatures must pass the SAME_FIX test: one code change fixes all conversations",
      "examples": [
        {
          "scenario": "User A: pins posted twice. User B: pins not posting at all",
          "wrong": "pinterest_publishing_failure",
          "why_wrong": "Duplicate pins vs no posting require different fixes",
          "correct_a": "pinterest_duplicate_pins",
          "correct_b": "pinterest_publishing_failure"
        }
      ]
    },
    "good_examples": [
      {
        "signature": "pinterest_duplicate_pins",
        "why": "Specific symptom - pins appearing twice"
      },
      {
        "signature": "pinterest_video_upload_failure",
        "why": "Specific content type + failure mode"
      },
      {
        "signature": "ghostwriter_timeout_error",
        "why": "Specific feature + specific error type"
      }
    ],
    "bad_examples": [
      {
        "signature": "pinterest_publishing_failure",
        "why_bad": "Groups different symptoms: duplicates, missing, timeouts, auth errors",
        "better": "Use symptom-specific: pinterest_duplicate_pins, pinterest_missing_pins, etc."
      },
      {
        "signature": "scheduling_issue",
        "why_bad": "Could be timing, UI, auth, or calendar - all different fixes",
        "better": "scheduling_timezone_mismatch, scheduling_ui_drag_drop_failure, etc."
      }
    ]
  }
}
```

### Interface Contract: Enhanced Theme Output

No changes to the `Theme` dataclass structure, but the `issue_signature` field must now pass stricter validation:

```python
# In src/theme_extractor.py - Validation logic (not changing dataclass)

def validate_signature_specificity(signature: str, symptoms: list[str]) -> bool:
    """
    Validate that a signature is specific enough.

    Returns False if signature appears to be at failure-mode level
    rather than symptom level.
    """
    # Broad failure indicators that suggest over-generalization
    BROAD_SUFFIXES = [
        '_failure',  # pinterest_publishing_failure
        '_issue',    # scheduling_issue
        '_problem',  # oauth_problem
        '_error',    # api_error (unless specific like timeout_error)
    ]

    # Specific symptom indicators that are acceptable
    SPECIFIC_PATTERNS = [
        '_duplicate_',   # duplicate_pins
        '_missing_',     # missing_pins
        '_timeout_',     # timeout_error
        '_permission_',  # permission_denied
        '_encoding_',    # encoding_error
    ]

    # If signature ends with broad suffix without specific pattern, flag it
    for suffix in BROAD_SUFFIXES:
        if signature.endswith(suffix):
            has_specific = any(p in signature for p in SPECIFIC_PATTERNS)
            if not has_specific:
                return False

    return True
```

---

## Improvement 2: PM Review Before Story Creation

### Architectural Position

PM Review fits between theme grouping and story creation as a quality gate.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Current Pipeline (src/two_stage_pipeline.py)                               │
│  ┌───────────────┐    ┌─────────────────┐    ┌──────────────────────────┐  │
│  │ Classification │ →  │ Theme Extraction │ →  │ Group by Signature        │  │
│  └───────────────┘    └─────────────────┘    └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                                          │
                                                          ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  NEW: PM Review Gate                                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ PMReviewService.review_theme_group()                                   │  │
│  │   Input: signature + list of themed conversations                     │  │
│  │   Output: PMReviewResult (keep_together | split with sub-groups)      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                                          │
                                                          ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Existing: Story Creation (src/story_tracking/services/story_creation_service.py) │
│  - Already handles split results via PMReviewResult                         │
│  - Creates stories for validated groups                                     │
│  - Routes orphans (<3 conversations) to OrphanIntegrationService           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Design: PMReviewService

**Location**: `src/story_tracking/services/pm_review_service.py`

```python
"""
PM Review Service

Evaluates theme groups before story creation to ensure coherence.
Uses LLM to answer: "Would these conversations all be fixed by one implementation?"
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

class ReviewDecision(str, Enum):
    KEEP_TOGETHER = "keep_together"
    SPLIT = "split"
    REJECT = "reject"  # All conversations are too different


@dataclass
class SubGroupSuggestion:
    """A suggested sub-group when splitting."""
    suggested_signature: str
    conversation_ids: List[str]
    rationale: str

    # Metadata for tracking
    confidence: float = 0.0


@dataclass
class PMReviewResult:
    """Result of PM review for a theme group."""

    # Input identification
    original_signature: str
    conversation_count: int

    # Decision
    decision: ReviewDecision
    reasoning: str

    # If split, the suggested sub-groups
    sub_groups: List[SubGroupSuggestion] = field(default_factory=list)

    # Conversations that don't fit any sub-group (become orphans)
    orphan_conversation_ids: List[str] = field(default_factory=list)

    # Review metadata
    model_used: str = ""
    review_duration_ms: int = 0

    @property
    def passed(self) -> bool:
        """Whether the group passed review (keep_together)."""
        return self.decision == ReviewDecision.KEEP_TOGETHER


@dataclass
class ConversationContext:
    """Context for a conversation in PM review."""
    conversation_id: str
    user_intent: str
    symptoms: List[str]
    affected_flow: str
    excerpt: str
    product_area: str
    component: str


class PMReviewService:
    """
    Evaluates theme groups for coherence before story creation.

    Uses LLM to determine if conversations in a group would all be
    addressed by the same implementation.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
    ):
        self.model = model
        self.temperature = temperature
        self._client = None  # Lazy init

    def review_group(
        self,
        signature: str,
        conversations: List[ConversationContext],
        product_context: Optional[str] = None,
    ) -> PMReviewResult:
        """
        Review a theme group for coherence.

        Args:
            signature: The issue_signature for this group
            conversations: List of conversation contexts to review
            product_context: Optional product documentation for context

        Returns:
            PMReviewResult with decision and any suggested splits
        """
        # Implementation calls LLM with PM_REVIEW_PROMPT
        pass

    def review_groups_batch(
        self,
        groups: Dict[str, List[ConversationContext]],
        product_context: Optional[str] = None,
    ) -> Dict[str, PMReviewResult]:
        """
        Review multiple theme groups in batch.

        Processes groups in confidence order (highest first).
        """
        pass
```

### PM Review Prompt Design

````markdown
You are a PM reviewing potential product tickets for Tailwind, a social media scheduling tool.

## The SAME_FIX Test

A group of conversations should become ONE ticket if and only if:

1. **Same code change** - One PR would fix ALL of them
2. **Same developer** - One person could own the entire fix
3. **Same test** - One acceptance test would verify ALL are fixed

## Product Context

{product_context}

## Group Under Review

**Signature**: {signature}
**Conversation Count**: {count}

{for each conversation}

### Conversation {i}

- **User Intent**: {user_intent}
- **Symptoms**: {symptoms}
- **Affected Flow**: {affected_flow}
- **Excerpt**: "{excerpt}"
  {end for}

## Your Task

Answer this question: **"Would ONE implementation fix ALL of these?"**

Consider:

1. Are users experiencing the SAME symptom? (duplicates vs missing vs timeout are DIFFERENT)
2. Would a developer look at the SAME code to fix all of these?
3. Is there ONE root cause, or MULTIPLE distinct causes?

## Response Format

```json
{
  "decision": "keep_together" | "split",
  "reasoning": "Brief explanation of your decision",
  "same_fix_confidence": 0.0-1.0,
  "sub_groups": [
    // Only if decision is "split"
    {
      "suggested_signature": "more_specific_signature_name",
      "conversation_ids": ["id1", "id2"],
      "rationale": "Why these belong together",
      "symptom": "The specific symptom these share"
    }
  ],
  "orphans": [
    // Conversations that don't fit any sub-group
    {
      "conversation_id": "id",
      "reason": "Why this doesn't fit"
    }
  ]
}
```
````

Important:

- If conversations have DIFFERENT symptoms (duplicates vs missing), they MUST be split
- A sub-group needs at least 3 conversations to become a ticket (others become orphans)
- Be specific in suggested signatures: `pinterest_duplicate_pins` not `pinterest_issue`

````

### Integration Point: StoryCreationService

The existing `StoryCreationService.process_theme_groups()` already handles `PMReviewResult` objects with `decision` and `sub_groups` fields. We extend the integration:

**File**: `src/story_tracking/services/story_creation_service.py`

```python
# Existing imports - add:
from .pm_review_service import PMReviewService, PMReviewResult, ConversationContext

class StoryCreationService:
    def __init__(
        self,
        story_service: StoryService,
        orphan_service: OrphanService,
        evidence_service: Optional[EvidenceService] = None,
        orphan_integration_service: Optional["OrphanIntegrationService"] = None,
        confidence_scorer: Optional["ConfidenceScorer"] = None,
        pm_review_service: Optional[PMReviewService] = None,  # NEW
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        validation_enabled: bool = DEFAULT_VALIDATION_ENABLED,
        pm_review_enabled: bool = False,  # NEW: Gate for rollout
        ...
    ):
        ...
        self.pm_review_service = pm_review_service
        self.pm_review_enabled = pm_review_enabled

    def process_theme_groups(
        self,
        theme_groups: Dict[str, List[Dict[str, Any]]],
        pipeline_run_id: Optional[int] = None,
    ) -> ProcessingResult:
        """
        Process theme groups with optional PM review.

        If pm_review_enabled:
        1. Run quality gates (existing)
        2. Run PM review on groups that pass quality gates
        3. Process PM review results (keep/split)
        4. Create stories from validated groups
        """
        result = ProcessingResult()

        for signature, conv_dicts in theme_groups.items():
            # ... existing quality gate logic ...

            # NEW: PM Review gate (after quality gates pass)
            if self.pm_review_enabled and self.pm_review_service:
                pm_result = self._run_pm_review(signature, conversations)

                if pm_result.decision == ReviewDecision.SPLIT:
                    self._handle_pm_split(pm_result, result, pipeline_run_id)
                    continue

            # ... existing story creation logic ...
````

### Data Flow

```
Theme Groups (Dict[signature, List[conversations]])
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│  Quality Gates (existing)                                      │
│  - Evidence validation                                         │
│  - Confidence scoring                                          │
│  - Min group size check                                        │
│                                                                │
│  FAIL → Route to OrphanIntegrationService                     │
│  PASS → Continue to PM Review                                 │
└───────────────────────────────────────────────────────────────┘
        │ (groups that passed quality gates)
        ▼
┌───────────────────────────────────────────────────────────────┐
│  PM Review Gate (NEW)                                          │
│  - Build ConversationContext for each conversation            │
│  - Call PMReviewService.review_group()                        │
│  - Evaluate SAME_FIX test via LLM                             │
│                                                                │
│  KEEP_TOGETHER → Continue to story creation                   │
│  SPLIT → Process sub-groups:                                  │
│    - Sub-groups with ≥3 convos → New signatures, create stories│
│    - Sub-groups with <3 convos → Route to OrphanIntegration   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│  Story Creation (existing)                                     │
│  - StoryCreationService._create_story_with_evidence()         │
│  - Include PM review reasoning in description                 │
└───────────────────────────────────────────────────────────────┘
```

---

## Interface Contracts

### PMReviewService Interface

```python
# src/story_tracking/services/pm_review_service.py

@dataclass
class ConversationContext:
    """Minimal context needed for PM review."""
    conversation_id: str
    user_intent: str
    symptoms: List[str]
    affected_flow: str
    excerpt: str
    product_area: str
    component: str


@dataclass
class SubGroupSuggestion:
    """A suggested sub-group from PM review split."""
    suggested_signature: str
    conversation_ids: List[str]
    rationale: str
    confidence: float = 0.0


@dataclass
class PMReviewResult:
    """Complete PM review result."""
    original_signature: str
    conversation_count: int
    decision: ReviewDecision  # keep_together | split | reject
    reasoning: str
    sub_groups: List[SubGroupSuggestion] = field(default_factory=list)
    orphan_conversation_ids: List[str] = field(default_factory=list)
    model_used: str = ""
    review_duration_ms: int = 0


class PMReviewService:
    def review_group(
        self,
        signature: str,
        conversations: List[ConversationContext],
        product_context: Optional[str] = None,
    ) -> PMReviewResult:
        """Review a single theme group."""
        ...

    def review_groups_batch(
        self,
        groups: Dict[str, List[ConversationContext]],
        product_context: Optional[str] = None,
    ) -> Dict[str, PMReviewResult]:
        """Review multiple groups, ordered by confidence."""
        ...
```

### Extended StoryCreationService Interface

```python
# Updates to src/story_tracking/services/story_creation_service.py

class StoryCreationService:
    def __init__(
        self,
        ...,
        pm_review_service: Optional[PMReviewService] = None,
        pm_review_enabled: bool = False,
    ):
        ...

    def process_theme_groups(
        self,
        theme_groups: Dict[str, List[Dict[str, Any]]],
        pipeline_run_id: Optional[int] = None,
    ) -> ProcessingResult:
        """
        Now includes PM review step when enabled.

        ProcessingResult extended with:
        - pm_review_splits: int  # Groups that were split by PM review
        - pm_review_kept: int    # Groups kept together by PM review
        """
        ...


# Extended ProcessingResult
@dataclass
class ProcessingResult:
    stories_created: int = 0
    orphans_created: int = 0
    stories_updated: int = 0
    orphans_updated: int = 0
    errors: List[str] = field(default_factory=list)
    created_story_ids: List[UUID] = field(default_factory=list)
    created_orphan_ids: List[UUID] = field(default_factory=list)
    quality_gate_rejections: int = 0
    orphan_fallbacks: int = 0
    # NEW: PM Review metrics
    pm_review_splits: int = 0
    pm_review_kept: int = 0
    pm_review_skipped: int = 0  # Groups that bypassed review
```

### Theme Extractor Enhancements

```python
# Updates to src/theme_extractor.py

# New validation function
def validate_signature_specificity(
    signature: str,
    symptoms: List[str],
) -> Tuple[bool, Optional[str]]:
    """
    Validate signature is specific enough.

    Returns:
        (is_valid, suggestion) - suggestion is a more specific signature if invalid
    """
    ...

# Updated extract method signature (no breaking changes)
class ThemeExtractor:
    def extract(
        self,
        conv: Conversation,
        canonicalize: bool = True,
        use_embedding: bool = False,
        auto_add_to_vocabulary: bool = False,
        strict_mode: bool = False,
        validate_specificity: bool = True,  # NEW: Enable specificity validation
    ) -> Theme:
        """
        Now includes optional signature specificity validation.

        If validate_specificity=True and signature fails validation,
        logs a warning but does not block (for backwards compatibility).
        """
        ...
```

---

## Agent Assignments

### Kai (Prompt Engineering)

**Domain**: Theme extraction prompt changes, vocabulary updates

**Files Owned**:

- `src/theme_extractor.py` - Prompt modifications and specificity validation
- `config/theme_vocabulary.json` - Signature quality guidelines and new fine-grained signatures
- Any new prompt files created for PM review

**Tasks**:

1. Update `THEME_EXTRACTION_PROMPT` with SAME_FIX test guidance
2. Update `FLEXIBLE_SIGNATURE_INSTRUCTIONS` with specificity rules
3. Add `validate_signature_specificity()` function
4. Update `signature_quality_guidelines` in vocabulary JSON
5. Add new fine-grained signatures for common broad categories
6. Write `PM_REVIEW_PROMPT` for PMReviewService

**Acceptance Criteria**:

- Signatures pass SAME_FIX test (manual review of 10 extractions)
- Specificity validation catches known-bad signatures
- PM review prompt produces valid JSON responses

### Marcus (Backend)

**Domain**: PM review service implementation, StoryCreationService integration

**Files Owned**:

- `src/story_tracking/services/pm_review_service.py` (NEW)
- `src/story_tracking/services/story_creation_service.py` - PM review integration
- `tests/test_pm_review_service.py` (NEW)
- `tests/test_story_creation_service_pm_review.py` (NEW)

**Tasks**:

1. Create `PMReviewService` with `review_group()` and `review_groups_batch()`
2. Define Pydantic models: `ConversationContext`, `SubGroupSuggestion`, `PMReviewResult`
3. Integrate PM review into `StoryCreationService.process_theme_groups()`
4. Add feature flag `pm_review_enabled` for controlled rollout
5. Extend `ProcessingResult` with PM review metrics
6. Handle sub-group creation and orphan routing from PM splits

**Acceptance Criteria**:

- `PMReviewService.review_group()` returns valid `PMReviewResult`
- Sub-groups with ≥3 conversations become stories
- Sub-groups with <3 conversations route to orphan integration
- PM review can be disabled via feature flag
- All new code has unit tests with 80%+ coverage

---

## Edge Cases

### 1. Empty or Invalid LLM Response

**Scenario**: PM review LLM call returns invalid JSON or empty response

**Handling**:

- Log error with full context
- Default to `decision=keep_together` (fail-safe)
- Include error in `ProcessingResult.errors`

### 2. All Conversations Become Orphans

**Scenario**: PM review splits a group into 5 sub-groups, all with <3 conversations

**Handling**:

- All go to `orphan_integration_service`
- No story created
- Log as `pm_review_splits` but not `stories_created`

### 3. Circular Signature Suggestions

**Scenario**: PM review suggests splitting into signatures that already exist

**Handling**:

- Check against existing story signatures before creating
- If signature exists, add conversations to existing story evidence
- Track in `stories_updated` rather than `stories_created`

### 4. Timeout During PM Review

**Scenario**: LLM call times out during batch review

**Handling**:

- Catch timeout exception
- Mark group as `pm_review_skipped`
- Continue with existing confidence-based decision
- Retry in next pipeline run

### 5. Conflicting Split Suggestions

**Scenario**: PM review suggests sub-groups with overlapping conversations

**Handling**:

- Assign conversation to first sub-group it appears in (by order)
- Log warning about overlap
- Consider as data quality issue for prompt improvement

### 6. Single-Conversation Groups

**Scenario**: Group has exactly 1 conversation (below MIN_GROUP_SIZE but passed earlier filters)

**Handling**:

- Skip PM review entirely
- Route directly to orphan integration
- Already handled by existing quality gates

---

## Acceptance Criteria

### Theme Extraction Specificity

1. **Given**: A conversation about duplicate pins on Pinterest
   **When**: Theme extraction runs
   **Then**: Signature is `pinterest_duplicate_pins`, NOT `pinterest_publishing_failure`

2. **Given**: A conversation about missing pins on Pinterest
   **When**: Theme extraction runs
   **Then**: Signature is `pinterest_missing_pins`, NOT `pinterest_publishing_failure`

3. **Given**: Current broad signature like `pinterest_publishing_failure`
   **When**: Specificity validation runs
   **Then**: Returns `is_valid=False` with suggested specific signature

### PM Review Integration

4. **Given**: A theme group with 4 conversations (2 about duplicates, 2 about missing pins)
   **When**: PM review runs
   **Then**: Decision is `split` with 2 sub-groups

5. **Given**: PM review returns `split` decision
   **When**: Sub-groups have ≥3 conversations each
   **Then**: Each sub-group becomes a separate story with new signature

6. **Given**: PM review returns `split` decision
   **When**: A sub-group has <3 conversations
   **Then**: Those conversations route to orphan integration

7. **Given**: `pm_review_enabled=False`
   **When**: Theme groups are processed
   **Then**: PM review is skipped entirely, existing behavior preserved

### Metrics and Observability

8. **Given**: Pipeline run with PM review enabled
   **When**: Processing completes
   **Then**: `ProcessingResult` includes `pm_review_splits`, `pm_review_kept`, `pm_review_skipped`

9. **Given**: Any PM review execution
   **When**: Review completes
   **Then**: Logs include original signature, decision, and review duration

---

## Migration Strategy

### Phase 1: Prompt Enhancement (Low Risk)

1. Update theme extraction prompt with SAME_FIX guidance
2. Add specificity validation as warnings only (no blocking)
3. Monitor extraction quality via sampling

**Rollback**: Revert prompt changes if signature quality degrades

### Phase 2: PM Review Service (Medium Risk)

1. Implement `PMReviewService` with comprehensive tests
2. Run shadow mode: execute PM review but don't act on results
3. Log decisions for manual review
4. Compare PM decisions against human judgment

**Rollback**: Disable via feature flag

### Phase 3: Full Integration (Higher Risk)

1. Enable PM review for new pipeline runs
2. Monitor story creation quality
3. Track orphan volume (should increase initially)
4. Adjust prompt/thresholds based on results

**Rollback**: Disable feature flag, existing stories unaffected

---

## File Summary

| File                                                    | Owner  | Action                                                    |
| ------------------------------------------------------- | ------ | --------------------------------------------------------- |
| `src/theme_extractor.py`                                | Kai    | Modify: prompt enhancement, specificity validation        |
| `config/theme_vocabulary.json`                          | Kai    | Modify: signature guidelines, new fine-grained signatures |
| `src/story_tracking/services/pm_review_service.py`      | Marcus | Create: PM review service                                 |
| `src/story_tracking/services/story_creation_service.py` | Marcus | Modify: PM review integration                             |
| `tests/test_pm_review_service.py`                       | Marcus | Create: Unit tests                                        |
| `tests/test_story_creation_service_pm_review.py`        | Marcus | Create: Integration tests                                 |
| `tests/test_theme_extractor_specificity.py`             | Kai    | Create: Specificity validation tests                      |

---

## References

- `docs/story-grouping-architecture.md` - Current grouping architecture
- `docs/story-granularity-standard.md` - INVEST criteria and SAME_FIX test
- `src/story_tracking/services/story_creation_service.py` - Existing integration point
- `src/theme_extractor.py` - Current theme extraction implementation
- `config/theme_vocabulary.json` - Current vocabulary with 78 signatures
