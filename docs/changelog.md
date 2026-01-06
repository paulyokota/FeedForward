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
  - `prompt-tester` - Test prompts and measure accuracy
  - `schema-validator` - Validate schema consistency
  - `escalation-validator` - Validate escalation rules
- Claudebase Developer Kit plugin (14 agents, 26 skills, 5 command groups)
- Environment configuration (`.env.example`) with tokens for GitHub, Intercom, Shortcut, OpenAI, Slack

### Changed
- N/A

### Fixed
- N/A

---

## Roadmap

See [PLAN.md](/PLAN.md) for the 5-phase implementation plan and [GitHub Issues](https://github.com/paulyokota/FeedForward/issues) for current backlog.
