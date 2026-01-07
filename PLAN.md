# FeedForward Project Specification

> **Document Purpose**: This is the authoritative project spec for FeedForward. It captures business context, technical decisions, methodology, and phased implementation plan. New sessions should read this first to understand the project's goals and approach.

**Last Updated**: 2026-01-06
**Status**: Approved
**Branch**: `claude/add-reference-folder-8y8BT`

---

## 1. Executive Summary

### What We're Building

FeedForward is an **LLM-powered pipeline** that analyzes Intercom support conversations to extract product insights. It classifies conversations by issue type, priority, sentiment, and churn risk, then routes actionable tickets to Shortcut for the product and engineering teams.

### Why It Matters

Product teams are drowning in support conversations. Valuable signals—feature requests, bugs, churn risk—are buried in unstructured text. Manual triage doesn't scale. FeedForward automates this analysis, surfacing insights that would otherwise be lost.

### Who It's For

- **Primary consumers**: Product and Engineering teams at the organization
- **Output format**: Actionable tickets in Shortcut (the organization's issue tracker)
- **Scale**: ~50-150 Intercom conversations per week

---

## 2. Development Methodology: Validation-Driven Development (VDD)

### Why VDD?

This project follows **Validation-Driven Development**, a methodology derived from UAT (User Acceptance Testing) research for agentic coding. See `reference/UAT-Agentic-Coding-Research.md` for the full research.

**Key insight from the research:**

> "The key is not to eliminate human oversight, but to **shift it earlier**—from reviewing code post-generation to defining criteria pre-generation."

**Critical findings that shaped our approach:**

- Agentic systems suffer from **overeagerness** (adding unrequested features) and **shifting assumptions** across iterations
- **37.6% security degradation** occurs after just 5 autonomous iterations without human oversight
- Only **14.5%** of agent context files specify non-functional requirements
- **Validation-Driven Development** patterns show the most promise for controlling agent behavior

### VDD vs Traditional Development

| Traditional                         | VDD (Our Approach)                                                             |
| ----------------------------------- | ------------------------------------------------------------------------------ |
| Write code → Test → See if it works | Define acceptance criteria → Write failing tests → Generate code to pass tests |
| "Let's see if the LLM can classify" | "Here's exactly what good classification means—make it pass"                   |
| Iterate until it "looks good"       | Iterate until acceptance criteria are met (max 3-5 cycles)                     |
| Quality is subjective               | Quality is measurable                                                          |

### The Generate-Test-Refine (GTR) Loop

Every phase follows this pattern:

```
1. GENERATE: Claude writes/refines prompt or code
      ↓
2. TEST: Execute acceptance tests (prompt-tester, pytest, validators)
      ↓
3. EVALUATE: Parse results (accuracy %, test pass/fail, security scan)
      ↓
4. DECIDE:
   - All criteria met? → COMPLETE (proceed to next phase)
   - Failures detected? → REFINE (max 3-5 iterations)
   - Stuck after 5 iterations? → ESCALATE to human
      ↓
5. REFINE: Specific feedback ("test X failed because Y") → targeted fix
      ↓
   (Loop back to TEST)
```

### Iteration Limits

**Critical constraint**: Maximum **3-5 autonomous iterations** per task before human review. This prevents:

- Security degradation through compounding errors
- Overeagerness (agents adding unrequested features)
- Brute-force fixes that mask real problems

---

## 3. Business Requirements

### Primary Outputs (Must Have)

1. **Feature Request Aggregation**
   - Identify feature requests in conversations
   - Group similar requests (deduplication)
   - Create Shortcut tickets for requests with frequency ≥ threshold

2. **Bug Detection & Aggregation**
   - Identify bug reports in conversations
   - Extract reproduction steps when available
   - Create Shortcut tickets with priority based on severity/frequency

### Secondary Outputs (Nice to Have)

3. **Churn Risk Detection**
   - Flag conversations indicating cancellation intent or deep frustration
   - Alert relevant team members

4. **Sentiment Trends**
   - Track sentiment over time
   - Surface patterns (e.g., "sentiment dropped after release X")

### Non-Goals (Explicitly Out of Scope)

- Real-time processing (batch is sufficient for this use case)
- Automatic responses to customers (analysis only)
- Integration with CODA research repo (deferred to later phase)
- Multi-language support (English only for MVP)

---

## 4. Technical Decisions

| Decision               | Choice               | Rationale                                                                                             |
| ---------------------- | -------------------- | ----------------------------------------------------------------------------------------------------- |
| **LLM Provider**       | OpenAI (gpt-4o-mini) | Cost-efficient (~$1.35/10K conversations), good structured output                                     |
| **Processing Pattern** | Batch (daily/weekly) | Sufficient for ~100/week volume, cost-effective, simpler ops                                          |
| **Database**           | PostgreSQL           | Structured output schema, SQL aggregation for reporting, lower volume doesn't need horizontal scaling |
| **Issue Tracker**      | Shortcut             | Organization's existing tool (not Jira)                                                               |
| **Hosting (MVP)**      | Local                | User preference for MVP, can migrate later                                                            |

### Classification Schema

(Implemented in `src/classifier.py`, criteria in `docs/acceptance-criteria.md`)

```yaml
issue_type: # Mutually exclusive
  - bug_report # Something broken, errors, not working
  - feature_request # Wants new capability
  - product_question # How do I use feature X?
  - plan_question # What's included in my plan?
  - marketing_question # Social media strategy, platform issues
  - billing # Payments, refunds, subscription changes
  - account_access # Tailwind login/password issues
  - feedback # General feedback, praise, complaints
  - other # Truly unclassifiable

sentiment:
  - frustrated # Emotion words, ALL CAPS, complaints
  - neutral # Matter-of-fact, no emotion
  - satisfied # Positive feedback, gratitude

churn_risk:
  boolean # Stacks with any issue_type
  # true: Active cancellation intent ("I want to cancel")
  # false: Everything else (including past cancellations, billing disputes)

priority:
  - urgent # Complete account lockout, payment system failure
  - high # Customer explicitly can't work
  - normal # Most issues (default)
  - low # Pure positive feedback
```

### Architectural Pattern: Hybrid LLM + Rules

Phase 1 revealed that LLMs struggle with certain semantic distinctions (e.g., past-tense "I cancelled" vs present-intent "I want to cancel"). Our solution:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  LLM Classifier │ ──▶ │ Rule-Based Post- │ ──▶ │  Final Output   │
│  (gpt-4o-mini)  │     │   Processing     │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**When to use rules vs LLM:**

- **LLM**: Semantic understanding, nuance, context (issue type, sentiment)
- **Rules**: Pattern matching, edge case overrides, deterministic logic

This pattern applies to:

- Churn risk validation (implemented)
- Escalation routing (Phase 3)
- Deduplication logic (Phase 3)

---

## 5. Phased Implementation Plan

### Phase Overview

| Phase | Name                     | Focus                   | Success Criteria                         |
| ----- | ------------------------ | ----------------------- | ---------------------------------------- |
| 1     | Prototype                | Classification accuracy | ≥80% agreement with human baseline       |
| 2     | Batch Pipeline MVP       | End-to-end pipeline     | Runs daily, stores to DB, zero data loss |
| 3     | Product Tool Integration | Shortcut tickets        | Escalation rules route to correct queues |
| 4     | Real-Time Workflows      | Webhooks                | <5 min latency for critical issues       |
| 5     | Optimization             | Cost & quality          | <$50/month, maintain accuracy            |

---

### Phase 1: Prototype (VDD Approach)

**Goal**: Build a classification prompt that achieves ≥80% agreement with human-labeled baseline.

#### Step 1.1: Define Acceptance Criteria

Create `acceptance_criteria/phase1.yaml`:

```yaml
acceptance_criteria:
  - id: AC-P1-001
    description: "Issue type classification accuracy"
    metric: accuracy_vs_human_baseline
    field: issue_type
    threshold: ">= 0.80"
    test_script: tests/test_classification.py::test_issue_type_accuracy

  - id: AC-P1-002
    description: "Priority classification accuracy"
    metric: accuracy_vs_human_baseline
    field: priority
    threshold: ">= 0.75"
    test_script: tests/test_classification.py::test_priority_accuracy

  - id: AC-P1-003
    description: "Sentiment classification accuracy"
    metric: accuracy_vs_human_baseline
    field: sentiment_category
    threshold: ">= 0.80"
    test_script: tests/test_classification.py::test_sentiment_accuracy

  - id: AC-P1-004
    description: "Churn risk detection recall"
    metric: recall
    field: churn_risk
    condition: "churn_risk == HIGH"
    threshold: ">= 0.90"
    rationale: "Missing high churn risk is worse than false positives"
    test_script: tests/test_classification.py::test_churn_risk_recall

  - id: AC-P1-005
    description: "Output schema compliance"
    metric: schema_validation
    threshold: "100%"
    test_script: tests/test_classification.py::test_output_schema
```

#### Step 1.2: Create Labeled Test Fixtures

Create `tests/fixtures/labeled_conversations.json`:

- 30-50 sample Intercom conversations (anonymized)
- Each labeled with expected: issue_type, priority, sentiment, churn_risk
- Include edge cases: ambiguous conversations, multi-issue threads, empty messages
- **Human baseline**: Two humans label independently, measure agreement rate

#### Step 1.3: Write Failing Tests

Create `tests/test_classification.py`:

- Tests that load fixtures, run classification, compare to expected labels
- Calculate per-field accuracy
- Tests FAIL initially (no prompt exists yet)

#### Step 1.4: Generate & Iterate (GTR Loop)

1. Write initial classification prompt (in `docs/prompts.md`)
2. Run `prompt-tester` subagent against fixtures
3. Analyze failures, refine prompt
4. Max 5 iterations, then human review
5. Log each version with `/prompt-iteration`

#### Step 1.5: Human Validation

- Review edge cases where prompt disagrees with human labels
- Some disagreements may indicate bad labels (update fixtures)
- Final accuracy must meet thresholds before proceeding

**Deliverables**:

- `acceptance_criteria/phase1.yaml`
- `tests/fixtures/labeled_conversations.json`
- `tests/test_classification.py`
- Production prompt in `docs/prompts.md` with accuracy metrics
- `src/classifier.py` (or similar) implementing the classification

---

### Phase 2: Batch Pipeline MVP

**Goal**: End-to-end pipeline that fetches from Intercom, classifies, and stores to PostgreSQL.

#### Pipeline Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌────────────┐     ┌────────────┐
│   Intercom   │ ──▶ │ Quality Filter  │ ──▶ │ Classifier │ ──▶ │ PostgreSQL │
│    Fetch     │     │ (~50% pass)     │     │ (LLM+Rules)│     │   Store    │
└──────────────┘     └─────────────────┘     └────────────┘     └────────────┘
```

**Quality Filter** (learned from Phase 1):

- Only process `customer_initiated` conversations
- Author must be `user` (not admin, bot, lead)
- Body must have >20 characters of real content
- Skip template clicks ("I have a product question")

This filter reduces LLM costs by ~50% while improving classification quality.

#### Acceptance Criteria

| ID        | Description                          | Threshold                    |
| --------- | ------------------------------------ | ---------------------------- |
| AC-P2-001 | Intercom fetch completes             | No errors                    |
| AC-P2-002 | Quality filter applied before LLM    | ~50% filtered                |
| AC-P2-003 | All quality conversations classified | 100%                         |
| AC-P2-004 | Results stored to database           | 100%                         |
| AC-P2-005 | Pipeline is idempotent               | No duplicates                |
| AC-P2-006 | Performance                          | <5 min for 100 conversations |

**Deliverables**:

- `docs/acceptance-criteria-phase2.md` - Detailed criteria
- `src/intercom_client.py` - Intercom API integration + quality filter
- `src/pipeline.py` - Orchestration
- `src/db/models.py` - Pydantic models
- `src/db/schema.sql` - PostgreSQL schema
- `tests/test_pipeline.py`

---

### Phase 3: Product Tool Integration

**Goal**: Escalation rules route classified conversations to Shortcut as actionable tickets.

#### Acceptance Criteria (Preview)

- Rules in `docs/escalation-rules.md` are executable
- Feature requests with frequency ≥10 auto-create Shortcut stories
- Critical bugs auto-create Shortcut bugs with high priority
- Deduplication prevents duplicate tickets for same issue
- `escalation-validator` subagent confirms rule consistency

**Deliverables**:

- `acceptance_criteria/phase3.yaml`
- `src/escalation_engine.py` - Rule evaluation
- `src/shortcut_client.py` - Shortcut API integration
- `tests/test_escalation.py`

---

### Phase 4: Context Enhancements (In Progress)

**Goal**: Leverage help articles and Shortcut story data to improve classification quality and enable downstream analytics.

**New Data Sources**:

- Intercom Help Center articles (static knowledge base)
- Shortcut ↔ Intercom conversation linking (bidirectional via Story ID v2 and URL patterns)

**Key Insight**: These create a relationship graph (articles ↔ conversations ↔ stories) that provides ground truth labels and semantic context.

#### Phase 4a: Help Article Context Injection ⭐

**Status**: ✅ Complete - Unit tests passing (17/17), ready for real-data validation
**Timeline**: 1-2 days (actual)
**Complexity**: Low
**Impact**: High (+10-15% accuracy on conversations with article references)

**Approach**:

1. Extract help article URLs from conversation messages/metadata
2. Fetch article metadata via Intercom API (title, category, summary)
3. Inject article context into Stage 2 LLM prompt (similar to URL context boosting)
4. Store article references in database for analytics

**Deliverables**: ✅ Complete

- ✅ `src/help_article_extractor.py` - Article URL extraction and metadata fetching (197 lines)
- ✅ `migrations/001_add_help_article_references.sql` - Database schema with analytics views
- ✅ `src/db/models.py` - HelpArticleReference Pydantic model
- ✅ `src/classifier_stage2.py` - Prompt enrichment with `help_article_context` parameter
- ✅ `tests/test_help_article_extraction.py` - Comprehensive test suite (17/17 passing)
- ✅ `docs/phase4a-implementation.md` - Complete implementation documentation

**Testing Results**:

- ✅ Unit tests: 17/17 passing (100%)
- ✅ Error handling validated (graceful degradation)
- ✅ All URL patterns tested (3 formats)
- ✅ Testing infrastructure complete (validation script, accuracy testing script, test data template)
- ⏳ Real-data validation: Ready to execute (requires test dataset preparation)
- ⏳ Accuracy improvement testing: Ready to execute (requires ground truth labels)

**Testing Infrastructure** (Created):

- ✅ `scripts/validate_phase4_extractors.py` - Real-data extraction rate validation
- ✅ `scripts/test_phase4_accuracy_improvement.py` - A/B accuracy testing (baseline vs enriched)
- ✅ `scripts/test_conversations_template.json` - Test dataset format template
- ✅ `scripts/README.md` - Complete testing guide and documentation

**Success Criteria** (Unit Tests):

- ✅ Article reference extraction: Handles all URL formats
- ✅ Prompt enrichment: 100% when articles detected
- ✅ Error handling: Graceful failures, no pipeline breakage
- ✅ Database integrity: Migration 001 applied successfully (2026-01-07)
- ⏳ Extraction rate: Target 15-20% (awaiting measurement)
- ⏳ Accuracy improvement: Target +10-15% (awaiting A/B testing)

**GitHub Issue**: #18 (complete)

#### Phase 4b: Shortcut Story Context Injection ⭐

**Status**: ✅ Complete - Unit tests passing (20/20), ready for real-data validation
**Timeline**: 1-2 days (actual)
**Complexity**: Low
**Impact**: High (+15-20% accuracy on conversations with Story ID v2)

**Approach**:

1. Check for `Story ID v2` in conversation custom attributes
2. Fetch Shortcut story metadata via Shortcut API (labels, epic, name, description, state)
3. Inject story context into Stage 2 LLM prompt (human-validated product area context)
4. Store story linkage in database for analytics

**Deliverables**: ✅ Complete

- ✅ `src/shortcut_story_extractor.py` - Story ID extraction and metadata fetching (240 lines)
- ✅ `migrations/002_add_shortcut_story_links.sql` - Database schema with analytics views
- ✅ `src/db/models.py` - ShortcutStoryLink Pydantic model
- ✅ `src/classifier_stage2.py` - Prompt enrichment with `shortcut_story_context` parameter
- ✅ `tests/test_shortcut_story_extraction.py` - Comprehensive test suite (20/20 passing)
- ✅ `docs/phase4b-implementation.md` - Complete implementation documentation

**Testing Results**:

- ✅ Unit tests: 20/20 passing (100%)
- ✅ Story ID extraction: Handles prefixed/raw formats, whitespace normalization
- ✅ Label extraction: Supports object and string formats
- ✅ Error handling validated (graceful degradation)
- ✅ Testing infrastructure complete (same tools as Phase 4a)
- ⏳ Real-data validation: Ready to execute (requires test dataset preparation)
- ⏳ Accuracy improvement testing: Ready to execute (requires ground truth labels)

**Testing Infrastructure** (Shared with Phase 4a):

- ✅ `scripts/validate_phase4_extractors.py` - Validates both article and story extraction rates
- ✅ `scripts/test_phase4_accuracy_improvement.py` - Tests all 4 scenarios (baseline, articles, stories, combined)
- ✅ `scripts/test_conversations_template.json` - Includes story_id_v2 in test format
- ✅ `scripts/README.md` - Documents testing workflow for both phases

**Success Criteria** (Unit Tests):

- ✅ Story linkage extraction: Handles all ID formats
- ✅ Prompt enrichment: 100% when Story ID v2 detected
- ✅ Error handling: Graceful failures, no pipeline breakage
- ✅ Database integrity: Migration 002 applied successfully (2026-01-07)
- ⏳ Extraction rate: Target 30-40% (awaiting measurement)
- ⏳ Accuracy improvement: Target +15-20% (awaiting A/B testing)
- ⏳ Label alignment: Will measure with ground truth validation (Phase 5)

**GitHub Issue**: #23 (complete)

#### Phase 4c: Documentation Coverage Gap Analysis (Next Sprint)

**Status**: Ready to implement (Phase 4a complete)
**Timeline**: 2-3 days
**Complexity**: Low
**Impact**: High (actionable support insights)

**Approach**:

1. Identify themes that frequently appear WITHOUT help article references
2. Identify articles that users reference but still have problems
3. Generate weekly reports:
   - "Top 10 Undocumented Themes"
   - "Top 10 Confusing Articles"
   - "Documentation Gaps by Product Area"

**Deliverables**:

- `src/analytics/doc_coverage.py` - Gap analysis queries
- `scripts/generate_doc_coverage_report.py` - Weekly automation
- Slack/email notification integration

**Success Criteria**:

- Weekly report generation: 100% automated
- Gap identification: 5-10 undocumented themes per month
- Measurable impact: Track conversation reduction after adding docs

**GitHub Issue**: #19

**See**: `docs/context-enhancements.md` for complete design of all 6 enhancements (Phases 4a, 4b, 4c, 5, 6+)

---

### Phase 5: Ground Truth Validation & Vocabulary Feedback (Future)

**Goal**: Use Shortcut story data as ground truth to validate accuracy and keep vocabulary aligned with reality.

#### Enhancement 3: Shortcut Story Ground Truth Validation

**Timeline**: 3-5 days
**Complexity**: Medium
**Impact**: Medium (objective quality metrics)

**Approach**:

- Fetch conversations with `Story ID v2` metadata
- Run theme extraction, compare to Shortcut story labels
- Generate accuracy reports with matches/mismatches
- Identify vocabulary gaps

**GitHub Issue**: #20

#### Enhancement 4: Vocabulary Feedback Loop from Shortcut Labels

**Timeline**: 4-6 days
**Complexity**: Medium
**Impact**: High (keeps vocabulary aligned)

**Approach**:

- Periodically fetch Shortcut stories from Intercom conversations
- Aggregate story labels and epics
- Identify new labels not in current vocabulary (>10 occurrences = high priority)
- Human review + approval → vocabulary expansion

**GitHub Issue**: #21

---

### Phase 6+: Theme-Based Story Suggestions (Future)

**Goal**: Auto-suggest Shortcut story links using vector similarity search.

**Timeline**: 10-15 days
**Complexity**: High (requires ML infrastructure)
**Impact**: High (faster escalation, better tracking)

**Infrastructure Requirements**:

- PostgreSQL pgvector extension
- OpenAI embeddings API (~$0.06/month for 3000 conversations)

**GitHub Issue**: #22

---

### Phase 7: Real-Time Workflows (Future)

**Goal**: Webhook-driven processing for time-sensitive issues.

- Intercom webhooks trigger immediate classification
- Critical issues (P0 bugs, high churn risk) alert within 5 minutes
- Requires infrastructure changes (webhook endpoint, queue)

---

### Phase 8: Optimization (Ongoing)

**Goal**: Cost efficiency and quality maintenance.

- Monthly cost < $50 (currently projected ~$1.35/month at volume)
- Weekly quality audits (sample 50 classifications)
- Quarterly prompt evolution for new product areas
- Track impact metrics (% of backlog from FeedForward insights)

---

## 6. Project Structure

```
FeedForward/
├── .claude/
│   ├── commands/           # Slash commands
│   │   ├── update-docs.md
│   │   ├── session-end.md
│   │   ├── create-issues.md
│   │   └── prompt-iteration.md
│   ├── agents/             # Subagents (domain-specific)
│   │   ├── prompt-tester.md
│   │   ├── schema-validator.md
│   │   └── escalation-validator.md
│   ├── hooks/              # Automation hooks
│   │   ├── block-main-push.sh
│   │   └── test-gate.sh
│   └── settings.json       # Permissions
├── acceptance_criteria/    # Machine-readable AC (VDD)
│   ├── phase1.yaml
│   ├── phase2.yaml
│   └── phase3.yaml
├── docs/
│   ├── architecture.md     # System design
│   ├── status.md           # Progress tracking
│   ├── changelog.md        # What's shipped
│   ├── prompts.md          # Classification prompts + metrics
│   └── escalation-rules.md # Routing rules
├── reference/              # Source materials
│   ├── intercom-llm-guide.md
│   ├── UAT-Agentic-Coding-Research.md
│   └── setup.md
├── src/                    # Application code
│   ├── classifier.py
│   ├── pipeline.py
│   ├── intercom_client.py
│   ├── shortcut_client.py
│   ├── escalation_engine.py
│   └── db/
│       ├── models.py
│       └── schema.sql
├── tests/
│   ├── fixtures/
│   │   └── labeled_conversations.json
│   ├── test_classification.py
│   ├── test_pipeline.py
│   └── test_escalation.py
├── CLAUDE.md               # Agent context
├── PLAN.md                 # This document
├── .env.example
└── .gitignore
```

---

## 7. Key Constraints & Guardrails

### Development Constraints (from CLAUDE.md)

- **Define acceptance criteria before implementing features**
- **Limit autonomous iteration**: 3-5 cycles max before human review
- **Be explicit about non-functional requirements**: No implicit assumptions
- **Never push directly to `main`**: Use feature branches and PRs

### Security Constraints

- Secrets in `.env` only (never committed)
- No customer PII in test fixtures (anonymize or synthesize)
- Static analysis must pass before merge

### Quality Gates

- All acceptance criteria tests must pass
- Test coverage ≥ 80% for new code
- `schema-validator` confirms Pydantic/DB/LLM alignment
- `escalation-validator` confirms rule consistency

---

## 8. Getting Started (For New Sessions)

### Context Loading Checklist

1. Read this document (`PLAN.md`) first
2. Read `CLAUDE.md` for project conventions
3. Check `docs/status.md` for current progress
4. Review relevant `acceptance_criteria/*.yaml` for current phase

### Before Writing Code

1. Identify which phase you're working on
2. Ensure acceptance criteria exist for the task
3. Check if tests exist (should be failing if criteria not yet met)
4. If no criteria/tests exist, create them FIRST

### After Completing Work

1. Run `/update-docs` to sync documentation
2. Use `/session-end [summary]` to commit and log progress
3. Developer-kit commands (`/developer-kit:changelog`, `/developer-kit:reflect`) handle changelog and session reflection

---

## 9. Open Questions & Decisions Pending

| Question                                | Status  | Notes                                                     |
| --------------------------------------- | ------- | --------------------------------------------------------- |
| How to source labeled test fixtures?    | Pending | Options: Export from Intercom, manually label, synthesize |
| PostgreSQL hosting for MVP?             | Pending | Options: Local, Supabase, Railway                         |
| Shortcut workspace/project for tickets? | Pending | Need user to specify                                      |

---

## 10. Revision History

| Date       | Author        | Change        |
| ---------- | ------------- | ------------- |
| 2026-01-06 | Claude + User | Initial draft |

---

_This document is the source of truth for FeedForward. Update it when decisions change._
