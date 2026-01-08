# Phase 3: Human Grouping Pattern Analysis

**Date**: 2026-01-08
**Training Set**: 52 groups, 168 classified conversations

## Training Set Accuracy: 44.2%

| Metric                       | Value         |
| ---------------------------- | ------------- |
| **Coherent groups**          | 23/52 (44.2%) |
| **Incoherent groups**        | 29            |
| **Conversations classified** | 168/174       |

This is consistent with the baseline (41.7%), confirming the patterns are systematic.

---

## A. Semantic Similarity Within Groups

### Key Finding: Humans group by UNDERLYING ISSUE, not message phrasing

Humans grouped conversations together when they:

1. **Report the same bug** (even if described differently)
2. **Are about the same feature** (even if one is a bug report and another a question)
3. **Have the same root cause** (even across category boundaries)

### Example: Story 61774 (4 conversations, all about "Delight" bug)

| Classification       | Message                                                                                      |
| -------------------- | -------------------------------------------------------------------------------------------- |
| bug_report           | "Why does it always add 'Delight' onto my pin titles on the smartpins"                       |
| bug_report           | "i have a problem with the smart pins, they keep getting added to the wrong pinterest board" |
| bug_report           | "If you look at my drafts - all my pins say 'delight' on them"                               |
| **product_question** | "Hi, why does it say 'Delight' at the end of each pin title? And how can I remove..."        |

**Insight**: All 4 conversations are about the same bug, but the last one asks "how can I remove" which triggers `product_question`. Humans grouped them because they're the same issue.

### Example: Story 60086 (11 conversations, account-switching bug)

| Count | Classification    | Example                                                                                |
| ----- | ----------------- | -------------------------------------------------------------------------------------- |
| 8     | bug_report        | "When I try to upload a draft into Arielle's account, it switches to Sophie's account" |
| 2     | **other**         | "operator", "hello"                                                                    |
| 1     | **plan_question** | "I just upgraded my plan, but it's not letting me add a second pinterest account?"     |

**Insight**: All 11 are about the same account-switching bug, but:

- Short greetings → "other"
- Plan-related framing → "plan_question"

---

## B. Category Confusion Matrix

### Top Confusion Pairs

| Confusion                         | Groups | Root Cause                                   |
| --------------------------------- | ------ | -------------------------------------------- |
| **bug_report ↔ other**            | 6      | Short messages ("hello", "operator", "team") |
| **bug_report ↔ product_question** | 6      | "Why does X happen?" vs "How do I use X?"    |
| **other ↔ product_question**      | 2      | Ticket follow-ups classified as "other"      |
| **bug_report ↔ plan_question**    | 2      | Plan limits perceived as bugs                |
| **bug_report ↔ feature_request**  | 1      | Marketing emails about new features          |
| **billing ↔ bug_report**          | 1      | Multi-issue conversations                    |

### Detailed Analysis

#### 1. Short Messages → "other" (MAJOR ISSUE)

Messages humans grouped with bug reports but classifier marks as "other":

- "hello"
- "operator"
- "Speak to person"
- "team"
- "Hi can I get an update on ticket number: 33252093?"
- "This article was deleted"

**Problem**: Classifier sees standalone message without context. Humans see it as part of the same issue.

**Solution**: When message is very short (<10 words) AND contains no clear category signal, it should NOT be classified as "other". Consider:

- Treating as "ambiguous" and skipping
- Inheriting category from conversation context (if available)

#### 2. bug_report vs product_question (FUZZY BOUNDARY)

Same underlying issue, different framing:

| Framing                            | Classification                 |
| ---------------------------------- | ------------------------------ |
| "Why can't I do X?"                | bug_report                     |
| "How do I do X?"                   | product_question               |
| "Is it not possible to X anymore?" | bug_report                     |
| "I'm trying to X but..."           | product_question OR bug_report |

**Problem**: Users encountering unexpected behavior often phrase it as a question ("How do I...?") rather than a bug report. Both belong together.

**Solution Options**:

1. **Merge categories**: Create `technical_issue` that encompasses both
2. **Broader bug_report**: Expand to include "confused about feature" when context suggests it's not working
3. **Semantic grouping**: Group by TOPIC (pin scheduling, smart.bio, etc.) rather than INTENT

#### 3. Feature Announcements Mixed with Bug Reports

Story 63667:

- 2 bug reports about Pin Scheduler not working
- 1 marketing email: "New SmartPin Updates! As we continue to listen to your feedback..."

**Problem**: Marketing emails to customers about features get classified as `feature_request`.

**Solution**: Add pattern detection for marketing/announcement emails (typically start with "New feature!", contain promotional language).

#### 4. Plan-Related Bugs

Story 60086:

- Bug: "It's not letting me add a second pinterest account"
- Could be: Plan limit OR actual bug

**Problem**: When users hit plan limits unexpectedly, they report it as a bug.

**Solution**:

- `plan_question` should include cases where plan limit is the ROOT CAUSE
- `bug_report` should be for cases where behavior is unexpected regardless of plan

---

## C. Category Definition Problems

### Categories That Are Too Narrow

| Category           | Problem                             | Evidence                                         |
| ------------------ | ----------------------------------- | ------------------------------------------------ |
| `bug_report`       | Misses question-phrased bug reports | "Is it not possible to X?" gets product_question |
| `product_question` | Overlaps with bug_report            | "How do I X?" when X is broken                   |
| `other`            | Catches too many ambiguous messages | Greetings, short follow-ups                      |

