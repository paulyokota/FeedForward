# FeedForward Project Index

> **Purpose**: Token-efficient overview of repository structure for rapid context during development. Last generated: 2026-01-23.

**Repository**: FeedForward - LLM-powered Intercom conversation analysis pipeline

---

## Executive Summary

FeedForward is a Python/FastAPI backend + Next.js frontend system that extracts product insights from Intercom support conversations. The pipeline classifies conversations, extracts themes, groups them by implementation strategy, and creates actionable Shortcut tickets.

| Metric             | Value                                                                                                            |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- |
| **Framework**      | FastAPI (Python 3.11) + Next.js                                                                                  |
| **Language**       | 92% Python, 8% TypeScript/JavaScript                                                                             |
| **Core LLM**       | OpenAI gpt-4o-mini                                                                                               |
| **Database**       | PostgreSQL (migrations in `migrations/`)                                                                         |
| **Code Files**     | 220 Python modules, ~30K LOC                                                                                     |
| **Test Framework** | pytest (18+ test files)                                                                                          |
| **Key Commands**   | `pytest -m "not slow"`, `uvicorn src.api.main:app --reload --port 8000`, `python -m src.two_stage_pipeline --days 7` |

---

## Directory Structure

```
FeedForward/
├── src/                          # Core pipeline (30K LOC, 220 modules)
│   ├── api/                      # FastAPI REST endpoints (8 routers)
│   │   ├── main.py              # App initialization, startup cleanup
│   │   ├── routers/             # Route handlers
│   │   │   ├── pipeline.py      # Pipeline control (run, status, trigger)
│   │   │   ├── themes.py        # Theme queries and analytics
│   │   │   ├── stories.py       # Story retrieval and grouping
│   │   │   ├── analytics.py     # Metrics and pipeline stats
│   │   │   ├── sync.py          # Shortcut/Intercom sync
│   │   │   ├── research.py      # Knowledge base search
│   │   │   ├── labels.py        # Theme labels management
│   │   │   └── health.py        # Health check endpoint
│   │   ├── schemas/             # Request/response schemas
│   │   │   ├── pipeline.py      # Pipeline schemas
│   │   │   ├── themes.py        # Theme schemas
│   │   │   └── analytics.py     # Analytics schemas
│   │   └── deps.py              # FastAPI dependencies
│   │
│   ├── db/                       # Database layer (6 modules)
│   │   ├── connection.py        # PostgreSQL connection pooling
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   ├── schema.sql           # Database schema definition
│   │   ├── classification_storage.py  # Conversation storage
│   │   ├── embedding_storage.py      # Embedding vectors
│   │   └── facet_storage.py         # Facet aggregation
│   │
│   ├── services/                 # Core business logic (4 modules)
│   │   ├── embedding_service.py      # OpenAI embedding generation
│   │   ├── facet_service.py         # Facet extraction for clustering
│   │   ├── hybrid_clustering_service.py  # Hybrid clustering algorithm
│   │   └── repo_sync_service.py      # Bidirectional Shortcut sync
│   │
│   ├── adapters/                 # External integrations (3 modules)
│   │   ├── base.py              # Adapter interface
│   │   ├── intercom_adapter.py   # Intercom API wrapper
│   │   └── coda_adapter.py       # Coda knowledge base integration
│   │
│   ├── research/                 # RAG and search (4 modules)
│   │   ├── models.py            # Research data models
│   │   ├── embedding_pipeline.py # Embedding for search
│   │   ├── unified_search.py     # Multi-source search
│   │   └── adapters/            # Research data adapters
│   │
│   ├── classification_manager.py # Stage 1/2 classification coordination
│   ├── classifier_stage1.py     # Initial issue categorization (8 categories)
│   ├── classifier_stage2.py     # Detailed classification
│   ├── confidence_scorer.py     # Grouping confidence metrics
│   ├── evidence_validator.py    # LLM evidence validation
│   ├── equivalence.py           # Theme equivalence logic
│   ├── escalation.py            # Escalation handling
│   ├── help_article_extractor.py # Knowledge extraction
│   ├── intercom_client.py       # Intercom API client (28K LOC)
│   ├── knowledge_aggregator.py  # Knowledge base aggregation
│   ├── knowledge_extractor.py   # Fact extraction from conversations
│   ├── orphan_matcher.py        # Unmatched conversation grouping
│   ├── resolution_analyzer.py   # Resolution pattern analysis
│   ├── shortcut_client.py       # Shortcut API client
│   ├── shortcut_story_extractor.py # Story extraction
│   ├── signature_utils.py       # Theme signature utilities
│   ├── slack_client.py          # Slack notification client
│   ├── story_formatter.py       # Story creation (38K LOC)
│   ├── theme_extractor.py       # Theme extraction (38K LOC)
│   ├── theme_quality.py         # Theme validation
│   ├── theme_tracker.py         # Theme storage and tracking (46K LOC)
│   ├── two_stage_pipeline.py    # Main pipeline orchestration (35K LOC)
│   ├── vocabulary.py            # Theme vocabulary management
│   ├── vocabulary_feedback.py   # Vocabulary improvement
│   ├── cli.py                   # CLI commands
│   └── coda_client.py           # Coda API client
│
├── tests/                        # Test suite (18 files, pytest)
│   ├── conftest.py              # Shared fixtures
│   ├── test_pipeline.py         # Pipeline integration tests
│   ├── test_hybrid_clustering_service.py
│   ├── test_hybrid_story_creation.py
│   ├── test_facet_service.py
│   ├── test_orphan_matcher.py
│   ├── test_orphan_service.py
│   ├── test_sync_router.py
│   ├── test_sync_service.py
│   ├── test_theme_extractor_specificity.py
│   ├── test_codebase_security.py
│   ├── test_help_article_extraction.py
│   ├── test_startup_cleanup.py
│   ├── test_dual_story_formatter.py
│   ├── test_run_scoping.py
│   └── test_pipeline_integration_insights.py
│
├── webapp/                       # Next.js frontend (TypeScript)
│   ├── app/                      # Next.js app directory
│   │   └── api/                  # Backend proxy routes
│   └── components/               # React components
│
├── config/                       # Configuration & vocabularies
│   ├── theme_vocabulary.json    # 78-theme vocabulary with context mapping
│   ├── resolution_patterns.json # Resolution analysis patterns
│   ├── research_search.yaml     # RAG search configuration
│   └── codebase_domain_map.yaml # Domain classification map
│
├── docs/                         # Comprehensive documentation (40+ files)
│   ├── PLAN.md                  # Project specification & VDD methodology
│   ├── architecture.md          # System design & data flow
│   ├── status.md                # Current progress & recent milestones
│   ├── changelog.md             # What's shipped
│   │
│   ├── Process Playbooks/
│   │   ├── process-playbook/gates/          # Process enforcement
│   │   │   ├── test-gate.md                 # Tests required before review
│   │   │   ├── learning-loop.md             # Dev fixes own issues
│   │   │   ├── functional-testing-gate.md   # Pipeline/LLM validation
│   │   │   ├── context-loading-gate.md      # Context deployment rules
│   │   │   └── backlog-hygiene.md           # Issue filing protocol
│   │   ├── process-playbook/review/
│   │   │   ├── five-personality-review.md   # Review protocol (5 agents, 2+ rounds)
│   │   │   └── reviewer-profiles.md         # Review personality specs
│   │   └── process-playbook/agents/
│   │       └── coordination-patterns.md     # Multi-agent workflows
│   │
│   ├── Architecture Documentation/
│   │   ├── story-grouping-architecture.md   # Story grouping design
│   │   ├── story-granularity-standard.md    # INVEST-based criteria
│   │   ├── theme-quality-architecture.md    # Theme specificity validation
│   │   ├── two-stage-classification-system.md
│   │   ├── search-rag-architecture.md       # Knowledge base search
│   │   └── story-tracking-web-app-architecture.md
│   │
│   ├── Reference Documentation/
│   │   ├── acceptance-criteria.md          # Phase validation criteria
│   │   ├── escalation-rules.md             # Escalation logic
│   │   ├── tailwind-codebase-map.md        # URL → Service routing
│   │   └── intercom-schema-analysis.md     # Intercom data structure
│
├── prompts/                      # Prompt templates (system prompts)
│   ├── classification/           # Stage 1/2 classification prompts
│   ├── extraction/               # Theme extraction prompts
│   └── grouping/                 # Story grouping prompts
│
├── data/                         # Training & sample data (70+ files)
│   ├── samples/                  # Intercom conversation samples
│   ├── historical_samples/       # Time-series training data
│   ├── conversation_types/       # Classification training sets
│   ├── phase1_results/           # Phase 1 baseline results
│   ├── classifier_data/          # Train/test splits
│   ├── shortcut_*.json           # Shortcut story mappings
│   ├── theme_fixtures.json       # Theme reference data
│   ├── training_data_summary.json
│   └── backfill_*.json           # Historical data imports
│
├── migrations/                   # Database migrations (18 files)
│   └── Version control via timestamps
│
├── .claude/                      # Claude Code configuration
│   ├── agents/                   # Custom agents
│   │   ├── prompt-tester.md      # Classification prompt testing
│   │   ├── schema-validator.md   # Schema validation
│   │   └── escalation-validator.md
│   ├── skills/                   # Skill implementations
│   │   ├── marcus-backend/       # Backend development skill
│   │   ├── sophia-frontend/      # Frontend development skill
│   │   ├── kai-prompt-engineering/  # Prompt optimization skill
│   │   ├── kenji-testing/        # Testing skill
│   │   ├── priya-architecture/   # Architecture skill
│   │   └── theo-documentation/   # Documentation skill
│   ├── commands/                 # Custom commands
│   │   ├── prompt-iteration.md
│   │   ├── session-end.md
│   │   └── update-docs.md
│   └── reviews/                  # PR review archives
│
├── context/                      # Product context
│   └── product/
│       ├── tailwind-taxonomy.md  # Product feature taxonomy
│       └── support-knowledge.md  # Support knowledge base
│
├── reference/                    # Research & methodology
│   ├── UAT-Agentic-Coding-Research.md  # VDD research paper
│   ├── intercom-llm-guide.md            # Intercom integration guide
│   └── setup.md                         # Project setup procedures
│
├── CLAUDE.md                     # Project context & process gates
├── PLAN.md                       # Full project specification (43K)
├── package.json                  # Node.js dependencies (openai, playwright)
├── requirements.txt              # Python dependencies
├── pyproject.toml               # Python project metadata (if present)
└── .env.example                 # Environment variable template
```

