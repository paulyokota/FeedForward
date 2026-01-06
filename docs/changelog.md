# Changelog

All notable changes to FeedForward will be documented in this file.

Format: [ISO Date] - Summary of changes

---

## [Unreleased]

### Added
- Initial project setup
- Reference documentation (`reference/`)
- Starter `CLAUDE.md`
- Documentation scaffolding (`docs/`)
- Slash commands for workflow automation:
  - `/update-docs` - Update all project docs after changes
  - `/session-end` - End-of-session cleanup and commit
  - `/create-issues` - Generate GitHub issues from specs
  - `/prompt-iteration` - Log prompt versions with metrics
- Subagents for specialized tasks:
  - `changelog` - Auto-format changelog entries
  - `retro` - Post-session retrospective
  - `prompt-tester` - Test prompts and measure accuracy
  - `schema-validator` - Validate schema consistency
  - `escalation-validator` - Validate escalation rules
- Environment configuration (`.env.example`) with tokens for GitHub, Intercom, Shortcut, OpenAI, Slack

### Changed
- N/A

### Fixed
- N/A

---

## Project Milestones

### Phase 1: Prototype
- [ ] Intercom API integration
- [ ] LLM classification prompt
- [ ] Accuracy baseline

### Phase 2: Batch Pipeline MVP
- [ ] Database schema
- [ ] Batch processing pipeline
- [ ] Basic reporting

### Phase 3: Product Tool Integration
- [ ] Escalation rules engine
- [ ] Jira/Productboard/Slack integrations

### Phase 4: Real-Time Workflows
- [ ] Webhook-driven processing
- [ ] Real-time alerts

### Phase 5: Optimization
- [ ] Cost optimization
- [ ] Quality monitoring
