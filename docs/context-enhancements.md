# Context Enhancement Design: Help Docs + Shortcut Integration

**Created**: 2026-01-07
**Updated**: 2026-01-07 (Corrected: Separated Help Articles from Shortcut Story Context)
**Status**: Phase 4a Complete ✅, Phase 4b In Progress 🚧
**Phases**: 4a-4c (immediate), Phase 5+ (future)

## Overview

This document defines **six enhancements** that leverage **two distinct data sources** to improve classification quality and downstream usefulness.

### Two Primary Data Sources

#### 1. Intercom Help Center Articles (Knowledge Base)

- **What**: Intercom's built-in help center / knowledge base articles
- **Access**: Via Intercom API (we have credentials)
- **How users interact**: Users reference articles in conversation messages (URLs)
- **Value**: Static documentation content provides semantic context
- **Example**: User says "I read https://help.tailwindapp.com/en/articles/123 but still confused"

#### 2. Shortcut ↔ Intercom Story Linking (Human-Validated Labels)

- **What**: Conversations linked to Shortcut stories by support team
- **Access (Intercom → Shortcut)**: Conversation has `Story ID v2` custom attribute → fetch that Shortcut story
- **Access (Shortcut → Intercom)**: Search Shortcut for Intercom conversation URLs → find all stories
- **Value**: Human-validated product area classification, labels, epics, descriptions
- **Example**: Conversation `12345` has `Story ID v2 = "sc-98765"` → Shortcut story has labels: ["Instagram", "Bug", "Scheduling"]

### Relationship Graph

These data sources create a **relationship graph**:

```
Help Articles ←→ Conversations ←→ Shortcut Stories

- Help articles ←→ Conversations: Article URLs in message bodies
- Conversations ←→ Shortcut stories: Story ID v2 attribute + URL search
- By extension: Help articles ←→ Shortcut stories (through conversations)
```

**Key insight**: This graph provides both:

- **Semantic context** from help articles (what users were trying to do)
- **Ground truth labels** from Shortcut stories (how humans categorized the issue)

---

## Enhancement 1: Help Article Context Injection ⭐

**Priority**: Phase 4a ✅ **COMPLETE**
**Complexity**: Low (1-2 days)
**Impact**: High (10-15% accuracy improvement on conversations with article references)

### Implementation Status

✅ **Complete** - See `docs/phase4a-implementation.md` for full details

**What was built**:

- `src/help_article_extractor.py` - Extraction and formatting logic
- `tests/test_help_article_extraction.py` - Comprehensive test suite
- `migrations/001_add_help_article_references.sql` - Database schema
- `src/db/models.py` - HelpArticleReference model
- `src/classifier_stage2.py` - Prompt integration

**GitHub Issue**: #18

---

## Enhancement 2: Shortcut Story Context Injection ⭐

**Priority**: Phase 4b 🚧 **IN PROGRESS**
**Complexity**: Low (1-2 days)
**Impact**: High (15-20% accuracy improvement on conversations with Story ID v2)

### How It Works

1. **Check for `Story ID v2`** in conversation custom attributes
   - Custom attribute: `custom_attributes.story_id_v2`
   - Format: `"sc-12345"` or similar Shortcut story ID

2. **Fetch Shortcut story** via Shortcut API
   - Endpoint: `GET /api/v3/stories/{story_id}`
   - Auth: Shortcut API token

3. **Extract story metadata**:
   - Story labels (product areas: "Instagram", "Scheduling", "Bug", etc.)
   - Story epic (higher-level grouping: "Publisher Improvements")
   - Story name (human-written issue summary)
   - Story description (detailed explanation)
   - Story state (In Development, Done, etc.)
   - Story workflow state

4. **Inject story context** into Stage 2 LLM prompt:

   ```
   The support team has already categorized this conversation:

   Linked Shortcut Story: sc-98765
   - Labels: Instagram, Scheduling, Bug
   - Epic: Publisher Improvements
   - Name: "Instagram posts not scheduling at correct times"
   - Description: "Users report that scheduled Instagram posts are posting 1-2 hours late..."
   - State: In Development

   This provides validated product area context.
   ```

