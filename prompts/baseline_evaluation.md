# Phase 2: Baseline Evaluation Results

**Date**: 2026-01-08
**Classifier**: src/classifier.py (GPT-4o-mini with structured output)

## Baseline Accuracy

| Metric                   | Value     |
| ------------------------ | --------- |
| **Baseline Accuracy**    | **41.7%** |
| Correct Groups           | 5         |
| Total Groups             | 12        |
| Mismatched Groups        | 7         |
| Conversations Classified | 39/40     |

## Correct Groups (All Same Category)

| Story ID | Conversations | Category       |
| -------- | ------------- | -------------- |
| 55720    | 2             | bug_report     |
| 53734    | 2             | bug_report     |
| 62569    | 2             | bug_report     |
| 58913    | 3             | bug_report     |
| 62845    | 2             | account_access |

## Confusion Patterns

The classifier is mixing up these categories most frequently:

1. **bug_report ↔ product_question** (3 groups)
   - Stories 60862, 63202, 52070
   - Users asking "how do I do X?" when X is broken vs. genuinely not knowing

2. **bug_report ↔ feature_request** (1 group)
   - Story 63005
   - "Impossible to add Instagram" classified as bug vs. feature request

3. **bug_report ↔ other ↔ plan_question** (1 group)
   - Story 60086 (11 conversations)
   - Short messages like "operator" and "hello" classified as "other"
   - Plan limit questions mixed in with bug reports

4. **bug_report ↔ other** (1 group)
   - Story 61917
   - Very short messages classified differently

## Top 5 Mismatch Examples

### 1. Story 63005 - bug_report vs feature_request

**Conv 1 (feature_request):**

> "Hey there, Remember that Pin you created? What if I told you it's just the beginning of something mu..."

**Conv 2 (bug_report):**

> "hi impossible to add my instagram account see error message attached"

**Analysis**: Both are about the same issue (Instagram connection), but different framing triggered different classifications.

### 2. Story 60862 - product_question vs bug_report

**Conv 1 (product_question):**

> "smartloop scheduling"

**Conv 2 (bug_report):**

> "I am trying to update smartloop settings and the 'save' button just spins and spins and never finish..."

**Analysis**: First message is too short to determine intent. Second clearly describes a bug.

### 3. Story 60086 - bug_report vs other vs plan_question

**Conversations classified as bug_report:**

> "I am having a problem with my dashboard today"
> "I have a problem to schedule new pins via publisher"

**Conversations classified as other:**

> "operator"
> "hello"

**Conversation classified as plan_question:**

> "I just upgraded my plan, but it's not letting me add a second pinterest account?"

**Analysis**: Very short messages and plan-related context cause divergence. All 11 conversations are about the same underlying issue.

### 4. Story 63202 - product_question vs bug_report

**Conv 1 (product_question):**

> "I'm trying to schedule a pin for tomorrow, instead of today, and the first pin schedule at the botto..."

**Conv 2 (bug_report):**

> "Is it not possible to select the start date and time of a pin anymore?"

**Analysis**: Same issue (scheduling date selection), but questioning tone vs. "is it broken?" tone.

### 5. Story 52070 - bug_report vs product_question

**Conv 1 (bug_report):**

> "Hi, why can I suddenly see scheduled FB posts for a page that I am an admin of, but I no longer help..."

**Conv 2 (product_question):**

> "Hello, I'm trying to understand how exactly my publisher was able to (accidentally) post to another..."

**Analysis**: Same issue (cross-account posting), but "why" vs "how" framing.

## Key Insights

1. **Short messages are problematic**: "hello", "operator", single-word messages get classified as "other" when they should inherit context from the issue.

2. **bug_report vs product_question boundary is fuzzy**: When users encounter unexpected behavior, they often phrase it as a question ("Is this possible?") rather than a bug report.

3. **Context matters more than individual message**: Humans group by the underlying issue, not by how each message is phrased.

4. **Plan-related bugs cause confusion**: "Can't add second account" could be a bug OR a plan limit question.

## Recommendations for Phase 3

1. Consider grouping `bug_report` and `product_question` when the underlying topic is the same
2. Handle short/ambiguous messages by looking at thread context
3. Add logic to detect when a "plan_question" might actually be a bug (user expects feature to work)
4. Consider a broader "issue" category that encompasses bugs and confused product questions

## Next Steps

Proceed to Phase 3: Analyze Human Grouping Patterns using training set to understand how humans group these conversations.
