<img width="1408" height="768" alt="Gemini_Generated_Image_la61xcla61xcla61" src="https://github.com/user-attachments/assets/18e19f80-b903-4401-9d9f-4a74ba5909c2" />

# FeedForward

FeedForward is an LLM-powered pipeline that analyzes Intercom support conversations to extract product insights and create implementation-ready stories.

Product teams are drowning in support conversations. Feature requests, bug reports, churn signals — they're buried in unstructured text and manual triage doesn't scale. FeedForward automates that analysis: it classifies conversations, extracts specific themes, scores grouping confidence, runs PM-style review, and produces stories ready for engineering sprint planning.

## Features

- **Two-stage classification** — fast routing classifier + refined analysis with full conversation context, both powered by gpt-4o-mini
- **Theme extraction** — 78-theme managed vocabulary with URL context boosting for product area disambiguation
- **Smart Digest** — full conversation text fed to LLM, producing diagnostic summaries and verbatim key excerpts
- **PM Review layer** — LLM-based coherence review that can keep, split, or reject theme groups before story creation
- **Quality gates** — evidence validation, confidence scoring, and 30-day recency requirements
- **Story tracking web app** — Next.js frontend with kanban board, story detail/edit, and pipeline controls
- **Bidirectional Shortcut sync** — push stories to Shortcut, pull updates back, webhook support
- **Semantic research search** — pgvector-backed similarity search across Coda research docs and Intercom conversations
- **Pipeline resilience** — checkpoint/resume for long backfills, streaming batch architecture with bounded memory
- **Discovery Engine** — AI-orchestrated 6-stage pipeline with 4 domain explorers for surfacing product opportunities beyond what the extraction pipeline captures

## Architecture

```
Intercom Conversations
        |
        v
+-------------------+     +--------------------+     +--------------------+
| Classification    | --> | Theme Extraction   | --> | Confidence Scoring |
| (2-stage routing) |     | (vocabulary-guided |     | (semantic + facet  |
|                   |     |  + Smart Digest)   |     |  similarity)       |
+-------------------+     +--------------------+     +--------------------+
                                                              |
                                                              v
                          +--------------------+     +--------------------+
                          | Story Creation     | <-- | PM Review          |
                          | (quality-gated,    |     | (keep / split /    |
                          |  evidence bundles) |     |  reject groups)    |
                          +--------------------+     +--------------------+
                                   |
                                   v
                          +--------------------+
                          | Stories + Orphans   |
                          | (Shortcut sync,     |
                          |  web app board)     |
                          +--------------------+
```

**Classification** routes conversations by type (product issue, how-to, feature request, billing, etc.) using a two-stage approach: Stage 1 classifies from the customer message alone for fast routing, Stage 2 re-analyzes with full support thread context for accuracy.

**Theme Extraction** identifies the specific issue — not just "product issue" but `pinterest_pin_scheduling_failure`. It uses a managed vocabulary of 78 themes, URL-based product area hints, and generates a diagnostic summary plus verbatim customer excerpts.

**Confidence Scoring** evaluates whether a group of conversations sharing a theme signature actually belong together, using semantic similarity, intent homogeneity, symptom overlap, and product/component matching.

**PM Review** asks an LLM "would these all go in the same sprint ticket?" and can split mixed groups into coherent sub-groups or reject incoherent ones entirely.

**Story Creation** applies quality gates (evidence validation, minimum group size of 3, 30-day recency), creates stories with evidence bundles, and routes failures to orphan accumulation for future graduation.

## Tech Stack

| Layer       | Technology                                          |
| ----------- | --------------------------------------------------- |
| Language    | Python 3.11                                         |
| API         | FastAPI                                             |
| Frontend    | Next.js (React, TypeScript, Tailwind CSS)           |
| LLM         | OpenAI gpt-4o-mini                                  |
| Database    | PostgreSQL + pgvector                               |
| Testing     | pytest (~2,500 tests across fast/medium/slow tiers) |
| Issue Sync  | Shortcut API (bidirectional)                        |
| Data Source | Intercom API + Coda research docs                   |

## Project Structure

