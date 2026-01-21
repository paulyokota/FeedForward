# Architecture Decision: Integration of ResolutionAnalyzer and KnowledgeExtractor

**Date**: 2025-01-21
**Author**: Priya (Architecture)
**Status**: DESIGN COMPLETE
**Context**: User chose INTEGRATE over DELETE from milestone-5-pr3-architecture.md

---

## Overview

This document designs how to wire `ResolutionAnalyzer` and `KnowledgeExtractor` into `two_stage_pipeline.py` while preserving async performance and enabling incremental rollout.

---

## Current State Analysis

### Existing Pipeline Flow

```
two_stage_pipeline.py
    |
    +--> extract_support_messages()     # Extract support messages from raw conv
    |
    +--> detect_resolution_signal()     # Simple 6-phrase detection (lines 71-97)
    |         |
    |         +--> Returns: {"action": "resolved", "signal": phrase} or None
    |
    +--> classify_stage1_async()        # Fast routing classification
    |
    +--> classify_stage2_async()        # Refined analysis (uses resolution_action)
    |
    +--> store_classification_results_batch()  # Batch DB insert
```

### ResolutionAnalyzer Capabilities

Located at: `/Users/paulyokota/Documents/GitHub/FeedForward/src/resolution_analyzer.py`

```python
# Input: List of support messages
# Output:
{
    "primary_action": {
        "action": "refund_processed",        # Specific action detected
        "category": "billing",               # Category (billing, account, etc.)
        "conversation_type": "billing_question",  # Suggested type
        "action_category": "billing_resolution",   # Action type
        "matched_keyword": "processed your refund"  # What triggered match
    },
    "all_actions": [...],                    # All detected actions
    "action_count": int,                     # Number of actions
    "categories": ["billing", "account"],    # Unique categories
    "suggested_type": "billing_question"     # From primary action
}
```

**Pattern Coverage**: 20+ patterns across 6 categories:

- billing (refund, payment update, subscription cancel, plan change)
- account (password reset, session cleared, account unlocked, oauth reconnect)
- product_issue (ticket created, bug confirmed, escalated)
- how_to (docs link, tutorial, walkthrough)
- feature_request (not available, roadmap, enhancement logged)
- configuration (settings adjusted, integration configured, setup completed)

### KnowledgeExtractor Capabilities

Located at: `/Users/paulyokota/Documents/GitHub/FeedForward/src/knowledge_extractor.py`

```python
# Input: customer_message, support_messages, conversation_type
# Output:
{
    "conversation_type": str,
    "root_cause": str | None,              # "this is due to a downtime"
    "solution_provided": str | None,        # "I've processed your refund"
    "product_mentions": ["Tailwind", "Pro plan"],
    "feature_mentions": ["drafts", "queue"],
    "customer_terminology": [...],          # Phrases customer used
    "support_terminology": [...],           # Phrases support used
    "self_service_gap": bool,               # Could this be automated?
    "gap_evidence": str | None              # "Support manually cancelled"
}
```

### Database Schema (Current)

From migration `001_add_two_stage_classification.sql`:

```sql
-- Already exists:
resolution_action VARCHAR(100),     -- Used: stores simple action
resolution_detected BOOLEAN,        -- Used: TRUE if detected
support_insights JSONB              -- Unused: designed for this purpose
```

---

## Design Decisions

### 1. Where to Call These Modules?

**Decision**: Call in Stage 2 processing, immediately after support messages are available.

**Rationale**:

- Stage 1 has no support context - these modules need support messages
- Call BEFORE Stage 2 LLM so resolution analysis can inform Stage 2
- Run in parallel with Stage 2 where possible (resolution analysis is fast)

**Integration Point** (in `classify_conversation_async`):

```
if support_messages:
    # NEW: Rich resolution analysis (fast, pattern-based)
    resolution_analysis = resolution_analyzer.analyze_conversation(support_messages)

    # EXISTING: Stage 2 LLM classification (slow, needs semaphore)
    stage2_result = await classify_stage2_async(
        resolution_signal=resolution_analysis["suggested_type"],  # Enhanced signal
        ...
    )

    # NEW: Knowledge extraction (fast, pattern-based)
    knowledge = knowledge_extractor.extract_from_conversation(
        customer_message,
        support_messages,
        stage2_result["conversation_type"]
    )
```

### 2. How to Store the Outputs?