---

## Key Entry Points

### API Endpoints (FastAPI - `src/api/main.py`)

**Base URL**: `http://localhost:8000` (dev) or deployed instance

**Pipeline Control**:

- `POST /api/pipeline/run` - Start new pipeline run
- `GET /api/pipeline/runs` - List pipeline runs
- `GET /api/pipeline/runs/{run_id}` - Get run status
- `POST /api/pipeline/{run_id}/stop` - Stop running pipeline

**Analysis Results**:

- `GET /api/themes` - List themes with frequencies
- `GET /api/themes/trending` - Top themes
- `GET /api/stories` - List created stories
- `GET /api/stories/{story_id}` - Story detail with conversations

**Sync & Integration**:

- `POST /api/sync/to-shortcut` - Sync stories to Shortcut
- `GET /api/sync/status` - Sync status

**Search & Analytics**:

- `POST /api/research/search` - Multi-source search
- `GET /api/analytics/classification` - Classification metrics
- `GET /api/analytics/theme-distribution` - Theme statistics

**Health**:

- `GET /health` - Health check

### CLI Commands (`src/cli.py`)

```bash
python src/cli.py themes              # List all themes with counts
python src/cli.py trending            # Top 10 themes
python src/cli.py pending             # Preview pending stories
```

### Pipeline Orchestration (`src/two_stage_pipeline.py`)

