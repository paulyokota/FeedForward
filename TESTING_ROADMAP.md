# FeedForward Test Suite Remediation Roadmap

**Prepared by**: Kenji (Testing Specialist)
**Date**: 2026-01-20
**Status**: Active

This document provides a prioritized roadmap for addressing test coverage gaps identified in `TEST_SUITE_AUDIT.md`.

---

## Quick Reference: Severity Levels

| Level | Color | Impact | Response Time |
|-------|-------|--------|---|
| CRITICAL | 🔴 | Blocks deployment, data at risk | Fix immediately (days) |
| HIGH | 🟠 | Prevents confident refactoring, gaps in coverage | Fix within sprint (1 week) |
| MEDIUM | 🟡 | Tech debt, maintainability issue | Fix within 2 sprints (2 weeks) |
| LOW | 🟢 | Nice to have, polish | Fix opportunistically |

---

## Phase 1: Stabilization (Weeks 1-2)

**Goal**: Fix failing tests and establish basic pytest infrastructure
**Effort**: 3-4 days
**Owner**: Kenji

### Week 1: Day 1-2 - Fix Test Failures & Configuration

#### Task 1.1: Fix API Mock Setup 🔴 CRITICAL
**Status**: Blocking all classifier tests
**Effort**: 4 hours
**Steps**:
1. Read `/home/user/FeedForward/tests/conftest.py`
2. Add OpenAI mock fixture:
```python
@pytest.fixture
def mock_openai_client():
    with patch('openai.OpenAI') as mock:
        mock.return_value.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"issue_type": "bug_report", ...}'))]
        )
        yield mock
```
3. Update `test_classifier.py` to use fixture
4. Verify 6 tests pass

**Acceptance Criteria**:
- [ ] `pytest tests/test_classifier.py -v` shows 6/6 passing
- [ ] No `APIConnectionError` exceptions
- [ ] Mock captures calls correctly

#### Task 1.2: Install Missing Dependencies 🔴 CRITICAL
**Status**: 16 tests erroring
**Effort**: 1 hour
**Steps**:
1. Add to `requirements.txt`:
   ```
   playwright>=1.40.0
   ```
2. Run `playwright install chromium`
3. Verify `pytest tests/test_ralph_v2.py -k "test_auth_keywords" -v` passes

**Acceptance Criteria**:
- [ ] No "Playwright not installed" errors
- [ ] 16 tests in `test_ralph_v2.py` pass or are skipped
- [ ] `requirements.txt` updated

#### Task 1.3: Create pytest Configuration 🟡 MEDIUM
**Status**: Test discovery inconsistent
**Effort**: 1 hour
**Steps**:
1. Create `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --strict-markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (multi-component)
    slow: Slow tests (>5s)
```
2. Register custom marks to eliminate warnings
3. Run `pytest --markers` to verify

**Acceptance Criteria**:
- [ ] No "Unknown pytest.mark.*" warnings
- [ ] `pytest --markers` shows all marks
- [ ] File created at `/home/user/FeedForward/pytest.ini`

#### Task 1.4: Fix Theme Extraction Fixtures 🔴 CRITICAL
**Status**: Empty fixtures, test skipped
**Effort**: 2 hours
**Steps**:
1. Read `tests/test_theme_extraction.py` to understand fixture format
2. Create `/home/user/FeedForward/data/theme_fixtures.json`:
```json
{
  "fixtures": [
    {
      "id": "conv_001",
      "source_body": "My pins aren't scheduling correctly",
      "issue_type": "bug_report",
      "sentiment": "frustrated",
      "churn_risk": false,
      "priority": "normal"
    }
  ]
}
```
3. Add 10-15 diverse examples (bug_report, feature_request, product_question, etc.)
4. Run `pytest tests/test_theme_extraction.py -v`

**Acceptance Criteria**:
- [ ] Fixture file created with 10+ examples
- [ ] `test_fixtures_exist` passes
- [ ] `test_theme_extraction` runs (may skip if ThemeExtractor not fully implemented)

### Week 1: Day 3 - Pydantic v2 Migrations