**Decision**: Use existing `support_insights JSONB` column for both modules.

**Schema Design**:

```json
{
  "resolution_analysis": {
    "primary_action": "refund_processed",
    "action_category": "billing_resolution",
    "all_actions": ["refund_processed", "plan_changed"],
    "categories": ["billing"],
    "suggested_type": "billing_question",
    "matched_keywords": ["processed your refund"]
  },
  "knowledge": {
    "root_cause": "This is due to a known billing sync issue",
    "solution_provided": "I've processed your refund",
    "product_mentions": ["Pro plan"],
    "feature_mentions": ["billing", "subscription"],
    "self_service_gap": true,
    "gap_evidence": "Support manually cancelled"
  }
}
```

**Why JSONB in existing column**:

- No schema migration required
- `support_insights` was designed for exactly this purpose (see migration comment)
- Flexible structure allows iterative refinement
- Queryable via PostgreSQL JSON operators when needed

### 3. Replace or Augment `detect_resolution_signal()`?

**Decision**: REPLACE with `ResolutionAnalyzer`, but add backward-compatible wrapper.

**Rationale**:

- `detect_resolution_signal()` is a subset of `ResolutionAnalyzer`
- Same 6 phrases plus 14 more patterns
- Same output format can be maintained for Stage 2 LLM
- Rich data stored separately in `support_insights`

**Backward Compatibility**:

```python
def detect_resolution_signal(support_messages: List[str]) -> Optional[Dict[str, Any]]:
    """
    Detect resolution patterns. Uses ResolutionAnalyzer internally.

    Returns simple format for backward compatibility with Stage 2 prompt.
    Rich analysis stored in support_insights during pipeline run.
    """
    analyzer = ResolutionAnalyzer()
    analysis = analyzer.analyze_conversation(support_messages)

    if analysis["primary_action"]:
        # Return simple format for Stage 2 LLM
        return {
            "action": analysis["primary_action"]["action"],
            "signal": analysis["primary_action"]["matched_keyword"]
        }
    return None
```

### 4. Minimal vs Full Integration

**Phase 1 (Minimal - This PR)**:

- Replace `detect_resolution_signal()` with `ResolutionAnalyzer` wrapper
- Store full analysis in `support_insights`
- Add `KnowledgeExtractor` after Stage 2
- Store knowledge in `support_insights`
- No LLM changes, no new migrations

**Phase 2 (Future - Separate PR)**:

- Enhance Stage 2 prompt with resolution categories
- Confidence boost from resolution agreement
- Self-service gap reporting/alerting
- Terminology feedback to vocabulary

---

## Implementation Plan

### File Changes

| File                               | Change                                                         | Owner  |
| ---------------------------------- | -------------------------------------------------------------- | ------ |
| `src/two_stage_pipeline.py`        | Replace `detect_resolution_signal()`, add knowledge extraction | Marcus |
| `src/resolution_analyzer.py`       | No changes (already complete)                                  | -      |
| `src/knowledge_extractor.py`       | No changes (already complete)                                  | -      |
| `src/db/classification_storage.py` | Update to store `support_insights`                             | Marcus |

### Code Changes

#### 1. Update `two_stage_pipeline.py`

