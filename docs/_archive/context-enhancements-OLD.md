# Context Enhancement Design: Help Docs + Shortcut Integration

**Created**: 2026-01-07
**Status**: Approved for Implementation
**Phase**: 4a-4b (immediate), Phase 5+ (future)

## Overview

This document defines five enhancements that leverage new data sources to improve classification quality and downstream usefulness:

1. **Intercom Help Center Articles** - Static knowledge base of support documentation
2. **Shortcut ↔ Intercom Linking** - Bidirectional conversation-story mapping via Story ID v2 and URL patterns

These data sources create a **relationship graph**:

- Help articles ↔ Conversations (via article links/references)
- Conversations ↔ Shortcut stories (via Story ID v2 and URL patterns)
- By extension: Help articles ↔ Shortcut stories (through conversations)

This graph provides **ground truth labels** and **semantic context** not currently available.

---

## Enhancement 1: Help Article Context Injection ⭐

**Priority**: Phase 4a (Immediate)
**Complexity**: Low (1-2 days)
**Impact**: High (10-15% accuracy improvement)

### How It Works

1. **Extract help article references** from conversation:
   - Parse message bodies for Intercom help article URLs
   - Check conversation metadata for linked articles
   - Pattern: `https://help.tailwindapp.com/en/articles/*` or `intercom://article/*`

2. **Fetch article content** via Intercom API:
   - Article title
   - Article category/collection
   - Article body (first 500 chars or summary)
   - Article tags (if available)

3. **Inject into Stage 2 prompt**:

   ```
   The user referenced this help article:
   Title: "How to connect Instagram Business accounts"
   Category: Account Setup > Social Connections
   Summary: "Instagram Business accounts require a linked Facebook Page..."

   This provides context about what the user was trying to do.
   ```

4. **Store article references** in database for analytics

### Architecture Integration

**Plug-in Points**:

- Context extraction: `src/intercom_client.py` (alongside `source.url` extraction)
- Prompt enrichment: `src/classifier_stage2.py` (append to system prompt)
- Database: Add `help_article_references` table and foreign key to `conversations`

**Implementation**:

```python
# src/help_article_extractor.py
class HelpArticleExtractor:
    def extract_article_urls(self, conversation: IntercomConversation) -> List[str]:
        """Extract help article URLs from conversation messages"""

    def fetch_article_metadata(self, article_url: str) -> HelpArticle:
        """Fetch article title, category, summary via Intercom API"""

    def format_for_prompt(self, articles: List[HelpArticle]) -> str:
        """Format article context for LLM prompt"""
```

**Database Schema**:

```sql
CREATE TABLE help_article_references (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    article_id VARCHAR(255),
    article_url TEXT,
    article_title TEXT,
    article_category TEXT,
    referenced_at TIMESTAMP DEFAULT NOW()
);
```

### Expected Impact

**Quality**:

- **10-15% accuracy improvement** on conversations that reference docs
- Resolves ambiguity when URL patterns alone are insufficient
- Example: User on `/scheduler` page references Instagram help article → clearly Instagram Scheduler issue, not other schedulers

**Coverage**:

- Helps with edge cases where users follow documentation but still have issues
- Identifies documentation quality problems (many users reference article X but still confused)

**Usefulness**:

- Links conversations to documentation gaps (see Enhancement 2)
- Provides semantic context beyond just page URL
- Supports future "improve this article" workflows

### Success Metrics

- **Article reference extraction rate**: Target 15-20% of conversations
- **Prompt enrichment rate**: 100% when articles detected
- **Classification confidence**: +10% avg on article-referenced conversations
- **Database integrity**: 100% article references stored

---

## Enhancement 2: Documentation Coverage Gap Analysis ⭐

**Priority**: Phase 4b (Next Sprint)
**Complexity**: Low (2-3 days)
**Impact**: High (actionable support insights)

### How It Works

1. **Track which conversations reference help articles** (from Enhancement 1)

2. **Identify conversations with shared themes but NO article references**:

   ```sql
   -- Find themes that appear frequently without documentation
   SELECT theme_signature, COUNT(*) as frequency
   FROM themes t
   LEFT JOIN help_article_references h ON t.conversation_id = h.conversation_id
   WHERE h.id IS NULL  -- No help article referenced
   GROUP BY theme_signature
   HAVING COUNT(*) >= 10
   ORDER BY frequency DESC
   ```

