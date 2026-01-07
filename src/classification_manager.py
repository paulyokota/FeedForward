#!/usr/bin/env python3
"""
Classification Manager

Orchestrates the complete two-stage classification system:
1. Stage 1: Quick routing (customer-only, fast)
2. Stage 2: Refined analysis (full context, accurate)
3. Resolution analysis (detect support actions)
4. Knowledge extraction (continuous learning)

This is the main entry point for conversation classification.
"""
from typing import Dict, List, Optional
from pathlib import Path

from classifier_stage1 import classify_stage1
from classifier_stage2 import classify_stage2, should_update_classification
from resolution_analyzer import ResolutionAnalyzer
from knowledge_extractor import KnowledgeExtractor


class ClassificationManager:
    """Manages the complete two-stage classification workflow."""

    def __init__(
        self,
        patterns_path: Optional[Path] = None
    ):
        """
        Initialize the classification manager.

        Args:
            patterns_path: Optional path to resolution patterns JSON
        """
        self.resolution_analyzer = ResolutionAnalyzer(patterns_path)
        self.knowledge_extractor = KnowledgeExtractor()

    def classify_new_conversation(
        self,
        customer_message: str,
        source_url: Optional[str] = None,
        source_type: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Stage 1: Quick classification for routing (customer message only).

        Use this when a conversation first arrives and needs immediate routing.

        Args:
            customer_message: The customer's initial message
            source_url: Optional source URL for context
            source_type: Optional source type (email, chat, etc.)

        Returns:
            {
                "stage": 1,
                "conversation_type": str,
                "confidence": str,
                "routing_priority": str,
                "auto_response_eligible": bool,
                "routing_team": str,
                "url_context": str | None
            }
        """
        # Run Stage 1 classification
        stage1_result = classify_stage1(
            customer_message,
            source_url=source_url,
            source_type=source_type
        )

        # Add routing information
        from classifier_stage1 import get_routing_team
        stage1_result["routing_team"] = get_routing_team(stage1_result["conversation_type"])

        return stage1_result

    def refine_with_support_context(
        self,
        customer_message: str,
        support_messages: List[str],
        stage1_result: Dict[str, any],
        source_url: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Stage 2: Refined classification with full conversation context.

        Use this after support has responded to get accurate classification
        and extract knowledge for continuous learning.

        Args:
            customer_message: The customer's initial message
            support_messages: List of support team responses
            stage1_result: Result from Stage 1 classification
            source_url: Optional source URL for context

        Returns:
            {
                "stage": 2,
                "conversation_type": str,
                "confidence": str,
                "changed_from_stage_1": bool,
                "stage1_type": str,
                "resolution_analysis": dict,
                "knowledge": dict,
                "update_recommended": bool
            }
        """
        # Analyze resolution actions
        resolution_analysis = self.resolution_analyzer.analyze_conversation(support_messages)

        # Run Stage 2 classification with resolution signal
        stage2_result = classify_stage2(
            customer_message,
            support_messages,
            resolution_signal=resolution_analysis.get("primary_action"),
            source_url=source_url
        )

        # Check if classification should be updated
        update_recommended = should_update_classification(stage1_result, stage2_result)

        # Extract knowledge for continuous learning
        knowledge = self.knowledge_extractor.extract_from_conversation(
            customer_message,
            support_messages,
            stage2_result["conversation_type"]
        )

        return {
            "stage": 2,
            "conversation_type": stage2_result["conversation_type"],
            "confidence": stage2_result["confidence"],
            "changed_from_stage_1": stage2_result["changed_from_stage_1"],
            "stage1_type": stage1_result["conversation_type"],
            "disambiguation_level": stage2_result.get("disambiguation_level"),
            "resolution_analysis": resolution_analysis,
            "knowledge": knowledge,
            "update_recommended": update_recommended
        }

    def classify_complete_conversation(
        self,
        customer_message: str,
        support_messages: List[str],
        source_url: Optional[str] = None,
        source_type: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Run complete two-stage classification workflow.

        Use this for batch processing of closed conversations.

        Args:
            customer_message: The customer's initial message
            support_messages: List of support team responses
            source_url: Optional source URL for context
            source_type: Optional source type (email, chat, etc.)

        Returns:
            {
                "stage1": dict,  # Stage 1 results
                "stage2": dict,  # Stage 2 results
                "final_type": str,
                "classification_updated": bool
            }
        """
        # Stage 1: Initial classification
        stage1_result = self.classify_new_conversation(
            customer_message,
            source_url=source_url,
            source_type=source_type
        )

        # Stage 2: Refined with support context (if support responded)
        if support_messages:
            stage2_result = self.refine_with_support_context(
                customer_message,
                support_messages,
                stage1_result,
                source_url=source_url
            )

            final_type = (
                stage2_result["conversation_type"]
                if stage2_result["update_recommended"]
                else stage1_result["conversation_type"]
            )

            return {
                "stage1": stage1_result,
                "stage2": stage2_result,
                "final_type": final_type,
                "classification_updated": stage2_result["update_recommended"]
            }
        else:
            # No support response yet - use Stage 1 only
            return {
                "stage1": stage1_result,
                "stage2": None,
                "final_type": stage1_result["conversation_type"],
                "classification_updated": False
            }


def main():
    """Test the classification manager."""
    manager = ClassificationManager()

    print("=" * 60)
    print("Classification Manager Test\n")

    # Test case 1: New conversation (Stage 1 only)
    print("Test 1: New Conversation (Stage 1)\n")

    customer_msg = "I need help with my account"
    stage1 = manager.classify_new_conversation(
        customer_msg,
        source_type="email"
    )

    print(f"Customer: {customer_msg}")
    print(f"Stage 1 Type: {stage1['conversation_type']}")
    print(f"Confidence: {stage1['confidence']}")
    print(f"Routing: {stage1['routing_team']}")
    print(f"Priority: {stage1['routing_priority']}")

    # Test case 2: Complete conversation (both stages)
    print("\n" + "=" * 60)
    print("Test 2: Complete Conversation (Both Stages)\n")

    customer_msg = "I need help with my account"
    support_msgs = [
        "I'm sorry you're looking to cancel your subscription. Could you share why?",
        "I've gone ahead and initialized that cancellation for you. You won't be charged again."
    ]

    result = manager.classify_complete_conversation(
        customer_msg,
        support_msgs,
        source_type="email"
    )

    print(f"Customer: {customer_msg}")
    print(f"\nStage 1:")
    print(f"  Type: {result['stage1']['conversation_type']}")
    print(f"  Confidence: {result['stage1']['confidence']}")

    if result['stage2']:
        print(f"\nStage 2:")
        print(f"  Type: {result['stage2']['conversation_type']}")
        print(f"  Confidence: {result['stage2']['confidence']}")
        print(f"  Changed: {result['stage2']['changed_from_stage_1']}")

        if result['stage2']['resolution_analysis']['primary_action']:
            action = result['stage2']['resolution_analysis']['primary_action']
            print(f"  Resolution: {action['action']} ({action['category']})")

        knowledge = result['stage2']['knowledge']
        print(f"  Root cause: {knowledge.get('root_cause')}")
        print(f"  Solution: {knowledge.get('solution_provided')}")
        print(f"  Self-service gap: {knowledge.get('self_service_gap')}")

    print(f"\nFinal Type: {result['final_type']}")
    print(f"Updated from Stage 1: {result['classification_updated']}")


if __name__ == "__main__":
    main()
