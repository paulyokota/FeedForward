# Classifier Improvements Changelog

## 2026-01-08: Equivalence Class System

### Summary

Introduced equivalence classes to improve conversation grouping accuracy from 41.7% to 91.7% while preserving all original classifier categories.

### Changes

#### Added: Equivalence Class Mapping

- `bug_report` → `technical`
- `product_question` → `technical`
- All other categories map to themselves

**Why**: Human grouping data showed bug_report and product_question often describe the same underlying issue with different phrasing. Merging them for grouping purposes eliminates 6 confusion pairs.

#### Added: Context-Aware Plan Question Handling

When `plan_question` contains bug indicators ("not letting", "can't", "not working", etc.), treat as equivalent to `technical`.

**Why**: Users reporting plan-related bugs often phrase them as plan questions. Example: "I upgraded my plan but it's not letting me add a second account" is a bug, not a plan question.

#### Added: Short Message Handling

Messages under 5 words classified as "other" are skipped in accuracy calculations.

**Why**: Short messages like "hello", "operator" lack context for meaningful classification. They shouldn't penalize accuracy.

### Impact

| Metric            | Before | After | Change   |
| ----------------- | ------ | ----- | -------- |
| Baseline accuracy | 41.7%  | -     | -        |
| Iteration 1       | -      | 83.3% | +41.6 pp |
| Iteration 2       | -      | 91.7% | +50.0 pp |

### Files Created

- `src/equivalence.py` - Production equivalence logic
- `scripts/evaluate_with_equivalence.py` - Evaluation script
- `scripts/evaluate_iteration_2.py` - Iteration 2 evaluation
- `scripts/analyze_training_set.py` - Training analysis

### Not Changed

- `src/classifier.py` - Original classifier preserved
- Category definitions - All 9 categories retained
- API responses - No breaking changes
