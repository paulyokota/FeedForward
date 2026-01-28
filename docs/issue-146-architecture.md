# Issue #146 Architecture: LLM-Powered Resolution/Knowledge Extraction

> Replace regex-based `ResolutionAnalyzer` and `KnowledgeExtractor` with LLM-powered extraction in the theme extractor.

**Branch:** `feature/146-llm-resolution-extraction`
**Issue:** [#146](https://github.com/paulyokota/FeedForward/issues/146)

---

## Executive Summary

Replace the pattern-matching `ResolutionAnalyzer` (14% coverage) and `KnowledgeExtractor` (8% coverage) with LLM-powered extraction in the theme extraction prompt. The LLM already has full conversation context—we're just not asking it to extract resolution/knowledge signals.

**Goal:** Improve coverage from 8-14% to >80-90%, enabling richer downstream decisions in PM Review and Story Creation.

---

## Decisions (Tech Lead)

| Question                             | Decision                           | Rationale                                                                   |
| ------------------------------------ | ---------------------------------- | --------------------------------------------------------------------------- |
| A/B test Stage 2 with/without hints? | **No**                             | Stage 2 already gets full conversation; 14% hint coverage wasn't meaningful |
| Downstream scope?                    | **PM Review + Story Creation**     | Minimum viable; Search/Analytics can follow                                 |
| Historical backfill?                 | **No**                             | Pre-prod; old data likely wiped after reviewing run #94 results             |
| Phase 2 timing?                      | **Explicit Tech Lead green light** | Pipeline #94 active; migration blocked until confirmed complete             |

---

## Architecture Overview

### Current State

```
Classification Pipeline
┌─────────────────────────────────────────────────────────┐
│  1. Stage 1 LLM Classification                          │
│  2. ResolutionAnalyzer (REGEX) ─┐                       │
│  3. Stage 2 LLM ←───────────────┘ uses as HINT (14%)    │
│  4. KnowledgeExtractor (REGEX) → stored, NEVER READ     │
│  5. Store in support_insights                           │
└─────────────────────────────────────────────────────────┘
                        ↓
Theme Extraction
┌─────────────────────────────────────────────────────────┐
│  Extracts: themes, diagnostic_summary, key_excerpts     │
│  DOES NOT: resolution, root_cause, solution             │
└─────────────────────────────────────────────────────────┘
                        ↓
PM Review → Story Creation (limited context)
```

### Target State

```
Classification Pipeline (simplified)
┌─────────────────────────────────────────────────────────┐
│  1. Stage 1 LLM Classification                          │
│  2. Stage 2 LLM (NO resolution hint needed)             │
│  3. Store in support_insights (no resolution/knowledge) │
└─────────────────────────────────────────────────────────┘
                        ↓
Theme Extraction (enriched)
┌─────────────────────────────────────────────────────────┐
│  Extracts: themes, diagnostic_summary, key_excerpts     │
│  NEW: resolution_action, root_cause, solution_provided, │
│       resolution_category                               │
└─────────────────────────────────────────────────────────┘
                        ↓
PM Review → Story Creation (rich resolution context)
```

---

## Implementation Phases

### Phase 1: Code Changes (Safe Now)

No database schema modifications. Can proceed immediately.

#### Phase 1A: Remove Regex Extractors (Marcus)

**Files to MODIFY:**

| File                             | Change                                                              |
| -------------------------------- | ------------------------------------------------------------------- |
| `src/classification_pipeline.py` | Remove `ResolutionAnalyzer`, `KnowledgeExtractor` imports and usage |
| `src/classifier_stage2.py`       | Remove `resolution_signal` parameter and prompt section             |
| `src/classification_manager.py`  | Remove regex extractor imports and usage                            |

**Files to DELETE:**

| File                              | Reason                     |
| --------------------------------- | -------------------------- |
| `src/resolution_analyzer.py`      | Replaced by LLM extraction |
| `src/knowledge_extractor.py`      | Replaced by LLM extraction |
| `config/resolution_patterns.json` | No longer needed           |

#### Phase 1B: Add LLM Extraction to Theme Extractor (Kai)

**Files to MODIFY:**

| File                     | Change                                                              |
| ------------------------ | ------------------------------------------------------------------- |
| `src/theme_extractor.py` | Add 4 new fields to `Theme` dataclass and `THEME_EXTRACTION_PROMPT` |

**New Fields:**

```python
# In Theme dataclass
resolution_action: str = ""      # escalated_to_engineering | provided_workaround | user_education | manual_intervention | no_resolution
root_cause: str = ""             # 1-sentence LLM hypothesis
solution_provided: str = ""      # 1-2 sentence solution description
resolution_category: str = ""    # escalation | workaround | education | self_service_gap | unresolved
```

**Prompt Additions:**

```
13. **resolution_action**: What action did support take to resolve this? (pick ONE)
    - escalated_to_engineering: Created ticket, reported to dev team
    - provided_workaround: Gave temporary solution
    - user_education: Explained how to use feature correctly
    - manual_intervention: Support did something user couldn't (cancelled, refunded, etc.)
    - no_resolution: Issue unresolved or conversation ongoing

14. **root_cause**: Your hypothesis for WHY this happened (1 sentence max)
    - Technical: bug, integration failure, API change, performance issue
    - UX: confusing interface, unclear documentation, hidden feature
    - User error: misunderstanding, wrong expectations
    - null if insufficient information

15. **solution_provided**: If resolved, what was the solution? (1-2 sentences max)
    - Include specific steps if a workaround was given
    - null if unresolved or no clear solution

16. **resolution_category**: Category for analytics (pick ONE)
    - escalation: Required engineering involvement
    - workaround: Temporary fix provided
    - education: User needed guidance
    - self_service_gap: Manual support for something that could be automated
    - unresolved: No resolution achieved
```

#### Phase 1C: Update PM Review + Story Creation (Marcus + Kai)

**Files to MODIFY:**

| File                                                    | Change                                           | Owner  |
| ------------------------------------------------------- | ------------------------------------------------ | ------ |
| `src/story_tracking/services/pm_review_service.py`      | Add 4 new fields to `ConversationContext`        | Marcus |
| `src/prompts/pm_review.py`                              | Update prompt template to display new fields     | Kai    |
| `src/story_tracking/services/story_creation_service.py` | Include resolution context in story descriptions | Marcus |
| `src/prompts/story_content.py`                          | Update story template with resolution fields     | Kai    |

#### Phase 1D: Tests (Kenji)

**Files to UPDATE/DELETE:**

| File                                          | Change                                        |
| --------------------------------------------- | --------------------------------------------- |
| `tests/test_pipeline_integration_insights.py` | Delete/repurpose tests for removed extractors |

**Files to CREATE:**

| File                                       | Purpose                                               |
| ------------------------------------------ | ----------------------------------------------------- |
| Integration test for resolution field flow | Verify: theme extraction → PM Review → Story Creation |

---

### Phase 2: Database Migration (BLOCKED)

**Status:** ❌ Requires explicit Tech Lead green light

**Blocker:** Pipeline run #94 is active in `theme_extraction` phase.

#### Phase 2A: Add Columns to Themes Table

**Migration file:** `src/db/migrations/018_llm_resolution_fields.sql`

```sql
-- Migration 018: LLM-Powered Resolution Extraction (Issue #146)

ALTER TABLE themes ADD COLUMN IF NOT EXISTS resolution_action VARCHAR(50);
ALTER TABLE themes ADD COLUMN IF NOT EXISTS root_cause TEXT;
ALTER TABLE themes ADD COLUMN IF NOT EXISTS solution_provided TEXT;
ALTER TABLE themes ADD COLUMN IF NOT EXISTS resolution_category VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_themes_resolution_category
    ON themes(resolution_category)
    WHERE resolution_category IS NOT NULL;
```

---

## Agent Assignments

### Kai (Prompt Engineering)

**Owns:**

- `src/theme_extractor.py` - Prompt and Theme dataclass
- `src/prompts/pm_review.py` - PM Review prompt template
- `src/prompts/story_content.py` - Story content template

**Must Not Touch:**

- `classification_pipeline.py`, `classifier_stage2.py` (Marcus)
- Database migrations (Marcus + Tech Lead)

**Acceptance Criteria:**

- [ ] Theme dataclass has 4 new fields with proper defaults
- [ ] Prompt extracts all 4 fields with valid enum values
- [ ] PM Review prompt displays new fields
- [ ] Story content template includes resolution context
- [ ] Unit tests pass for new field extraction

### Marcus (Backend)

**Owns:**

- `src/classification_pipeline.py` - Remove regex extraction
- `src/classifier_stage2.py` - Remove resolution_signal
- `src/classification_manager.py` - Remove regex extraction
- `src/story_tracking/services/pm_review_service.py` - Update ConversationContext
- `src/story_tracking/services/story_creation_service.py` - Wire resolution fields

**Deletes:**

- `src/resolution_analyzer.py`
- `src/knowledge_extractor.py`
- `config/resolution_patterns.json`

**Creates (Phase 2):**

- `src/db/migrations/018_llm_resolution_fields.sql`

**Acceptance Criteria:**

- [ ] Classification pipeline runs without regex extractors
- [ ] Stage 2 works without resolution_signal hint
- [ ] PM Review service receives new resolution fields
- [ ] Story creation includes resolution context
- [ ] All existing tests pass

### Kenji (Testing)

**Owns:**

- `tests/` - All test files

**Acceptance Criteria:**

- [ ] Tests for removed extractors deleted/repurposed
- [ ] Integration test verifies full data flow: theme extraction → PM Review → Story Creation
- [ ] No regressions in existing functionality

---

## Implementation Order

```
     Phase 1A (Marcus)              Phase 1B (Kai)
     Remove regex extractors        Add LLM extraction
              │                            │
              │         PARALLEL           │
              └────────────┬───────────────┘
                           │
                           ▼
                    Phase 1C (Both)
                    PM Review + Story Creation
                           │
                           ▼
                    Phase 1D (Kenji)
                    Tests + Integration
                           │
                           ▼
              ╔════════════════════════════════╗
              ║   TECH LEAD GATE               ║
              ║   Explicit green light for     ║
              ║   Phase 2 migration            ║
              ╚════════════════════════════════╝
                           │
                           ▼
                    Phase 2A (Marcus)
                    Run database migration
```

**Parallel:** 1A and 1B have no file conflicts
**Sequential:** 1C requires 1A+1B; 1D requires 1C; Phase 2 requires Tech Lead approval

---

## Interface Contracts

### Theme Dataclass (Updated)

```python
@dataclass
class Theme:
    # ... existing fields ...

    # Issue #146: LLM-powered resolution extraction
    resolution_action: str = ""      # escalated_to_engineering | provided_workaround | user_education | manual_intervention | no_resolution
    root_cause: str = ""             # 1-sentence LLM hypothesis
    solution_provided: str = ""      # 1-2 sentence solution description
    resolution_category: str = ""    # escalation | workaround | education | self_service_gap | unresolved
```

### ConversationContext (Updated)

```python
@dataclass
class ConversationContext:
    # ... existing fields ...

    # Issue #146: LLM-extracted resolution context
    resolution_action: str = ""
    root_cause: str = ""
    solution_provided: str = ""
    resolution_category: str = ""
```

---

## Integration Test Requirements

Per `integration-testing-gate.md`, cross-component data flow requires full-path tests.

| Test                                            | Verifies                                     |
| ----------------------------------------------- | -------------------------------------------- |
| `test_resolution_fields_extracted`              | Theme extractor populates 4 new fields       |
| `test_resolution_fields_flow_to_pm_review`      | PM Review receives new fields                |
| `test_resolution_fields_flow_to_story_creation` | Story creation uses new fields               |
| `test_classification_without_regex`             | Pipeline works without deprecated extractors |

---

## Risk Assessment

| Risk                             | Likelihood | Impact | Mitigation                                                   |
| -------------------------------- | ---------- | ------ | ------------------------------------------------------------ |
| Stage 2 quality degrades         | Low        | Medium | Hint was 14% coverage; Stage 2 sees full conversation anyway |
| LLM extraction quality low       | Medium     | Medium | Sample review after Phase 1B; target >80% vs current 14%     |
| Migration during active pipeline | N/A        | High   | **Hard blocked** until Tech Lead green light                 |

---

## Success Metrics

| Metric                       | Current (Regex)         | Target (LLM)             |
| ---------------------------- | ----------------------- | ------------------------ |
| `root_cause` coverage        | 8%                      | >80%                     |
| `resolution_action` coverage | 14%                     | >90%                     |
| PM Review context            | diagnostic_summary only | + root cause, resolution |
| Story descriptions           | symptoms only           | + root cause, solution   |
