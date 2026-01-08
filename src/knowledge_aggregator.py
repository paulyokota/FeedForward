#!/usr/bin/env python3
"""
Knowledge Aggregator

Aggregates knowledge extracted from multiple conversations to:
- Build theme knowledge base (root causes, solutions, frequency)
- Detect theme relationships (co-occurrence patterns)
- Identify emerging patterns (new themes)
- Track terminology evolution
- Flag self-service gaps

Processes batch of conversations and outputs aggregated insights.
"""
from collections import defaultdict, Counter
from typing import Dict, List, Set
from datetime import datetime


class KnowledgeAggregator:
    """Aggregates knowledge from multiple conversation extractions."""

    def __init__(self):
        """Initialize the knowledge aggregator."""
        self.theme_knowledge = defaultdict(lambda: {
            "root_causes": Counter(),
            "solutions": Counter(),
            "product_mentions": Counter(),
            "feature_mentions": Counter(),
            "customer_terminology": Counter(),
            "support_terminology": Counter(),
            "self_service_gaps": [],
            "conversation_count": 0
        })

        self.theme_cooccurrence = defaultdict(Counter)

    def add_conversation_knowledge(
        self,
        knowledge: Dict[str, any],
        themes: List[str]
    ) -> None:
        """
        Add knowledge from a single conversation.

        Args:
            knowledge: Extracted knowledge from knowledge_extractor
            themes: List of themes detected in the conversation
        """
        conversation_type = knowledge["conversation_type"]

        # Update theme-specific knowledge
        for theme in themes:
            self.theme_knowledge[theme]["conversation_count"] += 1

            # Root causes
            if knowledge.get("root_cause"):
                self.theme_knowledge[theme]["root_causes"][knowledge["root_cause"]] += 1

            # Solutions
            if knowledge.get("solution_provided"):
                self.theme_knowledge[theme]["solutions"][knowledge["solution_provided"]] += 1

            # Product mentions
            for product in knowledge.get("product_mentions", []):
                self.theme_knowledge[theme]["product_mentions"][product] += 1

            # Feature mentions
            for feature in knowledge.get("feature_mentions", []):
                self.theme_knowledge[theme]["feature_mentions"][feature] += 1

            # Terminology
            for term in knowledge.get("customer_terminology", []):
                self.theme_knowledge[theme]["customer_terminology"][term] += 1

            for term in knowledge.get("support_terminology", []):
                self.theme_knowledge[theme]["support_terminology"][term] += 1

            # Self-service gaps
            if knowledge.get("self_service_gap"):
                self.theme_knowledge[theme]["self_service_gaps"].append({
                    "evidence": knowledge.get("gap_evidence"),
                    "conversation_type": conversation_type
                })

        # Track theme co-occurrence
        if len(themes) > 1:
            themes_sorted = sorted(themes)
            for i, theme_a in enumerate(themes_sorted):
                for theme_b in themes_sorted[i+1:]:
                    self.theme_cooccurrence[theme_a][theme_b] += 1
                    self.theme_cooccurrence[theme_b][theme_a] += 1

    def get_theme_summary(self, theme: str, min_frequency: int = 2) -> Dict[str, any]:
        """
        Get aggregated knowledge summary for a theme.

        Args:
            theme: Theme ID
            min_frequency: Minimum frequency to include items

        Returns:
            {
                "theme_id": str,
                "conversation_count": int,
                "top_root_causes": list[tuple[str, int]],
                "top_solutions": list[tuple[str, int]],
                "product_mentions": dict[str, int],
                "feature_mentions": dict[str, int],
                "top_customer_terms": list[tuple[str, int]],
                "top_support_terms": list[tuple[str, int]],
                "self_service_gap_count": int,
                "related_themes": list[tuple[str, int]]
            }
        """
        if theme not in self.theme_knowledge:
            return None

        data = self.theme_knowledge[theme]

        # Filter by minimum frequency
        top_root_causes = [
            (cause, count) for cause, count in data["root_causes"].most_common(5)
            if count >= min_frequency
        ]

        top_solutions = [
            (solution, count) for solution, count in data["solutions"].most_common(5)
            if count >= min_frequency
        ]

        top_customer_terms = [
            (term, count) for term, count in data["customer_terminology"].most_common(10)
            if count >= min_frequency
        ]

        top_support_terms = [
            (term, count) for term, count in data["support_terminology"].most_common(10)
            if count >= min_frequency
        ]

        # Related themes (co-occurring themes)
        related = []
        if theme in self.theme_cooccurrence:
            related = self.theme_cooccurrence[theme].most_common(5)

        return {
            "theme_id": theme,
            "conversation_count": data["conversation_count"],
            "top_root_causes": top_root_causes,
            "top_solutions": top_solutions,
            "product_mentions": dict(data["product_mentions"]),
            "feature_mentions": dict(data["feature_mentions"]),
            "top_customer_terms": top_customer_terms,
            "top_support_terms": top_support_terms,
            "self_service_gap_count": len(data["self_service_gaps"]),
            "self_service_gaps": data["self_service_gaps"][:3],  # Top 3 examples
            "related_themes": related
        }

    def get_all_summaries(self, min_conversations: int = 2) -> Dict[str, Dict]:
        """
        Get summaries for all themes with minimum conversation count.

        Args:
            min_conversations: Minimum number of conversations to include theme

        Returns:
            Dictionary of theme_id -> summary
        """
        summaries = {}

        for theme in self.theme_knowledge:
            if self.theme_knowledge[theme]["conversation_count"] >= min_conversations:
                summaries[theme] = self.get_theme_summary(theme)

        return summaries

    def detect_emerging_patterns(
        self,
        frequency_threshold: int = 5
    ) -> List[Dict[str, any]]:
        """
        Detect emerging patterns that might warrant new themes.

        Args:
            frequency_threshold: Minimum frequency to consider a pattern

        Returns:
            List of potential new themes with evidence
        """
        # Aggregate all root causes across all themes
        all_root_causes = Counter()
        all_solutions = Counter()

        for theme_data in self.theme_knowledge.values():
            all_root_causes.update(theme_data["root_causes"])
            all_solutions.update(theme_data["solutions"])

        emerging = []

        # Root causes that appear frequently
        for cause, count in all_root_causes.most_common(20):
            if count >= frequency_threshold:
                emerging.append({
                    "type": "root_cause",
                    "pattern": cause,
                    "frequency": count,
                    "recommendation": "Consider creating theme if not already covered"
                })

        # Solutions that appear frequently
        for solution, count in all_solutions.most_common(20):
            if count >= frequency_threshold:
                emerging.append({
                    "type": "solution",
                    "pattern": solution,
                    "frequency": count,
                    "recommendation": "Common solution - check if theme exists"
                })

        return emerging

    def get_self_service_opportunities(self) -> List[Dict[str, any]]:
        """
        Get prioritized list of self-service opportunities.

        Returns:
            List of opportunities sorted by frequency
        """
        opportunities = []

        for theme, data in self.theme_knowledge.items():
            gap_count = len(data["self_service_gaps"])
            if gap_count > 0:
                # Get most common evidence
                evidence_counts = Counter(
                    gap["evidence"] for gap in data["self_service_gaps"]
                    if gap.get("evidence")
                )

                opportunities.append({
                    "theme": theme,
                    "gap_count": gap_count,
                    "conversation_count": data["conversation_count"],
                    "impact_percentage": (gap_count / data["conversation_count"]) * 100,
                    "common_evidence": evidence_counts.most_common(3),
                    "examples": data["self_service_gaps"][:3]
                })

        # Sort by gap count (most impactful first)
        opportunities.sort(key=lambda x: x["gap_count"], reverse=True)

        return opportunities

    def generate_vocabulary_updates(
        self,
        min_term_frequency: int = 3
    ) -> Dict[str, List[str]]:
        """
        Generate keyword suggestions for vocabulary updates.

        Args:
            min_term_frequency: Minimum frequency for term to be suggested

        Returns:
            Dictionary of theme_id -> suggested keywords
        """
        suggestions = {}

        for theme, data in self.theme_knowledge.items():
            keywords = []

            # Customer terminology (how users describe issues)
            for term, count in data["customer_terminology"].most_common(10):
                if count >= min_term_frequency:
                    keywords.append(term)

            # Support terminology (precise technical terms)
            for term, count in data["support_terminology"].most_common(10):
                if count >= min_term_frequency:
                    keywords.append(term)

            if keywords:
                suggestions[theme] = list(set(keywords))  # Deduplicate

        return suggestions


