# Two-Stage Classification System

**Complete integrated system combining:**

1. Two-stage classification (real-time + accurate)
2. Resolution analysis (support action signals)
3. Support knowledge base (continuous learning)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    INCOMING CONVERSATION                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │   STAGE 1: QUICK ROUTING      │
         │  (Customer Message Only)       │
         │                                │
         │  - Fast (<1s)                  │
         │  - Lower confidence            │
         │  - Good enough for routing     │
         └────────────┬──────────────────┘
                      │
                      ▼
         ┌───────────────────────────────┐
         │    ROUTE TO SUPPORT TEAM      │
         │   Auto-response if applicable  │
         └────────────┬──────────────────┘
                      │
                      ▼
         ┌───────────────────────────────┐
         │    SUPPORT TEAM RESPONDS      │
         └────────────┬──────────────────┘
                      │
                      ▼
         ┌───────────────────────────────┐
         │  STAGE 2: REFINED ANALYSIS    │
         │   (Full Conversation Context)  │
         │                                │
         │  - Customer + Support messages │
         │  - Resolution analysis         │
         │  - Support knowledge extraction│
         │  - High accuracy (100%)        │
         └────────────┬──────────────────┘
                      │
          ┌───────────┴────────────┐
          │                        │
          ▼                        ▼
┌──────────────────┐    ┌──────────────────────┐
│  UPDATE          │    │  KNOWLEDGE BASE      │
│  CLASSIFICATION  │    │  EXTRACTION          │
│                  │    │                      │
│  - Correct type  │    │  - Root causes       │
│  - Confidence    │    │  - Solutions         │
│  - Escalation    │    │  - Theme relations   │
│  - Analytics     │    │  - Terminology       │
└──────────────────┘    └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │  CONTINUOUS LEARNING │
                        │                      │
                        │  - Vocabulary update │
                        │  - Theme enrichment  │
                        │  - Pattern detection │
                        └──────────────────────┘
```

---

## Stage 1: Quick Routing

### Purpose

Provide immediate classification for routing and auto-responses.

### Input

- Customer's initial message
- Conversation metadata (source_type, source_url)

### Processing

- Fast LLM classification (gpt-4o-mini, <1s)
- URL context matching
- Vocabulary keyword matching

### Output

```python
{
  "conversation_type": "billing_question",
  "confidence": "medium",  # Expected: medium-high for Stage 1
  "routing_priority": "normal",
  "auto_response_eligible": false,
  "stage": 1
}
```

### Use Cases

- Route to correct support team
- Priority queue assignment
- Auto-response triggers
- Immediate escalation (high urgency)

---

## Stage 2: Refined Analysis

### Purpose

High-accuracy classification with support context for analytics and learning.

### Input

- Customer message
- Support response(s)
- Resolution actions
- Full conversation history

### Processing

1. **Full-context classification**
   - Customer + support messages
   - 100% high confidence target

2. **Resolution analysis**
   - Parse support actions (refund, docs, ticket, etc.)
   - Use as classification signal

3. **Knowledge extraction**
   - Root causes
   - Solutions provided
   - Product/feature mentions
   - Theme relationships

### Output

```python
{
  "conversation_type": "billing_question",  # May differ from Stage 1
  "confidence": "high",  # Expected: high for Stage 2
  "changed_from_stage_1": true,
  "resolution_signal": "refund_processed",
  "support_knowledge": {
    "root_cause": "Payment method expired",
    "solution_provided": "Processed refund, updated card",
    "products_mentioned": ["Tailwind", "Pro plan"],
    "features_mentioned": ["billing settings", "payment method"]
  },
  "related_themes": ["billing_payment_failure", "billing_settings_guidance"],
  "stage": 2
}
```

### Use Cases

- Update analytics with accurate data
- Trigger escalation rules (if needed)
- Feed vocabulary improvements
- Track support quality
- Identify self-service gaps

---

## Resolution Analysis

### Detected Patterns

**Support Actions:**

```python
RESOLUTION_PATTERNS = {
    # Billing
    "refund_processed": "billing_question",
    "payment_updated": "billing_question",
    "subscription_cancelled": "billing_question",
    "plan_changed": "billing_question",

    # Account
    "password_reset": "account_issue",
    "session_cleared": "account_issue",
    "account_unlocked": "account_issue",
    "oauth_reconnected": "account_issue",

    # Product Issues
    "ticket_created": "product_issue",
    "bug_confirmed": "product_issue",
    "escalated_to_engineering": "product_issue",

    # How-To
    "docs_link_sent": "how_to_question",
    "tutorial_provided": "how_to_question",
    "walkthrough_given": "how_to_question",

    # Feature Requests
    "feature_not_available": "feature_request",
    "roadmap_mentioned": "feature_request",
    "enhancement_logged": "feature_request",

    # Configuration
    "settings_adjusted": "configuration_help",
    "integration_configured": "configuration_help",
    "account_setup_completed": "configuration_help"
}
```

### Detection Method

Parse support messages for action keywords:

- "I've processed your refund" → `refund_processed`
- "I've created a ticket for engineering" → `ticket_created`
- "Here's the help doc: [link]" → `docs_link_sent`
- "I've reset your password" → `password_reset`

---

## Support Knowledge Base

### Schema

```python
{
  "theme_id": "billing_payment_failure",

  # Extracted from support responses
  "root_causes": [
    {
      "description": "Payment method expired",
      "frequency": 15,
      "first_seen": "2026-01-01",
      "last_seen": "2026-01-07"
    },
    {
      "description": "Card declined by bank",
      "frequency": 8,
      "first_seen": "2025-12-15",
      "last_seen": "2026-01-05"
    }
  ],

  "solutions": [
    {
      "description": "Update payment method in settings",
      "frequency": 20,
      "success_rate": 0.95,
      "avg_resolution_time_minutes": 5
    },
    {
      "description": "Process refund and retry",
      "frequency": 3,
      "success_rate": 1.0,
      "avg_resolution_time_minutes": 15
    }
  ],

  "related_themes": [
    {
      "theme_id": "billing_settings_guidance",
      "relationship": "often_co_occurs",
      "frequency": 12
    },
    {
      "theme_id": "billing_unexpected_charge",
      "relationship": "similar_root_cause",
      "frequency": 5
    }
  ],

  "terminology": {
    "support_terms": ["payment method", "card on file", "billing settings"],
    "customer_terms": ["payment failed", "card declined", "can't pay"]
  },

  "product_mentions": {
    "Pro plan": 15,
    "Advanced plan": 3,
    "billing settings": 18
  },

  "self_service_gap": {
    "detected": true,
    "evidence": "Support manually updates payment method 20 times",
    "recommendation": "Add self-service payment method update flow"
  }
}
```

### Extraction Pipeline

**Per Conversation:**

1. Extract root cause from support response
2. Extract solution provided
3. Extract product/feature mentions
4. Extract terminology (support vs customer language)
5. Detect resolution action

**Aggregation:**

1. Group by theme
2. Track frequencies
3. Identify patterns
4. Detect related themes (co-occurrence)
5. Flag self-service gaps

**Continuous Learning:**

1. Update theme descriptions with common root causes
2. Add keywords from customer terminology
3. Create new themes when pattern emerges (frequency threshold)
4. Merge duplicate themes (similar root causes + solutions)
5. Deprecate themes (frequency drops to zero)

---

## Data Flow

### Conversation Processing

```python
# Stage 1: Immediate
conversation = fetch_new_conversation()
stage1_result = classify_stage1(conversation.customer_message)
route_to_team(stage1_result.conversation_type)
send_auto_response_if_eligible(stage1_result)

