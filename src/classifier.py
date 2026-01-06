"""
Conversation classifier using OpenAI.

Classifies Intercom conversations into:
- issue_type: bug_report, feature_request, product_question, plan_question,
              marketing_question, billing, account_access, feedback, other
- sentiment: frustrated, neutral, satisfied
- churn_risk: boolean
- priority: urgent, high, normal, low
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


class ClassificationResult(BaseModel):
    """Structured output from classifier."""

    issue_type: str = Field(
        description="Primary issue category",
        enum=[
            "bug_report",
            "feature_request",
            "product_question",
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
        description="True if customer shows signs of leaving (cancellation, refund request, frustration)",
    )
    priority: str = Field(
        description="Urgency level",
        enum=["urgent", "high", "normal", "low"],
    )


SYSTEM_PROMPT = """You are a customer support classifier for Tailwind, a social media scheduling tool.

Analyze the customer message and classify it according to:

## Issue Type (pick ONE):
- bug_report: Something is broken, error messages, features not working as expected
- feature_request: Customer wants new capability or enhancement ("would be great if", "please add")
- product_question: "How do I use feature X?" - general usage questions about Tailwind features
- plan_question: Questions about subscription/plan LIMITS and what's INCLUDED - "how many accounts can I connect?", "what's in Pro vs Max?", removing/adding accounts related to plan limits
- marketing_question: Social media strategy, Pinterest/Instagram growth, best posting times, hashtags. Includes platform-specific issues (Pinterest suspension) that aren't Tailwind bugs.
- billing: Payment issues, refunds, subscription changes, unexpected charges
- account_access: Tailwind login problems, Tailwind password reset, Tailwind permissions (NOT platform issues like Pinterest suspension)
- feedback: Meta-feedback about the product or support experience, praise, general complaints about the service without a specific request
- other: Truly unclassifiable, spam, or completely off-topic

## Sentiment (focus on EMOTIONAL TONE, not problem severity):
- frustrated: Explicit emotion words ("annoying", "terrible", "ridiculous", "unacceptable"), ALL CAPS, exclamation marks showing anger, "I'm so frustrated", profanity
- neutral: Matter-of-fact tone, polite problem descriptions, straightforward questions - even if describing a serious issue. "I keep getting charged" stated calmly is neutral.
- satisfied: Explicit positive emotion ("love", "great", "thank you so much", "you're awesome")

IMPORTANT: Describing a problem does NOT mean frustrated. Judge by HOW they say it, not WHAT the problem is.

## Churn Risk:
CRITICAL: Only set churn_risk=true for CURRENT/FUTURE cancellation intent.

churn_risk = true ONLY if:
- Present/future intent: "I want to cancel", "how do I cancel", "please cancel"
- Explicitly leaving: "won't be using anymore", "switching to [competitor]"

churn_risk = false if:
- PAST TENSE "cancelled": "I cancelled on [date]", "I cancelled my plan last month" → they already left, now just asking billing questions
- Downgrade requests: "accidental upgrade, please downgrade" → staying as customer
- Refund without leaving: wants money back but not cancelling
- General billing questions about charges

VERB TENSE MATTERS:
- "I WANT to cancel" = present intent = TRUE
- "I CANCELLED" = past action = FALSE

## Priority:
- urgent: Complete account lockout, payment system failure affecting multiple transactions
- high: ONLY if customer explicitly says they cannot do their job/work due to this issue
- normal: Almost everything else - bugs, billing, questions, frustration, refunds, feature requests
- low: Pure positive feedback with no request

DEFAULT to "normal". Being frustrated does NOT mean high priority. Feature requests are "normal" not "low".

Respond with JSON only."""


def load_few_shot_examples(n_per_type: int = 2) -> str:
    """Load examples from labeled fixtures for few-shot prompting."""
    if not FIXTURES_FILE.exists():
        return ""

    with open(FIXTURES_FILE) as f:
        fixtures = json.load(f)["labeled"]

    # Group by issue type and take n examples per type
    by_type = {}
    for f in fixtures:
        t = f["issue_type"]
        if t not in by_type:
            by_type[t] = []
        if len(by_type[t]) < n_per_type:
            by_type[t].append(f)

    # Also include explicit churn risk examples (both positive and negative)
    churn_true = [f for f in fixtures if f.get("churn_risk", False)][:2]
    churn_false_with_cancel = [
        f for f in fixtures
        if not f.get("churn_risk", False)
        and ("cancel" in f["input_text"].lower() or "refund" in f["input_text"].lower())
    ][:2]

    # Format as examples
    examples = []
    for issue_type, samples in by_type.items():
        for s in samples:
            example = {
                "input": s["input_text"][:200],  # Truncate long examples
                "output": {
                    "issue_type": s["issue_type"],
                    "sentiment": s["sentiment"],
                    "churn_risk": s.get("churn_risk", False),
                    "priority": s["priority"],
                },
            }
            examples.append(example)

    # Add explicit churn examples
    for s in churn_true + churn_false_with_cancel:
        example = {
            "input": s["input_text"][:200],
            "output": {
                "issue_type": s["issue_type"],
                "sentiment": s["sentiment"],
                "churn_risk": s.get("churn_risk", False),
                "priority": s["priority"],
            },
        }
        if example not in examples:
            examples.append(example)

    if not examples:
        return ""

    return "\n\nHere are some examples:\n" + "\n".join(
        f"Input: {e['input']}\nOutput: {json.dumps(e['output'])}"
        for e in examples[:12]  # Limit to avoid token overflow
    )


def classify_conversation(text: str, use_examples: bool = True) -> dict:
    """
    Classify a customer conversation.

    Args:
        text: The customer message text
        use_examples: Whether to include few-shot examples

    Returns:
        {
            "issue_type": str,
            "sentiment": str,
            "churn_risk": bool,
            "priority": str,
        }
    """
    # Build prompt
    system = SYSTEM_PROMPT
    if use_examples:
        system += load_few_shot_examples()

    # Call OpenAI with structured output
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Classify this message:\n\n{text}"},
        ],
        response_format=ClassificationResult,
        temperature=0,
    )

    result = response.choices[0].message.parsed

    # Post-process churn_risk: override for known LLM limitations
    churn_risk = result.churn_risk
    if churn_risk:
        churn_risk = _validate_churn_risk(text, churn_risk)

    return {
        "issue_type": result.issue_type,
        "sentiment": result.sentiment,
        "churn_risk": churn_risk,
        "priority": result.priority,
    }


def _validate_churn_risk(text: str, llm_prediction: bool) -> bool:
    """
    Post-process churn_risk to handle LLM limitations.

    Override to False for known non-churn patterns that the LLM misclassifies.
    """
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

    # Billing dispute patterns (not a customer)
    not_customer_patterns = [
        r"i do not use your service",
        r"i don't use your service",
        r"cannot find any account",
        r"can't find any account",
        r"don't have an account",
        r"do not have an account",
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

    # If past-tense without present intent, not churn
    if has_past_tense and not has_present_intent:
        return False

    # If claiming not a customer, not churn (billing dispute)
    if has_not_customer:
        return False

    return llm_prediction


if __name__ == "__main__":
    # Quick test
    test_messages = [
        "How do I cancel my subscription?",
        "My pins aren't posting and I keep getting an error",
        "I love Tailwind! It's saved me so much time.",
    ]

    for msg in test_messages:
        print(f"\nInput: {msg}")
        try:
            result = classify_conversation(msg)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")
