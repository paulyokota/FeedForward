#!/usr/bin/env python3
"""
Stage 1: Quick Routing Classifier

Purpose: Fast classification for immediate routing and auto-responses
Input: Customer's initial message only
Speed: <1 second
Confidence: Medium-High acceptable
Use: Route to support team, priority assignment, auto-response triggers
"""
import os
import json
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load vocabulary for context
VOCAB_PATH = Path(__file__).parent.parent / "config" / "theme_vocabulary.json"
with open(VOCAB_PATH) as f:
    VOCABULARY = json.load(f)

# Stage 1 classification prompt
STAGE1_PROMPT = """You are a fast conversation classifier for customer support routing.

**Your Goal:** Quickly classify the conversation type from the customer's initial message for routing purposes.

**Conversation Details:**
- Source Type: {source_type}
- Source URL: {source_url}

**Customer Message:**
{customer_message}

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

## URL Context Boost

{url_context_hint}

## Classification Guidelines

- **Speed over perfection** - You have <1s, make a quick decision
- **Medium confidence is OK** - This is just for routing, Stage 2 will refine
- **When unclear, use general_inquiry** - Better to route broadly than incorrectly
- **Look for urgency signals** - Account access, payment failures, critical bugs
- **Spam detection** - Generic marketing, guest post offers, sales

---

Respond in JSON format:
{{
  "conversation_type": "one of the 8 types above",
  "confidence": "high|medium|low",
  "reasoning": "1-2 sentences explaining your choice",
  "key_signals": ["signal 1", "signal 2", "signal 3"],
  "urgency": "critical|high|normal|low",
  "routing_notes": "brief notes for support team (1 sentence)"
}}

Focus on SPEED and routing accuracy. Stage 2 will handle precise classification."""


def get_url_context_hint(source_url: str | None) -> str:
    """Generate URL context hint for prompt."""
    if not source_url:
        return "No URL context available."

    # Check vocabulary for URL pattern matches
    url_patterns = VOCABULARY.get("url_patterns", {})

    for pattern, info in url_patterns.items():
        if pattern in source_url:
            product_area = info.get("product_area", "unknown")
            return f"**URL Context:** User was on {pattern} ({product_area} area). This suggests they may need help with {product_area}-related features."

    return f"URL: {source_url} (no specific product area match)"


def classify_stage1(
    customer_message: str,
    source_url: str | None = None,
    source_type: str | None = None
) -> Dict[str, Any]:
    """
    Fast customer-only classification for routing.

    Args:
        customer_message: The customer's initial message
        source_url: Optional source URL for context
        source_type: Optional source type (email, chat, etc.)

    Returns:
        {
            "conversation_type": str,
            "confidence": "high" | "medium" | "low",
            "routing_priority": "urgent" | "high" | "normal" | "low",
            "auto_response_eligible": bool,
            "stage": 1,
            "url_context": str | None,
            "key_signals": list[str],
            "reasoning": str,
            "urgency": str
        }
    """
    if not customer_message or not customer_message.strip():
        return {
            "conversation_type": "general_inquiry",
            "confidence": "low",
            "routing_priority": "low",
            "auto_response_eligible": False,
            "stage": 1,
            "url_context": source_url,
            "key_signals": ["empty message"],
            "reasoning": "Empty customer message",
            "urgency": "low"
        }

    # Generate URL context hint
    url_hint = get_url_context_hint(source_url)

    # Build prompt
    prompt = STAGE1_PROMPT.format(
        source_type=source_type or "unknown",
        source_url=source_url or "none",
        customer_message=customer_message,
        url_context_hint=url_hint
    )

    # Call LLM (gpt-4o-mini for speed)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a fast, accurate conversation classifier for customer support routing."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Lower for consistency
            max_tokens=300,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        # Map urgency to routing priority
        urgency = result.get("urgency", "normal")
        routing_priority_map = {
            "critical": "urgent",
            "high": "high",
            "normal": "normal",
            "low": "low"
        }
        routing_priority = routing_priority_map.get(urgency, "normal")

        # Determine auto-response eligibility
        auto_response_eligible = (
            result["conversation_type"] == "spam" or
            (result["conversation_type"] == "how_to_question" and result["confidence"] == "high")
        )

        return {
            "conversation_type": result["conversation_type"],
            "confidence": result["confidence"],
            "routing_priority": routing_priority,
            "auto_response_eligible": auto_response_eligible,
            "stage": 1,
            "url_context": source_url,
            "key_signals": result.get("key_signals", []),
            "reasoning": result.get("reasoning", ""),
            "urgency": urgency,
            "routing_notes": result.get("routing_notes", "")
        }

    except Exception as e:
        # Fallback on error
        return {
            "conversation_type": "general_inquiry",
            "confidence": "low",
            "routing_priority": "normal",
            "auto_response_eligible": False,
            "stage": 1,
            "url_context": source_url,
            "key_signals": [f"classification error: {str(e)}"],
            "reasoning": "Classification failed, defaulting to general_inquiry",
            "urgency": "normal",
            "error": str(e)
        }


def should_auto_respond(stage1_result: Dict[str, Any]) -> bool:
    """
    Determine if conversation is eligible for auto-response.

    Args:
        stage1_result: Result from classify_stage1

    Returns:
        True if auto-response should be sent
    """
    return stage1_result.get("auto_response_eligible", False)


def get_routing_team(conversation_type: str) -> str:
    """
    Map conversation type to support team.

    Args:
        conversation_type: Classified type from Stage 1

    Returns:
        Team name to route to
    """
    routing_map = {
        "product_issue": "engineering_support",
        "billing_question": "billing_team",
        "account_issue": "account_support",
        "configuration_help": "onboarding_team",
        "how_to_question": "general_support",
        "feature_request": "product_team",
        "spam": "spam_filter",
        "general_inquiry": "general_support"
    }

    return routing_map.get(conversation_type, "general_support")


def main():
    """Test Stage 1 classifier."""
    test_cases = [
        {
            "message": "I need to cancel my account",
            "url": None,
            "source": "email"
        },
        {
            "message": "The signup page isn't working",
            "url": "/signup",
            "source": "web"
        },
        {
            "message": "How do I schedule posts to Pinterest?",
            "url": "/publisher/queue",
            "source": "chat"
        }
    ]

    print("=" * 60)
    print("Stage 1 Classifier Test\n")

    for i, test in enumerate(test_cases, 1):
        print(f"{i}. {test['message'][:50]}...")
        result = classify_stage1(
            test["message"],
            source_url=test["url"],
            source_type=test["source"]
        )
        print(f"   Type: {result['conversation_type']} ({result['confidence']})")
        print(f"   Priority: {result['routing_priority']}")
        print(f"   Team: {get_routing_team(result['conversation_type'])}")
        print(f"   Reasoning: {result['reasoning']}")
        print()


if __name__ == "__main__":
    main()
