#!/usr/bin/env python3
"""
Resolution Analyzer

Detects support actions in conversation responses and maps them to conversation types.
Uses pattern matching on support messages to identify resolution signals.

Example detections:
- "I've processed your refund" → refund_processed → billing_question
- "I've created a ticket for engineering" → ticket_created → product_issue
- "Here's the help doc: [link]" → docs_link_sent → how_to_question
"""
import json
from pathlib import Path
from typing import Dict, List, Optional


class ResolutionAnalyzer:
    """Analyzes support responses to detect resolution actions."""

    def __init__(self, patterns_path: Optional[Path] = None):
        """
        Initialize the resolution analyzer.

        Args:
            patterns_path: Path to resolution patterns JSON file
        """
        if patterns_path is None:
            patterns_path = Path(__file__).parent.parent / "config" / "resolution_patterns.json"

        with open(patterns_path) as f:
            data = json.load(f)
            self.patterns = data["patterns"]
            self.version = data["version"]

    def detect_resolution_action(self, support_message: str) -> Optional[Dict[str, str]]:
        """
        Detect resolution action from a single support message.

        Args:
            support_message: Support team response text

        Returns:
            {
                "action": str,              # e.g., "refund_processed"
                "category": str,            # e.g., "billing"
                "conversation_type": str,   # e.g., "billing_question"
                "action_category": str,     # e.g., "billing_resolution"
                "matched_keyword": str      # The keyword that triggered the match
            } or None if no match
        """
        if not support_message:
            return None

        message_lower = support_message.lower()

        # Check each category and pattern
        for category, actions in self.patterns.items():
            for action_name, pattern_data in actions.items():
                # Check if any keyword matches
                for keyword in pattern_data["keywords"]:
                    if keyword.lower() in message_lower:
                        return {
                            "action": action_name,
                            "category": category,
                            "conversation_type": pattern_data["conversation_type"],
                            "action_category": pattern_data["action_category"],
                            "matched_keyword": keyword
                        }

        return None

    def analyze_conversation(
        self,
        support_messages: List[str]
    ) -> Dict[str, any]:
        """
        Analyze all support messages in a conversation.

        Args:
            support_messages: List of support team responses

        Returns:
            {
                "primary_action": dict | None,      # Most significant action detected
                "all_actions": list[dict],          # All actions detected
                "action_count": int,                # Number of actions
                "categories": list[str],            # Unique categories
                "suggested_type": str | None        # Conversation type from primary action
            }
        """
        all_actions = []

        # Detect actions in each message
        for message in support_messages:
            action = self.detect_resolution_action(message)
            if action:
                all_actions.append(action)

        # Determine primary action (first escalation, or first resolution, or first action)
        primary_action = None
        if all_actions:
            # Priority: escalation > resolution > guidance > limitation > configuration
            action_priority = {
                "escalation": 1,
                "billing_resolution": 2,
                "account_resolution": 2,
                "guidance": 3,
                "limitation": 4,
                "configuration": 5
            }

            sorted_actions = sorted(
                all_actions,
                key=lambda a: action_priority.get(a["action_category"], 999)
            )
            primary_action = sorted_actions[0]

        # Extract unique categories
        categories = list(set(action["category"] for action in all_actions))

        return {
            "primary_action": primary_action,
            "all_actions": all_actions,
            "action_count": len(all_actions),
            "categories": categories,
            "suggested_type": primary_action["conversation_type"] if primary_action else None
        }

    def get_confidence_boost(
        self,
        resolution_analysis: Dict[str, any],
        predicted_type: str
    ) -> float:
        """
        Calculate confidence boost if resolution analysis agrees with prediction.

        Args:
            resolution_analysis: Result from analyze_conversation
            predicted_type: Predicted conversation type

        Returns:
            Confidence boost (0.0 to 0.3)
        """
        if not resolution_analysis["primary_action"]:
            return 0.0

        suggested_type = resolution_analysis["suggested_type"]

        # Strong agreement: boost confidence
        if suggested_type == predicted_type:
            # Higher boost for escalations (very reliable signal)
            if resolution_analysis["primary_action"]["action_category"] == "escalation":
                return 0.3
            else:
                return 0.2

        return 0.0


def main():
    """Test the resolution analyzer on example messages."""
    analyzer = ResolutionAnalyzer()

    # Test cases
    test_messages = [
        "I've processed your refund and it should appear in 3-5 business days.",
        "I've created a ticket for our engineering team to investigate this.",
        "Here's the help doc that covers this: https://help.example.com/article",
        "This feature isn't currently available, but it's on our roadmap.",
        "I've cleared your session - please try logging in again.",
        "No action - just a regular message."
    ]

    print("Resolution Analyzer Test\n")
    print("=" * 60)

    for i, message in enumerate(test_messages, 1):
        print(f"\n{i}. Message: {message[:60]}...")
        result = analyzer.detect_resolution_action(message)
        if result:
            print(f"   ✓ Detected: {result['action']} → {result['conversation_type']}")
            print(f"   Category: {result['category']} ({result['action_category']})")
            print(f"   Matched: '{result['matched_keyword']}'")
        else:
            print("   ✗ No action detected")

    # Test conversation analysis
    print("\n" + "=" * 60)
    print("\nConversation Analysis Test\n")

    conversation_messages = [
        "Thanks for reaching out! Let me look into this for you.",
        "I see the issue - this is a known bug that we're working on.",
        "I've created a ticket for engineering to investigate.",
        "In the meantime, here's a workaround you can try..."
    ]

    analysis = analyzer.analyze_conversation(conversation_messages)
    print(f"Messages analyzed: {len(conversation_messages)}")
    print(f"Actions detected: {analysis['action_count']}")
    print(f"Primary action: {analysis['primary_action']['action'] if analysis['primary_action'] else 'None'}")
    print(f"Suggested type: {analysis['suggested_type']}")
    print(f"Categories: {', '.join(analysis['categories'])}")


if __name__ == "__main__":
    main()
