"""
PM Review Prompt

LLM prompt for reviewing theme groups before story creation.
Evaluates whether conversations in a group would all be addressed by one implementation.

Owner: Kai (Prompt Engineering)
Used by: PMReviewService (Marcus - Backend)
"""

# PM Review Prompt Template
# Uses the SAME_FIX test to validate theme group coherence
PM_REVIEW_PROMPT = '''You are a PM reviewing potential product tickets for Tailwind, a social media scheduling tool.

## The SAME_FIX Test

A group of conversations should become ONE ticket if and only if:

1. **Same code change** - One PR would fix ALL of them
2. **Same developer** - One person could own the entire fix
3. **Same test** - One acceptance test would verify ALL are fixed

## Product Context

{product_context}

## Group Under Review

**Signature**: {signature}
**Conversation Count**: {count}

{conversations}

## Your Task

Answer this question: **"Would ONE implementation fix ALL of these?"**

Consider:

1. Are users experiencing the SAME symptom? (duplicates vs missing vs timeout are DIFFERENT)
2. Would a developer look at the SAME code to fix all of these?
3. Is there ONE root cause, or MULTIPLE distinct causes?

## Response Format

Respond with valid JSON only. No markdown code blocks.

{{
  "decision": "keep_together" | "split",
  "reasoning": "Brief explanation of your decision",
  "same_fix_confidence": 0.0-1.0,
  "sub_groups": [
    // Only if decision is "split"
    {{
      "suggested_signature": "more_specific_signature_name",
      "conversation_ids": ["id1", "id2"],
      "rationale": "Why these belong together",
      "symptom": "The specific symptom these share"
    }}
  ],
  "orphans": [
    // Conversations that don't fit any sub-group
    {{
      "conversation_id": "id",
      "reason": "Why this doesn't fit"
    }}
  ]
}}

Important:
- Each conversation_id MUST appear in exactly ONE place: either in ONE sub_group OR in orphans (never both, never multiple sub_groups)
- If a conversation is ambiguous and could fit multiple sub_groups, assign it to the MOST specific sub_group that fits
- If conversations have DIFFERENT symptoms (duplicates vs missing), they MUST be split
- A sub-group needs at least 3 conversations to become a ticket (others become orphans)
- Be specific in suggested signatures: `pinterest_duplicate_pins` not `pinterest_issue`
'''


# Conversation template for formatting individual conversations in the prompt
CONVERSATION_TEMPLATE = '''### Conversation {index}
- **ID**: {conversation_id}
- **User Intent**: {user_intent}
- **Symptoms**: {symptoms}
- **Affected Flow**: {affected_flow}
- **Product Area**: {product_area}
- **Component**: {component}
- **Excerpt**: "{excerpt}"
'''


def format_conversations_for_review(conversations: list[dict]) -> str:
    """
    Format a list of conversation contexts for the PM review prompt.

    Args:
        conversations: List of dicts with keys: conversation_id, user_intent,
                      symptoms, affected_flow, product_area, component, excerpt

    Returns:
        Formatted string for inclusion in PM_REVIEW_PROMPT
    """
    formatted = []
    for i, conv in enumerate(conversations, 1):
        symptoms_str = ", ".join(conv.get("symptoms", [])) if conv.get("symptoms") else "N/A"
        formatted.append(CONVERSATION_TEMPLATE.format(
            index=i,
            conversation_id=conv.get("conversation_id", "unknown"),
            user_intent=conv.get("user_intent", "N/A"),
            symptoms=symptoms_str,
            affected_flow=conv.get("affected_flow", "N/A"),
            product_area=conv.get("product_area", "N/A"),
            component=conv.get("component", "N/A"),
            excerpt=conv.get("excerpt", "")[:200],
        ))
    return "\n".join(formatted)


def build_pm_review_prompt(
    signature: str,
    conversations: list[dict],
    product_context: str = "",
) -> str:
    """
    Build the complete PM review prompt for a theme group.

    Args:
        signature: The issue_signature for this group
        conversations: List of conversation context dicts
        product_context: Optional product documentation for context

    Returns:
        Complete formatted prompt string
    """
    formatted_conversations = format_conversations_for_review(conversations)
    return PM_REVIEW_PROMPT.format(
        product_context=product_context or "Tailwind is a social media scheduling tool for Pinterest, Instagram, and Facebook.",
        signature=signature,
        count=len(conversations),
        conversations=formatted_conversations,
    )