5. **Store story linkage** in database for analytics

### Architecture Integration

**Plug-in Points**:

- Context extraction: Check `custom_attributes.story_id_v2` in Intercom conversation
- Story fetching: Shortcut API integration (new module)
- Prompt enrichment: `src/classifier_stage2.py` (add `shortcut_story_context` parameter)
- Database: Add `shortcut_story_links` table

**Implementation Plan**:

```python
# src/shortcut_story_extractor.py
class ShortcutStory(BaseModel):
    """Shortcut story metadata."""
    story_id: str
    name: str
    description: Optional[str]
    labels: List[str]
    epic_name: Optional[str]
    state: str
    workflow_state_name: str

class ShortcutStoryExtractor:
    def get_story_id_from_conversation(self, conversation: dict) -> Optional[str]:
        """Extract Story ID v2 from conversation custom attributes"""

    def fetch_story_metadata(self, story_id: str) -> Optional[ShortcutStory]:
        """Fetch story from Shortcut API"""

    def format_for_prompt(self, story: ShortcutStory) -> str:
        """Format story context for LLM prompt"""

    def extract_and_format(self, conversation: dict) -> str:
        """Extract story ID and format context in one step"""
```

**Database Schema**:

```sql
CREATE TABLE shortcut_story_links (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    story_id TEXT NOT NULL,
    story_name TEXT,
    story_labels JSONB,  -- Array of label strings
    story_epic TEXT,
    story_state TEXT,
    linked_at TIMESTAMP DEFAULT NOW(),

    UNIQUE (conversation_id, story_id)
);

-- Indexes
CREATE INDEX idx_story_links_story_id ON shortcut_story_links(story_id);
CREATE INDEX idx_story_links_conversation_id ON shortcut_story_links(conversation_id);
```

### Expected Impact

**Quality**:

- **15-20% accuracy improvement** on conversations with Story ID v2
- Estimated 30-40% of conversations have Story ID v2 (support team links frequently)
- Human-validated product area classification → strong disambiguation signal
- Example: Vague "scheduling issue" → Story labels reveal "Instagram" + "Legacy Publisher" → correct context

**Coverage**:

- Higher coverage than help articles (support links stories more often than users reference docs)
- Leverages existing support team categorization work (no additional manual effort)

**Usefulness**:

- Validates LLM classifications against human labels
- Identifies conversations support team already escalated (can skip auto-escalation)
- Provides ground truth for future model training/validation

### Success Metrics

- **Story linkage extraction rate**: Target 30-40% of conversations
- **Prompt enrichment rate**: 100% when Story ID v2 detected
- **Classification confidence improvement**: +15% avg on story-linked conversations
- **Label alignment**: 80%+ match between extracted themes and Shortcut labels

### Deliverables

- `src/shortcut_story_extractor.py` - Main extraction module
- `tests/test_shortcut_story_extraction.py` - Test suite
- `migrations/002_add_shortcut_story_links.sql` - Database migration
- `src/db/models.py` - ShortcutStoryLink model
- `src/classifier_stage2.py` - Add `shortcut_story_context` parameter

**GitHub Issue**: #23 (NEW - to be created)

---

## Enhancement 3: Documentation Coverage Gap Analysis

**Priority**: Phase 4c (After 4a + 4b)
**Complexity**: Low (2-3 days)
**Impact**: High (actionable support insights)

### How It Works

**Leverages data from Enhancement 1 (Help Articles)**

1. **Identify undocumented themes**:
   - Themes that frequently appear WITHOUT help article references
   - SQL: Find themes with COUNT(\*) >= 10 and no linked help articles

2. **Identify confusing articles**:
   - Articles users reference but still have product issues
   - SQL: Find articles referenced in conversations classified as `product_issue`