#### Task 1.5: Fix Pydantic Deprecation Warnings 🟡 MEDIUM
**Status**: 16 warnings in test output
**Effort**: 2 hours
**Steps**:
1. Fix `src/classifier.py`:
```python
# Replace class Config with ConfigDict
from pydantic import ConfigDict

class ClassificationResult(BaseModel):
    model_config = ConfigDict(json_schema_extra={"enum": [...]})
```
2. Fix `src/db/models.py` (4 models)
3. Fix `src/api/schemas/pipeline.py` (2 models)
4. Fix `src/api/schemas/themes.py` (1 model)
5. Run `pytest tests/ -v` - verify warnings eliminated

**Acceptance Criteria**:
- [ ] Zero Pydantic deprecation warnings
- [ ] All models still validate correctly
- [ ] All tests pass

### Week 1: Day 4 - Fixture Data Files

#### Task 1.6: Create Core Fixture Files 🟡 MEDIUM
**Status**: Tests use hardcoded or incomplete fixtures
**Effort**: 3 hours
**Steps**:
1. Create `/home/user/FeedForward/data/fixtures/`:
   - `conversations/sample.json` - realistic Intercom conversation
   - `conversations/edge_cases.json` - boundary test cases
   - `stories/sample.json` - Shortcut story format
   - `classifications/sample.json` - classifier output examples

2. Consolidate into `conftest.py` fixtures:
```python
@pytest.fixture
def sample_conversation():
    with open('data/fixtures/conversations/sample.json') as f:
        return json.load(f)
```

**Acceptance Criteria**:
- [ ] All fixture files created
- [ ] Consolidation function in conftest.py
- [ ] Tests using fixtures pass

**Deliverable**: `/home/user/FeedForward/pytest.ini`, updated `conftest.py`, fixture files

---

## Phase 2: Critical Unit Tests (Weeks 3-4)

**Goal**: Establish comprehensive unit tests for critical paths
**Effort**: 8-10 days
**Owner**: Kenji + Development team

### Week 2: Sprint 1 - API Endpoint Tests 🔴 CRITICAL

#### Task 2.1: Health & Pipeline Route Tests
**Status**: 0% endpoint coverage
**Effort**: 2 days
**Files**:
- Create `tests/test_api_health.py`
- Create `tests/test_api_pipeline.py`

**Tests Needed**:
```python
# test_api_health.py
def test_get_health():
    """GET /health should return 200 OK"""

def test_health_response_format():
    """Health response should include status"""

# test_api_pipeline.py
def test_get_pipeline_status():
    """GET /pipeline/status should return current run"""

def test_post_pipeline_run():
    """POST /pipeline/run should start run"""

def test_pipeline_status_invalid_run_id():
    """GET /pipeline/status/{invalid_id} should return 404"""
```

**Acceptance Criteria**:
- [ ] 8+ tests created
- [ ] All tests passing
- [ ] Coverage for: GET, POST, error cases

#### Task 2.2: Themes & Stories Route Tests
**Status**: 0% endpoint coverage
**Effort**: 2 days
**Files**:
- Create `tests/test_api_themes.py`
- Create `tests/test_api_stories.py`

**Tests Needed**:
```python
# test_api_themes.py
def test_get_themes_trending():
    """GET /themes/trending"""

def test_get_themes_orphans():
    """GET /themes/orphans"""

# test_api_stories.py
def test_post_create_story():
    """POST /stories"""

def test_get_story_by_id():
    """GET /stories/{id}"""
```

**Acceptance Criteria**:
- [ ] 10+ tests created
- [ ] All CRUD operations tested
- [ ] Error cases covered

#### Task 2.3: Sync & Analytics Route Tests
**Status**: 0% endpoint coverage
**Effort**: 1.5 days
**Files**:
- Create `tests/test_api_sync.py`
- Create `tests/test_api_analytics.py`

**Tests Needed**:
- Sync webhooks
- Analytics dashboard endpoints
- Error handling

**Acceptance Criteria**:
- [ ] 12+ tests created
- [ ] Webhook handling tested

**Deliverable**: 5 new test files, 30+ endpoint tests, all passing

---

### Week 2: Sprint 2 - Classification Pipeline Tests 🔴 CRITICAL