### Categories That Work Well

| Category          | Why It Works                                             |
| ----------------- | -------------------------------------------------------- |
| `account_access`  | Clear signal words: "login", "password", "can't connect" |
| `billing`         | Clear signal words: "charge", "refund", "payment"        |
| `feature_request` | Clear signal words: "would be great if", "please add"    |

---

## D. Recommended Category Changes

### Option 1: Merge bug_report + product_question (RECOMMENDED)

Create new category: `technical_issue`

**Definition**: Any conversation where:

- Something isn't working as expected
- User is confused about how to use a feature (often symptom of bug)
- Feature behavior changed unexpectedly

**Rationale**: Humans consistently group these together. The distinction is artificial.

**Expected Impact**:

- Eliminates 6 confusion pairs immediately
- Training accuracy should jump from 44% to ~60%+

### Option 2: Add "ambiguous" Handling for Short Messages

For messages under 10 words with no clear category signal:

- Option A: Skip classification entirely (mark as "unclassifiable")
- Option B: Classify as "other" but flag for human review
- Option C: Look at conversation context (if available) to inherit category

**Expected Impact**:

- Eliminates 6 confusion pairs (bug_report ↔ other)
- Training accuracy should improve by ~10 percentage points

### Option 3: Broader "other" Definition

Current "other": "Truly unclassifiable, spam, or completely off-topic"

Should exclude:

- Greetings that start a support conversation
- Ticket follow-ups
- Very short messages that lack context

---

## E. Recommended Logic Changes

### 1. Merge bug_report and product_question

```
OLD:
- bug_report: Something is broken, error messages, features not working
- product_question: "How do I use feature X?"

NEW:
- technical_issue: Something isn't working as expected, OR user is confused about
  how to use a feature when the root cause might be a bug, OR unexpected behavior
```

### 2. Short Message Handling

```
IF message_word_count < 10 AND no_clear_category_signal:
    classify_as = "ambiguous"  # Don't force into a category
```

### 3. Marketing Email Detection

```
IF contains(["new feature", "we're excited", "we've been listening", "updates!"]):
    classify_as = "marketing_announcement"  # Not feature_request
```

---

## F. Phase 4 Implementation Plan

1. **Update category definitions in classifier.py**:
   - Merge `bug_report` and `product_question` into `technical_issue`
   - Update SYSTEM_PROMPT with new definition

2. **Add short message handling**:
   - Skip or flag messages with <10 words and no category signal

3. **Update few-shot examples**:
   - Ensure examples show `technical_issue` for both bug reports and confused questions

4. **Test on training set first**:
   - Verify accuracy improves before running on test set

---

## Appendix: All Incoherent Groups

| Story ID | Categories                                  | Dominant                 | Example                                   |
| -------- | ------------------------------------------- | ------------------------ | ----------------------------------------- |
| 63667    | bug_report, feature_request                 | bug_report (67%)         | SmartPin scheduling bug + marketing email |
| 63323    | bug_report, other                           | other (50%)              | Blog import bug                           |
| 63580    | bug_report, other                           | other (50%)              | Ticket follow-up + Facebook bug           |
| 62932    | bug_report, account_access, plan_question   | account_access (33%)     | Pinterest reconnection issues             |
| 62777    | bug_report, product_question, other         | bug_report (33%)         | Pin title import bug                      |
| 61774    | bug_report, product_question                | bug_report (75%)         | "Delight" added to pin titles             |
| 61915    | bug_report, billing                         | bug_report (50%)         | Extension not working + billing question  |
| 59639    | bug_report, product_question                | product_question (50%)   | Scheduler not working                     |
| 60149    | bug_report, product_question, other         | bug_report (60%)         | Insight report issues                     |
| 60372    | bug_report, product_question, other         | bug_report (67%)         | Communities access issues                 |
| 61013    | bug_report, plan_question, other            | bug_report (33%)         | Account removal issues                    |
| 60509    | bug_report, product_question                | bug_report (67%)         | AI credits and bulk scheduling            |
| 60551    | product_question, feature_request, other    | product_question (50%)   | Smart schedule questions                  |
| 54908    | bug_report, product_question                | bug_report (50%)         | Publisher bug                             |
| 60549    | product_question, other                     | product_question (50%)   | Pin scheduler usage                       |
| 55645    | bug_report, product_question, plan_question | bug_report (40%)         | Pin scheduler + AI issues                 |
| 59975    | bug_report                                  | bug_report (100%)        | Failed pins (COHERENT)                    |
| 60047    | bug_report, product_question, other         | bug_report (64%)         | Pins not showing in schedule              |
| 57509    | bug_report, product_question, feedback      | bug_report (50%)         | Blog feature issues                       |
| 54811    | bug_report, product_question                | product_question (50%)   | Instagram stats                           |
| 55671    | bug_report, product_question                | bug_report (50%)         | Shopify connection                        |
| 54727    | bug_report, other                           | other (50%)              | Site crashing                             |
| 54598    | plan_question, account_access               | plan_question (50%)      | Account connection + plan                 |
| 35311    | marketing_question, plan_question           | marketing_question (50%) | Pinterest suspension + plan               |
| 58969    | plan_question, bug_report                   | plan_question (50%)      | Post limit + failed pins                  |
| 38817    | bug_report, plan_question                   | bug_report (50%)         | Monthly posts + plan                      |
