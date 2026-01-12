---
name: prompt-tester
triggers:
  keywords:
    - test prompt
    - measure accuracy
    - prompt accuracy
    - classification accuracy
    - test classifier
dependencies:
  tools:
    - Read
    - Bash
---

# Prompt Tester Skill

Test LLM classification prompts against sample data and measure accuracy.

## Purpose

Measure classification prompt accuracy using fixtures to validate prompt changes before deployment.

## Workflow

### Phase 1: Load Prompt and Schema

1. **Load Current Prompt**
   - Read from `docs/prompts.md`
   - Identify prompt version being tested
   - Extract classification schema

2. **Understand Classification Schema**
   - Issue types (categories)
   - Priority levels
   - Sentiment scale
   - Churn risk levels
   - Output format expected

### Phase 2: Prepare Test Data

1. **Find Sample Data**
   - Look for fixtures in `tests/fixtures/`
   - Check `data/samples/` directory
   - Look for labeled conversations in `data/labeled_fixtures.json`

2. **Verify Sample Quality**
   - Are ground truth labels provided?
   - Is sample size sufficient (minimum 10-20)?
   - Do samples cover diverse scenarios?

3. **If No Samples**: Request them or note the gap

### Phase 3: Run Classifications

1. **For Each Sample**
   - Format prompt with conversation data
   - Run classification (call LLM or use test runner)
   - Record predicted vs expected labels

2. **Capture Results**
   - Store predictions
   - Note any errors or failures
   - Track processing time if relevant

### Phase 4: Calculate Metrics

1. **Overall Accuracy**
   - Percentage of correct classifications
   - Total correct / total samples

2. **Per-Category Accuracy**
   - Issue type accuracy
   - Priority accuracy
   - Sentiment accuracy
   - Churn risk accuracy

3. **Confusion Patterns**
   - What gets misclassified as what?
   - Are there systematic errors?
   - Which categories are problematic?

### Phase 5: Analyze Failures

1. **Identify Common Patterns**
   - What types of conversations are misclassified?
   - Are there edge cases not handled?
   - Is there ambiguity in ground truth?

2. **Note Ambiguous Cases**
   - Where ground truth may be wrong
   - Where multiple labels could be valid

3. **Suggest Improvements**
   - Specific prompt modifications
   - Additional examples needed
   - Edge cases to address

## Output Format

```markdown
## Test Results

**Prompt Version**: [version from docs/prompts.md]
**Sample Size**: [N] conversations
**Overall Accuracy**: [X]%

### Per-Category Accuracy

| Category   | Accuracy | Notes           |
| ---------- | -------- | --------------- |
| Issue Type | X%       | [common errors] |
| Priority   | X%       | [common errors] |
| Sentiment  | X%       | [common errors] |
| Churn Risk | X%       | [common errors] |

### Failure Analysis

1. [Pattern 1]: [X] cases - [explanation]
2. [Pattern 2]: [X] cases - [explanation]

### Recommendations

- [Specific prompt improvement]
- [Edge case to handle]
```

## Success Criteria

- [ ] Prompt loaded from `docs/prompts.md`
- [ ] Test data found or gap documented
- [ ] Classifications run for all samples
- [ ] Metrics calculated (not estimated)
- [ ] Failure patterns identified
- [ ] Recommendations provided

## Constraints

- **Report actual numbers**, not estimates
- **Flag if sample size too small** for statistical significance
- **Note ambiguous ground truth** labels
- **Don't modify prompts directly** - only recommend changes

## Key Files

| File                         | Purpose                   |
| ---------------------------- | ------------------------- |
| `docs/prompts.md`            | Current prompt versions   |
| `data/labeled_fixtures.json` | Labeled test data         |
| `data/theme_fixtures.json`   | Theme extraction fixtures |
| `tests/fixtures/`            | Test fixture directory    |

## Common Pitfalls

- **Estimating accuracy**: Always measure with real data
- **Small sample size**: Need minimum 10-20 samples for validity
- **Ignoring ambiguity**: Some labels are genuinely ambiguous
- **Not documenting version**: Always note which prompt version tested

## Integration with Kai

This skill is typically invoked by Kai (prompt engineering skill) when:

- Testing new prompt versions
- Validating prompt modifications
- Measuring baseline before changes
- Comparing before/after accuracy

## If Blocked

If you cannot proceed:

1. State what's missing (fixtures, prompt, schema)
2. Explain what you've searched for
3. Request specific data needed
4. Provide partial results if available
