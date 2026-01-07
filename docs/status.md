# Project Status

## Current Phase

**Phase 4: Theme Extraction & Aggregation** - IN PROGRESS 🚧

## Latest: Vocabulary v2.2 + VDD (2026-01-07)

**Problem**: Broad themes like `analytics_data_issue` and `feature_access_question` were grouping unrelated issues that need different fixes.

**Solution**: Split broad themes into specific actionable signatures:

- `analytics_data_issue` → `analytics_counter_bug`, `blog_indexing_failure`, `engagement_decline_feedback`
- `feature_access_question` → `original_publisher_access`, `dashboard_version_issue`, `multi_account_question`

**VDD Infrastructure**: Added validation-driven development for vocabulary changes:

```bash
# Run before/after vocabulary changes
pytest tests/test_theme_extraction.py -v
```

- `data/theme_fixtures.json` - 7 human-labeled ground truth conversations
- `tests/test_theme_extraction.py` - Validates extraction accuracy (100% required)

**VDD Workflow**:

1. Find misclassified conversation → add to fixtures with expected theme
2. Update vocabulary to fix classification
3. Run tests → verify fix + no regressions
4. Commit when 100% passing

**Current State**: 34 themes, 17 actionable tickets, 7/7 fixtures passing

## Phase 4: Theme Extraction 🚧

**Status**: Vocabulary v2.2 complete with VDD validation

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
