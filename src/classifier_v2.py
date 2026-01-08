"""
Improved Conversation Classifier v2.

Key improvements based on Phase 3 human grouping analysis:
1. Merged bug_report + product_question into technical_issue
2. Added short message handling to avoid spurious "other" classifications
3. Updated category definitions to better match human grouping behavior

Changes from v1:
- bug_report + product_question → technical_issue
- Added is_ambiguous flag for short messages
- Tightened "other" definition
"""

import json
import os
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field

# Load API key from environment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_FILE = PROJECT_ROOT / "data" / "labeled_fixtures.json"


class ClassificationResultV2(BaseModel):
    """Structured output from improved classifier."""

    issue_type: str = Field(
        description="Primary issue category",
        enum=[
            "technical_issue",      # NEW: Merged bug_report + product_question
            "feature_request",
            "plan_question",
            "marketing_question",
            "billing",
            "account_access",
            "feedback",
            "other",
        ],
    )
    sentiment: str = Field(
        description="Customer sentiment",
        enum=["frustrated", "neutral", "satisfied"],
    )
    churn_risk: bool = Field(
        description="True if customer shows signs of leaving",
    )
    priority: str = Field(
        description="Urgency level",
        enum=["urgent", "high", "normal", "low"],
    )
    is_ambiguous: bool = Field(
        description="True if message is too short/vague to classify confidently",
        default=False,
    )


# Updated system prompt with merged categories and better "other" guidance
SYSTEM_PROMPT_V2 = """You are a customer support classifier for Tailwind, a social media scheduling tool.

Analyze the customer message and classify it according to:

## Issue Type (pick ONE):

- technical_issue: ANY problem with the product - bugs, errors, features not working, confusion about how to use features, unexpected behavior. This includes:
  * Something is broken or shows error messages
  * "How do I do X?" when X should work but doesn't
  * "Why is X happening?" when behavior is unexpected
  * "Is it not possible to X anymore?" (feature seems broken)
  * Features not loading, buttons not working, scheduling failures
  * User is confused because something changed or doesn't work as expected

- feature_request: Customer explicitly wants NEW capability ("would be great if", "please add", "I wish I could")

- plan_question: Questions about subscription/plan LIMITS and what's INCLUDED - "how many accounts can I connect?", "what's in Pro vs Max?"

- marketing_question: Social media strategy, Pinterest/Instagram growth, best posting times. Includes platform-specific issues (Pinterest suspension) that aren't Tailwind bugs.

- billing: Payment issues, refunds, subscription changes, unexpected charges

- account_access: Tailwind login problems, password reset, permissions. NOT platform connection issues (those are technical_issue)

- feedback: Meta-feedback about the product or support experience, praise, general complaints without a specific technical issue

- other: ONLY use for:
  * Actual spam or completely off-topic messages
  * Messages in foreign languages you can't understand
  * Messages that are TRULY unclassifiable even with context

  DO NOT use "other" for:
  * Short greetings like "hello", "hi", "help" - these are likely technical_issue
  * Ticket follow-ups like "any update?" - classify based on likely issue type
  * Single words that suggest support need - these are likely technical_issue

## Ambiguous Message Handling:

Set is_ambiguous=true if:
- Message has fewer than 5 words AND
- Contains no clear category signal (no error description, no feature name, no billing term)

Examples of ambiguous: "hello", "help", "operator", "team", "hi there"
Examples NOT ambiguous: "pins not posting", "billing question", "can't login"

When is_ambiguous=true, still make your best guess at issue_type based on support context (most short messages are technical_issue).

## Sentiment:
- frustrated: Explicit emotion ("annoying", "terrible", "ridiculous"), ALL CAPS, exclamation marks
- neutral: Matter-of-fact tone, polite descriptions
- satisfied: Explicit positive emotion ("love", "great", "thank you so much")

## Churn Risk:
- true: Present intent to cancel ("I want to cancel", "how do I cancel")
- false: Past tense cancellation, downgrade requests, general questions

## Priority:
- urgent: Complete account lockout, payment system failure
- high: ONLY if customer explicitly says they cannot do their job
- normal: Default for most issues
- low: Pure positive feedback with no request

Respond with JSON only."""


