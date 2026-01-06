# Classifier Acceptance Criteria

Measurable success criteria for the conversation classifier, following VDD principles.

## Overview

The classifier takes an Intercom conversation (source.body text) and outputs:

- `issue_type`: One of 9 categories
- `sentiment`: frustrated / neutral / satisfied
- `churn_risk`: boolean
- `priority`: urgent / high / normal / low

## Accuracy Thresholds

### Issue Type Classification

**Target: 80% accuracy on held-out test set**

| Category           | Min Precision | Min Recall | Notes                                    |
| ------------------ | ------------- | ---------- | ---------------------------------------- |
| billing            | 85%           | 80%        | High volume, critical to route correctly |
| bug_report         | 80%           | 85%        | Don't miss bugs - recall matters         |
| product_question   | 75%           | 75%        | May overlap with plan_question           |
| plan_question      | 75%           | 75%        | May overlap with product_question        |
| marketing_question | 70%           | 70%        | Lower volume, acceptable lower threshold |
| feature_request    | 75%           | 80%        | Don't miss feature requests              |
| account_access     | 80%           | 85%        | Critical - login issues are urgent       |
| feedback           | 70%           | 70%        | Catch-all for general feedback           |
| other              | 60%           | 60%        | Acceptable lower threshold               |

### Churn Risk Detection

**Target: 85% recall, 75% precision**

Rationale: Missing a churn signal is worse than a false positive. We'd rather flag too many than miss someone about to cancel.

Churn signals include:

- Explicit cancellation requests
- Refund requests
- "Not using anymore" / "haven't used in a while"
- Frustration + billing issue combination
- Competitor mentions

### Sentiment Analysis

**Target: 75% accuracy**

| Sentiment  | Indicators                                                                |
| ---------- | ------------------------------------------------------------------------- |
| frustrated | "annoying", "terrible", "not working", urgency, ALL CAPS, multiple issues |
| neutral    | Straightforward questions, no emotional language                          |
| satisfied  | "love", "great", "thanks so much", positive feedback                      |

### Priority Scoring

**Target: 70% agreement with human labels**

| Priority | Criteria                                      |
| -------- | --------------------------------------------- |
| urgent   | Account locked, payment failing, service down |
| high     | Bug blocking work, frustrated + churn risk    |
| normal   | Standard questions and issues                 |
| low      | General feedback, feature wishes              |

## Test Structure

### Unit Tests

- Each classification dimension tested independently
- Minimum 5 examples per category
- Edge cases explicitly tested

### Integration Tests

- Full classification pipeline
- Measures overall accuracy across all dimensions
- Tracks latency (should be <2s per conversation)

### Regression Tests

- Run on every prompt change
- Fail if accuracy drops >5% on any dimension

## Evaluation Metrics

```python
def evaluate_classifier(predictions, labels):
    return {
        "issue_type_accuracy": accuracy(predictions.issue_type, labels.issue_type),
        "issue_type_per_class": per_class_metrics(predictions.issue_type, labels.issue_type),
        "churn_risk_precision": precision(predictions.churn_risk, labels.churn_risk),
        "churn_risk_recall": recall(predictions.churn_risk, labels.churn_risk),
        "sentiment_accuracy": accuracy(predictions.sentiment, labels.sentiment),
        "priority_accuracy": accuracy(predictions.priority, labels.priority),
    }
```

## Pass/Fail Criteria

The classifier PASSES if:

- [ ] Issue type accuracy >= 80%
- [ ] Churn risk recall >= 85%
- [ ] Churn risk precision >= 75%
- [ ] Sentiment accuracy >= 75%
- [ ] No category has 0% recall (catastrophic failure)
- [ ] Latency p95 < 3 seconds

The classifier FAILS if any of the above are not met.

## Test/Train Split

From 50 labeled fixtures:

- **Train/examples**: 35 samples (70%) - used in prompt as few-shot examples
- **Test**: 15 samples (30%) - held out for evaluation

Split should be stratified to ensure each issue type appears in both sets.