# ... support responds ...

# Stage 2: Post-Response
support_responded = detect_support_response(conversation)
if support_responded:
    # Full analysis
    stage2_result = classify_stage2(
        conversation.customer_message,
        conversation.support_responses
    )

    # Resolution analysis
    resolution = analyze_resolution(conversation.support_responses)
    stage2_result.resolution_signal = resolution

    # Knowledge extraction
    knowledge = extract_support_knowledge(
        conversation,
        stage2_result.conversation_type
    )

    # Update classification if changed
    if stage2_result.conversation_type != stage1_result.conversation_type:
        update_classification(conversation.id, stage2_result)

    # Store knowledge
    store_knowledge(knowledge)

    # Trigger escalation if needed
    if should_escalate(stage2_result):
        create_escalation(conversation, stage2_result)
```

### Knowledge Base Updates

```python
# Nightly batch process
def update_knowledge_base():
    # 1. Aggregate knowledge from all Stage 2 classifications
    knowledge = aggregate_knowledge_by_theme()

    # 2. Detect new patterns
    new_patterns = detect_emerging_patterns(knowledge)

    # 3. Update vocabulary
    for pattern in new_patterns:
        if pattern.frequency > THRESHOLD:
            create_or_update_theme(pattern)

    # 4. Identify related themes
    relationships = find_theme_relationships(knowledge)
    update_theme_relationships(relationships)

    # 5. Flag self-service gaps
    gaps = detect_self_service_gaps(knowledge)
    create_gap_reports(gaps)

    # 6. Update theme descriptions with root causes
    enrich_theme_descriptions(knowledge)
