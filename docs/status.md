# Project Status

## Current Phase

**Phase 2: Batch Pipeline MVP** - Ready to begin

## Phase 1: COMPLETE ✅

**Final Metrics** (all targets exceeded):

| Metric               | Result | Target |
| -------------------- | ------ | ------ |
| Issue Type Accuracy  | 100%   | 80%    |
| Sentiment Accuracy   | 81.2%  | 75%    |
| Churn Risk Precision | 100%   | 75%    |
| Churn Risk Recall    | 100%   | 85%    |
| Priority Accuracy    | 93.8%  | 70%    |

**Deliverables**:

- [x] `src/classifier.py` - OpenAI gpt-4o-mini + rule-based post-processing
- [x] `tests/test_classifier.py` - 13 tests, all passing
- [x] `data/labeled_fixtures.json` - 50 human-labeled samples
- [x] `docs/acceptance-criteria.md` - Measurable thresholds
- [x] `docs/intercom-data-patterns.md` - API access patterns, quality filtering
- [x] `tools/labeler.py` - Streamlit UI for labeling

**Key Learnings** (incorporated into PLAN.md):

- Only ~50% of Intercom conversations are usable (quality filtering needed)
- LLMs need rule-based post-processing for edge cases (hybrid pattern)
- Churn risk is boolean, not enum (stacks with any issue type)

## What's Next

**Phase 2: Batch Pipeline MVP**

```
┌──────────────┐     ┌─────────────────┐     ┌────────────┐     ┌────────────┐
│   Intercom   │ ──▶ │ Quality Filter  │ ──▶ │ Classifier │ ──▶ │ PostgreSQL │
│    Fetch     │     │ (~50% pass)     │     │ (LLM+Rules)│     │   Store    │
└──────────────┘     └─────────────────┘     └────────────┘     └────────────┘
```

Deliverables:

- [ ] `src/intercom_client.py` - Fetch + quality filter
- [ ] `src/pipeline.py` - Orchestration
- [ ] `src/db/models.py` - Pydantic models
- [ ] `src/db/schema.sql` - PostgreSQL schema
- [ ] `tests/test_pipeline.py` - Pipeline tests

## Blockers

- PostgreSQL hosting decision pending (local vs Supabase vs Railway)

## Decision Log

| Date       | Decision                  | Rationale                                    |
| ---------- | ------------------------- | -------------------------------------------- |
| 2026-01-06 | OpenAI for LLM            | User preference                              |
| 2026-01-06 | Batch processing          | Cost-effective for ~100/week                 |
| 2026-01-06 | Data-driven schema        | Let real data inform categories              |
| 2026-01-06 | Hybrid LLM + rules        | LLM for semantics, rules for edge cases      |
| 2026-01-06 | Quality filter before LLM | ~50% of conversations not useful, saves cost |
