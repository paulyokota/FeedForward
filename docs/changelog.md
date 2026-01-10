# Changelog

All notable changes to FeedForward will be documented in this file.

Format: [ISO Date] - Summary of changes

---

## [Unreleased]

### Added

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