#### Task 2.4: Classification Mocking Infrastructure
**Status**: Tests fail when trying to call real API
**Effort**: 1 day
**Steps**:
1. Create `/home/user/FeedForward/tests/mocks/openai_mock.py`:
```python
class MockOpenAIResponse:
    def __init__(self, classification_data):
        self.choices = [MagicMock(message=MagicMock(content=json.dumps(classification_data)))]
```

2. Create fixtures for different classification scenarios:
```python
@pytest.fixture
def mock_bug_report_classification():
    return {...}

@pytest.fixture
def mock_feature_request_classification():
    return {...}
```

**Acceptance Criteria**:
- [ ] Mock module created
- [ ] 5+ classification scenarios mocked
- [ ] Fixtures verified to work

#### Task 2.5: Classifier Unit Tests
**Status**: 6 tests fail due to API
**Effort**: 2 days
**File**: Update `tests/test_classifier.py`

**Tests Needed**:
```python
def test_classify_conversation_bug_report():
    """Should classify bug report correctly"""

def test_classify_conversation_feature_request():
    """Should classify feature request"""

def test_classify_handles_api_error():
    """Should fallback if API fails"""

def test_classify_with_short_input():
    """Should handle short input"""

def test_classify_with_long_input():
    """Should truncate if needed"""

def test_sentiment_analysis():
    """Should detect sentiment correctly"""

def test_churn_risk_detection():
    """Should detect churn risk"""

def test_priority_scoring():
    """Should assign priority"""
```

**Acceptance Criteria**:
- [ ] All 8+ tests passing
- [ ] No API calls made
- [ ] Error cases covered

#### Task 2.6: Stage 1 & Stage 2 Pipeline Tests
**Status**: No tests for 2-stage system
**Effort**: 2 days
**Files**:
- Create `tests/test_classifier_stage1.py`
- Create `tests/test_classifier_stage2.py`

**Tests Needed**:
```python
# test_classifier_stage1.py
def test_stage1_routing_priority():
    """Stage 1 assigns routing priority"""

def test_stage1_confidence_scoring():
    """Stage 1 provides confidence"""

# test_classifier_stage2.py
def test_stage2_refinement():
    """Stage 2 refines Stage 1 output"""

def test_stage2_with_support_context():
    """Stage 2 uses support responses"""
```

**Acceptance Criteria**:
- [ ] 6+ tests created
- [ ] Stage progression tested
- [ ] Mocked LLM responses

**Deliverable**: 3 test files, 15+ classifier tests, all passing

---

### Week 3: Sprint 1 - External Service Client Tests 🔴 CRITICAL

#### Task 2.7: Intercom Client Unit Tests
**Status**: 0% isolated tests (mocked in integration tests)
**Effort**: 1.5 days
**File**: Create `tests/test_intercom_client_unit.py`

**Tests Needed**:
```python
def test_fetch_conversations_success():
    """Should fetch and parse conversations"""

def test_fetch_with_pagination():
    """Should handle paginated responses"""

def test_quality_filter_customer_initiated():
    """Should pass customer_initiated conversations"""

def test_quality_filter_admin_initiated():
    """Should filter admin_initiated"""

def test_quality_filter_short_messages():
    """Should filter <20 char messages"""

def test_quality_filter_template_clicks():
    """Should filter template messages"""

def test_fetch_invalid_token():
    """Should raise auth error"""

def test_fetch_timeout():
    """Should handle network timeout"""

def test_fetch_malformed_response():
    """Should handle invalid JSON"""
```

**Acceptance Criteria**:
- [ ] 9+ tests created
- [ ] All CRUD operations tested
- [ ] Error scenarios covered

#### Task 2.8: Shortcut Client Unit Tests
**Status**: 0% tests
**Effort**: 1.5 days
**File**: Create `tests/test_shortcut_client_unit.py`

**Tests Needed**:
```python
def test_create_story():
    """Should create story with labels"""

def test_update_story():
    """Should update story fields"""

def test_get_story():
    """Should fetch story metadata"""

def test_delete_story():
    """Should delete story"""

def test_create_with_invalid_labels():
    """Should validate label format"""

def test_rate_limiting():
    """Should handle HTTP 429"""

def test_auth_failure():
    """Should handle HTTP 401"""
```

