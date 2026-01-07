# Prompts & Classification

## Overview

This document tracks LLM prompts used for theme extraction, their accuracy metrics, and iteration history.

## Current Production Prompt

**Status**: Active (Theme Extraction with URL Context)

**Model**: gpt-4o-mini

**Approach**: Vocabulary-guided theme extraction with URL context boosting

**Template**:

```python
THEME_EXTRACTION_PROMPT = """
You are a product theme classifier for Tailwind (social media scheduling tool).

## Your Task
Extract product issues/themes from customer conversations.

## Known Themes
{vocabulary_section}

## URL Context (When Available)
{url_context_hint}
# Example: "User was on **Legacy Publisher** page. Strongly prefer Legacy Publisher themes."

## Instructions
1. Match conversation to existing themes FIRST (prefer known themes)
2. If URL context provided, prioritize themes from that product area
3. Extract: product_area, issue_signature, user_symptom, severity
4. Use "unclassified_needs_review" if no good match

## Output Format
JSON with theme details
"""
```

**Key Features**:

- **Vocabulary-guided**: Shows 61 known themes to LLM before extraction
- **URL context boosting**: Hints product area when source.url matches patterns
- **Match-first**: Prefer existing themes over creating new ones
- **Strict mode**: Force match to vocabulary (backfill use case)

## Classification Schema

### Product Areas (20+)

- `scheduling` - Pin Scheduler, Legacy Publisher, Multi-Network
- `content` - Drafts, content library, media management
- `analytics` - Reports, insights, performance tracking
- `integrations` - Social network connections (Pinterest, Instagram, etc.)
- `billing` - Subscriptions, payments, plan features
- `account` - Login, settings, team management
- `communities` - Tribes, community features
- `browser_extension` - Chrome/Firefox extension
- `smartloop` - Automated content recycling
- `other` - Doesn't fit above categories

### Issue Signatures

Canonical issue names like:

- `scheduling_failure_pin` - Posts fail to schedule (Pin Scheduler)
- `scheduling_failure_legacy` - Posts fail to schedule (Legacy Publisher)
- `pinterest_connection_failure` - Can't connect Pinterest account
- `csv_import_failure` - CSV import fails or errors
- `unclassified_needs_review` - No matching theme

### Severity Levels

- `high` - Blocking core workflows
- `medium` - Workaround available
- `low` - Minor inconvenience

## URL Context System

**Purpose**: Disambiguate product areas using page URL

**How It Works**:

1. Conversation includes `source.url` (e.g., `/dashboard/v2/scheduler`)
2. URL matches pattern in vocabulary → Product area
3. Prompt includes: "User was on **{product_area}** page. Strongly prefer {product_area} themes."
4. LLM prioritizes themes from that product area

**URL Patterns** (27 total):

- `/dashboard/v2/scheduler` → Multi-Network Scheduler
- `/publisher/queue` → Legacy Publisher
- `/dashboard/v2/advanced-scheduler/pinterest` → Pin Scheduler
- `/settings/billing` → Billing & Settings
- (See `config/theme_vocabulary.json` for full list)

**Validation Metrics** (Live Data):

- Pattern match rate: 80% (8/10 conversations with URLs)
- Product area accuracy: 100% (all matches routed correctly)
- False positive rate: 0%

## Accuracy Metrics

| Version         | Date       | Accuracy vs Shortcut Baseline | Notes                                        |
| --------------- | ---------- | ----------------------------- | -------------------------------------------- |
| v2.5 (baseline) | 2026-01-06 | 44.1%                         | Initial keyword matching                     |
| v2.6            | 2026-01-06 | 50.6% (+6.5%)                 | Customer keywords from Intercom              |
| v2.7            | 2026-01-07 | 53.2% (+9.1%)                 | Context boosting + Product Dashboard         |
| v2.8            | 2026-01-07 | 52.5% (+8.4%)                 | Extension, SmartLoop, Legacy/Next split      |
| v2.9            | 2026-01-07 | 52.5% (+8.4%)                 | Multi-Network + URL context (infrastructure) |

**Target**: ≥80% agreement with Shortcut training data (829 stories)

## Prompt Iteration History

### v0.1 (TBD)

- Initial prompt
- Baseline accuracy: TBD

## Cost Projections

| Volume               | Model       | Est. Monthly Cost |
| -------------------- | ----------- | ----------------- |
| 1,000 conversations  | gpt-4o-mini | ~$0.14            |
| 10,000 conversations | gpt-4o-mini | ~$1.35            |
| 50,000 conversations | gpt-4o-mini | ~$6.75            |

Based on ~500 input tokens + ~100 output tokens per conversation.
