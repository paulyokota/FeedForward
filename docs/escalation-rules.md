# Escalation Rules

Rules for routing classified conversations to alerts and tickets.

## Rule Priority

Rules are evaluated in priority order. First matching rule triggers action.

## Active Rules

### Priority 1: Immediate Alerts (Slack)

| Rule ID | Name              | Condition                                    | Action              |
| ------- | ----------------- | -------------------------------------------- | ------------------- |
| R001    | Churn Risk Alert  | `churn_risk = true`                          | Slack #churn-alerts |
| R002    | Urgent Priority   | `priority = urgent`                          | Slack #urgent       |
| R003    | Frustrated + High | `priority = high AND sentiment = frustrated` | Slack #support      |

### Priority 2: Ticket Creation (Shortcut)

| Rule ID | Name            | Condition                                 | Action                  |
| ------- | --------------- | ----------------------------------------- | ----------------------- |
| R004    | Bug Report      | `issue_type = bug_report`                 | Create Shortcut bug     |
| R005    | Feature Request | `issue_type = feature_request` (freq ≥ 3) | Create Shortcut feature |

### Priority 999: Default

| Rule ID | Name     | Condition         | Action          |
| ------- | -------- | ----------------- | --------------- |
| R999    | Log Only | `*` (matches all) | Log to database |

## Slack Alert Templates

### R001: Churn Risk Alert

```
:warning: *Churn Risk Detected*
Customer: {contact_email}
Issue Type: {issue_type}
Message: {source_body_preview}
<{intercom_url}|View in Intercom>
```

### R002: Urgent Priority

```
:rotating_light: *Urgent Issue*
Type: {issue_type}
Customer: {contact_email}
Message: {source_body_preview}
<{intercom_url}|View in Intercom>
```

### R003: Frustrated + High Priority

```
:face_with_symbols_on_mouth: *Frustrated Customer - High Priority*
Type: {issue_type}
Customer: {contact_email}
Message: {source_body_preview}
<{intercom_url}|View in Intercom>
```

## Shortcut Ticket Templates

### R004: Bug Report

```yaml
story_type: bug
name: "Bug: {source_subject_or_preview}"
description: |
  ## Customer Report
  {source_body}

  ## Classification
  - Priority: {priority}
  - Sentiment: {sentiment}
  - Churn Risk: {churn_risk}

  ## Source
  - Intercom ID: {id}
  - Customer: {contact_email}
priority_map:
  urgent: highest
  high: high
  normal: medium
  low: low
```

### R005: Feature Request (Aggregated)

```yaml
story_type: feature
name: "Feature Request: {aggregated_summary}"
description: |
  ## Request Summary
  Requested by {request_count} customers

  ## Sample Messages
  {sample_messages}
```

## Deduplication

### Slack Deduplication

- Track alerts by conversation ID in `escalation_log` table
- Don't re-alert for same conversation within 24 hours

### Shortcut Deduplication

- Check for existing ticket with same conversation ID before creating
- Store mapping in `escalation_log` table

## Configuration

Environment variables (see `.env.example`):

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_BOT_TOKEN=xoxb-...
SHORTCUT_API_TOKEN=...
```

## Dry Run Mode

When `--dry-run` is passed:

- Log what would be sent/created
- Don't make actual API calls
- Useful for testing rule logic

## Rule Change Log

| Date       | Change                        | Rationale                      |
| ---------- | ----------------------------- | ------------------------------ |
| 2026-01-06 | Align with implemented schema | Match classifier output fields |
| 2026-01-06 | Add Slack alert templates     | Clear notification format      |
| 2026-01-06 | Add deduplication rules       | Prevent alert/ticket spam      |
