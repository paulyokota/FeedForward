# Categorization System Improvements - Implementation Plan

**Date**: 2026-01-07
**Based on**: Categorization Effectiveness Evaluation (6.5/10 score)
**Priority**: High (addresses critical quality issues)

## Executive Summary

This document outlines immediate improvements to reduce "other" category usage from 22.6% to <10% and improve issue signature specificity from 39.7% generic to <20%.

**Estimated Impact**:

- "Other" category: -12.6% (from 22.6% to <10%)
- Generic signatures: -19.7% (from 39.7% to <20%)
- Improved actionability for support team
- Better documentation gap identification

**Estimated Effort**: 2-3 days implementation + 1 week testing

## Problem Statement

### Issue 1: High "Other" Category Usage (22.6%)

**Root Causes**:

1. **Misdirected Inquiries** (16 conversations): Users contacting wrong company/product
2. **Missing Product Area** (13 conversations): Professional services not in vocabulary
3. **Vague Conversations** (29 conversations): Generic product questions without specific context

**Impact**:

- Reduces actionability of analytics
- Makes it harder to identify documentation gaps
- Support team can't easily categorize/prioritize

### Issue 2: Generic Issue Signatures (39.7%)

**Examples**:

- `account_settings_guidance` (appears 13 times across 2 components)
- `general_product_question` (7 conversations)
- `scheduling_feature_question` (11 conversations)
- `professional_services_inquiry` (component = signature)

**Root Cause**: Theme extraction prompt allows fallback to generic terms like "question", "inquiry", "guidance" when conversation lacks specific signals.

**Impact**:

- Low actionability for engineering (what to fix?)
- Difficult to prioritize documentation creation
- Hard to detect duplicate issues

## Proposed Changes

### Change 1: Add Professional Services Product Area

**Rationale**: 13 conversations (5.1% of themes) are about professional services but fall into "other" category.

**Implementation**:

**File**: `config/theme_vocabulary.json`

**Before**:

```json
"System wide": [
  "professional_services_inquiry",
  ...
]
```

**After**:

```json
"Professional Services": [
  "consulting_inquiry",
  "done_for_you_services_inquiry",
  "training_request",
  "custom_development_inquiry",
  "professional_services_pricing"
]
```

**URL Mapping** (add):

```json
"/services": "Professional Services",
"/professional-services": "Professional Services",
"/consulting": "Professional Services"
```

**Expected Impact**: Reduces "other" by 5.1%

### Change 2: Improve Issue Signature Quality Guidelines

**Implementation**:

**File**: `src/theme_extractor.py`

Update `FLEXIBLE_SIGNATURE_INSTRUCTIONS` from:

```python
FLEXIBLE_SIGNATURE_INSTRUCTIONS = """IMPORTANT - Follow this decision process:
   a) First, check if this matches any KNOWN THEME above (same root issue, even if worded differently)
   b) If yes, use that exact signature
   c) If no match, create a new canonical signature (lowercase, underscores, format: [feature]_[problem])"""
```

To:

```python
FLEXIBLE_SIGNATURE_INSTRUCTIONS = """IMPORTANT - Create SPECIFIC, ACTIONABLE signatures:

**Decision Process**:
   a) First, check if this matches any KNOWN THEME above (same root issue, even if worded differently)
   b) If yes, use that exact signature
   c) If no match, create a new canonical signature following these rules:

**Signature Quality Rules**:
   ✅ DO: Be specific about the PROBLEM
      - "csv_import_encoding_error" (specific)
      - "ghostwriter_timeout_error" (specific)
      - "pinterest_board_permission_denied" (specific)

   ❌ DON'T: Use generic terms
      - NOT "account_settings_guidance" → "account_email_change_failure"
      - NOT "scheduling_feature_question" → "pin_spacing_interval_unclear"
      - NOT "general_product_question" → identify specific product first

   **Format**: [feature]_[specific_problem] (lowercase, underscores)
   **Avoid**: "question", "inquiry", "guidance", "general", "issue"
   **Include**: Actual error, symptom, or specific failure mode"""
```

