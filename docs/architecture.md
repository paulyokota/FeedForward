# Architecture

## Overview

FeedForward is an LLM-powered pipeline for analyzing Intercom conversations and extracting product insights.

**Current Phase**:

- Phase 1 (Two-Stage Classification): ✅ Complete
- Phase 4 (Theme Extraction & Aggregation): ✅ Complete
- Story Grouping Architecture: 🚧 In Progress (baseline established)

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
│  - Extract source.url            │ ← NEW: URL context
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│   Theme Extraction (LLM)         │
│  - Vocabulary-guided matching    │
│  - URL context boosting          │ ← NEW: Product area disambiguation
│  - Signature canonicalization    │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│      Database (PostgreSQL)       │
│  - Conversations                 │
│  - Themes (aggregated)           │
│  - Theme embeddings              │
└──────┬───────────────────────────┘
       │
       ▼
┌──────────────────────────────────┐
│  Escalation & Routing (Future)   │
│  - Auto-ticket creation          │
│  - Team assignments              │
│  - Slack alerts                  │
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
- `src/resolution_analyzer.py` - Detects support actions
- `src/knowledge_extractor.py` - Extracts insights per conversation
- `src/knowledge_aggregator.py` - Aggregates knowledge across conversations

**Status**: Production ready, 100% high confidence, awaiting database integration

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

### 9. Story Grouping Pipeline (NEW - 2026-01-08)

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

**In Progress**:
🚧 Story Grouping Pipeline

- ⏳ Improve scheduler symptom extraction (precision from 35.6% → 50%+)
- ⏳ Add error code extraction for disambiguation
- ⏳ Target 70%+ group purity
- ⏳ Implement orphan persistence (accumulate over time)

🚧 Production deployment
🚧 Monitoring and metrics

**Future**:
⏳ Escalation rules engine
⏳ Auto-ticket creation (Shortcut integration)
⏳ Slack alerts
⏳ Trend analysis and reporting
