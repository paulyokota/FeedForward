#!/usr/bin/env python3
"""
Signature Canonicalization Baseline Measurement (Issue #152)

Measures how well the current canonicalization approaches perform against
the human-labeled ground truth dataset.

Tests two approaches:
1. LLM-based canonicalization (current default)
2. Embedding-based canonicalization (existing but not default)

For each ground truth pair (sig_a, sig_b):
- Simulates: "sig_a exists, we're proposing sig_b"
- Runs canonicalization
- Checks if it returns sig_a (merged) or sig_b (kept separate)
- Compares to ground truth label

Metrics computed:
- Precision: Of pairs we merged, how many were actually "same"?
- Recall: Of pairs that are "same", how many did we merge?
- F1: Harmonic mean of precision and recall

Usage:
    # Run baseline measurement with LLM canonicalization
    python scripts/signature_baseline.py

    # Run with embedding-only (faster, cheaper)
    python scripts/signature_baseline.py --embedding-only

    # Run both and compare
    python scripts/signature_baseline.py --compare

    # Dry run - just show what would be tested
    python scripts/signature_baseline.py --dry-run
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
GROUND_TRUTH_PATH = DATA_DIR / "signature_ground_truth.json"
BASELINE_RESULTS_PATH = DATA_DIR / "signature_baseline_results.json"


@dataclass
class PairResult:
    """Result of testing a single pair."""
    sig_a: str
    sig_b: str
    ground_truth: str  # "same", "different", "ambiguous"
    predicted: str  # "merged" or "separate"
    canonical_signature: str  # What canonicalization returned
    correct: Optional[bool]  # True if prediction matches ground truth (None for ambiguous)
    method: str  # "llm" or "embedding"


@dataclass
class BaselineResults:
    """Results of baseline measurement."""
    method: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Counts
    total_pairs: int = 0
    same_pairs: int = 0
    different_pairs: int = 0
    ambiguous_pairs: int = 0

    # Predictions on non-ambiguous pairs
    true_positives: int = 0  # labeled "same", predicted "merged"
    false_positives: int = 0  # labeled "different", predicted "merged"
    true_negatives: int = 0  # labeled "different", predicted "separate"
    false_negatives: int = 0  # labeled "same", predicted "separate"

    # Predictions on ambiguous pairs (tracked separately)
    ambiguous_merged: int = 0
    ambiguous_separate: int = 0

    # Metrics
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    accuracy: float = 0.0

    # Individual pair results
    pair_results: List[dict] = field(default_factory=list)

    def compute_metrics(self):
        """Compute precision, recall, F1, accuracy from counts."""
        # Precision: TP / (TP + FP)
        if self.true_positives + self.false_positives > 0:
            self.precision = self.true_positives / (self.true_positives + self.false_positives)

        # Recall: TP / (TP + FN)
        if self.true_positives + self.false_negatives > 0:
            self.recall = self.true_positives / (self.true_positives + self.false_negatives)

        # F1: 2 * (precision * recall) / (precision + recall)
        if self.precision + self.recall > 0:
            self.f1 = 2 * (self.precision * self.recall) / (self.precision + self.recall)

        # Accuracy: (TP + TN) / total non-ambiguous
        total_non_ambiguous = self.same_pairs + self.different_pairs
        if total_non_ambiguous > 0:
            self.accuracy = (self.true_positives + self.true_negatives) / total_non_ambiguous

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "timestamp": self.timestamp,
            "counts": {
                "total_pairs": self.total_pairs,
                "same_pairs": self.same_pairs,
                "different_pairs": self.different_pairs,
                "ambiguous_pairs": self.ambiguous_pairs,
            },
            "confusion_matrix": {
                "true_positives": self.true_positives,
                "false_positives": self.false_positives,
                "true_negatives": self.true_negatives,
                "false_negatives": self.false_negatives,
            },
            "ambiguous_predictions": {
                "merged": self.ambiguous_merged,
                "separate": self.ambiguous_separate,
            },
            "metrics": {
                "precision": round(self.precision, 4),
                "recall": round(self.recall, 4),
                "f1": round(self.f1, 4),
                "accuracy": round(self.accuracy, 4),
            },
            "pair_results": self.pair_results,
        }


def load_ground_truth() -> List[dict]:
    """Load ground truth dataset."""
    if not GROUND_TRUTH_PATH.exists():
        raise FileNotFoundError(f"Ground truth not found at {GROUND_TRUTH_PATH}")

    with open(GROUND_TRUTH_PATH) as f:
        data = json.load(f)

    return data.get("pairs", [])


def get_signature_context(signature: str, run_id: int = 95) -> dict:
    """
    Fetch context for a signature from the database.
    Returns dict with product_area, component, user_intent, symptoms.
    """
    import subprocess

    query = f"""
    SELECT product_area, component, user_intent, symptoms::text
    FROM themes
    WHERE pipeline_run_id = {run_id}
      AND issue_signature = '{signature}'
    LIMIT 1
    """

    result = subprocess.run(
        ['psql', '-h', 'localhost', '-d', 'feedforward', '-t', '-A', '-F', '\t', '-c', query],
        capture_output=True, text=True
    )

    if result.returncode != 0 or not result.stdout.strip():
        return {
            "product_area": "other",
            "component": "unknown",
            "user_intent": "",
            "symptoms": [],
        }

    parts = result.stdout.strip().split('\t')

    symptoms = []
    if len(parts) > 3 and parts[3]:
        try:
            symptoms = json.loads(parts[3])
        except json.JSONDecodeError:
            pass

    return {
        "product_area": parts[0] if len(parts) > 0 else "other",
        "component": parts[1] if len(parts) > 1 else "unknown",
        "user_intent": parts[2] if len(parts) > 2 else "",
        "symptoms": symptoms,
    }


def test_llm_canonicalization(sig_a: str, sig_b: str, context_b: dict) -> Tuple[str, str]:
    """
    Test LLM-based canonicalization.

    Simulates: sig_a exists, we're proposing sig_b.
    Returns: (prediction, canonical_signature)
    """
    from theme_extractor import ThemeExtractor

    extractor = ThemeExtractor(use_vocabulary=False)

    # Mock the existing signatures to only include sig_a
    # We need to temporarily override get_existing_signatures
    original_method = extractor.get_existing_signatures

    def mock_get_existing(product_area=None, include_session=True):
        return [{
            "signature": sig_a,
            "product_area": context_b.get("product_area", "other"),
            "component": context_b.get("component", "unknown"),
            "count": 1,
        }]

    extractor.get_existing_signatures = mock_get_existing

    try:
        result = extractor.canonicalize_signature(
            proposed_signature=sig_b,
            product_area=context_b.get("product_area", "other"),
            component=context_b.get("component", "unknown"),
            user_intent=context_b.get("user_intent", ""),
            symptoms=context_b.get("symptoms", []),
            use_llm=True,
        )

        # If result == sig_a, they were merged
        # If result == sig_b (or normalized version), they were kept separate
        if result == sig_a:
            return "merged", result
        else:
            return "separate", result

    finally:
        extractor.get_existing_signatures = original_method


def test_embedding_canonicalization(sig_a: str, sig_b: str, context_a: dict, context_b: dict, threshold: float = 0.85) -> Tuple[str, str]:
    """
    Test embedding-based canonicalization.

    Simulates: sig_a exists, we're proposing sig_b.
    Returns: (prediction, canonical_signature)
    """
    from theme_extractor import ThemeExtractor, cosine_similarity

    extractor = ThemeExtractor(use_vocabulary=False)

    # Build descriptions for embedding
    def build_description(sig: str, ctx: dict) -> str:
        parts = [sig.replace('_', ' ')]
        if ctx.get("product_area"):
            parts.append(f"Product: {ctx['product_area']}")
        if ctx.get("component"):
            parts.append(f"Component: {ctx['component']}")
        if ctx.get("user_intent"):
            parts.append(f"Intent: {ctx['user_intent'][:100]}")
        if ctx.get("symptoms"):
            parts.append(f"Symptoms: {', '.join(ctx['symptoms'][:3])}")
        return " | ".join(parts)

    desc_a = build_description(sig_a, context_a)
    desc_b = build_description(sig_b, context_b)

    # Get embeddings
    emb_a = extractor.get_embedding(desc_a)
    emb_b = extractor.get_embedding(desc_b)

    # Compute similarity
    similarity = cosine_similarity(emb_a, emb_b)

    if similarity >= threshold:
        return "merged", sig_a
    else:
        return "separate", sig_b


def run_baseline(
    pairs: List[dict],
    method: str = "llm",
    embedding_threshold: float = 0.85,
    dry_run: bool = False,
) -> BaselineResults:
    """
    Run baseline measurement on ground truth pairs.

    Args:
        pairs: List of ground truth pairs
        method: "llm" or "embedding"
        embedding_threshold: Threshold for embedding similarity
        dry_run: If True, just show what would be tested
    """
    results = BaselineResults(method=method)
    results.total_pairs = len(pairs)

    for i, pair in enumerate(pairs):
        sig_a = pair["sig_a"]
        sig_b = pair["sig_b"]
        label = pair["label"]

        # Count by label
        if label == "same":
            results.same_pairs += 1
        elif label == "different":
            results.different_pairs += 1
        else:
            results.ambiguous_pairs += 1

        if dry_run:
            print(f"{i+1}. {sig_a} <-> {sig_b} [{label}]")
            continue

        # Get context for both signatures
        context_a = get_signature_context(sig_a)
        context_b = get_signature_context(sig_b)

        logger.info(f"Testing pair {i+1}/{len(pairs)}: {sig_a[:30]}... <-> {sig_b[:30]}...")

        # Run canonicalization
        try:
            if method == "llm":
                prediction, canonical = test_llm_canonicalization(sig_a, sig_b, context_b)
            else:
                prediction, canonical = test_embedding_canonicalization(
                    sig_a, sig_b, context_a, context_b, embedding_threshold
                )
        except Exception as e:
            logger.error(f"Error testing pair: {e}")
            prediction = "error"
            canonical = "error"

        # Determine correctness
        correct = None
        if label == "same":
            correct = (prediction == "merged")
            if correct:
                results.true_positives += 1
            else:
                results.false_negatives += 1
        elif label == "different":
            correct = (prediction == "separate")
            if correct:
                results.true_negatives += 1
            else:
                results.false_positives += 1
        else:  # ambiguous
            if prediction == "merged":
                results.ambiguous_merged += 1
            else:
                results.ambiguous_separate += 1

        # Record result
        pair_result = PairResult(
            sig_a=sig_a,
            sig_b=sig_b,
            ground_truth=label,
            predicted=prediction,
            canonical_signature=canonical,
            correct=correct,
            method=method,
        )

        results.pair_results.append({
            "sig_a": pair_result.sig_a,
            "sig_b": pair_result.sig_b,
            "ground_truth": pair_result.ground_truth,
            "predicted": pair_result.predicted,
            "canonical": pair_result.canonical_signature,
            "correct": pair_result.correct,
        })

        # Log result
        status = "✓" if correct else ("✗" if correct is False else "?")
        logger.info(f"  {status} Ground truth: {label}, Predicted: {prediction}")

    if not dry_run:
        results.compute_metrics()

    return results


def print_results(results: BaselineResults):
    """Print results in a readable format."""
    print("\n" + "=" * 60)
    print(f"BASELINE RESULTS: {results.method.upper()} CANONICALIZATION")
    print("=" * 60)

    print(f"\nDataset:")
    print(f"  Total pairs: {results.total_pairs}")
    print(f"  Same: {results.same_pairs}")
    print(f"  Different: {results.different_pairs}")
    print(f"  Ambiguous: {results.ambiguous_pairs}")

    print(f"\nConfusion Matrix (excluding ambiguous):")
    print(f"                    Predicted")
    print(f"                 Merged | Separate")
    print(f"  Actual Same:     {results.true_positives:3d}   |   {results.false_negatives:3d}")
    print(f"  Actual Diff:     {results.false_positives:3d}   |   {results.true_negatives:3d}")

    print(f"\nMetrics:")
    print(f"  Precision: {results.precision:.2%}  (Of merged pairs, how many were actually same?)")
    print(f"  Recall:    {results.recall:.2%}  (Of same pairs, how many did we merge?)")
    print(f"  F1 Score:  {results.f1:.2%}")
    print(f"  Accuracy:  {results.accuracy:.2%}")

    print(f"\nAmbiguous pairs:")
    print(f"  Merged: {results.ambiguous_merged}")
    print(f"  Separate: {results.ambiguous_separate}")

    # Show errors
    errors = [r for r in results.pair_results if r.get("correct") is False]
    if errors:
        print(f"\nErrors ({len(errors)} pairs):")
        for e in errors:
            print(f"  {e['sig_a'][:35]}")
            print(f"  {e['sig_b'][:35]}")
            print(f"    Ground truth: {e['ground_truth']}, Predicted: {e['predicted']}")
            print()


def save_results(results: BaselineResults):
    """Save results to file."""
    # Load existing results if any
    all_results = {}
    if BASELINE_RESULTS_PATH.exists():
        with open(BASELINE_RESULTS_PATH) as f:
            all_results = json.load(f)

    # Add new results under method key
    all_results[results.method] = results.to_dict()

    with open(BASELINE_RESULTS_PATH, 'w') as f:
        json.dump(all_results, f, indent=2)

    logger.info(f"Results saved to {BASELINE_RESULTS_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Measure baseline canonicalization performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--embedding-only', action='store_true',
        help='Use embedding-based canonicalization only (faster, cheaper)'
    )
    parser.add_argument(
        '--compare', action='store_true',
        help='Run both LLM and embedding methods and compare'
    )
    parser.add_argument(
        '--embedding-threshold', type=float, default=0.85,
        help='Threshold for embedding similarity (default: 0.85)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Just show what would be tested, no API calls'
    )

    args = parser.parse_args()

    # Load ground truth
    pairs = load_ground_truth()
    logger.info(f"Loaded {len(pairs)} ground truth pairs")

    if args.dry_run:
        print("\nDry run - pairs to test:")
        run_baseline(pairs, dry_run=True)
        return

    if args.compare:
        # Run both methods
        print("\n" + "=" * 60)
        print("Running EMBEDDING baseline first (faster)...")
        print("=" * 60)
        emb_results = run_baseline(pairs, method="embedding", embedding_threshold=args.embedding_threshold)
        print_results(emb_results)
        save_results(emb_results)

        print("\n" + "=" * 60)
        print("Running LLM baseline (slower, uses API)...")
        print("=" * 60)
        llm_results = run_baseline(pairs, method="llm")
        print_results(llm_results)
        save_results(llm_results)

        # Comparison
        print("\n" + "=" * 60)
        print("COMPARISON")
        print("=" * 60)
        print(f"\n{'Metric':<15} {'Embedding':<12} {'LLM':<12} {'Δ':<10}")
        print("-" * 50)
        print(f"{'Precision':<15} {emb_results.precision:.2%}       {llm_results.precision:.2%}       {llm_results.precision - emb_results.precision:+.2%}")
        print(f"{'Recall':<15} {emb_results.recall:.2%}       {llm_results.recall:.2%}       {llm_results.recall - emb_results.recall:+.2%}")
        print(f"{'F1':<15} {emb_results.f1:.2%}       {llm_results.f1:.2%}       {llm_results.f1 - emb_results.f1:+.2%}")
        print(f"{'Accuracy':<15} {emb_results.accuracy:.2%}       {llm_results.accuracy:.2%}       {llm_results.accuracy - emb_results.accuracy:+.2%}")

    elif args.embedding_only:
        results = run_baseline(pairs, method="embedding", embedding_threshold=args.embedding_threshold)
        print_results(results)
        save_results(results)
    else:
        results = run_baseline(pairs, method="llm")
        print_results(results)
        save_results(results)


if __name__ == "__main__":
    main()