```
FeedForward/
├── src/                        # Core pipeline code
│   ├── api/                    # FastAPI backend (25+ endpoints)
│   │   ├── main.py             # App entry point
│   │   ├── routers/            # Route handlers (health, pipeline, stories, themes, etc.)
│   │   └── schemas/            # Request/response models
│   ├── discovery/              # Discovery Engine (AI-orchestrated exploration)
│   │   ├── agents/             # Domain explorers + synthesis agents
│   │   ├── orchestrator.py     # Pipeline orchestration
│   │   └── models/             # Stage artifact contracts
│   ├── story_tracking/         # Story management layer
│   │   ├── services/           # Story, evidence, sync, orphan services
│   │   └── models/             # Story, evidence, sync models
│   ├── research/               # Semantic search (pgvector)
│   ├── classifier_stage1.py    # Fast routing classifier
│   ├── classifier_stage2.py    # Refined analysis classifier
│   ├── theme_extractor.py      # LLM theme extraction + Smart Digest
│   ├── intercom_client.py      # Intercom API integration
│   └── ...
├── webapp/                     # Next.js frontend
│   └── src/
│       ├── app/                # Pages (board, story detail, pipeline, research, analytics)
│       ├── components/         # UI components
│       └── lib/                # Types, utilities
├── tests/                      # pytest test suite
├── config/                     # Theme vocabulary, domain maps, search config
├── docs/                       # Architecture, status, changelog, runbooks
├── scripts/                    # Pipeline runner, diagnostics, validation
└── migrations/                 # SQL schema migrations
```

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ with the [pgvector](https://github.com/pgvector/pgvector) extension
- Node.js 18+
- API keys: `INTERCOM_ACCESS_TOKEN`, `OPENAI_API_KEY`

### Installation

```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd webapp && npm install && cd ..
```

### Environment Setup

```bash
cp .env.example .env
# Fill in required values:
#   DATABASE_URL        — PostgreSQL connection string
#   OPENAI_API_KEY      — OpenAI API key
#   INTERCOM_ACCESS_TOKEN — Intercom API token
#
# Optional:
#   SHORTCUT_API_TOKEN  — for bidirectional Shortcut sync
#   CODA_API_KEY        — for Coda research integration
```

### Running

Start the API server and frontend in separate terminals:

```bash
# Terminal 1: API
uvicorn src.api.main:app --reload --port 8000

# Terminal 2: Frontend
cd webapp && npm run dev
```

Then open [http://localhost:3000](http://localhost:3000). API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

## Pipeline Usage

The full pipeline (classification, theme extraction, story creation) runs through the API:

```bash
# Dev mode — handles pre-flight checks, cleanup, and monitoring
./scripts/dev-pipeline-run.sh
./scripts/dev-pipeline-run.sh --days 7        # Process 7 days
./scripts/dev-pipeline-run.sh --skip-cleanup  # Skip stale data cleanup
```

Classification can also be run standalone:

```bash
python -m src.classification_pipeline --days 7              # Last 7 days
python -m src.classification_pipeline --days 1 --max 10     # Small test batch
python -m src.classification_pipeline --dry-run             # No DB writes
python -m src.classification_pipeline --async --concurrency 20  # Parallel mode
```

CLI tools for inspecting results:

```bash
python src/cli.py themes           # List all themes
python src/cli.py trending         # Trending themes (2+ in 7 days)
python src/cli.py pending          # Preview pending tickets
```

## Testing

The test suite uses tiered pytest markers for faster iteration:

```bash
pytest -m "fast"               # ~1,726 pure unit tests (quick gate)
pytest -m "fast" -n auto       # Same, parallelized with xdist
pytest -m "fast or medium"     # ~2,200 tests (pre-merge requirement)
pytest tests/ -v               # ~2,492 tests (full suite, includes slow integration)
```

## Discovery Engine

Beyond the extraction pipeline, FeedForward includes a Discovery Engine — an AI-orchestrated system that proactively surfaces product opportunities humans might miss.

It runs as a 6-stage pipeline:

1. **Exploration** — 4 domain explorers (Customer Voice, Codebase, Analytics, Research) independently scan data sources
2. **Opportunity Framing** — PM agent synthesizes explorer findings into problem-focused briefs
3. **Solution + Validation** — iterative design loop: PM drafts solutions, validation agent stress-tests, experience agent evaluates UX
4. **Feasibility + Risk** — technical scoping with risk assessment
5. **Prioritization** — TPM-style ranking across opportunity set
6. **Human Review** — final checkpoint before execution

Phase 1 infrastructure is complete with 600+ discovery-specific tests and an orchestrator accessible via `POST /api/discovery/runs`.

See [docs/status.md](docs/status.md) for the latest on discovery engine progress.

## Documentation

| Document                                     | Purpose                              |
| -------------------------------------------- | ------------------------------------ |
| [PLAN.md](PLAN.md)                           | Full project spec and methodology    |
| [docs/architecture.md](docs/architecture.md) | System design and component details  |
| [docs/status.md](docs/status.md)             | Current progress and recent changes  |
| [docs/changelog.md](docs/changelog.md)       | What has shipped                     |
| [CLAUDE.md](CLAUDE.md)                       | Development conventions and CI gates |
