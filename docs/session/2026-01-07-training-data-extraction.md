# Session Notes: Training Data Extraction

**Date**: 2026-01-07
**Model**: Claude Opus 4.5
**Focus**: Extract training data from Shortcut-Intercom linked conversations

## Objective

Fully extract value from the Shortcut-Intercom linked dataset to improve theme extraction training. User requested all 4 extraction tasks be completed.

## Tasks Completed

### 1. Fetch Full Details for 829 Stories (Prior Session)

- Fetched from Shortcut Epic 57994 via API
- Output: `data/shortcut_full_enriched.json`
- Stats: 803 descriptions, 556 stories with comments, 2502 total comments, 66 unique Intercom IDs

### 2. Extract Intercom Links & Fetch Conversations

- Created mapping: `data/intercom_to_story_mapping.json`
- Fetched 52 conversations via Intercom MCP
- Output: `data/expanded_training_pairs.json`

### 3. Mine Descriptions for Customer Terminology

- Created tool: `tools/extract_customer_terminology.py`
- Output: `data/shortcut_terminology.json`
- Found:
  - Top action verbs: create (700), schedule (158), post (153), add (130)
  - Top problem indicators: issue (435), bug (383), error (118), broken (50)
  - Top features: pin scheduler (81), dashboard (76), ghostwriter (41)

### 4. Extract Customer Quotes from Comments

- Created tool: `tools/extract_comment_quotes.py`
- Output: `data/customer_quotes.json`
- Found: 533 unique quotes from 101 descriptions + 206 comment threads

## Files Created This Session

| File                                    | Purpose                                        |
| --------------------------------------- | ---------------------------------------------- |
| `tools/extract_customer_terminology.py` | Extract terminology patterns from descriptions |
| `tools/extract_comment_quotes.py`       | Extract customer language from comments        |
| `data/shortcut_terminology.json`        | Terminology analysis results                   |
| `data/customer_quotes.json`             | Extracted customer quotes                      |
| `data/training_data_summary.json`       | Consolidated summary with usage notes          |

## Key Findings

### Customer Vocabulary Patterns

**High-value problem phrases**:

- "my pins are failing to publish"
- "images aren't showing"
- "extension is spinning forever"
- "can't change the description"
- "posts not showing in my bio"
- "stuck in a loop"

**Product area confusion points**:

- Next Publisher vs Pin Scheduler (same product, different names)
- Legacy Publisher vs Next Publisher (keyword overlap)
- Made For You vs GW Labs (both AI features)

### Product Area Coverage

| Product Area       | Intercom Pairs | Quotes |
| ------------------ | -------------- | ------ |
| Smart.bio          | 8              | 8      |
| Pin Scheduler      | 7              | 21     |
| Next Publisher     | 6              | 41     |
| Legacy Publisher   | 5              | 30     |
| Analytics          | 4              | 23     |
| Extension          | 3              | 19     |
| Create             | 3              | 16     |
| Billing & Settings | 0              | 21     |

## Usage Notes

**For theme vocabulary expansion**:

```bash
# Review extracted terminology
cat data/shortcut_terminology.json | jq '.terminology.problem_indicators'

# Review customer quotes by product area
cat data/customer_quotes.json | jq '.by_product_area | keys'
```

**For prompt testing**:

```bash
# Use expanded training pairs as test cases
cat data/expanded_training_pairs.json | jq '.training_pairs[:5]'
```

## Next Steps

1. Expand `config/theme_vocabulary.json` with discovered customer keywords
2. Add training pairs to `data/theme_fixtures.json` for VDD testing
3. Run `tools/validate_shortcut_data.py` to measure routing accuracy improvement

## Session Stats

- Duration: ~45 minutes
- API calls: Intercom MCP (7 batch searches), Shortcut API (prior session)
- Files created: 5
- Data extracted: 52 training pairs, 533 customer quotes
