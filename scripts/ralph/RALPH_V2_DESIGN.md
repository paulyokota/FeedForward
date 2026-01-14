# Ralph V2 Architecture Design

**Version**: 2.0 Draft
**Date**: 2026-01-13
**Status**: Design Review

---

## Executive Summary

Ralph V2 shifts from **story-level refinement** to **pipeline-level optimization**. Instead of manually editing individual stories, Ralph modifies the Feed Forward pipeline itself - prompts, extraction logic, grouping rules - and measures the impact on story quality. Learnings are captured as code changes, not documentation.

---

## Problem Statement

### Ralph V1 Limitations

1. **Learnings don't persist** - Story edits die with those stories; improvements don't transfer to future batches
2. **Manual, not scalable** - Each story requires individual attention
3. **Documentation-heavy** - Progress tracked in text files, not code
4. **Single data source** - Only handles one type of feedback at a time

### Ralph V2 Goals

1. **Pipeline optimization** - Changes to prompts/logic apply to ALL future stories
2. **Learnings as code** - Improvements are committed to git, version controlled
3. **Multi-source support** - Works with Intercom, Coda tables, and Coda pages
4. **Autonomous operation** - Runs multiple iterations without human intervention
5. **Holistic quality measurement** - Gestalt comparison, not just dimension gaming

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        RALPH V2 LOOP                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  Test Data   │───▶│   Pipeline   │───▶│   Stories    │      │
│  │  (3 sources) │    │   Execution  │    │   Output     │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         │                   │                   ▼               │
│         │                   │          ┌──────────────┐        │
│         │                   │          │  Evaluation  │        │
│         │                   │          │  Framework   │        │
│         │                   │          └──────────────┘        │
│         │                   │                   │               │
│         │                   │                   ▼               │
│         │                   │          ┌──────────────┐        │
│         │                   ◀──────────│   Pipeline   │        │
│         │                              │ Modification │        │
│         │                              └──────────────┘        │
│         │                                      │               │
│         │                                      ▼               │
│         │                              ┌──────────────┐        │
│         └──────────────────────────────│  Git Commit  │        │
│                                        └──────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase Breakdown

### Phase 0: Context Loading

Ralph reads:

1. **Current pipeline code** - prompts, extraction logic, grouping rules
2. **Gold standard reference** - `docs/story_knowledge_base.md`
3. **Test data manifest** - available sample data from all sources
4. **Previous iteration results** - what was tried, what worked

**Key Files:**

```
src/prompts/                    # Classification and extraction prompts
src/theme_extractor.py          # Extraction logic
src/story_grouper.py            # Grouping logic (if exists)
docs/story_knowledge_base.md    # Gold standard for story structure
scripts/ralph/test_data/        # Sample feedback from all sources
scripts/ralph/progress.txt      # Iteration history
```

### Phase 1: Pipeline Execution

Run the current pipeline on test data to produce stories.

**Test Data Sources:**
| Source | Location | Format |
|--------|----------|--------|
| Intercom | `test_data/intercom/` | Conversation JSON |
| Coda Tables | `test_data/coda_tables/` | Table rows JSON |
| Coda Pages | `test_data/coda_pages/` | Page content MD |

**Output:**

- Generated stories in standardized format
- Execution metrics (time, tokens used, errors)

### Phase 2: Evaluation Framework

Three-tier evaluation:

#### Tier 1: Gestalt Comparison (PRIMARY)

**LLM-as-Judge approach:**

Compare each generated story holistically against gold standard examples. NOT dimension-by-dimension, but "does this feel like a well-formed story?"

```
Prompt structure:
- Here is the gold standard story format: [story_knowledge_base.md examples]
- Here is the generated story: [output]
- Rate overall alignment on 1-5 scale
- Explain what's working and what's not
- Do NOT score individual dimensions
```

**Why gestalt is primary:**

- Prevents Goodhart's Law (gaming individual metrics)
- Captures holistic quality that dimensions miss
- Aligns with human judgment of "good story"

**Target:** >= 4.0 average gestalt across all generated stories

#### Tier 2: Dimensional Analysis (DIAGNOSTIC)

INVEST dimensions scored **for diagnostic purposes only**, not as optimization targets:

- **I**ndependent - Can be developed alone?
- **N**egotiable - Room for engineering judgment?
- **V**aluable - Clear user value?
- **E**stimable - Can estimate effort?
- **S**mall - Completable in 1-3 days?
- **T**estable - Verifiable acceptance criteria?