```python
# At top of file
from resolution_analyzer import ResolutionAnalyzer
from knowledge_extractor import KnowledgeExtractor

# Module-level instances (initialized once)
_resolution_analyzer = None
_knowledge_extractor = None

def get_resolution_analyzer() -> ResolutionAnalyzer:
    global _resolution_analyzer
    if _resolution_analyzer is None:
        _resolution_analyzer = ResolutionAnalyzer()
    return _resolution_analyzer

def get_knowledge_extractor() -> KnowledgeExtractor:
    global _knowledge_extractor
    if _knowledge_extractor is None:
        _knowledge_extractor = KnowledgeExtractor()
    return _knowledge_extractor


def detect_resolution_signal(support_messages: List[str]) -> Optional[Dict[str, Any]]:
    """
    Detect resolution patterns using ResolutionAnalyzer.

    Returns simple format for backward compatibility with Stage 2 prompt.
    Full analysis available via get_full_resolution_analysis().
    """
    if not support_messages:
        return None

    analyzer = get_resolution_analyzer()
    analysis = analyzer.analyze_conversation(support_messages)

    if analysis["primary_action"]:
        return {
            "action": analysis["primary_action"]["action"],
            "signal": analysis["primary_action"]["matched_keyword"]
        }
    return None


def get_full_resolution_analysis(support_messages: List[str]) -> Dict[str, Any]:
    """Get full resolution analysis for storage in support_insights."""
    if not support_messages:
        return {}

    analyzer = get_resolution_analyzer()
    analysis = analyzer.analyze_conversation(support_messages)

    return {
        "primary_action": analysis["primary_action"]["action"] if analysis["primary_action"] else None,
        "action_category": analysis["primary_action"]["action_category"] if analysis["primary_action"] else None,
        "all_actions": [a["action"] for a in analysis["all_actions"]],
        "categories": analysis["categories"],
        "suggested_type": analysis["suggested_type"],
        "matched_keywords": [a["matched_keyword"] for a in analysis["all_actions"]]
    }


def extract_knowledge(
    customer_message: str,
    support_messages: List[str],
    conversation_type: str
) -> Dict[str, Any]:
    """Extract knowledge for storage in support_insights."""
    if not support_messages:
        return {}

    extractor = get_knowledge_extractor()
    knowledge = extractor.extract_from_conversation(
        customer_message,
        support_messages,
        conversation_type
    )

    # Return subset of fields for storage (exclude verbose terminology)
    return {
        "root_cause": knowledge["root_cause"],
        "solution_provided": knowledge["solution_provided"],
        "product_mentions": knowledge["product_mentions"],
        "feature_mentions": knowledge["feature_mentions"],
        "self_service_gap": knowledge["self_service_gap"],
        "gap_evidence": knowledge["gap_evidence"]
    }
```

#### 2. Update `classify_conversation_async()`

```python
async def classify_conversation_async(
    parsed: IntercomConversation,
    raw_conversation: dict,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """
    Run two-stage classification with resolution analysis and knowledge extraction.
    """
    support_messages = extract_support_messages(raw_conversation)

    # Stage 1
    stage1_result = await classify_stage1_async(
        customer_message=parsed.source_body,
        source_type=parsed.source_type,
        source_url=parsed.source_url,
        semaphore=semaphore,
    )

    # Stage 2 + Resolution + Knowledge (only if support responded)
    stage2_result = None
    resolution_signal = None
    support_insights = None  # NEW

    if support_messages:
        # Resolution analysis (fast, no semaphore needed)
        resolution_signal = detect_resolution_signal(support_messages)
        resolution_action = resolution_signal.get("action") if resolution_signal else None

        # Stage 2 LLM (slow, needs semaphore)
        stage2_result = await classify_stage2_async(
            customer_message=parsed.source_body,
            support_messages=support_messages,
            stage1_type=stage1_result["conversation_type"],
            resolution_signal=resolution_action,
            source_url=parsed.source_url,
            semaphore=semaphore,
        )

        # Build support_insights (NEW)
        final_type = stage2_result.get("conversation_type", stage1_result["conversation_type"])
        support_insights = {
            "resolution_analysis": get_full_resolution_analysis(support_messages),
            "knowledge": extract_knowledge(
                parsed.source_body,
                support_messages,
                final_type
            )
        }

    return {
        "conversation_id": parsed.id,
        "created_at": parsed.created_at,
        "source_body": parsed.source_body,
        "source_type": parsed.source_type,
        "source_url": parsed.source_url,
        "contact_email": parsed.contact_email,
        "contact_id": parsed.contact_id,
        "stage1_result": stage1_result,
        "stage2_result": stage2_result,
        "support_messages": support_messages,
        "resolution_signal": resolution_signal,
        "support_insights": support_insights,  # NEW
    }
```

#### 3. Update `store_classification_results_batch()`

In `src/db/classification_storage.py`, ensure `support_insights` is included in the batch insert:

```python
# In the INSERT statement, add support_insights column
# In the values tuple, add:
Json(result.get("support_insights")) if result.get("support_insights") else None
```

---

## Performance Considerations

### Async Performance Preserved

| Operation            | Current              | After Integration | Impact     |
| -------------------- | -------------------- | ----------------- | ---------- |
| Stage 1 LLM          | async with semaphore | unchanged         | none       |
| Stage 2 LLM          | async with semaphore | unchanged         | none       |
| Resolution analysis  | N/A                  | sync, ~1ms        | negligible |
| Knowledge extraction | N/A                  | sync, ~1ms        | negligible |
| DB batch insert      | unchanged            | +1 JSON column    | negligible |

