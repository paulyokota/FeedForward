# Stage 0 Explorers — Readiness Doc

Prep for Issues #216, #217, #218. Written 2026-02-08 to get the next session
running immediately without research overhead.

## The Pattern (from Customer Voice Explorer, #215)

Every explorer follows the same shape:

```
DataReader → Explorer.explore() → ExplorerResult → Explorer.build_checkpoint_artifacts() → ExplorerCheckpoint
```

### Interface contract

```python
class SomeExplorer:
    def __init__(self, reader: SomeReader, openai_client=None, config=None)
    def explore(self) -> ExplorerResult           # main flow
    def requery(self, request_text, ...) -> Dict   # follow-up questions
    def build_checkpoint_artifacts(self, result) -> Dict  # → ExplorerCheckpoint schema
```

### Shared infrastructure (no changes needed)

| Component                           | Status | Notes                                                                 |
| ----------------------------------- | ------ | --------------------------------------------------------------------- |
| `ExplorerResult` dataclass          | Exists | findings, coverage, token_usage, batch_errors                         |
| `ExplorerCheckpoint` Pydantic model | Exists | schema_version, agent_name, findings, coverage                        |
| `ExplorerFinding` model             | Exists | pattern_name, description, evidence, confidence, severity, scope      |
| `CoverageMetadata` model            | Exists | time_window_days, available, reviewed, skipped, model, findings_count |
| `EvidencePointer` model             | Exists | source_type, source_id, retrieved_at, confidence                      |
| `SourceType` enum                   | Exists | intercom, posthog, github, codebase, research, other                  |
| `STAGE_ARTIFACT_MODELS` mapping     | Exists | EXPLORATION → ExplorerCheckpoint (generic, not per-explorer)          |
| State machine                       | Exists | All explorers share Stage 0, one checkpoint advances to Stage 1       |
| Conversation service                | Exists | submit_checkpoint validates ExplorerCheckpoint, advances stage        |
| Prompts module                      | Exists | Add new prompt constants per explorer                                 |

### Two-pass LLM strategy

1. **Batch analysis**: Process N items per batch, open-ended pattern recognition
2. **Synthesis**: Merge findings across batches, deduplicate, reassess confidence
3. **Partial failure**: Per-batch errors caught, counted as `skipped`, run continues

### Coverage metadata invariant

`reviewed + skipped == available`

This holds regardless of data source. "Items" can be conversations, events,
files, documents — the invariant is about accounting for scope.

### Test patterns to replicate

**Unit tests** (~20-25 tests):

- Happy path, empty input, multiple batches, token tracking
- Partial failure, synthesis failure, invalid JSON
- Coverage invariant
- Formatting/truncation
- Checkpoint building (validates against ExplorerCheckpoint)
- Requery
- Confidence mapping

**Integration tests** (~5-7 tests):

- Full state machine flow: explore → checkpoint → advances to OPPORTUNITY_FRAMING
- Conversation audit trail events
- Prior checkpoints readable
- Taxonomy guard (no pipeline vocabulary)

---

## Explorer #1: Analytics Explorer (Issue #216)

### Data source: PostHog MCP

PostHog MCP tools available in the environment:

| Tool                                   | Purpose                                   |
| -------------------------------------- | ----------------------------------------- |
| `query-run`                            | Execute trends, funnels, or HogQL queries |
| `query-generate-hogql-from-question`   | Natural language → HogQL                  |
| `insight-query`                        | Run an existing insight                   |
| `insight-get` / `insights-get-all`     | Read saved insights                       |
| `event-definitions-list`               | Available event types                     |
| `properties-list`                      | Event properties                          |
| `logs-query`                           | Log entries with filtering                |
| `list-errors` / `error-details`        | Error tracking                            |
| `dashboards-get-all` / `dashboard-get` | Dashboard data                            |
| `feature-flag-get-all`                 | Feature flag state                        |

### Architecture decision: How does the explorer call PostHog?