**Expected Impact**: Reduces generic signatures by 15-20%

### Change 3: Add Signature Quality Examples to Vocabulary

**Implementation**:

**File**: `config/theme_vocabulary.json`

Add new section before `product_area_mapping`:

```json
"signature_quality_guidelines": {
  "_comment": "Examples of good vs bad signatures to guide LLM",
  "good_examples": [
    {
      "signature": "billing_cancellation_request",
      "why": "Specific action (cancellation) within billing"
    },
    {
      "signature": "csv_import_encoding_error",
      "why": "Specific error type (encoding) within CSV import"
    },
    {
      "signature": "pinterest_board_permission_denied",
      "why": "Specific error (permission denied) for specific action (board access)"
    },
    {
      "signature": "ghostwriter_timeout_error",
      "why": "Specific failure mode (timeout) for feature"
    }
  ],
  "bad_examples": [
    {
      "signature": "account_settings_guidance",
      "why_bad": "Too generic - what specific setting? What problem?",
      "better": "account_email_change_failure"
    },
    {
      "signature": "scheduling_feature_question",
      "why_bad": "Generic 'question' - what specific aspect of scheduling?",
      "better": "pin_spacing_interval_unclear"
    },
    {
      "signature": "general_product_question",
      "why_bad": "Completely generic - no product area or problem specified",
      "better": "identify_specific_product_first"
    }
  ]
}
```

Update theme extraction prompt to reference these:

```python
# In THEME_EXTRACTION_PROMPT, add before "## Conversation":
## Signature Quality Guidelines

{signature_quality_examples}

Remember: Signatures should be ACTIONABLE for engineering/documentation teams.
Generic terms like "question", "guidance", "inquiry" provide no value.
```

**Expected Impact**: Reduces generic signatures by additional 5-10%

### Change 4: Add Misdirected Inquiry Pre-Filter

**Rationale**: 16 conversations (6.2%) are users contacting the wrong company/product. These should be filtered earlier in the pipeline.

**Implementation**:

**New File**: `src/misdirected_filter.py`

```python
"""
Misdirected Inquiry Filter

Identifies conversations where users are contacting the wrong company/product
before full theme extraction runs.
"""

import re
from typing import Optional

COMPETITOR_PATTERNS = [
    r'\bhootsuite\b',
    r'\bbuffer\b',
    r'\blater\.com\b',
    r'\bplanoly\b',
    r'\bsprout\s*social\b',
    # Add more competitors as identified
]

UNRELATED_PRODUCT_PATTERNS = [
    r'\bshopify\s+support\b',  # Looking for Shopify, not our Shopify integration
    r'\bpinterest\s+support\b',  # Looking for Pinterest support, not scheduling
    r'\binstagram\s+support\b',
    # Add more patterns as identified
]

def is_misdirected_inquiry(customer_message: str, source_body: str = None) -> Optional[str]:
    """
    Check if conversation is a misdirected inquiry.

    Returns:
        Reason string if misdirected, None otherwise
    """
    text = (customer_message + " " + (source_body or "")).lower()

    # Check for competitor mentions
    for pattern in COMPETITOR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return f"competitor_mention:{re.search(pattern, text, re.IGNORECASE).group()}"

    # Check for unrelated product support requests
    for pattern in UNRELATED_PRODUCT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return f"unrelated_product:{re.search(pattern, text, re.IGNORECASE).group()}"

    return None
```

**Integration Point**: Add to pipeline BEFORE theme extraction:

```python
# In main pipeline
misdirected_reason = is_misdirected_inquiry(conv.source_body, conv.customer_message)
if misdirected_reason:
    # Skip theme extraction, mark as misdirected
    conv.misdirected = True
    conv.misdirected_reason = misdirected_reason
    # Auto-respond or route to human review
else:
    # Proceed with theme extraction
    theme = extractor.extract_theme(conv)
```

