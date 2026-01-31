"""
Implementation Context Synthesis Prompt

Generates actionable implementation guidance from:
- Story summary (title, symptoms, product_area)
- Retrieved similar candidates (prior stories, orphans, evidence)

Issue: #180
"""

from typing import Any, Dict, List


IMPLEMENTATION_CONTEXT_SYSTEM_PROMPT = """You are a senior software engineer helping developers understand how to implement a bug fix or feature.

Given:
1. A story summary describing the issue
2. Similar prior stories and research evidence from the knowledge base

Generate implementation guidance that is:
- Actionable: Specific next steps developers can follow
- Grounded: Based on patterns from prior art when available
- Concise: Summary in 2-3 sentences, 3-5 next steps

Output ONLY valid JSON with this exact structure (no markdown, no explanation):
{
    "summary": "2-3 sentence implementation summary",
    "relevant_files": [
        {"path": "file/path.ts", "rationale": "why relevant", "priority": "high|medium|low"}
    ],
    "next_steps": [
        "Step 1: ...",
        "Step 2: ..."
    ],
    "prior_art_references": [
        "Brief description of relevant prior story and how it helps"
    ]
}

Guidelines:
- For relevant_files: Only include files you are confident exist based on the evidence. If unsure, leave empty.
- For next_steps: Be specific and actionable. Start each step with a verb.
- For prior_art_references: Reference the most relevant prior stories/docs that informed your guidance.
- If the candidates don't provide useful prior art, say so honestly in the summary and focus on general best practices.
"""


def build_implementation_context_prompt(
    story_title: str,
    product_area: str,
    symptoms: List[str],
    candidates: List[Dict[str, Any]],
) -> str:
    """
    Build user prompt for implementation context synthesis.

    Args:
        story_title: The story title
        product_area: The product area (e.g., "scheduling", "billing")
        symptoms: List of symptoms/issues
        candidates: Retrieved candidates with title, snippet, similarity

    Returns:
        Formatted user prompt
    """
    # Build story summary section
    story_section = f"## Story to Implement\n\n**Title:** {story_title}\n"

    if product_area:
        story_section += f"**Product Area:** {product_area}\n"

    if symptoms:
        symptoms_text = "\n".join(f"- {s}" for s in symptoms[:5])
        story_section += f"\n**Symptoms:**\n{symptoms_text}\n"

    # Build candidates section
    if candidates:
        candidates_section = "\n## Prior Art (from knowledge base)\n\n"
        for i, candidate in enumerate(candidates[:10], 1):  # Limit to 10
            title = candidate.get("title", "Untitled")
            snippet = candidate.get("snippet", "")[:400]  # Limit snippet length
            similarity = candidate.get("similarity", 0)
            source_type = candidate.get("metadata", {}).get("source_type", "unknown")

            candidates_section += (
                f"### {i}. {title}\n"
                f"**Source:** {source_type} (similarity: {similarity:.2f})\n"
                f"**Content:** {snippet}\n\n"
            )
    else:
        candidates_section = (
            "\n## Prior Art\n\n"
            "No similar prior stories or documentation found in the knowledge base.\n"
        )

    # Combine sections
    prompt = f"""{story_section}
{candidates_section}
---

Based on the story and available prior art, generate implementation guidance as JSON.
"""

    return prompt
