# URL Context Integration for Theme Extraction

**Date**: 2026-01-07
**Task**: Integrate URL context boosting into theme extractor to disambiguate three schedulers

## Problem Statement

With three distinct scheduling systems in Tailwind (Pin Scheduler, Legacy Publisher, Multi-Network), keywords alone cannot reliably distinguish between them. All three use similar terminology like "scheduling", "posts not publishing", "drafts", etc.

**Example ambiguity**:

- "My posts aren't scheduling" could be:
  - Pin Scheduler issue → `/advanced-scheduler/pinterest`
  - Legacy Publisher issue → `/publisher/queue`
  - Multi-Network issue → `/dashboard/v2/scheduler`

**Solution**: Use `source.url` from Intercom conversations to boost the correct product area during theme extraction.

## Implementation

### 1. Data Model Changes

**Added `source_url` field to conversation models**:

```python
# src/db/models.py - Conversation model
class Conversation(BaseModel):
    source_body: Optional[str] = None
    source_type: Optional[str] = None
    source_subject: Optional[str] = None
    source_url: Optional[str] = None  # NEW - URL user was on
    contact_email: Optional[str] = None
```

```python
# src/intercom_client.py - IntercomConversation model
class IntercomConversation(BaseModel):
    source_body: str
    source_type: Optional[str] = None
    source_subject: Optional[str] = None
    source_url: Optional[str] = None  # NEW
```

**Extraction from Intercom API**:

```python
# src/intercom_client.py - parse_conversation()
return IntercomConversation(
    id=str(conv.get("id")),
    created_at=created_at,
    source_body=self.strip_html(source.get("body", "")),
    source_type=source.get("type"),
    source_subject=source.get("subject"),
    source_url=source.get("url"),  # NEW - extract from source object
    contact_email=author.get("email"),
    contact_id=author.get("id"),
    user_id=user_id,
)
```

### 2. Vocabulary Enhancement

**Added URL context mapping support to ThemeVocabulary**:

```python
# src/vocabulary.py
class ThemeVocabulary:
    def __init__(self, vocab_path: Optional[Path] = None):
        self._url_context_mapping: dict[str, str] = {}  # NEW
        self._product_area_mapping: dict[str, list[str]] = {}  # NEW
        self._load()

    def _load(self) -> None:
        # Load URL context mapping from vocabulary file
        self._url_context_mapping = data.get("url_context_mapping", {})
        # Remove comment entries (keys starting with "_")
        self._url_context_mapping = {
            k: v for k, v in self._url_context_mapping.items()
            if not k.startswith("_")
        }

    def match_url_to_product_area(self, url: Optional[str]) -> Optional[str]:
        """Match a URL to a product area using url_context_mapping."""
        if not url or not self._url_context_mapping:
            return None

        # Check each pattern against the URL
        for pattern, product_area in self._url_context_mapping.items():
            if pattern in url:
                logger.info(f"URL context match: {pattern} -> {product_area}")
                return product_area

        return None
```

**URL patterns from vocabulary (v2.9)**:

```json
{
  "url_context_mapping": {
    "/dashboard/v2/advanced-scheduler/pinterest": "Next Publisher",
    "/advanced-scheduler/pinterest": "Next Publisher",
    "/publisher/queue": "Legacy Publisher",
    "/publisher/drafts": "Legacy Publisher",
    "/dashboard/v2/drafts": "Multi-Network",
    "/dashboard/v2/scheduler": "Multi-Network"
  }
}
```

### 3. Theme Extractor Integration

**Enhanced extraction prompt with URL context hint**:

```python
# src/theme_extractor.py - extract()

# Check for URL context to boost product area matching
url_matched_product_area = None
url_context_hint = ""
if self.use_vocabulary and self.vocabulary and hasattr(conv, 'source_url'):
    url_matched_product_area = self.vocabulary.match_url_to_product_area(conv.source_url)
    if url_matched_product_area:
        url_context_hint = f"""
## URL Context

The user was on a page related to **{url_matched_product_area}** when they started this conversation.
**IMPORTANT**: Strongly prefer themes from the {url_matched_product_area} product area when matching.
"""
```

