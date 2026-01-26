# Changelog

All notable changes to FeedForward will be documented in this file.

Format: [ISO Date] - Summary of changes

---

## [Unreleased]

### Added

**Raw Component Preservation for Drift Detection (2026-01-23)**:

- New columns in `themes` table: `component_raw`, `product_area_raw`, `component_raw_inferred`
- Migration 016 (`016_add_raw_component_columns.sql`) adds columns and composite index
- Preserves original LLM output before normalization for audit and drift analysis
- `component_raw_inferred` flag distinguishes true LLM output from backfilled data
- Composite index `idx_themes_component_drift` supports queries finding multiple raw variants mapping to same canonical

**Pipeline Run Diagnostic Script (2026-01-26)**:

- New `scripts/diagnose_run.py` for investigating pipeline run results
- Checks data counts, embedding/facet overlap, cluster size distribution
- Runs hybrid clustering test to verify algorithm behavior
- Analyzes orphan signatures by type (hybrid vs legacy)
- Usage: `PYTHONPATH=. python scripts/diagnose_run.py <run_id>`

**Component Normalization and Canonicalization (2026-01-23)**:

- New `src/utils/normalize.py` module for consistent data formatting
- Two-level normalization: format (spaces/hyphens → underscores) + semantic (alias mapping)
- `COMPONENT_ALIASES` dict for known equivalent variants (e.g., "smartschedule" → "smart_schedule")
- `canonicalize_component()` used for grouping keys, raw values preserved separately
- Prevents fragmentation from LLM output inconsistency

**Stable Semantic Signatures for Hybrid Clusters (2026-01-23)**:

- `_compute_stable_hybrid_signature()` in `story_creation_service.py`
- Format: `hybrid_{action_type}_{direction}_{product_area}_{component}_{issue_part}`
- Enables cross-run orphan accumulation (replaces run-local `emb_X_facet_Y_Z` format)
- Deterministic signature from semantic content, not cluster IDs

### Changed

**Dev-Mode Pipeline Runner Improvements (2026-01-23-26)**:

- Auto-cleanup now includes embeddings and facets tables (not just themes/stories/orphans)
- Auto-restart server when code is stale (compares git commit time vs server start time)
- Added component drift detection after successful runs
- Shows raw variants mapping to same canonical for alias review

### Fixed

**Raw LLM Output Preservation (2026-01-23)** - Commit 76bd915:

- Theme extraction now preserves `component_raw` and `product_area_raw` before normalization
- Fixes loss of original LLM output that was being overwritten by normalized values
- Enables drift detection: find cases where LLM produces different raw values for same concept

---

### Added

**StructuredDescription Component (2026-01-22)** - PR #102:

- New `webapp/src/components/StructuredDescription.tsx` for rendering LLM-generated story descriptions
- Parses both `## Header` and `**Bold**` markdown formats into structured sections
- Progressive disclosure: Expand/collapse for sections exceeding 5 lines
- Checkbox rendering for acceptance criteria (`- [ ]` unchecked, `- [x]` checked with strikethrough)
- Structured/Raw view toggle for switching between parsed and original content
- Copy button with success/error feedback states
- Known section headers: Summary, Impact, Evidence, User Story, Acceptance Criteria, Symptoms, Technical Notes, INVEST Check
- Falls back to raw view when no known sections detected
- Test coverage: `webapp/src/components/__tests__/StructuredDescription.test.tsx`

**Session-Scoped Signature Canonicalization (2026-01-22)**:

- Track signatures created during extraction session in `_session_signatures` dict
- `get_existing_signatures()` now includes session signatures for within-batch matching
- Canonicalization runs for both vocabulary and non-vocabulary extraction modes
- Prevents signature fragmentation (e.g., `analytics_stats_bug` vs `analytics_counter_bug` for same issue)
- Result: Run 39 orphans dropped from 87 to 40 with this change

### Fixed

**Critical Hybrid Clustering Bugs (2026-01-22)** - Commit d88624d:

- **Conversations stuck on first run**: Removed `COALESCE(pipeline_run_id)` wrapper that prevented re-classification
  - Root cause: Conversations stayed linked to first run (e.g., run 45), so runs 46-50 had 0 linked conversations
  - Impact: Embedding/facet/theme phases found nothing (query by `pipeline_run_id = current_run`)
  - Fix: Update `pipeline_run_id` to current run on re-classification in `classification_storage.py`
- **Hybrid clustering never ran**: Fixed wrong method call `cluster_conversations()` → `cluster_for_run()`
  - Root cause: Method doesn't exist, silent failure via try/except, fell back to signature grouping
  - Fix: Call correct method name in `pipeline.py` line 851
- **PM review disabled for hybrid clusters**: Removed `and not hybrid_clustering_enabled` gate
  - Root cause: Line 770 disabled PM review when hybrid clustering enabled
  - Impact: Run 54 grouped 5 unrelated bugs in one story (images, credits, billing, scheduler)
  - Fix: Enable PM review for both signature and hybrid clustering paths
- **Classification hangs and crashes**: Added 30s timeout + exception handling
  - Root cause: No timeout on OpenAI API calls → infinite hang (run 48)
  - Root cause: No `return_exceptions=True` in `asyncio.gather()` → silent crash (run 48)
  - Fix: Add `asyncio.wait_for(..., timeout=30.0)` and `return_exceptions=True` in `two_stage_pipeline.py`

**Duplicate Conversation Assignment Bug (2026-01-22)**:

- Fixed bug where PM review splits could assign same conversation to multiple stories
- Root cause: LLM sometimes assigned conversation_id to multiple sub_groups
- Defense-in-depth fix:
  1. Prompt constraint: Each conversation_id MUST appear in exactly ONE place
  2. Code change: `_handle_pm_split()` uses `pop()` instead of `dict.get()` (first assignment wins)
  3. Warning logs when duplicate assignments are attempted
- Regression test added: `tests/test_story_creation_service_pm_review.py`
- Fixes conversation 215472742755019 appearing in both stories d3ee3a9c and a4b79d95

### Changed

**Streamlit Frontend Removal (2026-01-22)**:

- Removed deprecated `frontend/` directory (Streamlit UI)
- Project now uses Next.js webapp exclusively at `webapp/`
- Commands updated: Use `npm run dev` in `webapp/` instead of `streamlit run frontend/app.py`

### Added

**Theme Quality Improvements - SAME_FIX Test + PM Review (2026-01-21)** - PR #101:

- **SAME_FIX Test for Signature Specificity (Improvement 1)**:
  - New `validate_signature_specificity()` function in `src/theme_extractor.py`
  - Validates theme signatures for proper granularity at extraction time
  - Rejects broad suffixes (`_failure`, `_error`, `_issue`, `_problem`) unless accompanied by specific symptom indicators
  - Specific pattern allowlist: `_duplicate_`, `_missing_`, `_timeout_`, `_permission_`, `_sync_`, `_oauth_`, `_upload_`, etc.
  - Added `signature_quality_guidelines` to `config/theme_vocabulary.json` with SAME_FIX test examples

- **PM Review Before Story Creation (Improvement 2)**:
  - New `PMReviewService` in `src/story_tracking/services/pm_review_service.py`
  - LLM-based coherence evaluation: "Would ONE implementation fix ALL of these?"
  - Feature flag `PM_REVIEW_ENABLED` for controlled rollout (default: disabled)
  - Decision types: `keep_together` | `split` (creates sub-groups) | `reject` (all to orphans)
  - Sub-groups with >=3 conversations become stories, smaller ones become orphans
  - Integrated into `StoryCreationService.process_theme_groups()` after quality gates
  - Error handling defaults to `keep_together` (fail-safe behavior)