3. **Find conversations that reference articles and STILL have issues**:

   ```sql
   -- Articles that don't resolve user problems
   SELECT h.article_title, COUNT(*) as issue_frequency
   FROM help_article_references h
   JOIN conversations c ON h.conversation_id = c.id
   JOIN themes t ON c.id = t.conversation_id
   WHERE c.conversation_type = 'product_issue'  -- Still had a problem
   GROUP BY h.article_title
   ORDER BY issue_frequency DESC
   ```

4. **Generate reports**:
   - "Top 10 Undocumented Themes" (no articles exist)
   - "Top 10 Confusing Articles" (users read but still confused)
   - "Documentation Gaps by Product Area"

### Architecture Integration

**Plug-in Points**:

- Analytics layer on top of stored theme data
- New reporting module: `src/analytics/doc_coverage.py`
- Output to Slack, email, or dashboard

**Implementation**:

```python
# src/analytics/doc_coverage.py
class DocumentationCoverageAnalyzer:
    def find_undocumented_themes(self, min_frequency: int = 10) -> List[ThemeGap]:
        """Identify themes without corresponding help articles"""

    def find_confusing_articles(self, min_frequency: int = 5) -> List[ArticleGap]:
        """Find articles that don't resolve issues"""

    def generate_weekly_report(self) -> CoverageReport:
        """Generate weekly documentation gap report"""
```

### Expected Impact

**Quality** (Indirect):

- Better docs → fewer confused users → cleaner conversations
- Reduces "how-to" questions that should be self-serve

**Coverage**:

- Identifies knowledge base blind spots
- Prioritizes documentation work by frequency

**Usefulness**:

- **Actionable insights** for support/content team
- Data-driven documentation roadmap
- Measurable impact: "Added article for theme X → reduced conversations by Y%"

### Success Metrics

- **Weekly report generation**: 100% automated
- **Gap identification**: Find 5-10 undocumented themes per month
- **Article improvement**: Track article additions/updates triggered by reports
- **Conversation reduction**: Measure before/after adding docs

---

## Enhancement 3: Shortcut Story Ground Truth Validation

**Priority**: Phase 5 (After 4a/4b)
**Complexity**: Medium (3-5 days)
**Impact**: Medium (objective quality metrics)

### How It Works

1. **Fetch conversations with `Story ID v2` metadata**:
   - Intercom API returns conversations with custom attribute `Story ID v2`
   - These conversations were manually linked to Shortcut stories by support agents

2. **Run theme extraction** on these conversations (same pipeline as production)

3. **Fetch linked Shortcut story** via Shortcut API:
   - Story labels (e.g., "Instagram", "Scheduling", "Bug")
   - Story epic (e.g., "Publisher Improvements")
   - Story title and description

4. **Compare extracted themes to story labels**:
   - **Match**: Extracted theme aligns with story label → True Positive
   - **Mismatch**: Extracted theme differs → False Positive or vocabulary gap
   - **No theme extracted**: Conversation has story but no theme → False Negative

5. **Generate accuracy report**:

   ```
   Ground Truth Validation Report
   ================================
   Total conversations: 150
   Matched themes: 112 (74.7%)
   Mismatched themes: 23 (15.3%)
   Missing themes: 15 (10.0%)

   Top Mismatches:
   - Extracted "scheduling_failure_legacy" → Story label "Pin Scheduler" (5 cases)
   - Extracted "instagram_reels" → Story label "Instagram Stories" (3 cases)
   ```

### Architecture Integration

**Plug-in Points**:

- Separate validation pipeline (runs weekly/monthly)
- New module: `src/validation/ground_truth.py`
- Uses same theme extraction code as production
- Outputs accuracy report for human review

**Implementation**:

```python
# src/validation/ground_truth.py
class GroundTruthValidator:
    def fetch_conversations_with_stories(self) -> List[ConversationStoryPair]:
        """Fetch conversations that have Story ID v2"""

    def extract_themes_from_conversations(self, conversations: List) -> List[Theme]:
        """Run production theme extraction"""

    def fetch_shortcut_stories(self, story_ids: List[str]) -> List[ShortcutStory]:
        """Fetch Shortcut stories via API"""

    def compare_themes_to_labels(self, themes: List[Theme], stories: List[ShortcutStory]) -> ValidationReport:
        """Compare extracted themes to story labels"""

    def generate_report(self) -> ValidationReport:
        """Generate accuracy report with mismatches"""
```