**Prioritize themes from matched product area**:

```python
# Get known themes from vocabulary (if enabled)
if self.use_vocabulary and self.vocabulary:
    # If we have URL context, prioritize themes from that product area
    if url_matched_product_area:
        known_themes = self.vocabulary.format_for_prompt(
            product_area=url_matched_product_area,
            max_themes=50
        )
    else:
        known_themes = self.vocabulary.format_for_prompt(max_themes=50)
```

**Updated prompt template**:

```python
THEME_EXTRACTION_PROMPT = """...

## Product Context

{product_context}

{url_context_hint}  # NEW - injected when URL matches

## KNOWN THEMES

{known_themes}  # Prioritized by product area if URL matched

...
"""
```

## Testing

**Created `tools/test_url_context.py`** with 5 test cases:

| Test Case                 | URL Pattern                                  | Expected Match   | Result |
| ------------------------- | -------------------------------------------- | ---------------- | ------ |
| Pin Scheduler             | `/dashboard/v2/advanced-scheduler/pinterest` | Next Publisher   | ✓ Pass |
| Legacy Publisher          | `/publisher/queue`                           | Legacy Publisher | ✓ Pass |
| Multi-Network Scheduler   | `/dashboard/v2/scheduler`                    | Multi-Network    | ✓ Pass |
| Multi-Network Drafts      | `/dashboard/v2/drafts`                       | Multi-Network    | ✓ Pass |
| No URL (should not match) | `None`                                       | None             | ✓ Pass |

**Test output**:

```
✓ Loaded vocabulary with 27 URL patterns

Test: Pin Scheduler (Next Publisher)
  URL: https://www.tailwindapp.com/dashboard/v2/advanced-scheduler/pinterest
  ✓ Matched: Next Publisher

Test: Legacy Publisher
  URL: https://www.tailwindapp.com/publisher/queue
  ✓ Matched: Legacy Publisher

Test: Multi-Network Scheduler
  URL: https://www.tailwindapp.com/dashboard/v2/scheduler
  ✓ Matched: Multi-Network

Test: Multi-Network Drafts
  URL: https://www.tailwindapp.com/dashboard/v2/drafts
  ✓ Matched: Multi-Network

Test: No URL (should not match)
  URL: None
  ✓ No match (as expected)
```

## How It Works

1. **Conversation arrives** with `source.url` field from Intercom
2. **URL matching** checks if URL contains any patterns from `url_context_mapping`
3. **Product area boost** if match found:
   - Inject URL context hint into LLM prompt
   - Prioritize themes from matched product area in known themes list
   - LLM strongly prefers themes from that product area
4. **Fallback** if no URL match: standard theme extraction (no boosting)

## Example Flow

**Scenario**: User reports "My posts aren't scheduling" on `/dashboard/v2/scheduler`

1. URL matches pattern `/dashboard/v2/scheduler` → **Multi-Network**
2. Prompt includes: "The user was on a page related to **Multi-Network** when they started this conversation. **IMPORTANT**: Strongly prefer themes from the Multi-Network product area when matching."
3. Known themes list prioritized: Multi-Network themes shown first
4. LLM extracts: `multinetwork_scheduling_failure` (Multi-Network) ✓

**Without URL context**: Same message might match `scheduling_failure` (Next Publisher) ✗

## Benefits

### 1. Disambiguation Accuracy

**Before URL context** (ambiguous keywords):

- "scheduling not working" → Could match any of 3 schedulers
- "posts sent back to drafts" → Pin Scheduler or Legacy Publisher?
- "fill empty time slots" → Next or Legacy Publisher?

**After URL context** (URL disambiguates):