```

---

## Implementation Plan

### Phase 1: Two-Stage Classification (Foundation)

**Files to create:**

1. `src/classifier_stage1.py` - Fast customer-only classifier
2. `src/classifier_stage2.py` - Full-context classifier
3. `src/classification_manager.py` - Orchestrates both stages

**Database schema:**

```sql
-- Track both stages
ALTER TABLE conversations ADD COLUMN stage1_type VARCHAR(50);
ALTER TABLE conversations ADD COLUMN stage1_confidence VARCHAR(20);
ALTER TABLE conversations ADD COLUMN stage2_type VARCHAR(50);
ALTER TABLE conversations ADD COLUMN stage2_confidence VARCHAR(20);
ALTER TABLE conversations ADD COLUMN classification_changed BOOLEAN;
```

### Phase 2: Resolution Analysis (Enhancement)

**Files to create:**

1. `src/resolution_analyzer.py` - Detect support actions
2. `config/resolution_patterns.json` - Resolution pattern definitions

**Integration:**

- Add resolution detection to Stage 2
- Use as additional classification signal
- Track resolution accuracy

### Phase 3: Knowledge Base (Continuous Learning)

**Files to create:**

1. `src/knowledge_extractor.py` - Extract knowledge from conversations
2. `src/knowledge_aggregator.py` - Aggregate and pattern detection
3. `src/vocabulary_updater.py` - Feed back to vocabulary
4. `db/knowledge_schema.sql` - Knowledge base schema

**Database schema:**

```sql
CREATE TABLE theme_knowledge (
    theme_id VARCHAR(100) PRIMARY KEY,
    root_causes JSONB,
    solutions JSONB,
    related_themes JSONB,
    terminology JSONB,
    product_mentions JSONB,
    self_service_gap JSONB,
    updated_at TIMESTAMP
);

CREATE TABLE theme_relationships (
    theme_a VARCHAR(100),
    theme_b VARCHAR(100),
    relationship_type VARCHAR(50),
    frequency INTEGER,
    PRIMARY KEY (theme_a, theme_b)
);
```

---

## Success Metrics

### Stage 1 (Routing)

- **Speed**: <1 second average
- **Routing accuracy**: >80% (good enough for routing)
- **Confidence**: Medium-High acceptable

### Stage 2 (Analytics)

- **Accuracy**: >95% (with support context)
- **Confidence**: High (100% target)
- **Disambiguation**: >60% high/medium

### Resolution Analysis

- **Detection rate**: >70% of support responses have detectable action
- **Signal strength**: Resolution analysis agrees with classification >85%

### Knowledge Base

- **Coverage**: >50% of themes have root causes documented
- **Freshness**: Updated within 24 hours
- **Self-service gap detection**: Identify 5+ gaps per month

---

## Example End-to-End Flow

### T=0: Conversation Starts

**Customer message:**

> "I need help with my account"

**Stage 1 Classification:**

```json
{
  "conversation_type": "account_issue",
  "confidence": "medium",
  "reasoning": "Customer mentioned 'account' but unclear what issue",
  "routing": "account_support_team"
}
```

**Action:** Route to account support team

---

### T+5min: Support Responds

**Support message:**

> "I'm sorry you're looking to cancel your subscription. I can definitely help with that. Could you share why you're looking to cancel today?"

**Stage 2 Classification:**

```json
{
  "conversation_type": "billing_question",
  "confidence": "high",
  "changed_from_stage_1": true,
  "reasoning": "Support immediately addressed cancellation = billing issue",
  "resolution_signal": "cancellation_discussed",
  "support_knowledge": {
    "root_cause": null,
    "solution_provided": "Offered to assist with cancellation",
    "products_mentioned": ["subscription"],
    "features_mentioned": ["cancellation"]
  }
}
```

**Actions:**

1. Update conversation classification: `account_issue` → `billing_question`
2. Update analytics
3. Extract knowledge: "cancellation" is billing-related
4. Flag potential self-service gap (support manually processing cancellations)

---

### T+15min: Resolution

**Support message:**

> "I've gone ahead and initialized that cancellation for you. You won't be charged again and your account will revert to our free plan. Thanks for letting us know!"

**Resolution Analysis:**

```json
{
  "resolution_action": "subscription_cancelled",
  "confirms_type": "billing_question",
  "solution": "Subscription cancelled, reverted to free plan"
}
```

**Knowledge Extracted:**

```json
{
  "theme": "billing_cancellation_request",
  "root_cause": "Customer wanted to cancel",
  "solution": "Support cancelled subscription",
  "self_service_gap": true,
  "gap_evidence": "Support manually cancelled instead of self-service"
}
```

---

## Files Structure

```
src/
  classifier_stage1.py          # Fast customer-only classifier
  classifier_stage2.py          # Full-context classifier
  classification_manager.py     # Orchestrates both stages
  resolution_analyzer.py        # Detects support actions
  knowledge_extractor.py        # Extracts knowledge per conversation
  knowledge_aggregator.py       # Aggregates knowledge across conversations
  vocabulary_updater.py         # Feeds knowledge back to vocabulary

config/
  resolution_patterns.json      # Resolution pattern definitions

db/
  knowledge_schema.sql          # Knowledge base database schema

docs/
  two-stage-classification-system.md  # This file
```

---

## Next Steps

1. ✅ Design architecture (this doc)
2. ⏳ Build Stage 1 classifier
3. ⏳ Build Stage 2 classifier
4. ⏳ Build resolution analyzer
5. ⏳ Build knowledge extraction pipeline
6. ⏳ Test on 75 conversations
7. ⏳ Deploy to production
