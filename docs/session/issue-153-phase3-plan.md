# Issue #153: Phase 3 Implementation Plan

**Date**: 2026-01-30
**Status**: Ready for implementation
**Depends on**: Phase 2 outputs in `data/vocabulary_enhancement/`

---

## Objective

Codify validated term distinctions into `config/theme_vocabulary.json` to help the LLM:

1. Avoid conflating terms that look similar but have different code paths
2. Route conversations correctly based on user symptom patterns
3. Ask clarifying questions when terms are ambiguous

---

## Framework Summary

### Two-Dimensional Analysis

| Dimension        | Source                   | Question                                 |
| ---------------- | ------------------------ | ---------------------------------------- |
| **Code Path**    | Phase 2 validation       | Would one code change fix both?          |
| **User Symptom** | Theme diagnostic_summary | Do users describe problems the same way? |

Key insight: Same code path ≠ same user experience. `scheduled_pin` and `draft` share `PostFacet.put()` but have completely different symptom clusters.

---

## Decision Function

```python
def categorize_pair(jaccard, excl_ratio, name_overlap, code_path_same,
                    excl_p10, excl_p25, tolerance=0.03):
    """
    jaccard: Symptom co-occurrence (0-1)
    excl_ratio: Average exclusive symptom ratio (0-1)
    name_overlap: Boolean from has_name_overlap()
    code_path_same: Boolean from Phase 2 SAME_FIX
    excl_p10: 10th percentile of exclusivity ratios
    excl_p25: 25th percentile of exclusivity ratios
    tolerance: Buffer for near-threshold cases
    """

    # SIMILAR_UX: Shared symptom profiles (co-occurrence)
    if jaccard >= 0.15 and excl_ratio < excl_p10:
        return "SIMILAR_UX"

    # DIFFERENT_MODEL: Same code, different user concept
    if excl_ratio >= (excl_p25 - tolerance) and code_path_same and jaccard >= 0.05:
        return "DIFFERENT_MODEL"

    # NAME_CONFUSION: Naming causes confusion despite distinct symptoms
    if name_overlap and jaccard < 0.15:
        return "NAME_CONFUSION"

    # DISTINCT: No vocabulary entry needed
    return "DISTINCT"


def has_name_overlap(a, b):
    """Token overlap OR suffix match"""
    a_tokens = set(a.lower().replace('_', ' ').split())
    b_tokens = set(b.lower().replace('_', ' ').split())
    if a_tokens & b_tokens:
        return True

    suffixes = ['pin', 'account']  # Auto-derived from data
    for s in suffixes:
        if a.lower().endswith(s) and b.lower().endswith(s):
            return True
    return False
```

---

## Calibrated Thresholds (from current data)

| Parameter            | Value  | Derivation                            |
| -------------------- | ------ | ------------------------------------- |
| Jaccard "high"       | ≥ 0.15 | 90th percentile is 0.152              |
| excl_p10             | 0.516  | 10th percentile of exclusivity ratios |
| excl_p25             | 0.757  | 25th percentile of exclusivity ratios |
| excl_p25 - tolerance | 0.727  | Catches borderline cases              |
| Jaccard "minimal"    | ≥ 0.05 | Prevents noise in DIFFERENT_MODEL     |

---

## Categories and Pairs

### SIMILAR_UX (5 pairs)

**Rule**: Jaccard ≥ 0.15 AND Excl.Ratio < 0.516

| Pair                        | Jaccard | Excl.Ratio | Notes                                          |
| --------------------------- | ------- | ---------- | ---------------------------------------------- |
| title ↔ description         | 0.471   | 0.36       | Co-occurring fields in content generation      |
| account ↔ pinterest_account | 0.338   | 0.33       | Generic vs specific account reference          |
| pin ↔ board                 | 0.220   | 0.47       | Relationship co-occurrence (pins go on boards) |
| pin ↔ scheduled_pin         | 0.197   | 0.40       | Published vs queued state                      |
| account ↔ instagram_account | 0.175   | 0.41       | Generic vs specific account reference          |

**Vocabulary treatment**: "These co-occur in complaints—clarify which is affected"

### DIFFERENT_MODEL (3 pairs)

**Rule**: Excl.Ratio ≥ 0.727 AND code_path_same AND Jaccard ≥ 0.05

| Pair                  | Jaccard | Excl.Ratio | Code Path                |
| --------------------- | ------- | ---------- | ------------------------ |
| scheduled_pin ↔ draft | 0.152   | 0.73       | Both use PostFacet.put() |
| post ↔ draft          | 0.116   | 0.74       | Both use PostFacet.put() |
| post ↔ scheduled_pin  | 0.099   | 0.79       | Both use PostFacet.put() |

**Vocabulary treatment**: "Same system, different lifecycle state—ask: queued, draft, or published?"

### NAME_CONFUSION (3 pairs)

**Rule**: name_overlap AND Jaccard < 0.15

| Pair                                  | Jaccard | Excl.Ratio | Name Overlap    |
| ------------------------------------- | ------- | ---------- | --------------- |
| pin ↔ turbo_pin                       | 0.089   | 0.48       | Suffix 'pin'    |
| pin ↔ smartpin                        | 0.140   | 0.45       | Suffix 'pin'    |
| pinterest_account ↔ instagram_account | 0.025   | 0.95       | Token 'account' |

**Vocabulary treatment**: "Names overlap but different features—explicitly distinguish"

### DISTINCT (remainder)

No vocabulary entry needed.

---

## Output Format

Per Issue #153 spec, add to `config/theme_vocabulary.json`:

