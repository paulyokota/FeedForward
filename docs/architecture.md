# Architecture

## Overview

FeedForward is an LLM-powered pipeline for analyzing Intercom conversations and extracting product insights.

**Goal**: Create implementation-ready Shortcut stories from support conversations.

**Key Insight**: Categories (billing_question, product_issue, etc.) are **routing tools only** - they help direct conversations but are NOT the end deliverable. The real output is **themes** - specific, actionable issue signatures that map to implementation tickets.

**Pipeline Flow**:

```
Conversations → Classification (routing) → Theme Extraction → Confidence Scoring → PM Review → Shortcut Stories
                     ↑                            ↓                    ↓              ↓
               (routing tool)            (specific issues)    (quality gate)   (deliverable)
```

**Current Phase**:

- Phase 1 (Two-Stage Classification): ✅ Complete - routing categories
- Phase 4 (Theme Extraction & Aggregation): ✅ Complete - specific themes
- Story Grouping Architecture: 🚧 In Progress - PM review + story creation

## System Design

```
┌──────────────┐
│   Scheduler  │ (cron/GitHub Actions)
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────┐
│       Intercom API               │
│  - Fetch conversations           │
│  - Quality filtering (~50% pass) │
│  - Extract source.url            │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│   Classification (Routing Only)  │  ← Categories for routing, NOT deliverable
│  - 8 broad categories            │
│  - Fast routing decisions        │
│  - Spam filtering                │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│   Theme Extraction (LLM)         │  ← THE DELIVERABLE: Specific themes
│  - 78-theme vocabulary           │
│  - URL context boosting          │
│  - Specific issue signatures     │
│  - e.g., pinterest_pin_failure   │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│   Confidence Scoring             │  ← Quality gate for groupings
│  - Semantic similarity (30%)     │
│  - Intent homogeneity (15%)      │
│  - Symptom overlap (10%)         │
│  - Product/component match       │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│   PM Review Layer                │  ← Human-in-the-loop validation
│  - "Same implementation ticket?" │
│  - Sub-group creation            │
│  - INVEST criteria enforcement   │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│   Shortcut Story Creation        │  ← FINAL OUTPUT
│  - Implementation-ready stories  │
│  - Linked sample conversations   │
│  - PM reasoning included         │
└──────────────────────────────────┘
```

## Components

### 1. Intercom Client (`src/intercom_client.py`)

**Purpose**: Fetch and filter conversations from Intercom API

**Key Features**:

- Quality filtering (~50% pass rate) - filters out bot/admin messages, template clicks
- Extracts `source.url` for URL context boosting
- Paginated fetching with rate limiting
- HTML stripping and text normalization

**Output**: `IntercomConversation` objects ready for classification

### 2. Theme Extractor (`src/theme_extractor.py`)

**Purpose**: LLM-powered theme extraction with vocabulary guidance

**Architecture**:

- **Model**: OpenAI gpt-4o-mini (cost-optimized, fast)
- **Approach**: Vocabulary-guided match-first extraction
- **URL Context**: Boosts product area matching using `source.url`
- **Canonicalization**: Merges similar issues using embeddings or LLM

**Key Features**:

- Vocabulary-aware prompts (load known themes)
- URL pattern matching → product area boosting
- Strict mode (backfill) vs. flexible mode (new themes)
- Embedding-based similarity for canonicalization

**Output**: `Theme` objects with structured issue signatures

### 3. Theme Vocabulary (`src/vocabulary.py`)

**Purpose**: Managed vocabulary of known themes

**Structure**:

- **Themes**: 61 active themes across 20+ product areas
- **Keywords**: Customer-friendly aliases for matching
- **URL Patterns**: 27 URL patterns for product area disambiguation
- **Product Area Mapping**: Themes grouped by Shortcut product areas

**Key Features**:

- Match-first extraction (prefer existing themes)
- URL context mapping for disambiguation
- Version tracking (currently v2.9)
- Easy expansion and merging

**File**: `config/theme_vocabulary.json`

### 4. Database Layer (`src/db/`)

**Engine**: PostgreSQL (local for MVP)

**Schema**:

- `conversations` - Raw classified conversations with source_url
- `themes` - Individual theme extractions
- `theme_aggregates` - Rolled-up counts by issue signature
- `pipeline_runs` - Batch execution tracking

**Key Features**:

- Theme deduplication via signature matching
- Aggregation views for reporting
- Full-text search on symptoms

### 5. URL Context System (NEW)

**Purpose**: Disambiguate product areas using page URL

**How It Works**:

1. Conversation includes `source.url` (e.g., `/dashboard/v2/scheduler`)
2. URL matches pattern in `url_context_mapping` → Product area
3. LLM prompt includes URL context hint
4. Theme extraction prioritizes themes from that product area

**Validation**:

- 80% pattern match rate on live data
- 100% product area accuracy (no false positives)
- Solves three-scheduler disambiguation problem

**Critical for**: Legacy Publisher vs. Pin Scheduler vs. Multi-Network routing

### 6. Two-Stage Classification System (Phase 1) ✅

**Purpose**: Fast routing + accurate analytics through two-stage LLM classification

**Architecture**:

```
Customer Message
    ↓
┌─────────────────────────────────────┐
│  Stage 1: Fast Routing Classifier   │
│  - Customer message only            │
│  - gpt-4o-mini (temp 0.3)           │
│  - <1s response time                │
│  - 8 conversation types             │
│  - URL context hints                │
└─────────────┬───────────────────────┘
              │ Routing Decision
              ↓
    [Support Team Handles]
              │
              ↓ Support Responses
┌─────────────────────────────────────┐
│  Stage 2: Refined Analysis          │
│  - Full conversation context        │
│  - gpt-4o-mini (temp 0.1)           │
│  - High accuracy target             │
│  - Disambiguation tracking          │
│  - Support insights extraction      │
└─────────────┬───────────────────────┘
              │
              ↓
    Knowledge Base & Analytics
```