**Main entry point** for automated runs:

```bash
# Last 7 days of conversations
python -m src.two_stage_pipeline --days 7

# Test with 10 conversations
python -m src.two_stage_pipeline --days 1 --max 10

# Dry run (no database writes)
python -m src.two_stage_pipeline --dry-run

# Async mode with concurrency
python -m src.two_stage_pipeline --async --concurrency 20
```

**Pipeline Phases** (in order):

1. **Classification** (`classifier_stage1.py` + `classifier_stage2.py`) - Route conversations to 8 categories
2. **Filtering** - Remove spam and low-quality conversations
3. **Embedding Generation** (`embedding_service.py`) - OpenAI embeddings
4. **Facet Extraction** (`facet_service.py`) - Action type + direction
5. **Theme Extraction** (`theme_extractor.py`) - Extract from 78-theme vocabulary
6. **Hybrid Clustering** (`hybrid_clustering_service.py`) - Group by semantic similarity
7. **PM Review** (`story_formatter.py`) - Human validation with LLM support
8. **Story Creation** (`shortcut_client.py`) - Create Shortcut tickets

### Web App (`webapp/`)

**Running the full stack**:

```bash
# Terminal 1: Backend API
uvicorn src.api.main:app --reload --port 8000

# Terminal 2: Frontend
cd webapp && npm run dev

# Access at http://localhost:3000
```

