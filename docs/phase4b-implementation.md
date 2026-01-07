# Phase 4b Implementation: Shortcut Story Context Injection

**Status**: ✅ Implementation Complete, Unit Tests Passing (20/20)
**Date**: 2026-01-07
**GitHub Issue**: #23

## Overview

Phase 4b adds Shortcut story context extraction and injection to leverage human-validated product area classifications from support team's existing work. Expected to improve classification accuracy by 15-20% on conversations with Story ID v2 (estimated 30-40% of conversations).

## What Was Implemented

### 1. Core Module: `src/shortcut_story_extractor.py`

**Purpose**: Extract Shortcut story metadata from conversations and format for classification context

**Key Components**:

- `ShortcutStory` model - Structured story metadata (ID, name, labels, epic, description, state)
- `ShortcutStoryExtractor` class - Main extraction and formatting logic
  - `get_story_id_from_conversation()` - Extracts Story ID v2 from custom attributes
  - `fetch_story_metadata()` - Retrieves story details from Shortcut API
  - `format_for_prompt()` - Formats story context for LLM injection
  - `extract_and_format()` - Convenience method combining all steps

**Story ID Extraction**:

- Reads `custom_attributes.story_id_v2` from Intercom conversation
- Handles both prefixed (`sc-12345`) and raw (`12345`) formats
- Strips whitespace and normalizes ID

**Example Output**:

```
The support team has already categorized this conversation:

Linked Shortcut Story: 98765
  - Labels: Instagram, Scheduling, Bug
  - Epic: Publisher Improvements
  - Name: "Instagram posts not scheduling at correct times"
  - Description: "Users report scheduled Instagram posts posting 1-2 hours late..."
  - State: In Development

This provides validated product area context.
```

### 2. Database Schema: `migrations/002_add_shortcut_story_links.sql`

**New Table**: `shortcut_story_links`

```sql
- id (SERIAL PRIMARY KEY)
- conversation_id (FK to conversations)
- story_id (TEXT)
- story_name (TEXT)
- story_labels (JSONB - array of strings)
- story_epic (TEXT)
- story_state (TEXT)
- linked_at (TIMESTAMP)
```

**Indexes**:

- By story_id (find all conversations for a story)
- By conversation_id (find all stories for a conversation)
- By linked_at (trending stories)

**Analytics Views**:

- `most_linked_stories` - Top stories by conversation count + breakdown by issue type
- `conversations_with_stories` - Conversations enriched with story data
- `story_label_frequency` - Label occurrence for vocabulary expansion (Phase 5)

### 3. Database Model: `src/db/models.py`

**Added**: `ShortcutStoryLink` Pydantic model

- Matches database schema
- Validates story data
- Supports ORM conversion
- `story_labels` field as list[str] for JSON array

### 4. Stage 2 Classifier Integration: `src/classifier_stage2.py`

**Changes**:

- Added `shortcut_story_context` parameter to `classify_stage2()`
- Injected story context into LLM prompt template
- Story context appears after help article context, before resolution context

**Prompt Structure** (updated):

```
Customer Message:
{customer_message}

Support Response(s):
{support_messages}

{help_article_context}  ← Phase 4a

{shortcut_story_context}  ← NEW (Phase 4b)

{resolution_context}
```

### 5. Comprehensive Tests: `tests/test_shortcut_story_extraction.py`

**Test Coverage**:

