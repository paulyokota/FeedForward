# Phase 3: Escalation Engine - Acceptance Criteria

## Overview

Apply rules to classified conversations to route urgent issues and create actionable tickets.

## Acceptance Criteria

| ID        | Description                          | Threshold                | Test                        |
| --------- | ------------------------------------ | ------------------------ | --------------------------- |
| AC-P3-001 | Rules evaluate without errors        | 100% success             | `test_rule_evaluation`      |
| AC-P3-002 | Churn risk triggers Slack alert      | All churn_risk=true      | `test_churn_risk_alert`     |
| AC-P3-003 | Urgent priority triggers Slack alert | All priority=urgent      | `test_urgent_alert`         |
| AC-P3-004 | Bug reports create Shortcut tickets  | Configurable threshold   | `test_bug_ticket_creation`  |
| AC-P3-005 | Feature requests aggregated          | Group similar requests   | `test_feature_aggregation`  |
| AC-P3-006 | No duplicate Slack alerts            | Idempotent within window | `test_alert_deduplication`  |
| AC-P3-007 | No duplicate Shortcut tickets        | Check before create      | `test_ticket_deduplication` |
| AC-P3-008 | Dry-run mode available               | No external API calls    | `test_dry_run`              |

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

- [ ] `docs/escalation-rules.md` - Human-readable rule definitions
- [ ] `src/escalation.py` - Rule engine
- [ ] `src/slack_client.py` - Slack webhook integration
- [ ] `src/shortcut_client.py` - Shortcut API integration (deferred if no token)
- [ ] `tests/test_escalation.py` - Unit tests with mocked APIs