---

## Core Modules & Responsibilities

### Classification (`src/classifier_*.py`)

**Two-stage routing system**:

- **Stage 1** (`classifier_stage1.py`): Broad categorization into 8 types
  - `billing_question`, `product_feature_request`, `product_issue`, `payment_issue`
  - `technical_integration_issue`, `mobile_app_issue`, `account_management`, `other`
- **Stage 2** (`classifier_stage2.py`): Detailed classification within categories

**Confidence scoring** (`confidence_scorer.py`):

- Semantic similarity (30%)
- Intent homogeneity (15%)
- Symptom overlap (10%)
- Product/component match (rest)

### Theme Extraction (`src/theme_extractor.py` - 38K LOC)

**Core responsibility**: Extract specific, actionable themes from conversations

**Key features**:

- 78-theme vocabulary (config/theme_vocabulary.json)
- URL context boosting for product area disambiguation
- SAME_FIX test for signature specificity
- Confidence scoring per extraction

**Vocabulary mapping** (URL patterns):

- Pinterest features: Analytics, Next Publisher, Legacy Publisher, Create, etc.
- Cross-platform: Multi-Network scheduler, Communities, Billing & Settings
- Labs: GW Labs (Ghostwriter), CoPilot, Made For You

### Story Grouping (`src/story_formatter.py` - 38K LOC)

**Three grouping strategies**:

1. **Signature-based**: Group conversations with identical theme signatures
2. **Hybrid clustering**: Semantic grouping with facet-based separation
3. **Orphan matching**: Catch unmatched conversations via semantic search

**PM Review Layer** (`story_formatter.py`):

- LLM evaluates theme groups for coherence
- Decisions: `keep_together`, `split`, `reject`
- Minimum 3 conversations per story (INVEST criteria)

### Database Layer (`src/db/`)

**Models**:

- `conversations` - Raw Intercom data
- `classifications` - Stage 1/2 routing
- `themes` - Extracted themes per conversation
- `embeddings` - Vector embeddings for clustering
- `facets` - Semantic facets (action_type, direction)
- `stories` - Grouped and validated stories
- `pipeline_runs` - Execution tracking

**Storage modules**:

- `classification_storage.py` - Conversation lifecycle
- `embedding_storage.py` - Vector storage
- `facet_storage.py` - Facet aggregation

### Services (`src/services/`)

| Service                        | Purpose                                               |
| ------------------------------ | ----------------------------------------------------- |
| `embedding_service.py`         | OpenAI embedding generation + caching                 |
| `facet_service.py`             | Semantic facet extraction (action_type, direction)    |
| `hybrid_clustering_service.py` | Clustering algorithm (similarity + facet constraints) |
| `repo_sync_service.py`         | Bidirectional Shortcut ↔ FeedForward sync             |

