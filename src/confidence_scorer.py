#!/usr/bin/env python3
"""
Confidence Scorer for Story Groupings.

Scores how confident we are that conversations in a group belong together.
Used in Phase 2 of the story grouping architecture.

Confidence signals (updated based on PM review calibration 2026-01-08):
- Semantic similarity (30%): Cosine similarity of conversation embeddings
- Intent similarity (20%): Semantic similarity of user_intent fields
- Intent homogeneity (15%): Penalizes high variance in intents (clusters = bad)
- Symptom overlap (10%): Jaccard similarity of symptom keywords (reduced - not discriminative)
- Product area match (10%): All conversations same product_area
- Component match (10%): All conversations same component
- Platform uniformity (5%): All conversations about same platform (Pinterest/IG/FB)

Usage:
    from confidence_scorer import ConfidenceScorer

    scorer = ConfidenceScorer()
    scored_groups = scorer.score_groups(conversations_by_signature)
    # Returns list of ScoredGroup objects sorted by confidence_score descending
"""
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from openai import OpenAI

# Constants
MIN_GROUP_SIZE = 3  # Decision from architecture doc

# Platforms to detect for uniformity check
PLATFORMS = {'pinterest', 'instagram', 'facebook', 'twitter', 'linkedin', 'tiktok'}


@dataclass
class ScoredGroup:
    """A group of conversations with a confidence score."""
    signature: str
    conversations: list[dict]
    confidence_score: float
    # Breakdown of score components
    embedding_similarity: float
    symptom_overlap: float
    intent_similarity: float
    intent_homogeneity: float  # NEW: penalizes variance
    platform_uniformity: float  # NEW: same platform check
    product_area_match: bool
    component_match: bool


