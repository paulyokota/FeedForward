# Codebase Search Optimization - Validation-Driven Development Architecture

## Problem Statement

The dual-format story generation pipeline includes codebase exploration to find relevant code for engineering stories. Currently, the search logic uses hardcoded patterns and heuristics that may not find the most relevant files or may return noise.

**Goal**: Apply Validation-Driven Development (VDD) to systematically improve the codebase search precision and recall through iterative testing and evaluation.

## Design Principles

1. **LLM-as-Judge Evaluation**: Use Claude Code as the evaluator since it can navigate the actual codebase to verify relevance, rather than isolated API calls guessing from snippets.

2. **Hybrid Scoring**: Dimensional scores for apples-to-apples comparison across iterations, plus overall gestalt to catch unexpected issues.

3. **Sufficient Sample Size**: Use enough conversations per iteration to distinguish real patterns from noise, avoiding logic swings based on thin data.

4. **Independent Validation**: Evaluator explores codebase independently before judging our results, preventing confirmation bias.

5. **Multi-Repo Support**: Target all approved Tailwind codebases (aero, tack, charlotte, ghostwriter, zuck), not just a single repo.

6. **Dual Exploration for Consistency**: Run independent exploration twice and use the union to create stable ground truth, mitigating non-deterministic evaluator behavior.

7. **Product Area Tracking**: Track metrics separately by product domain to prevent oscillating improvements that help one area while hurting another.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     ITERATION LOOP                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   SEARCH     │──│  EVALUATE    │──│   LEARN      │──→ NEXT   │
│  │   PHASE      │  │   PHASE      │  │   PHASE      │   CYCLE   │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
    Run search         Two-step          Analyze low
    logic on           evaluation:       scores, propose
    conversation       1. Independent    logic changes,
    batch              2. Compare &      commit to
                       Judge             codebase
```

---

## Iteration Zero: Baseline Measurement

Before making any changes to the search logic, run a baseline iteration to establish starting metrics.

### Purpose

- Establish ground truth metrics for current search logic
- Provide reference point for measuring improvement
- Use larger batch size (30-40 conversations) for statistical significance

### Process

1. Pull a large, diverse conversation batch (30-40 conversations)
2. Run current search logic without modifications
3. Execute full evaluation process (dual exploration + judgment)
4. Record baseline precision, recall, and dimensional scores
5. Document baseline per product area

### Exit Criteria

Baseline complete when:

- All conversations processed
- Metrics calculated and recorded
- Per-product-area breakdown documented
- Uncertain classification rate documented as baseline expectation

---

## Phase 1: Search Phase

### Input

- **Conversation Batch**: 15-20 Intercom conversations
  - Pulled fresh each iteration for variability
  - Diverse across product areas (communities, scheduling, analytics, etc.)
  - Mix of bug reports, feature questions, and configuration issues

### Product Area Classification

Each conversation is auto-classified into a product area during search:

| Product Area | Keywords/Signals                                     |
| ------------ | ---------------------------------------------------- |
| Communities  | pins, members, community feed, posts, groups         |
| Scheduling   | calendar, schedule, publish, queue, optimal times    |
| Analytics    | metrics, insights, reports, performance, engagement  |
| Integrations | connect, disconnect, oauth, permissions, third-party |
| Onboarding   | setup, getting started, first time, trial            |
| Uncertain    | Low confidence or conflicting signals                |

**Classification Failure Handling**:

- Tag ambiguous conversations as "uncertain"
- During judge step, evaluator validates classification based on relevant code found
- Track "uncertain" rate as a health metric
- Anomalous scores in a product area trigger classification review

### Process

1. For each conversation, extract the customer issue/symptoms
2. Auto-classify into product area based on keywords
3. Run codebase exploration logic across all approved repos
4. Capture:
   - Files found (path, repo, line numbers)
   - Snippets extracted (code content, context)
   - Search terms used
   - Exploration metadata (glob patterns, grep queries)
   - Product area classification (with confidence)

### Output

```json
{
  "conversation_id": "12345",
  "issue_summary": "Pins not appearing in communities after publishing",
  "product_area": "communities",
  "classification_confidence": 0.85,
  "search_results": {
    "files_found": [...],
    "snippets": [...],
    "search_terms_used": [...],
    "exploration_log": [...]
  }
}
```

---

## Phase 2: Evaluation Phase

### Dual Exploration for Ground Truth Stability

To mitigate non-deterministic evaluator behavior, we run independent exploration **twice** and use the **union** of results as our ground truth.

#### Model Calibration Phase (Iterations 1-2)

During the first two iterations, use different models for each exploration run:

- **Run A**: Claude Opus (higher capability, higher cost)
- **Run B**: Claude Sonnet (lower cost, faster)

Track which files each model finds independently. After two iterations, compare:

- Does Sonnet find roughly the same relevant files as Opus?
- Are there critical files Opus catches that Sonnet misses?

**Calibration Decision**:

Overlap rate = |Sonnet findings ∩ Opus findings| / |Opus findings|

- If overlap >= 90%: Switch to dual-Sonnet for iterations 3+
- If overlap < 90%: Opus consistently finds important things Sonnet misses - keep hybrid approach or Opus-only

### Three-Step Evaluation Process

#### Step 1: Independent Exploration (Run A)

The first evaluator (Claude Code instance) receives ONLY the conversation and issue summary, NOT our search results.

**Evaluator Prompt**:

```
Given this customer issue: "[issue summary]"

