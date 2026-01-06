"""
Theme extractor for identifying and canonicalizing conversation themes.

Uses product context to extract structured themes that can be aggregated,
tracked over time, and turned into actionable tickets.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from openai import OpenAI

# Handle both module and script execution
try:
    from .db.models import Conversation
except ImportError:
    from db.models import Conversation

logger = logging.getLogger(__name__)

# Load product context
PRODUCT_CONTEXT_PATH = Path(__file__).parent.parent / "context" / "product"


def load_product_context() -> str:
    """Load product documentation for context."""
    context_parts = []

    if PRODUCT_CONTEXT_PATH.exists():
        for file in PRODUCT_CONTEXT_PATH.glob("*.md"):
            content = file.read_text()
            # Truncate very long docs to avoid token limits
            if len(content) > 15000:
                content = content[:15000] + "\n\n[truncated for length]"
            context_parts.append(f"# {file.stem}\n\n{content}")

    return "\n\n---\n\n".join(context_parts)


THEME_EXTRACTION_PROMPT = """You are a product analyst for Tailwind, a social media scheduling tool focused on Pinterest, Instagram, and Facebook.

Your job is to extract a structured "theme" from a customer support conversation. Themes help us:
1. Detect when multiple customers have the same issue
2. Track trends over time
3. Create actionable tickets for engineering/product

## Product Context

{product_context}

## Theme Structure

Extract these fields:

1. **product_area**: The main product area (one of):
   - scheduling (Pin Scheduler, SmartSchedule, Pin Spacing, Multi-Network Scheduler)
   - ai_creation (SmartPin, Ghostwriter, Tailwind Create)
   - pinterest_publishing (pins, boards, Pinterest API issues)
   - instagram_publishing (posts, stories, reels)
   - facebook_publishing (pages, posts)
   - communities (Tailwind Communities)
   - analytics (keyword research, performance tracking)
   - billing (plans, credits, payments, subscriptions)
   - account (login, connections, OAuth, profile management)
   - integrations (Canva, browser extension, e-commerce)
   - other

2. **component**: The specific feature or sub-component (e.g., "smartschedule", "pin_spacing", "ghostwriter", "csv_import")

3. **issue_signature**: A canonical, lowercase, underscore-separated identifier for this specific issue type.
   This should be reusable - if another customer has the same issue, they should get the same signature.
   Examples: "pins_not_publishing_to_board", "smartschedule_times_not_optimal", "ai_credits_exhausted"

4. **user_intent**: What the user was trying to accomplish (in plain English)

5. **symptoms**: List of observable symptoms the user described (2-4 items)

6. **affected_flow**: The user journey or flow that's broken (e.g., "Pin Scheduler → Pinterest API")

7. **root_cause_hypothesis**: Your best guess at the technical root cause based on product knowledge

## Conversation

Issue Type: {issue_type}
Sentiment: {sentiment}
Priority: {priority}
Churn Risk: {churn_risk}

Message:
{source_body}

## Instructions

1. Use your product knowledge to map user language to actual features
2. Create issue_signatures that would match across similar reports
3. Be specific in symptoms - these help engineers reproduce
4. If unsure about a field, make your best inference

Respond with valid JSON only:
"""


@dataclass
class Theme:
    """Extracted theme from a conversation."""

    conversation_id: str
    product_area: str
    component: str
    issue_signature: str
    user_intent: str
    symptoms: list[str]
    affected_flow: str
    root_cause_hypothesis: str
    extracted_at: datetime = None

    def __post_init__(self):
        if self.extracted_at is None:
            self.extracted_at = datetime.utcnow()

    def to_dict(self) -> dict:
        d = asdict(self)
        d['extracted_at'] = self.extracted_at.isoformat()
        return d


class ThemeExtractor:
    """Extracts themes from classified conversations."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = OpenAI()
        self.model = model
        self._product_context = None

    @property
    def product_context(self) -> str:
        if self._product_context is None:
            self._product_context = load_product_context()
            logger.info(f"Loaded {len(self._product_context)} chars of product context")
        return self._product_context

    def extract(self, conv: Conversation) -> Theme:
        """Extract theme from a single conversation."""

        prompt = THEME_EXTRACTION_PROMPT.format(
            product_context=self.product_context[:10000],  # Limit context size
            issue_type=conv.issue_type,
            sentiment=conv.sentiment,
            priority=conv.priority,
            churn_risk=conv.churn_risk,
            source_body=conv.source_body or "",
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a product analyst. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        return Theme(
            conversation_id=conv.id,
            product_area=result.get("product_area", "other"),
            component=result.get("component", "unknown"),
            issue_signature=result.get("issue_signature", "unknown_issue"),
            user_intent=result.get("user_intent", ""),
            symptoms=result.get("symptoms", []),
            affected_flow=result.get("affected_flow", ""),
            root_cause_hypothesis=result.get("root_cause_hypothesis", ""),
        )

    def extract_batch(self, conversations: list[Conversation]) -> list[Theme]:
        """Extract themes from multiple conversations."""
        themes = []
        for conv in conversations:
            try:
                theme = self.extract(conv)
                themes.append(theme)
                logger.info(f"Extracted theme: {theme.issue_signature}")
            except Exception as e:
                logger.error(f"Failed to extract theme for {conv.id}: {e}")
        return themes


def format_theme_for_ticket(theme: Theme, similar_count: int = 1, sample_messages: list[str] = None) -> str:
    """Format a theme as a ticket description for human + agentic consumption."""

    samples = ""
    if sample_messages:
        samples = "\n".join(f'> "{msg[:200]}..."' for msg in sample_messages[:3])

    trend = ""
    if similar_count > 1:
        trend = f" ({similar_count} reports)"

    return f"""## {theme.issue_signature.replace('_', ' ').title()}{trend}

**Product Area:** {theme.product_area} → {theme.component}
**Affected Flow:** {theme.affected_flow}
**User Intent:** {theme.user_intent}

### Symptoms
{chr(10).join(f'- {s}' for s in theme.symptoms)}

### Root Cause Hypothesis
{theme.root_cause_hypothesis}

### Sample Customer Messages
{samples or '_No samples available_'}

### Suggested Investigation
- Review {theme.component} code for issues matching symptoms
- Check logs for errors in {theme.affected_flow} flow
- Verify API responses and error handling
"""


# Quick test
if __name__ == "__main__":
    import sys
    # Add src to path for running as script
    sys.path.insert(0, str(Path(__file__).parent))

    logging.basicConfig(level=logging.INFO)

    # Test with a sample conversation
    test_conv = Conversation(
        id="test_123",
        created_at=datetime.utcnow(),
        source_body="My pins are showing as scheduled but they never actually post to Pinterest. I've been waiting for 3 days and nothing has shown up on my boards. This is really frustrating because I have a product launch coming up.",
        issue_type="bug_report",
        sentiment="frustrated",
        churn_risk=False,
        priority="high",
    )

    extractor = ThemeExtractor()
    theme = extractor.extract(test_conv)

    print("\n" + "="*60)
    print("EXTRACTED THEME:")
    print("="*60)
    print(json.dumps(theme.to_dict(), indent=2))

    print("\n" + "="*60)
    print("FORMATTED TICKET:")
    print("="*60)
    print(format_theme_for_ticket(theme, similar_count=5, sample_messages=[test_conv.source_body]))
