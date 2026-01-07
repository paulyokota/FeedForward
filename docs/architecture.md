# Architecture

## Overview

FeedForward is an LLM-powered pipeline for analyzing Intercom conversations and extracting product insights.

**Current Phase**: Theme Extraction & Aggregation (Phase 4)

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

### 6. Conversation Type Classification (NEW)

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

**In Progress**:
🚧 Expanding theme vocabulary

- ⏳ Billing themes (7% of conversations - critical gap)
- ⏳ Account/auth themes (20% of conversations)
- ⏳ Onboarding/setup themes
  🚧 Production deployment
  🚧 Monitoring and metrics

**Future**:
⏳ Escalation rules engine
⏳ Auto-ticket creation (Shortcut integration)
⏳ Slack alerts
⏳ Trend analysis and reporting