**Database Schema**:

```sql
CREATE TABLE ground_truth_validations (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id),
    story_id VARCHAR(255),
    extracted_theme VARCHAR(255),
    story_label VARCHAR(255),
    match_status VARCHAR(50),  -- 'matched', 'mismatched', 'missing'
    validated_at TIMESTAMP DEFAULT NOW()
);
```

### Expected Impact

**Quality**:

- **Objective accuracy measurement** (currently only have test set)
- Real-world validation against human-labeled data
- Identifies systematic classification errors

**Coverage**:

- Identifies vocabulary gaps (themes in stories but not in our vocabulary)
- Finds themes we're over-detecting (false positives)

**Usefulness**:

- Data-driven vocabulary refinement
- Prompt iteration metrics (track accuracy over time)
- Confidence in production classification

### Success Metrics

- **Validation coverage**: 100+ conversations per validation run
- **Accuracy baseline**: Establish current accuracy vs. Shortcut labels
- **Improvement tracking**: Measure accuracy changes after vocabulary updates
- **Mismatch resolution**: Review and fix 80% of mismatches within 2 weeks

---

## Enhancement 4: Vocabulary Feedback Loop from Shortcut Labels ⭐

**Priority**: Phase 5 (Alongside Enhancement 3)
**Complexity**: Medium (4-6 days)
**Impact**: High (keeps vocabulary aligned with reality)

### How It Works

1. **Periodically fetch Shortcut stories** created from Intercom conversations:
   - Search Shortcut for stories containing Intercom conversation URLs
   - Pattern: `https://app.intercom.com/a/apps/*/inbox/*/conversation/*`
   - Returns all stories that reference Intercom conversations

2. **Extract story labels, epics, and titles**:
   - Labels: "Instagram", "Scheduling", "Bug", "Feature Request"
   - Epics: "Publisher Improvements", "Analytics Enhancements"
   - Titles: Human-written summaries of the issue

3. **Aggregate label frequency**:

   ```
   Label Frequency Analysis (Last 30 Days)
   =======================================
   Instagram: 45 stories
   Scheduling: 32 stories
   Analytics: 18 stories
   Carousel Posts: 12 stories  ← NEW LABEL (not in our vocabulary)
   ```

4. **Map to existing theme vocabulary**:
   - **Existing labels**: Already covered by themes
   - **New labels**: Appear frequently but missing from vocabulary
   - **Emerging labels**: Low frequency now, watch for trends

5. **Flag vocabulary expansion suggestions**:

   ```
   Vocabulary Expansion Suggestions
   =================================
   HIGH PRIORITY (>10 occurrences):
   - "Carousel Posts" (12 stories) → Suggest adding theme: instagram_carousel_posts
   - "Link in Bio" (15 stories) → Suggest adding theme: link_in_bio_issues

   WATCH LIST (3-10 occurrences):
   - "TikTok Analytics" (5 stories) → Monitor for next month
   ```

6. **Human review + approval**:
   - Support/product team reviews suggestions
   - Approves new themes with keywords and URL patterns
   - Updates `config/theme_vocabulary.json`

7. **Next theme extraction uses updated vocabulary**

### Architecture Integration

**Plug-in Points**:

- Standalone pipeline (runs monthly)
- New module: `src/vocabulary/feedback_loop.py`
- Outputs vocabulary expansion suggestions
- Human review workflow (Slack message + approval)

**Implementation**:

```python
# src/vocabulary/feedback_loop.py
class VocabularyFeedbackLoop:
    def fetch_intercom_stories_from_shortcut(self, days: int = 30) -> List[ShortcutStory]:
        """Search Shortcut for stories with Intercom URLs"""

    def extract_labels_and_epics(self, stories: List[ShortcutStory]) -> LabelFrequency:
        """Aggregate label frequency"""

    def map_to_existing_vocabulary(self, labels: LabelFrequency) -> VocabularyMapping:
        """Find labels not in current vocabulary"""

    def generate_expansion_suggestions(self, unmapped_labels: List[str]) -> List[ThemeSuggestion]:
        """Suggest new themes based on frequency"""

    def send_review_notification(self, suggestions: List[ThemeSuggestion]) -> None:
        """Notify team for human review (Slack/email)"""
```

### Expected Impact

**Quality**:

- **Keeps vocabulary aligned** with actual product issues
- Prevents vocabulary drift over time
- Catches emergent themes early