**Acceptance Criteria**:
- [ ] 8+ tests created
- [ ] CRUD operations covered
- [ ] Error handling tested

#### Task 2.9: Coda Client Unit Tests
**Status**: 0% tests
**Effort**: 1 day
**File**: Create `tests/test_coda_client_unit.py`

**Tests Needed**:
```python
def test_read_table():
    """Should read table rows"""

def test_sync_row_status():
    """Should update row status"""

def test_invalid_doc_id():
    """Should handle invalid doc ID"""

def test_timeout():
    """Should handle timeout"""
```

**Acceptance Criteria**:
- [ ] 5+ tests created
- [ ] Core operations tested

**Deliverable**: 3 new test files, 20+ service tests, all passing

---

### Week 3: Sprint 2 - Database CRUD Tests 🔴 CRITICAL

#### Task 2.10: Database Models & Connection Tests
**Status**: No CRUD tests
**Effort**: 1.5 days
**File**: Create `tests/test_database_unit.py`

**Tests Needed**:
```python
def test_conversation_model_validation():
    """Should reject invalid issue_type"""

def test_conversation_required_fields():
    """Should require id, created_at, source_body"""

def test_save_conversation():
    """Should save and retrieve conversation"""

def test_update_conversation():
    """Should update existing conversation"""

def test_delete_conversation():
    """Should delete conversation"""

def test_transaction_rollback():
    """Should rollback on error"""

def test_concurrent_inserts():
    """Should handle concurrent inserts"""

def test_cascade_delete():
    """Should cascade delete related records"""

def test_constraint_violation():
    """Should enforce unique constraints"""
```

**Acceptance Criteria**:
- [ ] 9+ tests created
- [ ] All CRUD operations tested
- [ ] Transactions tested
- [ ] Constraints validated

**Deliverable**: 1 new test file, 9+ database tests, all passing

---

## Phase 3: Integration Testing (Weeks 5-6)

**Goal**: Establish end-to-end workflow testing
**Effort**: 4-5 days
**Owner**: Development team

### Week 4: Sprint 1 - End-to-End Pipeline Tests 🟠 HIGH

#### Task 3.1: Full Pipeline Integration Test
**File**: Create `tests/integration/test_full_pipeline.py`

**Tests Needed**:
```python
def test_pipeline_fetch_classify_store():
    """Fetch → Classify → Store workflow"""
    # 1. Mock Intercom API to return conversation
    # 2. Run classification
    # 3. Verify stored in database
    # 4. Verify Shortcut ticket created

def test_pipeline_error_recovery():
    """Pipeline should continue on single conversation error"""

def test_pipeline_with_real_data_shapes():
    """Pipeline should handle real Intercom data format"""
```

**Acceptance Criteria**:
- [ ] 3+ integration tests
- [ ] Full workflow tested
- [ ] Error recovery verified

### Week 4: Sprint 2 - Multi-Step Workflow Tests 🟠 HIGH

#### Task 3.2: Story Lifecycle Tests
**File**: Expand `tests/test_phase5_integration.py`

**Tests Needed**:
```python
def test_orphan_lifecycle():
    """Orphan → Accumulate → Graduate → Story"""

def test_sync_workflow_end_to_end():
    """Create → Push → Webhook → Pull → Sync"""
```

**Acceptance Criteria**:
- [ ] Lifecycle tests added
- [ ] State transitions verified

**Deliverable**: 5+ integration tests, full workflows verified

---

## Phase 4: Coverage & Quality (Weeks 7-8)

**Goal**: Achieve 80% overall coverage, improve test quality
**Effort**: 3-4 days

### Week 5: Sprint 1 - Coverage Measurement

#### Task 4.1: Set Up Coverage Reporting
**Effort**: 2 hours
**Steps**:
1. Add to `pytest.ini`:
```ini
[coverage:run]
source = src
omit = */migrations/*
```

2. Run: `pytest tests/ --cov=src --cov-report=html`
3. Generate coverage report

#### Task 4.2: Edge Case Tests
**Effort**: 2 days
**Tests Needed**:
- Very long inputs (10K+ chars)
- Unicode & special characters
- Concurrent operations
- Rate limiting scenarios
- Network timeouts
- Malformed API responses

### Week 5: Sprint 2 - Quality Improvements

