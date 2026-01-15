# Architecture: Dual-Format Story Output with Agent SDK Codebase Context

**Status**: Approved
**Issue**: #37
**Date**: 2026-01-15

---

## Overview

This architecture adds dual-format story output (Human + AI sections) and codebase-aware context using the Claude Agent SDK for agentic exploration of locally cloned repositories.

---

## Key Decisions

| Decision                      | Choice                   | Rationale                                                                 |
| ----------------------------- | ------------------------ | ------------------------------------------------------------------------- |
| Primary exploration mechanism | Claude Agent SDK         | Same quality as Claude Code, dynamic adaptation, maintained by Anthropic  |
| Phasing                       | Agent SDK from Phase 1   | Avoid tuning against wrong foundation, static map chases invalid patterns |
| Repo sync interval            | 6 hours (background job) | Codebase doesn't change frequently, acceptable staleness                  |
| Static codebase map role      | Supplementary/fallback   | Enriches with stable references (table names, API patterns)               |

---

## Security Requirements (Implementation)

These are NOT phase-gates. Implement during Phase 1.

### 1. Path Validation

```python
REPO_BASE_PATH = Path(os.environ.get("FEEDFORWARD_REPOS_PATH", "/Users/paulyokota/repos"))
APPROVED_REPOS = {"aero", "tack", "charlotte", "ghostwriter", "zuck"}

def validate_path(path: str) -> bool:
    """Ensure path is within approved repo directories."""
    resolved = Path(path).resolve()
    return resolved.is_relative_to(REPO_BASE_PATH)
```

### 2. Command Injection Protection

```python
def ensure_repo_fresh(self, repo_name: str) -> SyncResult:
    if repo_name not in APPROVED_REPOS:
        raise ValueError(f"Unauthorized repo: {repo_name}")

    # Use subprocess with shell=False and list args (never shell=True)
    subprocess.run(["git", "-C", repo_path, "fetch"], shell=False, timeout=30)
```

### 3. Secrets Redaction

```python
BLACKLIST_PATTERNS = [".env*", "*secrets*", "*credentials*", "*.pem", "*.key"]
REDACTION_REGEX = r"(api_key|password|token|secret)\s*[=:]\s*['\"][^'\"]+['\"]"

def filter_exploration_results(results: dict) -> dict:
    """Filter out sensitive files and redact secrets from code snippets."""
    # Implementation details in src/codebase_context.py
```

---

## Architecture Components

### 1. CodebaseContextProvider

**File**: `src/story_tracking/services/codebase_context_provider.py`

**Responsibilities**:

- Background repo sync (every 6 hours) with timing metrics
- Agentic exploration using Agent SDK tools (Glob, Grep, Read)
- Path validation and secrets redaction
- Static context fallback from codebase map

### 2. DualStoryFormatter

**File**: `src/story_formatter.py` (enhanced)

**Responsibilities**:

- Human section: Customer evidence, symptoms, user intent
- AI section: Codebase context, implementation suggestions (third-person framing)
- Metadata and branding footer

### 3. Background Sync Service

**File**: `src/services/repo_sync_service.py`

**Responsibilities**:

- Scheduled git fetch/pull every 6 hours
- Timing metrics logging to database
- Error handling and alerting

### 4. Database Schema Changes

**Migration**: `src/db/migrations/XXX_add_dual_format_support.sql`

```sql
ALTER TABLE stories
ADD COLUMN format_version VARCHAR(10) DEFAULT 'v1',
ADD COLUMN ai_section TEXT,
ADD COLUMN codebase_context JSONB;

CREATE TABLE repo_sync_metrics (
    id UUID PRIMARY KEY,
    repo_name VARCHAR(50) NOT NULL,
    fetch_duration_ms INTEGER,
    pull_duration_ms INTEGER,
    total_duration_ms INTEGER,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Data Flow

```
Theme Extraction
       ↓
CodebaseContextProvider
  ├── Background: Repo sync (every 6h)
  ├── On-demand: Agent SDK exploration
  └── Fallback: Static codebase map
       ↓
