# Changelog

All notable changes to FeedForward will be documented in this file.

Format: [ISO Date] - Summary of changes

---

## [Unreleased]

### Added

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
