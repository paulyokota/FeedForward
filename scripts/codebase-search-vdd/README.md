# Codebase Search VDD - Dual Exploration Evaluator

This script orchestrates the dual exploration evaluation process for measuring codebase search quality using Validation-Driven Development (VDD) principles.

## Overview

The evaluation process:

1. **Dual Exploration**: Launch TWO independent Claude Code explorations (using Opus + Sonnet during calibration)
2. **Ground Truth Construction**: Combine results from both explorations as the union of files found
3. **Comparison**: Compare our search results against ground truth to identify:
   - Intersection (files we found that are in ground truth)
   - Our Unique (files only we found - need judging)
   - Ground Truth Unique (files we missed - recall gap)
4. **Judgment**: Use judge model to determine relevance of "Our Unique" files
5. **Metrics**: Calculate precision/recall with per-product-area breakdown
6. **Calibration**: Track which files each model found during iterations 1-2 for model selection

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              evaluate_results.py                         │
│                                                          │
│  ┌─────────────┐                                        │
│  │ Read stdin  │ ← search_results.json                  │
│  └──────┬──────┘                                        │
│         │                                                │
│         ▼                                                │
│  ┌─────────────────────────────────────────┐            │
│  │  For each conversation:                 │            │
│  │                                          │            │
│  │  ┌──────────────┐    ┌──────────────┐  │            │
│  │  │  Run A       │    │  Run B       │  │ (parallel) │
│  │  │  (Opus)      │    │  (Sonnet*)   │  │            │
│  │  └──────┬───────┘    └──────┬───────┘  │            │
│  │         │                   │           │            │
│  │         └─────────┬─────────┘           │            │
│  │                   ▼                     │            │
│  │         ┌──────────────────┐            │            │
│  │         │  Union = Ground  │            │            │
│  │         │  Truth           │            │            │
│  │         └─────────┬────────┘            │            │
│  │                   │                     │            │
│  │                   ▼                     │            │
│  │         ┌──────────────────┐            │            │
│  │         │  Compare with    │            │            │
│  │         │  Our Results     │            │            │
│  │         └─────────┬────────┘            │            │
│  │                   │                     │            │
│  │                   ▼                     │            │
│  │         ┌──────────────────┐            │            │
│  │         │  Judge Our       │            │            │
│  │         │  Unique Files    │            │            │
│  │         └─────────┬────────┘            │            │
│  │                   │                     │            │
│  │                   ▼                     │            │
│  │         ┌──────────────────┐            │            │
│  │         │  Calculate       │            │            │
│  │         │  Precision/Recall│            │            │
│  │         └──────────────────┘            │            │
│  └─────────────────────────────────────────┘            │
│                                                          │
│  ┌─────────────────────────────────────────┐            │
│  │  Aggregate metrics across all           │            │
│  │  conversations                           │            │
│  └──────┬──────────────────────────────────┘            │
│         │                                                │
│         ▼                                                │
│  ┌──────────────┐                                       │
│  │ Output JSON  │ → evaluation_results.json             │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘

* During calibration iterations 1-2, Run B uses Sonnet
  After calibration, if overlap >= 90%, both runs use Sonnet
```

## Configuration

Configuration is read from `config.json`:

```json
{
  "repos_path": "/Users/paulyokota/Documents/GitHub",
  "approved_repos": ["aero", "tack", "charlotte", "ghostwriter", "zuck"],
  "calibration_iterations": 2,
  "calibration_overlap_threshold": 0.9,
  "models": {
    "exploration_opus": "claude-opus-4-20250514",
    "exploration_sonnet": "claude-sonnet-4-20250514",
    "judge": "claude-opus-4-20250514"
  }
}
```

## Input Format

The script reads JSON from stdin with this structure:

```json
{
  "iteration_number": 1,
  "timestamp": "2026-01-15T15:30:00Z",
  "conversations": [
    {
      "conversation_id": "12345",
      "issue_summary": "User reports pins not showing in community feed...",
      "product_area": "communities",
      "classification_confidence": 0.85,
      "search_results": {
        "files_found": [
          "aero/app/services/pins_service.rb",
          "aero/app/controllers/communities_controller.rb"
        ],
        "search_terms_used": ["pins", "community", "feed"],
        "exploration_log": []
      }
    }
  ]
}
```

**File Path Format**: All file paths must use `repo/path/to/file` format (e.g., `aero/app/services/pins_service.rb`).

## Output Format

The script outputs JSON to stdout with comprehensive evaluation results:

```json
{
  "iteration_number": 1,
  "timestamp": "2026-01-15T15:30:00Z",
  "metrics": {
    "aggregate": {
      "precision": 0.825,
      "recall": 0.714,
      "conversations_evaluated": 15
    },
    "by_product_area": {
      "communities": {
        "precision": 0.85,
        "recall": 0.75,
        "count": 5
      },
      "scheduling": {
        "precision": 0.8,
        "recall": 0.68,
        "count": 4
      }
    },
    "calibration": {
      "opus_only_files": 12,
      "sonnet_only_files": 3,
      "both_models_files": 45,
      "overlap_rate": 0.789,
      "recommendation": "Keep Opus-Sonnet hybrid or Opus-only"
    }
  },
  "conversations": [
    {
      "conversation_id": "12345",
      "issue_summary": "...",
      "product_area": "communities",
      "run_a": {
        "model": "claude-opus-4-20250514",
        "files_found": ["aero/app/services/pins_service.rb", "..."],
        "error": null
      },
      "run_b": {
        "model": "claude-sonnet-4-20250514",
        "files_found": ["aero/app/services/pins_service.rb", "..."],
        "error": null
      },
      "ground_truth_files": ["aero/app/services/pins_service.rb", "..."],
      "our_files": ["aero/app/services/pins_service.rb", "..."],
      "intersection": ["aero/app/services/pins_service.rb"],
      "our_unique": ["aero/app/models/pin.rb"],
      "ground_truth_unique": ["aero/app/services/community_feed_service.rb"],
      "our_unique_judgments": [
        {
          "file": "aero/app/models/pin.rb",
          "relevant": true,
          "actionable": "yes",
          "reasoning": "Defines Pin model with validation logic"
        }
      ],
      "precision": 0.85,
      "recall": 0.75,
      "calibration_data": {
        "opus_only": ["aero/app/services/community_feed_service.rb"],
        "sonnet_only": [],
        "both_models": ["aero/app/services/pins_service.rb"]
      }
    }
  ]
}
```

## Usage

### Basic Usage

```bash
# Read search results from stdin, output evaluation to stdout
cat search_results.json | python evaluate_results.py > evaluation.json

