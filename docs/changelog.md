# Changelog

All notable changes to FeedForward will be documented in this file.

Format: [ISO Date] - Summary of changes

---

## [Unreleased]

### Added

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
