#!/usr/bin/env python3
"""
Stage 2: Refined Analysis Classifier

Purpose: High-accuracy classification with full conversation context
Input: Customer message + support response(s) + resolution actions
Speed: Can be slower (not time-critical)
Confidence: 100% high target
Use: Analytics, knowledge extraction, escalation, continuous learning
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, List
from openai import OpenAI

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Stage 2 classification prompt
STAGE2_PROMPT = """You are analyzing a COMPLETE customer support conversation for accurate classification and knowledge extraction.

**Your Goal:** Provide high-confidence classification using the full conversation context (customer + support).

**Conversation Details:**
- Source Type: {source_type}
- Source URL: {source_url}
- Stage 1 Type: {stage1_type} (initial routing classification)

**Customer Message:**
{customer_message}

**Support Response(s):**
{support_messages}

{resolution_context}

---

## Conversation Types

Classify into ONE of these types (customer's PRIMARY need):

1. **product_issue** - Bug, feature not working, data issue, technical problem
2. **how_to_question** - Feature usage help, workflow guidance, "how do I..."
3. **feature_request** - New capability request, enhancement idea
4. **account_issue** - Login problems, access issues, OAuth, permissions, sessions
5. **billing_question** - Payment, plan changes, invoice, subscription, cancellation
6. **configuration_help** - Setup assistance, integration, settings configuration
7. **general_inquiry** - Unclear intent, exploratory, multiple topics
8. **spam** - Marketing, guest posts, sales pitches, irrelevant

## Key Advantages of Support Context

Support responses reveal:
- **Disambiguating vague requests** - "cancel my account" → Support confirms it's subscription cancellation
- **Root causes** - "This is due to downtime" reveals product issue vs user error
- **Precise product area** - Support mentions specific features, products
- **Issue confirmation** - Support confirms what the actual problem is

## Classification Guidelines

- **Aim for HIGH confidence** - You have full context, be precise
- **Support response is ground truth** - Use what support confirmed, not just customer's vague description
- **Resolution signal helps** - If support cancelled subscription → billing_question
- **Disambiguate Stage 1** - Did Stage 1 miss the real issue? Support reveals truth
- **When support clarifies** - Trust support's interpretation of customer need

---

Respond in JSON format:
{{
  "conversation_type": "one of the 8 types above",
  "confidence": "high|medium|low",
  "reasoning": "2-3 sentences explaining your choice, referencing support context",

  "disambiguation": {{
    "level": "high|medium|low|none - how much did support clarify vague customer message?",
    "what_customer_said": "brief summary of customer's vague request",
    "what_support_revealed": "what support confirmed the issue actually is"
  }},

  "support_insights": {{
    "issue_confirmed": "what support confirmed (or null)",
    "root_cause": "why it's happening per support (or null)",
    "solution_type": "what kind of fix was offered (or null)",
    "products_mentioned": ["product1", "product2"],
    "features_mentioned": ["feature1", "feature2"]
  }},

  "classification_change": {{
    "changed_from_stage1": true|false,
    "reason_for_change": "why classification changed (or null if unchanged)"
  }}
}}

Provide HIGH-CONFIDENCE, ACCURATE classification using full conversation context."""


def classify_stage2(
    customer_message: str,
    support_messages: List[str],
    resolution_signal: str | None = None,
    source_url: str | None = None,
    stage1_type: str = "unknown"
) -> Dict[str, Any]:
    """
    Full-context classification with support responses.

    Args:
        customer_message: The customer's initial message
        support_messages: List of support team responses
        resolution_signal: Detected resolution action (from resolution_analyzer)
        source_url: Optional source URL for context
        stage1_type: Type from Stage 1 classification

    Returns:
        {
            "conversation_type": str,
            "confidence": "high" | "medium" | "low",
            "changed_from_stage_1": bool,
            "stage1_type": str,
            "resolution_signal": dict | None,
            "disambiguation_level": "high" | "medium" | "low" | "none",
            "stage": 2,
            "reasoning": str,
            "support_insights": dict
        }
    """
    if not customer_message or not customer_message.strip():
        return {
            "conversation_type": "general_inquiry",
            "confidence": "low",
            "changed_from_stage_1": False,
            "stage1_type": stage1_type,
            "resolution_signal": resolution_signal,
            "disambiguation_level": "none",
            "stage": 2,
            "reasoning": "Empty customer message",
            "support_insights": {}
        }

    if not support_messages:
        # No support context - return same as Stage 1
        return {
            "conversation_type": stage1_type,
            "confidence": "medium",
            "changed_from_stage_1": False,
            "stage1_type": stage1_type,
            "resolution_signal": resolution_signal,
            "disambiguation_level": "none",
            "stage": 2,
            "reasoning": "No support response available, using Stage 1 classification",
            "support_insights": {}
        }

    # Build resolution context section
    resolution_context = ""
    if resolution_signal and isinstance(resolution_signal, dict):
        action = resolution_signal.get("action", "unknown")
        suggested_type = resolution_signal.get("conversation_type", "unknown")
        resolution_context = f"""
**Resolution Signal Detected:**
- Action: {action}
- Suggests type: {suggested_type}
- This provides additional classification confidence
"""

    # Format support messages
    support_text = "\n\n".join([f"Support: {msg}" for msg in support_messages])

    # Build prompt
    prompt = STAGE2_PROMPT.format(
        source_type="unknown",  # Not critical for Stage 2
        source_url=source_url or "none",
        stage1_type=stage1_type,
        customer_message=customer_message,
        support_messages=support_text,
        resolution_context=resolution_context
    )

    # Call LLM (gpt-4o-mini, could upgrade to gpt-4o for even better accuracy)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a highly accurate conversation classifier with full conversation context. Aim for 100% high confidence."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Very low for consistency and accuracy
            max_tokens=500,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        # Extract fields
        conversation_type = result["conversation_type"]
        confidence = result.get("confidence", "medium")

        disambiguation = result.get("disambiguation", {})
        support_insights = result.get("support_insights", {})
        classification_change = result.get("classification_change", {})

        return {
            "conversation_type": conversation_type,
            "confidence": confidence,
            "changed_from_stage_1": classification_change.get("changed_from_stage1", False),
            "stage1_type": stage1_type,
            "resolution_signal": resolution_signal,
            "disambiguation_level": disambiguation.get("level", "medium"),
            "stage": 2,
            "reasoning": result.get("reasoning", ""),
            "support_insights": support_insights,
            "disambiguation": disambiguation,
            "change_reason": classification_change.get("reason_for_change")
        }

    except Exception as e:
        # Fallback on error
        return {
            "conversation_type": stage1_type,  # Fall back to Stage 1
            "confidence": "low",
            "changed_from_stage_1": False,
            "stage1_type": stage1_type,
            "resolution_signal": resolution_signal,
            "disambiguation_level": "none",
            "stage": 2,
            "reasoning": f"Classification failed: {str(e)}",
            "support_insights": {},
            "error": str(e)
        }


def should_update_classification(
    stage1_result: Dict[str, Any],
    stage2_result: Dict[str, Any]
) -> bool:
    """
    Determine if Stage 2 should override Stage 1 classification.

    Args:
        stage1_result: Result from Stage 1
        stage2_result: Result from Stage 2

    Returns:
        True if classification should be updated
    """
    # Update if types differ and Stage 2 has high confidence
    return (
        stage1_result["conversation_type"] != stage2_result["conversation_type"]
        and stage2_result["confidence"] == "high"
    )


def extract_disambiguation_level(
    customer_message: str,
    support_messages: List[str]
) -> str:
    """
    Assess how much support clarified the customer's vague message.

    Args:
        customer_message: Customer's initial message
        support_messages: Support team responses

    Returns:
        "high" | "medium" | "low" | "none"
    """
    # This is now handled by the LLM in Stage 2
    # Kept for backward compatibility
    if not support_messages:
        return "none"

    # Heuristic: longer support responses likely provide more disambiguation
    avg_support_length = sum(len(msg) for msg in support_messages) / len(support_messages)

    if avg_support_length > 200:
        return "high"
    elif avg_support_length > 100:
        return "medium"
    else:
        return "low"


def main():
    """Test Stage 2 classifier."""
    test_cases = [
        {
            "customer": "I need help with my account",
            "support": [
                "I'm sorry you're looking to cancel your subscription. Could you share why?",
                "I've initialized that cancellation for you. You won't be charged again."
            ],
            "stage1": "account_issue"
        },
        {
            "customer": "The signup page isn't working",
            "support": [
                "I'm sorry about that! This is due to a downtime we experienced earlier.",
                "The issue has been resolved now. You should try signing up again."
            ],
            "stage1": "product_issue"
        }
    ]

    print("=" * 60)
    print("Stage 2 Classifier Test\n")

    for i, test in enumerate(test_cases, 1):
        print(f"{i}. Customer: {test['customer'][:40]}...")
        print(f"   Stage 1: {test['stage1']}")

        result = classify_stage2(
            test["customer"],
            test["support"],
            stage1_type=test["stage1"]
        )

        print(f"   Stage 2: {result['conversation_type']} ({result['confidence']})")
        print(f"   Changed: {result['changed_from_stage_1']}")
        print(f"   Disambiguation: {result['disambiguation_level']}")
        print(f"   Reasoning: {result['reasoning'][:60]}...")
        print()


if __name__ == "__main__":
    main()
