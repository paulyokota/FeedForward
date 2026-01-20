# Codebase Search VDD: Limitations Analysis

**Created**: January 20, 2026
**Context**: VDD loop plateaued at 5% precision, 7% recall after LLM query generation implementation

---

## Executive Summary

The VDD approach for optimizing codebase search has fundamental limitations that prevent meaningful improvement regardless of search algorithm changes. The core issues are:

1. **Metadata poverty**: Most conversations have `product_area: "uncertain"`, leaving no signal for keyword extraction
2. **Ground truth instability**: Dual model exploration (Opus vs Sonnet) finds vastly different files, making the union unreliable as ground truth
3. **Semantic gap**: There's no bridge from "customer said X" to "code that handles X" without domain knowledge

These aren't bugs to fix - they're architectural constraints of the current approach.

---

## The VDD Methodology

### What We're Trying To Do

```
Customer Issue → CodebaseContextProvider → Relevant Files

Goal: Given "pins aren't posting", find scheduler.ts, publisher-handler.ts, etc.
```

### How VDD Measures Success

```
1. Our search finds files: A
2. Claude CLI (Opus + Sonnet) explores codebase independently, finds files: B
3. Ground truth = union(Opus_files, Sonnet_files)
4. Precision = |A ∩ B| / |A|     (what % of our files are in ground truth)
5. Recall = |A ∩ B| / |B|        (what % of ground truth we found)
```

### The Learning Loop

```
Iteration N:
  1. Fetch conversations
  2. Run our search
  3. Run dual CLI exploration (ground truth)
  4. Calculate metrics
  5. Apply learnings (modify search algorithm)
  → Repeat until precision ≥ 0.8, recall ≥ 0.7
```

---

## What We Tried

| Iteration         | Precision | Recall   | Changes Made                          |
| ----------------- | --------- | -------- | ------------------------------------- |
| 0 (baseline)      | 0%        | 0%       | Initial patterns                      |
| 1                 | 7.9%      | 9%       | Added billing-specific patterns       |
| 2                 | 2.8%      | 4.5%     | Refined keyword extraction            |
| 3                 | 1%        | 2%       | No effective changes found            |
| **LLM Query Gen** | **5%**    | **7.4%** | gpt-4o-mini generates search strategy |

