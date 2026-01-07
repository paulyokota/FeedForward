#!/usr/bin/env python3
"""
Knowledge Extractor

Extracts support knowledge from individual conversations:
- Root causes (why the issue happened)
- Solutions provided (how it was fixed)
- Product/feature mentions (what was discussed)
- Terminology (support vs customer language)
- Self-service gaps (manual support work that could be automated)

This feeds the continuous learning system for vocabulary improvement.
"""
import re
from typing import Dict, List, Optional, Set
from collections import Counter


class KnowledgeExtractor:
    """Extracts structured knowledge from conversation messages."""

    def __init__(self):
        """Initialize the knowledge extractor."""
        # Common product/feature indicators
        self.product_indicators = [
            r'\b(tailwind|ghost|publisher|scheduler|create|smart\.bio|analytics)\b',
            r'\b(pro plan|advanced plan|free plan|subscription|account)\b',
            r'\b(drafts?|posts?|queue|calendar|settings?)\b',
            r'\b(instagram|pinterest|facebook|twitter|linkedin|tiktok)\b'
        ]

        # Solution indicators
        self.solution_indicators = [
            r"i've (processed|sent|created|updated|cleared|reset|adjusted)",
            r"you (can|should|need to|will need to)",
            r"try (to|using|signing|clearing)",
            r"visit (this|the|our)",
            r"here's (how|what|the|a)",
            r"check out",
            r"follow these steps"
        ]

        # Root cause indicators
        self.root_cause_indicators = [
            r"(this is|it's) (because|due to|caused by)",
            r"the (issue|problem|reason) is",
            r"(unfortunately|currently|at this time)",
            r"(known bug|known issue|limitation)",
            r"(downtime|outage|service issue)"
        ]

    def extract_from_conversation(
        self,
        customer_message: str,
        support_messages: List[str],
        conversation_type: str
    ) -> Dict[str, any]:
        """
        Extract knowledge from a complete conversation.

        Args:
            customer_message: Customer's initial message
            support_messages: List of support responses
            conversation_type: Classified conversation type

        Returns:
            {
                "conversation_type": str,
                "root_cause": str | None,
                "solution_provided": str | None,
                "product_mentions": list[str],
                "feature_mentions": list[str],
                "customer_terminology": list[str],
                "support_terminology": list[str],
                "self_service_gap": bool,
                "gap_evidence": str | None
            }
        """
        # Combine all support messages for analysis
        full_support_text = " ".join(support_messages) if support_messages else ""

        # Extract components
        root_cause = self._extract_root_cause(full_support_text)
        solution = self._extract_solution(full_support_text)
        products, features = self._extract_product_mentions(full_support_text)
        customer_terms = self._extract_terminology(customer_message)
        support_terms = self._extract_terminology(full_support_text)
        gap, gap_evidence = self._detect_self_service_gap(full_support_text, conversation_type)

        return {
            "conversation_type": conversation_type,
            "root_cause": root_cause,
            "solution_provided": solution,
            "product_mentions": products,
            "feature_mentions": features,
            "customer_terminology": customer_terms,
            "support_terminology": support_terms,
            "self_service_gap": gap,
            "gap_evidence": gap_evidence
        }

    def _extract_root_cause(self, support_text: str) -> Optional[str]:
        """
        Extract root cause explanation from support response.

        Args:
            support_text: Combined support messages

        Returns:
            Root cause explanation or None
        """
        if not support_text:
            return None

        # Look for sentences containing root cause indicators
        sentences = re.split(r'[.!?]+', support_text)

        for sentence in sentences:
            for pattern in self.root_cause_indicators:
                if re.search(pattern, sentence.lower()):
                    # Return the sentence, cleaned up
                    return sentence.strip()

        # Check for specific patterns
        patterns = [
            r"(?:this is|it's) (?:because|due to) ([^.!?]+)",
            r"(?:the (?:issue|problem|reason) is) ([^.!?]+)",
            r"(?:unfortunately|currently) ([^.!?]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, support_text.lower())
            if match:
                return match.group(1).strip()

        return None

    def _extract_solution(self, support_text: str) -> Optional[str]:
        """
        Extract solution provided from support response.

        Args:
            support_text: Combined support messages

        Returns:
            Solution description or None
        """
        if not support_text:
            return None

        # Look for sentences containing solution indicators
        sentences = re.split(r'[.!?]+', support_text)

        solutions = []
        for sentence in sentences:
            for pattern in self.solution_indicators:
                if re.search(pattern, sentence.lower()):
                    solutions.append(sentence.strip())
                    break

        if solutions:
            # Return first substantive solution (at least 20 chars)
            for solution in solutions:
                if len(solution) > 20:
                    return solution

        return None

    def _extract_product_mentions(self, text: str) -> tuple[List[str], List[str]]:
        """
        Extract product and feature mentions from text.

        Args:
            text: Message text

        Returns:
            (products, features) tuple of lists
        """
        if not text:
            return [], []

        text_lower = text.lower()
        products = []
        features = []

        # Products
        if 'tailwind' in text_lower:
            products.append('Tailwind')
        if 'ghost' in text_lower or 'ghostwriter' in text_lower:
            products.append('Ghost')
        if 'smart.bio' in text_lower or 'smartbio' in text_lower:
            products.append('smart.bio')

        # Plans
        if 'pro plan' in text_lower:
            products.append('Pro plan')
        if 'advanced plan' in text_lower:
            products.append('Advanced plan')
        if 'free plan' in text_lower:
            products.append('Free plan')

        # Features
        feature_patterns = {
            'drafts': r'\bdrafts?\b',
            'queue': r'\bqueue\b',
            'scheduler': r'\bscheduler?\b',
            'publisher': r'\bpublisher?\b',
            'calendar': r'\bcalendar\b',
            'analytics': r'\banalytics\b',
            'create': r'\bcreate\b',
            'settings': r'\bsettings?\b',
            'billing': r'\bbilling\b',
            'subscription': r'\bsubscription\b'
        }

        for feature_name, pattern in feature_patterns.items():
            if re.search(pattern, text_lower):
                features.append(feature_name)

        return list(set(products)), list(set(features))

    def _extract_terminology(self, text: str) -> List[str]:
        """
        Extract key terminology/phrases from text.

        Args:
            text: Message text

        Returns:
            List of 2-3 word phrases
        """
        if not text:
            return []

        # Extract noun phrases (simple heuristic: 2-3 word sequences)
        text_lower = text.lower()

        # Remove URLs
        text_lower = re.sub(r'https?://\S+', '', text_lower)

        # Find 2-3 word phrases
        words = re.findall(r'\b[a-z]+\b', text_lower)

        phrases = []
        for i in range(len(words) - 1):
            # 2-word phrases
            phrase = f"{words[i]} {words[i+1]}"
            if self._is_meaningful_phrase(phrase):
                phrases.append(phrase)

            # 3-word phrases
            if i < len(words) - 2:
                phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
                if self._is_meaningful_phrase(phrase):
                    phrases.append(phrase)

        # Return most common phrases (limit to top 10)
        if phrases:
            phrase_counts = Counter(phrases)
            return [phrase for phrase, count in phrase_counts.most_common(10)]

        return []

    def _is_meaningful_phrase(self, phrase: str) -> bool:
        """
        Check if a phrase is meaningful (not all stopwords).

        Args:
            phrase: Phrase to check

        Returns:
            True if meaningful
        """
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
            'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'should', 'could', 'may', 'might', 'can', 'to',
            'of', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'as', 'that',
            'this', 'it', 'you', 'i', 'we', 'they', 'he', 'she', 'my', 'your',
            'our', 'their', 'his', 'her', 'its', 'me', 'us', 'them', 'him'
        }

        words = phrase.split()

        # Must have at least one non-stopword
        has_content_word = any(word not in stopwords for word in words)

        # Must be reasonable length
        is_reasonable_length = 5 <= len(phrase) <= 40

        return has_content_word and is_reasonable_length

    def _detect_self_service_gap(
        self,
        support_text: str,
        conversation_type: str
    ) -> tuple[bool, Optional[str]]:
        """
        Detect if this interaction reveals a self-service gap.

        Args:
            support_text: Support response text
            conversation_type: Classified conversation type

        Returns:
            (has_gap, evidence) tuple
        """
        if not support_text:
            return False, None

        text_lower = support_text.lower()

        # Pattern: Support manually doing something user could do
        manual_action_patterns = [
            (r"i've (processed|cancelled|updated|changed|reset|cleared) your", "Support manually {action}"),
            (r"i can (cancel|update|change|reset|clear) (your|the|this)", "Support offers to manually {action}"),
            (r"let me (cancel|update|change|reset|clear|process)", "Support manually handling {action}"),
            (r"i'll go ahead and (cancel|update|change|reset|clear|process)", "Support manually handling {action}"),
        ]

        for pattern, evidence_template in manual_action_patterns:
            match = re.search(pattern, text_lower)
            if match:
                action = match.group(1)
                evidence = evidence_template.format(action=action)
                return True, evidence

        # Pattern: Common self-service candidates by type
        self_service_candidates = {
            "billing_question": [
                "cancel",
                "subscription",
                "payment method",
                "plan change"
            ],
            "account_issue": [
                "password reset",
                "email change",
                "delete account"
            ]
        }

        if conversation_type in self_service_candidates:
            for keyword in self_service_candidates[conversation_type]:
                if keyword in text_lower:
                    return True, f"Support manually handled {keyword} - could be self-service"

        return False, None