def main():
    """Test the knowledge aggregator."""
    aggregator = KnowledgeAggregator()

    # Simulate adding knowledge from multiple conversations
    print("=" * 60)
    print("Knowledge Aggregator Test\n")

    # Conversation 1: Billing cancellation
    knowledge1 = {
        "conversation_type": "billing_question",
        "root_cause": "Customer wants to cancel subscription",
        "solution_provided": "Support cancelled subscription and reverted to free plan",
        "product_mentions": ["Pro plan"],
        "feature_mentions": ["subscription", "billing"],
        "customer_terminology": ["cancel account", "stop paying"],
        "support_terminology": ["cancel subscription", "free plan"],
        "self_service_gap": True,
        "gap_evidence": "Support manually cancelled subscription"
    }
    aggregator.add_conversation_knowledge(knowledge1, ["billing_cancellation_request"])

    # Conversation 2: Another billing cancellation
    knowledge2 = {
        "conversation_type": "billing_question",
        "root_cause": "Customer wants to cancel subscription",
        "solution_provided": "Support cancelled subscription",
        "product_mentions": ["Advanced plan"],
        "feature_mentions": ["subscription"],
        "customer_terminology": ["cancel my plan", "don't want"],
        "support_terminology": ["cancel subscription", "process cancellation"],
        "self_service_gap": True,
        "gap_evidence": "Support manually cancelled subscription"
    }
    aggregator.add_conversation_knowledge(knowledge2, ["billing_cancellation_request"])

    # Conversation 3: Product issue
    knowledge3 = {
        "conversation_type": "product_issue",
        "root_cause": "Downtime experienced by the service",
        "solution_provided": "Try signing up again now that issue is resolved",
        "product_mentions": ["Tailwind"],
        "feature_mentions": ["signup"],
        "customer_terminology": ["signup broken", "can't register"],
        "support_terminology": ["sign up", "service downtime"],
        "self_service_gap": False,
        "gap_evidence": None
    }
    aggregator.add_conversation_knowledge(knowledge3, ["service_downtime_signup"])

    # Get summaries
    print("Theme Summaries:\n")

    for theme_id, summary in aggregator.get_all_summaries(min_conversations=1).items():
        print(f"\n{theme_id}:")
        print(f"  Conversations: {summary['conversation_count']}")
        print(f"  Top root causes: {summary['top_root_causes']}")
        print(f"  Top solutions: {summary['top_solutions']}")
        print(f"  Self-service gaps: {summary['self_service_gap_count']}")

    # Self-service opportunities
    print("\n" + "=" * 60)
    print("Self-Service Opportunities:\n")

    for opp in aggregator.get_self_service_opportunities():
        print(f"\n{opp['theme']}:")
        print(f"  Occurrences: {opp['gap_count']} / {opp['conversation_count']} ({opp['impact_percentage']:.1f}%)")
        print(f"  Evidence: {opp['common_evidence']}")

    # Vocabulary suggestions
    print("\n" + "=" * 60)
    print("Vocabulary Update Suggestions:\n")

    for theme, keywords in aggregator.generate_vocabulary_updates(min_term_frequency=1).items():
        print(f"\n{theme}:")
        print(f"  Suggested keywords: {', '.join(keywords)}")


if __name__ == "__main__":
    main()