**Option A: MCP tools at runtime** — Explorer agent calls PostHog MCP tools
directly during `explore()`. This is the most natural fit for an agent that
"explores with open-ended reasoning" but makes the agent session-bound and
harder to test (MCP calls aren't easily mockable with the same pattern).

**Option B: PostHogReader wrapper** — Create a `PostHogReader` class that
abstracts PostHog access (wraps MCP calls or direct API calls). Inject the
reader like `ConversationReader`. Test with `MockPostHogReader`.

**Option C: Pre-fetched data** — A separate step fetches PostHog data into
a local format (JSON/dict), then the explorer analyzes it. Clean separation
but adds a pipeline step.

**Recommendation: Option B.** Same dependency injection pattern as Customer
Voice. The `PostHogReader` wraps PostHog MCP tool calls (or API calls)
behind a clean interface. Tests mock the reader. The agent stays a pure
function.

### Data access design

```python
@dataclass
class PostHogDataPoint:
    """A unit of PostHog data the explorer sees."""
    data_type: str           # "trend", "funnel", "event_sample", "insight"
    query_description: str   # What was asked
    result_summary: str      # Formatted result text for LLM
    raw_data: Dict[str, Any] # Original response
    retrieved_at: datetime
    source_ref: str          # e.g., "insight_12345" or "trend_pageview_7d"

class PostHogReader:
    def __init__(self, posthog_client=None):
        ...

    def fetch_overview(self, days: int = 14) -> List[PostHogDataPoint]:
        """Fetch a broad overview of product analytics.

        Strategy: cast a wide net, then let the LLM find patterns.
        - List all event definitions → sample top events
        - Fetch existing dashboards/insights
        - Pull error rates
        - Pull funnel data if funnels exist
        """
        ...

    def fetch_specific(self, query: str) -> PostHogDataPoint:
        """Fetch specific data for a targeted question (requery support)."""
        ...

    def get_data_point_count(self) -> int:
        """How many data points were available."""
        ...
```

### Batching strategy

PostHog data is different from conversations — it's not a uniform stream.
Possible approach:

1. **Discovery phase**: Query event definitions, dashboards, insights to
   build a "table of contents" of available analytics
2. **Deep-dive batches**: Group related metrics (e.g., all funnel data,
   all error data, all feature adoption data) into batches
3. **Synthesis**: Cross-reference patterns across metric groups

The batch boundaries are semantic (by metric domain) not just size-based.

### Prompts

Need new prompt constants:

- `ANALYTICS_BATCH_ANALYSIS_SYSTEM` — "You are analyzing product usage data..."
- `ANALYTICS_BATCH_ANALYSIS_USER` — template with `{data_points_json}`
- `ANALYTICS_SYNTHESIS_SYSTEM` / `_USER` — same pattern as Customer Voice
- `ANALYTICS_REQUERY_SYSTEM` / `_USER` — targeted follow-up

### Evidence pointers

`source_type: SourceType.POSTHOG`
`source_id`: insight ID, dashboard ref, event name, or HogQL query hash

### Key risk

The "open-ended exploration" aspect is harder with analytics than with
conversations. Conversations are self-contained text — an LLM reads them
and reasons. Analytics data is numeric/tabular — the LLM needs the data
pre-formatted in a way that enables pattern recognition. The quality of
the `PostHogReader.fetch_overview()` output directly determines whether
the LLM can find anything interesting.

### Files to create

- `src/discovery/agents/posthog_data_access.py` — PostHogReader + PostHogDataPoint
- `src/discovery/agents/analytics_explorer.py` — AnalyticsExplorer class
- `src/discovery/agents/prompts.py` — add analytics prompt constants
- `tests/discovery/test_analytics_explorer.py` — unit tests
- `tests/discovery/test_analytics_explorer_integration.py` — integration tests

### Files to modify

None. SourceType.POSTHOG already exists. ExplorerCheckpoint is generic.

---

## Explorer #2: Codebase Explorer (Issue #217)

### Data source: Local file system + git

This is architecturally the simplest because there's no external API. Claude
Code already has Glob, Grep, Read, and git access. The question is how to
structure the data access layer.

### Data access design

```python
@dataclass
class CodebaseItem:
    """A unit of codebase data the explorer sees."""
    item_type: str          # "file", "diff", "git_log", "directory_summary"
    path: str               # File path or directory
    content: str            # File content, diff text, or summary
    metadata: Dict[str, Any]  # Line count, last modified, commit count, etc.

class CodebaseReader:
    def __init__(self, repo_root: str, days: int = 30):
        self.repo_root = repo_root
        self.days = days

    def fetch_recently_changed(self, days: int = 30, limit: int = None) -> List[CodebaseItem]:
        """Files changed in the last N days (via git log).

        Returns file content + change metadata (commit count, authors, churn).
        Excludes test files, config, docs by default (configurable).
        """
        ...

    def fetch_hotspots(self) -> List[CodebaseItem]:
        """Files with high complexity or change frequency."""
        ...

    def fetch_directory_summaries(self, paths: List[str]) -> List[CodebaseItem]:
        """High-level structure summaries for specified directories."""
        ...

    def fetch_file(self, path: str) -> Optional[CodebaseItem]:
        """Single file for requery."""
        ...
```

### Batching strategy

Unlike conversations (uniform items), the codebase has structure. Options:

1. **By directory**: Each batch is one top-level directory (src/, tests/, webapp/)
2. **By recency**: Batch recently-changed files together
3. **By type**: Source files, test files, config files
4. **Hybrid**: Recently-changed source files in batch 1, high-churn files
   in batch 2, directory structure overview in batch 3

**Recommendation: Hybrid.** Start with what's changed recently (highest
signal-to-noise), then look at structural patterns.