def main():
    """Test the knowledge extractor."""
    extractor = KnowledgeExtractor()

    # Test case 1: Billing cancellation
    print("=" * 60)
    print("Test 1: Billing Cancellation\n")

    customer_msg = "I need to cancel my account"
    support_msgs = [
        "I'm sorry you're looking to cancel your subscription. Could you share why you're looking to cancel?",
        "I've gone ahead and initialized that cancellation for you. You won't be charged again and your account will revert to our free plan."
    ]

    knowledge = extractor.extract_from_conversation(
        customer_msg,
        support_msgs,
        "billing_question"
    )

    print(f"Root cause: {knowledge['root_cause']}")
    print(f"Solution: {knowledge['solution_provided']}")
    print(f"Products: {', '.join(knowledge['product_mentions'])}")
    print(f"Features: {', '.join(knowledge['feature_mentions'])}")
    print(f"Self-service gap: {knowledge['self_service_gap']}")
    if knowledge['gap_evidence']:
        print(f"Evidence: {knowledge['gap_evidence']}")

    # Test case 2: Product issue
    print("\n" + "=" * 60)
    print("Test 2: Product Issue\n")

    customer_msg = "The signup page isn't working"
    support_msgs = [
        "I'm sorry about that! This is due to a downtime we experienced earlier today.",
        "The issue has been resolved now. You should be able to try signing up again."
    ]

    knowledge = extractor.extract_from_conversation(
        customer_msg,
        support_msgs,
        "product_issue"
    )

    print(f"Root cause: {knowledge['root_cause']}")
    print(f"Solution: {knowledge['solution_provided']}")
    print(f"Self-service gap: {knowledge['self_service_gap']}")


if __name__ == "__main__":
    main()
