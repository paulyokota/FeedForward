# Intercom Schema Analysis

Analysis of Intercom's conversation data structure to inform FeedForward's classification schema.

**Data source**: Live API sample (20 conversations from 336,412 total)
**Date**: 2026-01-06

## Key Intercom Fields

### Core Conversation Fields

| Field            | Type      | Description                   | Use for Classification   |
| ---------------- | --------- | ----------------------------- | ------------------------ |
| `id`             | string    | Unique conversation ID        | Primary key              |
| `created_at`     | timestamp | When conversation started     | Time analysis            |
| `state`          | enum      | `open`, `closed`, `snoozed`   | Status tracking          |
| `priority`       | enum      | `priority`, `not_priority`    | Urgency signal           |
| `source.type`    | enum      | `conversation`, `email`       | Channel                  |
| `source.body`    | HTML      | Initial customer message      | **Classification input** |
| `source.subject` | string    | Email subject (if applicable) | Additional context       |

### Assignment & Handling

| Field                       | Type | Description                                                    |
| --------------------------- | ---- | -------------------------------------------------------------- |
| `admin_assignee_id`         | int  | Current human assignee                                         |
| `team_assignee_id`          | int  | Current team                                                   |
| `ai_agent_participated`     | bool | Whether AI handled any part                                    |
| `ai_agent.resolution_state` | enum | `confirmed_resolution`, `assumed_resolution`, `routed_to_team` |

### Existing Classification

| Field                                             | Sample Values                                                  |
| ------------------------------------------------- | -------------------------------------------------------------- |
| `topics`                                          | "Billing" (only topic in sample)                               |
| `tags`                                            | "Non-Ecomm"                                                    |
| `custom_attributes.Language`                      | "English"                                                      |
| `custom_attributes.Fin AI Agent resolution state` | "Confirmed Resolution", "Assumed Resolution", "Routed to team" |
| `custom_attributes.CX Score rating`               | 3, 4, 5                                                        |
| `custom_attributes.CX Score explanation`          | AI-generated summary                                           |

### Statistics (for SLA/escalation logic)

| Field                            | Description                    |
| -------------------------------- | ------------------------------ |
| `statistics.time_to_first_close` | Seconds until first resolution |
| `statistics.time_to_admin_reply` | Seconds until human responded  |
| `statistics.count_reopens`       | Times customer reopened        |
| `statistics.count_assignments`   | Handoffs between agents        |

### Conversation Parts (Messages)

| Field         | Description                                       |
| ------------- | ------------------------------------------------- |
| `part_type`   | `comment`, `assignment`, `close`, `snoozed`, etc. |
| `body`        | HTML message content                              |
| `author.type` | `user`, `admin`, `bot`                            |
| `author.name` | Display name                                      |

## Observed Patterns

### Source Types

- `email`: 55% (11/20 in sample)
- `conversation`: 45% (9/20) - in-app chat

### AI Participation

- AI involved: 30% (6/20)
- Resolution states when AI participates:
  - "Confirmed Resolution" - customer explicitly confirmed
  - "Assumed Resolution" - customer stopped responding
  - "Routed to team" - AI couldn't handle, escalated

### Topics

- Only "Billing" topic observed in sample
- Topics appear to be manually assigned or rule-based

### Common Conversation Types (from message content)

1. **Feature questions**: "Where can I find my smartloops?"
2. **Billing issues**: Payment failures, plan changes, pricing
3. **How-to requests**: "Why should I reschedule a pin?"
4. **Bug reports**: "I can't create Facebook Carousel posts"
5. **Churn prevention**: Cancellation-related outreach

## Gaps in Intercom's Native Classification

Intercom provides:

- Basic topic assignment
- AI resolution tracking
- CX scores (with AI-generated explanations)

What's missing (our opportunity):

1. **Issue type categorization**: bug, feature_request, how_to, billing, churn_risk
2. **Sentiment analysis**: frustrated, neutral, satisfied
3. **Priority scoring**: based on content + customer signals
4. **Product area mapping**: which feature/component is affected
5. **Churn risk detection**: proactive identification
6. **Actionable insight extraction**: "Customer wants X feature"

## Recommended Classification Categories

Based on Intercom schema + observed patterns:

### Issue Type (mutually exclusive)

- `bug_report` - Something is broken
- `feature_request` - Customer wants new capability
- `how_to` - Usage question
- `billing` - Payment/subscription issues
- `account_access` - Login/permission issues
- `feedback` - General feedback without specific ask
- `churn_risk` - Cancellation signals
- `other` - Doesn't fit above

### Sentiment (mutually exclusive)

- `frustrated` - Negative emotion, urgency
- `neutral` - Matter-of-fact
- `satisfied` - Positive feedback

### Priority (mutually exclusive)

- `urgent` - Immediate attention needed
- `high` - Important but not emergency
- `normal` - Standard handling
- `low` - Nice to have

### Product Area (multi-select possible)

- To be derived from conversation content
- Maps to product features/components

## Sample Conversations Saved

| File                                 | Description                          |
| ------------------------------------ | ------------------------------------ |
| `data/samples/intercom_sample.json`  | 20 conversation summaries            |
| `data/samples/conv_billing.json`     | Full billing conversation with parts |
| `data/samples/conv_ai_resolved.json` | AI-resolved conversation             |

## Next Steps

1. Use samples to create labeled test fixtures
2. Design database schema based on this analysis
3. Build classification prompt with these categories
4. Test against real conversation content