### External Integrations

| Client               | Purpose                  | Key Methods                                |
| -------------------- | ------------------------ | ------------------------------------------ |
| `intercom_client.py` | Intercom API (28K LOC)   | fetch_conversations(), get_help_articles() |
| `shortcut_client.py` | Shortcut story creation  | create_story(), link_conversations()       |
| `slack_client.py`    | Escalation notifications | post_message()                             |
| `coda_client.py`     | Knowledge base sync      | query_docs()                               |

---

## Configuration & Vocabularies

### Theme Vocabulary (`config/theme_vocabulary.json`)

**Structure**:

- 78 discrete themes (action signatures)
- URL context mapping for product area disambiguation
- Signature quality guidelines (SAME_FIX test criteria)
- Version tracking (currently v2.15)

**Example themes**:

- `pinterest_pin_failure` - Pin creation failures
- `scheduler_publish_timeout` - Scheduling timeouts
- `account_permission_issue` - Permission-based blockers

### Resolution Patterns (`config/resolution_patterns.json`)

- Resolution detection heuristics
- Self-service opportunity identification

---

## Dependencies

### Python (`requirements.txt`)

**Core**:

- `fastapi>=0.109.0` - Web framework
- `uvicorn[standard]>=0.27.0` - ASGI server
- `openai>=1.0.0` - LLM API client
- `anthropic>=0.18.0` - Backup LLM
- `psycopg2-binary>=2.9.0` - PostgreSQL driver
- `pydantic>=2.0.0` - Data validation
- `requests>=2.31.0` - HTTP client

**Testing**:

- `pytest>=7.0.0` - Test framework
- `python-dotenv>=1.0.0` - Environment config

### Node.js (`package.json`)

**Direct**:

- `openai@^6.16.0` - OpenAI SDK (Node.js)
- `playwright@^1.57.0` - Browser automation
- `playwright-core@^1.57.0` - Playwright engine

**Dev**:

- `tailwindcss@^4.1.18` - CSS framework
- `@tailwindcss/postcss@^4.1.18` - Tailwind PostCSS

---

## Recent Changes & Active Areas

**Latest Milestone** (2026-01-22): Hybrid Clustering Bug Fixes - Pipeline end-to-end working

| Area                     | Status | Last Changed         |
| ------------------------ | ------ | -------------------- |
| Hybrid clustering        | FIXED  | 2026-01-22 (d88624d) |
| PM review integration    | ACTIVE | 2026-01-21           |
| Theme quality validation | ACTIVE | 2026-01-21           |
| Classification pipeline  | STABLE | 2026-01-22           |
| Database schema          | STABLE | 2026-01-22           |
| Embedding/facet services | ACTIVE | 2026-01-22           |
| Shortcut sync            | STABLE | 2026-01-10           |

**High-churn files** (frequent modifications):

- `two_stage_pipeline.py` - Main orchestration
- `theme_extractor.py` - Theme extraction logic
- `story_formatter.py` - Story creation & grouping
- `theme_tracker.py` - Theme storage
- `intercom_client.py` - Intercom integration

---

## Testing Strategy

### Test Execution

```bash
# Fast tier only (quick feedback)
pytest

# Pre-merge (fast + medium tiers)
pytest -m "not slow"

# Full suite (all tiers)
pytest --override-ini="addopts=" -v

# Run specific test
pytest tests/test_pipeline.py -v

# Run with coverage
pytest --override-ini="addopts=" --cov=src
```

### Test Files by Domain

| Test File                                      | Purpose                  | Coverage                 |
| ---------------------------------------------- | ------------------------ | ------------------------ |
| `test_pipeline.py`                             | E2E pipeline integration | Classification → Stories |
| `test_hybrid_clustering_service.py`            | Clustering algorithm     | Similarity + facets      |
| `test_facet_service.py`                        | Facet extraction         | Action type, direction   |
| `test_theme_extractor_specificity.py`          | SAME_FIX validation      | Signature quality        |
| `test_orphan_matcher.py`                       | Orphan grouping          | Semantic matching        |
| `test_hybrid_story_creation.py`                | Story creation flow      | Grouping + validation    |
| `test_sync_router.py` + `test_sync_service.py` | Shortcut sync            | Bidirectional sync       |
| `test_codebase_security.py`                    | Security linting         | Code quality             |