**Use:** Identify WHICH aspect needs improvement when gestalt is low.
**NOT used as:** Primary success metric.

#### Tier 3: Technical Validation (Playwright)

Verify that stories reference real, accessible code locations.

**Process:**

1. Extract `technical_area` from each story
2. Run Playwright validation against GitHub repos
3. Confirm developer could navigate to investigate

**Target:** >= 85% of technical areas validate successfully

### Phase 3: Gap Analysis

When evaluation scores are below threshold, identify the root cause:

**Question tree:**

```
Is gestalt low?
├── YES → Which aspects feel wrong?
│   ├── Structure? → Check prompt output format instructions
│   ├── Technical depth? → Check extraction logic
│   ├── Actionability? → Check grouping logic
│   └── Clarity? → Check prompt language
└── NO → Check dimensional diagnostics
    └── Which dimension is lowest?
        ├── I (Independent) → Grouping creating dependencies?
        ├── N (Negotiable) → Prompts too prescriptive?
        ├── V (Valuable) → Extraction missing user pain?
        ├── E (Estimable) → Missing technical context?
        ├── S (Small) → Grouping too broad?
        └── T (Testable) → Prompts not generating criteria?
```

**Output:** Specific pipeline component to modify + hypothesis for improvement

### Phase 4: Pipeline Modification

Make targeted changes to the identified component:

**Modifiable Components:**
| Component | Location | What to Change |
|-----------|----------|----------------|
| Classification prompts | `src/prompts/classify.py` | Theme detection, categorization |
| Extraction prompts | `src/prompts/extract.py` | Story generation, acceptance criteria |
| Theme extractor | `src/theme_extractor.py` | Processing logic, filtering |
| Story grouper | `src/story_grouper.py` | Grouping rules, similarity thresholds |
| Output formatter | `src/formatters/` | Story structure, field mapping |

**Change Guidelines:**

1. One component per iteration (isolate variables)
2. Small, testable changes
3. Document hypothesis: "I expect this change to improve X because Y"
4. Preserve ability to rollback

### Phase 5: Commit & Loop

1. **Stage changes** - Only modified pipeline files
2. **Commit with context:**

   ```
   Ralph V2: [component] - [hypothesis]

   Iteration: N
   Before: gestalt X.X, playwright Y%
   Change: [specific modification]
   Expected: [improvement hypothesis]

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
   ```

3. **Update progress.txt** with iteration results
4. **Loop back to Phase 1** with modified pipeline

---

## Playwright Session Persistence

### Problem

Current implementation requires login on every validation run, breaking autonomous operation.

### Solution

Use Playwright's storage state persistence:

```python
# First run - interactive login, save state
browser = playwright.chromium.launch(headless=False)
context = browser.new_context()
# ... user logs in ...
context.storage_state(path="outputs/playwright_state.json")

# Subsequent runs - load saved state
context = browser.new_context(storage_state="outputs/playwright_state.json")
# ... already authenticated ...
```

### Implementation in ralph.sh

```bash
# At loop start
STORAGE_STATE="${OUTPUT_DIR}/playwright_state.json"

if [ ! -f "$STORAGE_STATE" ]; then
    echo "No saved session. Opening browser for initial login..."
    python3 scripts/ralph/init_playwright_session.py
fi

# Pass to validation script
python3 validate_playwright.py --storage-state "$STORAGE_STATE" ...
```

### Session Expiry Handling

If validation detects login page (session expired):

1. Pause and notify user
2. Open browser for re-authentication
3. Save new state
4. Resume validation

---

## Test Data Harness

### Directory Structure

```
scripts/ralph/test_data/
├── manifest.json              # Lists all available test data
├── intercom/
│   ├── sample_001.json        # Conversation about OAuth issues
│   ├── sample_002.json        # Conversation about AI features
│   └── ...
├── coda_tables/
│   ├── user_feedback.json     # Extracted table rows
│   └── feature_requests.json  # Feature request data
└── coda_pages/
    ├── research_findings.md   # Full page content
    └── interview_notes.md     # Interview summaries
```

### manifest.json Schema

