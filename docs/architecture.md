# Architecture

## Overview

FeedForward is an LLM-powered pipeline for analyzing Intercom conversations and extracting product insights.

## System Design

```
┌──────────────┐
│   Scheduler  │ (cron/GitHub Actions)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Intercom API │ Fetch conversations
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  LLM Batch   │ Classification (OpenAI)
│  Inference   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Database   │ Store insights
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Escalation  │ Apply rules, route to tools
│    Rules     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Reporting   │ Aggregations, alerts
└──────────────┘
```

## Components

### Data Ingestion
- **Source**: Intercom API
- **Method**: Paginated fetch with rate limiting
- **Storage**: Raw conversations cached before processing

### LLM Classification
- **Model**: OpenAI gpt-4o-mini (cost-optimized)
- **Output**: Structured JSON (issue type, priority, sentiment, churn risk)
- **Schema**: See `docs/prompts.md` for prompt templates

### Database
- **Engine**: TBD (PostgreSQL or MongoDB)
- **Tables**: `conversation_insights`, `feature_requests`, `escalation_actions`

### Escalation Engine
- **Rules**: Defined in `docs/escalation-rules.md`
- **Actions**: Jira tickets, Slack alerts, Productboard notes

## Data Flow

TBD - will document as components are built.

## Dependencies

TBD - will document external services and APIs.
