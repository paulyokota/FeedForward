# Codebase Explorer Implementation Plan — Issue #217

## Overview

Implement a Codebase Explorer agent that reads recently-changed source files
via git and discovers patterns (tech debt, architecture opportunities,
recurring complexity) using the same two-pass LLM strategy as the Customer
Voice Explorer (#215).

**Branch**: `feature/217-codebase-explorer`
**Estimated files created**: 5
**Estimated files modified**: 1 (prompts.py — add constants)
**Infrastructure changes**: None

---

## Design Decisions

### D1: CoverageMetadata field naming

The `CoverageMetadata` Pydantic model has required fields named
`conversations_available`, `conversations_reviewed`, `conversations_skipped`.
For a codebase explorer, files are the unit of analysis, not conversations.

**Decision**: Populate the `conversations_*` fields with file counts (since
they are the required fields and the model validates them), AND add extra
fields `items_type: "files"` to document what the numbers represent. The
model uses `extra="allow"` so this works without schema changes.

**Rationale**: Changing the model would be a breaking change affecting the
Customer Voice Explorer and all existing tests. The readiness doc explicitly
says "items can be conversations, events, files, documents — the invariant
is about accounting for scope." The extra `items_type` field makes the
semantics clear to downstream consumers.

### D2: Data source — git log + file read

The `CodebaseReader` uses `subprocess` to call `git log` and `git diff-tree`
for recently-changed files. File contents are read directly from disk.
No external API dependencies.

**Scope boundaries**:

- Default: `src/` directory only (production code, not tests/docs/config)
- Exclusions: `__pycache__/`, `.git/`, `node_modules/`, binary files, `*.pyc`
- Time window: files changed in last 30 days (configurable)
- Max files: 100 (configurable)
- Max chars per file: 3000 (code is denser than conversations)

### D3: Batching strategy — hybrid

Unlike conversations (uniform items), code files vary in size and relevance.
Batch by recency: most-recently-changed files first, in groups of ~10-15.
This puts highest-signal files (active development) in early batches.

### D4: Evidence pointers

`source_type: SourceType.CODEBASE`
`source_id`: file path relative to repo root (e.g., `src/api/main.py`)

For line-specific findings, the LLM can include line references in the
description, but `source_id` stays at file level for stability (line numbers
shift across commits).

### D5: Prompt design — actionable opportunities, not observations

The prompts must focus on patterns that would lead to actionable work:
tech debt with measurable impact, architecture bottlenecks, duplicated
logic, missing abstractions that cause bugs. NOT just "this function
is long" observations.

Critical constraint carried forward: NO reference to existing pipeline
taxonomy, theme vocabulary, or predefined categories.

---

## Files to Create

### 1. `src/discovery/agents/codebase_data_access.py`

Data access layer for the codebase explorer.

```python
@dataclass
class CodebaseItem:
    path: str               # Relative to repo root
    content: str            # File content (truncated to max_chars)
    item_type: str          # "source_file"
    metadata: Dict[str, Any]  # commit_count, last_modified, line_count, authors

class CodebaseReader:
    def __init__(self, repo_root: str, days: int = 30)

    def fetch_recently_changed(self, days=30, limit=None) -> List[CodebaseItem]
        # git log --name-only to find files changed in time window
        # Read file contents from disk
        # Exclude: __pycache__, .git, node_modules, binary, *.pyc
        # Default scope: src/ directory
        # Ordered by: most recent commit first

    def fetch_file(self, path: str) -> Optional[CodebaseItem]
        # Single file read for requery support

    def get_item_count(self, days=30) -> int
        # Count of files changed in time window (for coverage)
```

**Key implementation notes**:

- `subprocess.run(["git", "log", ...])` for git operations
- `pathlib.Path` for file reading
- Skip binary files via `.suffix` check or `git diff --numstat` (binary shows `-`)
- Metadata from `git log --format="%H %an %ai" --follow` per file

### 2. `src/discovery/agents/codebase_explorer.py`

The explorer agent itself. Follows the Customer Voice Explorer structure exactly.

```python
@dataclass
class CodebaseExplorerConfig:
    time_window_days: int = 30
    max_files: int = 100
    batch_size: int = 10      # Smaller than conversations (code is denser)
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_chars_per_file: int = 3000

class CodebaseExplorer:
    def __init__(self, reader: CodebaseReader, openai_client=None, config=None)

    def explore(self) -> ExplorerResult
        # 1. Fetch recently changed files from reader
        # 2. Split into batches (default 10 per batch)
        # 3. Per-batch LLM analysis (pattern recognition)
        # 4. Synthesis pass (dedup, cross-reference)
        # 5. Return ExplorerResult

    def requery(self, request_text, previous_findings, file_paths=None) -> Dict
        # Follow-up questions; fetches specific files if paths provided

    def build_checkpoint_artifacts(self, result: ExplorerResult) -> Dict
        # Transform to ExplorerCheckpoint schema
        # agent_name: "codebase"
        # source_type: SourceType.CODEBASE
        # evidence_file_paths → source_id

    # Internal:
    def _analyze_batch(self, batch, batch_idx) -> tuple
    def _synthesize(self, all_batch_findings, total_reviewed) -> tuple
    def _format_file(self, item: CodebaseItem) -> str
        # [path] lines=N commits=M last_modified=...
        # <file content, truncated to budget>
```

**Reused from Customer Voice** (same pattern):

- `ExplorerResult` dataclass (imported from customer_voice module)
- `_map_confidence()` helper (extract to shared location or copy)
- Error handling: per-batch try/except, synthesis fallback
- Coverage invariant: reviewed + skipped == available
- LLM calling: `response_format={"type": "json_object"}`

**Different from Customer Voice**:

- `_format_file()` instead of `_format_conversation()`
- Evidence key in LLM output: `evidence_file_paths` instead of `evidence_conversation_ids`
- `agent_name: "codebase"` in checkpoint
- `source_type: SourceType.CODEBASE` in evidence pointers

### 3. Prompt additions to `src/discovery/agents/prompts.py`

Six new prompt constants:

**CODEBASE_BATCH_ANALYSIS_SYSTEM**: "You are a senior engineer reviewing
recently-changed source code for patterns — tech debt, architecture
opportunities, recurring complexity, duplicated logic, error-prone patterns,
missing abstractions. NOT classifying into predefined categories. Discovering
patterns from scratch."

**CODEBASE_BATCH_ANALYSIS_USER**: Template with `{batch_size}`,
`{time_window_days}`, `{formatted_files}`. Returns JSON with `findings`
list where each finding has `evidence_file_paths` (not conversation IDs).

**CODEBASE_SYNTHESIS_SYSTEM / \_USER**: Same merge/dedup/reassess pattern
as Customer Voice synthesis.

**CODEBASE_REQUERY_SYSTEM / \_USER**: Follow-up questions about specific
files or patterns.

### 4. `tests/discovery/test_codebase_explorer.py`

Unit tests (~25 tests). Mirrors `test_customer_voice.py` structure.

```python
# Helpers
_make_codebase_item(**overrides) -> CodebaseItem
_make_batch_response(findings=None) -> mock LLM response
_make_synthesis_response(findings=None)
_make_llm_response(content_dict)

class MockCodebaseReader:
    def __init__(self, items=None, count=None)
    def fetch_recently_changed(self, days, limit=None)
    def fetch_file(self, path)
    def get_item_count(self, days)

# Test classes
class TestExplore:          # happy path, empty, multi-batch, token tracking
class TestErrorHandling:    # batch failure, synthesis fallback, invalid JSON
class TestCoverageInvariant:# reviewed + skipped == available
class TestFormatFile:       # truncation, metadata, empty files
class TestBuildCheckpoint:  # valid checkpoint, validates against model, empty findings
class TestRequery:          # with/without file paths
class TestConfidenceMapping:# reuse _map_confidence tests
```

### 5. `tests/discovery/test_codebase_explorer_integration.py`

Integration tests (~5 tests). Mirrors `test_explorer_integration.py`.

```python
@pytest.mark.slow
class TestCodebaseExplorerFullFlow:
    test_codebase_checkpoint_advances_to_opportunity_framing()
    test_checkpoint_events_in_conversation()
    test_empty_findings_checkpoint_still_advances()

@pytest.mark.slow
class TestCodebaseRequeryFlow:
    test_requery_through_conversation()

@pytest.mark.slow
class TestCodebaseTaxonomyGuard:
    test_findings_dont_use_pipeline_categories()
```

---

## File to Modify

### `src/discovery/agents/prompts.py`

Add 6 new constants (CODEBASE_BATCH_ANALYSIS_SYSTEM, \_USER,
CODEBASE_SYNTHESIS_SYSTEM, \_USER, CODEBASE_REQUERY_SYSTEM, \_USER).
No changes to existing constants.

---

## Shared Code Decision: `_map_confidence`

The `_map_confidence()` function currently lives in `customer_voice.py`.
The codebase explorer needs the same function.

**Decision**: Copy the function into `codebase_explorer.py` as a module-level
helper (same pattern as Customer Voice). This avoids creating a shared
utility for two callers, which would be premature abstraction. If a third
explorer needs it, extract then.

Similarly, `ExplorerResult` is defined in `customer_voice.py`. Rather than
creating a shared module prematurely, re-define it in `codebase_explorer.py`
(identical dataclass). When the orchestrator (#225) exists, it can extract
shared types if needed.

---

## Implementation Order

1. **CodebaseReader + CodebaseItem** (`codebase_data_access.py`)
   - Data access layer, git integration, file reading
   - No LLM dependency — testable in isolation

2. **Prompts** (add to `prompts.py`)
   - 6 new constants, no changes to existing

3. **CodebaseExplorer** (`codebase_explorer.py`)
   - Explorer agent following Customer Voice pattern
   - Depends on reader and prompts

4. **Unit tests** (`test_codebase_explorer.py`)
   - Mock reader + mock LLM client
   - ~25 tests covering all paths

5. **Integration tests** (`test_codebase_explorer_integration.py`)
   - Full state machine flow with InMemoryStorage/Transport
   - ~5 tests

6. **Verification**
   - `pytest tests/discovery/ -v` — all discovery tests pass
   - `pytest -m "not slow"` — no regressions in fast suite

---

## Acceptance Criteria

1. `CodebaseReader.fetch_recently_changed()` returns files changed in the
   last N days, excluding test/config/binary files
2. `CodebaseExplorer.explore()` produces an `ExplorerResult` with findings
   and coverage metadata
3. Coverage invariant holds: `reviewed + skipped == available`
4. `build_checkpoint_artifacts()` produces output that validates against
   `ExplorerCheckpoint` model
5. Per-batch errors are caught and don't abort the run
6. Synthesis failure falls back to raw batch findings
7. Checkpoint submission advances state machine to OPPORTUNITY_FRAMING
8. Taxonomy guard passes: no pipeline vocabulary in output
9. All existing discovery tests continue to pass (258 tests)
10. New tests: ~25 unit + ~5 integration = ~30 total

---

## Risks and Mitigations

| Risk                                                      | Mitigation                                                                                                            |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `subprocess.run` for git could be slow on large repos     | Limit to `src/` scope, cap at 100 files                                                                               |
| Binary file detection could miss edge cases               | Use `.suffix` allowlist (.py, .ts, .js, .tsx, .jsx, .json, .yaml, .yml, .md, .sql, .html, .css) rather than blocklist |
| LLM produces shallow "this function is long" observations | Prompt explicitly demands actionable patterns with impact assessment                                                  |
| File content too large for LLM context                    | 3000 char budget per file, batch size of 10                                                                           |

---

## Out of Scope

- Multi-explorer orchestration (Issue #225)
- Functional testing against real codebase (would need functional test plan)
- Changes to CoverageMetadata model (defer to when 3+ explorers exist)
- Git blame analysis (defer to iteration)
- Hotspot detection beyond recency (defer to iteration)