### Scope/stop conditions

The codebase is large. Unlike conversations (200 is a natural limit), the
codebase has thousands of files. Need clear boundaries:

- **Default scope**: `src/` directory, files changed in last 30 days
- **Exclusions**: `node_modules/`, `__pycache__/`, `.git/`, binary files
- **Max files per batch**: ~10-15 (code is denser than conversations)
- **Max chars per file**: ~3000 (more generous than conversations because
  code structure matters)

### Prompts

Need new prompt constants:

- `CODEBASE_BATCH_ANALYSIS_SYSTEM` — "You are a senior engineer reviewing
  code for patterns, tech debt, and architecture opportunities..."
- `CODEBASE_BATCH_ANALYSIS_USER` — template with `{files_json}`
- `CODEBASE_SYNTHESIS_SYSTEM` / `_USER`
- `CODEBASE_REQUERY_SYSTEM` / `_USER`

### Evidence pointers

`source_type: SourceType.CODEBASE`
`source_id`: `file_path:line_number` or `file_path` (for file-level findings)

For git-related findings:
`source_type: SourceType.GITHUB`
`source_id`: `issue_number`, `pr_number`, or `commit_sha`

### Key advantage

The LLM is reading code, which it's naturally good at. The data formatting
is straightforward — just file contents with metadata. Less risk of the
"data needs careful formatting" problem that affects analytics.

### Key risk

Scope creep. "Find tech debt" could mean anything. The prompts need to
focus on _actionable opportunities_ (things worth fixing that would have
measurable impact), not just observations ("this function is long").

### Files to create

- `src/discovery/agents/codebase_data_access.py` — CodebaseReader + CodebaseItem
- `src/discovery/agents/codebase_explorer.py` — CodebaseExplorer class
- `src/discovery/agents/prompts.py` — add codebase prompt constants
- `tests/discovery/test_codebase_explorer.py` — unit tests
- `tests/discovery/test_codebase_explorer_integration.py` — integration tests

### Files to modify

None.

---

## Explorer #3: Research/Market Explorer (Issue #218)

### Data source: Internal docs + web search

This is the least-defined explorer. The issue says so explicitly.

### Data access design