**Total impact**: <1ms per conversation, well within noise margin.

### Memory Considerations

- `ResolutionAnalyzer` loads `resolution_patterns.json` once (~5KB)
- `KnowledgeExtractor` has no external data
- Both are stateless pattern matchers - safe for concurrent use

---

## Incremental Rollout

### Feature Flag Approach (Optional)

```python
ENABLE_RICH_RESOLUTION = os.getenv("ENABLE_RICH_RESOLUTION", "true").lower() == "true"
ENABLE_KNOWLEDGE_EXTRACTION = os.getenv("ENABLE_KNOWLEDGE_EXTRACTION", "true").lower() == "true"

if support_messages:
    if ENABLE_RICH_RESOLUTION:
        resolution_signal = detect_resolution_signal(support_messages)  # Uses ResolutionAnalyzer
    else:
        resolution_signal = detect_resolution_signal_simple(support_messages)  # Old 6-phrase version

    if ENABLE_KNOWLEDGE_EXTRACTION:
        knowledge = extract_knowledge(...)
```

**Recommendation**: Skip feature flags for Phase 1. The integration is low-risk (pattern matching, not LLM) and the old code path is trivial to restore if needed.

---

## Testing Strategy

### Unit Tests

1. **ResolutionAnalyzer wrapper**
   - Verify backward-compatible output format
   - Verify full analysis contains expected fields

2. **KnowledgeExtractor wrapper**
   - Verify subset of fields returned
   - Verify None handling for empty support messages

### Integration Tests

1. **Pipeline end-to-end**
   - Run pipeline on test conversation with support messages
   - Verify `support_insights` populated in DB
   - Verify classification unchanged (same accuracy)

2. **Performance**
   - Run async pipeline on 100 conversations
   - Verify throughput unchanged (>5 conv/sec)

---

## Acceptance Criteria

- [ ] `detect_resolution_signal()` uses `ResolutionAnalyzer` internally
- [ ] `support_insights` column populated with resolution analysis
- [ ] `support_insights` column populated with knowledge extraction
- [ ] Existing tests pass (no regression)
- [ ] Async throughput unchanged (>5 conv/sec on 100 conversations)
- [ ] No new database migrations required

---

## Agent Assignments

### Marcus (Backend)

**Owns**:

- `src/two_stage_pipeline.py` (integration changes)
- `src/db/classification_storage.py` (support_insights storage)

**Creates**:

- Helper functions: `get_full_resolution_analysis()`, `extract_knowledge()`

**Does not touch**:

- `src/resolution_analyzer.py` (already complete)
- `src/knowledge_extractor.py` (already complete)

**Acceptance**:

- Pipeline stores `support_insights` for conversations with support messages
- Backward compatibility: Stage 2 receives same resolution signal format
- Tests pass, throughput unchanged

### Kenji (Testing)

**Creates**:

- Unit tests for new helper functions
- Integration test for `support_insights` storage

**Acceptance**:

- 100% coverage on new code paths
- Performance test confirms no degradation

---

## Alternatives Considered

### A. Separate Database Columns

```sql
ADD COLUMN resolution_analysis JSONB;
ADD COLUMN knowledge_extraction JSONB;
```

**Rejected**: Requires migration, `support_insights` already exists for this purpose.

### B. Call in Stage 1

**Rejected**: Stage 1 has no support messages. Resolution analysis requires support context.

### C. Run in Parallel with Stage 2 LLM

```python
resolution_task = asyncio.create_task(run_resolution_analysis(...))
stage2_task = asyncio.create_task(classify_stage2_async(...))
resolution, stage2 = await asyncio.gather(resolution_task, stage2_task)
```

**Rejected**: Over-engineering. Resolution analysis is <1ms, not worth the complexity. Knowledge extraction depends on Stage 2 result anyway.

### D. Feature Flags

**Deferred**: Not needed for Phase 1 given low risk. Can add later if issues emerge.

---

## References

- Previous decision: `.claude/decisions/milestone-5-pr3-architecture.md`
- ResolutionAnalyzer: `src/resolution_analyzer.py`
- KnowledgeExtractor: `src/knowledge_extractor.py`
- Pattern config: `config/resolution_patterns.json`
- Migration: `src/db/migrations/001_add_two_stage_classification.sql`
