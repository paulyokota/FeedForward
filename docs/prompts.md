# Prompts & Classification

## Overview

This document tracks LLM prompts used for conversation classification, their accuracy metrics, and iteration history.

## Current Production Prompt

**Status**: Not yet defined

**Model**: gpt-4o-mini

**Template**:
```
TBD - will be developed in Phase 1
```

## Classification Schema

### Issue Types
- `PRODUCT_BUG` - Errors, unexpected behavior, functionality issues
- `ACCOUNT_ACCESS` - Login, permissions, password, account settings
- `BILLING` - Charges, subscriptions, payments, invoices, refunds
- `FEATURE_REQUEST` - New capabilities or enhancements
- `UX_FRICTION` - Confusion, onboarding difficulties, unclear UI
- `USAGE_QUESTION` - How to use existing features
- `OTHER` - Doesn't fit above categories

### Priority Levels
- `CRITICAL` - Core functionality broken, payment failure, data loss, security
- `HIGH` - Important feature broken, blocking workflows
- `MEDIUM` - Workaround available, non-critical friction
- `LOW` - Minor inconvenience, cosmetic issues

### Sentiment
- Range: -1.0 (very negative) to 1.0 (very positive)
- Categories: `VERY_NEGATIVE`, `NEGATIVE`, `NEUTRAL`, `POSITIVE`, `VERY_POSITIVE`

### Churn Risk
- `HIGH` - Mentions cancellation, deep frustration, comparing competitors
- `MEDIUM` - Significant issues but no cancellation signals
- `LOW` - Satisfied or minor issues

## Accuracy Metrics

| Version | Date | Accuracy vs Human Baseline | Notes |
|---------|------|---------------------------|-------|
| - | - | - | Not yet measured |

**Target**: ≥80% agreement with human baseline

## Prompt Iteration History

### v0.1 (TBD)
- Initial prompt
- Baseline accuracy: TBD

## Cost Projections

| Volume | Model | Est. Monthly Cost |
|--------|-------|-------------------|
| 1,000 conversations | gpt-4o-mini | ~$0.14 |
| 10,000 conversations | gpt-4o-mini | ~$1.35 |
| 50,000 conversations | gpt-4o-mini | ~$6.75 |

Based on ~500 input tokens + ~100 output tokens per conversation.
