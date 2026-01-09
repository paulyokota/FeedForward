# Changelog

All notable changes to FeedForward will be documented in this file.

Format: [ISO Date] - Summary of changes

---

## [Unreleased]

### Added

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