# Or use with run_search.py in a pipeline (when implemented)
python run_search.py < conversations.json | python evaluate_results.py > evaluation.json
```

### Test Run

```bash
# Test with sample input
cat test_input.json | python evaluate_results.py
```

### Environment Setup

Ensure you have the Anthropic API key set:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Metrics Explained

### Precision

```
precision = (intersection + our_unique_relevant) / total_files_we_found
```

Measures how many of the files we found are actually relevant. High precision means low noise.

### Recall

```
recall = (intersection + our_unique_relevant) / ground_truth_total
```

Measures how many of the relevant files (ground truth) we actually found. High recall means we're not missing important files.

### Per-Product-Area Metrics

Tracks precision/recall separately for each product domain (communities, scheduling, analytics, etc.) to:

- Detect domain-specific weaknesses
- Prevent oscillating improvements that help one area while hurting another
- Guide targeted improvements

### Calibration Data

During iterations 1-2, tracks which files each model finds:

- **opus_only**: Files only Opus found (potential blind spots for Sonnet)
- **sonnet_only**: Files only Sonnet found (less likely, but possible)
- **both_models**: Files both found (high confidence)
- **overlap_rate**: `both_models / total_opus_files`

If overlap rate >= 0.9 after 2 iterations, switch to dual-Sonnet for cost efficiency.

## Dual Exploration Rationale

### Why Two Runs?

LLM exploration is non-deterministic. Running twice and taking the union provides:

1. **Stability**: Ground truth doesn't shift wildly between evaluations
2. **Completeness**: Catches files that might be missed in a single run
3. **Confidence**: Files found by both runs are high-confidence relevant

### Why Different Models During Calibration?

Opus is more capable but expensive. Sonnet is faster and cheaper. By comparing them in iterations 1-2:

- If Sonnet performs nearly as well (90%+ overlap), use dual-Sonnet going forward
- If Opus consistently finds critical files Sonnet misses, stick with Opus or hybrid

### Independence Principle

**Critical**: Exploration runs do NOT see our search results. They only see:

- Conversation ID
- Issue summary
- Available codebases

This prevents confirmation bias where the evaluator just validates whatever we found.

## Error Handling

- **Exploration failures**: Logged in `run_a.error` or `run_b.error`, evaluation continues
- **Judge failures**: Falls back to marking all "Our Unique" files as not relevant (conservative)
- **Invalid input**: Script exits with error message to stderr

## Performance Considerations

- **Parallel execution**: Both exploration runs happen simultaneously using `asyncio`
- **API rate limits**: Be aware of Anthropic API rate limits when evaluating large batches
- **Cost**: During calibration (Opus + Sonnet), cost is ~$0.50-$1.00 per conversation

## Integration with VDD Loop

This script is Phase 2 (Evaluation) of the VDD iteration loop:

```
run_search.py → evaluate_results.py → analyze_and_learn.py → (next iteration)
```

See `docs/architecture/codebase-search-vdd.md` for full VDD architecture.

## Future Enhancements

- [ ] Add dimensional scoring (File Relevance, Snippet Quality, Service Accuracy, etc.)
- [ ] Support gestalt score (overall quality assessment)
- [ ] Add classification validation (verify product area assignments)
- [ ] Support actionability tracking
- [ ] Add anomaly detection for product areas >0.15 below aggregate
- [ ] Parallelize evaluation across multiple conversations
- [ ] Add retry logic for transient API failures