#### Task 4.3: Refactor & Consolidate
**Effort**: 1.5 days
**Steps**:
1. Move integration tests to `tests/integration/`
2. Consolidate fixtures to `conftest.py`
3. Create `tests/fixtures/` directory
4. Standardize mock patterns

---

## Success Criteria

### Immediate (Week 1)
- [ ] All test failures fixed (493→500+ passing)
- [ ] Zero Pydantic deprecation warnings
- [ ] pytest.ini created
- [ ] Fixture files created

### Short-term (Week 2-3)
- [ ] 30+ API endpoint tests added
- [ ] 15+ classifier tests added
- [ ] 20+ service client tests added
- [ ] 9+ database tests added
- [ ] Total: 500→600+ tests passing

### Medium-term (Week 4-5)
- [ ] 5+ integration tests added
- [ ] Coverage reporting set up
- [ ] Coverage report: ≥60% source code
- [ ] Zero failing tests
- [ ] Total: 600+ tests passing

### Long-term (Week 6-8)
- [ ] Coverage: ≥80% of critical paths
- [ ] Edge case tests: >50 tests
- [ ] Documentation: Updated TESTING.md
- [ ] CI/CD: All tests passing in pipeline
- [ ] Total: 700+ tests passing

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Tests too slow | CI/CD delays | Mark slow tests, run separately |
| Tests flaky | False failures | Use fixed seeds, mock time |
| Tests brittle | Maintenance burden | Use fixtures, avoid hardcoding |
| Coverage gaps remain | Bugs in production | Prioritize critical path tests |

---

## Tracking & Metrics

### Weekly Reporting

Track these metrics weekly:
```
Week N:
- Tests passing: XXX (+YYY from last week)
- Tests failing: X
- Coverage %: XX%
- New tests added: YYY
- Tech debt items closed: Z
```

### Dashboard Metrics

Target trajectory:
```
Week 1:  500 passing, 7 failing  → 500 passing, 0 failing
Week 2:  510 passing, 0 failing  → 550 passing, 0 failing
Week 3:  570 passing, 0 failing  → 620 passing, 0 failing
Week 4:  650 passing, 0 failing  → 700 passing, 0 failing
Week 5+: Maintain ≥700, <1% failure rate
```

---

## Resource Requirements

### Personnel
- **Kenji** (Lead): 8-10 hours/week for 4 weeks
- **Dev Team**: 5-10 hours/week for 4 weeks
- **Tech Lead**: 2-3 hours/week for reviews

### Infrastructure
- Test database (SQLite): Already available
- Mock libraries: unittest.mock (built-in)
- Coverage tool: Already installed

### Timeline
- **Start**: Next sprint
- **Critical tests**: 2-3 weeks
- **Full completion**: 6-8 weeks

---

## Exit Criteria

When can this initiative be considered complete?

✅ **Complete** when:
1. Zero failing/erroring tests (all 500+)
2. All critical path tests implemented (API, classifier, DB, services)
3. Coverage ≥80% of business logic
4. Pydantic warnings = 0
5. No test flakiness in CI/CD
6. New feature PRs include tests
7. Tech lead can approve merges with confidence

---

## Next Steps

### Immediately (Today)
- [ ] Review this roadmap with tech lead
- [ ] Assign owners to Phase 1 tasks
- [ ] Create GitHub issues for each task

### This Week (Phase 1 Stabilization)
- [ ] Task 1.1: Fix OpenAI mock setup
- [ ] Task 1.2: Install Playwright
- [ ] Task 1.3: Create pytest.ini
- [ ] Task 1.4: Fix theme fixtures
- [ ] Task 1.5: Fix Pydantic warnings

### Next Sprint (Phase 2 Critical Tests)
- [ ] Tasks 2.1-2.6: API & classification tests
- [ ] Tasks 2.7-2.9: Service client tests
- [ ] Task 2.10: Database tests

### Weeks 5-8 (Phase 3-4: Integration & Coverage)
- [ ] End-to-end workflow tests
- [ ] Coverage reporting
- [ ] Quality improvements

---

**Prepared by**: Kenji (Testing Specialist)
**Date**: 2026-01-20
**Next Review**: After Phase 1 completion