**Coverage**:

- Discovers themes our current vocabulary misses
- Product team already categorizes issues in Shortcut - we leverage their work
- Identifies seasonal/campaign-specific themes

**Usefulness**:

- Data-driven vocabulary maintenance
- Reduces manual vocabulary curation effort
- Measurable: "Added N themes from Shortcut feedback last quarter"

### Success Metrics

- **Monthly feedback loop execution**: 100% automated
- **Label extraction coverage**: 80%+ of Shortcut stories analyzed
- **Expansion suggestions**: 3-5 new themes per month (initially, tapers over time)
- **Human review response time**: <1 week from suggestion to approval
- **Vocabulary growth**: Track version updates (currently v2.9)

---

## Enhancement 5: Theme-Based Story Suggestion

**Priority**: Future (Requires ML Infrastructure)
**Complexity**: High (10-15 days)
**Impact**: High (faster escalation, better tracking)

### How It Works

1. **Compute conversation embedding** when extracting themes:
   - Use OpenAI embeddings API (`text-embedding-3-small`)
   - Store embedding alongside theme in database

2. **Vector similarity search** against historical conversations:
   - When new conversation arrives, compute embedding
   - Find top 5 most similar conversations (cosine similarity)
   - Filter for conversations that have `Story ID v2` set

3. **Suggest linked stories** to support agents:

   ```
   Similar Conversations:
   - Conversation #12345 (similarity: 0.92) → Linked to Story ABC-123
   - Conversation #67890 (similarity: 0.87) → Linked to Story ABC-456

   Suggestion: Consider linking this conversation to one of these stories.
   ```

4. **Display in support UI** (future integration):
   - Intercom widget or Slack bot
   - "This looks similar to [Story XYZ] - link it?"

### Architecture Integration

**Plug-in Points**:

- Post-theme-extraction step
- Requires vector database (PostgreSQL with pgvector extension)
- New module: `src/recommendations/story_linker.py`
- API endpoint for real-time suggestions during support triage

**Implementation**:

```python
# src/recommendations/story_linker.py
class StoryLinker:
    def compute_embedding(self, conversation: IntercomConversation) -> np.ndarray:
        """Compute OpenAI embedding for conversation"""

    def find_similar_conversations(self, embedding: np.ndarray, top_k: int = 5) -> List[SimilarConversation]:
        """Vector similarity search in database"""

    def filter_conversations_with_stories(self, conversations: List) -> List[ConversationStoryPair]:
        """Keep only conversations that have Story ID v2"""

    def suggest_story_links(self, conversation_id: int) -> List[StorySuggestion]:
        """Generate story link suggestions"""
```

**Database Schema**:

```sql
-- Add pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to conversations
ALTER TABLE conversations ADD COLUMN embedding vector(1536);

-- Create index for fast similarity search
CREATE INDEX ON conversations USING ivfflat (embedding vector_cosine_ops);
```

### Expected Impact

**Quality**:

- **Consistent conversation→story linking** (reduces human error)
- Ensures similar issues are linked to same story

**Coverage**:

- More conversations linked to stories (better data for future analysis)
- Catches recurring problems that support might miss

**Usefulness**:

- **Faster issue escalation** (support sees "this is a known issue")
- Better tracking of recurring problems
- Supports future auto-escalation workflows

### Success Metrics

- **Suggestion accuracy**: 70%+ of suggestions accepted by support
- **Linking rate increase**: +20% conversations linked to stories
- **Latency**: <500ms for similarity search
- **Coverage**: Suggestions available for 60%+ of conversations (have similar matches)

### Infrastructure Requirements

- **PostgreSQL pgvector extension** (vector similarity search)
- **OpenAI embeddings API** (~$0.02 per 1000 conversations)
- **Embedding storage**: ~6KB per conversation (1536 dimensions × 4 bytes)

**Cost Estimate**:

- 100 conversations/day × 30 days = 3000 conversations/month
- 3000 × $0.02/1000 = **$0.06/month** (embeddings)
- Storage: 3000 × 6KB = **18MB/month** (negligible)

---

## Implementation Order

### Recommended Phasing