3. **Generate weekly reports**:
   - "Top 10 Undocumented Themes"
   - "Top 10 Confusing Articles" (referenced but didn't resolve issue)
   - "Documentation Gaps by Product Area"

### Architecture Integration

**Plug-in Points**:

- Analytics layer on top of stored theme + article reference data
- New module: `src/analytics/doc_coverage.py`
- Scheduled execution: Weekly cron job
- Output: Slack notifications, email, or dashboard

**Implementation**:

```python
# src/analytics/doc_coverage.py
class DocumentationCoverageAnalyzer:
    def find_undocumented_themes(self, min_frequency: int = 10) -> List[ThemeGap]:
        """Themes without corresponding help articles"""

    def find_confusing_articles(self, min_frequency: int = 5) -> List[ArticleGap]:
        """Articles that don't resolve issues"""

    def generate_weekly_report(self) -> CoverageReport:
        """Weekly documentation gap report"""
```

### Expected Impact

**Quality** (Indirect):

- Better docs → fewer confused users → cleaner conversations
- Reduces "how-to" questions that should be self-serve

**Usefulness**:

- **Actionable insights** for support/content team
- Data-driven documentation roadmap
- Measurable: "Added article for theme X → reduced conversations by Y%"

### Success Metrics

- Weekly report generation: 100% automated
- Gap identification: 5-10 undocumented themes per month
- Measurable impact: Track conversation reduction after adding docs

**GitHub Issue**: #19 (needs description update to reflect correct dependencies)

---

## Enhancement 4: Shortcut Story Ground Truth Validation

**Priority**: Phase 5 (Future)
**Complexity**: Medium (3-5 days)
**Impact**: Medium (objective quality metrics)

### How It Works

**Leverages data from Enhancement 2 (Shortcut Story Context)**

1. **Fetch conversations with `Story ID v2`** (already linked by support team)
2. **Run theme extraction** on these conversations (same pipeline as production)
3. **Fetch linked Shortcut story** labels via Enhancement 2's infrastructure
4. **Compare extracted themes to story labels**:
   - Match: Extracted theme aligns with story label → True Positive
   - Mismatch: Different labels → False Positive or vocabulary gap
   - Missing: Conversation has story but no theme extracted → False Negative
5. **Generate accuracy report** with specific mismatches
6. **Identify vocabulary gaps** (labels in Shortcut but not in our theme vocabulary)

### Expected Impact

**Quality**:

- **Objective accuracy measurement** against real human labels
- Identifies systematic classification errors
- Tracks accuracy improvements over time

**Coverage**:

- Finds vocabulary gaps (Shortcut uses "Carousel Posts" but we don't have that theme)
- Identifies over-detection (we extract themes Shortcut doesn't use)

**Usefulness**:

- Data-driven vocabulary refinement
- Prompt iteration metrics (track accuracy after prompt changes)
- Confidence in production classification quality

**GitHub Issue**: #20

---

## Enhancement 5: Vocabulary Feedback Loop from Shortcut Labels

**Priority**: Phase 5 (Alongside Enhancement 4)
**Complexity**: Medium (4-6 days)
**Impact**: High (keeps vocabulary aligned with reality)

### How It Works

**Uses bidirectional Shortcut ↔ Intercom linking**

1. **Search Shortcut** for stories containing Intercom conversation URLs
   - Pattern: `https://app.intercom.com/a/apps/*/inbox/*/conversation/*`
   - Returns all stories that reference Intercom conversations

2. **Extract story labels and epics** from matched stories

3. **Aggregate label frequency** (last 30 days):

   ```
   Instagram: 45 stories
   Scheduling: 32 stories
   Carousel Posts: 12 stories  ← NEW (not in vocabulary)
   ```

4. **Map to existing vocabulary**:
   - Existing labels: Already covered
   - New labels: Appear frequently but missing from vocabulary
   - Emerging labels: Low frequency, watch for trends

5. **Flag expansion suggestions**:
   - High priority: >10 occurrences
   - Watch list: 3-10 occurrences

6. **Human review + approval** → vocabulary expansion

7. **Next theme extraction** uses updated vocabulary

### Expected Impact

**Quality**:

- Keeps vocabulary aligned with actual product issues
- Prevents vocabulary drift over time
- Catches emergent themes early (new features, seasonal campaigns)

**Coverage**:

- Discovers themes our current vocabulary misses
- Leverages product team's existing categorization work

**Usefulness**:

- Data-driven vocabulary maintenance
- Reduces manual curation effort
- Measurable: "Added N themes from Shortcut feedback last quarter"

**GitHub Issue**: #21

---

## Enhancement 6: Theme-Based Story Suggestion

**Priority**: Phase 6+ (Future)
**Complexity**: High (10-15 days)
**Impact**: High (faster escalation, better tracking)

### How It Works

1. **Compute conversation embedding** (OpenAI embeddings API)
2. **Vector similarity search** against historical conversations
3. **Filter for conversations with Story ID v2**
4. **Suggest linked stories** to support agents:
   ```
   Similar Conversations:
   - Conversation #12345 (similarity: 0.92) → Story sc-456
   - Conversation #67890 (similarity: 0.87) → Story sc-789
   ```
5. **Display in support UI** (future integration)

### Expected Impact

**Quality**:

- Consistent conversation→story linking
- Similar issues linked to same story

**Usefulness**:

- Faster issue escalation
- Better tracking of recurring problems

### Infrastructure Requirements

- PostgreSQL pgvector extension
- OpenAI embeddings API (~$0.06/month for 3000 conversations)

**GitHub Issue**: #22

---

## Implementation Order

| Phase | Enhancement                   | Timeline   | Status      | Dependencies             |
| ----- | ----------------------------- | ---------- | ----------- | ------------------------ |
| 4a    | Help Article Context          | 1-2 days   | ✅ Complete | None                     |
| 4b    | Shortcut Story Context        | 1-2 days   | 🚧 Current  | Shortcut API integration |
| 4c    | Coverage Gap Analysis         | 2-3 days   | ⏳ Future   | Enhancement 1 (4a)       |
| 5     | Ground Truth Validation       | 3-5 days   | ⏳ Future   | Enhancement 2 (4b)       |
| 5     | Vocabulary Feedback Loop      | 4-6 days   | ⏳ Future   | Enhancement 4            |
| 6+    | Theme-Based Story Suggestions | 10-15 days | ⏳ Future   | Vector DB setup          |

---

## Success Metrics Summary

| Enhancement                | Key Metric                                        | Target                                 |
| -------------------------- | ------------------------------------------------- | -------------------------------------- |
| 1. Help Article Context    | Accuracy improvement on article-referenced convos | +10-15%                                |
| 2. Shortcut Story Context  | Accuracy improvement on story-linked convos       | +15-20%                                |
| 3. Coverage Gap Analysis   | Undocumented themes identified per month          | 5-10 themes                            |
| 4. Ground Truth Validation | Accuracy vs. Shortcut labels                      | Establish baseline, track improvements |
| 5. Vocabulary Feedback     | New themes added per month                        | 3-5 themes (initially)                 |
| 6. Story Suggestions       | Suggestion acceptance rate                        | 70%+                                   |

---

## Related Documents

- `PLAN.md` - Overall project plan (update with Phase 4b)
- `docs/architecture.md` - System architecture
- `docs/phase4a-implementation.md` - Phase 4a complete implementation
- GitHub Issues: #18 (done), #19 (update), #20-22 (future), #23 (create for 4b)

---

## Revision History

| Date       | Author        | Change                                                                                                              |
| ---------- | ------------- | ------------------------------------------------------------------------------------------------------------------- |
| 2026-01-07 | Claude + User | Initial design document                                                                                             |
| 2026-01-07 | Claude + User | **Corrected**: Separated Help Articles from Shortcut Story context into distinct enhancements. Now 6 total (was 5). |
