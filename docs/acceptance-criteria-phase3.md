# Phase 3: Escalation Engine - Acceptance Criteria

## Overview

Apply rules to classified conversations to route urgent issues and create actionable tickets.

## Acceptance Criteria

| ID        | Description                          | Threshold                | Test                        | Status   |
| --------- | ------------------------------------ | ------------------------ | --------------------------- | -------- |
| AC-P3-001 | Rules evaluate without errors        | 100% success             | `test_rule_evaluation`      | PASS     |
| AC-P3-002 | Churn risk triggers Slack alert      | All churn_risk=true      | `test_churn_risk_alert`     | PASS     |
| AC-P3-003 | Urgent priority triggers Slack alert | All priority=urgent      | `test_urgent_alert`         | PASS     |
| AC-P3-004 | Bug reports create Shortcut tickets  | Configurable threshold   | `test_bug_ticket_creation`  | DEFERRED |
| AC-P3-005 | Feature requests aggregated          | Group similar requests   | `test_feature_aggregation`  | DEFERRED |
| AC-P3-006 | No duplicate Slack alerts            | Idempotent within window | `test_alert_deduplication`  | PASS     |
| AC-P3-007 | No duplicate Shortcut tickets        | Check before create      | `test_ticket_deduplication` | DEFERRED |
| AC-P3-008 | Dry-run mode available               | No external API calls    | `test_dry_run`              | PASS     |

**Note**: AC-P3-004, AC-P3-005, AC-P3-007 are deferred pending Shortcut API integration. Current implementation uses console logging (dry_run mode) for Slack alerts simulation.

## Rule Definitions

### Immediate Alerts (Slack)

| Trigger                                      | Channel       | Urgency |
| -------------------------------------------- | ------------- | ------- |
| `churn_risk = true`                          | #churn-alerts | High    |
| `priority = urgent`                          | #urgent       | High    |
| `priority = high AND sentiment = frustrated` | #support      | Medium  |

### Ticket Creation (Shortcut)

| Trigger                              | Story Type | Priority                |
| ------------------------------------ | ---------- | ----------------------- |
| `issue_type = bug_report`            | Bug        | Based on priority field |
| `issue_type = feature_request` (≥3x) | Feature    | Normal                  |

### Deduplication Rules

- **Slack**: Don't re-alert for same conversation within 24 hours
- **Shortcut**: Check for existing ticket with same conversation ID before creating

## Test Fixtures

Tests will use classified conversations from the database, plus mock external APIs.

## Deliverables

- [x] `docs/escalation-rules.md` - Human-readable rule definitions
- [x] `src/escalation.py` - Rule engine (5 rules: R001-R005)
- [x] `src/slack_client.py` - Slack webhook integration (with dry_run mode)
- [x] `src/shortcut_client.py` - Shortcut API integration (deferred - logs only)
- [x] `tests/test_escalation.py` - Unit tests with mocked APIs (20 tests)
