# Story Grouping Architecture

## Problem Statement

Our current theme extraction pipeline groups conversations by `issue_signature`, but this produces groupings that aren't implementation-ready. Example: two conversations grouped under `instagram_oauth_multi_account` were actually:

- One about **reconnecting Pinterest** (different platform entirely)
- One about **disconnecting Instagram** (opposite user goal)

A PM or Tech Lead would never put these in the same sprint ticket.

## Design Goals

1. **Implementation-ready groupings** - Each story should be one actionable ticket
2. **Same root cause** - Conversations in a group share the same underlying issue
3. **Same fix** - One implementation would address all conversations in the group
4. **Atomic** - Can't be reasonably split further

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Theme Extraction (per-conversation)               │
│  - Extract theme, symptoms, intent                          │
│  - Initial signature assignment from vocabulary             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: Initial Grouping + Confidence Scoring             │
│  - Group by signature                                       │
│  - Score each group (semantic similarity, overlap)          │
│  - Sort by confidence DESC                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: PM/Tech Lead Review (iterative)                   │
│  For each group (highest confidence first):                 │
│    - Pass: conversations + product context + vocabulary     │
│    - Ask: "Same implementation ticket? If not, split how?"  │
│    - If split → attempt orphan rehoming to validated groups │
│    - Mark group as validated                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: Story Creation                                    │
│  - Only from validated groups                               │
│  - Include PM reasoning in description                      │
│  - Flag low-confidence or singleton groups for human review │
└─────────────────────────────────────────────────────────────┘
```

## Phase Details

### Phase 1: Theme Extraction (Existing)

Uses `ThemeExtractor` with vocabulary to extract per-conversation:

- `issue_signature` - Initial theme assignment
- `product_area` - Product area (billing, scheduling, etc.)
- `component` - Specific component
- `user_intent` - What user was trying to do
- `symptoms` - Observable symptoms
- `affected_flow` - User journey that's broken
- `root_cause_hypothesis` - Technical guess

**Source:** `src/theme_extractor.py`

### Phase 2: Confidence Scoring (New)

After initial grouping by signature, score each group's coherence.

**Confidence Signals (calibrated 2026-01-08):**

| Signal              | Weight | Description                                               |
| ------------------- | ------ | --------------------------------------------------------- |
| Semantic similarity | 30%    | Cosine similarity of conversation embeddings within group |
| Intent similarity   | 20%    | Semantic similarity of user_intent fields                 |
| Intent homogeneity  | 15%    | Penalizes high variance in intents (clusters = bad)       |
| Symptom overlap     | 10%    | Jaccard similarity of symptom keywords (low signal)       |
| Product area match  | 10%    | All conversations same product_area                       |
| Component match     | 10%    | All conversations same component                          |
| Platform uniformity | 5%     | All conversations about same platform (Pinterest/IG/FB)   |

**Score Calculation:**

```python
confidence = (
    0.30 * embedding_similarity +
    0.20 * intent_similarity +
    0.15 * intent_homogeneity +      # NEW: mean * (1 - std * 2)
    0.10 * symptom_overlap +          # Reduced - not discriminative
    0.10 * (1.0 if same_product_area else 0.0) +
    0.10 * (1.0 if same_component else 0.0) +
    0.05 * platform_uniformity        # NEW: detects platform mixing
)
```

**Key calibration learnings:**

- Symptom overlap scores were 0.06-0.15 across all groups - not discriminative, reduced weight
- Intent similarity alone doesn't capture diversity - added homogeneity to detect variance
- Platform mixing (Pinterest vs Instagram) was a major source of bad groupings - added detection

**Output:** Groups sorted by confidence score (0-100), highest first.

### Phase 3: PM/Tech Lead Review (New)

Iterative review process with orphan rehoming.

**Process:**

```
validated_groups = []
orphan_pool = []

for group in sorted_groups_by_confidence_desc:
    # Include any orphans that might fit
    candidates = group.conversations + relevant_orphans(orphan_pool, group)

    result = pm_review(candidates, product_context)

    if result.decision == "keep_together":
        validated_groups.append(group)
    else:
        # Split into sub-groups
        for sub_group in result.sub_groups:
            if sub_group.size >= MIN_GROUP_SIZE:
                validated_groups.append(sub_group)
            else:
                orphan_pool.extend(sub_group.conversations)

        # Try to rehome orphans to already-validated groups
        rehome_orphans(orphan_pool, validated_groups)
```

**PM/Tech Lead Prompt:**

```
You are a PM reviewing tickets before sprint planning for Tailwind, a social media
scheduling tool.

## Product Context
{product_context_summary}

## Proposed Grouping
Signature: {signature}
Conversations: {count}

{for each conversation}
### Conversation {i}
- User Intent: {intent}
- Symptoms: {symptoms}
- Affected Flow: {affected_flow}
- Excerpt: {excerpt}
{end for}