Explore the Tailwind codebases (aero, tack, charlotte, ghostwriter, zuck)
to find ALL code that would be relevant to investigating or fixing this issue.

Use your own search strategy. Look for:
- Feature implementations related to the symptoms
- API handlers, services, and data models
- Related configuration and constants
- Test files that reveal expected behavior

Report all relevant files and code sections you find.
```

#### Step 1b: Independent Exploration (Run B)

Run the same exploration prompt with a fresh Claude Code instance. Use a different model during calibration phase (Sonnet vs Opus).

#### Ground Truth Construction

```
ground_truth_files = union(run_a_files, run_b_files)
```

Files found by both runs have higher confidence. Files found by only one run are still included but flagged.

#### Step 2: Compare and Judge

After constructing ground truth from dual exploration, compare with our search results:

| Category                | Definition                    | Action                               |
| ----------------------- | ----------------------------- | ------------------------------------ |
| **Intersection**        | Files found by BOTH us and GT | Validated as relevant                |
| **Our Unique**          | Files only WE found           | Evaluator judges: relevant or noise? |
| **Ground Truth Unique** | Files only in GT (we missed)  | Our misses (recall gap)              |

**File Matching Semantics**: Use exact file path matching (repo + relative path). Example: `aero/app/services/pins_service.rb` must match exactly.

For "Our Unique" files, the evaluator explicitly judges:

```
Ground truth files (from dual exploration): [ground_truth_files]
Our search also found these additional files: [our unique files]

