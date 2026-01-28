"""
PM Review Prompt

LLM prompt for reviewing theme groups before story creation.
Evaluates whether conversations in a group would all be addressed by one implementation.

Owner: Kai (Prompt Engineering)
Used by: PMReviewService (Marcus - Backend)
"""

# Token budget constants for prompt formatting
# Context: PM Review prompt needs to fit within ~4K tokens for cost efficiency.
# Each conversation takes ~200-400 tokens depending on content. Limiting excerpts
# ensures we can review groups of 10-15 conversations without truncation.
MAX_KEY_EXCERPTS_IN_PROMPT = 5  # Limit key excerpts to avoid prompt bloat
MAX_EXCERPT_TEXT_LENGTH = 500  # Characters - balances context vs token cost

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
# When diagnostic_summary and key_excerpts are available, they provide richer context
# than the raw excerpt. The template uses {context_section} to insert either:
# - Smart Digest fields (preferred): diagnostic_summary + key_excerpts
# - Fallback: raw excerpt when smart digest is not available
# Resolution fields (Issue #146) are added when available.
CONVERSATION_TEMPLATE = '''### Conversation {index}
- **ID**: {conversation_id}
- **User Intent**: {user_intent}
- **Symptoms**: {symptoms}
- **Affected Flow**: {affected_flow}
- **Product Area**: {product_area}
- **Component**: {component}
{context_section}{resolution_section}'''


# Template for Smart Digest context (diagnostic_summary only)
# Key Excerpts section is added conditionally when available
SMART_DIGEST_TEMPLATE = '''- **Diagnostic Summary**: {diagnostic_summary}'''

# Template for Key Excerpts section (only included when excerpts exist)
KEY_EXCERPTS_TEMPLATE = '''- **Key Excerpts**:
{key_excerpts_formatted}'''


# Template for fallback excerpt (when smart digest is not available)
EXCERPT_TEMPLATE = '''- **Excerpt**: "{excerpt}"'''

# Template for resolution context (Issue #146)
# Only included when resolution fields are available
RESOLUTION_TEMPLATE = '''- **Root Cause**: {root_cause}
- **Resolution**: {resolution_action} ({resolution_category})
- **Solution Given**: {solution_provided}'''


def _format_key_excerpts(key_excerpts: list[dict]) -> str:
    """
    Format key_excerpts list for display in prompt.

    Args:
        key_excerpts: List of dicts with 'text' and 'relevance' keys

    Returns:
        Formatted string with each excerpt and its relevance,
        or None if no excerpts (caller should omit section entirely)
    """
    if not key_excerpts:
        return None  # Signal to caller to omit Key Excerpts section

    lines = []
    for i, excerpt in enumerate(key_excerpts[:MAX_KEY_EXCERPTS_IN_PROMPT], 1):
        text = excerpt.get("text", "")[:MAX_EXCERPT_TEXT_LENGTH]
        relevance = excerpt.get("relevance", "")
        if relevance:
            lines.append(f'  {i}. "{text}" - *{relevance}*')
        else:
            lines.append(f'  {i}. "{text}"')
    return "\n".join(lines)


def _format_resolution_section(conv: dict) -> str:
    """
    Format resolution context section for a conversation.

    Args:
        conv: Conversation dict with optional resolution fields:
            - root_cause, resolution_action, resolution_category, solution_provided

    Returns:
        Formatted resolution section string, or empty string if no resolution data
    """
    # Issue #146: Add resolution context when available
    root_cause = conv.get("root_cause", "")
    resolution_action = conv.get("resolution_action", "")
    resolution_category = conv.get("resolution_category", "")
    solution_provided = conv.get("solution_provided", "")

    # Only include resolution section if at least one field has content
    if not any([root_cause, resolution_action, solution_provided]):
        return ""

    return "\n" + RESOLUTION_TEMPLATE.format(
        root_cause=root_cause or "N/A",
        resolution_action=resolution_action or "N/A",
        resolution_category=resolution_category or "N/A",
        solution_provided=solution_provided or "N/A",
    )


def format_conversations_for_review(conversations: list[dict]) -> str:
    """
    Format a list of conversation contexts for the PM review prompt.

    Uses Smart Digest fields (diagnostic_summary, key_excerpts) when available,
    falling back to raw excerpt for older data without smart digest.
    Resolution fields (Issue #146) are included when available.

    Args:
        conversations: List of dicts with keys:
            - conversation_id, user_intent, symptoms, affected_flow,
              product_area, component
            - Smart Digest (preferred): diagnostic_summary, key_excerpts
            - Fallback: excerpt
            - Resolution (Issue #146): root_cause, resolution_action,
              resolution_category, solution_provided

    Returns:
        Formatted string for inclusion in PM_REVIEW_PROMPT
    """
    formatted = []
    for i, conv in enumerate(conversations, 1):
        symptoms_str = ", ".join(conv.get("symptoms", [])) if conv.get("symptoms") else "N/A"

        # Build context section: prefer Smart Digest, fall back to excerpt
        diagnostic_summary = conv.get("diagnostic_summary", "")
        key_excerpts = conv.get("key_excerpts", [])

        if diagnostic_summary:
            # Smart Digest available - use richer context
            context_section = SMART_DIGEST_TEMPLATE.format(
                diagnostic_summary=diagnostic_summary,
            )
            # Only add Key Excerpts section if excerpts exist (avoid confusing LLM with empty section)
            key_excerpts_formatted = _format_key_excerpts(key_excerpts)
            if key_excerpts_formatted:
                context_section += "\n" + KEY_EXCERPTS_TEMPLATE.format(
                    key_excerpts_formatted=key_excerpts_formatted,
                )
        else:
            # Fallback: use raw excerpt (for older data without smart digest)
            excerpt = conv.get("excerpt", "")[:MAX_EXCERPT_TEXT_LENGTH]
            context_section = EXCERPT_TEMPLATE.format(excerpt=excerpt)

        # Build resolution section (Issue #146)
        resolution_section = _format_resolution_section(conv)

        formatted.append(CONVERSATION_TEMPLATE.format(
            index=i,
            conversation_id=conv.get("conversation_id", "unknown"),
            user_intent=conv.get("user_intent", "N/A"),
            symptoms=symptoms_str,
            affected_flow=conv.get("affected_flow", "N/A"),
            product_area=conv.get("product_area", "N/A"),
            component=conv.get("component", "N/A"),
            context_section=context_section,
            resolution_section=resolution_section,
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
