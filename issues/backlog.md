# FeedForward Backlog

> Issue tracking for FeedForward. See [README.md](./README.md) for format and workflow.

---

## In Progress

_(none)_

---

## Backlog

### [ISSUE-001] Create acceptance criteria for Phase 1
**Phase**: 1 | **Priority**: high | **Type**: task
Define machine-readable acceptance criteria in `acceptance_criteria/phase1.yaml` per VDD methodology.
- [ ] Create acceptance_criteria directory
- [ ] Define accuracy thresholds for each classification field
- [ ] Link criteria to test scripts

### [ISSUE-002] Create labeled test fixtures
**Phase**: 1 | **Priority**: high | **Type**: task
Create sample Intercom conversations with human labels for testing classification accuracy.
- [ ] Create tests/fixtures directory
- [ ] Add 30-50 anonymized/synthetic conversations
- [ ] Label each with: issue_type, priority, sentiment, churn_risk
- [ ] Include edge cases (ambiguous, multi-issue, empty)

### [ISSUE-003] Write failing classification tests
**Phase**: 1 | **Priority**: high | **Type**: task
Create pytest tests that validate classification output against labeled fixtures.
- [ ] Create tests/test_classification.py
- [ ] Test accuracy per field against thresholds
- [ ] Test output schema compliance
- [ ] Tests should FAIL initially (no classifier yet)

### [ISSUE-004] Build classification prompt
**Phase**: 1 | **Priority**: high | **Type**: feature
Create the LLM classification prompt and iterate using GTR loop.
- [ ] Draft initial prompt in docs/prompts.md
- [ ] Run against test fixtures
- [ ] Iterate until accuracy thresholds met (max 5 iterations)
- [ ] Log versions with /prompt-iteration

### [ISSUE-005] Implement classifier module
**Phase**: 1 | **Priority**: medium | **Type**: feature
Create Python module that calls OpenAI API with the classification prompt.
- [ ] Create src/classifier.py
- [ ] Implement structured output parsing
- [ ] Add Pydantic models for classification result

---

## Done

_(none yet)_
