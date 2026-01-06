# Escalation Rules

## Overview

Rules engine for routing classified conversations to appropriate actions and tools.

## Rule Priority

Rules are evaluated in priority order. Higher priority rules (lower numbers) take precedence.

## Active Rules

### Priority 1: Critical Escalations

| Rule ID | Name | Condition | Action |
|---------|------|-----------|--------|
| R001 | P0 Bug (Enterprise) | `issue_type=PRODUCT_BUG AND priority=CRITICAL AND segment=enterprise` | Page on-call engineer |
| R002 | High Churn Risk | `churn_risk=HIGH AND sentiment_score < -0.7` | Alert CS manager |

### Priority 2: Revenue-Impacting

| Rule ID | Name | Condition | Action |
|---------|------|-----------|--------|
| R003 | Billing Critical | `issue_type=BILLING AND priority IN [CRITICAL, HIGH]` | Escalate to finance team |

### Priority 3: Product Feedback

| Rule ID | Name | Condition | Action |
|---------|------|-----------|--------|
| R004 | Popular Feature Request | `issue_type=FEATURE_REQUEST AND frequency >= 10` | Create Productboard note |
| R005 | UX Friction Pattern | `issue_type=UX_FRICTION AND frequency >= 5` | Schedule UX review |

### Priority 999: Default

| Rule ID | Name | Condition | Action |
|---------|------|-----------|--------|
| R999 | Default Queue | `*` (matches all) | Add to PM review queue |

## Actions

### Notification Actions
- `PAGE_ONCALL_ENGINEER` - PagerDuty integration
- `ALERT_CS_MANAGER` - Slack #customer-success-alerts
- `SEND_SLACK_MESSAGE` - Custom channel/message

### Ticket Actions
- `CREATE_JIRA_P0` - High-priority bug ticket
- `CREATE_JIRA_STANDARD` - Normal priority ticket
- `CREATE_PRODUCTBOARD_NOTE` - Feature request tracking

### Assignment Actions
- `ASSIGN_TO_FINANCE` - Billing team queue
- `ADD_TO_PM_QUEUE` - Product manager review

## Thresholds

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Feature request frequency | 10 mentions | Before auto-creating Productboard note |
| UX friction frequency | 5 mentions | Before scheduling UX review |
| High churn sentiment | < -0.7 | Combined with churn_risk=HIGH |

## Integration Credentials

See `.env.example` for required tokens:
- Jira: `JIRA_API_TOKEN`, `JIRA_BASE_URL`
- Productboard: `PRODUCTBOARD_API_TOKEN`
- Slack: `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`

## Rule Change Log

| Date | Change | Rationale |
|------|--------|-----------|
| - | Initial rules defined | Based on intercom-llm-guide.md recommendations |