| Phase | Enhancement                                  | Timeline    | Dependencies          |
| ----- | -------------------------------------------- | ----------- | --------------------- |
| 4a    | Enhancement 1: Help Article Context          | This sprint | None (low complexity) |
| 4b    | Enhancement 2: Coverage Gap Analysis         | Next sprint | Enhancement 1         |
| 5     | Enhancement 3: Ground Truth Validation       | Future      | Shortcut API setup    |
| 5     | Enhancement 4: Vocabulary Feedback Loop      | Future      | Enhancement 3         |
| 6+    | Enhancement 5: Theme-Based Story Suggestions | Future      | Vector DB setup       |

### Phase 4a: Help Article Context Injection (This Sprint)

**Timeline**: 1-2 days
**Success Criteria**:

- Help article URL extraction from conversations
- Intercom API integration for article metadata
- Context injection into Stage 2 prompt
- Database schema for article references
- Tests: 100% extraction rate on conversations with article URLs

**Deliverables**:

- `src/help_article_extractor.py`
- Database migration: `help_article_references` table
- Updated `src/classifier_stage2.py` (prompt enrichment)
- Tests: `tests/test_help_article_extraction.py`

### Phase 4b: Coverage Gap Analysis (Next Sprint)

**Timeline**: 2-3 days
**Success Criteria**:

- SQL queries for undocumented themes
- SQL queries for confusing articles
- Weekly report generation
- Slack/email notification integration

**Deliverables**:

- `src/analytics/doc_coverage.py`
- `scripts/generate_doc_coverage_report.py`
- Automated weekly reporting (cron or GitHub Actions)

---

## Architectural Compatibility

All enhancements are **ADDITIVE** - they don't break existing flow:

### Current Two-Stage Pipeline

```
1. Fetch conversations (quality filtering)
2. Extract source.url (URL context)
3. Stage 1: Fast routing
4. Stage 2: Theme extraction with vocabulary
5. Store themes in DB
```

### Enhanced Pipeline (Phase 4a)

```
1. Fetch conversations (quality filtering)
2. Extract source.url (URL context)
2a. Extract help article URLs ← NEW (Enhancement 1)
2b. Fetch article metadata ← NEW (Enhancement 1)
3. Stage 1: Fast routing
4. Stage 2: Theme extraction with vocabulary + article context ← ENHANCED
5. Store themes + article references in DB ← ENHANCED
```

### Validation & Feedback Loops (Phase 5)

```
Production Pipeline (above)
    ↓
Stored Data (conversations, themes, article refs)
    ↓
┌─────────────────────────────────────┐
│  Validation Pipeline (separate)    │
│  - Ground Truth Validation (E3)    │
│  - Vocabulary Feedback Loop (E4)   │
└─────────────────────────────────────┘
    ↓
Vocabulary Updates → Feeds back into Production Pipeline
```

**Key Point**: Enhancement 1 is the only one that modifies the critical path, but it's **optional context enrichment** like URL boosting - pipeline doesn't break if article extraction fails.

---

## Success Metrics Summary

| Enhancement                | Key Metric                                        | Target                                 |
| -------------------------- | ------------------------------------------------- | -------------------------------------- |
| 1. Help Article Context    | Accuracy improvement on article-referenced convos | +10-15%                                |
| 2. Coverage Gap Analysis   | Undocumented themes identified per month          | 5-10 themes                            |
| 3. Ground Truth Validation | Accuracy vs. Shortcut labels                      | Establish baseline, track improvements |
| 4. Vocabulary Feedback     | New themes added per month                        | 3-5 themes (initially)                 |
| 5. Story Suggestions       | Suggestion acceptance rate                        | 70%+                                   |

---

## Open Questions

| Question                                        | Status  | Resolution Needed                      |
| ----------------------------------------------- | ------- | -------------------------------------- |
| How to access Intercom Help Center API?         | Pending | Verify API endpoint and authentication |
| Shortcut API rate limits?                       | Pending | Check limits for story fetching        |
| pgvector extension available on our PostgreSQL? | Pending | Confirm for Enhancement 5              |
| Who reviews vocabulary expansion suggestions?   | Pending | Identify product/support stakeholder   |

---

## Related Documents

- `PLAN.md` - Overall project plan (add Phase 4a/4b/5 sections)
- `docs/architecture.md` - System architecture (update with new components)
- `docs/status.md` - Current status (update with Phase 4a progress)
- GitHub Issues - Create issues for each enhancement

---

## Revision History

| Date       | Author        | Change                  |
| ---------- | ------------- | ----------------------- |
| 2026-01-07 | Claude + User | Initial design document |