---

## Development Workflow

### Process Gates (From `CLAUDE.md`)

**Critical Path Checklist** (Every PR):

1. Tests exist and pass (`pytest -m "not slow"` for pre-merge, full suite with `pytest --override-ini="addopts=" -v`)
2. Build passes
3. Pipeline PRs include functional test evidence
4. Review converged (5-personality, 2+ rounds)
5. Dev fixes own code (Learning Loop gate)
6. CONVERGED comment posted before merge

**Key Gates**:

- **Test Gate**: Tests required before review (no exceptions)
- **Learning Loop**: Original dev fixes their review issues
- **5-Personality Review**: 2+ rounds with 5 separate review agents
- **Functional Testing**: Evidence required for pipeline/LLM changes
- **Backlog Hygiene**: Issues filed before session ends

### Review Protocol

**5-Personality Review** (5 separate agents, minimum 2 rounds):

| Agent    | Focus                     | Location                              |
| -------- | ------------------------- | ------------------------------------- |
| Reginald | Correctness, performance  | `.claude/skills/review-5personality/` |
| Sanjay   | Security, validation      |                                       |
| Quinn    | Output quality, coherence |                                       |
| Dmitri   | Simplicity, YAGNI         |                                       |
| Maya     | Clarity, maintainability  |                                       |

Full protocol: `docs/process-playbook/review/five-personality-review.md`

### Skill Deployment

**Development Skills** (from `.claude/skills/`):

| Skill                    | Owner  | Domain                        |
| ------------------------ | ------ | ----------------------------- |
| `marcus-backend`         | Marcus | `src/`, database, API         |
| `sophia-frontend`        | Sophia | `webapp/`, UI                 |
| `kai-prompt-engineering` | Kai    | Prompts, classification       |
| `kenji-testing`          | Kenji  | Tests, edge cases             |
| `priya-architecture`     | Priya  | Design, conflict resolution   |
| `theo-documentation`     | Theo   | Post-merge docs & reflections |

---

## Documentation Index

**Essential Reading Order**:

1. **PLAN.md** - Full project specification & VDD methodology (43K)
2. **CLAUDE.md** - Process gates & skill deployment (14K)
3. **docs/architecture.md** - System design & pipeline flow
4. **docs/status.md** - Current progress & milestones
5. **docs/story-grouping-architecture.md** - Story creation design
6. **docs/theme-quality-architecture.md** - Theme validation approach

**Process Documentation**:

- `docs/process-playbook/gates/` - Enforcement procedures
- `docs/process-playbook/review/five-personality-review.md` - Review protocol
- `docs/process-playbook/agents/coordination-patterns.md` - Multi-agent workflows

**Reference**:

- `reference/UAT-Agentic-Coding-Research.md` - VDD research & methodology
- `reference/intercom-llm-guide.md` - Intercom implementation guide
- `docs/tailwind-codebase-map.md` - URL → Service mapping

---

## Quick Stats

| Metric               | Value                   |
| -------------------- | ----------------------- |
| Python files         | 220                     |
| Python LOC           | ~30,000                 |
| API routes           | 19                      |
| Database tables      | 8                       |
| Theme vocabulary     | 78 themes               |
| Test files           | 18                      |
| Documentation files  | 40+                     |
| Database migrations  | 18                      |
| Git commits (recent) | ~200+ since milestone 8 |

---

## Token Savings

This index represents:

- **Full codebase analysis**: ~2,500 files across 27 directories
- **Documentation**: 40+ MD files (60K+ lines)
- **Compressed reference**: ~4,000 words vs. 200K+ full repository content
- **Estimated savings**: 85-90% token reduction for context-aware development

Use this index to jump to specific modules without reading full files during development.
