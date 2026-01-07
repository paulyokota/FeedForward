# Project Status

## Current Phase

**Phase 4: Theme Extraction & Aggregation** - IN PROGRESS 🚧

## Latest: Vocabulary v2.1 Expansion (2026-01-06)

**Problem**: 37% of themed conversations were in catch-all buckets (`general_product_question`, `unclassified_needs_review`, `misdirected_inquiry`), resulting in only 12 tickets from 400+ conversations.

**Solution**: Expanded vocabulary from 22 to 30 themes, adding:

- `professional_services_inquiry` - managed services/consulting requests
- `smartbio_configuration` - smart.bio link customization
- `unsupported_platform_inquiry` - eBay, TikTok, etc.
- `pin_editing_question` - editing pins, bulk operations
- `feature_access_question` - Original Publisher, beta features
- `dashboard_loading_error` - loading errors, blank screens
- `communities_feature_question` - Tailwind Communities
- `ai_language_mismatch` - wrong language generation

**Results after re-extraction**:

| Metric             | Before      | After       | Change      |
| ------------------ | ----------- | ----------- | ----------- |
| Actionable themes  | 162 (63.0%) | 195 (75.9%) | +33 (+13pp) |
| Catch-all themes   | 95 (37.0%)  | 62 (24.1%)  | -33         |
| Themes for tickets | 12          | 20          | +8 new      |

**Scripts added**:

- `scripts/reextract_catchall.py` - Re-extract themes for catch-all conversations

## Phase 4: Theme Extraction 🚧

**Status**: Vocabulary v2.1 complete, ready for ticket creation

**Deliverables**:

- [x] `src/theme_extractor.py` - LLM-based theme extraction with product context
- [x] `src/theme_tracker.py` - Store, aggregate, and query themes
- [x] `src/cli.py` - CLI for viewing themes and ticket previews
- [x] `src/db/schema.sql` - themes + theme_aggregates tables
- [x] `context/product/*.md` - Product documentation for context

**CLI Commands**:

```bash
python src/cli.py themes           # List all themes
python src/cli.py trending         # Trending (2+ occurrences in 7 days)
python src/cli.py pending          # Preview ALL pending tickets
python src/cli.py ticket <sig>     # Preview specific ticket
python src/cli.py extract <id>     # Extract theme from conversation
```

**Ticket Format**: Each ticket includes:

- Product area and component mapping
- Canonical issue_signature for aggregation
- User intent and symptoms
- Affected flow and root cause hypothesis
- Sample customer messages
- Suggested investigation steps

**Signature Canonicalization**: Two-phase extraction ensures consistent signatures:

1. Phase 1: Extract theme details (product_area, component, symptoms, etc.)
2. Phase 2: Canonicalize signature against existing signatures in database

Tested embedding-based canonicalization as cheaper alternative - rejected due to lower accuracy (0.627 similarity) and actually slower (N API calls vs 1 LLM call).

**Branch**: `feature/theme-extraction` - ready for PR

---

## Phase 3: COMPLETE ✅

**Final Metrics**:

| Metric            | Result      | Target            |
| ----------------- | ----------- | ----------------- |
| Rule Evaluation   | ✅ Working  | 100% success      |
| Churn Risk Alert  | ✅ Working  | Triggers Slack    |
| Urgent Alert      | ✅ Working  | Triggers Slack    |
| Bug Report Ticket | ✅ Working  | Logs for Shortcut |
| Deduplication     | ✅ Verified | No duplicates     |
| Unit Tests        | 20 passing  | All pass          |

**Deliverables**:

- [x] `docs/escalation-rules.md` - Rule definitions (6 rules)
- [x] `docs/acceptance-criteria-phase3.md` - Acceptance criteria
- [x] `src/escalation.py` - Rule engine with 5 rules
- [x] `src/slack_client.py` - Slack webhook integration (dry-run ready)
- [x] `src/db/schema.sql` - Added escalation_log table
- [x] `tests/test_escalation.py` - 20 unit tests passing

**Run escalation**:

```bash
# After running pipeline, evaluate escalation rules
python -c "from src.escalation import run_escalation; run_escalation(dry_run=True)"
```

**Note**: Add `SLACK_WEBHOOK_URL` to `.env` to enable real Slack alerts.

## Phase 2: COMPLETE ✅

**Final Metrics**:

| Metric                | Result      | Target        |
| --------------------- | ----------- | ------------- |
| Intercom Fetch        | ✅ Working  | Functional    |
| Quality Filter        | 17%         | ~50% (varies) |
| Classification        | 100%        | 100%          |
| DB Storage            | ✅ Working  | Functional    |
| Idempotency           | ✅ Verified | No duplicates |
| Pipeline Time (5 msg) | ~10s        | <5min/100     |

**Deliverables**:

- [x] `src/intercom_client.py` - Fetch + quality filter
- [x] `src/pipeline.py` - CLI orchestration (--days, --dry-run, --max)
- [x] `src/db/models.py` - Pydantic models
- [x] `src/db/schema.sql` - PostgreSQL schema
- [x] `src/db/connection.py` - Database operations
- [x] `tests/test_pipeline.py` - 13 unit tests passing
- [x] `docs/acceptance-criteria-phase2.md` - Acceptance criteria

**Run the pipeline**:

```bash
python -m src.pipeline --days 7             # Last 7 days
python -m src.pipeline --days 1 --max 10    # Test with 10 conversations
python -m src.pipeline --dry-run            # No DB writes
```

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

**Phase 4: Real-Time Workflows** (optional)

Webhook-driven processing for time-sensitive issues:

- Intercom webhooks trigger immediate classification
- Critical issues alert within 5 minutes
- Requires infrastructure changes (webhook endpoint)

**Or continue with**:

- Add `SLACK_WEBHOOK_URL` to test real Slack alerts
- Add `SHORTCUT_API_TOKEN` for real ticket creation
- Run pipeline on larger dataset (30 days)

## Blockers

None

## Decision Log

| Date       | Decision                  | Rationale                                    |
| ---------- | ------------------------- | -------------------------------------------- |
| 2026-01-06 | OpenAI for LLM            | User preference                              |
| 2026-01-06 | Batch processing          | Cost-effective for ~100/week                 |
| 2026-01-06 | Data-driven schema        | Let real data inform categories              |
| 2026-01-06 | Hybrid LLM + rules        | LLM for semantics, rules for edge cases      |
| 2026-01-06 | Quality filter before LLM | ~50% of conversations not useful, saves cost |
| 2026-01-06 | LLM for canonicalization  | Embedding approach slower & less accurate    |
