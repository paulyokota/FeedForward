"""
Domain Classifier Service

Classifies customer support issues into product categories using Claude Haiku 4.5.
Integrates with codebase domain map to provide context-aware search paths.

Architecture:
- Input: Raw customer conversation
- Classifier: Claude Haiku 4.5 (fast, cost-effective)
- Output: Category + recommended search paths
- Latency target: <500ms

Reference: docs/architecture.md
"""

import json
import logging
import time
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Configuration
DOMAIN_MAP_PATH = Path(__file__).parent.parent.parent.parent / "config" / "codebase_domain_map.yaml"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
CLASSIFICATION_TIMEOUT_MS = 500


@dataclass
class ClassificationResult:
    """Result of issue classification using Haiku."""

    category: str
    confidence: str  # "high", "medium", "low"
    reasoning: str
    suggested_repos: List[str] = field(default_factory=list)
    suggested_search_paths: List[str] = field(default_factory=list)
    alternative_categories: List[str] = field(default_factory=list)
    keywords_matched: List[str] = field(default_factory=list)
    classification_duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None


class DomainClassifier:
    """
    Classifies customer issues into product categories using Haiku.

    Uses a two-stage approach:
    1. Keyword matching against domain map (fast fallback)
    2. Haiku classification (accurate, semantic understanding)

    Cost: ~$0.00015 per classification (~$4.50/month for 1,000 daily issues)
    Latency: Target <500ms
    """

    def __init__(self):
        """Initialize the classifier with domain map and Anthropic client."""
        try:
            self.client = Anthropic()
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}. Check ANTHROPIC_API_KEY environment variable.")
            raise ValueError("Anthropic API key not configured") from e

        self.domain_map = self._load_domain_map()
        self.categories = self.domain_map.get("categories", {})
        self._build_keyword_index()

    def _load_domain_map(self) -> Dict:
        """Load the codebase domain knowledge map from YAML."""
        try:
            if not DOMAIN_MAP_PATH.exists():
                logger.error(f"Domain map not found at {DOMAIN_MAP_PATH}")
                return {}

            with open(DOMAIN_MAP_PATH, "r") as f:
                domain_map = yaml.safe_load(f)
                logger.info(f"Loaded domain map with {len(domain_map.get('categories', {}))} categories")
                return domain_map
        except Exception as e:
            logger.error(f"Failed to load domain map: {e}", exc_info=True)
            return {}

    def _build_keyword_index(self):
        """Build keyword → category index for fast matching."""
        self.keyword_index: Dict[str, List[str]] = {}  # keyword -> [categories]

        for category, config in self.categories.items():
            keywords = config.get("keywords", [])
            for keyword in keywords:
                if keyword not in self.keyword_index:
                    self.keyword_index[keyword] = []
                self.keyword_index[keyword].append(category)

        logger.debug(f"Built keyword index with {len(self.keyword_index)} keywords")

    def _keyword_fallback_classification(self, text: str) -> Optional[ClassificationResult]:
        """
        Fast keyword-based fallback classification.

        Returns None if no keywords match (will use Haiku instead).
        """
        text_lower = text.lower()
        category_scores: Dict[str, int] = {}

        # Score categories by keyword matches
        for keyword, categories in self.keyword_index.items():
            if keyword in text_lower:
                for category in categories:
                    category_scores[category] = category_scores.get(category, 0) + 1

        if not category_scores:
            return None

        # Return top category if confident
        top_category = max(category_scores, key=category_scores.get)
        score = category_scores[top_category]

        # Only use fallback if we have strong signal (multiple keywords matched)
        if score < 2:
            return None

        category_config = self.categories.get(top_category, {})
        return ClassificationResult(
            category=top_category,
            confidence="medium",  # Keyword matching is less confident than Haiku
            reasoning=f"Matched {score} keywords from domain map",
            suggested_repos=category_config.get("repos", []),
            suggested_search_paths=category_config.get("search_paths", []),
            alternative_categories=[c for c, s in sorted(category_scores.items(), key=lambda x: -x[1])[1:3]],
            keywords_matched=sorted(
                [kw for kw in self.keyword_index.keys() if kw in text_lower], key=lambda x: len(x), reverse=True
            )[:5],
            success=True,
        )

    def classify(self, issue_text: str, stage2_context: Optional[str] = None) -> ClassificationResult:
        """
        Classify a customer support issue into a product category.

        Args:
            issue_text: Raw customer message or issue description
            stage2_context: Optional additional context (e.g., from stage 2 analysis)

        Returns:
            ClassificationResult with category, confidence, and suggested search paths

        Raises:
            Does not raise; returns error in result on failure
        """
        start_time = time.time()

        try:
            # Try keyword fallback first (fast path)
            fallback_result = self._keyword_fallback_classification(issue_text)
            if fallback_result:
                duration_ms = int((time.time() - start_time) * 1000)
                fallback_result.classification_duration_ms = duration_ms
                logger.info(f"Keyword fallback matched category: {fallback_result.category}")
                return fallback_result

            # Use Haiku for semantic classification
            result = self._classify_with_haiku(issue_text, stage2_context, start_time)
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Classification failed: {e}", exc_info=True)
            return ClassificationResult(
                category="bug_report",
                confidence="low",
                reasoning="Classification error, defaulting to bug_report",
                success=False,
                error=str(e),
                classification_duration_ms=duration_ms,
            )

    def _classify_with_haiku(
        self, issue_text: str, stage2_context: Optional[str], start_time: float
    ) -> ClassificationResult:
        """Use Haiku to classify the issue."""
        # Build category definitions for prompt
        category_defs = self._build_category_definitions()

        # Build the prompt
        prompt = self._build_classification_prompt(issue_text, stage2_context, category_defs)

        try:
            # Call Haiku with enforced timeout
            response = self.client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=500,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
                timeout=CLASSIFICATION_TIMEOUT_MS / 1000,  # Convert ms to seconds
            )

            # Parse response
            response_text = response.content[0].text

            # Try to extract JSON from response
            classification = self._parse_classification_response(response_text)

            # Enrich with search paths from domain map
            category_config = self.categories.get(classification["category"], {})
            classification["suggested_repos"] = category_config.get("repos", [])
            classification["suggested_search_paths"] = category_config.get("search_paths", [])
            classification["keywords_matched"] = self._extract_matched_keywords(issue_text, classification["category"])

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Classified as {classification['category']} ({classification['confidence']})",
                extra={"duration_ms": duration_ms},
            )

            return ClassificationResult(
                category=classification["category"],
                confidence=classification["confidence"],
                reasoning=classification["reasoning"],
                suggested_repos=classification.get("suggested_repos", []),
                suggested_search_paths=classification.get("suggested_search_paths", []),
                alternative_categories=classification.get("alternative_categories", []),
                keywords_matched=classification.get("keywords_matched", []),
                classification_duration_ms=duration_ms,
                success=True,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Haiku classification failed: {e}", exc_info=True)
            return ClassificationResult(
                category="bug_report",
                confidence="low",
                reasoning="Classification error",
                success=False,
                error=str(e),
                classification_duration_ms=duration_ms,
            )

    def _build_category_definitions(self) -> str:
        """Build category definitions string for prompt."""
        lines = []
        for category, config in self.categories.items():
            description = config.get("description", "")
            keywords = ", ".join(config.get("keywords", [])[:5])  # Limit to first 5 keywords
            lines.append(f"- {category}: {description}")
            lines.append(f"  Keywords: {keywords}")

        return "\n".join(lines)

    def _build_classification_prompt(self, issue_text: str, stage2_context: Optional[str], category_defs: str) -> str:
        """Build the classification prompt for Haiku."""
        context_block = ""
        if stage2_context:
            context_block = f"\n\nAdditional Context:\n{stage2_context}"

        prompt = f"""You are a technical issue classifier. Classify this customer support issue into ONE of the categories below.

ISSUE TEXT:
{issue_text}{context_block}

AVAILABLE CATEGORIES:
{category_defs}

Respond with ONLY a valid JSON object (no markdown, no explanation):
{{
  "category": "category_name",
  "confidence": "high|medium|low",
  "reasoning": "Brief explanation",
  "alternative_categories": ["cat1", "cat2"]
}}"""

        return prompt

    def _parse_classification_response(self, response_text: str) -> Dict:
        """Parse Haiku's JSON response."""
        # Try to extract JSON from response
        try:
            # Find JSON object in response
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1

            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)

                # Validate required fields
                if "category" not in result:
                    result["category"] = "bug_report"
                if "confidence" not in result:
                    result["confidence"] = "medium"
                if "reasoning" not in result:
                    result["reasoning"] = "Classification parsed from response"
                if "alternative_categories" not in result:
                    result["alternative_categories"] = []

                # Ensure category exists in domain map
                if result["category"] not in self.categories:
                    logger.warning(f"Unknown category: {result['category']}, defaulting to bug_report")
                    result["category"] = "bug_report"

                return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse classification JSON: {e}")

        # Fallback
        return {
            "category": "bug_report",
            "confidence": "low",
            "reasoning": "Failed to parse response",
            "alternative_categories": [],
        }

    def _extract_matched_keywords(self, text: str, category: str) -> List[str]:
        """Extract keywords from text that match the category."""
        category_config = self.categories.get(category, {})
        keywords = category_config.get("keywords", [])
        text_lower = text.lower()

        matched = [kw for kw in keywords if kw in text_lower]
        return matched[:5]  # Limit to first 5

    def get_category_info(self, category: str) -> Optional[Dict]:
        """Get configuration details for a category."""
        return self.categories.get(category)

    def list_categories(self) -> List[str]:
        """List all available categories."""
        return sorted(list(self.categories.keys()))