DualStoryFormatter
  ├── Human section (evidence, symptoms)
  └── AI section (codebase context)
       ↓
StoryCreationService
  └── Store with format_version='v2'
```

---

## Implementation Plan

### Phase 1: Core Infrastructure

| Task                                        | Owner   | Parallelizable? | Dependencies |
| ------------------------------------------- | ------- | --------------- | ------------ |
| 1.1 Create CodebaseContextProvider skeleton | Backend | Yes             | None         |
| 1.2 Add path validation and security        | Backend | Yes             | None         |
| 1.3 Database migrations                     | Backend | Yes             | None         |
| 1.4 Background sync service                 | Backend | Yes             | 1.3          |
| 1.5 Unit tests for security functions       | Testing | Yes             | 1.2          |

### Phase 2: Agent SDK Integration

| Task                                  | Owner      | Parallelizable? | Dependencies |
| ------------------------------------- | ---------- | --------------- | ------------ |
| 2.1 Agent SDK exploration task spec   | Prompt Eng | Yes             | 1.1          |
| 2.2 Implement explore_for_theme()     | Backend    | No              | 2.1, 1.2     |
| 2.3 Secrets redaction implementation  | Backend    | Yes             | 1.2          |
| 2.4 Integration tests with real repos | Testing    | No              | 2.2          |

### Phase 3: Dual Format Integration

| Task                                    | Owner      | Parallelizable? | Dependencies |
| --------------------------------------- | ---------- | --------------- | ------------ |
| 3.1 DualStoryFormatter implementation   | Backend    | Yes             | None         |
| 3.2 AI section template refinement      | Prompt Eng | Yes             | None         |
| 3.3 Integrate with StoryCreationService | Backend    | No              | 3.1, 2.2     |
| 3.4 End-to-end tests                    | Testing    | No              | 3.3          |

### Phase 4: Validation

| Task                               | Owner   | Parallelizable? | Dependencies |
| ---------------------------------- | ------- | --------------- | ------------ |
| 4.1 Run with real theme data       | All     | No              | 3.4          |
| 4.2 PM quality review (50 stories) | PM      | No              | 4.1          |
| 4.3 Performance tuning             | Backend | No              | 4.1          |
| 4.4 Documentation update           | Docs    | Yes             | 4.1          |

---

## Parallelization Strategy

**Parallel Work Streams:**

1. **Backend Infrastructure** (Tasks 1.1-1.4, 2.2-2.3, 3.1, 3.3)
2. **Prompt Engineering** (Tasks 2.1, 3.2)
3. **Testing** (Tasks 1.5, 2.4, 3.4)
4. **Documentation** (Task 4.4)

**Max Parallelization**: Phase 1 tasks can run in parallel. Phase 2/3 have dependencies but multiple streams can progress simultaneously.

---

## Success Criteria

| Metric                  | Target               | Measurement                 |
| ----------------------- | -------------------- | --------------------------- |
| Story format compliance | 100%                 | Automated schema validation |
| AI section quality      | >70% PM satisfaction | 50-story review             |
| Exploration latency     | <30s per theme       | Performance logs            |
| Security violations     | 0                    | Audit logs                  |
| Sync job reliability    | >99% uptime          | Monitoring                  |

---

## Key Resources

- GitHub Issue #37: https://github.com/paulyokota/FeedForward/issues/37
- Mock Example: `docs/examples/dual-format-story-example.md`
- Story Knowledge Base: `docs/story_knowledge_base.md`
- Agent SDK Docs: https://platform.claude.com/docs/en/agent-sdk/overview

---

## Revision History

| Date       | Change                                    | Author                   |
| ---------- | ----------------------------------------- | ------------------------ |
| 2026-01-15 | Initial architecture (Priya)              | Architect                |
| 2026-01-15 | Override: Agent SDK from Phase 1          | Product Lead + Tech Lead |
| 2026-01-15 | Security review additions                 | Code Reviewer            |
| 2026-01-15 | Finalized: 6h sync, security requirements | Product Lead             |
