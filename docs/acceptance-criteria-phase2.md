# Phase 2 Acceptance Criteria

Batch pipeline that fetches from Intercom, classifies, and stores to PostgreSQL.

## Pipeline Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌────────────┐     ┌────────────┐
│   Intercom   │ ──▶ │ Quality Filter  │ ──▶ │ Classifier │ ──▶ │ PostgreSQL │
│    Fetch     │     │ (~50% pass)     │     │ (LLM+Rules)│     │   Store    │
└──────────────┘     └─────────────────┘     └────────────┘     └────────────┘
```

## Acceptance Criteria

### AC-P2-001: Intercom Fetch

**Description**: Fetch conversations from Intercom API without error.

**Test**: `tests/test_pipeline.py::test_intercom_fetch`

**Criteria**:

- [ ] Fetches conversations from specified time range
- [ ] Handles pagination correctly (cursor-based)
- [ ] Returns raw conversation data with required fields

### AC-P2-002: Quality Filter

**Description**: Filter conversations before LLM to reduce costs.

**Test**: `tests/test_pipeline.py::test_quality_filter`

**Criteria**:

- [ ] Only passes `customer_initiated` conversations
- [ ] Only passes `user` authored messages (not admin/bot/lead)
- [ ] Requires body length > 20 characters
- [ ] Skips template clicks ("I have a product question")
- [ ] ~50% of conversations filtered (based on Phase 1 analysis)

### AC-P2-003: Classification Coverage

**Description**: All quality conversations are classified.

**Test**: `tests/test_pipeline.py::test_classification_coverage`

**Criteria**:

- [ ] 100% of quality conversations get classification result
- [ ] No classification errors or timeouts
- [ ] Uses existing classifier from Phase 1

### AC-P2-004: Database Storage

**Description**: Results stored to PostgreSQL.

**Test**: `tests/test_pipeline.py::test_db_storage`

**Criteria**:

- [ ] All classified conversations inserted to database
- [ ] Schema matches classification output
- [ ] Timestamps and metadata preserved

### AC-P2-005: Idempotency

**Description**: Re-running pipeline doesn't create duplicates.

**Test**: `tests/test_pipeline.py::test_idempotency`

**Criteria**:

- [ ] Running twice on same data produces same row count
- [ ] Uses conversation ID as unique key
- [ ] Updates existing records on re-run (upsert)

### AC-P2-006: Performance

**Description**: Pipeline completes in reasonable time.

**Test**: `tests/test_pipeline.py::test_performance`

**Criteria**:

- [ ] < 5 minutes for 100 conversations
- [ ] Batching for LLM calls if beneficial

## Database Schema

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,              -- Intercom conversation ID
    created_at TIMESTAMP NOT NULL,

    -- Raw input
    source_body TEXT,
    source_type TEXT,                 -- 'conversation', 'email', etc.
    contact_email TEXT,

    -- Classification output
    issue_type TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    churn_risk BOOLEAN NOT NULL,
    priority TEXT NOT NULL,

    -- Metadata
    classified_at TIMESTAMP DEFAULT NOW(),
    classifier_version TEXT
);

CREATE INDEX idx_conversations_created_at ON conversations(created_at);
CREATE INDEX idx_conversations_issue_type ON conversations(issue_type);
CREATE INDEX idx_conversations_churn_risk ON conversations(churn_risk) WHERE churn_risk = true;
```

## Test Data

Use conversations fetched via Intercom MCP or API. For unit tests, use fixtures from Phase 1.

## Pass/Fail

Pipeline PASSES if:

- [ ] All 6 acceptance criteria met
- [ ] Tests pass: `pytest tests/test_pipeline.py`
- [ ] Can run `python -m src.pipeline --days 7` successfully