- **ProcessingResult PM Review Metrics**:
  - `pm_review_kept`: Groups kept together by PM review
  - `pm_review_splits`: Groups split into sub-groups by PM review
  - `pm_review_rejects`: Groups where all conversations rejected (routed to orphans)
  - `pm_review_skipped`: Groups that bypassed PM review (disabled, timeout, single-conv)

- **Test Coverage**: 15 tests in `tests/test_story_creation_service_pm_review.py`

### Fixed

**Pipeline Pagination Bug - Search API Integration (2026-01-21)**:

- Fixed critical bug where pipeline fetched ALL Intercom conversations (338k+) and filtered by date client-side
- Added `search_by_date_range_async()` method to IntercomClient using Intercom Search API
- Updated `fetch_quality_conversations_async()` to use Search API for server-side `created_at` filtering
- Added async methods with aiohttp for true non-blocking I/O in pipeline
- Added orphan worker cleanup to prevent leaked processes on server restart
- Reduced 2-day fetch time from ~9 hours to ~30 seconds (run 26: 91 conversations in 65.7s)
- PR #100: 5-personality review completed (2 rounds → CONVERGED)
  - Round 1: All 5 reviewers BLOCK (debug prints, PID file security, sock_read timeout, deprecated datetime)
  - Round 2: All 5 reviewers APPROVE after fixes (~60 debug prints removed, PID mechanism deleted, timeouts fixed)

### Added

**Milestone 6: Canonical Pipeline Consolidation (2026-01-21)** - PR #99 (Issues #82, #83, #85):

- Wired quality gates (EvidenceValidator + ConfidenceScorer) into `StoryCreationService`
- New `_apply_quality_gates()` method runs at top of processing loop
- New `_route_to_orphan_integration()` method for unified orphan routing
- Added `QualityGateResult` dataclass for structured gate pass/fail decisions
- Added `quality_gate_rejections` counter to `ProcessingResult`
- Added `orphan_fallbacks` counter for observability when fallback path is used
- Partial failure tracking: processed conversation IDs tracked to prevent duplicates on fallback
- Retired `PipelineIntegrationService` (466 lines deleted, zero production callers)
- Retired `test_pipeline_integration.py` (507 lines deleted)
- Cleaned `__init__.py` exports (no more dead exports)
- Updated architecture docs to reflect canonical pipeline path:
  ```
  two_stage_pipeline.py -> StoryCreationService -> Quality Gates -> Story/Orphan
  ```
- 68 new tests for quality gates including boundary condition tests (49.9, 50.0, 50.1 thresholds)

**Dry Run Preview Visibility (2026-01-21)** - PR #93 (Issue #75):

- Added ability to preview classification results from dry runs in the UI
- New backend endpoint: `GET /api/pipeline/status/{run_id}/preview`
- Dry run preview shows:
  - Classification breakdown by type and confidence (bar charts)
  - 5-10 representative sample conversations with snippets
  - Top 5 extracted themes with counts
  - Total classified count and timestamp
- In-memory storage with automatic cleanup (max 5 previews) prevents unbounded memory growth
- Proactive cleanup on new dry runs and terminal run completion
- Pydantic models: `DryRunSample`, `DryRunClassificationBreakdown`, `DryRunPreview`
- TypeScript types added to `webapp/src/lib/types.ts`
- Frontend preview panel in `webapp/src/app/pipeline/page.tsx`
- 30 unit tests in `tests/api/test_pipeline_dry_run_preview.py`

**ResolutionAnalyzer and KnowledgeExtractor Pipeline Integration (2026-01-21)** - PR #92 (Issues #78, #79):

- Wired `ResolutionAnalyzer` and `KnowledgeExtractor` modules into `two_stage_pipeline.py`
- Replaced simple `detect_resolution_signal()` with full `ResolutionAnalyzer` analysis
- Added helper functions:
  - `get_full_resolution_analysis()` - Returns complete resolution analysis for storage
  - `extract_knowledge()` - Extracts knowledge fields for support_insights
- `support_insights` JSONB column now populated with:
  - `resolution_analysis`: primary_action, action_category, all_actions, categories, suggested_type, matched_keywords
  - `knowledge`: root_cause, solution_provided, product_mentions, feature_mentions, self_service_gap, gap_evidence
- Module-level eager initialization for stateless analyzers (efficient re-use)
- Both sync and async pipeline paths enriched with support_insights
- 21 new tests in `tests/test_pipeline_integration_insights.py`
- Added Architect Output Review Gate for deletion approval workflow in process-playbook

**StoryCreationService Pipeline Integration (2026-01-21)** - PR #81 (Issue #77):

- Wired `StoryCreationService` into UI pipeline router, replacing inline story creation logic
- Added `process_theme_groups()` method as the UI pipeline entry point for story creation
- Consolidated `MIN_GROUP_SIZE` constant (removed duplicate `MIN_CONVERSATIONS_FOR_STORY`)
- Added proper error tracking for pipeline run linking and evidence creation failures
- Security hardening: conversation ID validation, proper exception handling (never swallow KeyboardInterrupt/SystemExit)
- 11 new tests in `tests/test_story_creation_service.py` for pipeline integration
- Reduced pipeline.py by ~50 lines through service delegation

**Vector Integration Phase 1 Complete (2026-01-20)** - PRs #52, #57, #60, #61:

- Accept/reject endpoints for suggested evidence:
  - `POST /api/research/stories/{story_id}/suggested-evidence/{evidence_id}/accept`
  - `POST /api/research/stories/{story_id}/suggested-evidence/{evidence_id}/reject`
  - Evidence ID format: `source_type:source_id`
  - Error codes: 400 (invalid format), 404 (story not found), 409 (duplicate)
