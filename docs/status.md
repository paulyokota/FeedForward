# Project Status

## Current Phase

**Phase 1 (Two-Stage Classification): COMPLETE** ✅
**Phase 2 (Database Integration): COMPLETE** ✅
**Phase 4 (Theme Extraction): COMPLETE** ✅
**Classifier Improvement Project: COMPLETE** ✅
**Phase 5 (Ground Truth Validation): COMPLETE** ✅
**Story Grouping Architecture: COMPLETE** ✅
**Frontend Dashboard: COMPLETE** ✅
**Multi-Source Architecture: COMPLETE** ✅
**Story Tracking Web App: PHASE 2.5 COMPLETE** ✅
**Milestone 6 (Canonical Pipeline Consolidation): COMPLETE** ✅
**Theme Quality Architecture: IMPROVEMENTS 1 & 2 COMPLETE** ✅
**Pipeline Quality v1: COMPLETE** ✅
**Customer-Only Digest: COMPLETE** ✅
**Smart Digest (Issue #144): COMPLETE** ✅
**LLM Resolution Extraction (Issue #146): COMPLETE** ✅
**Async Pipeline Responsiveness (Issue #148): COMPLETE** ✅
**Test Suite Optimization (Issue #147): COMPLETE** ✅
**Story Evidence Quality (Issue #197): COMPLETE** ✅
**Implementation Head-Start Relevance (Issue #198): COMPLETE** ✅
**30-Day Recency Gate (Issue #200): COMPLETE** ✅
**Pipeline Checkpoint/Resumability (Issue #202): COMPLETE** ✅
**Streaming Batch Resume (Issue #209): COMPLETE** ✅
**Discovery Engine: PHASE 1 COMPLETE — FIRST REAL RUN SUCCESSFUL** ✅

## Latest: Second Real Run (Aero) + Quality Evaluation + Architecture Direction (2026-02-10)

**Second discovery run against external product repo (aero). Human review revealed two systemic pipeline issues.**

- Run ID: `2a9d5cb3-7477-4375-8854-86dceca4ae82` (aero product repo)
- Target repo support: `--target-repo ../aero --scope-dirs packages/ --doc-paths tmp/`
- Auto-pull with stash/restore, RepoSyncer service added
- ArtifactChain.tsx rewritten with structured views per stage (evidence chips, risk teasers, solution components)

**Quality evaluation findings (opportunities #1, #6):**

- Over-grouping: findings from unrelated areas merged into single broad opportunities
- Forced user-facing framing: internal engineering tasks shoehorned into product opportunity molds (e.g., proposing user feedback on internal event tracking)
- source_type mislabeling: research documents labeled as "intercom" in OpportunityPM evidence

**Architecture direction decided (3-way discussion: Paul, Claude, Codex):**

- Key thesis: pipeline over-constrains agents, forcing nonsensical conforming output
- Direction: descriptive schemas + adaptive routing (more agent freedom, not more guardrails)
- Filed #260 (surface-specificity constraint) and #261 (adaptive routing with descriptive schemas)

**Next steps tracked in GitHub Issues:**

- #260: Surface-specificity constraint (surgical prompt fix, do first)
- #261: Adaptive pipeline routing with descriptive schemas (fundamental architecture change)
- #226-231: Phase 2 issues (most blocked by #256, now resolved)

### Previous: First Real Run + Pipeline Hardening (2026-02-10)

**Discovery Engine Phase 1 validated against real data.**

First end-to-end run against 500+ Intercom conversations, PostHog analytics, codebase, and internal docs:

- Run ID: `6548f72d-553e-4a1e-9c4e-d93e70fe5807`
- 18 findings → 18 briefs → 18 solutions → 17 specs (1 infeasible) → 17 rankings → human_review
- ~43 min elapsed, estimated $1-2 (gpt-4o-mini)
- 5 attempts required — each uncovered LLM→Pydantic validation mismatches
- 642 discovery tests passing

Hardening fixes committed:

- Dict→string coercion for LLM fields that return structured dicts (~30% of the time)
- Per-solution error resilience (skip and warn instead of failing entire run)
- Empty evidence filtering in codebase and customer voice explorers
- Explorer merge now accepts checkpoint dicts (not raw ExplorerResult tuples)
- Standalone run script: `scripts/run_discovery.py`

**Completed this session:**

- #255: Shared coercion utility ✅ (PR #257)
- #256: DB persistence for discovery runs ✅ (PR #258)

### Previous: Phase 1 Pipeline Infrastructure (2026-02-09)

All implementable Phase 1 issues complete: #235, #221, #222, #223, #224, #225 (PRs #241-#246)

- 638 discovery tests passing
- E2E test exercises full Stage 0→5 pipeline with checkpoint validation
- Issues #226-#231 deferred to Phase 2

### Previous: Research Explorer — Stage 0 Internal Doc Analysis (2026-02-08)

**Issue #218 COMPLETE** ✅ — Research Explorer Agent (PR #239)

Fourth and final Stage 0 explorer. Reads internal markdown docs and surfaces latent product signals:

- ResearchReader data access: filesystem walk of docs/ and reference/, bucket-based classification
- Bucket-based batching (strategy, architecture, process, session_notes, reference, general)
- Two-pass LLM strategy (per-bucket batch analysis + cross-bucket synthesis)
- Evidence via doc paths → EvidencePointer(RESEARCH, path), empty evidence filtering
- 387 discovery tests passing (42 new: 35 unit + 7 integration)

**All Stage 0 explorers now complete**: Customer Voice (#215), Codebase (#217), Analytics (#216), Research (#218)

### Previous: Codebase Explorer (2026-02-08)

**Issue #217 COMPLETE** ✅ — Codebase Explorer Agent (PR #237)

- CodebaseReader: git log + disk read, scoped to src/, extension allowlist
- Two-pass LLM strategy matching CustomerVoiceExplorer pattern
- 297 discovery tests passing (39 new: 33 unit + 6 integration)

### Previous: Opportunity PM Agent (2026-02-08)

**Issue #219 COMPLETE** ✅ — Opportunity PM Agent (PR #236)

Stage 1 agent that synthesizes explorer findings into problem-focused OpportunityBriefs:

- Single-pass LLM strategy: explorer findings are structured JSON (3-10 findings), one call produces all briefs
- OpportunityFramingCheckpoint wrapper model for multi-brief submission (single checkpoint per stage)
- Evidence traceability: conversation IDs validated against explorer findings, unknown IDs filtered with warnings
- Counterfactual framing enforced at prompt level (no solution direction)
- Re-query support for follow-up questions to explorers (pure LLM function, orchestrator handles events)
- 258 discovery tests passing (32 new: 25 unit + 7 integration)
- Codex-reviewed via Agenterminal (2HMK234: evidence traceability fix, REVIEW_APPROVED)

**Next**: Issue #65 (P1 SQL injection fix) or next Discovery Engine stage

---

## Previous: Customer Voice Explorer — Capability Thesis Test (2026-02-08)

**Issue #215 COMPLETE** ✅ — Customer Voice Explorer Agent (capability thesis PASS)

First explorer agent and primary thesis test for the Discovery Engine:

- Two-pass LLM strategy: per-batch analysis (10 batches of 20) + synthesis pass
- Data access layer reads raw conversations from Postgres (COALESCE/NULLIF fallback)
- ExplorerCheckpoint artifact model validates EXPLORATION stage output
- Deterministic truncation: first message + last 3 + metadata, 2000 char budget
- Per-batch error isolation (one LLM failure doesn't abort the run)
- Comparison script for side-by-side analysis vs pipeline themes
- Functional test: 200 real conversations, 5 findings, 1 novel pattern, ~$0.02 cost
- 226 discovery tests passing (65 new for #215)
- Codex-reviewed via Agenterminal (3QEL461: 2 rounds, REVIEW_APPROVED)

**Thesis result**: Explorer operates at strategic abstraction level (product area patterns) vs pipeline's tactical level (specific bugs/features). Complementary, not competitive. 1 novel cross-cutting pattern surfaced.

---

## Previous (2): Discovery Engine Foundation (2026-02-08)

**Issue #213 COMPLETE** ✅ — Foundation: state machine, artifact contracts, run metadata (PR #232)
**Issue #214 COMPLETE** ✅ — Conversation protocol for agent dialogue (PR #233)

Infrastructure now in place:

- Postgres state machine with 6-stage pipeline, transition matrices, send-back support
- 4 Pydantic artifact contracts (EvidencePointer, OpportunityBrief, SolutionBrief, TechnicalSpec)
- Conversation protocol: JSON envelope events, Agenterminal transport, per-stage artifact validation
- ConversationService: create, post, read, checkpoint, complete with ownership guards
- 143 discovery engine tests (all passing)
- Codex-reviewed via Agenterminal (DISCOVERYENGREVIEW)

---

## Previous: Discovery Engine Architecture (2026-02-07)

**Issues #212-#231** — AI-Orchestrated Project Discovery Engine

Architecture designed and project set up for implementation:

- 6-stage pipeline: Exploration → Opportunity Framing → Solution + Validation → Feasibility + Risk → Prioritization → Human Review
- 10 specialized Claude Code agents (4 domain explorers + 6 synthesis/design/scoping agents)
- Claude Code instances via Agent SDK as the agent engine (not LangChain)
- Conversation protocol for agent dialogue, Postgres state machine for orchestration
- 9 hard requirements across 2 phases
- 19 issues across 2 milestones in GitHub Project: https://github.com/users/paulyokota/projects/2
- Phase 1 (8-10 weeks): Prove capability thesis — do agents discover things humans miss?
- Phase 2 (conditional): Add operational maturity — cost controls, evidence validation, variance bounding
- Key decision gates: after Customer Voice Explorer (#215), after end-to-end test (#225)

---

## Previous: Streaming Batch Resume (2026-02-01)

**Issue #209 COMPLETE** - Streaming Batch Resume for Intercom Backfill

- PR #210 merged: Transform pipeline from fetch-all to streaming batch architecture
- Key guarantees:
  - Max rework on crash = 1 batch (~50 conversations)
  - Memory bounded to 1 batch
  - Cursor resume skips already-fetched pages
- Feature-flagged: `PIPELINE_STREAMING_BATCH=true` (default: off)
- Configurable batch size: `PIPELINE_STREAMING_BATCH_SIZE` (10-500, default 50)
- Implementation:
  - `_run_streaming_batch_pipeline_async`: Main streaming loop
  - `_process_streaming_batch`: Per-batch processing (detail fetch → recovery → classify → store)
  - Checkpoint saved AFTER storage (never before)
  - Stop checks only at batch boundaries
- Codex review: 3 rounds, 2 critical fixes (cumulative stats, max_conversations enforcement)
- 15 new tests added, all 37 checkpoint tests pass
- Runbook added: `docs/runbook/streaming-batch-pipeline.md`
- Tested: dry run (10 convs) + full run (15 convs → 6 themes) ✅

---

## Previous: Pipeline Checkpoint/Resumability (2026-02-01)

**Issue #202 COMPLETE** - Pipeline Checkpoint/Resumability for Long Backfills

- PR #204 merged: Checkpoint persistence + resume capability for classification phase
- Key features:
  - JSONB `checkpoint` column in `pipeline_runs` for progress tracking
  - `resume=true` + optional `resume_run_id` for explicit cross-day resume
  - Skip classification for already-stored conversations (preserves 30-60 min work)
  - Safety: requires `resume_run_id` if multiple resumable runs exist
  - Monotonic counters: stats include totals (new + previously processed)
- Resume behavior documented: re-fetch all + skip classification for stored IDs
- New files: `docs/backfill-runbook.md`, migration 022, 22 new tests
- 5-personality review: CONVERGED after 5 rounds with Codex

---

## Previous: 30-Day Recency Gate (2026-02-01)

**Issue #200 COMPLETE** - 30-Day Recency Gate for Story Creation

- PR #203 merged: Groups must have at least one conversation from the last 30 days
- All-old groups route to orphan accumulation with reason "No recent conversations (last 30 days)"
- Gate covers: signature groups, hybrid clusters, PM keep-together, PM split sub-groups, orphan graduation
- No high-severity bypass - recency is about staleness, not urgency
- Codex review: 2 issues fixed (RealDictCursor access, N+1 query elimination)
- 29 new tests added, all 159 story creation tests pass
- 5-personality review: CONVERGED

---

## Previous: Implementation Head-Start Relevance (2026-01-31)

**Issue #198 FIXED** - Improve Implementation Head-Start Relevance

- PR #201 merged: High-signal term detection + relevance gating
- 4 phases implemented:
  1. High-signal term detection (product_area/component/error terms prioritized)
  2. Implementation_context wired to all 4 story creation paths
  3. Relevance gating in provider (threshold: high_signal >= 1 OR diversity >= 2)
  4. Audit trail via score_metadata.relevance_metrics
- Codex review: 2 Medium issues fixed (source_fields consistency, low-confidence parity)
- 44 new tests added, all 211 modified-file tests pass
- 5-personality review: CONVERGED in 2 rounds

---

## Previous: Story Evidence Quality Fixed (2026-01-31)

**Issue #197 FIXED** - Raise Story Evidence Quality

- PR #199 merged: Evidence creation during orphan graduation + excerpt_count field
- Root cause: 78.8% of stories had `evidence_count=0` despite 100% theme extraction
- Three fixes: evidence bundle creation, theme_signature population, new `excerpt_count` field
- Frontend: `EvidenceBadge` component for low-evidence warnings
- Migration 021 applied: `excerpt_count` column with backfill
- Post-merge verification: **100%** of stories now have `excerpt_count > 0`
- 5-personality review: CONVERGED in 3 rounds

---

## Previous: Pipeline API Bug Fixed (2026-01-31)

**Issue #189 FIXED** - Pipeline API Environment Variable Bug

- PR #191 merged: Load env vars explicitly in pipeline background task
- Root cause: `anyio.to_thread.run_sync` worker didn't have `INTERCOM_ACCESS_TOKEN`
- Fix: Added `load_dotenv()` with resolved absolute path + fail-fast check
- Created `_finalize_failed_run` helper for consistent error handling
- 5-personality review: CONVERGED in 2 rounds
- Functional test: Run 111 completed successfully (fetched=5)

**Issue #180 COMPLETE** - Hybrid Implementation Context

- PR #186 merged: Adds AI-synthesized implementation guidance to stories
- Migration 019 applied: `implementation_context` JSONB column on stories table
- Vector retrieval from Coda pages/themes + OpenAI synthesis

---

## Previous: BrokenPipe Pipeline Fix (2026-01-30)

**Issue #185 fixed** - Pipeline no longer crashes when uvicorn reloads during execution

Root cause: `print()` statements fail with `BrokenPipeError` when background task loses stdout. Solution: Replace with logging using `SafeStreamHandler` that gracefully ignores broken pipes.

| Metric                  | Value        |
| ----------------------- | ------------ |
| print() calls converted | 93 (83 + 10) |
| New tests added         | 9            |
| Files modified          | 5            |

---

## Previous: Pre-existing Test Fixes & Embedding Migration (2026-01-30)

**PR #183 merged** - Fixed 16 pre-existing test failures
**PR #184 merged** - Embedding model alignment between search and pipeline

### Test Fixes (PR #183)

After Issue #178 changed `dual_format_enabled` default to `True`, 16 tests started failing:

| File                                    | Fix Applied                                                |
| --------------------------------------- | ---------------------------------------------------------- |
| `test_domain_classifier_integration.py` | Skip when `REPO_BASE_PATH` unavailable                     |
| `test_issue_148_event_loop.py`          | Use real `QualityCheckResult` dataclass (3 occurrences)    |
| `test_phase5_integration.py`            | Add `dual_format_enabled=False` + `create_or_get` mock     |
| `test_pipeline_canonical_flow.py`       | Add `dual_format_enabled=False` to 7 tests + fixture mocks |
| `test_story_creation_service.py`        | Update default behavior test to expect `True`              |

**5-personality review**: All 5 approved in Round 1

### Embedding Migration (PR #184)

Fixed Issue #181 where `UnifiedSearchService` and `EmbeddingPipeline` could use different embedding models. After merge, ran reindex with `force=true`:

| Metric           | Before                    | After                                |
| ---------------- | ------------------------- | ------------------------------------ |
| Total embeddings | 10                        | **1,786**                            |
| Coda pages       | 0                         | 1,234                                |
| Intercom         | 5                         | 547                                  |
| Model alignment  | ❌ Potentially mismatched | ✅ Both use `text-embedding-3-small` |

---

## Previous: Issue #176 Fix - Duplicate Orphan Signature Cascade (2026-01-30)

**Issue #176 CLOSED** - PR #177 merged

### Problem

Run #96 failed catastrophically: 593 themes extracted, 0 stories/orphans persisted. When an orphan graduated to a story, its signature row remained in `story_orphans` (UNIQUE constraint). New conversations with the same signature tried INSERT → duplicate key violation → transaction abort cascaded to all subsequent clusters.

### Solution

Made orphan creation idempotent and added post-graduation routing:

| Component                                  | Change                                                            |
| ------------------------------------------ | ----------------------------------------------------------------- |
| `OrphanService.create_or_get()`            | `ON CONFLICT DO NOTHING` + same-cursor re-read                    |
| `OrphanService.get_by_signature()`         | Returns ANY orphan (active or graduated)                          |
| `OrphanMatcher._add_to_graduated_story()`  | Routes post-graduation conversations to story via EvidenceService |
| `OrphanIntegrationResult.stories_appended` | New metric for post-graduation additions                          |

**5-personality review converged** after 2 rounds.

### Run #96 Recovery

Used manual endpoint `POST /api/pipeline/96/create-stories` to resume story creation:

| Metric          | Before Fix | After Fix |
| --------------- | ---------- | --------- |
| stories_created | 0          | **35**    |
| orphans_created | 0          | **376**   |

**Files changed:**

- `src/story_tracking/services/orphan_service.py` - idempotent creation
- `src/orphan_matcher.py` - graduated flow routing
- `src/story_tracking/services/orphan_integration.py` - EvidenceService injection
- `src/story_tracking/services/story_creation_service.py` - parallel graduated handling
- `tests/test_orphan_service.py`, `tests/test_orphan_matcher.py`, `tests/test_orphan_integration.py` - new tests

---

## Previous: Evidence Bundle Improvements (2026-01-30)

**Issues #156, #157, #158** - Milestone 10 Stream A (PR #174 - merged)

### What Changed

Implemented signal-based evidence ranking, diagnostic summary preference, and evidence metadata completeness:

| Issue | Feature                                               | Status      |
| ----- | ----------------------------------------------------- | ----------- |
| #156  | Diagnostic summary + key_excerpts over raw excerpt    | ✅ Complete |
| #157  | Evidence metadata (email, intercom_url, org/user IDs) | ✅ Complete |
| #158  | Signal-based ranking (replaces first-N selection)     | ✅ Complete |

**Key implementation details:**

- Ranking factors: key_excerpts > diagnostic_summary > error patterns > symptoms > text length
- Jaccard similarity (0.65 threshold) dedupes key_excerpts against diagnostic_summary
- Pre-compiled regex patterns at module level for performance
- Total excerpt cap prevents unbounded memory growth

**5-personality review converged** after 2 rounds with fixes:

- Fixed inverted tie-breaker sort order
- Fixed HTTP status regex (was matching any 3-digit number)
- Fixed no-op test (`ids == ids`)
- Added explanatory comments for magic numbers

**Files changed:**

- `src/story_tracking/services/story_creation_service.py` - main implementation
- `src/api/routers/pipeline.py` - pipeline query for metadata
- `src/story_tracking/models/__init__.py` - EvidenceExcerpt model
- `src/story_tracking/services/evidence_service.py` - JSON serialization
- `tests/test_story_creation_service.py` - 36 new tests
- `tests/test_evidence_pipeline_integration.py` - new integration test file

---

## Previous: Test Suite Optimization (2026-01-30)

**Issue #147 CLOSED** - Pytest markers for fast/slow test split

### What Changed

Added pytest markers to split the test suite for faster iteration:

| Command                 | Tests | Time             |
| ----------------------- | ----- | ---------------- |
| `pytest -m "not slow"`  | 1,196 | ~5 min           |
| `pytest -m slow`        | 204   | integration only |
| `pytest -m integration` | 204   | same as slow     |

**Files changed:**

- Created `pytest.ini` with marker registration
- Marked 10 integration test files as `slow` + `integration`
- Updated `CLAUDE.md` with new test commands

**Also fixed 3 pre-existing test failures:**

- `test_run_scoping.py` - regex outdated after Issue #148 async refactor
- `test_context_gaps_endpoint.py` - import path mismatch for dependency override
- `test_story_formatter.py` - env var vs module variable caching issue

---

## Previous: Vocabulary Enhancement & Race Condition Fix (2026-01-30)

**Issue #152 CLOSED** - Race condition in parallel theme extraction fixed
**Issue #153 CLOSED** - Systematic vocabulary enhancement complete

### Issue #152: Race Condition Fix

Serialized the canonicalization critical section to prevent concurrent extractions from creating near-duplicate signatures.

**Changes:**

- Wrapped `canonicalize_signature()` + `add_session_signature()` in `_session_lock`
- Changed `threading.Lock()` to `threading.RLock()` for reentrant acquisition
- Added 4 deterministic concurrency tests
- No performance degradation (48.33s vs 50.42s baseline for 20 extractions)

**Validation:** Next pipeline run should show no >90% similar signature pairs.

### Issue #153: Vocabulary Enhancement

Added data-driven term distinctions to help LLM disambiguate similar concepts during theme extraction.

**Changes:**

- Added `term_distinctions` section to `config/theme_vocabulary.json` with 11 term pairs across 3 categories:
  - **similar_ux** (5 pairs): title/description, account/pinterest_account, pin/board, etc.
  - **different_model** (3 pairs): scheduled_pin/draft, post/draft, post/scheduled_pin
  - **name_confusion** (3 pairs): pin/turbo_pin, pin/smartpin, pinterest_account/instagram_account
- Integrated term distinctions into extraction prompt via `vocabulary.format_term_distinctions()`
- Functional tests: 8/8 pass (100%)

**Methodology:** Two-dimensional analysis combining code path validation (SAME_FIX test) with user symptom clustering (Jaccard similarity, exclusivity ratios). Thresholds calibrated to percentiles from actual data distribution.

---

## Previous: Race Condition Discovery (2026-01-28)

**Issue #151 Opened** - Parallel extraction creates duplicate signatures (superseded by #152)

### Discovery

While salvaging pipeline run 95, discovered that parallel theme extraction (introduced in Issue #148) has a race condition. Two concurrent threads processing similar issues can both create "new" signatures before either registers theirs.

### Evidence

Run 95 (30-day pipeline) results:
| Metric | Count |
|--------|-------|
| Conversations classified | 1440 |
| Themes extracted | 543 |
| Stories created | 15 |
| Orphans created | 402 |

Signature similarity analysis found pairs like:

- `multi_network_scheduling_failure` vs `multinetwork_scheduling_failure` (98% similar)
- `pinterest_connection_failure` vs `pinterest_connection_issue` (89% similar)

### Bug Fixes (Same Session)

Also fixed 3 bugs that blocked run 95:

- `context_usage_logs` INSERT missing `conversation_id`
- Theme storage type mismatches (`symptoms`, `quality_score`, `quality_details`)
- Missing unique constraint on `context_usage_logs.theme_id`

---

## Previous: Issue #148 Async Pipeline Responsiveness (2026-01-28)

**Issue #148 Closed** - Eliminated 40-80+ minute server unresponsiveness during pipeline runs

### Problem Solved

FastAPI server became completely unresponsive during pipeline runs because `BackgroundTasks.add_task()` executed sync functions in the event loop thread, blocking all HTTP requests.

### What Shipped

| Component             | Change                                                           | Impact                           |
| --------------------- | ---------------------------------------------------------------- | -------------------------------- |
| `pipeline.py`         | Wrapped pipeline in `anyio.to_thread.run_sync()` + parallel task | True background execution        |
| `pipeline.py`         | Semaphore-controlled parallel theme extraction (up to 20)        | 10-20x faster theme extraction   |
| `theme_extractor.py`  | New `extract_async()` using `asyncio.to_thread`                  | Non-blocking LLM calls           |
| `theme_extractor.py`  | `threading.Lock` for `_session_signatures` access                | Thread-safe signature cache      |
| `schemas/pipeline.py` | Concurrency validation (max 20)                                  | OpenAI rate limit compliance     |
| `pipeline.py`         | `_MAX_ACTIVE_RUNS=100` limit                                     | Prevents unbounded memory growth |
| Legacy cleanup        | Deleted 258-line `_process_themes_for_stories` function          | Removed 2-month-old dead code    |

### Review Process

5-personality review converged in 3 rounds:

- **Round 1**: 5 HIGH severity issues found (thread safety, silent failures, resource limits, dead code)
- **Round 2**: 1 incomplete fix found (orphaned property after dead code removal)
- **Round 3**: All 5 reviewers APPROVE, 0 new issues → CONVERGED

### Tests

- 25 new unit and integration tests for async behavior
- Coverage: thread safety, error propagation, concurrency limits, cancellation

### Technical Details

**Key insight**: `BackgroundTasks.add_task()` with sync functions doesn't create true background tasks - it runs them in the event loop thread, blocking all async operations.

**Solution pattern**:

```python
# Wrong (blocks event loop):
background_tasks.add_task(sync_function)

# Correct (true background):
background_tasks.add_task(anyio.to_thread.run_sync, sync_function)
```

**Concurrency**: Semaphore limits parallel theme extraction to 20 (OpenAI's per-minute rate limit), preventing 429 errors while maximizing throughput.

---

## Previous: Issue #146 LLM Resolution Extraction (2026-01-28)

**Issue #146 Closed** - Replaced regex-based resolution extraction with LLM extraction

### What Shipped

| Change    | Description                                                                                                 |
| --------- | ----------------------------------------------------------------------------------------------------------- |
| Deleted   | `ResolutionAnalyzer`, `KnowledgeExtractor`, `resolution_patterns.json` (8-14% coverage)                     |
| Added     | 4 resolution fields to Theme: `resolution_action`, `root_cause`, `solution_provided`, `resolution_category` |
| Wired     | Fields flow through PM Review → Story Creation                                                              |
| Migration | 018: Added columns to `themes` table                                                                        |
| Tests     | 39 integration tests (including DB persistence regression guards)                                           |

### Review Process

5-personality review converged in 2 rounds:

- **Round 1**: Reginald/Quinn found critical bug (resolution fields not persisted to DB)
- **Fix**: Added fields to INSERT statements in `pipeline.py` and `theme_tracker.py`
- **Round 2**: All 5 reviewers APPROVE, 0 new issues

### Database Cleaned

Prior to running pipeline with new extraction, all analysis data was wiped:

- Themes: 529 → 0
- Stories: 23 → 0
- Conversations: 1424 preserved

### Follow-up Items (Non-blocking)

- M1: Consolidate resolution enum definitions
- M2: Add docstrings to resolution fields
- S1/S2: Consider length limits and prompt injection hardening (LOW severity)
- Functional test recommended before production deployment

---

## Previous: Smart Digest Validation & Doc Cleanup (2026-01-28 evening)

**Pipeline Run 93** - First clean test run after Issue #144 merge

### Test Results

| Metric        | Value                                                  |
| ------------- | ------------------------------------------------------ |
| Conversations | 428 classified → 129 processed (actionable types only) |
| Themes        | 127 extracted                                          |
| Stories       | 0 (insufficient volume per theme)                      |
| Orphans       | 110                                                    |
| Duration      | 31 minutes                                             |

### Smart Digest Validation: ✅ WORKING

Confirmed all #144 features are functioning:

- `full_conversation` stored in `support_insights` JSONB (365-4447 chars per conversation)
- `diagnostic_summary` populated with rich contextual summaries
- `key_excerpts` populated with structured quotes and relevance annotations
- Theme extraction using full conversation context (slower but richer)

No stories created because max conversations per theme was 3 (need more volume). PM Review only runs during story creation, so confidence comparison not yet measurable.

### Documentation Cleanup

Post-#144 doc audit identified stale references. Fixed:

- **CLAUDE.md**: Added "Smart Digest (Issue #144)" section with field locations
- **docs/architecture.md**: Added Smart Digest Flow diagram, updated schema section with new fields
- **docs/status.md**: Added terminology table clarifying `full_conversation` vs `customer_digest` vs `source_body[:500]`

Integration testing gate was already properly linked (not orphaned as initially thought).

---

## Previous: Smart Digest Complete (2026-01-28)

**Issue #144 Closed** - Full implementation of LLM-powered conversation summarization

### What Shipped (Two Merges)

**Phase 1+2: Theme Extraction with Smart Digest**

- Theme extraction now receives `full_conversation` text (not just heuristic digest)
- New output fields: `diagnostic_summary`, `key_excerpts`, `context_used`, `context_gaps`
- `diagnostic_summary`: LLM interpretation of the issue
- `key_excerpts`: Verbatim customer quotes preserving original language

**Phase 3+4: PM Review Integration + Context Gap Analytics**

- PM Review now uses `diagnostic_summary` instead of truncated `source_body[:500]`
- New CLI command for context gap analysis
- API endpoint for context gap metrics

### Conversation Context Terminology

The pipeline evolved through three approaches to conversation context:

| Term                 | Source            | Description                                            |
| -------------------- | ----------------- | ------------------------------------------------------ |
| `source_body[:500]`  | Legacy (pre-#139) | Truncated raw conversation text (first 500 chars)      |
| `customer_digest`    | Issue #139        | Heuristic-extracted customer messages (~800 chars max) |
| `full_conversation`  | Issue #144        | Complete conversation text passed to theme extraction  |
| `diagnostic_summary` | Issue #144 output | LLM-generated developer-focused summary of the issue   |
| `key_excerpts`       | Issue #144 output | Verbatim customer quotes with relevance explanations   |

**Current state**: Theme extraction receives `full_conversation` and outputs `diagnostic_summary` + `key_excerpts`. PM Review uses `diagnostic_summary` instead of `source_body[:500]`.

### Process Learnings Documented

Three process improvements added to playbook from Issue #144 post-mortem:

1. **Integration Testing Gate** (`docs/process-playbook/gates/integration-testing-gate.md`)
   - New gate: Features with cross-component data flow require integration tests
   - Unit tests in isolation missed that `full_conversation` was never wired through pipeline

2. **Functional Test Timing** (`docs/process-playbook/gates/functional-testing-gate.md`)
   - Added recommendation: Consider functional testing BEFORE code review for pipeline features
   - Earlier testing would have caught dead code issue sooner

3. **Marcus Anti-Pattern** (`.claude/skills/marcus-backend/IDENTITY.md`)
   - Documented "Silently Disabling Features" anti-pattern
   - Hardening rules: TRACE data origin, ASK if constraint is real, FLAG don't fix silently

4. **Architect Constraint Verification** (`.claude/skills/priya-architecture/SKILL.md`)
   - Added checklist item: "Verify constraints are real"
   - When dev says "we don't have X data", architect should verify if it's real constraint or implementation gap

---

## Previous: Smart Digest Investigation (2026-01-28)

**Issue #144 Filed** - Comprehensive plan for LLM-powered conversation summarization

### Investigation Summary

Deep-dive into PM Review excerpt quality revealed multiple gaps in how conversation context flows through the pipeline:

1. **PM Review receives truncated source_body** - `source_body[:500]` instead of the richer `customer_digest` that exists in `support_insights`

2. **A/B testing showed clear improvement** - Running PM Review with digest vs source_body increased confidence from 0.4 → 0.8 on real conversation groups

3. **Theme extraction also limited** - Discovered theme extraction only sees heuristic-selected digest, not full conversation

4. **Product context heavily truncated** - 68K chars of disambiguation docs → 10K chars passed to LLM

### Key Decisions Made

- **Unified LLM call**: Theme extraction + smart digest creation in one call seeing full conversation
- **Preserve raw evidence**: Output both `diagnostic_summary` (interpretation) AND `key_excerpts` (verbatim quotes)
- **Separate optimized context doc**: New `pipeline-disambiguation.md` for LLM consumption, keep canonical docs static
- **Context usage instrumentation**: Log `context_used` and `context_gaps` to iteratively improve disambiguation guidance

---

## Previous: Customer-Digest Functional Test & Clustering Quality Discovery (2026-01-27)

**Issue #139 Functional Test Complete** - 30-day pipeline run validated customer_digest implementation

### Functional Test Results (Run 91)

| Metric                    | Value            |
| ------------------------- | ---------------- |
| Conversations             | 1,270            |
| Customer digest populated | 100% (1270/1270) |
| Themes                    | 516              |
| Stories                   | 21               |
| Orphans                   | 348              |

### Quality Investigation

While validating customer_digest, discovered **story grouping quality regression**. Top story "Fix board selection saving issues in pin scheduler" (10 conversations) contained 7 distinct issues that should have been separate stories.

**Root cause traced**: Hybrid clustering uses `(action_type, direction)` for sub-grouping. All 10 conversations had identical facets (`bug_report`, `deficit`) despite having different `issue_signature` values from theme extraction.

**Key finding**: Facet taxonomy is too coarse - doesn't distinguish between:

- Board selection bugs
- Multi-account scheduling bugs
- Bulk delete requests
- Calendar navigation issues

### Options Evaluated

Considered adding `issue_signature` to clustering, but signatures not normalized enough (261 unique signatures for 516 themes, inconsistent naming like `multi_network_scheduling_failure` vs `multinetwork_scheduling_failure`).

**Pressure test of `product_area` + `component`**:

- Helps in 4/5 top stories
- Risk: Story 4 (coherent group) would be over-split
- `product_area` alone may be safer first step

### New Issue Filed

**#141** - Incremental theme count updates during theme extraction (monitoring visibility)

### Decision

User wants to sit with clustering findings before making changes. Potential #123 reopen with expanded scope pending.

---

## Previous: Customer-Only Digest for Embeddings (2026-01-26)

**Issue #139 Complete** - PR #140 merged after 5-personality review convergence

### What Was Shipped

New digest extraction system that isolates customer voice from support responses for better semantic matching:

1. **digest_extractor.py** - Fast heuristic-based message scoring and digest building:
   - Extracts customer messages from conversation_parts
   - Scores messages by specificity (question words, length, code/URLs, punctuation)
   - Builds 800-char digest: first message + most specific additional message
   - Security hardening: bounded regex patterns, MAX_INPUT_SIZE limits

2. **Pipeline integration** - `customer_digest` stored in support_insights JSONB column

3. **3-tier fallback hierarchy** - Applied consistently across all services:
   - embedding_service.py (vector embeddings)
   - facet_service.py (facet extraction)
   - theme_extractor.py (theme extraction with 50-char minimum)

### Test Coverage

- **73 total tests** (68 new digest tests + 5 embedding priority tests)
- Security coverage: ReDoS protection, memory limits, input validation

### Code Review

- **Round 1**: 35 issues found across 5 reviewers
  - Reginald: Security (ReDoS, memory limits), edge cases, constants
  - Sanjay: Input validation, error handling, scoring brittleness
  - Quinn: Output quality, separator optimization, edge case smoothing
  - Dmitri: Complexity, magic numbers, over-engineering
  - Maya: Documentation, naming, test coverage
- **Round 2**: CONVERGED (all 5 reviewers APPROVED)
  - 35/35 issues resolved
  - Quinn's remaining medium-priority items acknowledged as future improvements
  - All reviewers confidence 90-95%

### Files Changed

- `src/digest_extractor.py` (+300 new)
- `src/classification_pipeline.py` (+3)
- `src/embedding_service.py` (+14/-2)
- `src/facet_service.py` (+14/-2)
- `src/theme_extractor.py` (+14/-2)
- `tests/test_digest_extractor.py` (+68 new)
- `tests/test_embedding_service.py` (+5)

---

## Previous: Pipeline Quality v1 Validation Complete (2026-01-26)

**Issue #129 Complete** - Functional validation passed, Phase 3 issues closed

### Run 88 Results (30-day window)

| Metric        | Value                   |
| ------------- | ----------------------- |
| Conversations | 1,264                   |
| Themes        | 507                     |
| Stories       | 21                      |
| Orphans       | 341                     |
| PM Reviews    | 42 (40 splits, 2 keeps) |

### Quality Evaluation

- **Evidence Grouping**: PASS - No mixed root causes, PM review 95% split rate
- **Implementation Details**: PASS - 21/21 stories have code_context
- **Metadata Quality**: PASS - 19/21 descriptive titles
- **Orphan Quality**: PASS - Rich theme_data

### Phase 3 Decisions

All closed as not needed:

- **#123** (Clustering Semantics) - PM review handles edge cases
- **#125** (Classification Persistence) - Orphan quality sufficient
- **#127** (Stable Cluster IDs) - No cross-run aggregation needed

**Key Finding**: Option B (simple clustering + PM review) is sufficient. No hard constraints needed.

---

## Previous: Code Context Precision Improvements (2026-01-26)

**Issue #134 Complete** - PR #137 merged after 5-personality review convergence

### What Was Shipped

Implemented 6 improvements to make code_context reliably surface relevant files/snippets:

1. **Noise exclusion patterns** - Filters build/, dist/, node_modules/, \*.min.js, compiled assets
2. **Stop-word filtering** - Removes generic terms (user, data, issue, error) from keyword matching
3. **Deterministic file ranking** - PATH_PRIORITY_TIERS (src/ > api/ > lib/ > tests/) applied before 100-file limit
4. **Component preservation** - New `theme_component` parameter prevents category from overwriting specific component
5. **Low-confidence detection** - `_is_low_confidence_result()` explicitly signals insufficient quality
6. **Consolidated ranking logic** - Removed duplicate get_path_priority() method

### Test Coverage

- **98 total tests** (24 new tests added)
- New test coverage:
  - Noise filtering (build/dist/node_modules exclusion)
  - Stop-word filtering (generic term removal)
  - Path priority tiers (deterministic ranking)
  - Low-confidence detection (weak vs strong matches)
  - Component parameter preservation

### Code Review

- **Round 1**: 5 issues found
  - Reginald/Dmitri: Duplicate ranking logic (two systems doing same thing differently)
  - Maya: Magic number without constant, log level misuse, missing determinism test, poor docs
- **Round 2**: CONVERGED (all 5 reviewers LGTM, 91-96% confidence)
- **Key Learning**: Multiple reviewers catching same issue indicates significance

### Files Changed

- `src/story_tracking/services/codebase_context_provider.py` (+199/-26)
- `src/story_tracking/services/codebase_security.py` (+131/-10)
- `tests/test_codebase_context_provider.py` (+239/-10)
- `tests/test_codebase_security.py` (+94/0)

---

## Previous: Hybrid Clustering Fragmentation Analysis (2026-01-26)

**Run 85 in progress** - 45 days of data (Dec 12, 2025 → Jan 26, 2026)

### Current State

Hybrid clustering pipeline runs end-to-end without errors, but produces **severely fragmented output**:

| Metric                              | Run 84 (7 days)                    |
| ----------------------------------- | ---------------------------------- |
| Conversations classified            | 306                                |
| Actionable (with themes)            | 117                                |
| Embedding clusters                  | 61                                 |
| Hybrid clusters (after facet split) | 90                                 |
| Size-1 clusters                     | 69 (77%)                           |
| Size-2 clusters                     | 15 (17%)                           |
| Size-3+ clusters                    | 6 (6%)                             |
| Stories created                     | 0 (hybrid), 1 (signature fallback) |
| Orphans created                     | 93                                 |

**Root Cause**: Double-fragmentation from two-stage algorithm:

1. Stage 1: Embedding clustering (distance_threshold=0.5) produces 61 clusters
2. Stage 2: Facet sub-grouping (action_type + direction) splits into 90 sub-clusters
3. Result: Most clusters too small for MIN_GROUP_SIZE=3

### Tuning Levers (Not Yet Adjusted)

| Parameter            | Current | Effect of Increasing                               |
| -------------------- | ------- | -------------------------------------------------- |
| `distance_threshold` | 0.5     | Fewer, larger embedding clusters                   |
| `MIN_GROUP_SIZE`     | 3       | Lower threshold = more stories from small clusters |
| Facet sub-grouping   | Enabled | Disabling = less fragmentation but less relevance  |

### What Was Done (2026-01-23-26)

- **Raw component preservation**: Migration 016 adds columns for drift detection
- **Component normalization**: `src/utils/normalize.py` with alias mapping
- **Stable hybrid signatures**: Cross-run orphan accumulation enabled
- **Diagnostic script**: `scripts/diagnose_run.py` for investigating run results
- **Dev-mode improvements**: Auto-cleanup of embeddings/facets, stale server detection

### Next Steps

1. Wait for Run 85 to complete (45 days = larger sample)
2. Analyze with: `PYTHONPATH=. python scripts/diagnose_run.py 85`
3. Compare cluster size distribution to Run 84
4. If still fragmented, adjust tuning levers (likely: increase distance_threshold)

---

## Previous: LLM-Generated Story Content Fields (2026-01-26)

**Commit 33fabd8** - Issue #133: Replace boilerplate with LLM-generated story fields

### Session Summary

Added 4 new LLM-generated fields to story content generation, replacing static boilerplate sections (INVEST Check, Instructions, Guardrails) with dynamically generated, story-specific content.

### What Was Done

**New LLM-Generated Fields**:

- `acceptance_criteria`: Given/When/Then format derived from symptoms
- `investigation_steps`: Component-specific debugging guidance
- `success_criteria`: Observable/measurable outcomes for validation
- `technical_notes`: Testing approach and vertical slice recommendations

**Implementation Changes**:

- Updated `src/prompts/story_content.py` with 4 new output fields and good/bad examples
- Enhanced `GeneratedStoryContent` dataclass with new fields in `story_content_generator.py`
- Added `_extract_list_field()` helper method for parsing LLM list outputs
- Updated `_mechanical_fallback()` to provide sensible defaults for new fields
- Modified `src/story_formatter.py` to use generated content, removed static sections
- Total: 9 LLM-generated fields per story (up from 5)

**Test Coverage**:

- 12 new tests for new fields and formatter changes
- Tests cover field extraction, fallback behavior, and formatting

**Documentation**:

- Updated `docs/architecture/story-content-generation.md` to document all 9 fields

### Impact

Stories now contain implementation-ready content tailored to each specific issue rather than generic boilerplate. Investigation steps are component-aware, acceptance criteria are symptom-specific, and technical notes provide testing guidance relevant to the problem domain.

---

## Previous: Hybrid Clustering Bug Fixes - End-to-End Pipeline Working (2026-01-22)

**Commit d88624d** - Critical bugs fixed during runs 46-54 testing

### Session Summary

Debugged and fixed 4 critical bugs preventing hybrid clustering (#106-#109) from working end-to-end. Pipeline now successfully runs: classification → embedding generation → facet extraction → theme extraction → hybrid clustering → PM review → story creation.

### What Was Done

**Bug 1: Conversations Stuck on First Run** (classification_storage.py)

- **Issue**: `COALESCE(pipeline_run_id)` kept conversations permanently linked to first run
- **Result**: Runs 46-50 had 0 conversations linked (all stuck on run 45)
- **Impact**: Embedding/facet/theme phases found nothing (query `WHERE pipeline_run_id = {current}`)
- **Fix**: Remove COALESCE, update pipeline_run_id to current run on re-classification

**Bug 2: Hybrid Clustering Never Ran** (pipeline.py)

- **Issue**: Called `cluster_conversations()` method that doesn't exist
- **Result**: Silent failure via try/except, fell back to signature grouping
- **Fix**: Call correct method `cluster_for_run(pipeline_run_id)`

**Bug 3: PM Review Disabled for Hybrid Clusters** (pipeline.py)

- **Issue**: Line 770 had `pm_review_enabled and not hybrid_clustering_enabled`
- **Result**: Run 54 grouped 5 unrelated bugs in one story (images, credits, billing, scheduler)
- **Fix**: Remove disable gate - PM review works for both signature and hybrid paths

**Bug 4: Classification Hangs and Crashes** (two_stage_pipeline.py)

- **Issue**: No timeout on OpenAI API calls → infinite hang (run 48)
- **Issue**: No exception handling in `asyncio.gather()` → silent crash (run 48)
- **Fix**: Added 30s timeout + `return_exceptions=True` + error logging

**Testing**:

- Run 54 completed successfully with hybrid clustering enabled
- 201 conversations → 87 embeddings → 87 facets → 85 themes → 3 stories
- All stories marked `grouping_method = 'hybrid_cluster'`

---

## Previous: Theme Quality Improvements - SAME_FIX Test + PM Review (2026-01-21)

**PR #101 MERGED** - 5-Personality Review CONVERGED (2 rounds)

### Session Summary

Implemented two key improvements from `docs/theme-quality-architecture.md` to improve theme extraction specificity and add PM review validation before story creation. These changes prevent unrelated issues from being grouped together (e.g., "duplicate pins" vs "missing pins" no longer share a single signature).

### What Was Done

**Improvement 1: SAME_FIX Test for Signature Specificity**

| Change                             | Description                                                                                                 |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `validate_signature_specificity()` | New function in `theme_extractor.py` validates signatures at extraction time                                |
| Broad suffix detection             | Rejects `_failure`, `_error`, `_issue`, `_problem` suffixes unless accompanied by specific symptom patterns |
| Specific pattern allowlist         | Allows `_duplicate_`, `_missing_`, `_timeout_`, `_permission_`, `_sync_`, `_oauth_`, `_upload_`, etc.       |
| Vocabulary guidelines              | Added `signature_quality_guidelines` to `theme_vocabulary.json` with SAME_FIX examples                      |

**Improvement 2: PM Review Before Story Creation**

| Change             | Description                                                                        |
| ------------------ | ---------------------------------------------------------------------------------- |
| `PMReviewService`  | New service in `pm_review_service.py` evaluates theme groups for coherence via LLM |
| Feature flag       | `PM_REVIEW_ENABLED=true` activates PM review (default: disabled for rollout)       |
| Decision types     | `keep_together`, `split` (creates sub-groups), `reject` (routes all to orphans)    |
| Sub-group handling | Sub-groups with >=3 conversations become stories, smaller ones become orphans      |
| Error handling     | Defaults to `keep_together` on LLM errors (fail-safe)                              |

**ProcessingResult Metrics Extended**

| Metric              | Purpose                                                      |
| ------------------- | ------------------------------------------------------------ |
| `pm_review_kept`    | Groups kept together by PM review                            |
| `pm_review_splits`  | Groups split into sub-groups                                 |
| `pm_review_rejects` | Groups where all conversations rejected                      |
| `pm_review_skipped` | Groups that bypassed review (disabled, timeout, single-conv) |

**5-Personality Review (2 Rounds)**:

- Round 1: Review issues identified and fixed
- Round 2: All 5 reviewers APPROVE, CONVERGED

**Tests Added**: 15 tests in `test_story_creation_service_pm_review.py` covering:

- PM review disabled/enabled behavior
- Keep together, split, and reject decisions
- Sub-group creation and orphan routing
- Error handling and quality gate integration

### Next Steps

1. Enable PM review in production (`PM_REVIEW_ENABLED=true`) for controlled rollout
2. Monitor `pm_review_splits` and `pm_review_rejects` metrics
3. Continue with roadmap Track A/B as planned
4. Issue #62 (coda_page adapter bug) remains priority

---

## Previous: Pipeline Pagination Fix - Search API Integration (2026-01-21)

**PR #100 MERGED** - 5-Personality Review CONVERGED

### Session Summary

Fixed critical pipeline pagination bug. Pipeline was fetching ALL conversations from Intercom (338k+) and filtering by date client-side, taking 9+ hours. Implemented server-side date filtering using Intercom Search API, reducing fetch time from hours to ~30 seconds.

### What Was Done

**Pipeline Pagination Bug Fixed**:

| Issue                      | Description                                            | Solution                                              |
| -------------------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| Client-side date filtering | Pipeline fetched ALL conversations, filtered in Python | Use Search API for server-side `created_at` filtering |
| 9+ hour fetch times        | Paginating through 338k+ conversations                 | Now fetches only date-range conversations             |
| Run 26 verification        | 2-day window test                                      | 91 conversations in 65.7 seconds                      |

**Technical Changes**:

| File                          | Change                                        | Impact                                       |
| ----------------------------- | --------------------------------------------- | -------------------------------------------- |
| `src/intercom_client.py`      | Added `search_by_date_range_async()` method   | Server-side date filtering via Search API    |
| `src/intercom_client.py`      | Updated `fetch_quality_conversations_async()` | Now uses Search API instead of List API      |
| `src/two_stage_pipeline.py`   | Updated to use new async method               | Pipeline uses efficient date-bounded queries |
| `src/api/routers/pipeline.py` | Removed PID tracking (YAGNI)                  | Cleaner code, eliminated security risk       |

**5-Personality Review (2 Rounds)**:

| Reviewer | Round 1 | Round 2 | Key Finding                           |
| -------- | ------- | ------- | ------------------------------------- |
| Reginald | BLOCK   | APPROVE | Added sock_read timeout to aiohttp    |
| Sanjay   | BLOCK   | APPROVE | Removed PID file TOCTOU vulnerability |
| Quinn    | BLOCK   | APPROVE | Cleared FUNCTIONAL_TEST_REQUIRED      |
| Dmitri   | BLOCK   | APPROVE | Removed ~216 lines of bloat           |
| Maya     | BLOCK   | APPROVE | Removed debug prints from production  |

**Tests Added**:

- 18 async tests for Search API methods (tests/test_intercom_async.py)
- 1 xfail documenting known production bug (4xx retry behavior)

### Follow-up Items

- Sync/async path divergence documented as known limitation (separate PR if needed)
- Rate limiting handled at gateway layer (out of scope)

---

## Previous: Milestone 6 - Canonical Pipeline Consolidation (2026-01-21)

### Session Summary

Completed Milestone 6 (Issues #82, #83, #85): Wired quality gates into `StoryCreationService`, retired `PipelineIntegrationService`, and aligned documentation with the canonical pipeline.

### What Was Done

**Milestone 6 Complete** - Canonical Pipeline Consolidation:

| Issue | Title                                        | Status   |
| ----- | -------------------------------------------- | -------- |
| #82   | Wire quality gates into StoryCreationService | Complete |
| #83   | Retire PipelineIntegrationService            | Complete |
| #85   | Align docs with canonical pipeline           | Complete |
| #80   | Remove legacy single-stage pipeline          | Complete |

**Quality Gates Added to StoryCreationService** (#82):

| Change                                  | Impact                                              |
| --------------------------------------- | --------------------------------------------------- |
| `QualityGateResult` dataclass           | Structured result type for gate pass/fail decisions |
| `_apply_quality_gates()` method         | Runs validation + scoring at top of processing loop |
| `_route_to_orphan_integration()` method | Unified orphan routing for failed groups            |
| EvidenceValidator integration           | Checks required fields (id, excerpt)                |
| ConfidenceScorer integration            | Scores group coherence, threshold 50.0              |
| `quality_gate_rejections` counter       | Track rejected groups in ProcessingResult           |

**PipelineIntegrationService Retired** (#83):

| Change                                            | Impact                                      |
| ------------------------------------------------- | ------------------------------------------- |
| File deleted: `pipeline_integration.py`           | 466 lines of orphaned code removed          |
| Test file deleted: `test_pipeline_integration.py` | 507 lines of tests for deleted code removed |
| `__init__.py` exports cleaned                     | No more dead exports                        |
| Zero production callers affected                  | Service was never used in production        |

**Architectural Decisions (from T-002)**:

| Decision              | Choice                       | Rationale                               |
| --------------------- | ---------------------------- | --------------------------------------- |
| Quality gate location | StoryCreationService         | All callers benefit from quality checks |
| Failure behavior      | Block (route to orphans)     | Reversible, maintains data quality      |
| Gate ordering         | Validation then scoring      | Fast-fail on validation, skip scoring   |
| Orphan path           | Via OrphanIntegrationService | Unified orphan logic across all paths   |

**Canonical Pipeline Path**:

```
src/two_stage_pipeline.py
    ↓
StoryCreationService.process_theme_groups()
    ↓
Quality Gates (EvidenceValidator + ConfidenceScorer)
    ↓
Story Creation (passed) OR Orphan Integration (failed)
```

### Next Steps

1. Continue with roadmap Track A/B as planned
2. Issue #62 (coda_page adapter bug) remains priority

---

## Previous: Dry Run Preview Visibility (2026-01-21)

### Session Summary

Completed PR #93 (Issue #75): Added ability to preview classification results from dry runs in the UI. Users can now see what would have been classified before committing to a production run.

### What Was Done

**PR #93 Merged** - Dry Run Preview Visibility:

| Change                                                                   | Impact                                                   |
| ------------------------------------------------------------------------ | -------------------------------------------------------- |
| New endpoint `GET /api/pipeline/status/{run_id}/preview`                 | Preview dry run results without storing to database      |
| `DryRunSample`, `DryRunClassificationBreakdown`, `DryRunPreview` schemas | Structured preview data for frontend consumption         |
| In-memory preview storage with cleanup                                   | Max 5 previews, auto-cleanup on terminal runs            |
| Proactive cleanup before storage                                         | Guarantees memory limits even if storage fails           |
| Frontend preview panel                                                   | Bar charts for type/confidence, sample cards, top themes |
| TypeScript types in `webapp/src/lib/types.ts`                            | Full type safety for frontend integration                |
| 30 unit tests                                                            | Storage, endpoint, cleanup, and edge case coverage       |

**Preview Panel Features**:

- **Classification breakdown**: Bar charts showing distribution by type and confidence
- **Sample conversations**: 5-10 diverse samples with snippets (200 chars)
- **Top themes**: Top 5 extracted themes with counts
- **Metadata**: Total classified count and timestamp

**5-Personality Review (2 rounds)**:

- Round 1: 5/5 REQUEST_CHANGES (cleanup, edge cases, UI improvements)
- Round 2: All issues resolved, 5/5 APPROVE, CONVERGED

### Next Steps

1. Continue with roadmap Track A/B as planned
2. Issue #62 (coda_page adapter bug) remains priority

---

## Previous: ResolutionAnalyzer and KnowledgeExtractor Integration (2026-01-21)

### Session Summary

Completed PR #92 (Issues #78, #79): Integrated `ResolutionAnalyzer` and `KnowledgeExtractor` modules into the two-stage classification pipeline, enriching the `support_insights` JSONB column with structured resolution and knowledge data.

### What Was Done

**PR #92 Merged** - ResolutionAnalyzer and KnowledgeExtractor Integration:

| Change                                                               | Impact                                                                    |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Replaced `detect_resolution_signal()` with full `ResolutionAnalyzer` | Richer resolution tracking with categories, all actions, matched keywords |
| Added `get_full_resolution_analysis()` helper                        | Clean interface for resolution data extraction                            |
| Added `extract_knowledge()` helper                                   | Structured knowledge extraction (root cause, solution, mentions)          |
| Module-level analyzer initialization                                 | Efficient re-use of stateless analyzers                                   |
| Both sync and async paths enriched                                   | Consistent support_insights population                                    |
| 21 new tests                                                         | Comprehensive coverage of new functionality                               |
| Architect Output Review Gate                                         | Process gate for deletion approval workflow                               |

**5-Personality Review (2 rounds)**:

- Round 1: Issues identified (4 REQUEST_CHANGES, 1 APPROVE)
- Round 2: All issues resolved, 5/5 APPROVE, CONVERGED

---

## Previous: StoryCreationService Pipeline Integration (2026-01-21)

### Session Summary

Completed PR #81 (Issue #77): Wired `StoryCreationService` into the UI pipeline router, consolidating story creation logic from inline code to the dedicated service layer.

### What Was Done

**PR #81 Merged** - StoryCreationService Integration:

| Change                                                                  | Impact                                         |
| ----------------------------------------------------------------------- | ---------------------------------------------- |
| Replaced inline story creation in `_run_pm_review_and_story_creation()` | ~50 lines removed from pipeline.py             |
| Added `process_theme_groups()` entry point                              | Clean pipeline integration                     |
| Consolidated `MIN_GROUP_SIZE` constant                                  | Removed duplicate constant                     |
| Added error tracking for pipeline linking                               | Proper failure visibility                      |
| Security fixes S1-S3                                                    | Conversation ID validation, exception handling |

**5-Personality Review (3 rounds)**:

- Round 1: Initial review with issues identified
- Round 2: Sanjay raised 3 security issues (S1-S3)
- Round 3: All issues resolved, CONVERGED

**Security Fixes Applied**:

- S1: Conversation ID validation before use
- S2: Pipeline run linking error tracking
- S3: Evidence creation error tracking
- Bonus: Never swallow KeyboardInterrupt/SystemExit

**Test Coverage**: 11 new tests for pipeline integration

### Next Steps

1. Continue with roadmap Track A/B as planned
2. Issue #62 (coda_page adapter bug) remains priority

---

## Previous: Roadmap Planning & Agent Protocol (2026-01-20)

### Session Summary

Created comprehensive roadmap proposal and used agent coordination protocol for async discussion between Claude Code and Codex to resolve sequencing disagreements. Decision: 4-week parallel tracks (PM UX + Implementation Context).

### What Was Done

**Roadmap Creation** (`docs/proposed_roadmap_jan_20_claude.md`):

- 6-phase roadmap prioritizing implementation context as core differentiator
- Key insight: code pointers (#44, #46, #56) are "head start on implementation"
- Issue #62 (coda_page adapter) identified as Week 1 blocker

**Agent Coordination (T-001)**:

- Claude Code (architect) vs Codex (implementation check) discussion
- Claude: Implementation context first (core value prop)
- Codex: PM UX spine first (operational risk)
- Resolution: Hybrid parallel tracks

**Decided Roadmap (4-week parallel tracks)**:

| Week | Track A (PM UX)            | Track B (Implementation Context) |
| ---- | -------------------------- | -------------------------------- |
| 1    | #62 coda_page fix          | #46 repo sync                    |
| 2    | #53 pipeline control       | #44 wire classifier              |
| 3    | #54 run summary            | #56 impl context UI              |
| 4    | #55 evidence accept/reject | Buffer                           |

**Files Created**:

- `docs/proposed_roadmap_jan_20_claude.md` - Claude's 6-phase roadmap
- `docs/agent-conversation-archive/2026-01-20_T-001.md` - Archived T-001 discussion
- `docs/agent-conversation.md` - Updated with archived summary

### Next Steps

1. Fix #62 coda_page adapter bug (Week 1, Track A)
2. Implement #46 repo sync + static fallback (Week 1, Track B)
3. Begin #53 pipeline control (Week 2)

---

## Previous: Vector Integration Phase 1 Complete (2026-01-20)

### Session Summary

Completed Vector Integration Phase 1 (issue #43). Implemented accept/reject endpoints, rejection filtering, setup scripts, and fixed critical bugs discovered during functional testing.

### What Was Done

**Vector Integration Phase 1 - All PRs Merged**:

| PR  | Feature                                                 | Status    |
| --- | ------------------------------------------------------- | --------- |
| #52 | Schema migration (`suggested_evidence_decisions` table) | ✅ Merged |
| #57 | Accept/reject endpoints for suggested evidence          | ✅ Merged |
| #60 | Recovery of orphaned changes from #58/#59               | ✅ Merged |
| #61 | Fix embedding model + missing URL column                | ✅ Merged |

**Accept/Reject Endpoints** (PR #57):

- `POST /api/research/stories/{story_id}/suggested-evidence/{evidence_id}/accept`
- `POST /api/research/stories/{story_id}/suggested-evidence/{evidence_id}/reject`
- Evidence ID format: `source_type:source_id` (e.g., `coda_page:page_abc123`)
- Proper error handling: 400 (invalid format), 404 (story not found), 409 (duplicate decision)
- 15 new endpoint tests

**Filter Rejected Evidence** (recovered in PR #60):

- `get_suggested_evidence` now excludes previously rejected items
- Query `suggested_evidence_decisions` table for rejected IDs
- 3 new filter tests

**Setup Script & Runbook** (recovered in PR #60):

- `scripts/run_initial_embeddings.py` - 5-step validation with progress output
- `docs/runbook/vector-search-setup.md` - Installation and troubleshooting guide

**Bug Fixes** (PR #61):

- Switched from `text-embedding-3-large` (3072 dims) to `text-embedding-3-small` (1536 dims)
  - pgvector 0.8 has 2000 dimension limit for indexes
- Added missing `url` column to INSERT statement in embedding_pipeline.py
- Updated migration schema to match

**Functional Test Results**:

- ✅ pgvector extension verified
- ✅ research_embeddings table created
- ✅ 10 embeddings generated (5 themes, 5 intercom)
- ⚠️ P95 latency 712ms (target 500ms) - expected with small dataset

**Issue Filed**:

- #62: coda_page adapter "no such column: name" bug (future session)

### Test Coverage

- 50 tests in `test_research.py` (all passing)
- Covers: endpoints, filtering, evidence decisions, search functionality

### Next Steps

1. Fix coda_page adapter schema issue (issue #62)
2. Run full embedding pipeline with production data
3. Wire suggested evidence into story creation flow

---

## Previous: PR #42 Domain Classifier & Vector Integration Review (2026-01-20)

---

---

> **📁 Older entries archived**: See [`docs/status-archive.md`](./status-archive.md) for entries from 2026-01-19 through 2026-01-07.

---

## Phase 4: Theme Extraction ✅

**Status**: Vocabulary v2.2 complete with VDD validation

**Deliverables**:

- [x] `src/theme_extractor.py` - LLM-based theme extraction with product context
- [x] `src/theme_tracker.py` - Store, aggregate, and query themes
- [x] `src/cli.py` - CLI for viewing themes and ticket previews
- [x] `src/db/schema.sql` - themes + theme_aggregates tables
- [x] `context/product/*.md` - Product documentation for context

**CLI Commands**:

```bash
python src/cli.py themes           # List all themes
python src/cli.py trending         # Trending (2+ occurrences in 7 days)
python src/cli.py pending          # Preview ALL pending tickets
python src/cli.py ticket <sig>     # Preview specific ticket
python src/cli.py extract <id>     # Extract theme from conversation
```

**Ticket Format**: Each ticket includes:

- Product area and component mapping
- Canonical issue_signature for aggregation
- User intent and symptoms
- Affected flow and root cause hypothesis
- Sample customer messages
- Suggested investigation steps

**Signature Canonicalization**: Two-phase extraction ensures consistent signatures:

1. Phase 1: Extract theme details (product_area, component, symptoms, etc.)
2. Phase 2: Canonicalize signature against existing signatures in database

Tested embedding-based canonicalization as cheaper alternative - rejected due to lower accuracy (0.627 similarity) and actually slower (N API calls vs 1 LLM call).

**Branch**: `feature/theme-extraction` - ready for PR

---

## Phase 3: COMPLETE ✅

**Final Metrics**:

| Metric            | Result      | Target            |
| ----------------- | ----------- | ----------------- |
| Rule Evaluation   | ✅ Working  | 100% success      |
| Churn Risk Alert  | ✅ Working  | Triggers Slack    |
| Urgent Alert      | ✅ Working  | Triggers Slack    |
| Bug Report Ticket | ✅ Working  | Logs for Shortcut |
| Deduplication     | ✅ Verified | No duplicates     |
| Unit Tests        | 20 passing  | All pass          |

**Deliverables**:

- [x] `docs/escalation-rules.md` - Rule definitions (6 rules)
- [x] `docs/acceptance-criteria-phase3.md` - Acceptance criteria
- [x] `src/escalation.py` - Rule engine with 5 rules
- [x] `src/slack_client.py` - Slack webhook integration (dry-run ready)
- [x] `src/db/schema.sql` - Added escalation_log table
- [x] `tests/test_escalation.py` - 20 unit tests passing

**Run escalation**:

```bash
# After running pipeline, evaluate escalation rules
python -c "from src.escalation import run_escalation; run_escalation(dry_run=True)"
```

**Note**: Add `SLACK_WEBHOOK_URL` to `.env` to enable real Slack alerts.

## Phase 2: COMPLETE ✅

**Final Metrics**:

| Metric                | Result      | Target        |
| --------------------- | ----------- | ------------- |
| Intercom Fetch        | ✅ Working  | Functional    |
| Quality Filter        | 17%         | ~50% (varies) |
| Classification        | 100%        | 100%          |
| DB Storage            | ✅ Working  | Functional    |
| Idempotency           | ✅ Verified | No duplicates |
| Pipeline Time (5 msg) | ~10s        | <5min/100     |

**Deliverables**:

- [x] `src/intercom_client.py` - Fetch + quality filter
- [x] `src/pipeline.py` - CLI orchestration (--days, --dry-run, --max)
- [x] `src/db/models.py` - Pydantic models
- [x] `src/db/schema.sql` - PostgreSQL schema
- [x] `src/db/connection.py` - Database operations
- [x] `tests/test_pipeline.py` - 13 unit tests passing
- [x] `docs/acceptance-criteria-phase2.md` - Acceptance criteria

**Run the pipeline**:

```bash
python -m src.pipeline --days 7             # Last 7 days
python -m src.pipeline --days 1 --max 10    # Test with 10 conversations
python -m src.pipeline --dry-run            # No DB writes
```

## Phase 1: COMPLETE ✅

**Final Metrics** (all targets exceeded):

| Metric               | Result | Target |
| -------------------- | ------ | ------ |
| Issue Type Accuracy  | 100%   | 80%    |
| Sentiment Accuracy   | 81.2%  | 75%    |
| Churn Risk Precision | 100%   | 75%    |
| Churn Risk Recall    | 100%   | 85%    |
| Priority Accuracy    | 93.8%  | 70%    |

**Deliverables**:

- [x] `src/classifier.py` - OpenAI gpt-4o-mini + rule-based post-processing
- [x] `tests/test_classifier.py` - 13 tests, all passing
- [x] `data/labeled_fixtures.json` - 50 human-labeled samples
- [x] `docs/acceptance-criteria.md` - Measurable thresholds
- [x] `docs/intercom-data-patterns.md` - API access patterns, quality filtering
- [x] `tools/labeler.py` - Streamlit UI for labeling

**Key Learnings** (incorporated into PLAN.md):

- Only ~50% of Intercom conversations are usable (quality filtering needed)
- LLMs need rule-based post-processing for edge cases (hybrid pattern)
- Churn risk is boolean, not enum (stacks with any issue type)

## What's Next

**Immediate: Fix #175 (Story API Count Mismatch)**

- API `/api/stories` returns 4 stories when DB has more
- Likely a filter or query issue

**Future Options**:

- Add `SLACK_WEBHOOK_URL` for real Slack alerts
- Add `SHORTCUT_API_TOKEN` for real ticket creation
- Phase 4: Real-Time Workflows (webhook-driven processing)

## Blockers

None currently - #176 resolved, pipeline producing stories.

## Recent Session Notes

### 2026-02-01: Issue #200 - 30-Day Recency Gate for Story Creation

**Objective**: Add hard-coded 30-day recency requirement for story creation. Groups must have at least one conversation from the last 30 days to become stories.

**Implementation**:

- Added `created_at` to `ConversationData` dataclass and threaded through pipeline
- Added `RECENCY_WINDOW_DAYS = 30` constant in `models/orphan.py` (single source of truth)
- Added `_has_recent_conversation()` helper for story creation recency checks
- Added recency gate to `_apply_quality_gates` (covers signature groups, hybrid clusters, PM keep-together)
- Added recency check to `_handle_pm_split` for PM review sub-groups
- Added `_check_conversation_recency()` and `_get_conversation_recency_bulk()` to orphan_service for graduation checks
- Added `skip_recency_check` parameter to `graduate()` to avoid N+1 queries in bulk graduation

**Gate Coverage**:
| Path | Recency Check Location |
|------|----------------------|
| Signature-based groups | `_apply_quality_gates` |
| Hybrid clusters | `_apply_quality_gates` |
| PM keep-together | `_apply_quality_gates` |
| PM split sub-groups | `_handle_pm_split` |
| Orphan graduation | `graduate()` and `check_and_graduate_ready()` |

**Review**: 5-personality + Codex review → 2 issues fixed (RealDictCursor access, N+1 elimination) → PR #203 merged

**Tests**: 29 new recency gate tests + 130 story creation tests pass

**Issue #200**: CLOSED

---

### 2026-01-30: Issue #176 Fix and Run #96 Recovery

**Objective**: Fix duplicate orphan signature cascade failure and recover run #96.

**Implementation**:

- `create_or_get()` with `ON CONFLICT DO NOTHING` for idempotent creation
- `get_by_signature()` returns graduated orphans for post-graduation routing
- `_add_to_graduated_story()` routes conversations to their story via EvidenceService
- New `stories_appended` metric tracks post-graduation additions

**Review**: 5-personality (2 rounds) → CONVERGED → PR #177 merged

**Recovery**: `POST /api/pipeline/96/create-stories` resumed story creation:

- Before: 0 stories, 0 orphans
- After: **35 stories, 376 orphans**

**Issue #176**: CLOSED

---

### 2026-01-30: Post-Milestone 10 Pipeline Validation

**Objective**: Run full pipeline on 30 days of data to validate Milestone 10 changes.

**Results**:

- Pipeline run #96 completed
- ✅ 1,530 conversations classified
- ✅ 593 themes extracted (12 filtered as `unclassified_needs_review` - appropriate)
- ❌ 0 stories created (blocked by #176)
- ❌ 0 orphans created (blocked by #176)

**Issues Filed**:
| Issue | Description |
|-------|-------------|
| #175 | API `/api/stories` returns 4 stories when DB has 15 |
| #176 | Orphan signature duplicate causes cascade transaction abort |

**Root Cause (#176)**: After orphan graduates to story, code attempts to insert another orphan with same signature → unique constraint violation → transaction not rolled back → all subsequent operations fail.

**Suggested Fixes**:

1. Use upsert: `ON CONFLICT (signature) DO UPDATE`
2. Ensure graduation clears/reuses orphan record
3. Add savepoints for isolation

## Decision Log

| Date       | Decision                  | Rationale                                    |
| ---------- | ------------------------- | -------------------------------------------- |
| 2026-01-06 | OpenAI for LLM            | User preference                              |
| 2026-01-06 | Batch processing          | Cost-effective for ~100/week                 |
| 2026-01-06 | Data-driven schema        | Let real data inform categories              |
| 2026-01-06 | Hybrid LLM + rules        | LLM for semantics, rules for edge cases      |
| 2026-01-06 | Quality filter before LLM | ~50% of conversations not useful, saves cost |
| 2026-01-06 | LLM for canonicalization  | Embedding approach slower & less accurate    |
