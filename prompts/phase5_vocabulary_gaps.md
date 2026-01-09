# Phase 5D: Vocabulary Gap Analysis

**Generated**: 2026-01-08 14:24:13

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Vocabulary Gaps | 0 |
| High Priority Gaps (10+ occurrences) | 0 |
| Medium Priority Gaps (5-9 occurrences) | 0 |
| Low Priority Gaps (<5 occurrences) | 0 |

---

## Shortcut Product Area Coverage

| Product Area | Count | Coverage Status |
|--------------|-------|-----------------|
| Pin Scheduler | 31 | Covered |
| Next Publisher | 25 | Covered |
| Legacy Publisher | 24 | Covered |
| Create | 22 | Covered |
| Smart.bio | 15 | Covered |
| Analytics | 15 | Covered |
| Billing & Settings | 13 | Covered |
| Extension | 11 | Covered |
| Made For You | 10 | Covered |
| GW Labs | 8 | Covered |
| Product Dashboard | 6 | Covered |
| SmartLoop | 5 | Covered |
| Communities | 4 | Covered |
| CoPilot | 3 | Covered |
| Jarvis | 1 | Covered |
| Email | 1 | Covered |
| Ads | 1 | Covered |

---

## Vocabulary Gaps

**No gaps found!** All Shortcut product areas have FeedForward mappings.

---

## Most Common Mismatch Patterns

These patterns show where FeedForward extraction differs from Shortcut labels:

| Extracted -> Ground Truth | Count |
|---------------------------|-------|
| other -> Create | 11 |
| integrations -> Smart.bio | 9 |
| other -> Pin Scheduler | 8 |
| other -> Next Publisher | 7 |
| next_publisher -> Pin Scheduler | 6 |
| other -> Made For You | 5 |
| scheduling -> Extension | 4 |
| pinterest_publishing -> Analytics | 4 |
| other -> Legacy Publisher | 4 |
| pinterest_publishing -> SmartLoop | 3 |
| other -> Smart.bio | 3 |
| other -> Billing & Settings | 2 |
| other -> Product Dashboard | 2 |
| pinterest_publishing -> Create | 2 |
| account -> Extension | 2 |

---

## Recommendations

### 1. Fix Mapping: other -> Create
- **Occurrences**: 11
- **Priority**: high
- **Action**: Consider mapping 'other' to include 'Create'

### 2. Fix Mapping: integrations -> Smart.bio
- **Occurrences**: 9
- **Priority**: high
- **Action**: Consider mapping 'integrations' to include 'Smart.bio'

### 3. Fix Mapping: other -> Pin Scheduler
- **Occurrences**: 8
- **Priority**: high
- **Action**: Consider mapping 'other' to include 'Pin Scheduler'

### 4. Fix Mapping: other -> Next Publisher
- **Occurrences**: 7
- **Priority**: high
- **Action**: Consider mapping 'other' to include 'Next Publisher'

### 5. Fix Mapping: next_publisher -> Pin Scheduler
- **Occurrences**: 6
- **Priority**: high
- **Action**: Consider mapping 'next_publisher' to include 'Pin Scheduler'

### 6. Fix Mapping: other -> Made For You
- **Occurrences**: 5
- **Priority**: high
- **Action**: Consider mapping 'other' to include 'Made For You'

### 7. Fix Mapping: scheduling -> Extension
- **Occurrences**: 4
- **Priority**: medium
- **Action**: Consider mapping 'scheduling' to include 'Extension'

### 8. Fix Mapping: pinterest_publishing -> Analytics
- **Occurrences**: 4
- **Priority**: medium
- **Action**: Consider mapping 'pinterest_publishing' to include 'Analytics'

### 9. Fix Mapping: other -> Legacy Publisher
- **Occurrences**: 4
- **Priority**: medium
- **Action**: Consider mapping 'other' to include 'Legacy Publisher'

### 10. Fix Mapping: pinterest_publishing -> SmartLoop
- **Occurrences**: 3
- **Priority**: medium
- **Action**: Consider mapping 'pinterest_publishing' to include 'SmartLoop'

---

## Root Cause Analysis

Based on the mismatch patterns, the main accuracy issues stem from:

1. **Granularity Mismatch**: FeedForward uses broad categories (scheduling, ai_creation) while Shortcut uses specific product names (Pin Scheduler, Create, Made For You)

2. **Ambiguous Messages**: Short messages like "help" or "not working" lack context to determine the specific product

3. **Multi-Product Conversations**: Some conversations mention multiple products, making single-label classification difficult

4. **Keyword False Positives**: Keyword matching sometimes picks wrong category (e.g., "account" keyword in Pin Scheduler context)

## Next Steps

1. If gaps exist: Add new vocabulary entries for uncovered Shortcut areas
2. Consider training extraction to output Shortcut-specific labels instead of broad FeedForward categories
3. Improve LLM prompt to be aware of specific Tailwind product names