For each of our additional files:
1. Is it relevant to the customer issue? (yes/no)
2. Is it actionable for fixing the bug? (yes/no/maybe)
3. Brief reasoning
```

#### Step 3: Classification Validation

During judgment, the evaluator also validates our product area classification:

```
We classified this conversation as: [product_area]
Based on the relevant code you found, does this classification seem accurate?
If not, what would be a better classification?
```

Track classification mismatches as a health metric.

### Metrics Calculation

**Precision**:

```
precision = (intersection + our_unique_judged_relevant) / total_we_found
```

**Recall**:

```
recall = (intersection + our_unique_relevant) / (intersection + our_unique_relevant + ground_truth_unique)
```

**Dimensional Scores** (1-5 scale):

- **File Relevance**: Are found files actually related to the issue?
- **Snippet Quality**: Are code snippets useful for understanding/fixing?
- **Service Accuracy**: Did we find code in the correct repo/service?
- **Noise Ratio**: How much irrelevant code did we return?
- **Coverage**: Did we find the key files an engineer would need?

**Gestalt Score** (1-5 scale):
Overall quality assessment that can catch issues not covered by dimensional scores.

### Per-Product-Area Metrics

Track precision and recall separately for each product area:

```json
{
  "aggregate": { "precision": 0.75, "recall": 0.68 },
  "by_product_area": {
    "communities": { "precision": 0.82, "recall": 0.71, "count": 5 },
    "scheduling": { "precision": 0.65, "recall": 0.6, "count": 4 },
    "analytics": { "precision": 0.78, "recall": 0.72, "count": 3 },
    "integrations": { "precision": 0.7, "recall": 0.65, "count": 2 },
    "uncertain": { "precision": 0.55, "recall": 0.5, "count": 1 }
  },
  "classification_accuracy": 0.87,
  "uncertain_rate": 0.07
}
```

**Anomaly Detection**: Flag product areas with scores >0.15 below aggregate (absolute difference). For example, if aggregate precision is 0.75, flag any product area with precision < 0.60.

Anomalies may indicate:

- Search logic gaps for that domain
- Classification errors
- Need for domain-specific search patterns

---

## Phase 3: Learning Phase

### Analysis

1. Aggregate scores across all conversations in the batch
2. Calculate per-product-area metrics and identify anomalies
3. Identify patterns in low-scoring results:
   - Which product areas have low precision?
   - What search terms led to noise?
   - What relevant code did we consistently miss?
4. Check model calibration data (iterations 1-2):
   - Opus vs Sonnet overlap rate
   - Files found exclusively by each model
5. Review classification accuracy and uncertain rate
6. Distinguish patterns from outliers (need sufficient sample size)

### Improvement Proposals

Based on analysis, propose specific logic changes:

- Add/modify search term generation rules
- Adjust file filtering patterns
- Improve snippet selection heuristics
- Update repo-specific search strategies
- Add domain-specific search paths based on product area
- Refine classification keywords if accuracy is low

**Guard Rails**: Before implementing changes, verify they won't regress other product areas. Check historical per-area metrics.

**Rollback Procedure**: If a change causes >0.10 regression in any product area:

1. Revert the change immediately
2. Document the failure mode (which area, what pattern)
3. Propose alternative approach that won't cause regression

### Implementation

- Commit changes to existing codebase exploration code
- Document what was changed and why in progress file
- Ensure git history tracks all modifications
- Record which product areas the change targets

---

## Configuration Parameters

| Parameter             | Default | Description                                           |
| --------------------- | ------- | ----------------------------------------------------- |
| `MIN_ITERATIONS`      | 3       | Minimum cycles before early exit (forces exploration) |
| `MAX_ITERATIONS`      | 10      | Hard cap to prevent runaway                           |
| `BATCH_SIZE`          | 15-20   | Conversations per iteration                           |
| `PRECISION_THRESHOLD` | 0.80    | Target precision score                                |
| `RECALL_THRESHOLD`    | 0.70    | Target recall score                                   |
| `GESTALT_THRESHOLD`   | 4.0     | Minimum overall quality                               |

### Convergence Criteria

Exit early (after MIN_ITERATIONS) if:

- Precision >= PRECISION_THRESHOLD
- Recall >= RECALL_THRESHOLD
- Gestalt >= GESTALT_THRESHOLD
- No regression from previous iteration

### Force Improvement Rule

Even if scores are good, if iteration < MIN_ITERATIONS:

- Identify at least one area for potential improvement
- Implement and test the change
- Continue to next iteration

---

## File Structure

```
scripts/codebase-search-vdd/
├── run_vdd_loop.sh              # Main orchestrator with convergence detection
├── PROMPT.md                    # Instructions for iteration agent
├── progress.txt                 # Cross-iteration memory
├── config.json                  # Iteration parameters
├── fetch_conversations.py       # Pull conversations (Intercom API or database)
├── run_search.py                # Execute search logic on batch
├── evaluate_results_v2.py       # CLI-based evaluation with dual exploration
├── apply_learnings.py           # Autonomous learning phase (CLI-based)
├── backups/                     # Pre-modification code backups
└── outputs/
    ├── iteration_0/             # Baseline measurement
    ├── iteration_1/
    │   ├── conversations.json
    │   ├── search_results.json
    │   ├── evaluation.json
    │   └── learnings.json
    └── ...
```

### Conversation Sources

The VDD system supports multiple conversation sources:

| Mode                     | Flag                        | Source                | Use Case                         |
| ------------------------ | --------------------------- | --------------------- | -------------------------------- |
| Intercom API             | (default)                   | Live Intercom API     | Fresh, diverse conversations     |
| Database (all)           | `--from-db`                 | PostgreSQL            | Offline testing, reproducibility |
| Database (Intercom only) | `--from-db --intercom-only` | PostgreSQL (filtered) | Real support data only           |

**Database Breakdown** (as of 2026-01-16):

- **Coda imports**: 9,364 conversations (research/interview data)
- **Real Intercom**: 680 conversations (actual support tickets)

For VDD testing with representative support data, use `--from-db --intercom-only`.

### CLI-Based Execution

All LLM calls use Claude CLI instead of Anthropic SDK:

```bash
# Evaluation uses Claude CLI for dual exploration
env -u ANTHROPIC_API_KEY python3 evaluate_results_v2.py < search_results.json