- User on `/advanced-scheduler/pinterest` + "scheduling not working" → Pin Scheduler ✓
- User on `/publisher/queue` + "posts sent back to drafts" → Legacy Publisher ✓
- User on `/dashboard/v2/scheduler` + "Instagram not posting" → Multi-Network ✓

### 2. Proper Issue Routing

With three schedulers having different architectures and teams:

- **Pin Scheduler** issues → Next Publisher team
- **Legacy Publisher** issues → Original Publisher team
- **Multi-Network** issues → Cross-platform scheduling team

URL context ensures issues route to the correct team immediately.

### 3. Coverage Completeness

With v2.9 vocabulary + URL context:

- ✓ Pin Scheduler (5 themes) - Pinterest-only, new system
- ✓ Legacy Publisher (3 themes) - Pinterest-only, old system
- ✓ Multi-Network (3 themes) - Cross-platform (Pinterest/Instagram/Facebook)

All scheduling systems now have proper theme coverage AND URL-based disambiguation.

## Limitations and Future Work

### Current Limitations

1. **URL availability**: Not all Intercom conversations include `source.url` (e.g., email-initiated conversations)
2. **Pattern-based matching**: Uses simple substring matching (e.g., `/scheduler/` in URL)
3. **Single product area**: URL can only boost one product area (first match wins)

### Future Enhancements

1. **Fuzzy URL matching**: Handle URL variations, query parameters, fragments
2. **Multi-signal boosting**: Combine URL + keywords + conversation type for stronger disambiguation
3. **Confidence scoring**: Track how often URL context improves classification accuracy
4. **Dynamic pattern learning**: Automatically discover new URL → product area patterns from labeled data

## Validation on Real Data

**Next step**: Run theme extraction on real Intercom conversations to measure impact.

**Expected improvements**:

- Legacy Publisher: 64.3% → 75%+ (better "fill empty slots" routing)
- Next Publisher: 41.1% → 60%+ (better Pin Scheduler disambiguation)
- Multi-Network: Baseline → 70%+ (new product area, URL critical for detection)

**Measurement approach**:

1. Mine Shortcut for stories with Intercom links (user already provided script)
2. Extract conversations from Intercom API (includes source.url)
3. Run theme extraction with URL context enabled
4. Compare product area routing against manual Shortcut labels

## Files Modified

1. `src/db/models.py` - Added `source_url` field to Conversation
2. `src/intercom_client.py` - Added `source_url` field to IntercomConversation, extract from source object
3. `src/vocabulary.py` - Added URL context mapping support, `match_url_to_product_area()` method
4. `src/theme_extractor.py` - Added URL context boosting logic, updated prompt template
5. `tools/test_url_context.py` - Created test suite for URL matching

## Configuration

URL patterns are defined in `config/theme_vocabulary.json`:

```json
{
  "version": "2.9",
  "url_context_mapping": {
    "_comment": "Maps Intercom source.url patterns to Product Areas...",
    "/dashboard/v2/advanced-scheduler/pinterest": "Next Publisher",
    "/advanced-scheduler/pinterest": "Next Publisher",
    "/publisher/queue": "Legacy Publisher",
    "/publisher/drafts": "Legacy Publisher",
    "/dashboard/v2/drafts": "Multi-Network",
    "/dashboard/v2/scheduler": "Multi-Network"
  }
}
```

To add new patterns:

1. Edit `config/theme_vocabulary.json`
2. Add pattern → product area mapping to `url_context_mapping`
3. Restart theme extraction (vocabulary auto-loads)

## Conclusion

URL context integration completes the infrastructure for disambiguating Tailwind's three scheduling systems. Combined with v2.9 vocabulary (Multi-Network themes), we now have:

1. ✓ **Theme coverage** for all three schedulers
2. ✓ **URL disambiguation** to route issues correctly
3. ✓ **Tested implementation** with 100% test pass rate

**Ready for real Intercom data validation**.