```json
{
  "version": "1.0",
  "sources": [
    {
      "type": "intercom",
      "path": "intercom/sample_001.json",
      "description": "Pinterest OAuth failure reports",
      "expected_themes": ["oauth", "pinterest", "authentication"],
      "complexity": "medium"
    },
    {
      "type": "coda_table",
      "path": "coda_tables/user_feedback.json",
      "description": "AI copilot feedback from Coda research",
      "expected_themes": ["ai", "ghostwriter", "brand-voice"],
      "complexity": "high"
    }
  ]
}
```

### Test Runner

```python
# scripts/ralph/run_pipeline_test.py

def run_test(source_path, pipeline_version):
    """Run pipeline on test data and return evaluation metrics."""

    # Load test data
    data = load_source(source_path)

    # Run current pipeline
    stories = pipeline.generate_stories(data)

    # Evaluate
    gestalt_scores = evaluate_gestalt(stories, GOLD_STANDARD)
    dimensional_scores = evaluate_dimensions(stories)
    playwright_results = validate_playwright(stories)

    return {
        "gestalt_avg": mean(gestalt_scores),
        "dimensional_avg": mean(dimensional_scores),
        "playwright_pct": playwright_results["success_rate"],
        "stories": stories,
        "details": {...}
    }
```

---

## Success Criteria

### Per-Iteration

| Metric                | Target | Purpose                 |
| --------------------- | ------ | ----------------------- |
| Gestalt Average       | >= 4.0 | Primary quality measure |
| Playwright Validation | >= 85% | Technical accuracy      |
| Pipeline Change       | >= 1   | Ensures progress        |

### Loop Completion

All of the following must be true:

1. Gestalt average >= 4.0 across all test data sources
2. Playwright validation >= 85%
3. No source type has gestalt < 3.5 (ensures generalization)
4. At least one pipeline change was committed this session

### Plateau Conditions

Output `<promise>PLATEAU_REACHED</promise>` if:

- 5+ iterations without gestalt improvement
- Pipeline changes causing regressions
- Architectural limitation identified (requires human design)

---

## Iteration Work Gate (Carried from V1)

Before ANY completion promise, verify:

- [ ] At least one pipeline component was modified
- [ ] Changes were committed to git
- [ ] Evaluation was run on ALL test data sources
- [ ] Results show improvement OR documented why not possible

---

## Migration Plan

### Phase 1: Infrastructure (This Session)

1. Create `test_data/` directory with sample data
2. Update `validate_playwright.py` for session persistence
3. Create `init_playwright_session.py` for first-run auth
4. Draft new PROMPT_V2.md

### Phase 2: Test Harness (Next Session)

1. Create `run_pipeline_test.py`
2. Implement gestalt evaluation prompt
3. Create `manifest.json` with initial test cases
4. Validate harness works end-to-end

### Phase 3: Loop Integration (Following Session)

1. Update `ralph.sh` for V2 flow
2. Replace PROMPT.md with PROMPT_V2.md
3. Test full loop with 2-3 iterations
4. Refine based on results

---

## Open Questions

1. **Test data volume** - How many samples per source type? (Suggest: 3-5 per source)
2. **Gestalt prompt tuning** - How to calibrate LLM-as-judge for consistency?
3. **Rollback mechanism** - How does Ralph revert a bad pipeline change?
4. **Parallel evaluation** - Can we evaluate multiple sources simultaneously?

---

## Appendix: Example Iteration Log

```
=== Ralph V2 Iteration 3 ===

**Phase 1: Pipeline Execution**
- Ran on: 3 Intercom, 2 Coda tables, 1 Coda page
- Stories generated: 8
- Execution time: 45 seconds

**Phase 2: Evaluation**
- Gestalt average: 3.7 (target: 4.0) ❌
- Playwright: 87.5% (target: 85%) ✓
- Lowest source: Coda pages (gestalt 3.2)

**Phase 3: Gap Analysis**
- Coda page stories lack actionability
- Root cause: Extraction prompt doesn't handle long-form content
- Hypothesis: Add chunking for pages > 2000 words

**Phase 4: Modification**
- File: src/prompts/extract.py
- Change: Added content chunking for long documents
- Lines modified: 45-67

**Phase 5: Commit**
- Hash: abc123
- Message: "Ralph V2: extract.py - chunk long documents for better extraction"

**Decision: CONTINUE** (gestalt below 4.0)
```

---

_Design by Claude Opus 4.5 - Feed Forward Project_