**Components**:

1. **Stage 1 Classifier** (`src/classifier_stage1.py`)
   - **Purpose**: Fast routing for immediate support needs
   - **Input**: Customer message + optional URL context
   - **Speed**: <1 second (gpt-4o-mini, temp 0.3)
   - **Confidence**: Medium-high acceptable (routing decision)
   - **Output**: conversation_type, routing_priority, auto_response_eligible
   - **Types**: product_issue, how_to_question, feature_request, account_issue, billing_question, configuration_help, general_inquiry, spam

2. **Stage 2 Classifier** (`src/classifier_stage2.py`)
   - **Purpose**: Accurate classification for analytics and knowledge extraction
   - **Input**: Customer message + support responses + resolution signals
   - **Accuracy**: High confidence target (gpt-4o-mini, temp 0.1)
   - **Features**:
     - Disambiguation tracking (what customer said vs. what support revealed)
     - Support insights extraction (root cause, solution type, products/features)
     - Classification refinement (can override Stage 1)
     - Resolution pattern detection
   - **Output**: refined conversation_type, confidence, disambiguation_level, support_insights

3. **Resolution and Knowledge Integration** (PR #92)
   - **ResolutionAnalyzer** (`src/resolution_analyzer.py`) - Integrated into `two_stage_pipeline.py`
     - Detects 48 resolution patterns across 6 categories
     - Provides full analysis: primary_action, action_category, all_actions, categories, suggested_type
     - Module-level eager initialization for efficient re-use
   - **KnowledgeExtractor** (`src/knowledge_extractor.py`) - Integrated into `two_stage_pipeline.py`
     - Extracts: root_cause, solution_provided, product_mentions, feature_mentions
     - Detects self_service_gap with gap_evidence
   - **support_insights JSONB** - Populated with structured data:
     ```json
     {
       "resolution_analysis": {
         "primary_action": "refund_processed",
         "action_category": "billing_resolution",
         "all_actions": ["refund_processed"],
         "categories": ["billing"],
         "suggested_type": "billing_question",
         "matched_keywords": ["processed your refund"]
       },
       "knowledge": {
         "root_cause": "billing sync issue",
         "solution_provided": "processed refund",
         "product_mentions": ["Pro plan"],
         "feature_mentions": ["billing"],
         "self_service_gap": true,
         "gap_evidence": "Support manually cancelled"
       }
     }
     ```

**Test Results**:

- **Stage 1**: 100% high confidence on test data (5/5 real conversations)
- **Stage 2**: 100% high confidence with support context (3/3 conversations)
- **Classification improvements**: 33% (1/3 refined from Stage 1)
- **Disambiguation**: 100% high on all conversations with support
- **Value**: Instagram issue correctly refined account_issue → configuration_help

**Key Achievement**: Demonstrates disambiguation value

```
Customer: "Having trouble getting my Instagram account connected"
Stage 1: account_issue (high) - Routes to account support

Support reveals: Business account type + Facebook Page requirements
Stage 2: configuration_help (high) - True root cause identified
```

**Files**:

- `src/classifier_stage1.py` - Fast routing classifier
- `src/classifier_stage2.py` - Refined analysis classifier
- `src/classification_manager.py` - Orchestrates both stages
- `src/resolution_analyzer.py` - Detects support actions (integrated into two_stage_pipeline.py)
- `src/knowledge_extractor.py` - Extracts insights per conversation (integrated into two_stage_pipeline.py)
- `src/knowledge_aggregator.py` - Aggregates knowledge across conversations
- `src/two_stage_pipeline.py` - End-to-end pipeline with ResolutionAnalyzer + KnowledgeExtractor integration
- `tests/test_pipeline_integration_insights.py` - 21 tests for pipeline integration

**Status**: Production ready, support_insights populated with resolution_analysis and knowledge data

### 7. Equivalence Class System (NEW - 2026-01-08)

**Purpose**: Enable accurate conversation grouping without modifying the core classifier

**Problem Solved**: Human groupings (via Shortcut story_id) showed that conversations classified as `bug_report` and `product_question` are often the same underlying issue expressed differently. Rather than losing the granularity of the original categories (which have routing value), we introduce equivalence classes at the evaluation layer.

**Architecture**:

```
Original Classification          Equivalence Class (for grouping)
─────────────────────────────    ─────────────────────────────────
bug_report          ───────────→ technical
product_question    ───────────→ technical
plan_question + bug indicators → technical (context-aware)
all other categories ──────────→ themselves
```

**Components**:

1. **Base Equivalence Mapping** (`src/equivalence.py`)
   - `bug_report` → `technical`
   - `product_question` → `technical`

2. **Context-Aware Refinement**
   - Detects bug indicators in `plan_question` messages
   - Keywords: "not letting", "won't let", "can't", "not working", etc.
   - When detected, treats as `technical` for grouping

3. **Short Message Handling**
   - Messages <5 words classified as "other" are ambiguous
   - Skipped in accuracy calculations

**Results**:

- Baseline accuracy: 41.7%
- Final accuracy: 100% (after data cleanup)
- Preserves all 9 original categories for routing
- Uses equivalence only for grouping/reporting

**Files**:

- `src/equivalence.py` - Production equivalence logic
- `scripts/evaluate_with_equivalence.py` - Evaluation script
- `data/story_id_ground_truth.json` - Ground truth dataset

### 8. Vocabulary Feedback Loop (NEW - 2026-01-08)

**Purpose**: Continuous monitoring for vocabulary drift and gap detection

**Problem Solved**: As the product evolves, new features and product areas may emerge that aren't covered by the existing vocabulary. This system detects gaps before they become significant.

**How It Works**:

```
Shortcut API (recent stories)
        ↓
Extract product areas & labels
        ↓
Compare against COVERED_PRODUCT_AREAS
        ↓
Generate gap report with priorities
```

**Usage**:

```bash
# Monthly check (recommended)
python -m src.vocabulary_feedback --days 30

# Quarterly check
python -m src.vocabulary_feedback --days 90

# Save to file
python -m src.vocabulary_feedback --days 30 --output reports/vocab_feedback.md
```

**Coverage Status** (as of 2026-01-08):

- 17 Shortcut product areas covered
- 0 vocabulary gaps found
- 100% coverage of ground truth dataset

**Files**:

- `src/vocabulary_feedback.py` - Feedback loop script
- `prompts/phase5_final_report_2026-01-08.md` - Validation report

### 9. Signature Tracking System (NEW - 2026-01-09)

**Purpose**: Prevent signature mismatches between theme extraction and story creation

**Problem Solved**: During historical backfill, we discovered that 88% of conversation counts were orphaned because:

1. Theme extractor produces signature: `billing_cancellation_request`
2. PM review modifies it to: `billing_cancellation_requests`
3. Stories created with PM's signature
4. Backfill counts using extractor's signature
5. Phase 3 can't match counts to stories (different keys)

**Architecture**:

```
Theme Extraction          PM Review           Story Creation
─────────────────────    ──────────────      ────────────────
billing_cancellation_    suggests:           story created as:
request                  billing_cancella-   billing_cancella-
                         tion_requests       tion_requests
        │                       │                   │
        │   ┌───────────────────┼───────────────────┘
        │   │ SignatureRegistry │
        │   │ ─────────────────│────────────────────
        └──►│ equivalences:    │
            │   original → PM  │
            │                  ▼
            │ reconcile_counts() merges both
            └─────────────────────────────────────
```

**Components**:

1. **SignatureRegistry** (`src/signature_utils.py`)
   - `normalize()` - Standardizes signatures (lowercase, underscores)
   - `register_equivalence()` - Tracks original → PM signature mapping
   - `get_canonical()` - Returns PM-approved form
   - `reconcile_counts()` - Merges counts using equivalences

2. **Equivalence File** (`data/signature_equivalences.json`)
   - Persists mappings between pipeline runs
   - Format: `{"equivalences": {"original": "canonical"}}`

**Usage in Pipeline**:

```python
# Phase 1: When PM review changes signature
registry = get_registry()
if sg_sig != original_sig:
    registry.register_equivalence(original_sig, sg_sig)
registry.save()  # Persist for Phase 3

# Phase 3: Reconcile counts
reconciled, orphans = registry.reconcile_counts(counts, story_mapping)
# reconciled now has all counts merged by canonical signature
```

**Validation**:

- Run `python -c "from src.signature_utils import SignatureRegistry; r = SignatureRegistry(); print(f'{len(r._equivalences)} equivalences')"` to check mappings
- After Phase 3, orphan percentage should be <5% (vs 88% without this system)

**Files**:

- `src/signature_utils.py` - Registry implementation
- `data/signature_equivalences.json` - Persisted mappings
- `scripts/run_historical_pipeline.py` - Updated to use registry

### 10. Evidence Validation System (NEW - 2026-01-09)

**Purpose**: Ensure Shortcut stories have actionable evidence, not placeholder text

**Problem Solved**: Stories created during historical backfill had placeholder text:

```
Note: This theme was identified during historical backfill.
Sample conversations were not captured during batch processing.

To gather evidence:
- Search Intercom for recent conversations matching this theme
- Add representative samples to this ticket
```

This defeats the purpose of automated story creation.

**Architecture**:

```
Theme Extraction          Evidence Validator         Story Creation
─────────────────        ──────────────────        ────────────────
Extract themes &  ──────►  validate_samples()  ────► If valid:
capture metadata          - Check required fields     create story
                          - Check for placeholders
                          - Calculate coverage      If invalid:
                                                     SKIP + warn
```

**Required vs Recommended Fields**:

| Field          | Type        | Purpose                | Validation                                  |
| -------------- | ----------- | ---------------------- | ------------------------------------------- |
| `id`           | REQUIRED    | Conversation reference | Must be present                             |
| `excerpt`      | REQUIRED    | Context for story      | Must be present, >20 chars, no placeholders |
| `email`        | RECOMMENDED | Display in story       | Warn if <80% coverage                       |
| `intercom_url` | RECOMMENDED | Link to conversation   | Warn if <80% coverage                       |
| `org_id`       | OPTIONAL    | Jarvis org link        | No validation                               |
| `user_id`      | OPTIONAL    | Jarvis user link       | No validation                               |
| `contact_id`   | OPTIONAL    | Lookup reference       | No validation                               |

**Validation Behavior**:

1. **Invalid samples (missing required fields)**: Story creation SKIPPED with error message
2. **Poor evidence (missing recommended fields)**: Story created with WARNING
3. **Placeholder excerpts detected**: Story creation SKIPPED (catches the historical backfill bug)

**Components**:

1. **EvidenceValidator** (`src/evidence_validator.py`)
   - `validate_samples()` - Main validation function
   - `validate_sample()` - Single sample validation
   - `build_evidence_report()` - Human-readable report
   - `EvidenceQuality` dataclass with is_valid, errors, warnings, coverage

2. **Integration Points**:
   - `scripts/create_theme_stories.py` - Validates before creating each story
   - `scripts/run_historical_pipeline.py` - Validates in Phase 1 and orphan promotion

**Usage**:

```python
from evidence_validator import validate_samples

evidence = validate_samples(data["samples"])
if not evidence.is_valid:
    print(f"SKIPPING: {evidence.errors}")
    continue
if evidence.warnings:
    print(f"Warning: {evidence.warnings}")

# Safe to create story
create_story(data)
```

**Validation**:

- Run `python -m pytest tests/test_evidence_validator.py -v` (20 tests)
- Includes real-world scenario test for placeholder detection

**Files**:

- `src/evidence_validator.py` - Validation implementation
- `tests/test_evidence_validator.py` - Test suite
- `scripts/create_theme_stories.py` - Uses validation
- `scripts/run_historical_pipeline.py` - Uses validation

---

### 11. Story Grouping Pipeline (2026-01-08)

**Purpose**: Create implementation-ready story groupings from classified conversations

**Problem Solved**: Theme extraction groups conversations by `issue_signature`, but these aren't implementation-ready. Example: `instagram_oauth_multi_account` contained Pinterest, Instagram, AND Facebook issues - never in the same sprint ticket.

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Theme Extraction (per-conversation)               │
│  - Extract theme, symptoms, intent                          │
│  - Initial signature assignment from vocabulary             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: Initial Grouping + Confidence Scoring             │
│  - Group by signature                                       │
│  - Score each group (semantic similarity, overlap)          │
│  - Sort by confidence DESC                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: PM/Tech Lead Review (iterative)                   │
│  - "Same implementation ticket? If not, split how?"         │
│  - Creates validated sub-groups                             │
│  - Orphans (<3 convos) accumulate over time                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: Story Creation                                    │
│  - Only from validated groups (≥3 conversations)            │
│  - Include PM reasoning in description                      │
└─────────────────────────────────────────────────────────────┘
```

**Confidence Scoring Signals** (calibrated):

| Signal              | Weight | Description                    |
| ------------------- | ------ | ------------------------------ |
| Semantic similarity | 30%    | Embedding cosine similarity    |
| Intent similarity   | 20%    | User intent embeddings         |
| Intent homogeneity  | 15%    | Penalizes high variance        |
| Symptom overlap     | 10%    | Jaccard similarity             |
| Product area match  | 10%    | Boolean                        |
| Component match     | 10%    | Boolean                        |
| Platform uniformity | 5%     | Detects Pinterest/IG/FB mixing |

**Validation Results** (ground truth comparison):

| Metric             | Value      |
| ------------------ | ---------- |
| Pairwise Precision | 35.6%      |
| Pairwise Recall    | 10.6%      |
| Pure Groups        | 9/20 (45%) |

**Key Finding**: Low recall is correct - humans group broadly for triage, we group narrowly for implementation per INVEST criteria.

**Files**:

- `src/confidence_scorer.py` - Confidence scoring
- `scripts/run_pm_review_all.py` - PM review batch runner
- `scripts/validate_grouping_accuracy.py` - Validation pipeline
- `docs/story-grouping-architecture.md` - Full architecture doc
- `docs/story-granularity-standard.md` - INVEST-based criteria

### 10. Conversation Type Classification (Legacy)

**Strategic Decision**: All-Support Strategy (2026-01-07)

FeedForward tracks **all support conversations**, not just product issues. This provides richer customer insights for product, support, and success teams.

**Classification Schema** (7 types):

1. **Product Issue** - Bug reports, features not working, data issues
2. **How-To Question** - Feature usage, workflows, feature discovery
3. **Feature Request** - New capabilities, enhancements, integrations
4. **Account Issue** - Login, access, OAuth, permissions
5. **Billing Question** - Payment, plans, invoices, subscriptions
6. **Configuration Help** - Setup, integration config, settings
7. **General Inquiry** - Unclear intent, exploratory questions

Plus: **Spam/Not Support** (filtered out)

**Distribution** (based on 75-conversation analysis, 2026-01-07):

- How-To Questions: 25% (high confidence)
- Account Issues: 20% (high confidence, 93% from email)
- Billing Questions: 7% (high confidence)
- Feature Requests: 1%
- General/Unclear: 37% (needs quality filtering improvement)
- Spam: 4% (should be filtered at source)

**Source Type Patterns**:

- **In-app conversations** → 83% how-to + general inquiry (users actively in product)
- **Email** → 42% account issues + 12% billing (can't access product)

**Vocabulary Implications**:

- ✅ Product themes covered (61 themes, 20+ areas)
- ❌ **Billing themes missing** (critical gap - 7% of conversations)
- ❌ Account/auth themes missing (20% of conversations)
- ⚠️ Onboarding/setup themes sparse

See: `docs/conversation-type-schema.md` for full analysis

## Data Flow

### Theme Extraction Pipeline

```
1. Fetch Conversations
   └─> IntercomClient.fetch_quality_conversations()
       - Filter by quality
       - Extract source.url

2. URL Context Matching
   └─> ThemeVocabulary.match_url_to_product_area()
       - Check URL against patterns
       - Return matched product area

3. Theme Extraction
   └─> ThemeExtractor.extract()
       - Build vocabulary-aware prompt
       - Inject URL context hint (if matched)
       - LLM extracts theme details
       - Canonicalize signature

4. Store Results
   └─> Database.store_theme()
       - Insert theme record
       - Update aggregates
       - Calculate embeddings
```

### URL Context Boosting Flow

```
User Message: "My posts aren't scheduling"
    + source.url: "/publisher/queue"
         ↓
URL Pattern Match: "/publisher/queue" → Legacy Publisher
         ↓
Prompt Enhancement:
    "User was on **Legacy Publisher** page.
     Strongly prefer Legacy Publisher themes."
         ↓
Theme Prioritization: Legacy Publisher themes shown first
         ↓
Result: scheduling_failure_legacy (Legacy Publisher) ✓

Without URL context → Could match any of 3 schedulers (ambiguous)
```

## Performance Patterns

### Async Classification Pipeline

**File**: `src/two_stage_pipeline.py`

The pipeline supports both sync and async modes:

```bash
# Sync mode (debugging, small batches)
python -m src.two_stage_pipeline --days 7 --max 10

# Async mode (production, ~10-20x faster)
python -m src.two_stage_pipeline --async --days 30 --concurrency 20
```

**How It Works**:

1. Fetch all conversations (sync - Intercom client limitation)
2. Classify in parallel using `asyncio.gather()` with semaphore
3. Batch insert results to database

**Speedup**: ~10-20x for classification phase

### Batch Database Operations

**File**: `src/db/classification_storage.py`

**Batch Inserts**: `store_classification_results_batch()`

- Uses `psycopg2.extras.execute_values()` for bulk upserts
- Single query for N rows instead of N queries
- ~50x faster for batches of 50+

**Consolidated Stats**: `get_classification_stats()`

- Single CTE query instead of 8 separate queries
- ~8x faster stats retrieval

### Parallel Contact Fetching

**File**: `src/intercom_client.py`

```python
# Old way (N+1 pattern - slow)
for conv in conversations:
    org_id = client.fetch_contact_org_id(conv.contact_id)  # 1 API call each

# New way (batch - fast)
contact_ids = [c.contact_id for c in conversations]
org_id_map = client.fetch_contact_org_ids_batch_sync(contact_ids)  # Parallel
for conv in conversations:
    org_id = org_id_map.get(conv.contact_id)  # Dict lookup
```

**How It Works**:

- `aiohttp` for async HTTP requests
- Semaphore limits concurrency (default 20)
- Deduplicates contact_ids automatically

**Speedup**: ~50x for contact enrichment

### Performance Summary

| Operation                   | Before      | After     | Speedup |
| --------------------------- | ----------- | --------- | ------- |
| Classification (100 convos) | ~200s       | ~10-15s   | 10-20x  |
| DB inserts (100 rows)       | 100 queries | 2 queries | 50x     |
| Stats query                 | 8 queries   | 1 query   | 8x      |
| Contact fetch (100)         | ~100s       | ~2-5s     | 20-50x  |

## Dependencies

### External Services

- **Intercom API** - Conversation data source
- **OpenAI API** - LLM for theme extraction (gpt-4o-mini)
- **Shortcut API** - Training data and validation (read-only)

### Python Libraries

- `openai` - OpenAI API client
- `psycopg2` - PostgreSQL driver
- `requests` - HTTP client for APIs
- `numpy` - Vector operations for embeddings
- `pydantic` - Data validation and models

### Development Tools

- `pytest` - Testing framework
- `streamlit` - Theme labeling UI
- `python-dotenv` - Environment configuration

## Configuration

### Environment Variables

Required:

- `INTERCOM_ACCESS_TOKEN` - Intercom API access
- `OPENAI_API_KEY` - OpenAI API key
- `DATABASE_URL` - PostgreSQL connection string

Optional:

- `SHORTCUT_API_TOKEN` - For training data validation

### Vocabulary Configuration

**File**: `config/theme_vocabulary.json`

**Key Sections**:

- `themes` - 61 theme definitions with keywords
- `product_area_mapping` - Themes grouped by Shortcut labels
- `url_context_mapping` - 27 URL patterns for disambiguation
- `version` - Currently v2.9

## Validation & Testing

### Validation Approach (VDD)

**Validation-Driven Development**:

- Define acceptance criteria BEFORE implementation
- Write failing tests first
- Max 3-5 autonomous iterations before human review
- Measure success objectively (accuracy thresholds)

### Test Data

- **Shortcut Training Data**: 829 manually-labeled stories
- **Validation Accuracy**: 52.5% (keyword baseline)
- **LLM Precision**: 74% on classified stories (48% unclassified)

### Testing Tools

- `tools/validate_shortcut_data.py` - Keyword vs LLM validation
- `tools/test_url_context.py` - Unit tests for URL matching
- `tools/test_url_context_live.py` - Live data validation
- `tools/theme_labeler.py` - Streamlit UI for manual labeling

### 12. API and Frontend Layer (NEW - 2026-01-09)

**Purpose**: Operational visibility into the pipeline - kick off runs, check status, browse themes.

**Architecture Decision**: FastAPI backend + Streamlit frontend because:

- API layer survives frontend changes
- Enables future CLI/mobile clients
- Supports future multi-source ingestion (research repos beyond Intercom)

**System Design**:

```
┌─────────────────────┐     ┌─────────────────────┐
│  Streamlit Frontend │────►│   FastAPI Backend   │
│  (localhost:8501)   │     │   (localhost:8000)  │
│                     │     │                     │
│  - Dashboard        │     │  - /api/analytics   │
│  - Pipeline         │     │  - /api/pipeline    │
│  - Themes           │     │  - /api/themes      │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │     PostgreSQL      │
                            │  conversations      │
                            │  themes             │
                            │  pipeline_runs      │
                            └─────────────────────┘
```

**API Endpoints (25+ total)**:

| Category  | Endpoints                                                                                   |
| --------- | ------------------------------------------------------------------------------------------- |
| Health    | `/health`, `/health/db`, `/health/full`                                                     |
| Analytics | `/api/analytics/dashboard`, `/stats`, `/stories`, `/themes/trending`, `/sources`            |
| Pipeline  | `/api/pipeline/run`, `/status/{id}`, `/status/{id}/preview`, `/history`, `/active`, `/stop` |
| Themes    | `/api/themes/trending`, `/orphans`, `/singletons`, `/all`, `/{signature}`                   |
| Stories   | `/api/stories`, `/api/stories/{id}`, `/board`, `/search`                                    |
| Sync      | `/api/sync/shortcut/push`, `/pull`, `/webhook`, `/status/{id}`                              |
| Labels    | `/api/labels`, `/api/labels/import`                                                         |

**Frontend Pages**:

| Page      | Purpose                                             |
| --------- | --------------------------------------------------- |
| Dashboard | Metrics overview, classification distribution, runs |
| Pipeline  | Run configuration, status polling, history          |
| Themes    | Trending/orphan/singleton tabs, filtering           |

**Files**:

```
src/api/
├── main.py           # FastAPI app (19 routes)
├── deps.py           # DB dependency injection
├── routers/
│   ├── health.py     # Health checks
│   ├── analytics.py  # Dashboard metrics
│   ├── pipeline.py   # Run/status/history
│   └── themes.py     # Trending/orphans
└── schemas/          # Pydantic models

frontend/
├── app.py            # Streamlit entry
├── api_client.py     # API wrapper
└── pages/
    ├── 1_Dashboard.py
    ├── 2_Pipeline.py
    └── 3_Themes.py
```

**Running**:

```bash
# Terminal 1
uvicorn src.api.main:app --reload --port 8000

# Terminal 2
streamlit run frontend/app.py

# Then open http://localhost:8501
```

API docs at http://localhost:8000/docs

---

### 13. Multi-Source Data Integration: Coda (NEW - 2026-01-09)

**Purpose**: Extend theme extraction beyond Intercom to include UX research data from Coda.

**Data Source**: Tailwind Research Ops (`c4RRJ_VLtW`)

**Content Types**:

| Type                | Count               | Content                                          | Value  |
| ------------------- | ------------------- | ------------------------------------------------ | ------ |
| AI Summary          | 27 (5-10 populated) | Synthesized interview insights, quotes, personas | HIGH   |
| Discovery Learnings | 1                   | JTBD framework, MVP priorities                   | HIGH   |
| Research Questions  | 1                   | Product research priorities                      | MEDIUM |
| Debrief/Notes       | 16                  | Templates (mostly unfilled)                      | LOW    |

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  Coda Research Repository                                   │
│  - AI Summaries (user interviews)                          │
│  - Discovery Learnings (synthesized insights)              │
│  - Research Questions (product priorities)                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Coda Client (src/coda_client.py - planned)                │
│  - Fetch pages by type                                     │
│  - Parse structured content                                │
│  - Extract quotes and insights                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Theme Extraction                                          │
│  - Map Coda sections to theme types                        │
│  - Extract user quotes as evidence                         │
│  - Classify by product area                                │
│  - Merge with Intercom-sourced themes                      │
└─────────────────────────────────────────────────────────────┘
```

**Extractable Theme Types**:

| Theme Type        | Coda Source                  | Example                                                  |
| ----------------- | ---------------------------- | -------------------------------------------------------- |
| Pain Point        | AI Summary quotes            | "I have to pick the board manually for every single pin" |
| Feature Request   | AI Summary feature sections  | "Help me generate descriptions in-app"                   |
| Workflow Friction | AI Summary workflow sections | "20 tab switches per minute"                             |
| User Need/Job     | Discovery Learnings          | "Knowing how much work I have done/left to do"           |

**API Access**:

```python
# Get page content
GET /docs/{doc_id}/pages/{page_id}/content

# Returns structured content with:
# - style: h1, h2, h3, paragraph, bulletedListItem
# - content: Plain text
# - lineLevel: Indentation
```

**Configuration** (`.env`):

```
CODA_API_KEY=<api_key>
CODA_DOC_ID=c4RRJ_VLtW
```

**Documentation**: `docs/coda-research-repo.md`

---

### 14. Story Tracking System (NEW - 2026-01-10)

**Purpose**: Canonical story management with bidirectional Shortcut sync and analytics.

**Architecture**:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Webapp (Next.js)  │────►│   FastAPI Backend   │────►│   Shortcut API      │
│   (localhost:3000)  │     │   (localhost:8000)  │     │   (external)        │
│                     │     │                     │     │                     │
│  - Board view       │     │  - /api/stories     │     │  - Create stories   │
│  - Story detail     │     │  - /api/sync        │     │  - Update stories   │
│  - Edit mode        │     │  - /api/labels      │     │  - Webhook events   │
└─────────────────────┘     └──────────┬──────────┘     └─────────────────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │     PostgreSQL      │
                            │  stories            │
                            │  story_evidence     │
                            │  story_sync_metadata│
                            │  label_registry     │
                            └─────────────────────┘
```

**Services** (`src/story_tracking/services/`):

| Service                    | Purpose                                                  |
| -------------------------- | -------------------------------------------------------- |
| `StoryService`             | CRUD, search, board view, status management              |
| `EvidenceService`          | Evidence bundles, conversation/theme linking             |
| `SyncService`              | Bidirectional Shortcut sync (push/pull/webhook)          |
| `LabelRegistryService`     | Label management, Shortcut taxonomy import               |
| `AnalyticsService`         | Story metrics, trending themes, source distribution      |
| `StoryCreationService`     | **Canonical** story creation with quality gates (PR #81) |
| `OrphanService`            | Manage orphan conversations below MIN_GROUP_SIZE         |
| `OrphanIntegrationService` | Unified orphan routing from quality gate failures        |

**API Routes**:

| Category  | Endpoints                                                               |
| --------- | ----------------------------------------------------------------------- |
| Stories   | `GET/POST /api/stories`, `GET/PATCH/DELETE /api/stories/{id}`           |
| Board     | `GET /api/stories/board`, `GET /api/stories/search`                     |
| Evidence  | `POST /api/stories/{id}/evidence/*`                                     |
| Sync      | `POST /api/sync/shortcut/push`, `/pull`, `/webhook`, `GET /status/{id}` |
| Labels    | `GET /api/labels`, `POST /api/labels`, `POST /api/labels/import`        |
| Analytics | `GET /api/analytics/stories`, `/themes/trending`, `/sources`            |

**Sync Strategy**: Last-write-wins using timestamps

- `last_internal_update_at` vs `last_external_update_at` determines direction
- Webhook handler for real-time Shortcut updates
- Sync metadata tracks status, errors, and direction

**Database Tables**:

```sql
stories              -- Canonical work items (system of record)
story_evidence       -- Evidence bundles (conversations, themes, excerpts)
story_comments       -- Comments with source tracking (internal/shortcut)
story_sync_metadata  -- Bidirectional sync state
label_registry       -- Shortcut taxonomy + internal labels
```

**Files**:

```
src/story_tracking/
├── models/
│   ├── story.py         # Story, StoryCreate, StoryUpdate
│   ├── evidence.py      # StoryEvidence, EvidenceExcerpt
│   ├── sync.py          # SyncMetadata, SyncResult
│   └── label.py         # LabelEntry, LabelCreate
└── services/
    ├── story_service.py
    ├── evidence_service.py
    ├── sync_service.py
    ├── label_registry_service.py
    ├── analytics_service.py
    ├── story_creation_service.py  # Canonical story creation with quality gates
    ├── orphan_service.py
    └── orphan_integration.py       # Unified orphan routing

src/api/routers/
├── stories.py           # Story CRUD + board
├── sync.py              # Shortcut sync endpoints
└── labels.py            # Label management

webapp/                  # Next.js frontend
├── src/app/
│   ├── page.tsx         # Board view
│   └── story/[id]/      # Story detail + edit
└── src/lib/
    └── types.ts         # StatusKey, STATUS_ORDER
```

---

### 15. Canonical Pipeline and Quality Gates (NEW - 2026-01-21)

**Purpose**: Single canonical path for conversation processing with quality gates ensuring story data quality.

**Canonical Pipeline Path**:

```
┌─────────────────────────────────────────────────────────────┐
│  src/two_stage_pipeline.py                                   │
│  - Fetch conversations from Intercom/Coda                   │
│  - Run Stage 1 + Stage 2 classification                     │
│  - Group by theme signature                                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  StoryCreationService.process_theme_groups()                 │
│  (src/story_tracking/services/story_creation_service.py)    │
│                                                             │
│  FOR EACH theme_group:                                      │
│    ┌─────────────────────────────────────────────────────┐  │
│    │ QUALITY GATES (run at top of processing loop)       │  │
│    │                                                     │  │
│    │ 1. EvidenceValidator.validate_samples()             │  │
│    │    - Check required fields (id, excerpt)            │  │
│    │    - Detect placeholder text                        │  │
│    │                                                     │  │
│    │ 2. ConfidenceScorer.score_groups()                  │  │
│    │    - Semantic similarity (30%)                      │  │
│    │    - Intent homogeneity (15%)                       │  │
│    │    - Symptom overlap (10%)                          │  │
│    │    - Product/component match                        │  │
│    └─────────────────────────────────────────────────────┘  │
│                      │                                      │
│          ┌───────────┴───────────┐                          │
│          ▼                       ▼                          │
│   PASSED GATES?          FAILED GATES?                      │
│          │                       │                          │
│          ▼                       ▼                          │
│   Create Story           Route to Orphans                   │
│   (confidence_score      (via OrphanIntegrationService)     │
│    persisted)                                               │
└─────────────────────────────────────────────────────────────┘
```

**Quality Gate Configuration**:

| Gate                | Threshold/Behavior                           | On Failure                  |
| ------------------- | -------------------------------------------- | --------------------------- |
| Evidence Validation | Required fields: `id`, `excerpt` (>20 chars) | Route to orphan integration |
| Confidence Scoring  | Minimum score: 50.0 (configurable)           | Route to orphan integration |
| Minimum Group Size  | >= 3 conversations                           | Route to orphan integration |

**QualityGateResult Type**:

```python
@dataclass
class QualityGateResult:
    signature: str
    passed: bool

    # Validation results
    evidence_quality: Optional[EvidenceQuality] = None
    validation_passed: bool = True

    # Scoring results
    scored_group: Optional[ScoredGroup] = None
    confidence_score: float = 0.0
    scoring_passed: bool = True

    # Failure details
    failure_reason: Optional[str] = None
```

**Decision Rationale** (from T-002):

- **Gates in StoryCreationService**: All callers benefit from quality checks
- **Block on failure**: Route to orphans (reversible), maintain data quality
- **Unified orphan path**: OrphanIntegrationService for consistent orphan handling

**Entry Points**:

| Entry Point    | Location                                      | Purpose                      |
| -------------- | --------------------------------------------- | ---------------------------- |
| CLI            | `python -m src.two_stage_pipeline`            | Direct pipeline execution    |
| API (UI)       | `POST /api/pipeline/run`                      | UI-triggered runs            |
| Story Creation | `StoryCreationService.process_theme_groups()` | Quality-gated story creation |

**Files**:

- `src/two_stage_pipeline.py` - Canonical pipeline entry point
- `src/story_tracking/services/story_creation_service.py` - Quality gates + story creation
- `src/confidence_scorer.py` - Group coherence scoring
- `src/evidence_validator.py` - Evidence quality validation
- `src/story_tracking/services/orphan_integration.py` - Unified orphan routing

---

### 16. Unified Research Search (NEW - 2026-01-13)

**Purpose**: Semantic search across Coda research and Intercom support data for evidence discovery and story enrichment.

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  Data Sources                                               │
│  - Coda Pages (AI Summaries, Research)                     │
│  - Coda Themes (Synthesized insights)                       │
│  - Intercom Support (Conversations)                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Source Adapters (src/research/adapters/)                   │
│  - CodaSearchAdapter (pages, themes)                        │
│  - IntercomSearchAdapter (conversations)                    │
│  - Abstract base with content hashing, snippet creation     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Embedding Pipeline (src/research/embedding_pipeline.py)    │
│  - OpenAI text-embedding-3-large (3072 dimensions)         │
│  - Batch embedding with content hash change detection       │
│  - pgvector storage with HNSW index                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Unified Search Service (src/research/unified_search.py)    │
│  - Semantic similarity search                               │
│  - "More like this" related content                         │
│  - Story evidence suggestions                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  API Layer (src/api/routers/research.py)                   │
│  - /api/research/search                                     │
│  - /api/research/similar/{source_type}/{source_id}         │
│  - /api/research/stories/{id}/suggested-evidence           │
└─────────────────────────────────────────────────────────────┘
```

**Key Features**:

- **Source Adapter Pattern**: Extensible design for adding new data sources
- **Content Hash Detection**: Only re-embed changed content (incremental updates)
- **HNSW Index**: Fast approximate nearest neighbor search
- **Evidence Suggestions**: Semantic matching for story enrichment
- **Graceful Degradation**: Search continues if embedding service unavailable

**Files**:

```
src/research/
├── __init__.py
├── models.py               # Pydantic models
├── unified_search.py       # Search service (474 lines)
├── embedding_pipeline.py   # Content ingestion (445 lines)
└── adapters/
    ├── base.py             # Abstract base (111 lines)
    ├── coda_adapter.py     # Coda adapter (274 lines)
    └── intercom_adapter.py # Intercom adapter (163 lines)

src/api/routers/research.py # API endpoints (301 lines)
config/research_search.yaml  # Configuration
tests/test_research.py       # 32 tests
webapp/src/app/research/     # Frontend search page
```

**Database**: `research_embeddings` table with pgvector extension

**Documentation**: `docs/search-rag-architecture.md`

---

### 17. Domain Classifier & Codebase Context (NEW - 2026-01-20)

**Purpose**: Map customer issues to relevant code areas using semantic classification and a curated domain knowledge map.

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  Customer Issue (issue_summary, product_area, symptoms)     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Domain Classifier (src/story_tracking/services/            │
│                     domain_classifier.py)                   │
│  - Stage 1: Fast keyword fallback (<50ms)                  │
│  - Stage 2: Claude Haiku 4.5 semantic classification       │
│  - Latency target: <500ms total                            │
│  - Cost: ~$0.00015 per classification                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Domain Knowledge Map (config/codebase_domain_map.yaml)    │
│  - 16 issue categories (scheduling, billing, auth, etc.)   │
│  - Keywords per category for fast matching                 │
│  - Repository mappings (aero, tack, webapp, etc.)          │
│  - Search paths per category                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Codebase Context Provider (src/story_tracking/services/    │
│                             codebase_context_provider.py)   │
│  - explore_with_classification() - Guided exploration       │
│  - Classification-prioritized search paths                  │
│  - File discovery with relevance scoring                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Output: ClassificationResult + ExplorationResult           │
│  - Category, confidence, reasoning                          │
│  - Suggested repos and search paths                         │
│  - Matched keywords and alternative categories              │
│  - Discovered files with relevance scores                  │
└─────────────────────────────────────────────────────────────┘
```

**Classification Categories** (16 total):

| Category            | Description                              |
| ------------------- | ---------------------------------------- |
| scheduling          | Pin scheduling, calendar issues          |
| billing             | Payments, subscriptions, plans           |
| auth                | Login, OAuth, account access             |
| ai_creation         | Ghostwriter, AI-generated content        |
| analytics           | Reports, metrics, insights               |
| media               | Images, videos, uploads                  |
| social_integrations | Pinterest, Instagram, TikTok connections |
| communities         | Groups, collaborative features           |
| notifications       | Alerts, emails, in-app messages          |
| performance         | Speed, timeouts, errors                  |
| mobile              | iOS/Android apps                         |
| browser_extension   | Chrome extension                         |
| team_collaboration  | Workspaces, permissions                  |
| api                 | Developer API, webhooks                  |
| onboarding          | Signup, trial, first-time experience     |
| bug_report          | General bugs (fallback)                  |

**Key Features**:

- **Two-Stage Classification**: Fast keyword fallback + semantic Haiku for accuracy
- **Domain-Specific Search**: Repositories and paths curated per category
- **Graceful Degradation**: Falls back to standard exploration on classification error
- **Test Coverage**: 37 tests (24 unit + 13 integration)

**Files**:

```
config/codebase_domain_map.yaml              # Domain knowledge map (602 lines)
src/story_tracking/services/
├── domain_classifier.py                     # Haiku classifier (335 lines)
└── codebase_context_provider.py             # Exploration service (967 lines)
tests/
├── test_domain_classifier.py                # 24 unit tests
└── test_domain_classifier_integration.py    # 13 integration tests
scripts/validate_domain_classifier.py        # Manual validation
```

**Current Status**:

- ✅ Classification working with 37 tests passing
- ⚠️ Not yet wired into story creation flow
- ⚠️ `ensure_repo_fresh` and `get_static_context` raise `NotImplementedError`

**Documentation**: `docs/analysis/codebase-search-vdd-limitations.md` (methodology analysis)

---

## Current Status

**Implemented**:
✅ Intercom integration with quality filtering
✅ Theme extraction with vocabulary guidance
✅ URL context boosting (v2.9)
✅ PostgreSQL database schema
✅ Theme canonicalization
✅ Validation framework
✅ Conversation type classification schema (all-support strategy)
✅ Two-stage classification system (Phase 1)
✅ Equivalence class system for grouping (100% accuracy)
✅ Phase 5 Ground Truth Validation (64.5% family accuracy)
✅ Vocabulary feedback loop for drift monitoring
✅ Story Grouping baseline (45% purity, validation pipeline)
✅ FastAPI + Streamlit frontend (25+ API endpoints, 3 UI pages)
✅ Coda research repository exploration (API access verified, content analyzed)
✅ Story Tracking Web App (Next.js) - Phases 1-2.5 complete
✅ Phase 3: Bidirectional Shortcut Sync (SyncService, LabelRegistryService)
✅ Phase 4: Analytics Enhancements (AnalyticsService, trending themes)
✅ Coda data integration (4,682 conversations, 1,919 themes loaded)
✅ Multi-source story creation (Intercom + Coda research)
✅ Unified Research Search with vector embeddings (pgvector + HNSW)

**In Progress**:
🚧 Production deployment
🚧 Monitoring and metrics

**Future**:
⏳ Webhook-driven real-time sync
⏳ Advanced analytics dashboard
⏳ Slack alerts for high-priority stories
⏳ Trend analysis and reporting
