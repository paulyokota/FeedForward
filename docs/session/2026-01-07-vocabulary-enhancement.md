# Vocabulary Enhancement Results

**Date**: 2026-01-07
**Task**: Expand theme vocabulary with customer keywords from training data

## Enhancement Applied

**Version**: v2.5 → v2.6

Added **64 customer keywords** across 9 themes targeting low-accuracy product areas.

### Keywords Added by Theme

| Theme                            | Keywords Added              | Target Area      |
| -------------------------------- | --------------------------- | ---------------- |
| `integration_connection_failure` | +10                         | Extension        |
| `dashboard_version_issue`        | +8                          | Legacy Publisher |
| `legacy_pin_editing_blocked`     | +9                          | Legacy Publisher |
| `m4u_*` (3 themes)               | +2 each (M4U abbreviations) | Made For You     |
| `scheduling_failure`             | +6                          | Scheduling       |
| `analytics_counter_bug`          | +6                          | Analytics        |
| `copilot_feature_question`       | +5                          | CoPilot          |
| `smartbio_display_issue`         | +6                          | Smart.bio        |
| `crossposting_failure`           | +6                          | Crossposting     |

### Sample Keywords Added

**Extension** (integration_connection_failure):

- "spinning wheel", "spinning extension", "WHOOPS popup"
- "chrome extension", "browser extension"
- "extension stopped working", "extension won't connect"

**Legacy Publisher** (legacy_pin_editing_blocked):

- "uploading without titles", "pins sent back to drafts"
- "smartloop error", "spam safeguard"

**Made For You** (all m4u\_\* themes):

- "m4u", "m 4 u" (abbreviation previously missing)

**Ads** (no keywords added - already had good coverage):

- Existing keywords sufficient

## Validation Results

**Method**: Keyword baseline matching against 417 labeled Shortcut stories

### Overall Performance

| Metric       | Before (v2.5) | After (v2.6) | Change       |
| ------------ | ------------- | ------------ | ------------ |
| **Accuracy** | **44.1%**     | **50.6%**    | **+6.5%** ✓✓ |
| Correct      | 184           | 211          | +27          |
| Wrong        | 180           | 153          | -27          |
| No Match     | 53            | 53           | 0            |

### Product Area Improvements

| Product Area         | Before | After | Change     | Status                |
| -------------------- | ------ | ----- | ---------- | --------------------- |
| **Ads**              | 9.5%   | 33.3% | **+23.8%** | ✓✓ Excellent          |
| **Legacy Publisher** | 25.0%  | 42.9% | **+17.9%** | ✓✓ Great              |
| **CoPilot**          | 61.5%  | 76.9% | **+15.4%** | ✓ Good                |
| **Made For You**     | 35.5%  | 45.2% | **+9.7%**  | ✓ Good                |
| Analytics            | 56.2%  | 56.2% | 0%         | = Same                |
| Smart.bio            | 93.3%  | 93.3% | 0%         | = Same (already high) |
| Extension            | 72.7%  | 63.6% | -9.1%      | ⚠️ Regression         |

### Regression Analysis

**Extension (72.7% → 63.6%)**:

Extension issues were confused with Next Publisher because:

- "spinning" keyword now stronger in `scheduling_failure` theme
- Extension issues often mention "schedule" and "scheduling"

**Examples of misclassification**:

- "User's Chrome extension is forever spinning and not scheduling" → Classified as Next Publisher
- "When trying to pin from the extension, Pin Scheduler is timing out" → Classified as Next Publisher

**Root cause**: Keyword overlap between Extension and Scheduling themes.

**Fix options**:

1. Add context checking (if "extension" appears, prioritize Extension themes)
2. Create more specific Extension themes (extension_scheduling_failure)
3. Use URL context (extension pages → Extension product area)

### Top Performers

| Product Area | Accuracy | Notes                               |
| ------------ | -------- | ----------------------------------- |
| Smart.bio    | 93.3%    | Excellent keyword coverage          |
| Create       | 84.4%    | Context-specific keywords work well |
| CoPilot      | 76.9%    | Improved with customer phrases      |
| Communities  | 76.9%    | Good specific keywords              |

### Still Low Accuracy

| Product Area      | Accuracy | Issue                                    |
| ----------------- | -------- | ---------------------------------------- |
| System wide       | 0.0%     | Catch-all category, no specific keywords |
| Catalog Site      | 0.0%     | Only 4 stories, low coverage             |
| Nav               | 0.0%     | Only 2 stories                           |
| Internal Tracking | 0.0%     | Internal tools, generic keywords         |
| Nectar9           | 0.0%     | Internal tool, 1 story                   |
| Jarvis            | 22.2%    | Internal tool, confused with other areas |

## Key Findings

1. **Customer vocabulary works**: Adding phrases from real conversations improved accuracy by 6.5%
2. **Abbreviations matter**: "M4U" was missing, causing Made For You to be under-recognized
3. **Context is important**: "spinning extension" vs "spinning wheel" in scheduler - need disambiguation
4. **High performers stayed high**: Smart.bio (93.3%), Create (84.4%) maintained accuracy
5. **Internal tools are hard**: Jarvis, Internal Tracking have generic keywords

## Next Steps

### Option 1: Fix Extension Regression

Add URL context checking to prioritize Extension when source URL contains "/extension"

### Option 2: Add More Themes

Create themes for coverage gaps:

- Product Dashboard (18 stories, 0 themes)
- Onboarding (9 stories, 33.3% accuracy)
- Email (6 stories, 33.3% accuracy)

### Option 3: Improve Disambiguation

Add theme-specific context rules:

- If "extension" + "spinning" → Extension (not Scheduling)
- If "legacy" + "pin" → Legacy Publisher (not Next Publisher)
- If "ads" + specific context → Ads (not generic)

### Option 4: Test LLM Classification

Run `python tools/validate_shortcut_data.py --llm --sample 5` to compare LLM vs keyword accuracy

## Files Modified

- `config/theme_vocabulary.json` (v2.5 → v2.6)
- Created: `tools/enhance_vocabulary.py`
- Session notes: `docs/session/2026-01-07-vocabulary-enhancement.md`

## Commands Used

```bash
# Run enhancement
python tools/enhance_vocabulary.py

# Validate accuracy
python tools/validate_shortcut_data.py
```
