# Phase 4 Testing Scripts

This directory contains scripts for validating and testing Phase 4a (Help Article Context) and Phase 4b (Shortcut Story Context) implementations.

## Scripts Overview

### 1. `validate_phase4_extractors.py`

**Purpose**: Validate extractors against real Intercom data to measure extraction rates and data quality.

**Usage**:

```bash
# Using Intercom API (requires implementation)
python scripts/validate_phase4_extractors.py --sample-size 100 --output validation_results.txt

# Using test data file
python scripts/validate_phase4_extractors.py --test-data path/to/conversations.json --output validation_results.txt
```

**What it measures**:

- Help article extraction rate (target: 15-20% of conversations)
- Shortcut story extraction rate (target: 30-40% of conversations)
- Data quality validation
- URL pattern distribution
- Label and epic frequency
- Sample extractions for manual review

**Output**:

- Console report with extraction statistics
- Optional output file with detailed results
- Sample extractions for validation

### 2. `test_phase4_accuracy_improvement.py`

**Purpose**: A/B test Stage 2 classification accuracy with/without context enrichment.

**Usage**:

```bash
# Full test suite (baseline + article + story + combined)
python scripts/test_phase4_accuracy_improvement.py --test-set path/to/test_conversations.json --output accuracy_results.txt

# Skip baseline test (useful for re-running)
python scripts/test_phase4_accuracy_improvement.py --test-set path/to/test_conversations.json --skip-baseline
```

**What it measures**:

- Baseline accuracy (no context enrichment)
- Help article context impact on accuracy
- Shortcut story context impact on accuracy
- Combined context impact (both enrichments)
- Confidence score improvements

**Expected improvements**:

- Help articles: +10-15% accuracy improvement
- Shortcut stories: +15-20% accuracy improvement
- Combined: +20-30% accuracy improvement

**Output**:

- Comparison report showing improvements vs baseline
- Pass/fail indicators for expected improvement ranges
- Detailed per-conversation results

### 3. `test_conversations_template.json`

**Purpose**: Template for preparing test conversation datasets.

**Format**:

```json
[
  {
    "id": "conversation_123456",
    "customer_message": "...",
    "support_messages": ["..."],
    "ground_truth": {
      "primary_theme": "Instagram",
      "issue_type": "Bug"
    },
    "raw_conversation": {
      "id": "123456",
      "source": {"url": "..."},
      "custom_attributes": {"story_id_v2": "..."},
      "conversation_parts": {...}
    }
  }
]
```

**Required fields**:

- `id`: Conversation identifier
- `customer_message`: Initial customer message
- `support_messages`: Array of support agent responses
- `ground_truth`: Expected classification results
  - `primary_theme`: Expected theme (e.g., "Instagram", "Pinterest", "Billing")
  - `issue_type`: Expected type (e.g., "Bug", "Question", "Feature Request")
- `raw_conversation`: Full Intercom conversation object for extractors

## Preparing Test Data

### Step 1: Fetch Conversations from Intercom

Option A: Use Intercom MCP server to fetch conversations
Option B: Export conversations from Intercom manually
Option C: Query database for previously processed conversations

### Step 2: Add Ground Truth Labels

Manually label each conversation with expected classification:

- `primary_theme`: The correct product area theme
- `issue_type`: The correct issue type

### Step 3: Validate Format

Ensure JSON matches the template structure:

- All required fields present
- `raw_conversation` includes full Intercom conversation object
- Ground truth labels match vocabulary

## Running the Full Test Suite

### Phase 1: Extractor Validation

```bash
# Validate extraction rates on 100 conversations
python scripts/validate_phase4_extractors.py --sample-size 100 --output results/extractor_validation.txt
```

**Review**:

- Check extraction rates are within expected ranges
- Validate sample extractions for quality
- Identify any edge cases

### Phase 2: Accuracy Testing

```bash
# Prepare test set with ground truth labels (50-100 conversations)
# Then run accuracy improvement tests

python scripts/test_phase4_accuracy_improvement.py \
  --test-set data/test_conversations.json \
  --output results/accuracy_improvement.txt
```

**Review**:

- Verify accuracy improvements meet targets
- Check confidence score improvements
- Identify misclassifications for further analysis

## Expected Results

### Extractor Validation

**Phase 4a (Help Articles)**:

- Extraction rate: 15-20% of conversations
- URL patterns: mix of help.tailwindapp.com, intercom.help, intercom://
- Data quality: article titles, categories, and summaries extracted correctly

**Phase 4b (Shortcut Stories)**:

- Extraction rate: 30-40% of conversations
- Story ID formats: mix of prefixed (sc-12345) and raw (12345)
- Data quality: labels, epics, names, and descriptions extracted correctly

### Accuracy Testing

**Baseline** (no context):

- Varies by dataset quality
- Establishes comparison baseline

**With Help Articles** (Phase 4a):

- +10-15% accuracy improvement on conversations with help articles
- Higher confidence scores
- Better disambiguation when user references documentation

**With Shortcut Stories** (Phase 4b):

- +15-20% accuracy improvement on conversations with Story ID v2
- Strongest improvement due to human-validated product area context
- More accurate theme classification

**Combined** (Phase 4a + 4b):

- +20-30% accuracy improvement on conversations with both contexts
- Highest confidence scores
- Most accurate classification

## Troubleshooting

### Issue: No conversations fetched

**Solution**: Implement Intercom API integration in `validate_phase4_extractors.py` or use `--test-data` flag with exported conversations

### Issue: API authentication failures

**Solution**: Verify environment variables:

- `INTERCOM_ACCESS_TOKEN` for help article extraction
- `SHORTCUT_API_TOKEN` for story extraction

### Issue: Low extraction rates

**Possible causes**:

- Test dataset may not be representative
- Custom attribute field names may differ
- URL patterns may need adjustment

### Issue: Accuracy improvements below targets

**Possible causes**:

- Ground truth labels may be incorrect
- Test set may be too small (increase to 100+ conversations)
- Context extraction may be failing silently (check logs)
- Baseline accuracy may already be very high (ceiling effect)

## Next Steps After Testing

1. **Document results** in `docs/phase4-test-results.md`
2. **Apply database migrations** if validation passes
3. **Integrate into pipeline** if accuracy improvements meet targets
4. **Set up monitoring** for extraction rates and accuracy in production

## Related Documentation

- `docs/phase4-test-results.md` - Unit test results and next steps
- `docs/phase4a-implementation.md` - Phase 4a implementation details
- `docs/phase4b-implementation.md` - Phase 4b implementation details
- `docs/session/phase4-testing-session.md` - Testing session summary
