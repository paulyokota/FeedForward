# VDD Codebase Search - Conversation Fetcher

Fetches diverse Intercom conversations for Validation-Driven Development (VDD) testing of codebase search logic.

## Purpose

This script fetches real customer conversations from Intercom and classifies them into product areas using keyword matching. It's used to test the quality of our codebase search system by providing diverse, real-world test cases.

## Features

- **Diversity Sampling**: Automatically balances conversations across product areas
- **Auto-Classification**: Uses keyword matching to classify conversations
- **Confidence Scoring**: Tags low-confidence classifications as "uncertain"
- **JSON Output**: Structured data for pipeline integration

## Usage

### Basic Usage

```bash
# Fetch 35 conversations for baseline testing
python fetch_conversations.py --batch-size 35

# Fetch 18 conversations for iteration testing
python fetch_conversations.py --batch-size 18

# Customize lookback period
python fetch_conversations.py --batch-size 35 --days-back 60
```

### Output Format

The script outputs JSON to stdout:

```json
[
  {
    "conversation_id": "123456",
    "issue_summary": "My pins aren't posting to the schedule calendar...",
    "product_area": "scheduling",
    "classification_confidence": 0.75,
    "created_at": "2024-01-15T10:30:00",
    "source_url": "https://app.tailwindapp.com/schedule",
    "matched_keywords": ["schedule", "calendar", "pins", "posting"]
  }
]
```

### Pipeline Integration

```bash
# Pipe to run_search.py
python fetch_conversations.py --batch-size 35 | python run_search.py

# Save to file
python fetch_conversations.py --batch-size 35 > conversations.json
```

## Configuration

Product areas and keywords are defined in `config.json`:

```json
{
  "product_areas": [
    {
      "name": "scheduling",
      "keywords": ["calendar", "schedule", "publish", "queue"]
    },
    {
      "name": "analytics",
      "keywords": ["metrics", "insights", "reports", "performance"]
    }
  ]
}
```

## Classification Logic

### Keyword Matching

- Each product area has a list of keywords
- Score = (matched keywords) / (total keywords)
- Best score wins

### Confidence Threshold

- **Confident** (>= 0.4): Assigned to product area
- **Uncertain** (< 0.4): Tagged as "uncertain"

### Diversity Sampling

- Target: Equal distribution across product areas
- Skips over-represented areas after collecting 30% of batch
- Allows filling when 80%+ of batch is collected

## Environment Requirements

- `INTERCOM_ACCESS_TOKEN` environment variable must be set
- Python 3.10+
- Dependencies: Uses FeedForward's `src.intercom_client`

## Testing

Run tests:

```bash
pytest tests/test_fetch_conversations_vdd.py -v
```

Test coverage:

- Keyword-based classification
- Diversity sampling
- Issue summary extraction
- JSON output format
- Edge cases (empty keywords, no matches, etc.)

## VDD Integration

This fetcher is part of the VDD (Validation-Driven Development) system:

1. **fetch_conversations.py** (this script) - Fetch diverse test cases
2. **run_search.py** - Execute codebase searches
3. **evaluate_results.py** - Dual exploration evaluation
4. **analyze_and_learn.py** - Extract learnings

See `progress.txt` for current iteration status.

## Implementation Details

### ProductAreaClassifier

Performs keyword-based classification:

```python
classifier = ProductAreaClassifier(product_areas)
result = classifier.classify(conversation_text)
# Returns: ProductAreaClassification(product_area, confidence, matched_keywords)
```

### ConversationFetcher

Main fetching logic with diversity sampling:

```python
fetcher = ConversationFetcher(config_path)
conversations = fetcher.fetch_recent_conversations(
    batch_size=35,
    days_back=30
)
```

### Issue Summary Extraction

Truncates long conversations intelligently:

- Max 300 characters
- Breaks at word boundaries
- Adds " ..." ellipsis for truncated text