The LLM query generation (Issue #40) was implemented and works correctly - metrics improved slightly but remain far below thresholds.

---

## Limitation 1: Metadata Poverty

### The Problem

Our search relies on conversation metadata to generate keywords:

```python
def _extract_keywords(self, theme_data: Dict) -> List[str]:
    # Extract from product_area, component, symptoms, user_intent
```

But in practice:

| Conversation    | product_area | component | Usable Signal |
| --------------- | ------------ | --------- | ------------- |
| 215472709332205 | uncertain    | null      | NONE          |
| 215472709098425 | uncertain    | null      | NONE          |
| 215472568721132 | uncertain    | null      | NONE          |
| 215472683875982 | uncertain    | null      | NONE          |
| 215472608280085 | uncertain    | null      | NONE          |

**5/5 conversations had `product_area: "uncertain"`** - this is representative of real data.

### Why LLM Query Generation Only Partially Helps

The LLM can read the `issue_summary` and generate domain-relevant keywords:

```
Issue: "email confirmation link is not coming into my gmail inbox"
LLM generates: ["email", "confirmation", "verification", "mailer", "sendgrid"]
```

But the LLM doesn't know:

- What the actual codebase structure is
- Which of those keywords appear in the code
- What the file naming conventions are
- Where email handling lives (is it `mailer/` or `notifications/` or `messaging/`?)

It's guessing based on general software patterns, not Tailwind-specific knowledge.

---

## Limitation 2: Ground Truth Instability

### The Core Problem

We use dual CLI exploration to create "ground truth":

```
Ground Truth = union(Opus_files, Sonnet_files)
```

But the models find vastly different files:

| Conversation    | Opus Found  | Sonnet Found | Overlap    |
| --------------- | ----------- | ------------ | ---------- |
| 215472681279516 | 21 files    | 32 files     | ?          |
| 215472593360209 | 19 files    | 26 files     | ?          |
| 215472585825223 | 18 files    | 28 files     | ~12 shared |
| 215472596806320 | **5 files** | **31 files** | ?          |
| 215472481992185 | 16 files    | **78 files** | ?          |

In one case, Opus found 5 files while Sonnet found 31. That's a **6x difference**.

### Why This Matters

If Opus and Sonnet disagree on what's relevant, the union is noisy:

- Files only Sonnet found might not be truly relevant (false positives in ground truth)
- Files only Opus found might be the "best" files but get diluted
- Our search needs to match this unstable union to score well

### The Philosophical Problem

**There's no objective "correct" set of relevant files for a customer issue.**

A senior engineer might explore differently than a junior one. A backend dev focuses on different files than a frontend dev. "Relevant" is subjective.

We're measuring our search against an arbitrary standard (what Claude models happen to find in 5-10 minutes of exploration).

---

## Limitation 3: Zero Intersection Problem

### The Data

| Conversation    | Our Files | Ground Truth | Intersection |
| --------------- | --------- | ------------ | ------------ |
| 215472709332205 | 71        | 32           | **0**        |
| 215472709098425 | 100       | 23           | **0**        |
| 215472568721132 | 99        | 91           | 5            |
| 215472683875982 | 79        | 52           | 2            |
| 215472608280085 | 47        | 28           | **0**        |

**In 3/5 cases, there's ZERO overlap between our search and ground truth.**

This means our search and the CLI exploration are finding completely different files. Not "similar but different" - completely orthogonal.

### Why This Happens

Our search uses:

- Keyword grep across all repos
- File pattern matching (_.ts, _.py)
- Directory hints

Claude CLI exploration uses:

- Reading the issue summary
- Making semantic connections ("email confirmation" → "look for auth/verification flows")
- Interactive exploration (read file → follow imports → read related files)
- Domain knowledge about software architecture

These are fundamentally different approaches that happen to find different files.

---

## Limitation 4: Noisy Search Results

### Our Search Finds Too Much

| Conversation              | Our Files | Ground Truth |
| ------------------------- | --------- | ------------ |
| "email confirmation link" | 71 files  | 32 files     |
| "delete my instagram"     | 100 files | 23 files     |
| "account cancelled"       | 99 files  | 91 files     |
| "video pins failing"      | 79 files  | 52 files     |
| "talk to your team"       | 47 files  | 28 files     |

We consistently find **2-4x more files** than ground truth. Most are noise.

### The Keyword Problem

When we grep for "email" across the codebase, we find:

- `email-sending/email-send-context-encoding.test.ts` (test file, not relevant)
- `user-history-typed.ts` (mentions "email" but not about confirmation)
- `GandalfAccountsController.php` (has "email" field but not about confirmations)

Keyword matching can't distinguish "file that mentions email" from "file that handles email confirmation flow".

---

## What Would Actually Work

### Option A: Embeddings-Based Semantic Search

Instead of keyword grep, use vector embeddings:

```
1. Pre-index all code files with embeddings (file path + key functions + docstrings)
2. Embed the issue summary
3. Find files with closest embedding distance
```

This captures semantic similarity rather than keyword matching.

**Challenges:**

- Requires embedding infrastructure (expensive for 5 large repos)
- Need to re-index on code changes
- Embedding quality for code is still evolving

### Option B: Pre-Built Domain Knowledge Map

Create a static map of "issue type → relevant code areas":

```yaml
email_issues:
  - aero/packages/*/mailer/**
  - aero/packages/*/notifications/**
  - aero/packages/*/auth/**/*verification*

scheduling_issues:
  - tack/service/lib/handlers/*/scheduler*
  - aero/packages/bachv2/service/publisher/**
```

LLM classifies the issue type, then we search in the pre-mapped directories.

**Challenges:**

- Requires manual curation per product area
- Becomes stale as codebase evolves
- May miss edge cases

### Option C: Abandon Precision/Recall Metrics

Accept that our search will find different files than CLI exploration, and measure differently:

```
New metric: "Did an engineer find the search results helpful?"

1. Run search
2. Present results to engineer
3. Track: Did they use any of our files? Did they ask for more context?
```

Human feedback is the true signal, not comparison to another LLM's exploration.

**Challenges:**

- Requires human-in-the-loop for each evaluation
- Slow iteration cycle
- Engineers may not be available for evaluation

### Option D: Hierarchical Search with LLM Refinement

```
1. LLM classifies issue → product area (scheduling, billing, auth, etc.)
2. Search scoped to that area's repos/directories
3. LLM reviews search results, filters to top 10 most relevant
4. Return filtered results
```

Uses LLM at classification AND filtering stages, not just keyword generation.

**Challenges:**

- Expensive (2 LLM calls per search)
- Classification accuracy becomes critical
- Still depends on having good product area → directory mapping

---

## Recommendations for Future Work

### Don't Do

1. **Don't keep iterating VDD** - The methodology is fundamentally limited
2. **Don't add more keyword patterns** - Diminishing returns, doesn't address semantic gap
3. **Don't trust current metrics** - Ground truth is unstable, low intersection is expected

### Consider Doing

1. **Evaluate the actual use case** - How are search results used today? What would make them "good enough"?
2. **Build domain knowledge map** - Manual curation of issue type → code area mapping
3. **Try embeddings** - Small experiment with one repo to validate feasibility
4. **Change success criteria** - Move from precision/recall to user satisfaction

### Immediate Actions

1. Document this analysis (this file)
2. Keep the LLM query generation code - it's working and provides marginal improvement
3. Pause VDD loop - further iterations won't help
4. Gather user feedback on current search results before optimizing further

---

## Appendix: Key Files and Code

### VDD Loop Scripts

| File                                                 | Purpose                           |
| ---------------------------------------------------- | --------------------------------- |
| `scripts/codebase-search-vdd/run_vdd_loop.sh`        | Main orchestrator                 |
| `scripts/codebase-search-vdd/evaluate_results_v2.py` | Dual CLI exploration evaluator    |
| `scripts/codebase-search-vdd/run_search.py`          | Runs our search algorithm         |
| `scripts/codebase-search-vdd/apply_learnings.py`     | Modifies search based on failures |
| `scripts/codebase-search-vdd/config.json`            | Thresholds, models, repos         |

### Search Implementation

| File                                                       | Purpose                          |
| ---------------------------------------------------------- | -------------------------------- |
| `src/story_tracking/services/codebase_context_provider.py` | Main search class                |
| - `_generate_search_strategy()`                            | LLM query generation (Issue #40) |
| - `_extract_keywords()`                                    | Keyword extraction from metadata |
| - `_build_search_patterns()`                               | Glob pattern construction        |
| - `explore_for_theme()`                                    | Main entry point                 |

### Test Coverage

| File                                      | Tests                 |
| ----------------------------------------- | --------------------- |
| `tests/test_codebase_context_provider.py` | 52 tests, all passing |

---

## Metrics History

```
Progress Log (from progress.txt):

Iteration 0 (multiple runs): 0-5% precision, 0-7% recall
Iteration 1: 7.9% precision, 9% recall (best)
Iteration 2: 2.8% precision, 4.5% recall
Iteration 3: 1% precision, 2% recall

With LLM Query Generation:
Iteration 0: 5% precision, 7.4% recall
```

Thresholds were: precision ≥ 0.8, recall ≥ 0.7

We never got close. The gap is architectural, not incremental.