**Expected Impact**: Reduces "other" by 6.2%

### Change 5: Update Stage 1 Confidence Criteria (Lower Priority)

**Current Issue**: Only 0.6% of conversations are "high" confidence (should be >60%)

**Root Cause**: Stage 1 confidence criteria are too strict or unclear

**Implementation**: (Details to be added after reviewing Stage 1 code more thoroughly)

**Deferred**: This requires more investigation and doesn't directly address the two critical issues (other% and generic signatures). Tackle after immediate fixes.

## Implementation Priority

### Phase 1: Immediate (This Week)

1. ✅ Add Professional Services product area to vocabulary
2. ✅ Update signature quality guidelines in theme extractor
3. ✅ Add signature examples to vocabulary
4. ⏳ Test on 20-30 sample conversations

**Estimated Effort**: 1-2 days

### Phase 2: Near-Term (Next Week)

1. Implement misdirected inquiry filter
2. Run full regression testing on all 257 conversations
3. Measure improvement metrics
4. Update documentation

**Estimated Effort**: 2-3 days

### Phase 3: Follow-Up (Next Month)

1. Review Stage 1 confidence scoring
2. Monitor "other" and generic signature rates weekly
3. Identify new patterns requiring vocabulary expansion

**Estimated Effort**: Ongoing

## Success Metrics

### Before (Baseline)

| Metric                           | Current | Target            |
| -------------------------------- | ------- | ----------------- |
| "Other" category                 | 22.6%   | <10%              |
| Generic signatures               | 39.7%   | <20%              |
| Professional services in "other" | 5.1%    | 0% (new category) |
| Misdirected inquiries            | 6.2%    | <2% (filtered)    |

### After (Expected)

| Metric                | Expected            | Improvement          |
| --------------------- | ------------------- | -------------------- |
| "Other" category      | <10%                | -12.6% ✅            |
| Generic signatures    | <20%                | -19.7% ✅            |
| Professional services | 5.1% (new category) | Properly categorized |
| Misdirected inquiries | <2%                 | Auto-filtered        |

## Testing Plan

### Unit Tests

1. Test professional services vocabulary matching
2. Test signature quality validation
3. Test misdirected inquiry filter patterns

### Integration Tests

1. Re-run theme extraction on 20-30 sample conversations
2. Compare before/after signatures for quality
3. Measure "other" category reduction

### Validation

1. Manual review of 10 sample themes
2. Verify signatures are more specific
3. Confirm professional services properly categorized

## Rollout Plan

### Step 1: Code Changes (Day 1)

- Update `config/theme_vocabulary.json`
- Update `src/theme_extractor.py`
- Create `src/misdirected_filter.py`

### Step 2: Testing (Day 2)

- Run on test dataset
- Validate improvements
- Adjust patterns/thresholds

### Step 3: Documentation (Day 3)

- Update PLAN.md with improvements
- Document new vocabulary sections
- Create before/after comparison report

### Step 4: Deployment (Day 4)

- Deploy to production pipeline
- Monitor metrics for 1 week
- Generate comparison report

## Risks & Mitigation

### Risk 1: Over-Filtering Misdirected Inquiries

**Mitigation**: Start with conservative patterns, log all filtered conversations, review weekly

### Risk 2: Signatures Become Too Specific (Fragmentation)

**Mitigation**: Continue using embedding-based canonicalization, monitor singleton rate

### Risk 3: Professional Services Category Too Broad

**Mitigation**: Start with clear subcategories, expand based on actual data

## Next Steps

1. Review this plan with stakeholders
2. Implement Phase 1 changes
3. Test and validate
4. Roll out to production
5. Monitor and iterate

---

**Status**: Ready for implementation
**Owner**: TBD
**Timeline**: 1 week for Phase 1, 2 weeks total
