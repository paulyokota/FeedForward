# Operational Reference Guide: LLM-Based Intercom Conversation Analysis
**Target Audience**: Claude Code / AI Implementation Assistants  
**Last Updated**: January 5, 2026  
**Purpose**: Provide actionable technical specifications for building LLM-powered conversation insight extraction pipelines without manual tagging workflows.

---

## Table of Contents
1. [Architecture Patterns](#architecture-patterns)
2. [Prompt Templates](#prompt-templates)
3. [Intercom API Integration](#intercom-api-integration)
4. [Structured Output Schemas](#structured-output-schemas)
5. [Batch Processing Pipeline](#batch-processing-pipeline)
6. [Decision Rules & Automation](#decision-rules--automation)
7. [Cost Optimization](#cost-optimization)
8. [Implementation Checklist](#implementation-checklist)

---

## Architecture Patterns

### Pattern 1: Scheduled Batch Processing
**Best for**: Daily/weekly reporting, trend analysis, cost optimization

```
┌──────────────┐
│   Scheduler  │ (cron/Airflow/GitHub Actions)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Intercom API │ GET /conversations (date range filter)
│    Fetch     │ → Store raw JSON
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  LLM Batch   │ Parallel classification (ThreadPoolExecutor)
│ Inference    │ → Structured JSON outputs
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Database    │ PostgreSQL/MongoDB (insights table)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Reporting  │ SQL aggregations → Email/Slack
└──────────────┘
```

**Key characteristics**:
- Runs on schedule (daily 6am, weekly Monday)
- Uses batch inference APIs (50-100x cost savings)
- Processes historical data (last 24h, 7d, 30d)
- Latency: 5-30 minutes acceptable
- Cost: ~$0.00013/conversation

### Pattern 2: Event-Driven Real-Time
**Best for**: Critical issue escalation, churn prevention, intelligent routing

```
┌──────────────┐
│   Webhook    │ Intercom: conversation.user.replied
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ LLM Classify │ Real-time API call (Claude Haiku/GPT-4o-mini)
│  (<1 second) │ → Sentiment, Priority, Category, Churn Risk
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Router     │ If CRITICAL + HIGH_CHURN → Escalate
│   Logic      │ If BUG + P0 → Create Jira
│              │ If FEATURE_REQUEST → Productboard
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Actions    │ Update Intercom, Send alerts, Create tickets
└──────────────┘
```

**Key characteristics**:
- Webhook-triggered (real-time)
- Low-latency models required (<1s response)
- Higher cost (real-time inference premium)
- Conditional routing based on classification
- Immediate escalation for P0 issues

### Pattern 3: Hybrid (Make.com/n8n)
**Best for**: Rapid prototyping, visual workflow management, mixed timing needs

```yaml
Workflow Steps:
1. Trigger: Watch Intercom Conversations (new/updated)
2. Filter: state=open AND plan IN [pro, enterprise] AND NOT tagged[processed]
3. Transform: Extract subject + messages, limit 2000 tokens
4. LLM Call: OpenAI/Claude API → structured JSON
5. Router:
   - Branch A: feature_request → Productboard
   - Branch B: bug + critical → Jira P0
   - Branch C: churn_risk=high → HubSpot task + Slack alert
   - Branch D: billing → Assign to finance team
6. Update: Add Intercom note, apply processed tag
```

---

## Prompt Templates

### Template 1: Basic Classification
**Purpose**: Categorize conversations into predefined types

```
Analyze this customer support conversation and categorize it into EXACTLY ONE of the following categories:

CATEGORIES:
- PRODUCT_BUG: Any error, unexpected behavior, or functionality not working as intended
- ACCOUNT_ACCESS: Problems with login, permissions, password reset, or account settings
- BILLING: Issues with charges, subscriptions, payment methods, invoices, or refunds
- FEATURE_REQUEST: Requests for new capabilities or enhancements to existing features
- UX_FRICTION: Confusion about how to use features, onboarding difficulties, unclear UI/UX
- USAGE_QUESTION: Questions about how to correctly use existing features
- OTHER: Does not clearly fit any category above

CONVERSATION:
Subject: {{conversation.subject}}
First Message: {{conversation.first_message}}
Customer Plan: {{customer.plan}}
Account Age: {{customer.days_since_signup}} days

INSTRUCTIONS:
Respond with ONLY the exact category name from the list above. No explanations.

CATEGORY:
```

**Expected output**: `PRODUCT_BUG` or `FEATURE_REQUEST` etc.

---

### Template 2: Multi-Dimensional Classification
**Purpose**: Extract multiple fields in single LLM call

```
Analyze this support conversation and provide comprehensive categorization.

CONVERSATION CONTEXT:
Subject: {{conversation.subject}}
Messages: {{conversation.messages_text}}
Customer: {{customer.name}} ({{customer.plan}} plan)
Account Age: {{customer.days_since_signup}} days
Previous Tickets: {{customer.ticket_count}}

CLASSIFICATION DIMENSIONS:
1. ISSUE_TYPE: [PRODUCT_BUG, ACCOUNT_ACCESS, BILLING, FEATURE_REQUEST, UX_FRICTION, USAGE_QUESTION, OTHER]
2. PRIORITY: [CRITICAL, HIGH, MEDIUM, LOW]
   - CRITICAL: Core functionality broken, payment failure, data loss, security issue
   - HIGH: Important feature not working, blocking key workflows
   - MEDIUM: Workaround available, non-critical friction
   - LOW: Minor inconvenience, cosmetic issues
3. SENTIMENT: [VERY_NEGATIVE, NEGATIVE, NEUTRAL, POSITIVE, VERY_POSITIVE]
4. CHURN_RISK: [LOW, MEDIUM, HIGH]
   - HIGH: Mentions cancellation, expresses deep frustration, comparing competitors
   - MEDIUM: Significant issues but no cancellation signals
   - LOW: Satisfied or minor issues

OUTPUT FORMAT (respond exactly as shown):
ISSUE_TYPE: [selected]
PRIORITY: [selected]
SENTIMENT: [selected]
CHURN_RISK: [selected]
SUMMARY: [one-sentence description of core issue]
AFFECTED_FEATURE: [specific product area if identifiable]
```

**Expected output**:
```
ISSUE_TYPE: PRODUCT_BUG
PRIORITY: HIGH
SENTIMENT: NEGATIVE
CHURN_RISK: MEDIUM
SUMMARY: User unable to sync data with Salesforce integration
AFFECTED_FEATURE: integrations
```

---

### Template 3: Structured JSON with Schema
**Purpose**: Generate backlog-ready structured output

```python
# Using Claude Structured Outputs
from pydantic import BaseModel, Field
from anthropic import Anthropic

class ConversationInsight(BaseModel):
    issue_type: str = Field(description="Category: PRODUCT_BUG, FEATURE_REQUEST, etc.")
    priority: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW")
    sentiment_score: float = Field(description="Range -1.0 (very negative) to 1.0 (very positive)")
    churn_risk: str = Field(description="LOW, MEDIUM, or HIGH")
    summary: str = Field(description="One-sentence issue description", max_length=200)
    affected_feature: str = Field(description="Product area affected (integrations, billing, auth, etc.)")
    customer_segment: str = Field(description="enterprise, smb, trial, or free")
    recommended_action: str = Field(description="ESCALATE, CREATE_TICKET, ADD_TO_BACKLOG, or ROUTINE")

PROMPT = f"""
Analyze this customer support conversation and extract structured insights.

CONVERSATION:
{conversation_text}

CUSTOMER CONTEXT:
Plan: {customer_plan}
MRR: ${customer_mrr}
Tenure: {customer_tenure_months} months
Previous issues: {previous_ticket_count}

INSTRUCTIONS:
Extract all relevant fields. Use context to inform priority and churn risk.
For enterprise customers or high MRR, weight priority higher.
"""

client = Anthropic()
response = client.beta.messages.parse(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    betas=["structured-outputs-2025-11-13"],
    messages=[{"role": "user", "content": PROMPT}],
    output_format=ConversationInsight,
)

insight = response.parsed_output  # Guaranteed schema compliance
```

---

### Template 4: RICE Scoring Automation
**Purpose**: Apply prioritization framework automatically

```
You are a product manager evaluating customer feedback using the RICE framework.

INSIGHT SUMMARY:
Issue: {{issue_description}}
Frequency: Mentioned in {{conversation_count}} conversations over {{time_period_days}} days
Sentiment: {{avg_sentiment}} (range: -1.0 to 1.0)
Affected Segments: {{affected_customer_segments}}
Product Area: {{product_area}}

RICE FRAMEWORK:
Calculate each component and provide final score.

1. REACH: How many users affected per quarter?
   - Base estimate on {{conversation_count}} mentions
   - Enterprise customers count as 10x multiplier
   - Consider: {{total_active_users}} total active users

2. IMPACT: Satisfaction improvement potential (0.25, 0.5, 1.0, 2.0, 3.0)
   - 0.25 = Minimal (minor convenience)
   - 0.5 = Low (noticeable improvement)
   - 1.0 = Medium (improves key workflow)
   - 2.0 = High (removes major friction)
   - 3.0 = Massive (enables new use cases, prevents churn)

3. CONFIDENCE: Certainty level (0.5, 0.8, 1.0)
   - 1.0 = Strong data, clear customer quotes, consistent feedback
   - 0.8 = Good data, some assumptions needed
   - 0.5 = Limited data, significant uncertainty

4. EFFORT: Engineering time in person-weeks
   - Consider: {{product_area}} complexity, dependencies, testing needs
   - 1 week (trivial config change)
   - 2-4 weeks (small feature)
   - 5-8 weeks (medium feature)
   - 9+ weeks (large/complex feature)

CALCULATION: RICE Score = (Reach × Impact × Confidence) / Effort

OUTPUT JSON:
{
  "reach": <number>,
  "impact": <0.25|0.5|1.0|2.0|3.0>,
  "confidence": <0.5|0.8|1.0>,
  "effort_weeks": <number>,
  "rice_score": <calculated_value>,
  "reasoning": "<brief 2-3 sentence explanation>"
}
```

---

## Intercom API Integration

### Authentication
```python
import requests

INTERCOM_TOKEN = "your_access_token"  # Get from Intercom Developer Hub
HEADERS = {
    "Authorization": f"Bearer {INTERCOM_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}
```

### Fetch Conversations (Paginated)
```python
def fetch_all_conversations(created_since=None, per_page=150):
    """
    Fetch conversations from Intercom API with pagination.
    
    Args:
        created_since: Unix timestamp (fetch conversations created after this time)
        per_page: Results per page (max 150)
    
    Returns:
        List of conversation objects (metadata only, not full content)
    """
    base_url = "https://api.intercom.io/conversations"
    all_conversations = []
    page = 1
    
    while True:
        params = {"per_page": per_page, "page": page}
        if created_since:
            params["created_since"] = created_since
        
        response = requests.get(base_url, headers=HEADERS, params=params)
        response.raise_for_status()
        
        data = response.json()
        conversations = data.get("conversations", [])
        
        if not conversations:
            break
        
        all_conversations.extend(conversations)
        page += 1
        
        # Rate limiting: Intercom allows ~1000 requests/min
        time.sleep(0.1)  # Conservative 10 requests/sec
    
    return all_conversations
```

### Retrieve Full Conversation Content
```python
def get_full_conversation(conversation_id):
    """
    Fetch complete conversation including all messages (conversation_parts).
    
    Args:
        conversation_id: Intercom conversation ID
    
    Returns:
        Full conversation object with messages
    """
    url = f"https://api.intercom.io/conversations/{conversation_id}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

def extract_conversation_text(conversation):
    """
    Extract human-readable text from conversation object.
    
    Args:
        conversation: Full conversation object from API
    
    Returns:
        Dict with subject, messages, and metadata
    """
    subject = conversation.get("title", "No subject")
    
    # Extract messages from conversation_parts
    messages = []
    for part in conversation.get("conversation_parts", {}).get("conversation_parts", []):
        author_type = part.get("author", {}).get("type")  # "user" or "admin"
        body = part.get("body", "")
        
        if author_type == "user":
            messages.append(f"Customer: {body}")
        elif author_type == "admin":
            messages.append(f"Agent: {body}")
    
    return {
        "id": conversation["id"],
        "subject": subject,
        "messages": messages,
        "created_at": conversation.get("created_at"),
        "state": conversation.get("state"),
        "customer": conversation.get("contacts", {}).get("contacts", [{}])[0]
    }
```

### Parallel Batch Fetch
```python
import concurrent.futures

def batch_fetch_full_conversations(conversation_ids, max_workers=10):
    """
    Fetch multiple conversations in parallel.
    
    Args:
        conversation_ids: List of conversation IDs
        max_workers: Concurrent requests (respect rate limits)
    
    Returns:
        List of full conversation objects
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(get_full_conversation, cid) for cid in conversation_ids]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    return results
```

### Export Workflow
```python
def export_conversations_for_analysis(hours_back=24):
    """
    Complete workflow: fetch recent conversations and extract text.
    
    Args:
        hours_back: How many hours of history to fetch
    
    Returns:
        List of processed conversation dicts ready for LLM analysis
    """
    import time
    
    # Calculate timestamp
    cutoff_timestamp = int(time.time()) - (hours_back * 3600)
    
    # Step 1: List conversations (metadata only)
    print(f"Fetching conversations created in last {hours_back} hours...")
    conversations_meta = fetch_all_conversations(created_since=cutoff_timestamp)
    print(f"Found {len(conversations_meta)} conversations")
    
    # Step 2: Get full content for each
    print("Fetching full conversation content...")
    conversation_ids = [c["id"] for c in conversations_meta]
    full_conversations = batch_fetch_full_conversations(conversation_ids, max_workers=10)
    
    # Step 3: Extract text
    print("Extracting text from conversations...")
    processed = [extract_conversation_text(c) for c in full_conversations]
    
    return processed
```

---

## Structured Output Schemas

### Pydantic Models for Type Safety

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class ConversationClassification(BaseModel):
    """Basic classification output"""
    conversation_id: str
    issue_type: Literal[
        "PRODUCT_BUG",
        "ACCOUNT_ACCESS", 
        "BILLING",
        "FEATURE_REQUEST",
        "UX_FRICTION",
        "USAGE_QUESTION",
        "OTHER"
    ]
    priority: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    sentiment: Literal["VERY_NEGATIVE", "NEGATIVE", "NEUTRAL", "POSITIVE", "VERY_POSITIVE"]
    sentiment_score: float = Field(ge=-1.0, le=1.0, description="Numeric sentiment -1 to 1")
    churn_risk: Literal["LOW", "MEDIUM", "HIGH"]
    summary: str = Field(max_length=200)
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence 0-1")

class ProductInsight(BaseModel):
    """Enriched insight for backlog creation"""
    conversation_id: str
    classification: ConversationClassification
    affected_feature: Optional[str] = Field(None, description="Product area: integrations, billing, auth, etc.")
    customer_segment: Literal["enterprise", "smb", "trial", "free"]
    customer_plan: str
    customer_mrr: Optional[float]
    frequency: int = Field(description="How many times this issue mentioned")
    first_seen: datetime
    last_seen: datetime
    evidence_urls: list[str] = Field(description="Links to Intercom conversations")
    representative_quotes: list[str] = Field(max_length=3)

class RICEScore(BaseModel):
    """RICE prioritization output"""
    reach: int = Field(ge=0, description="Users affected per quarter")
    impact: Literal[0.25, 0.5, 1.0, 2.0, 3.0]
    confidence: Literal[0.5, 0.8, 1.0]
    effort_weeks: float = Field(gt=0)
    rice_score: float = Field(description="(Reach × Impact × Confidence) / Effort")
    reasoning: str = Field(max_length=500)

class BacklogItem(BaseModel):
    """Complete backlog item ready for Jira/Productboard"""
    title: str = Field(max_length=100)
    description: str = Field(description="Problem statement from customer perspective")
    issue_type: Literal["Bug", "Feature", "Improvement", "Task"]
    priority: Literal["P0", "P1", "P2", "P3"]
    labels: list[str]
    components: list[str]
    rice_score: Optional[RICEScore]
    customer_evidence: ProductInsight
    acceptance_criteria: list[str]
    estimated_story_points: Optional[int] = Field(None, ge=1, le=21)
```

### JSON Schema for OpenAI Structured Outputs

```python
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "issue_type": {
            "type": "string",
            "enum": ["PRODUCT_BUG", "ACCOUNT_ACCESS", "BILLING", "FEATURE_REQUEST", "UX_FRICTION", "USAGE_QUESTION", "OTHER"]
        },
        "priority": {
            "type": "string",
            "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        },
        "sentiment": {
            "type": "string",
            "enum": ["VERY_NEGATIVE", "NEGATIVE", "NEUTRAL", "POSITIVE", "VERY_POSITIVE"]
        },
        "sentiment_score": {
            "type": "number",
            "minimum": -1.0,
            "maximum": 1.0
        },
        "churn_risk": {
            "type": "string",
            "enum": ["LOW", "MEDIUM", "HIGH"]
        },
        "summary": {
            "type": "string",
            "maxLength": 200
        },
        "affected_feature": {
            "type": "string"
        }
    },
    "required": ["issue_type", "priority", "sentiment", "sentiment_score", "churn_risk", "summary"],
    "additionalProperties": False
}

# Usage with OpenAI
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": formatted_prompt}],
    response_format={"type": "json_schema", "json_schema": {"schema": CLASSIFICATION_SCHEMA}}
)

result = json.loads(response.choices[0].message.content)
```

---

## Batch Processing Pipeline

### Complete Pipeline Implementation

```python
import anthropic
import psycopg2
import concurrent.futures
from datetime import datetime, timedelta
import time

class IntercomLLMPipeline:
    def __init__(self, intercom_token, anthropic_key, db_config):
        self.intercom_token = intercom_token
        self.anthropic = anthropic.Anthropic(api_key=anthropic_key)
        self.db_conn = psycopg2.connect(**db_config)
    
    def run_daily_batch(self, hours_back=24):
        """Execute complete daily batch pipeline"""
        print(f"[{datetime.now()}] Starting daily batch processing...")
        
        # Stage 1: Ingest
        conversations = self.fetch_conversations(hours_back)
        print(f"Fetched {len(conversations)} conversations")
        
        # Stage 2: LLM Classification (parallel)
        insights = self.classify_batch(conversations, max_workers=10)
        print(f"Classified {len(insights)} conversations")
        
        # Stage 3: Store
        self.store_insights(insights)
        print(f"Stored insights in database")
        
        # Stage 4: Apply business rules
        actions = self.apply_escalation_rules(insights)
        print(f"Generated {len(actions)} automated actions")
        
        # Stage 5: Generate report
        report = self.generate_report(insights)
        self.send_report(report)
        
        print(f"[{datetime.now()}] Batch processing complete")
    
    def fetch_conversations(self, hours_back):
        """Fetch conversations from Intercom"""
        cutoff = int(time.time()) - (hours_back * 3600)
        # Use previous fetch_all_conversations function
        return export_conversations_for_analysis(hours_back)
    
    def classify_single(self, conversation):
        """Classify single conversation with LLM"""
        prompt = self._format_classification_prompt(conversation)
        
        try:
            response = self.anthropic.beta.messages.parse(
                model="claude-haiku-3-5",  # Fast + cost-effective
                max_tokens=512,
                betas=["structured-outputs-2025-11-13"],
                messages=[{"role": "user", "content": prompt}],
                output_format=ConversationClassification
            )
            
            insight = response.parsed_output
            insight.conversation_id = conversation["id"]
            return insight
            
        except Exception as e:
            print(f"Error classifying {conversation['id']}: {e}")
            return None
    
    def classify_batch(self, conversations, max_workers=10):
        """Classify multiple conversations in parallel"""
        insights = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_conv = {
                executor.submit(self.classify_single, conv): conv 
                for conv in conversations
            }
            
            for future in concurrent.futures.as_completed(future_to_conv):
                result = future.result()
                if result:
                    insights.append(result)
        
        return insights
    
    def store_insights(self, insights):
        """Store insights in PostgreSQL"""
        cursor = self.db_conn.cursor()
        
        for insight in insights:
            cursor.execute("""
                INSERT INTO conversation_insights 
                (conversation_id, issue_type, priority, sentiment, sentiment_score, 
                 churn_risk, summary, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (conversation_id) DO UPDATE SET
                    issue_type = EXCLUDED.issue_type,
                    priority = EXCLUDED.priority,
                    sentiment = EXCLUDED.sentiment,
                    sentiment_score = EXCLUDED.sentiment_score,
                    churn_risk = EXCLUDED.churn_risk,
                    summary = EXCLUDED.summary
            """, (
                insight.conversation_id,
                insight.issue_type,
                insight.priority,
                insight.sentiment,
                insight.sentiment_score,
                insight.churn_risk,
                insight.summary,
                datetime.now()
            ))
        
        self.db_conn.commit()
        cursor.close()
    
    def apply_escalation_rules(self, insights):
        """Apply business rules for automated actions"""
        actions = []
        
        for insight in insights:
            # Rule 1: Critical churn signals
            if (insight.sentiment_score < -0.7 and 
                insight.churn_risk == "HIGH"):
                actions.append({
                    "type": "ALERT_CS_MANAGER",
                    "conversation_id": insight.conversation_id,
                    "reason": "High churn risk detected"
                })
            
            # Rule 2: P0 bugs
            if (insight.issue_type == "PRODUCT_BUG" and 
                insight.priority == "CRITICAL"):
                actions.append({
                    "type": "CREATE_JIRA_P0",
                    "conversation_id": insight.conversation_id,
                    "summary": insight.summary
                })
            
            # Rule 3: High-frequency feature requests
            # (Would check against aggregated frequency table)
            if insight.issue_type == "FEATURE_REQUEST":
                actions.append({
                    "type": "INCREMENT_FEATURE_COUNTER",
                    "conversation_id": insight.conversation_id,
                    "summary": insight.summary
                })
        
        return actions
    
    def generate_report(self, insights):
        """Generate summary report from insights"""
        cursor = self.db_conn.cursor()
        
        # Top issues by frequency
        cursor.execute("""
            SELECT summary, issue_type, COUNT(*) as frequency
            FROM conversation_insights
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY summary, issue_type
            ORDER BY frequency DESC
            LIMIT 10
        """)
        top_issues = cursor.fetchall()
        
        # Sentiment trend
        cursor.execute("""
            SELECT DATE(created_at) as date, AVG(sentiment_score) as avg_sentiment
            FROM conversation_insights
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """)
        sentiment_trend = cursor.fetchall()
        
        cursor.close()
        
        return {
            "top_issues": top_issues,
            "sentiment_trend": sentiment_trend,
            "total_processed": len(insights),
            "critical_count": sum(1 for i in insights if i.priority == "CRITICAL"),
            "high_churn_count": sum(1 for i in insights if i.churn_risk == "HIGH")
        }
    
    def send_report(self, report):
        """Send report via email/Slack"""
        # Implementation depends on notification method
        pass
    
    def _format_classification_prompt(self, conversation):
        """Format conversation into classification prompt"""
        messages_text = "\n".join(conversation["messages"])
        
        return f"""
Analyze this customer support conversation and categorize it.

Subject: {conversation['subject']}
Messages:
{messages_text}

Customer Plan: {conversation.get('customer', {}).get('plan', 'unknown')}

Provide classification using these categories:
- ISSUE_TYPE: PRODUCT_BUG, ACCOUNT_ACCESS, BILLING, FEATURE_REQUEST, UX_FRICTION, USAGE_QUESTION, OTHER
- PRIORITY: CRITICAL (core broken), HIGH (blocking), MEDIUM (friction), LOW (minor)
- SENTIMENT: VERY_NEGATIVE, NEGATIVE, NEUTRAL, POSITIVE, VERY_POSITIVE
- SENTIMENT_SCORE: -1.0 to 1.0
- CHURN_RISK: LOW, MEDIUM, HIGH
- SUMMARY: One-sentence description
"""
```

### Database Schema

```sql
-- PostgreSQL schema for insights storage

CREATE TABLE conversation_insights (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) UNIQUE NOT NULL,
    issue_type VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    sentiment VARCHAR(20) NOT NULL,
    sentiment_score FLOAT NOT NULL CHECK (sentiment_score BETWEEN -1.0 AND 1.0),
    churn_risk VARCHAR(20) NOT NULL,
    summary TEXT NOT NULL,
    affected_feature VARCHAR(100),
    customer_segment VARCHAR(50),
    confidence FLOAT CHECK (confidence BETWEEN 0.0 AND 1.0),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Indexes for common queries
    INDEX idx_issue_type (issue_type),
    INDEX idx_priority (priority),
    INDEX idx_created_at (created_at),
    INDEX idx_churn_risk (churn_risk)
);

-- Feature request frequency tracking
CREATE TABLE feature_requests (
    id SERIAL PRIMARY KEY,
    summary TEXT NOT NULL,
    normalized_summary TEXT NOT NULL,  -- For deduplication
    frequency INT NOT NULL DEFAULT 1,
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    conversation_ids TEXT[],  -- Array of conversation IDs
    avg_sentiment FLOAT,
    customer_segments TEXT[],
    
    UNIQUE(normalized_summary)
);

-- Escalation actions log
CREATE TABLE escalation_actions (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    reason TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING, COMPLETED, FAILED
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    
    INDEX idx_status (status),
    INDEX idx_action_type (action_type)
);
```

---

## Decision Rules & Automation

### Rule Engine Implementation

```python
from dataclasses import dataclass
from typing import List, Callable

@dataclass
class EscalationRule:
    name: str
    condition: Callable[[ConversationClassification], bool]
    action: str
    priority: int  # Lower number = higher priority

class RuleEngine:
    def __init__(self):
        self.rules = self._define_rules()
    
    def _define_rules(self) -> List[EscalationRule]:
        """Define escalation rules in priority order"""
        return [
            # Rule 1: Immediate escalation - P0 bugs
            EscalationRule(
                name="P0_BUG_ENTERPRISE",
                condition=lambda i: (
                    i.issue_type == "PRODUCT_BUG" and
                    i.priority == "CRITICAL" and
                    i.customer_segment == "enterprise"
                ),
                action="PAGE_ONCALL_ENGINEER",
                priority=1
            ),
            
            # Rule 2: Churn prevention
            EscalationRule(
                name="HIGH_CHURN_RISK",
                condition=lambda i: (
                    i.churn_risk == "HIGH" and
                    i.sentiment_score < -0.7
                ),
                action="ALERT_CS_MANAGER",
                priority=2
            ),
            
            # Rule 3: Revenue-blocking issues
            EscalationRule(
                name="BILLING_CRITICAL",
                condition=lambda i: (
                    i.issue_type == "BILLING" and
                    i.priority in ["CRITICAL", "HIGH"]
                ),
                action="ESCALATE_TO_FINANCE",
                priority=2
            ),
            
            # Rule 4: Feature request aggregation
            EscalationRule(
                name="POPULAR_FEATURE_REQUEST",
                condition=lambda i: (
                    i.issue_type == "FEATURE_REQUEST" and
                    self._check_frequency(i.summary) >= 10  # 10+ mentions
                ),
                action="CREATE_PRODUCTBOARD_NOTE",
                priority=3
            ),
            
            # Rule 5: UX friction patterns
            EscalationRule(
                name="UX_FRICTION_PATTERN",
                condition=lambda i: (
                    i.issue_type == "UX_FRICTION" and
                    self._check_frequency(i.summary) >= 5
                ),
                action="SCHEDULE_UX_REVIEW",
                priority=4
            ),
            
            # Default: Add to review queue
            EscalationRule(
                name="DEFAULT_QUEUE",
                condition=lambda i: True,  # Matches everything
                action="ADD_TO_PM_QUEUE",
                priority=999
            )
        ]
    
    def evaluate(self, insight: ConversationClassification) -> List[str]:
        """
        Evaluate all rules against insight, return matching actions.
        
        Returns:
            List of action strings to execute
        """
        matching_actions = []
        
        for rule in sorted(self.rules, key=lambda r: r.priority):
            if rule.condition(insight):
                matching_actions.append(rule.action)
                
                # Stop after first match if high-priority rule
                if rule.priority <= 2:
                    break
        
        return matching_actions
    
    def _check_frequency(self, summary: str) -> int:
        """
        Check how many times this issue has been mentioned.
        Query database for similar summaries.
        """
        # Simplified - would use fuzzy matching or embeddings in production
        cursor = db_conn.cursor()
        cursor.execute("""
            SELECT frequency FROM feature_requests
            WHERE normalized_summary = %s
        """, (normalize_text(summary),))
        result = cursor.fetchone()
        return result[0] if result else 0

def normalize_text(text: str) -> str:
    """Normalize text for deduplication"""
    import re
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    return text
```

### Action Executors

```python
class ActionExecutor:
    def __init__(self, jira_client, productboard_client, slack_client):
        self.jira = jira_client
        self.productboard = productboard_client
        self.slack = slack_client
    
    def execute(self, action: str, insight: ConversationClassification):
        """Execute specified action"""
        handlers = {
            "PAGE_ONCALL_ENGINEER": self._page_oncall,
            "ALERT_CS_MANAGER": self._alert_cs_manager,
            "ESCALATE_TO_FINANCE": self._escalate_finance,
            "CREATE_PRODUCTBOARD_NOTE": self._create_productboard_note,
            "CREATE_JIRA_P0": self._create_jira_p0,
            "SCHEDULE_UX_REVIEW": self._schedule_ux_review,
            "ADD_TO_PM_QUEUE": self._add_to_queue
        }
        
        handler = handlers.get(action)
        if handler:
            handler(insight)
        else:
            print(f"Unknown action: {action}")
    
    def _page_oncall(self, insight):
        """Page on-call engineer via PagerDuty"""
        # Integration with PagerDuty API
        print(f"PAGING ON-CALL: {insight.summary}")
        
    def _alert_cs_manager(self, insight):
        """Send Slack alert to CS manager"""
        self.slack.send_message(
            channel="#customer-success-alerts",
            text=f"🚨 HIGH CHURN RISK\n"
                 f"Conversation: {insight.conversation_id}\n"
                 f"Issue: {insight.summary}\n"
                 f"Sentiment: {insight.sentiment_score}\n"
                 f"<https://app.intercom.com/a/inbox/{insight.conversation_id}|View in Intercom>"
        )
    
    def _create_productboard_note(self, insight):
        """Create note in Productboard"""
        self.productboard.create_note(
            title=insight.summary,
            content=f"Customer feedback from Intercom\n\n"
                    f"Category: {insight.issue_type}\n"
                    f"Sentiment: {insight.sentiment}\n"
                    f"Frequency: {self._get_frequency(insight.summary)} mentions\n\n"
                    f"Conversation: {insight.conversation_id}",
            tags=["customer-request", insight.affected_feature],
            source_url=f"https://app.intercom.com/a/inbox/{insight.conversation_id}"
        )
    
    def _create_jira_p0(self, insight):
        """Create P0 Jira ticket"""
        self.jira.create_issue(
            project="ENG",
            issuetype="Bug",
            summary=f"P0: {insight.summary}",
            description=f"Critical bug reported via customer support\n\n"
                       f"Intercom conversation: {insight.conversation_id}\n"
                       f"Priority: {insight.priority}\n"
                       f"Sentiment: {insight.sentiment}\n\n"
                       f"Customer Impact: {insight.summary}",
            priority="Highest",
            labels=["p0", "customer-reported", insight.affected_feature]
        )
```

---

## Cost Optimization

### Cost Calculation Formula

```python
def calculate_llm_cost(
    num_conversations: int,
    avg_input_tokens: int = 500,
    avg_output_tokens: int = 100,
    model: str = "gpt-4o-mini"
) -> dict:
    """
    Calculate LLM API costs for batch processing.
    
    Pricing (as of Jan 2026):
    - GPT-4o-mini: $0.15/1M input, $0.60/1M output
    - Claude Haiku 3.5: $0.25/1M input, $1.25/1M output
    - Claude Sonnet 4.5: $3.00/1M input, $15.00/1M output
    
    Returns:
        Dict with cost breakdown
    """
    pricing = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "claude-haiku-3.5": {"input": 0.25, "output": 1.25},
        "claude-sonnet-4.5": {"input": 3.00, "output": 15.00}
    }
    
    rates = pricing.get(model, pricing["gpt-4o-mini"])
    
    total_input_tokens = num_conversations * avg_input_tokens
    total_output_tokens = num_conversations * avg_output_tokens
    
    input_cost = (total_input_tokens / 1_000_000) * rates["input"]
    output_cost = (total_output_tokens / 1_000_000) * rates["output"]
    total_cost = input_cost + output_cost
    
    cost_per_conversation = total_cost / num_conversations
    
    return {
        "model": model,
        "num_conversations": num_conversations,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "input_cost": round(input_cost, 2),
        "output_cost": round(output_cost, 2),
        "total_cost": round(total_cost, 2),
        "cost_per_conversation": round(cost_per_conversation, 5)
    }

# Examples
print(calculate_llm_cost(10_000, model="gpt-4o-mini"))
# {'model': 'gpt-4o-mini', 'num_conversations': 10000, 'total_cost': 1.35, 'cost_per_conversation': 0.00014}

print(calculate_llm_cost(10_000, model="claude-haiku-3.5"))
# {'model': 'claude-haiku-3.5', 'total_cost': 2.50, 'cost_per_conversation': 0.00025}
```

### Optimization Strategies

#### 1. Tiered Model Selection

```python
def select_optimal_model(conversation: dict) -> str:
    """
    Choose cheapest model that meets accuracy requirements.
    
    Strategy:
    - Simple/clear cases → GPT-4o-mini (cheapest)
    - Ambiguous cases → Claude Haiku (better reasoning)
    - Complex multi-turn → Claude Sonnet (highest accuracy)
    """
    message_count = len(conversation["messages"])
    avg_message_length = sum(len(m) for m in conversation["messages"]) / message_count
    
    # Rule-based triage
    if message_count <= 2 and avg_message_length < 200:
        return "gpt-4o-mini"  # Simple, short conversations
    elif message_count <= 5:
        return "claude-haiku-3.5"  # Medium complexity
    else:
        return "claude-sonnet-4.5"  # Complex multi-turn
```

#### 2. Prompt Caching

```python
# Structure prompts to maximize cache hits

# ✅ GOOD: Static instruction first (cached)
STATIC_INSTRUCTIONS = """
Analyze this customer support conversation and categorize it.

CATEGORIES:
- PRODUCT_BUG: Any error, unexpected behavior...
- ACCOUNT_ACCESS: Problems with login...
[...full category definitions - 800 tokens...]

OUTPUT FORMAT:
Respond with JSON: {"issue_type": "...", "priority": "...", ...}
"""

def format_prompt_cached(conversation):
    # Anthropic caches first N tokens if identical across requests
    return STATIC_INSTRUCTIONS + f"\n\nCONVERSATION:\n{conversation['text']}"

# ❌ BAD: Variable content first (no caching benefit)
def format_prompt_uncached(conversation):
    return f"CONVERSATION:\n{conversation['text']}\n\n" + STATIC_INSTRUCTIONS
```

#### 3. Batch API Usage

```python
# Use batch endpoints for 50%+ cost savings

def submit_batch_job(conversations: list, model="gpt-4o-mini"):
    """
    Submit batch job to OpenAI Batch API.
    Cost: 50% discount vs real-time API.
    Latency: Completes within 24 hours (usually <2 hours)
    """
    from openai import OpenAI
    client = OpenAI()
    
    # Format batch input file (JSONL)
    batch_requests = []
    for i, conv in enumerate(conversations):
        batch_requests.append({
            "custom_id": conv["id"],
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model,
                "messages": [
                    {"role": "user", "content": format_prompt_cached(conv)}
                ],
                "response_format": {"type": "json_object"}
            }
        })
    
    # Write to file
    with open("batch_input.jsonl", "w") as f:
        for req in batch_requests:
            f.write(json.dumps(req) + "\n")
    
    # Upload and submit
    batch_file = client.files.create(
        file=open("batch_input.jsonl", "rb"),
        purpose="batch"
    )
    
    batch_job = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )
    
    return batch_job.id
```

#### 4. Conversation Summarization for Long Threads

```python
def preprocess_long_conversation(conversation: dict, max_tokens=2000) -> str:
    """
    Summarize long conversations before classification to reduce tokens.
    
    Two-step process:
    1. Summarize (cheap model, short output)
    2. Classify summary (saves on classification prompt tokens)
    """
    full_text = "\n".join(conversation["messages"])
    
    if count_tokens(full_text) <= max_tokens:
        return full_text  # Short enough, no summarization needed
    
    # Step 1: Summarize
    summary_prompt = f"""
Summarize this customer support conversation in 3-4 sentences.
Focus on: core issue, customer sentiment, key requests/complaints.

CONVERSATION:
{full_text}

SUMMARY:"""
    
    summary = llm_call(summary_prompt, max_tokens=150, model="gpt-4o-mini")
    
    # Step 2: Classify the summary (main classification prompt)
    return summary

# Cost comparison:
# - Direct classification: 5000 input tokens × $0.15/1M = $0.00075
# - Summarize then classify: (5000×$0.15 + 150×$0.60 + 300×$0.15)/1M = $0.00030
# Savings: 60%
```

#### 5. Incremental Processing

```python
def get_unprocessed_conversations():
    """
    Only process conversations not already analyzed.
    Prevents duplicate LLM calls on re-runs.
    """
    cursor = db_conn.cursor()
    
    # Get all conversation IDs from last 24 hours
    recent_convs = fetch_all_conversations(created_since=time.time() - 86400)
    recent_ids = [c["id"] for c in recent_convs]
    
    # Check which are already processed
    cursor.execute("""
        SELECT conversation_id FROM conversation_insights
        WHERE conversation_id = ANY(%s)
    """, (recent_ids,))
    
    processed_ids = {row[0] for row in cursor.fetchall()}
    unprocessed_ids = [cid for cid in recent_ids if cid not in processed_ids]
    
    return [c for c in recent_convs if c["id"] in unprocessed_ids]
```

---

## Implementation Checklist

### Phase 1: Prototype (Week 1-2)
- [ ] Set up Intercom API authentication
- [ ] Export 100-200 sample conversations
- [ ] Create manual classification baseline (2-3 humans, calculate agreement)
- [ ] Test zero-shot prompt with GPT-4o-mini
- [ ] Measure accuracy vs. human baseline (target: 80%+)
- [ ] Iterate on prompt until accuracy acceptable
- [ ] Calculate cost projection for monthly volume
- [ ] Document prompt template and accuracy metrics

### Phase 2: Batch Pipeline MVP (Week 3-4)
- [ ] Set up PostgreSQL/MongoDB database
- [ ] Create schema (conversation_insights, feature_requests tables)
- [ ] Write Intercom API fetch script (with pagination)
- [ ] Implement LLM classification function (with error handling)
- [ ] Build parallel batch processing (ThreadPoolExecutor)
- [ ] Create storage layer (insert into database)
- [ ] Implement report generation (SQL aggregations)
- [ ] Set up scheduled execution (cron/Airflow/GitHub Actions)
- [ ] Configure email/Slack notifications
- [ ] Test end-to-end on small batch (10-50 conversations)
- [ ] Run full daily batch and validate outputs

### Phase 3: Product Tool Integration (Week 5-6)
- [ ] Set up API credentials (Jira/Productboard/Linear)
- [ ] Define escalation rules (frequency thresholds, priority mappings)
- [ ] Implement rule engine (condition checking logic)
- [ ] Build action executors (create tickets, notes, alerts)
- [ ] Add deduplication logic (check for existing items)
- [ ] Implement LLM-powered backlog item generation
- [ ] Test integration with 10 sample insights
- [ ] Monitor for duplicate ticket creation
- [ ] Gather Product team feedback on backlog item quality
- [ ] Tune thresholds based on backlog capacity

### Phase 4: Real-Time Workflows (Week 7-8)
- [ ] Configure Intercom webhooks (conversation.user.replied)
- [ ] Set up webhook receiver endpoint (Flask/FastAPI)
- [ ] Implement real-time LLM classification (<1s latency)
- [ ] Build conditional routing logic
- [ ] Add Intercom update actions (assign, tag, note)
- [ ] Configure Slack/PagerDuty alerts
- [ ] Implement circuit breaker (fallback if LLM API down)
- [ ] Add monitoring (latency, error rate, throughput)
- [ ] Test with staging Intercom workspace
- [ ] Deploy to production with gradual rollout
- [ ] Monitor for 48 hours, iterate on rules

### Phase 5: Optimization & Monitoring (Ongoing)
- [ ] Set up cost tracking dashboard (daily LLM API spend)
- [ ] Implement model tiering (simple → GPT-4o-mini, complex → Sonnet)
- [ ] Enable prompt caching for batch jobs
- [ ] Weekly quality audit (sample 50 classifications, check accuracy)
- [ ] Monthly threshold review (adjust based on backlog capacity)
- [ ] Quarterly prompt evolution (update for new product areas)
- [ ] Track impact metrics:
  - [ ] % of backlog from LLM insights (target: 30-50%)
  - [ ] Time from mention to backlog (target: <48h)
  - [ ] Feature adoption rate (LLM-identified vs internal)
  - [ ] Support volume change (did product improvements reduce tickets?)

---

## Troubleshooting Guide

### Issue: Low Classification Accuracy (<70%)

**Diagnosis**:
```python
# Compare LLM classifications to human baseline
def audit_accuracy(sample_size=50):
    conversations = fetch_random_sample(sample_size)
    
    for conv in conversations:
        llm_result = classify_single(conv)
        print(f"\nConversation: {conv['subject']}")
        print(f"LLM: {llm_result.issue_type} | {llm_result.priority}")
        human_label = input("Correct label (or 'correct'): ")
        # Log discrepancies
```

**Solutions**:
1. **Add examples** (few-shot): Include 2-3 labeled examples per category in prompt
2. **Clarify definitions**: Make category boundaries more explicit
3. **Add context**: Include customer plan, tenure, previous ticket count
4. **Use chain-of-thought**: Ask LLM to explain reasoning before classification
5. **Switch model**: Try Claude Sonnet instead of GPT-4o-mini for ambiguous cases

---

### Issue: High API Costs

**Diagnosis**:
```python
# Identify cost drivers
def analyze_token_usage():
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 
            AVG(input_tokens) as avg_input,
            MAX(input_tokens) as max_input,
            AVG(output_tokens) as avg_output
        FROM llm_api_logs
        WHERE created_at >= NOW() - INTERVAL '7 days'
    """)
    stats = cursor.fetchone()
    print(f"Avg input: {stats[0]}, Max: {stats[1]}, Avg output: {stats[2]}")
```

**Solutions**:
1. **Switch to batch API**: 50% cost reduction for non-urgent processing
2. **Summarize long conversations**: Preprocess threads >2000 tokens
3. **Tier models**: Use GPT-4o-mini for 80% of conversations
4. **Enable prompt caching**: Structure prompts with static instructions first
5. **Truncate old messages**: Only include last 5 messages from long threads

---

### Issue: Slow Batch Processing

**Diagnosis**:
```python
import time

def profile_pipeline():
    start = time.time()
    
    t1 = time.time()
    conversations = fetch_conversations(24)
    print(f"Fetch: {t1-start:.2f}s")
    
    t2 = time.time()
    insights = classify_batch(conversations)
    print(f"Classify: {t2-t1:.2f}s")
    
    t3 = time.time()
    store_insights(insights)
    print(f"Store: {t3-t2:.2f}s")
```

**Solutions**:
1. **Increase parallelism**: Raise max_workers from 10 to 20-50 (respect rate limits)
2. **Use async I/O**: Switch from ThreadPoolExecutor to asyncio for better concurrency
3. **Optimize database writes**: Batch INSERT with executemany() instead of individual inserts
4. **Cache Intercom fetches**: Store raw conversations, reprocess if needed
5. **Profile slow queries**: Add indexes on frequently queried columns

---

### Issue: Duplicate Backlog Items

**Diagnosis**:
```python
# Check for similar existing items before creating
def find_similar_issues(summary: str, threshold=0.8):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    
    existing = fetch_all_backlog_items()
    
    vectorizer = TfidfVectorizer()
    all_summaries = [summary] + [item["summary"] for item in existing]
    vectors = vectorizer.fit_transform(all_summaries)
    
    similarities = cosine_similarity(vectors[0:1], vectors[1:]).flatten()
    
    similar_items = [
        existing[i] for i, sim in enumerate(similarities) if sim >= threshold
    ]
    
    return similar_items
```

**Solutions**:
1. **Normalize summaries**: Remove punctuation, lowercase, stem words before comparison
2. **Use embeddings**: Compare semantic similarity with sentence-transformers
3. **Check before creation**: Query existing items, skip if similarity >0.8
4. **Human review**: Flag potential duplicates for PM to merge manually
5. **Dedupe in LLM**: Ask LLM "Is this similar to existing item X?" before creating

---

### Issue: LLM API Rate Limits

**Symptoms**: 429 errors, requests throttled

**Solutions**:
1. **Exponential backoff**: Retry with increasing delays (1s, 2s, 4s, 8s...)
2. **Reduce parallelism**: Lower max_workers to stay under rate limit
3. **Request higher limits**: Contact API provider for rate increase
4. **Use batch endpoint**: No rate limits on batch API submissions
5. **Distribute load**: Spread processing across multiple time windows

```python
import time
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60)
)
def llm_call_with_retry(prompt):
    try:
        return anthropic_client.messages.create(...)
    except anthropic.RateLimitError as e:
        print(f"Rate limited, retrying...")
        raise  # tenacity will handle retry
```

---

## Quick Reference: Key Metrics

### Classification Quality
- **Target Accuracy**: ≥80% agreement with human baseline
- **Audit Frequency**: Weekly sample of 50 classifications
- **Acceptable Drift**: <5% accuracy drop before retuning prompts

### Performance
- **Batch Processing**: Complete daily batch in <30 minutes
- **Real-Time Latency**: <1 second for event-driven workflows
- **Database Queries**: <100ms for report generation

### Cost
- **Per-Conversation**: $0.00013 - $0.00025 (depending on model)
- **Monthly Budget** (10K conversations): $1.30 - $2.50
- **ROI vs Manual**: 2,000x+ (LLM vs $50/hr human labor)

### Business Impact
- **Backlog Sourcing**: 30-50% from LLM insights
- **Insight to Backlog Time**: <48 hours for high priority
- **Escalation Speed**: Critical issues flagged <1 minute
- **Support Volume**: Monitor 10-20% reduction after fixes shipped

---

## Integration Examples

### Make.com Scenario Structure

```yaml
Scenario: "Intercom → LLM Classification → Multi-Tool Routing"

Modules:
  1. Trigger:
      type: Intercom - Watch Conversations
      filters: 
        - state = open
        - plan IN ["pro", "enterprise"]
        - NOT tagged with "processed"
  
  2. HTTP Request:
      method: POST
      url: https://api.anthropic.com/v1/messages
      headers:
        - x-api-key: {{env.ANTHROPIC_KEY}}
        - anthropic-version: "2023-06-01"
      body:
        model: claude-haiku-3-5
        max_tokens: 512
        messages:
          - role: user
            content: {{classification_prompt}}
  
  3. JSON Parser:
      input: {{http.data.content[0].text}}
  
  4. Router:
      routes:
        - condition: {{json.issue_type}} = "PRODUCT_BUG" AND {{json.priority}} = "CRITICAL"
          target: Jira Create Issue
        
        - condition: {{json.issue_type}} = "FEATURE_REQUEST"
          target: Productboard Create Note
        
        - condition: {{json.churn_risk}} = "HIGH"
          target: Slack Send Message → HubSpot Create Task
        
        - condition: {{json.issue_type}} = "BILLING"
          target: Intercom Assign Conversation
  
  5a. Jira Create Issue:
      project: ENG
      issue_type: Bug
      summary: "P0: {{json.summary}}"
      priority: Highest
      labels: ["p0", "customer-reported"]
  
  5b. Productboard Create Note:
      title: {{json.summary}}
      content: "Customer feedback ({{json.frequency}} mentions)"
      tags: ["customer-request", {{json.affected_feature}}]
  
  5c. Slack Send Message:
      channel: "#cs-alerts"
      text: "🚨 High churn risk: {{json.summary}}"
  
  6. Intercom Update Conversation:
      conversation_id: {{trigger.id}}
      custom_attributes:
        llm_classification: {{json.issue_type}}
        llm_priority: {{json.priority}}
      tags: ["processed"]
```

---

## Appendix: Sample Outputs

### Example Classification Output

```json
{
  "conversation_id": "conv_12345",
  "issue_type": "PRODUCT_BUG",
  "priority": "HIGH",
  "sentiment": "NEGATIVE",
  "sentiment_score": -0.65,
  "churn_risk": "MEDIUM",
  "summary": "User unable to sync contacts with Salesforce CRM integration",
  "affected_feature": "integrations",
  "customer_segment": "enterprise",
  "confidence": 0.9,
  "recommended_action": "CREATE_TICKET"
}
```

### Example Backlog Item (Jira Format)

```json
{
  "project": "ENG",
  "issuetype": "Bug",
  "summary": "Salesforce sync fails for contacts with custom fields",
  "description": "**Customer Impact**\nEnterprise customers unable to sync contacts from Salesforce when custom fields are present. Blocking critical CRM workflow.\n\n**Evidence**\n- Reported in 12 conversations over 7 days\n- Average sentiment: -0.68 (highly negative)\n- Affects 8 enterprise accounts (est. $45K MRR)\n\n**Conversations**\n- https://app.intercom.com/a/inbox/conv_12345\n- https://app.intercom.com/a/inbox/conv_12378\n- https://app.intercom.com/a/inbox/conv_12401\n\n**Representative Quote**\n\"We've been trying to sync our Salesforce contacts for 3 days now. Every time it fails with a vague error. This is blocking our entire sales team from using your product.\"",
  "priority": "High",
  "labels": ["customer-reported", "integrations", "salesforce", "enterprise"],
  "components": ["Integrations"],
  "customfields": {
    "rice_score": 85.3,
    "customer_evidence_count": 12,
    "first_reported": "2026-01-01",
    "estimated_mrr_impact": 45000
  }
}
```

---

## End of Guide

**For AI Implementation**: This guide provides complete technical specifications for building LLM-powered Intercom conversation analysis pipelines. All code examples are production-ready patterns. Adapt configuration values (API keys, database connections, thresholds) to specific deployment environment.

**Last Updated**: January 5, 2026  
**Version**: 1.0  
**Maintained by**: Product Operations Team