def classify_conversation_v2(text: str) -> dict:
    """
    Classify a customer conversation using improved v2 logic.

    Key improvements:
    - Merged bug_report + product_question → technical_issue
    - Better handling of short/ambiguous messages
    - Tighter "other" definition

    Returns:
        {
            "issue_type": str,  # Now includes "technical_issue" instead of bug_report/product_question
            "sentiment": str,
            "churn_risk": bool,
            "priority": str,
            "is_ambiguous": bool,  # NEW: flags uncertain classifications
        }
    """
    # Pre-check for very short messages
    word_count = len(text.split())

    # Call OpenAI with structured output
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_V2},
            {"role": "user", "content": f"Classify this message:\n\n{text}"},
        ],
        response_format=ClassificationResultV2,
        temperature=0,
    )

    result = response.choices[0].message.parsed

    # Post-process churn_risk
    churn_risk = result.churn_risk
    if churn_risk:
        churn_risk = _validate_churn_risk(text, churn_risk)

    # Force is_ambiguous for very short messages without clear signals
    is_ambiguous = result.is_ambiguous
    if word_count < 5:
        # Check for clear category signals
        text_lower = text.lower()
        clear_signals = [
            "error", "bug", "broken", "fail", "not working", "can't", "cannot",
            "billing", "charge", "refund", "payment", "invoice",
            "login", "password", "access", "sign in",
            "cancel", "subscription", "plan", "upgrade", "downgrade",
            "feature", "add", "would be great", "wish",
        ]
        has_signal = any(signal in text_lower for signal in clear_signals)
        if not has_signal:
            is_ambiguous = True

    return {
        "issue_type": result.issue_type,
        "sentiment": result.sentiment,
        "churn_risk": churn_risk,
        "priority": result.priority,
        "is_ambiguous": is_ambiguous,
    }


def _validate_churn_risk(text: str, llm_prediction: bool) -> bool:
    """Post-process churn_risk to handle LLM limitations."""
    import re
    text_lower = text.lower()

    # Past-tense cancellation patterns (not current churn)
    past_patterns = [
        r"i cancelled",
        r"i canceled",
        r"was cancell",
        r"subscription is cancelled",
        r"subscription was cancelled",
    ]

    # Not a customer patterns
    not_customer_patterns = [
        r"i do not use your service",
        r"i don't use your service",
        r"cannot find any account",
    ]

    # Present intent signals (true churn)
    present_intent = [
        "want to cancel",
        "how do i cancel",
        "please cancel",
        "i'd like to cancel",
        "need to cancel",
    ]

    has_past_tense = any(re.search(p, text_lower) for p in past_patterns)
    has_not_customer = any(re.search(p, text_lower) for p in not_customer_patterns)
    has_present_intent = any(p in text_lower for p in present_intent)

    if has_past_tense and not has_present_intent:
        return False

    if has_not_customer:
        return False

    return llm_prediction


def map_v2_to_v1(issue_type: str) -> str:
    """
    Map v2 categories back to v1 for comparison purposes.
    technical_issue → bug_report (most common in v1)
    """
    if issue_type == "technical_issue":
        return "bug_report"  # For comparison, map to most common original
    return issue_type


if __name__ == "__main__":
    # Quick test
    test_messages = [
        "hello",  # Should be ambiguous
        "How do I cancel my subscription?",  # billing or technical_issue
        "My pins aren't posting and I keep getting an error",  # technical_issue
        "I love Tailwind! It's saved me so much time.",  # feedback
        "smartloop scheduling",  # Should be technical_issue (short but has feature name)
        "Is it not possible to select the start date anymore?",  # technical_issue
        "operator",  # ambiguous
    ]

    for msg in test_messages:
        print(f"\nInput: {msg}")
        try:
            result = classify_conversation_v2(msg)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")