- ✅ Extract Story ID v2 from custom attributes
- ✅ Handle Story ID with/without 'sc-' prefix
- ✅ Strip whitespace from Story ID
- ✅ Handle missing custom attributes gracefully
- ✅ Fetch story metadata from Shortcut API
- ✅ Handle API failures gracefully (returns None, doesn't crash)
- ✅ Extract labels from both object and string formats
- ✅ Extract epic information
- ✅ Format complete and minimal stories
- ✅ Truncate long descriptions to 500 chars
- ✅ Handle None story (returns empty string)
- ✅ End-to-end extraction and formatting

**Test Types**:

- Unit tests with mocked API responses
- Integration test markers for future live API tests

## How It Works (End-to-End Flow)

```
1. Support team links conversation to Shortcut story
   └─> Sets custom_attributes.story_id_v2 = "sc-98765"

2. Conversation reaches Stage 2 classifier
   └─> ShortcutStoryExtractor.extract_and_format(conversation)

3. Story ID extracted from custom attributes
   └─> get_story_id_from_conversation() → "98765"

4. Story metadata fetched from Shortcut API
   └─> fetch_story_metadata("98765") → ShortcutStory object

5. Story context formatted and injected into Stage 2 prompt
   └─> "Linked Shortcut Story: 98765, Labels: Instagram, Scheduling, Bug..."

6. LLM classifies with human-validated context
   └─> Strong product area signal improves accuracy

7. Story linkage stored in database
   └─> shortcut_story_links table for analytics
```

## Integration Points

### Existing Shortcut Client

Phase 4b leverages the existing `src/shortcut_client.py`:

- Uses established authentication pattern
- Reuses Shortcut API base URL and headers
- Extends functionality without modifying existing client

**Why separate extractor?**

- `ShortcutClient` is for _writing_ (creating/updating stories)
- `ShortcutStoryExtractor` is for _reading_ (fetching metadata for context)
- Separation of concerns: ticket creation vs. classification context

### Pipeline Integration (Future)

When ready to enable in production:

1. Add ShortcutStoryExtractor to pipeline orchestration
2. Call `extract_and_format()` before Stage 2 classification
3. Store story links to database after classification
4. Monitor extraction rate (target: 30-40% of conversations)

**Code Pattern** (similar to Phase 4a):

```python
from src.shortcut_story_extractor import ShortcutStoryExtractor

# Initialize extractors
story_extractor = ShortcutStoryExtractor()

# Extract story context
story_context = story_extractor.extract_and_format(raw_conversation)

# Pass to Stage 2
classify_stage2(
    customer_message,
    support_messages,
    shortcut_story_context=story_context  # Optional parameter
)
```

## Success Metrics (Defined, Not Yet Measured)

| Metric                                | Target                                        | Measurement                                  |
| ------------------------------------- | --------------------------------------------- | -------------------------------------------- |
| Story linkage extraction rate         | 30-40% of conversations                       | Count conversations with Story ID v2 / total |
| Prompt enrichment rate                | 100% when Story ID v2 detected                | Count enriched prompts / Story IDs extracted |
| Classification confidence improvement | +15% avg on story-linked conversations        | Compare confidence before/after on test set  |
| Label alignment                       | 80%+ match between themes and Shortcut labels | Ground truth validation (Phase 5)            |

**Note**: Metrics will be measured during Phase 4b testing and production rollout.

## What's Next

### Testing Results

**Unit Tests**: ✅ 20/20 passing (100%)

See `docs/phase4-test-results.md` for complete test results and issues fixed.

### Immediate Next Steps (Real Data Validation)

2. **Test Against Real Intercom Data**
   - Fetch 50-100 conversations with Story ID v2
   - Run story extraction
   - Validate extraction accuracy (manual review)
   - Measure extraction rate (% with Story ID v2)

3. **Test Classification Improvement**
   - Run Stage 2 on conversations WITH story context
   - Run Stage 2 on conversations WITHOUT story context
   - Compare confidence scores and accuracy
   - Target: +15-20% improvement on story-linked conversations

4. **Apply Database Migration**

   ```bash
   psql -U user -d feedforward -f migrations/002_add_shortcut_story_links.sql
   ```

5. **Integrate into Pipeline**
   - Add ShortcutStoryExtractor initialization to pipeline
   - Call extract_and_format before Stage 2
   - Store story links after classification

### Phase 4c (Next Sprint)

Once Phase 4b is validated and deployed:

- **Documentation Coverage Gap Analysis** (GitHub Issue #19)
- Build on help article reference data (Phase 4a)
- Generate "Top 10 Undocumented Themes" reports
- Identify "confusing articles" (referenced but still had issues)

### Phase 5 (Future)

Leverage Shortcut story data for:

- **Enhancement 4**: Ground Truth Validation (compare extracted themes to story labels)
- **Enhancement 5**: Vocabulary Feedback Loop (expand theme vocabulary from Shortcut labels)

## Files Modified/Created

### Created

- ✅ `src/shortcut_story_extractor.py` (234 lines)
- ✅ `tests/test_shortcut_story_extraction.py` (298 lines)
- ✅ `migrations/002_add_shortcut_story_links.sql` (98 lines)
- ✅ `docs/phase4b-implementation.md` (this file)

### Modified

- ✅ `src/db/models.py` (added ShortcutStoryLink model)
- ✅ `src/classifier_stage2.py` (added shortcut_story_context parameter + prompt injection)
- ✅ `PLAN.md` (added Phase 4b, renumbered Phase 4b→4c)
- ✅ `docs/context-enhancements.md` (corrected to separate Help Articles from Shortcut Story context - now 6 enhancements)

### GitHub Issues

- ✅ #23 - Enhancement 2: Shortcut Story Context Injection (Phase 4b) - Created

## Design Documentation

See `docs/context-enhancements.md` for:

- Complete design of all 6 context enhancements
- Distinction between Help Articles (Phase 4a) and Shortcut Stories (Phase 4b)
- Architectural integration details
- Expected impact analysis
- Implementation phasing (4a → 4b → 4c → 5 → 6+)
- Success metrics for each enhancement

## Dependencies

**Python Packages** (already in project):

- `requests` - HTTP client for Shortcut API
- `pydantic` - Data validation for models
- `pytest` - Testing framework (dev)

**External APIs**:

- Shortcut API - Story metadata fetching
  - Endpoint: `GET /api/v3/stories/{story_id}`
  - Auth: Token header (SHORTCUT_API_TOKEN)
  - Rate limits: Standard Shortcut API limits apply

**Existing Modules**:

- `src/shortcut_client.py` - Reused for API patterns and auth

**Environment Variables**:

- `SHORTCUT_API_TOKEN` - Required (same as existing shortcut_client.py)

## Notes & Considerations

### Graceful Degradation

- Story context is **optional enrichment**
- Pipeline doesn't break if Story ID v2 missing or fetch fails
- Missing story context → classifier works with existing context (help articles, URL, support messages)
- No impact on conversations without Story ID v2

### Performance

- Story metadata fetching adds ~200-500ms per story
- Only affects conversations with Story ID v2 (30-40% estimated)
- Total impact: +0.2-0.5s per story-linked conversation
- Acceptable for batch processing (Stage 2 is not time-critical)

### API Rate Limits

- Shortcut API: Standard rate limits apply
- Story endpoint moderate traffic (only when Story ID v2 present)
- Consider caching story metadata (future optimization)

### Data Quality

- Story ID v2 set manually by support team → high coverage but not 100%
- Labels and epics are human-validated → high quality product area context
- Story descriptions may be sparse for older stories

### Privacy & Data

- No PII in story metadata (labels, epics, names are internal product areas)
- Story IDs are internal Shortcut identifiers (safe to store)
- No customer data sent to Shortcut API (only story IDs)

## Comparison with Phase 4a (Help Articles)

| Aspect             | Phase 4a: Help Articles          | Phase 4b: Shortcut Stories            |
| ------------------ | -------------------------------- | ------------------------------------- |
| **Data Source**    | Intercom Help Center             | Shortcut (project management)         |
| **Trigger**        | User references article URL      | Support links Story ID v2             |
| **Coverage**       | 15-20% of conversations          | 30-40% of conversations               |
| **Context Type**   | Semantic (what user tried to do) | Categorical (validated product areas) |
| **Accuracy Boost** | +10-15%                          | +15-20%                               |
| **Value**          | Identifies doc gaps              | Ground truth for validation           |
| **Human Input**    | None (user action)               | Manual (support categorization)       |

**Combined Impact**: Conversations with BOTH help articles AND story links get dual context boost.

## Related Documentation

- `docs/context-enhancements.md` - Complete enhancement design (all 6 phases)
- `docs/phase4a-implementation.md` - Phase 4a (Help Articles) implementation
- `docs/architecture.md` - System architecture (needs update post-deployment)
- `PLAN.md` - Project plan with Phase 4b details
- GitHub Issue #23 - Implementation tracking

---

**Status**: ✅ Implementation complete, ready for testing and validation
**Next**: Run tests, validate on real data, measure accuracy improvement, integrate into pipeline