## Your Task
Would you put ALL of these in ONE implementation ticket? Consider:
1. Same root cause? (Would one fix address all of these?)
2. Same implementation surface? (Same code area, same team?)
3. Same user goal? (Users trying to accomplish the same thing?)

## Response Format
{
  "decision": "keep_together" | "split",
  "reasoning": "Brief explanation",
  "sub_groups": [  // Only if split
    {
      "suggested_signature": "more_specific_name",
      "conversation_ids": ["id1", "id2"],
      "rationale": "Why these belong together"
    }
  ],
  "orphans": [  // Conversations that don't fit anywhere
    {
      "conversation_id": "id",
      "suggested_home": "existing_signature or 'new_group_needed'",
      "rationale": "Why"
    }
  ]
}
```

**Orphan Rehoming Logic:**

When an orphan is created:

1. Check semantic similarity to all validated groups
2. If similarity > threshold (0.85), suggest as candidate
3. Re-run PM review on that group + orphan candidate
4. If still coherent, add orphan to group

### Phase 4: Story Creation

Only create stories from validated groups.

**Story Content:**

- Title: `[{count}] {signature}`
- PM reasoning included in description
- Confidence score shown
- Flag if:
  - Singleton group (only 1 conversation)
  - Low confidence (< 70%)
  - Contains rehomed orphans

## Validation Results (Ground Truth Comparison)

### Dataset

- **169 conversations** from ground truth with known human groupings
- **27 human groups** (story_id based, ≥3 conversations each)
- **20 pipeline groups** after PM review

### Quantitative Metrics

| Metric             | Value      | Interpretation                                   |
| ------------------ | ---------- | ------------------------------------------------ |
| Pairwise Precision | 35.6%      | Of 278 pairs we create, 99 match human groupings |
| Pairwise Recall    | 10.6%      | Of 934 human pairs, we find 99                   |
| F1 Score           | 16.3%      | Harmonic mean                                    |
| Pure Groups        | 9/20 (45%) | Groups that perfectly match one human story_id   |

### Key Finding: Different Purposes, Different Granularity

| Approach         | Purpose               | Avg Group Size | Appropriate For          |
| ---------------- | --------------------- | -------------- | ------------------------ |
| Human (story_id) | Triage assignment     | 6.3            | "Send to extension team" |
| Our Pipeline     | Sprint implementation | 4.6            | "One PR, one developer"  |

**Low recall is expected and correct** - humans group broadly for triage, we group narrowly for implementation per INVEST criteria.

### Accuracy Assessment by Category

| Category          | Count | Assessment              | Evidence                                     |
| ----------------- | ----- | ----------------------- | -------------------------------------------- |
| Pure groups       | 9/20  | ✅ Implementation-ready | Same fix would address all                   |
| Over-split cases  | 7/20  | ✅ Actually correct     | Human groups violate "Small" criterion       |
| Under-split cases | 4/20  | ⚠️ Need improvement     | `pin_scheduler_scheduling_failure` too broad |

### Example Analysis: Story 88 (Extension Issues)

Humans grouped 35 extension conversations together. We split into 7 signatures:

| Our Signature                               | Count | Same PR?             |
| ------------------------------------------- | ----- | -------------------- |
| `extension_installation_availability_issue` | 4     | PR #1: Install flow  |
| `extension_chrome_integration_issue`        | 4     | PR #2: Chrome API    |
| `extension_ui_loading_issue`                | 5     | PR #3: UI rendering  |
| `extension_functionality_missing`           | 5     | PR #4: Feature gaps  |
| `extension_pinterest_integration_issue`     | 3     | PR #5: Pinterest API |

**Assessment**: Our splitting is correct per INVEST standard - these are genuinely different implementation areas requiring different fixes.

### Target Metrics

| Metric         | Current | Target | Rationale                      |
| -------------- | ------- | ------ | ------------------------------ |
| Group Purity   | 45%     | 70%+   | Implementation-ready threshold |
| Avg Group Size | 4.6     | 3-6    | Sprint-sized stories           |
| Precision      | 35.6%   | 50%+   | Reduce over-grouping           |

### Improvement Areas

1. **Scheduler symptom extraction** - `pin_scheduler_scheduling_failure` groups 16 conversations from 6 different bugs
2. **Error code extraction** - Would help disambiguate similar symptoms
3. **Do NOT target high recall** - Different purpose than human triage

---

## Implementation Plan

### Step 1: PM/Tech Lead Prompt Testing ✅

- [x] Draft prompt
- [x] Test on 9 groupings (full valid set)
- [x] Refine based on results (tested size-aware variant, reverted)

### Step 2: Confidence Scoring ✅

- [x] Implement embedding-based similarity
- [x] Implement symptom/intent overlap
- [x] Add intent homogeneity signal
- [x] Add platform uniformity signal
- [x] Test scoring on known good/bad groupings
- [x] Calibrate weights based on PM review correlation

### Step 3: Review Pipeline (In Progress)

- [x] Implement batch PM review runner
- [ ] Implement orphan persistence (accumulate over time)
- [ ] Implement orphan matching on new extractions
- [ ] Integration tests

### Step 4: Validation

- [ ] Run against ground truth data (if available)
- [ ] Measure metrics
- [ ] Iterate on thresholds

## Decisions

1. **MIN_GROUP_SIZE = 3** - Minimum 3 conversations for a valid group
2. **Orphan fate** - Orphans wait in pool for future runs; may match with new conversations to reach 3+
3. **Confidence threshold** - See calibration results below
4. **Batch vs Individual** - Will test if batching PM reviews degrades quality vs individual calls

## Calibration Results (2026-01-08)

### Test Dataset

- **258 conversations** extracted from 30-day Intercom history
- **31 unique signatures** identified
- **9 valid groups** (≥3 conversations, excluding `unclassified_needs_review`)

### PM Review Results (with improved confidence scoring)

| Signature                         | Confidence | Platform | PM Decision | Valid Sub-groups | Orphans |
| --------------------------------- | ---------- | -------- | ----------- | ---------------- | ------- |
| billing_refund_request            | 66.1       | 1.0      | **KEEP**    | -                | 0       |
| billing_cancellation_request      | 61.6       | 0.5      | SPLIT       | 4 (47,7,4,5)     | 0       |
| pinterest_publishing_failure      | 60.1       | 1.0      | SPLIT       | 1 (11)           | 3       |
| billing_unexpected_charge         | 57.8       | 1.0      | SPLIT       | 1 (3)            | 1       |
| ghostwriter_timeout_error         | 56.4       | 1.0      | SPLIT       | 0                | 2       |
| instagram_oauth_multi_account     | 55.5       | **0.33** | SPLIT       | 0                | 3       |
| billing_payment_failure           | 55.2       | 1.0      | SPLIT       | 0                | 3       |
| billing_settings_guidance         | 54.6       | 1.0      | SPLIT       | 0                | 2       |
| analytics_interpretation_question | 47.7       | 1.0      | SPLIT       | 0                | 3       |

**Result: 1 of 9 groups (11%) passed PM review unchanged.**

### Outputs

- **1 validated group** kept as-is (`billing_refund_request`)
- **6 valid sub-groups** created from splits (≥3 conversations each)
- **17 orphan sub-groups** (<3 conversations) - legitimate distinct issues with low volume

### Key Insights

1. **Confidence scoring is for prioritization, not decision-making.** All groups require PM review regardless of score. Higher scores just mean process first.

2. **Platform uniformity detects bad groupings.** `instagram_oauth_multi_account` scored 0.33 (3 platforms mixed) - correctly flagged as problematic.

3. **Orphans are legitimate issues, not over-splitting.** Manual review confirmed orphan sub-groups represent genuinely distinct implementation surfaces (e.g., Pinterest OAuth ≠ Instagram OAuth ≠ Facebook OAuth).

4. **Size-aware prompts backfire.** Tested prompt modifications to reduce orphans - resulted in keeping groups together that genuinely needed splitting. Reverted to original prompt.

### Calibrated Thresholds

| Purpose            | Threshold | Action                                      |
| ------------------ | --------- | ------------------------------------------- |
| **Prioritization** | Sort DESC | Process high-confidence groups first        |
| **Extra scrutiny** | < 45      | Flag for additional human review            |
| **Auto-reject**    | < 20      | Only `unclassified_needs_review` falls here |
| **Auto-approve**   | None      | All groups require PM review                |

### Orphan Handling Strategy

**Decision: Accumulate over time.**

Orphans (sub-groups with <3 conversations) are stored and carried forward to future extraction runs. When new conversations match an existing orphan signature, they accumulate until reaching MIN_GROUP_SIZE (3), at which point they become valid groups for story creation.

This approach:

- Avoids creating low-signal tickets from singletons
- Preserves legitimate distinct issues that happen to be low-volume
- Allows patterns to emerge over multiple extraction cycles

### Implementation Files

- `src/confidence_scorer.py` - Confidence scoring with calibrated signals
- `scripts/run_pm_review_all.py` - PM review batch runner
- `data/pm_review_results.json` - Full PM review outputs
- `data/theme_extraction_results.jsonl` - Source data (258 conversations)

## References

- `src/theme_extractor.py` - Current theme extraction
- `config/theme_vocabulary.json` - 78 theme signatures
- `context/product/*.md` - Product context for PM prompt
- `data/phase5_ground_truth.jsonl` - Validation data (if exists)