- Filter rejected evidence from suggestions in `get_suggested_evidence` endpoint
- `scripts/run_initial_embeddings.py` - 5-step validation script for vector setup
- `docs/runbook/vector-search-setup.md` - Installation and troubleshooting guide
- 18 new tests for evidence endpoints and filtering (50 total in test_research.py)
- `suggested_evidence_decisions` table (PR #52) for tracking PM accept/reject decisions

### Fixed

**Embedding Pipeline Bugs (2026-01-20)** - PR #61:

- Switched from `text-embedding-3-large` to `text-embedding-3-small` (pgvector 0.8 has 2000 dim limit)
- Added missing `url` column to INSERT statement in `embedding_pipeline.py`
- Updated migration schema with `url TEXT NOT NULL`

### Known Issues

- #62: coda_page adapter fails with "no such column: name" (deferred to future session)
- P95 search latency 712ms with small dataset (expected to improve with more embeddings)

---

**Domain Knowledge Map + Haiku Classification (2026-01-20)** - PR #42:

- `config/codebase_domain_map.yaml` - 16 issue categories mapped to codebase locations
  - Categories: scheduling, billing, auth, ai_creation, analytics, media, social_integrations, etc.
  - Each category includes: description, keywords, repos, search_paths
- `src/story_tracking/services/domain_classifier.py` - Haiku 4.5 classifier service
  - Two-stage classification: fast keyword fallback + semantic Haiku
  - Latency target: <500ms (keyword: <50ms)
  - Cost: ~$0.00015 per classification (~$4.50/month for 1,000 daily)
  - Structured output with category, confidence, reasoning, suggested paths
- `explore_with_classification()` method in `CodebaseContextProvider`
  - Classification-guided exploration with prioritized search paths
  - Fallback to standard exploration on error
- Test suite: 37 tests (24 unit + 13 integration)
- Validation script: `scripts/validate_domain_classifier.py`

**VDD Methodology Limitations Analysis (2026-01-20)**:

- Created `docs/analysis/codebase-search-vdd-limitations.md`
- Documented 4 fundamental limitations preventing VDD success
- Recommended alternatives: domain map, embeddings, human feedback

**Vector Integration Plan Architecture Review (2026-01-20)**:

- 5-personality review appended to `docs/vector-integration-plan.md`
- Round 1: 21 issues identified (2 critical, 4 high)
- Round 2: All reviewers CONVERGE, plan approved
- Security items consciously deferred (internal tool scope)

**Hybrid Review Output Protocol (2026-01-19)**:

- 5-personality reviewers now output in hybrid format:
  - Verbose markdown to `.claude/reviews/PR-{N}/{reviewer}.md`
  - Compact JSON to `.claude/reviews/PR-{N}/{reviewer}.json` (~2-5KB each)
  - Short summary message returned to Tech Lead
- New fields for Tech Lead decision-making: `why`, `verify`, `scope`, `see_verbose`
- Unique issue ID prefixes per reviewer: R (Reginald), S (Sanjay), Q (Quinn), D (Dmitri), M (Maya)
- Created `.claude/reviews/SCHEMA.md` documenting the format
- Updated all 5 personality files with Output Protocol section
- Added `/post-compact` command for context recovery after auto-compaction

**Voice Mode Support (2026-01-18)**:

- Voice conversation commands: `/voice` and `/voice-stop`
- `format-voice-output.sh` hook for voice output formatting
- Updated `.claude/settings.json` with voice hook configuration

### Fixed

**VDD Codebase Search Round 1 Review Fixes (2026-01-19)**:

- Q1/S3 CRITICAL: Replaced hardcoded `/Users/paulyokota` path with `${REPOS_PATH}` env var
- D1 HIGH: Deleted 800+ lines of dead code (`evaluate_results.py` - SDK version superseded by v2)
- S1 HIGH: Fixed shell argument injection via bash arrays in `run_vdd_loop.sh`
- Q3 HIGH: Added consistent model validation across VDD scripts
- R1 MEDIUM: Added config file existence check with clear error message
- R2 MEDIUM: Replaced greedy JSON regex with brace-counting parser in `apply_learnings.py`
- R4 MEDIUM: Added None guards for nullable Story fields in `cheap_mode_evaluator.py`
- Q4 MEDIUM: Added `sys.path.insert` for cross-directory imports in ralph scripts
- D2/D3 LOW: Removed stale doc refs and broken `example_usage.sh`

**Test Configuration (2026-01-16)**:

- Added `tests/conftest.py` to configure PYTHONPATH for pytest
- Fixes import errors in `test_codebase_context_provider.py`, `test_codebase_security.py`, `test_dual_story_formatter.py`

**Ralph V2 Dual-Mode Evaluation System (2026-01-16)**:

- Complete dual-mode evaluation system for story quality assessment
  - `scripts/ralph/` - Full implementation (4,589 lines across 14 files)
  - Expensive mode: LLM-based evaluation (gestalt scoring)
  - Cheap mode: Pattern-based evaluation (keyword matching)
  - Gap tracking: Measures calibration between modes (target: ≤0.5)
- Pattern learning loop:
  - Provisional patterns proposed from expensive mode feedback
  - Commit patterns at ≥70% accuracy over 10+ stories
  - Reject patterns at <30% accuracy over 5+ stories
- Convergence monitoring:
  - Divergence detection with diagnostics
  - Self-healing action recommendations
  - Convergence proof (stable gap within target)
- Configuration consolidated in `ralph_config.py`
- 38 unit tests (all passing)
- 5-personality code review converged in 2 rounds
- Commit: 3000d3b

### Fixed

**VDD Codebase Search - JSON Output Format (2026-01-16)**:

- Switched from bullet list to JSON output format for file extraction
  - New format: `{"relevant_files": ["repo/path/file.ext", ...]}`
  - Moved format instructions to END of prompt (recency effect)
  - Stronger compliance language ("will be DISCARDED")
- Fixed prompt compliance issue causing "0 files extracted"
  - Root cause: Sonnet sometimes output summary instead of file list
  - JSON format is more reliable for structured output
- Improved extraction logic:
  - Priority 1: JSON parsing with "relevant_files" key
  - Fallback: Regex patterns for backward compatibility
- Fixed ReDoS vulnerability (replaced regex with linear brace counting)
- Added FORMAT_ERROR detection vs parsing issues
- Added `--fresh` flag to archive outputs and start fresh run
- Commits: 9f2ead7, 2c39475

**VDD Offline Mode & Data Improvements (2026-01-16)**:

- Database-backed conversation fetching for offline VDD testing
  - `--from-db` flag in `fetch_conversations.py` queries PostgreSQL instead of Intercom API
  - `DatabaseConversationFetcher` class with `stage1_type` to product area mapping
  - Diversity sampling maintained across product areas
- `--intercom-only` flag to filter out Coda imports (research data)
  - Excludes `coda_*` prefixed IDs to only use real support conversations
  - Database: 9,364 Coda imports vs 680 real Intercom conversations
- CLI conversion for `apply_learnings.py`:
  - Converted from Anthropic SDK to Claude CLI subprocess
  - Uses `env -u ANTHROPIC_API_KEY` to force CLI subscription mode
  - Model validation whitelist prevents command injection
- Updated `run_vdd_loop.sh` with new flags: `--from-db`, `--intercom-only`
- Fetched 50 new Intercom conversations (Jan 13-16) to fill data gap

**VDD Codebase Search System (2026-01-15)**:

- Complete VDD (Validation-Driven Development) harness for codebase search optimization
  - `scripts/codebase-search-vdd/` - Full VDD loop infrastructure
  - `run_vdd_loop.sh` - Bash orchestrator with convergence detection
  - `fetch_conversations.py` - Fetch conversations from Intercom for testing
  - `run_search.py` - Run codebase search using CodebaseContextProvider
  - `evaluate_results_v2.py` - CLI-based evaluation using dual exploration pattern
  - `apply_learnings.py` - Apply learnings from evaluation to improve search
  - `config.json` - Configurable thresholds and parameters
- CLI-based evaluation approach (v2):
  - Uses `claude --print` for explorations instead of Anthropic SDK
  - Dual exploration pattern: Two independent Claude explorations build ground truth
  - Model validation to prevent command injection
  - No separate API key required (uses Claude Code's auth)
  - Significantly faster than SDK tool-use approach (~1 call vs ~25+ round-trips)
- Architecture documentation: `docs/architecture/codebase-search-vdd.md`
- Tests: `tests/test_fetch_conversations_vdd.py`
- Commits: 0e47b09, 12e026c, 2576808

**Voice Mode Improvements (2026-01-15)**:

- Improved voice mode defaults in `.claude/skills/voice-mode/SKILL.md`:
  - Added `metrics_level: "minimal"` as default for cleaner output
  - Documented multi-sentence response pattern for better readability
  - Queue messages with `wait_for_response=false` except final message
- Added experimental PostToolUse hook for voice output formatting
- Commit: 2d4b87b

**Knowledge Cache Learning System (2026-01-13)**:

- Learning system for story generation with codebase context
  - `scripts/ralph/knowledge_cache.py` - Two-phase learning module
    - `load_knowledge_for_generation()` - Loads codebase map, patterns, rules, insights
    - `update_knowledge_from_scoping()` - Captures good/bad patterns from validation
  - `scripts/ralph/learned_patterns.json` - Cached patterns from scoping validation
  - Bounded growth (max 50 insights per service), error handling, configuration constants
- Pipeline integration in `scripts/ralph/run_pipeline_test.py`:
  - Loads knowledge context before story generation (~16K chars)
  - Auto-updates cache after each scoping validation run
  - Automatic learning loop: generate → validate → learn → generate better
- Updated `scripts/ralph/PROMPT_V2.md`:
  - Added knowledge cache to Required Reading (Phase 0, section 5)
  - Added `knowledge_cache.py` to Modifiable Components table
  - Updated Phase 1 steps to show learning loop
- Renamed `scripts/ralph/PROMPT.md` → `scripts/ralph/PROMPT_V1.md` (for history)
- Commits: dc8107c, 8d6bf93

**Ralph V2 Pipeline Optimization Session (2026-01-13)**:

- Ran 7-iteration autonomous loop optimizing Feed Forward story generation
- Achieved gestalt 5.0 (all sources 5/5), scoping plateaued at 3.5
- Key improvements to `scripts/ralph/run_pipeline_test.py`:
  - Fixed file path patterns to actual Tailwind codebase structure
  - Fixed service architecture (aero → brandy2 → ghostwriter, not ghostwriter → brandy2)
  - Excluded gandalf from Pinterest OAuth chain
  - Added Ghostwriter-specific scoping rules (brand voice ≠ context retention)
- Bug fix: MAX_ITERATIONS enforcement
  - `scripts/ralph/PROMPT_V2.md` - Added HARD CAP CHECK to iteration work gate
  - `scripts/ralph/ralph_v2.sh` - Write MAXIMUM ITERATIONS to progress.txt
  - Ralph now stops at configured max instead of continuing indefinitely
- Commits: d56a986, 103a351

**Ralph Wiggum Autonomous Loop Infrastructure (2026-01-13)**:

- Complete autonomous story generation loop for Feed Forward
  - `scripts/ralph/ralph.sh` - Bash loop script with completion detection
  - `scripts/ralph/PROMPT.md` - Hardened 5-phase workflow (1,264 lines)
  - `scripts/ralph/prd.json` - Task tracking with database stories
  - `scripts/ralph/progress.txt` - Cross-iteration memory system
- Quality thresholds: Gestalt >= 4.0, Dimensional >= 3.5, Playwright >= 85%
- Initialized with 2 stories from database
- Ready to run: `./scripts/ralph/ralph.sh 15`

**Unified Research Search with Vector Embeddings (2026-01-13)**:

- Semantic search across Coda research and Intercom support data
  - `src/research/` module with adapters, unified search, embedding pipeline
  - pgvector with HNSW index for approximate nearest neighbor search
  - OpenAI text-embedding-3-large (3072 dimensions)
  - Content hash-based change detection for incremental reindexing
- Source adapter pattern (`src/research/adapters/`):
  - `base.py` - Abstract base with content hashing, snippet creation
  - `coda_adapter.py` - Coda pages and themes adapter
  - `intercom_adapter.py` - Intercom support conversations adapter
- UnifiedSearchService (`src/research/unified_search.py`):
  - `search()` - Query-based semantic search with source filtering
  - `search_similar()` - "More like this" similarity search
  - `suggest_evidence()` - Evidence suggestions for stories (Coda-only)
  - `get_stats()` - Embedding statistics
- EmbeddingPipeline (`src/research/embedding_pipeline.py`):
  - Batch embedding with OpenAI API
  - Graceful degradation on embedding service failures
  - Configurable via `config/research_search.yaml`
- Research API router (`src/api/routers/research.py`):
  - `GET /api/research/search` - Semantic search
  - `GET /api/research/similar/{source_type}/{source_id}` - Similar content
  - `GET /api/research/stats` - Embedding statistics
  - `POST /api/research/reindex` - Trigger re-embedding (admin)
  - `GET /api/research/stories/{id}/suggested-evidence` - Story evidence
- Frontend `/research` page (`webapp/src/app/research/page.tsx`):
  - Multi-source search UI with source filtering
  - Search results with similarity scores and source badges
  - Debounced search input
- Frontend components:
  - `ResearchSearch.tsx` - Search input with suggestions
  - `SearchResults.tsx` - Results display with metadata
  - `SourceFilter.tsx` - Filter by Coda Pages, Themes, Intercom
  - `SuggestedEvidence.tsx` - Evidence suggestions for story detail
- Research search types (`webapp/src/lib/types.ts`):
  - ResearchSourceType, SearchResult, SuggestedEvidence
  - SOURCE_TYPE_CONFIG with display labels and colors
- Database migration: `src/db/migrations/001_add_research_embeddings.sql`
- Test suite: 32 tests in `tests/test_research.py`
- Architecture documentation: `docs/search-rag-architecture.md`
- Configuration: `config/research_search.yaml`

**Tailwind Codebase Map (2026-01-13)**:

- Comprehensive URL → Service mapping for Intercom ticket routing (`docs/tailwind-codebase-map.md`)
  - 24 validated components with 99% confidence scores
  - Page Title → Path lookup table for feature name vocabulary
  - URL Path gotchas (legacy vs v2 routes) documented via Playwright verification
  - Service detection decision tree with regex patterns
  - Backend service inventory (bach, aero, otto, tack, charlotte, etc.)
  - Database schema patterns (Jarvis, Cockroach, Supabase)
- Verified against live Tailwind app using Playwright browser automation
- Confidentiality marker added for internal use

**Coda Standalone Extraction Script (2026-01-12)**:

- Standalone Node.js extraction script (`scripts/coda_full_extract.js`)
  - Launches Chromium with persistent profile for one-time auth
  - Recursively discovers pages from navigation and content links
  - Scroll-to-load for lazy content extraction
  - Resumable via manifest (skips already-extracted pages)
  - Logs to console and `data/coda_raw/extraction.log`
- Webapp extraction controls at `/tools/extraction`
- Updated `docs/coda-extraction/coda-extraction-doc.md` with standalone script documentation

**Coda JSON Extraction System (2026-01-12)**:

- High-speed Coda content extraction via direct JSON parsing
  - Discovered Coda's internal JSON endpoints (`fui-critical`, `fui-allcanvas`)
  - `scripts/coda_embed_probe.js` - Network probe to capture JSON endpoints
  - `scripts/coda_json_extract.js` - Direct JSON parsing (1,271 pages in 1.4 seconds)
  - `scripts/coda_storage_optimize.js` - Compress JSON + create SQLite/FTS5 database
- Storage optimization:
  - `data/coda_raw/archive/*.gz` - Compressed JSON (107MB → 11MB, 90% reduction)
  - `data/coda_raw/coda_content.db` - SQLite + FTS5 for full-text search (20MB)
  - `data/coda_raw/pages_json/*.md` - 1,271 markdown files for RAG embedding
- Performance: 1,271 pages extracted in 1.4 seconds at $0 cost (vs 20+ min and $0.10/page for vision)
- Search example: `sqlite3 coda_content.db "SELECT title FROM pages_fts WHERE pages_fts MATCH 'prototype'"`

**Coda Extraction Strategy (2026-01-12)**:

- Documentation for comprehensive Coda data extraction (`docs/coda-extraction/`)
  - `coda-extraction-doc.md` - "Extract Everything, Decide Later" philosophy
  - `coda-extraction-pmt.md` - Playwright workflow prompt for page extraction
- Key decisions:
  - Coda as peer data source (equal weight to Intercom themes)
  - Hybrid extraction: Playwright (pages) + API (tables, hierarchy)
  - Output structure: `data/coda_raw/` with manifest tracking
  - Supports multiple downstream uses: theme source, story enrichment, validation signal

**Skills Migration (2026-01-12)**:

- Migrated v1 agent profiles to v2 skills architecture (PR #31)
- Converted old agent profiles (`docs/process-playbook/agents/`) to redirect stubs
- Skills now in `.claude/skills/{agent}/SKILL.md + IDENTITY.md`
- Declarative context loading via `keywords.yaml`

**Coda Story Formatting & Markdown Rendering (2026-01-12)**:

- Coda story formatting functions (`src/story_formatter.py`):
  - `format_coda_excerpt()` - Format Coda excerpts with participant/table links
  - `format_excerpt_multi_source()` - Router for source-aware formatting
  - `build_research_story_description()` - Research story template (Theme Summary → Quotes → Investigation)
- Frontend markdown rendering:
  - Added `react-markdown` for rendering story descriptions
  - Comprehensive CSS styles for markdown content (headers, blockquotes, links, code)
- Frontend Coda evidence support (`EvidenceBrowser.tsx`):
  - `getExcerptUrl()` - Source-aware URL generation for Coda/Intercom excerpts
  - Coda deep links using composite IDs (`coda_row_{table_slug}_{row_id}`)
- Backfill script (`scripts/backfill_coda_formatting.py`):
  - Regenerate descriptions for existing Coda stories
  - Idempotency check to prevent double-formatting
- Unit tests for all new formatting functions

**Webapp Analytics & Bug Fixes (2026-01-12)**:

- Analytics page (`webapp/src/app/analytics/page.tsx`)
  - Story metrics dashboard with MetricCard components
  - Status distribution DonutChart visualization
  - TrendingList for theme trends
  - Period selector (7d, 30d, 90d)
- New frontend components:
  - `MetricCard` - Displays metric with optional delta indicator
  - `DonutChart` - SVG donut chart with legend
  - `TrendingList` - Theme trends with direction indicators
  - `EvidenceBrowser` - Collapsible evidence excerpts by source
  - `LabelPicker` - Searchable label dropdown with keyboard navigation
  - `ShortcutSyncPanel` - Sync status and action buttons
  - `SyncStatusBadge` - Visual sync state indicator
- Frontend test coverage (24 new tests):
  - `SyncStatusBadge.test.tsx` - State rendering tests
  - `charts.test.tsx` - MetricCard, DonutChart, TrendingList tests
  - `EvidenceBrowser.test.tsx` - Evidence display and grouping tests
  - `LabelPicker.test.tsx` - Label selection and dropdown tests
  - `ShortcutSyncPanel.test.tsx` - Sync panel integration tests
- Backend test coverage (8 new tests):
  - `test_sync_service.py` - Metadata stripping tests for `_strip_feedforward_metadata()`

### Fixed

**Webapp Bug Fixes (2026-01-12)**:

- Fixed Tailwind CSS resolution error in Next.js Turbopack - Added `turbopack.root: process.cwd()` to `next.config.ts`
- Fixed analytics 500 error - SQL referenced non-existent `theme_signature` column
- Fixed "Refresh from Shortcut" appending duplicate metadata - Added `_strip_feedforward_metadata()` regex
- Fixed UI theme flash on page refresh - Inline script sets theme before React hydration
- Fixed drop indicator contrast in dark mode - Changed background to `hsl(0, 0%, 20%)`

**Phases 3 & 4: Shortcut Sync + Analytics (2026-01-10)**:

- Bidirectional Shortcut sync service (`src/story_tracking/services/sync_service.py`)
  - `push_to_shortcut()` - Push story changes to Shortcut
  - `pull_from_shortcut()` - Pull updates from Shortcut
  - `sync_story()` - Auto-determine sync direction based on timestamps
  - `handle_webhook()` - Process Shortcut webhook events
  - `_format_shortcut_description()` - Rich description formatting with metadata
- Label registry service (`src/story_tracking/services/label_registry_service.py`)
  - `list_labels()` - List all labels with optional source filter
  - `import_from_shortcut()` - Import labels from Shortcut taxonomy
  - `ensure_label_in_shortcut()` - Create label in Shortcut if missing
- Analytics service (`src/story_tracking/services/analytics_service.py`)
  - `get_story_metrics()` - Aggregate story counts by status/priority
  - `get_trending_themes()` - Themes with growing evidence
  - `get_source_distribution()` - Breakdown by data source
  - `get_evidence_summary()` - Evidence statistics
- Sync API router (`src/api/routers/sync.py`)
  - `POST /api/sync/shortcut/push` - Push story to Shortcut
  - `POST /api/sync/shortcut/pull` - Pull story from Shortcut
  - `POST /api/sync/shortcut/webhook` - Webhook handler
  - `GET /api/sync/shortcut/status/{story_id}` - Sync status
- Labels API router (`src/api/routers/labels.py`)
  - `GET /api/labels` - List all labels
  - `POST /api/labels/import` - Import from Shortcut
  - `POST /api/labels` - Create internal label
- Enhanced analytics endpoints (`src/api/routers/analytics.py`)
  - `GET /api/analytics/stories` - Story metrics
  - `GET /api/analytics/themes/trending` - Trending themes
  - `GET /api/analytics/sources` - Source distribution
- Sync and label models (`src/story_tracking/models/sync.py`, `label.py`)
- Comprehensive test suite (6 new test files)

**Coda Research Integration (2026-01-10)**:

- Coda JSON loader script (`scripts/load_coda_json.py`)
  - Loads extracted Coda themes as pseudo-conversations
  - Groups by source_row_id for deduplication
  - Sets `data_source='coda'` for source tracking
- 4,682 Coda conversations loaded into database
- 1,919 aggregated Coda themes created
- 3 research-based stories created from Coda insights:
  - Mobile App feature request
  - Cloud Storage Integration request
  - Streams Terminology clarification
- 6 total stories synced to Shortcut (#518-523)

**Webapp Draft Status Support (2026-01-10)**:

- Added "draft" to StatusKey type (`webapp/src/lib/types.ts`)
- Added "draft" to STATUS_ORDER array
- Added draft config to STATUS_CONFIG with label and color
- Added `--status-draft` CSS variable for dark theme (60% lightness)
- Added `--status-draft` CSS variable for light theme (45% lightness)
- Draft column now visible in webapp board view

**Sajid-Inspired Design System (2026-01-10)**:

- Pure HSL neutral color system with 5% lightness increments
- Satoshi font (locally loaded via next/font/local)
- Higher contrast UI layers (10% increments between elements)
- Gradient backgrounds for raised elements
- Updated header, search, buttons, theme toggle styling
- Consistent styling between main page and story detail page

**Story Tracking Web App Phase 2.5 Complete (2026-01-09)**:

- Interactive kanban board with drag-and-drop (`webapp/src/app/board/page.tsx`)
  - Cards can be dragged between columns to update status
  - Smooth animations with Framer Motion
  - Custom collision detection for reliable drop targeting
  - Visual drop indicators matching dragged card height
- Drag-and-drop infrastructure:
  - Type definitions (`webapp/src/lib/dnd.types.ts`)
    - DraggableId and DroppableId type-safe ID formats
    - DraggableData and DroppableData for collision detection
    - StoryMoveEvent for status updates
    - Helper functions for ID creation and extraction
  - DndBoardProvider (`webapp/src/components/DndBoardProvider.tsx`)
    - Custom collision detection using ID patterns (story-_, column-_)
    - Context-based height sharing for drop indicators
    - Drag state management with React Context
    - ARIA live region for screen reader announcements
  - DroppableColumn (`webapp/src/components/DroppableColumn.tsx`)
    - SortableContext integration for vertical list sorting
    - Drop indicators with animated height transitions
    - Bottom drop zone for empty columns and column ends
    - Empty state handling with placeholder
- Accessibility features:
  - Keyboard navigation with arrow keys and Space/Enter
  - Screen reader announcements for drag events
  - Focus indicators on keyboard navigation
  - Semantic ARIA roles (status, live region)
- Visual feedback:
  - Animated drag overlay with 3° rotation and 1.02x scale
  - Drop indicators with matching card height
  - Card collapse animation during drag (height: 0 transition)
  - Enhanced shadow on drag overlay
- Technical implementation:
  - dnd-kit core for drag-and-drop primitives
  - dnd-kit sortable for sortable lists
  - Framer Motion for smooth overlay animations
  - Custom PointerSensor with 8px activation constraint
  - KeyboardSensor with sortable coordinates

**Story Tracking Web App Phase 2 Complete (2026-01-09)**:

- Edit mode UI for story detail page (`webapp/src/app/story/[id]/page.tsx`)
  - Edit/Save/Cancel buttons with loading states
  - Full field editing: title, description, severity, product area, technical area
  - Label management with add/remove chip UI
  - Theme-aware styling (light and dark modes)
  - Error handling and validation
  - Auto-populates edit form from current story state
- Pipeline integration service (`src/story_tracking/services/pipeline_integration.py`)
  - `PipelineIntegrationService` class bridges PM review to story creation
  - `ValidatedGroup` dataclass for PM review output
  - `create_candidate_story()` - Single story creation with deduplication
  - `bulk_create_candidates()` - Batch creation with progress logging
  - `find_existing_story()` - Signature-based deduplication
  - Automatic evidence bundle creation with conversation links
  - Source stats calculation and excerpt preparation
- Comprehensive test suite (`tests/test_pipeline_integration.py`)
  - 14 tests covering creation, deduplication, bulk operations, validation
  - Mock fixtures for StoryService and EvidenceService
  - Edge case testing (empty groups, missing fields, errors)
- Bug fixes:
  - Fixed `FeedForwardLogo.tsx` TypeScript error (systemTheme → resolvedTheme)
  - Fixed `ThemeProvider.tsx` React best practices (lazy state initialization, useMemo optimization)

**Story Tracking Web App Scaffolding (2026-01-09)**:

- Database schema for system of record (`src/db/migrations/004_story_tracking_schema.sql`)
  - `stories` - Canonical work items with Shortcut-compatible fields
  - `story_comments` - Comments with source tracking (internal/shortcut)
  - `story_evidence` - Evidence bundles (conversations, themes, excerpts, source_stats)
  - `story_sync_metadata` - Bidirectional Shortcut sync state
  - `label_registry` - Shortcut taxonomy + internal extensions
- Pydantic models (`src/story_tracking/models/`)
  - Story, StoryCreate, StoryUpdate, StoryWithEvidence
  - StoryEvidence, EvidenceExcerpt, StoryComment
  - SyncMetadata, LabelRegistryEntry
- Service layer stubs (`src/story_tracking/services/`)
  - StoryService - CRUD, listing, search (stubs with TODOs)
  - EvidenceService - Evidence management (stubs with TODOs)
- Session kickoff doc (`docs/session/story-tracking-webapp-kickoff.md`)
- Feature branch: `feature/story-tracking-webapp`
- `frontend-design` plugin installed for UI development

**Multi-Source Architecture Complete (2026-01-09)**:

- Coda bulk import: 14,769 themes from 356 tables (9,675 rows)
- Source adapters (`src/adapters/`)
  - `coda_adapter.py` - Normalizes Coda table rows to common format
  - `intercom_adapter.py` - Normalizes Intercom conversations
- Cross-source analytics (`src/analytics/cross_source.py`)
  - `get_cross_source_themes()` - Themes ranked by source presence
  - `get_high_confidence_themes()` - Themes in BOTH sources
  - `get_source_comparison_report()` - Summary statistics
- Priority categorization: high_confidence, strategic, tactical
- Pipeline updates (`src/two_stage_pipeline.py`)
  - Added `--source` parameter (intercom/coda)
- Theme tracker updates (`src/theme_tracker.py`)
  - `source_counts` JSONB field for per-source tracking
- Story formatter updates (`src/story_formatter.py`)
  - `format_multi_source_evidence()` - Evidence from both sources
  - `build_multi_source_description()` - Full story with source breakdown
- Import reports (`reports/coda_import_2026-01-09.md`)

**Coda Research Repository Integration (2026-01-09)**:

- Coda API credentials configured (`.env`)
  - `CODA_API_KEY` - API authentication
  - `CODA_DOC_ID` - Tailwind Research Ops document (`c4RRJ_VLtW`)
- Comprehensive repository analysis (`docs/coda-research-repo.md`)
  - 100 pages explored (hierarchical canvas content)
  - 100 tables with structured research data (synthesis, call trackers, surveys)
  - AI Summary pages (27) with synthesized user research insights
  - Discovery Learnings page with JTBD framework
  - Bank of Research Questions with product priorities
- Content extraction via `/pages/{id}/content` API endpoint
  - Structured markdown parsing (headings, bullets, paragraphs)
  - User quotes, proto-personas, pain points, feature requests
- Theme extraction strategy documented
  - Maps to existing FeedForward theme types
  - Integrates with Intercom-sourced themes

**FastAPI + Streamlit Frontend (2026-01-09)**:

- FastAPI backend (`src/api/`)
  - `main.py` - App entrypoint with CORS, 19 routes
  - `deps.py` - Database dependency injection with RealDictCursor
  - `routers/health.py` - Health checks (`/health`, `/health/db`, `/health/full`)
  - `routers/analytics.py` - Dashboard metrics (`/api/analytics/dashboard`, `/stats`)
  - `routers/pipeline.py` - Pipeline control (`/api/pipeline/run`, `/status/{id}`, `/history`, `/active`)
  - `routers/themes.py` - Theme browsing (`/api/themes/trending`, `/orphans`, `/singletons`, `/all`, `/{signature}`)
  - `schemas/` - Pydantic models for all endpoints
- Streamlit frontend (`frontend/`)
  - `app.py` - Main entry with API health check
  - `api_client.py` - FeedForwardAPI wrapper class
  - `pages/1_Dashboard.py` - Metrics overview, classification charts, recent runs
  - `pages/2_Pipeline.py` - Run configuration form, status polling, history table
  - `pages/3_Themes.py` - Trending/orphan/singleton tabs, filtering, detail view
  - `README.md` - Frontend documentation
- Updated `requirements.txt` with FastAPI and uvicorn dependencies
- Architecture documentation (`docs/architecture.md` Section 12)

**Signature Tracking System (2026-01-09)**:

- Signature utilities module (`src/signature_utils.py`)
  - `SignatureRegistry` class for tracking PM signature changes
  - `normalize()` - Standardizes signatures (lowercase, underscores, no special chars)
  - `register_equivalence()` - Tracks original → canonical mappings
  - `get_canonical()` - Follows equivalence chains to find PM-approved form
  - `reconcile_counts()` - Merges historical counts using equivalences
  - `build_signature_from_components()` - Consistent signature construction
  - Persistence to `data/signature_equivalences.json`
- Comprehensive test suite (`tests/test_signature_utils.py`)
  - 23 tests covering normalization, equivalences, reconciliation, persistence
  - Real-world scenario test validating 0% orphan rate (was 88%)
- Pipeline hardening (`scripts/run_historical_pipeline.py`)
  - Automatic equivalence tracking when PM review changes signatures
  - Phase 3 uses `reconcile_counts()` for matching
- Architecture documentation (`docs/architecture.md` Section 9)
  - Documents problem, solution, and usage patterns

**Historical Backfill Evidence Capture (2026-01-09)**:

- Enhanced metadata extraction (`scripts/run_historical_pipeline.py`)
  - `extract_conversation_metadata()` - Extracts email, contact_id, user_id from conversations
  - `enrich_with_org_ids()` - Batch fetches org_id from Intercom contacts (async, ~20 concurrent)
  - Intercom URL construction for direct conversation links
- Evidence now includes in Shortcut stories:
  - Email linked to Intercom conversation
  - Org linked to Jarvis organization page
  - User linked to Jarvis user page
  - Full conversation excerpt
- Applied to both Phase 1 (seed) and Phase 2 (backfill) processing
- Enables actionable evidence in promoted orphan stories

**Evidence Validation System (2026-01-09)**:

- Evidence validator module (`src/evidence_validator.py`)
  - `validate_samples()` - Main validation with required/recommended field checks
  - `validate_sample()` - Single sample validation
  - `build_evidence_report()` - Human-readable diagnostic report
  - `EvidenceQuality` dataclass with is_valid, errors, warnings, coverage
  - Placeholder detection to catch historical backfill bug
- Comprehensive test suite (`tests/test_evidence_validator.py`)
  - 20 tests covering validation, coverage calculation, placeholder detection
  - Real-world scenario tests for the exact bug this prevents
- Pipeline integration:
  - `scripts/create_theme_stories.py` - Validates before creating each story
  - `scripts/run_historical_pipeline.py` - Validates in Phase 1 and orphan promotion
  - Stories with invalid evidence are SKIPPED with error messages
  - Stories with poor evidence are created with WARNINGS
- Architecture documentation (`docs/architecture.md` Section 10)
  - Documents required vs recommended fields
  - Validation behavior and usage examples

**Story Formatting Updates (2026-01-09)**:

- Updated 53 orphan stories in Shortcut with proper formatting
  - Verb-first titles (Fix, Investigate, Process, Improve, Review)
  - Structured descriptions with Problem Statement, Investigation Paths, Symptoms, Evidence, Acceptance Criteria
  - Consistent formatting matching existing story patterns

**Pipeline Performance Optimizations (2026-01-08)**:

- Async classification pipeline (`src/two_stage_pipeline.py`)
  - `run_pipeline_async()` with configurable concurrency (default 20 parallel)
  - `--async` flag for production use, ~10-20x faster than sequential
  - Semaphore-controlled API calls to prevent rate limiting
- Batch database inserts (`src/db/classification_storage.py`)
  - `store_classification_results_batch()` using `execute_values` for bulk upserts
  - ~50x faster than individual inserts for large batches
- Consolidated stats query (`src/db/classification_storage.py`)
  - `get_classification_stats()` rewritten as single CTE query
  - 8 queries → 1 query, ~8x faster
- Parallel contact fetching (`src/intercom_client.py`)
  - `fetch_contact_org_ids_batch()` async method with aiohttp
  - `fetch_contact_org_ids_batch_sync()` wrapper for sync code
  - ~50x faster than sequential `fetch_contact_org_id()` calls
- Updated `scripts/classify_to_file.py` to use batch contact fetching

**Story Formatter Consolidation (2026-01-08)**:

- Single source of truth for Shortcut story formatting (`src/story_formatter.py`)
  - `format_excerpt()` - Standardized excerpt with linked metadata
  - `build_story_description()` - Complete story description builder
  - `build_story_name()` - Consistent story naming: `[count] Category - suffix`
  - `get_story_type()` - Category to type mapping (bug/feature/chore)
- Updated `scripts/create_shortcut_stories.py` to import from shared module
- Updated `scripts/create_theme_stories.py` to import from shared module
- Updated `scripts/README.md` with source of truth reference
- Prevents format drift across story creation scripts

**Story Grouping Architecture - Ground Truth Validation Complete (2026-01-08)**:

- Story grouping validation pipeline (`scripts/validate_grouping_accuracy.py`)
  - Compares pipeline groupings against human-labeled story_id ground truth
  - Pairwise precision/recall metrics for grouping evaluation
  - Group purity analysis (% from single human story)
  - Baseline: 35.6% precision, 10.6% recall, 45% pure groups
- Story granularity standard (`docs/story-granularity-standard.md`)
  - INVEST criteria (Independent, Negotiable, Valuable, Estimable, Small, Testable)
  - "Same Story = Same Fix" rule for implementation-ready groupings
  - Bug grouping criteria (duplicates vs related vs unrelated)
  - Decision flowchart for group splitting
- Confidence scoring system (`src/confidence_scorer.py`)
  - Embedding similarity (30%), Intent similarity (20%), Intent homogeneity (15%)
  - Symptom overlap (10%), Product/Component match (10% each), Platform uniformity (5%)
  - Calibrated weights based on PM review correlation
- PM review batch runner (`scripts/run_pm_review_all.py`)
  - LLM validates: "Same implementation ticket? If not, split how?"
  - Creates sub-groups with suggested signatures
  - Orphan handling: sub-groups <3 accumulate over time
- Story grouping architecture documentation (`docs/story-grouping-architecture.md`)
  - 4-phase pipeline design (extraction → scoring → PM review → story creation)
  - Validation results with quantitative metrics
  - Target metrics: 70%+ purity, 50%+ precision

**Phase 5 Ground Truth Validation - Vocabulary Feedback Loop (2026-01-08)**:

- Vocabulary feedback loop script (`src/vocabulary_feedback.py`)
  - Monitors Shortcut stories for new product areas not in vocabulary
  - CLI: `python -m src.vocabulary_feedback --days 30`
  - Generates gap reports with priority levels (high/medium/low)
  - Zero vocabulary gaps found (100% coverage)
- Ground truth validation pipeline (`scripts/phase5_*.py`)
  - `phase5_load_ground_truth.py` - Load 195 conversations with story_id_v2
  - `phase5_run_extraction.py` - Hybrid keyword + LLM extraction
  - `phase5_compare_accuracy.py` - Calculate precision/recall metrics
  - `phase5_vocabulary_gaps.py` - Identify missing themes
  - `phase5_extraction_v2.py` - Iteration 2: Shortcut product names
  - `phase5_extraction_v3.py` - Iteration 3: Context-aware extraction
  - `phase5_accuracy_v2.py` - Family-based semantic matching
- Comprehensive validation documentation:
  - `prompts/phase5_ground_truth_validation.md` - Master specification
  - `prompts/phase5_final_report_2026-01-08.md` - Final report
  - `prompts/phase5_accuracy_report.md` - Accuracy breakdown
  - `prompts/phase5_vocabulary_gaps.md` - Gap analysis
  - `prompts/phase5_data_summary.md` - Dataset statistics
- Family-based semantic matching for product area accuracy
  - Groups similar products (scheduling family, ai_creation family)
  - 64.5% accuracy (up from 44.8% exact match)

**Classifier Improvement - 100% Grouping Accuracy (2026-01-08)**:

- Equivalence class system for conversation grouping (`src/equivalence.py`)
  - Maps `bug_report` and `product_question` to `technical` equivalence class
  - Context-aware refinement: `plan_question` with bug indicators → `technical`
  - Short message handling: skip ambiguous "other" messages (<5 words)
- Story ID backfill script (`scripts/backfill_story_ids.py`)
- Ground truth dataset with Shortcut story mappings (`data/story_id_ground_truth.json`)
- Training set analysis script (`scripts/analyze_training_set.py`)
- Equivalence-based evaluation scripts (`scripts/evaluate_with_equivalence.py`, `scripts/evaluate_iteration_2.py`)
- Comprehensive analysis documentation:
  - `prompts/classification_improvement_report_2026-01-08.md` - Final report (100% accuracy)
  - `prompts/human_grouping_analysis.md` - Human grouping pattern analysis
  - `prompts/baseline_evaluation.md` - Baseline results (41.7%)
  - `prompts/iteration_1_results.md` - First iteration (83.3%)
  - `prompts/improvements_changelog.md` - Change tracking
  - `prompts/data_summary.md` - Dataset statistics
- Database migration for story_id tracking (`src/db/migrations/002_add_story_id.sql`)

**Two-Stage Classification System - Phase 2 Database Integration Complete (2026-01-07)**:

- Database migration for two-stage classification fields (`src/db/migrations/001_add_two_stage_classification.sql`)
  - Stage 1 classification fields (type, confidence, routing_priority, urgency, auto_response_eligible, routing_team)
  - Stage 2 classification fields (type, confidence, classification_changed, disambiguation_level, reasoning)
  - Support context tracking (has_support_response, support_response_count)
  - Resolution detection (resolution_action, resolution_detected)
  - JSONB support_insights column for flexible data extraction
  - Indexes for common query patterns
- Classification storage module (`src/db/classification_storage.py`)
  - `store_classification_result()` - Stores complete two-stage classification with UPSERT
  - `get_classification_stats()` - Aggregated statistics (confidence distribution, classification changes, top types)
  - Context manager pattern for safe database connections
- End-to-end integration pipeline (`src/two_stage_pipeline.py`)
  - Fetches quality conversations from Intercom with date filtering
  - Runs two-stage classification on each conversation
  - Extracts support messages from conversation parts
  - Detects resolution signals in support responses
  - Stores all results in PostgreSQL database
  - CLI interface with --days, --max, --dry-run options
- Pydantic model updates (`src/db/models.py`)
  - ConversationType, Confidence, RoutingPriority, Urgency, DisambiguationLevel types
  - Extended Conversation model with all two-stage fields
- Live integration test: 3 conversations, 100% high confidence, 33% classification improvement rate

**Two-Stage Classification System - Phase 1 Complete (2026-01-07)**:

- Stage 1 Fast Routing Classifier (`src/classifier_stage1.py`)
  - OpenAI gpt-4o-mini integration with temperature 0.3
  - 8 conversation types for immediate routing
  - URL context hints from vocabulary
  - Auto-response eligibility detection
  - Team routing recommendations
  - 100% high confidence on test data
- Stage 2 Refined Analysis Classifier (`src/classifier_stage2.py`)
  - OpenAI gpt-4o-mini integration with temperature 0.1
  - Full conversation context (customer + support messages)
  - Disambiguation tracking (what customer said vs. what support revealed)
  - Support insights extraction (root cause, solution type, products/features)
  - Classification change detection and reasoning
  - Resolution signal integration
  - 100% high confidence on conversations with support
- Classification orchestration (`src/classification_manager.py`)
- Resolution pattern detection (`src/resolution_analyzer.py`) - 48 patterns across 6 categories
- Knowledge extraction pipeline (`src/knowledge_extractor.py`)
- Knowledge aggregation (`src/knowledge_aggregator.py`)
- Resolution patterns configuration (`config/resolution_patterns.json`)
- Test scripts for Phase 1 system:
  - `tools/demo_integrated_system.py` - Demo with 10 sample conversations
  - `tools/test_phase1_live.py` - Live test with real Intercom data
  - `tools/test_phase1_system.py` - Full system test (75 conversations)
- Complete Phase 1 results documentation (`docs/session/phase1-results.md`)
- Two-stage classification architecture documentation

**URL Context Integration (2026-01-07)**:

- URL context boosting for product area disambiguation
- `source_url` field in Conversation and IntercomConversation models
- URL pattern matching in ThemeVocabulary (27 patterns)
- URL context hints in LLM prompts
- Unit tests for URL matching (`tools/test_url_context.py`)
- Live data validation script (`tools/test_url_context_live.py`)
- Comprehensive documentation of URL context system

**Theme Vocabulary Expansion (2026-01-07)**:

- Vocabulary v2.9: Multi-Network Scheduler support (3 themes)
- Vocabulary v2.8: Extension UI, Legacy/Next Publisher split, SmartLoop (7 themes)
- Vocabulary v2.7: Context boosting + Product Dashboard themes
- Vocabulary v2.6: Customer keywords from Intercom data
- URL context mappings for three schedulers (Pin, Legacy, Multi-Network)
- Product area mapping for 20+ product areas
- 61 active themes with keywords and examples

**Validation & Testing (2026-01-07)**:

- Shortcut training data extraction (829 stories)
- LLM vs keyword validation framework
- `tools/validate_shortcut_data.py` - Validation against Shortcut labels
- `tools/validate_with_intercom.py` - Live Intercom data validation
- Streamlit theme labeler for manual review (`tools/theme_labeler.py`)
- VDD (Validation-Driven Development) workflow

**Tools & Scripts (2026-01-07)**:

- `tools/extract_customer_terminology.py` - Mine keywords from conversations
- `tools/extract_comment_quotes.py` - Extract Shortcut comment data
- `tools/enhance_vocabulary.py` - Automated vocabulary enhancement
- `tools/add_product_dashboard_themes.py` - Product Dashboard theme generation

**Session Documentation (2026-01-07)**:

- 9 detailed session documents tracking all work
- LLM validation analysis
- URL context integration & validation reports
- Vocabulary evolution tracking (v2.5 → v2.9)

**Previous Features**:

- Initial project setup
- Reference documentation (`reference/`)
- Starter `CLAUDE.md`
- Documentation scaffolding (`docs/`)
- Slash commands for workflow automation
- Subagents for specialized tasks
- Claudebase Developer Kit plugin
- Theme extraction system with product context
- Theme aggregation and canonicalization
- Shortcut integration with ticket templates
- Database schema (PostgreSQL)
- Intercom client with quality filtering
- Managed vocabulary system

### Changed

**Architecture (2026-01-07)**:

- Enhanced Intercom client to extract `source.url` from conversations
- Updated ThemeExtractor to use URL context for product area boosting
- Modified vocabulary system to load URL patterns and mappings
- Improved theme extraction prompt with URL context hints
- Enhanced validation framework with live data testing

**Data Models (2026-01-07)**:

- Added `source_url` field to Conversation model
- Added `source_url` field to IntercomConversation model
- Updated vocabulary to v2.9 with Multi-Network support

**Documentation (2026-01-07)**:

- Updated `docs/architecture.md` with URL context system
- Updated `docs/status.md` with validation results
- Created comprehensive session documentation

### Fixed

**Theme Canonicalization (Previous)**:

- Removed LIMIT 50 bug causing 83% singleton rate
- Fixed NULL component issue in vocabulary

**Vocabulary Coverage (2026-01-07)**:

- Added missing SmartLoop themes (100% accuracy improvement)
- Split Legacy vs Next Publisher for better disambiguation
- Added Multi-Network Scheduler (3rd scheduling system)
- Filled Extension UI coverage gaps

---

## Roadmap

See [PLAN.md](/PLAN.md) for the 5-phase implementation plan and [GitHub Issues](https://github.com/paulyokota/FeedForward/issues) for current backlog.