# Learning phase also uses Claude CLI
env -u ANTHROPIC_API_KEY python3 apply_learnings.py < evaluation.json
```

**Why CLI?** Uses Claude Code's subscription billing instead of separate API credits.

---

## Integration Points

### Codebase Exploration Code

The search logic being optimized lives in:

- `src/story_tracking/services/codebase_context_provider.py`
- `src/story_tracking/services/codebase_security.py`

Changes are committed directly to these files during iteration.

### Approved Repositories

All repos must be cloned locally in the same parent directory as FeedForward:

```
~/Documents/GitHub/
├── FeedForward/      # This repo
├── aero/             # Main Tailwind app
├── tack/             # Pinterest integration service
├── charlotte/        # Analytics service
├── ghostwriter/      # AI text generation
└── zuck/             # Social media integration
```

### Environment Configuration

```
FEEDFORWARD_REPOS_PATH=/Users/paulyokota/Documents/GitHub
FEEDFORWARD_APPROVED_REPOS=aero,tack,charlotte,ghostwriter,zuck
```

---

## Success Criteria

### Per-Iteration

- [ ] All conversations in batch processed without errors
- [ ] Precision and recall calculated for each conversation
- [ ] Per-product-area metrics calculated
- [ ] Dimensional scores recorded
- [ ] Gestalt score provided with reasoning
- [ ] Classification accuracy tracked
- [ ] At least one improvement identified (if not converged)

### Baseline (Iteration Zero)

- [ ] 30-40 conversations processed
- [ ] Baseline precision/recall established
- [ ] Per-product-area baseline documented
- [ ] Classification system validated

### Model Calibration (Iterations 1-2)

- [ ] Opus vs Sonnet comparison data collected
- [ ] Overlap rate calculated
- [ ] Model decision made for iterations 3+

### Overall

- [ ] Achieve precision >= 80%
- [ ] Achieve recall >= 70%
- [ ] Gestalt consistently >= 4.0
- [ ] No product area >0.15 below aggregate
- [ ] Classification accuracy >= 85%
- [ ] Search logic changes committed with clear documentation
- [ ] No regressions from baseline

---

## Risk Mitigation

| Risk                            | Mitigation                                                 |
| ------------------------------- | ---------------------------------------------------------- |
| Overfitting to specific issues  | Diverse conversation batches, minimum iteration count      |
| Evaluator bias                  | Independent exploration before seeing our results          |
| Logic swing from thin data      | Require batch size >= 15, pattern vs outlier analysis      |
| Breaking existing functionality | Commit changes incrementally, track git history            |
| Runaway iterations              | Hard MAX_ITERATIONS cap                                    |
| Inconsistent evaluation         | Fixed dimensional criteria, documented gestalt rubric      |
| Evaluator non-determinism       | Dual exploration with union for ground truth stability     |
| Oscillating improvements        | Per-product-area tracking, guard rails before changes      |
| Classification errors           | Uncertain category, cross-validation during judge step     |
| Model cost overruns             | Calibration phase to determine if Sonnet suffices for Opus |

---

## Open Questions

1. ~~**Conversation Selection**: Should we weight certain product areas more heavily, or pure random sampling?~~
   **RESOLVED**: Use diverse sampling across product areas, track metrics per area to detect imbalances.

2. **Cross-Iteration Learning**: Should later iterations have access to patterns discovered in earlier iterations (accumulated wisdom)?

3. ~~**Baseline Measurement**: Do we run one iteration with current logic before making changes to establish baseline?~~
   **RESOLVED**: Yes, Iteration Zero with larger batch (30-40 conversations) establishes baseline.

4. **Actionability Tracking**: How do we use the "actionable" tag without optimizing for it initially?

5. **Domain-Specific Search**: Should we build product-area-aware search paths into the logic proactively, or discover them through VDD iteration?

---

## Next Steps

1. [x] Architecture review via developer-kit (Round 1)
2. [x] Incorporate review feedback (baseline, dual exploration, product areas)
3. [ ] Architecture review via developer-kit (Round 2)
4. [ ] Create orchestrator script structure
5. [ ] Implement product area classification logic
6. [ ] Implement conversation fetching with diversity sampling
7. [ ] Build dual exploration evaluation harness
8. [ ] Run Iteration Zero (baseline with 30-40 conversations)
9. [ ] Begin calibration iterations (1-2)
10. [ ] Make model decision and continue iteration loop