class ConfidenceScorer:
    """Scores conversation groupings for coherence."""

    def __init__(self, embedding_model: str = "text-embedding-3-small"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.embedding_model = embedding_model
        self._embedding_cache: dict[str, list[float]] = {}

    def score_groups(
        self,
        conversations_by_signature: dict[str, list[dict]],
        verbose: bool = False
    ) -> list[ScoredGroup]:
        """
        Score all groups and return sorted by confidence DESC.

        Args:
            conversations_by_signature: Dict mapping signature -> list of conversation dicts
            verbose: Print progress

        Returns:
            List of ScoredGroup objects sorted by confidence_score descending
        """
        scored_groups = []

        for signature, conversations in conversations_by_signature.items():
            if verbose:
                print(f"Scoring {signature} ({len(conversations)} conversations)...")

            score = self._score_group(signature, conversations)
            scored_groups.append(score)

        # Sort by confidence DESC
        scored_groups.sort(key=lambda g: g.confidence_score, reverse=True)
        return scored_groups

    def _score_group(self, signature: str, conversations: list[dict]) -> ScoredGroup:
        """Calculate confidence score for a single group."""

        # Handle singleton/pair groups - lower confidence by default
        if len(conversations) < MIN_GROUP_SIZE:
            return ScoredGroup(
                signature=signature,
                conversations=conversations,
                confidence_score=30.0,  # Low confidence for under-sized groups
                embedding_similarity=0.0,
                symptom_overlap=0.0,
                intent_similarity=0.0,
                intent_homogeneity=0.0,
                platform_uniformity=1.0,
                product_area_match=True,
                component_match=True,
            )

        # Calculate each signal
        embedding_sim = self._calc_embedding_similarity(conversations)
        symptom_overlap = self._calc_symptom_overlap(conversations)
        intent_sim, intent_homogeneity = self._calc_intent_metrics(conversations)
        platform_uniformity = self._calc_platform_uniformity(conversations)
        product_match = self._check_product_area_match(conversations)
        component_match = self._check_component_match(conversations)

        # Updated weighted score (0-100) based on PM review calibration
        confidence = (
            0.30 * embedding_sim * 100 +
            0.20 * intent_sim * 100 +
            0.15 * intent_homogeneity * 100 +  # NEW
            0.10 * symptom_overlap * 100 +      # Reduced from 0.25
            0.10 * (100 if product_match else 0) +
            0.10 * (100 if component_match else 0) +
            0.05 * platform_uniformity * 100    # NEW
        )

        return ScoredGroup(
            signature=signature,
            conversations=conversations,
            confidence_score=round(confidence, 1),
            embedding_similarity=round(embedding_sim, 3),
            symptom_overlap=round(symptom_overlap, 3),
            intent_similarity=round(intent_sim, 3),
            intent_homogeneity=round(intent_homogeneity, 3),
            platform_uniformity=round(platform_uniformity, 3),
            product_area_match=product_match,
            component_match=component_match,
        )

    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text, with caching."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        # Truncate very long text
        text = text[:8000] if len(text) > 8000 else text

        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        embedding = response.data[0].embedding
        self._embedding_cache[text] = embedding
        return embedding

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def _calc_embedding_similarity(self, conversations: list[dict]) -> float:
        """
        Calculate average pairwise cosine similarity of conversation excerpts.
        Returns 0-1 score.
        """
        if len(conversations) < 2:
            return 1.0

        # Get embeddings for excerpts
        embeddings = []
        for conv in conversations:
            text = conv.get("excerpt", "") or conv.get("source_body", "")
            if text:
                embeddings.append(self._get_embedding(text))

        if len(embeddings) < 2:
            return 1.0

        # Calculate pairwise similarities
        similarities = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = self._cosine_similarity(embeddings[i], embeddings[j])
                similarities.append(sim)

        return sum(similarities) / len(similarities) if similarities else 1.0

    def _calc_symptom_overlap(self, conversations: list[dict]) -> float:
        """
        Calculate Jaccard similarity of symptom keywords across conversations.
        Returns 0-1 score.
        """
        if len(conversations) < 2:
            return 1.0

        # Extract symptom sets
        symptom_sets = []
        for conv in conversations:
            symptoms = conv.get("symptoms", [])
            if isinstance(symptoms, list):
                # Normalize: lowercase, split into words
                words = set()
                for symptom in symptoms:
                    if isinstance(symptom, str):
                        words.update(symptom.lower().split())
                symptom_sets.append(words)

        if len(symptom_sets) < 2:
            return 1.0

        # Calculate pairwise Jaccard similarities
        similarities = []
        for i in range(len(symptom_sets)):
            for j in range(i + 1, len(symptom_sets)):
                set_a, set_b = symptom_sets[i], symptom_sets[j]
                if set_a or set_b:  # At least one non-empty
                    intersection = len(set_a & set_b)
                    union = len(set_a | set_b)
                    jaccard = intersection / union if union > 0 else 0
                    similarities.append(jaccard)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _calc_intent_metrics(self, conversations: list[dict]) -> tuple[float, float]:
        """
        Calculate both intent similarity AND homogeneity.

        Returns:
            (intent_similarity, intent_homogeneity)
            - similarity: Average pairwise similarity (high = similar intents)
            - homogeneity: Penalizes variance (high mean + low std = good)
        """
        if len(conversations) < 2:
            return 1.0, 1.0

        # Get embeddings for intents
        embeddings = []
        for conv in conversations:
            intent = conv.get("user_intent", "")
            if intent:
                embeddings.append(self._get_embedding(intent))

        if len(embeddings) < 2:
            return 1.0, 1.0

        # Calculate pairwise similarities
        similarities = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = self._cosine_similarity(embeddings[i], embeddings[j])
                similarities.append(sim)

        if not similarities:
            return 1.0, 1.0

        # Intent similarity = mean
        mean_sim = sum(similarities) / len(similarities)

        # Intent homogeneity = penalize high variance
        # High mean + low std = homogeneous (good)
        # High mean + high std = clusters (bad)
        std_sim = float(np.std(similarities)) if len(similarities) > 1 else 0.0

        # Homogeneity score: mean * (1 - std), clamped to [0, 1]
        # If std is high (0.3+), this significantly penalizes the score
        homogeneity = max(0.0, min(1.0, mean_sim * (1 - std_sim * 2)))

        return mean_sim, homogeneity

    def _calc_platform_uniformity(self, conversations: list[dict]) -> float:
        """
        Check if all conversations mention the same social platforms.

        Returns 1.0 if uniform, lower if mixed platforms detected.
        """
        if len(conversations) < 2:
            return 1.0

        # Detect platforms mentioned in each conversation
        conv_platforms = []
        for conv in conversations:
            text = (
                conv.get("excerpt", "") + " " +
                conv.get("user_intent", "") + " " +
                conv.get("affected_flow", "")
            ).lower()

            mentioned = {p for p in PLATFORMS if p in text}
            conv_platforms.append(mentioned)

        # If no platforms detected anywhere, assume uniform
        all_mentioned = set().union(*conv_platforms) if conv_platforms else set()
        if not all_mentioned:
            return 1.0

        # Check if all conversations mention the same platforms
        non_empty = [p for p in conv_platforms if p]
        if not non_empty:
            return 1.0

        # If all non-empty sets are identical, perfect uniformity
        first = non_empty[0]
        if all(p == first for p in non_empty):
            return 1.0

        # Otherwise, penalize based on diversity
        # More unique platforms = lower score
        unique_platforms = len(all_mentioned)
        return 1.0 / unique_platforms if unique_platforms > 0 else 1.0

    def _check_product_area_match(self, conversations: list[dict]) -> bool:
        """Check if all conversations have the same product_area."""
        areas = {conv.get("product_area") for conv in conversations}
        return len(areas) == 1

    def _check_component_match(self, conversations: list[dict]) -> bool:
        """Check if all conversations have the same component."""
        components = {conv.get("component") for conv in conversations}
        return len(components) == 1


def load_theme_results(filepath: Path) -> dict[str, list[dict]]:
    """Load theme extraction results grouped by signature."""
    groups: dict[str, list[dict]] = defaultdict(list)

    with open(filepath) as f:
        for line in f:
            conv = json.loads(line)
            signature = conv.get("issue_signature", "unknown")
            groups[signature].append(conv)

    return dict(groups)


def main():
    """Score groups from theme extraction results."""
    import argparse

    parser = argparse.ArgumentParser(description="Score conversation groupings")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "theme_extraction_results.jsonl",
        help="Input file with theme extraction results"
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=MIN_GROUP_SIZE,
        help=f"Minimum group size to score fully (default: {MIN_GROUP_SIZE})"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress"
    )
    args = parser.parse_args()

    print(f"Loading theme results from: {args.input}")
    groups = load_theme_results(args.input)
    print(f"Found {len(groups)} unique signatures")
    print("-" * 60)

    scorer = ConfidenceScorer()
    scored = scorer.score_groups(groups, verbose=args.verbose)

    print("\n" + "=" * 60)
    print("CONFIDENCE SCORES (sorted by confidence DESC)")
    print("=" * 60)

    for sg in scored:
        size_flag = "" if len(sg.conversations) >= args.min_size else " [UNDER-SIZED]"
        print(f"\n{sg.signature}{size_flag}")
        print(f"  Conversations: {len(sg.conversations)}")
        print(f"  Confidence: {sg.confidence_score:.1f}/100")
        print(f"  Breakdown:")
        print(f"    - Embedding similarity: {sg.embedding_similarity:.3f}")
        print(f"    - Intent similarity: {sg.intent_similarity:.3f}")
        print(f"    - Intent homogeneity: {sg.intent_homogeneity:.3f}")
        print(f"    - Symptom overlap: {sg.symptom_overlap:.3f}")
        print(f"    - Platform uniformity: {sg.platform_uniformity:.3f}")
        print(f"    - Product area match: {sg.product_area_match}")
        print(f"    - Component match: {sg.component_match}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    valid_groups = [g for g in scored if len(g.conversations) >= args.min_size]
    undersized = [g for g in scored if len(g.conversations) < args.min_size]

    print(f"Total groups: {len(scored)}")
    print(f"Valid groups (>= {args.min_size} convos): {len(valid_groups)}")
    print(f"Under-sized groups: {len(undersized)}")

    if valid_groups:
        avg_conf = sum(g.confidence_score for g in valid_groups) / len(valid_groups)
        print(f"Average confidence (valid groups): {avg_conf:.1f}")

        high_conf = [g for g in valid_groups if g.confidence_score >= 70]
        print(f"High confidence (>=70): {len(high_conf)}")


if __name__ == "__main__":
    main()