```json
{
  "term_distinctions": {
    "similar_ux": {
      "_description": "Terms that co-occur in complaints - clarify which is affected",
      "title_vs_description": {
        "terms": ["title", "description"],
        "co_occurrence": "high",
        "guidance": "Often mentioned together in content generation issues. Both are text fields generated by Ghostwriter. Ask: 'Is the issue with the title, description, or both?'"
      },
      "account_vs_pinterest_account": {
        "terms": ["account", "pinterest_account"],
        "co_occurrence": "high",
        "guidance": "Users say 'account' generically. Clarify: 'Are you referring to your Tailwind account settings or your connected Pinterest account?'"
      },
      "pin_vs_board": {
        "terms": ["pin", "board"],
        "co_occurrence": "high",
        "relationship": "pins belong to boards",
        "guidance": "These co-occur because pins go on boards. Ask: 'Is the issue with the pin itself or with which board it's assigned to?'"
      },
      "pin_vs_scheduled_pin": {
        "terms": ["pin", "scheduled_pin"],
        "co_occurrence": "moderate",
        "guidance": "Clarify state: 'Is this about a pin that's already published on Pinterest, or one that's scheduled to post later?'"
      },
      "account_vs_instagram_account": {
        "terms": ["account", "instagram_account"],
        "co_occurrence": "moderate",
        "guidance": "Users say 'account' generically. Clarify: 'Are you referring to your Tailwind account or your connected Instagram account?'"
      }
    },
    "different_model": {
      "_description": "Same underlying code but different user lifecycle states",
      "scheduled_pin_vs_draft": {
        "terms": ["scheduled_pin", "draft"],
        "code_path": "Both use PostFacet.put() in tack",
        "user_difference": "scheduled_pin is queued with a publish time; draft is saved but not scheduled",
        "symptoms_scheduled_pin": [
          "bulk delete requests",
          "spam filter flags",
          "pins not showing in queue"
        ],
        "symptoms_draft": [
          "bulk editing",
          "ghostwriter generation",
          "content creation workflow"
        ],
        "guidance": "Ask: 'Is this content scheduled to post at a specific time, or is it saved as a draft you're still working on?'"
      },
      "post_vs_draft": {
        "terms": ["post", "draft"],
        "code_path": "Both use PostFacet.put() in tack",
        "user_difference": "post is ready/published content; draft is work-in-progress",
        "guidance": "Ask: 'Has this content been published or scheduled, or is it still a draft?'"
      },
      "post_vs_scheduled_pin": {
        "terms": ["post", "scheduled_pin"],
        "code_path": "Both use PostFacet.put() in tack",
        "user_difference": "post is general content; scheduled_pin is Pinterest-specific queue item",
        "guidance": "Ask: 'Are you referring to content across platforms, or specifically to Pinterest scheduled pins?'"
      }
    },
    "name_confusion": {
      "_description": "Names overlap but these are different features - explicitly distinguish",
      "pin_vs_turbo_pin": {
        "terms": ["pin", "turbo_pin"],
        "why_confusing": "Both contain 'pin' but turbo_pin is a paid promotion feature",
        "pin_definition": "Regular Pinterest content (published or scheduled)",
        "turbo_pin_definition": "Paid feature that boosts pin visibility (stored in aero Postgres, not tack)",
        "guidance": "If user mentions 'turbo' or 'boost', they mean turbo_pin. Otherwise, clarify: 'Are you asking about regular pins or the Turbo promotion feature?'"
      },
      "pin_vs_smartpin": {
        "terms": ["pin", "smartpin"],
        "why_confusing": "Both contain 'pin' but smartpin is an automation feature",
        "pin_definition": "Regular Pinterest content",
        "smartpin_definition": "Automated pin generation feature (stored in aero MySQL, not tack)",
        "guidance": "If user mentions 'auto', 'generate', or 'SmartPin', they mean the automation feature. Otherwise, clarify."
      },
      "pinterest_account_vs_instagram_account": {
        "terms": ["pinterest_account", "instagram_account"],
        "why_confusing": "Both are '*_account' but different platforms with different code paths",
        "pinterest_account_code": "tack service, TokenV5Facet",
        "instagram_account_code": "zuck service, Graph API",
        "guidance": "Always clarify which platform when user says 'my account' or 'connected account'."
      }
    }
  }
}
```

---

## Implementation Steps

1. **Read current vocabulary file**: `config/theme_vocabulary.json`
2. **Add term_distinctions section** with the structure above
3. **Bump version** to 2.16
4. **Update description** to note vocabulary enhancement
5. **Validate JSON** syntax
6. **Run tests** if any exist for vocabulary loading

---

## Maintenance Notes

1. **Suffix list**: Currently `['pin', 'account']`. Update if new compound objects appear.
2. **Recalibration**: Re-run percentile calculation when themes table grows >50%
3. **Percentile values**: Stored in this doc for reference; could be added to vocabulary metadata

---

## Data Sources

- Phase 1: `data/vocabulary_enhancement/phase1_terms.json` (325 candidate pairs)
- Phase 2: `data/vocabulary_enhancement/phase2_validations.json` (SAME_FIX verdicts)
- Code paths: `data/vocabulary_enhancement/code_paths.json`
- Symptom analysis: Derived from `themes.diagnostic_summary` in this session

---

## Validation Approach

After implementation:

1. Verify JSON parses correctly
2. Spot-check that existing vocabulary sections are unchanged
3. Manual review of guidance text for clarity
4. (Optional) Test with sample theme extraction to verify guidance is used

---

_Phase 3 implementation plan for Issue #153_
