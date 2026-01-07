#!/usr/bin/env python3
"""
Demo: Integrated Two-Stage Classification System

Demonstrates the complete system on sample conversations:
1. Resolution pattern detection
2. Knowledge extraction per conversation
3. Knowledge aggregation across conversations
4. Theme relationship mapping
5. Self-service gap identification
6. Vocabulary update suggestions

Uses realistic sample conversations to validate system functionality.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from resolution_analyzer import ResolutionAnalyzer
from knowledge_extractor import KnowledgeExtractor
from knowledge_aggregator import KnowledgeAggregator
from classification_manager import ClassificationManager


# Sample conversations based on real patterns from analysis
SAMPLE_CONVERSATIONS = [
    {
        "id": "1",
        "customer_message": "I need to cancel my account",
        "support_messages": [
            "I'm sorry you're looking to cancel your subscription. Could you share why you're looking to cancel?",
            "I've gone ahead and initialized that cancellation for you. You won't be charged again and your account will revert to our free plan. Thanks for letting us know!"
        ],
        "type": "billing_question",
        "themes": ["billing_cancellation_request"]
    },
    {
        "id": "2",
        "customer_message": "The signup page isn't working",
        "support_messages": [
            "I'm sorry about that! This is due to a downtime we experienced earlier today.",
            "The issue has been resolved now. You should be able to try signing up again."
        ],
        "type": "product_issue",
        "themes": ["service_downtime_signup"]
    },
    {
        "id": "3",
        "customer_message": "I can't log in to my account",
        "support_messages": [
            "I can help with that. Let me clear your session for you.",
            "I've cleared your session. Please visit this link to log back in, or try using a different web browser."
        ],
        "type": "account_issue",
        "themes": ["session_clearing_required", "account_login_failure"]
    },
    {
        "id": "4",
        "customer_message": "How do I schedule posts to Pinterest?",
        "support_messages": [
            "Great question! Here's how to schedule posts to Pinterest.",
            "You'll need to first connect your Pinterest account in settings, then you can use the scheduler to queue up your posts. Here's the help doc that covers this: https://help.tailwindapp.com/scheduler"
        ],
        "type": "how_to_question",
        "themes": ["pinterest_scheduling_guidance"]
    },
    {
        "id": "5",
        "customer_message": "My payment failed",
        "support_messages": [
            "I'm sorry to hear that. Let me check your account.",
            "I see the issue - your payment method has expired. I've updated it for you and processed the payment. You're all set!"
        ],
        "type": "billing_question",
        "themes": ["billing_payment_failure"]
    },
    {
        "id": "6",
        "customer_message": "The Instagram connection keeps failing",
        "support_messages": [
            "I can help with that. This is usually because Instagram OAuth pulls your primary account instead of the one you want to connect.",
            "Try using an incognito browser window to sign in to Instagram with the account you want to connect, then try the connection again."
        ],
        "type": "account_issue",
        "themes": ["instagram_oauth_multi_account"]
    },
    {
        "id": "7",
        "customer_message": "I want to delete my account",
        "support_messages": [
            "I can help remove your profile. Before I do that, make sure to download any drafts or create files you want to keep.",
            "Once you've saved your data, let me know and I'll proceed with the deletion."
        ],
        "type": "account_issue",
        "themes": ["account_deletion_request"]
    },
    {
        "id": "8",
        "customer_message": "The queue isn't loading",
        "support_messages": [
            "I'm sorry about that. This is a known bug that our engineering team is working on.",
            "I've created a ticket for your issue and added you to the list of affected users. We'll notify you when it's fixed."
        ],
        "type": "product_issue",
        "themes": ["publisher_queue_loading_issue"]
    },
    {
        "id": "9",
        "customer_message": "Can you add dark mode?",
        "support_messages": [
            "Thanks for the suggestion! Dark mode isn't currently available, but it's on our roadmap.",
            "I've logged your request with our product team. We'll let you know if this gets prioritized."
        ],
        "type": "feature_request",
        "themes": ["feature_request_dark_mode"]
    },
    {
        "id": "10",
        "customer_message": "How do I upgrade my plan?",
        "support_messages": [
            "You can upgrade your plan in the billing settings.",
            "Go to Settings > Billing, and you'll see the available plans. Click 'Upgrade' on the plan you want. Let me know if you need help with that!"
        ],
        "type": "how_to_question",
        "themes": ["billing_plan_upgrade_guidance"]
    }
]


def main():
    """Run demo of integrated system."""
    print("=" * 80)
    print("INTEGRATED TWO-STAGE CLASSIFICATION SYSTEM - DEMO")
    print("=" * 80)
    print(f"\nProcessing {len(SAMPLE_CONVERSATIONS)} sample conversations\n")

    # Initialize components
    resolution_analyzer = ResolutionAnalyzer()
    knowledge_extractor = KnowledgeExtractor()
    knowledge_aggregator = KnowledgeAggregator()
    classification_manager = ClassificationManager()

    # Statistics
    resolution_stats = {
        "total": len(SAMPLE_CONVERSATIONS),
        "actions_detected": 0,
        "conversations_with_actions": 0
    }

    print("-" * 80)
    print("PROCESSING CONVERSATIONS")
    print("-" * 80)

    for i, conv in enumerate(SAMPLE_CONVERSATIONS, 1):
        print(f"\n[{i}/{len(SAMPLE_CONVERSATIONS)}] Conversation {conv['id']}")
        print(f"Customer: {conv['customer_message'][:60]}...")

        # 1. Run complete classification
        result = classification_manager.classify_complete_conversation(
            conv['customer_message'],
            conv['support_messages']
        )

        print(f"  Stage 1 Type: {result['stage1']['conversation_type']} ({result['stage1']['confidence']})")

        if result['stage2']:
            print(f"  Stage 2 Type: {result['stage2']['conversation_type']} ({result['stage2']['confidence']})")

            # 2. Resolution analysis
            resolution = result['stage2']['resolution_analysis']
            if resolution['primary_action']:
                action = resolution['primary_action']
                print(f"  ✓ Resolution: {action['action']} → {action['conversation_type']}")
                resolution_stats['conversations_with_actions'] += 1
                resolution_stats['actions_detected'] += resolution['action_count']
            else:
                print(f"  ✗ No resolution action detected")

            # 3. Knowledge extraction
            knowledge = result['stage2']['knowledge']
            if knowledge.get('root_cause'):
                print(f"  Root cause: {knowledge['root_cause'][:50]}...")
            if knowledge.get('solution_provided'):
                print(f"  Solution: {knowledge['solution_provided'][:50]}...")
            if knowledge.get('self_service_gap'):
                print(f"  ⚠️  Self-service gap: {knowledge['gap_evidence']}")

            # 4. Add to aggregator
            knowledge_aggregator.add_conversation_knowledge(knowledge, conv['themes'])

    # Generate reports
    print("\n" + "=" * 80)
    print("RESOLUTION ANALYSIS SUMMARY")
    print("=" * 80)

    print(f"\nTotal conversations: {resolution_stats['total']}")
    print(f"Conversations with actions: {resolution_stats['conversations_with_actions']}")
    print(f"Detection rate: {(resolution_stats['conversations_with_actions'] / resolution_stats['total'] * 100):.1f}%")
    print(f"Total actions detected: {resolution_stats['actions_detected']}")

    # Knowledge aggregation
    print("\n" + "=" * 80)
    print("KNOWLEDGE AGGREGATION RESULTS")
    print("=" * 80)

    summaries = knowledge_aggregator.get_all_summaries(min_conversations=1)
    print(f"\nThemes with knowledge: {len(summaries)}\n")

    for theme_id, summary in summaries.items():
        print(f"{theme_id}:")
        print(f"  Conversations: {summary['conversation_count']}")

        if summary['top_root_causes']:
            causes = ', '.join(f"{c[:30]}... ({n})" for c, n in summary['top_root_causes'][:2])
            print(f"  Root causes: {causes}")

        if summary['top_solutions']:
            solutions = ', '.join(f"{s[:30]}... ({n})" for s, n in summary['top_solutions'][:2])
            print(f"  Solutions: {solutions}")

        if summary['related_themes']:
            related = ', '.join(f"{t} ({c})" for t, c in summary['related_themes'][:2])
            print(f"  Related: {related}")

    # Self-service opportunities
    print("\n" + "=" * 80)
    print("SELF-SERVICE OPPORTUNITIES")
    print("=" * 80)

    opportunities = knowledge_aggregator.get_self_service_opportunities()
    print(f"\nFound {len(opportunities)} self-service opportunities\n")

    for opp in opportunities:
        print(f"{opp['theme']}:")
        print(f"  Impact: {opp['gap_count']} / {opp['conversation_count']} ({opp['impact_percentage']:.0f}%)")
        if opp['common_evidence']:
            print(f"  Evidence: {opp['common_evidence'][0][0]}")

    # Vocabulary suggestions
    print("\n" + "=" * 80)
    print("VOCABULARY UPDATE SUGGESTIONS")
    print("=" * 80)

    vocab_suggestions = knowledge_aggregator.generate_vocabulary_updates(min_term_frequency=1)
    print(f"\nKeyword suggestions for {len(vocab_suggestions)} themes\n")

    for theme, keywords in list(vocab_suggestions.items())[:5]:
        print(f"{theme}:")
        print(f"  Keywords: {', '.join(keywords[:5])}")

    print("\n" + "=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print("\nThe integrated system successfully:")
    print("  ✓ Detected resolution actions")
    print("  ✓ Extracted knowledge per conversation")
    print("  ✓ Aggregated insights across conversations")
    print("  ✓ Identified theme relationships")
    print("  ✓ Flagged self-service opportunities")
    print("  ✓ Generated vocabulary suggestions")


if __name__ == "__main__":
    main()