```python
@dataclass
class ResearchItem:
    """A unit of research data the explorer sees."""
    item_type: str          # "internal_doc", "web_search_result", "github_discussion"
    source: str             # File path or URL
    content: str            # Text content
    retrieved_at: datetime
    metadata: Dict[str, Any]

class ResearchReader:
    def __init__(self, doc_paths: List[str] = None, web_search_enabled: bool = True):
        self.doc_paths = doc_paths or ["docs/", "reference/"]
        self.web_search_enabled = web_search_enabled

    def fetch_internal_docs(self) -> List[ResearchItem]:
        """Read internal documentation and reference materials."""
        ...

    def fetch_web_context(self, queries: List[str]) -> List[ResearchItem]:
        """Web search for market/competitor context."""
        ...

    def fetch_github_context(self) -> List[ResearchItem]:
        """GitHub issues/discussions for internal research context."""
        ...
```

### Key design decision

What does this explorer actually search for? The internal docs (`docs/`,
`reference/`) are static — the explorer would read them once and extract
patterns. Web search adds dynamism but introduces reliability concerns.

**Phase 1 recommendation** (from the issue): Start narrow.

- Read internal docs only
- No web search initially
- Let findings prove or disprove the value before adding complexity

### Evidence pointers

`source_type: SourceType.RESEARCH`
`source_id`: file path or URL

### Key risk

This explorer might not produce useful findings in Phase 1. Internal docs
are small and well-known. The real value would come from web search
(competitor analysis, market trends), but that's harder to test and
validate. Consider making this the LAST explorer to implement.

### Files to create

- `src/discovery/agents/research_data_access.py` — ResearchReader + ResearchItem
- `src/discovery/agents/research_explorer.py` — ResearchExplorer class
- `src/discovery/agents/prompts.py` — add research prompt constants
- `tests/discovery/test_research_explorer.py` — unit tests
- `tests/discovery/test_research_explorer_integration.py` — integration tests

### Files to modify

None.

---

## Recommended Order

1. ~~**#217 Codebase Explorer**~~ — DONE (PR #237, merged 2026-02-08).
   39 tests, 297 total discovery tests passing.

2. **#216 Analytics Explorer** — Real value from a different data source,
   but PostHog MCP integration adds complexity. The data formatting
   challenge (making numeric data LLM-readable) needs careful design.

3. **#218 Research/Market Explorer** — Least defined, most risk of low-value
   findings in Phase 1. Wait until the pattern is battle-tested.

## Multi-Explorer Checkpoint Design

Currently, Stage 0 (EXPLORATION) produces a single `ExplorerCheckpoint`.
When multiple explorers exist, there's a question: does each explorer
submit its own checkpoint, or do findings get merged first?

**Current state machine design**: One checkpoint per stage. `submit_checkpoint()`
advances the stage. So only one explorer can submit.

**Options**:

A. **Merge before checkpoint**: An orchestrator collects findings from all
explorers and merges them into a single ExplorerCheckpoint. The Opportunity
PM sees one unified set of findings.

B. **Multiple exploration stages**: Run each explorer as a separate discovery
run. Opportunity PM synthesizes across runs.

C. **Change state machine**: Allow multiple checkpoints per stage. Breaking change.

**Recommendation for Phase 1**: Option A is simplest. The merge step is
just concatenation + dedup of findings. The `agent_name` field in
ExplorerCheckpoint would become a list or a composite name. But this is
an orchestration concern — don't solve it until the orchestrator exists.

**For now**: Each explorer can be tested independently. The integration
tests verify single-explorer → checkpoint → stage advancement. Multi-explorer
orchestration is Issue #225 territory.

---

## Quick-Start Checklist (for next session)

To implement any explorer, follow this sequence:

1. [ ] Create data access module (`src/discovery/agents/{name}_data_access.py`)
2. [ ] Create explorer agent (`src/discovery/agents/{name}_explorer.py`)
3. [ ] Add prompt constants to `src/discovery/agents/prompts.py`
4. [ ] Create unit tests (`tests/discovery/test_{name}_explorer.py`)
5. [ ] Create integration tests (`tests/discovery/test_{name}_explorer_integration.py`)
6. [ ] Run `pytest tests/discovery/ -v` — all tests pass
7. [ ] Run `pytest -m "not slow"` — no regressions
8. [ ] PR + review cycle

No model changes. No enum changes. No state machine changes.
Just: reader + agent + prompts + tests.
