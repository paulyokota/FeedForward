#!/usr/bin/env python3
"""
Signature Embedding Clustering Prototype (Issue #152)

Tests embedding-based signature canonicalization against ground truth.
Compares different embedding strategies:
- A: Signature only
- B: Signature + symptoms
- C: Signature + symptoms + diagnostic_summary

Evaluates by clustering signatures and checking if ground truth "same" pairs
land in the same cluster, and "different" pairs land in different clusters.

Usage:
    # Run all strategies and compare
    python scripts/signature_embedding_prototype.py

    # Test specific strategy
    python scripts/signature_embedding_prototype.py --strategy C

    # Tune distance threshold
    python scripts/signature_embedding_prototype.py --threshold 0.35

    # Dry run - show what would be tested
    python scripts/signature_embedding_prototype.py --dry-run
"""

import argparse
import json
import logging
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from openai import OpenAI
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
GROUND_TRUTH_PATH = DATA_DIR / "signature_ground_truth.json"
RESULTS_PATH = DATA_DIR / "signature_prototype_results.json"


@dataclass
class SignatureContext:
    """Context for a signature from Run 95 themes."""
    signature: str
    product_area: str
    component: str
    # Aggregated from all themes with this signature
    user_intents: List[str] = field(default_factory=list)
    symptoms: List[List[str]] = field(default_factory=list)
    diagnostic_summaries: List[str] = field(default_factory=list)
    count: int = 0


@dataclass
class ClusteringResult:
    """Result of clustering evaluation against ground truth."""
    strategy: str
    threshold: float
    n_clusters: int

    # Counts (same as baseline for comparability)
    total_pairs: int = 0
    same_pairs: int = 0
    different_pairs: int = 0
    ambiguous_pairs: int = 0

    # Confusion matrix
    true_positives: int = 0   # same pairs in same cluster
    false_positives: int = 0  # different pairs in same cluster
    true_negatives: int = 0   # different pairs in different clusters
    false_negatives: int = 0  # same pairs in different clusters

    # Ambiguous (tracked separately)
    ambiguous_same_cluster: int = 0
    ambiguous_different_cluster: int = 0

    # Metrics
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    accuracy: float = 0.0

    # Per-pair results for analysis
    pair_results: List[dict] = field(default_factory=list)

    # Cluster assignments for debugging
    cluster_assignments: Dict[str, int] = field(default_factory=dict)

    def compute_metrics(self):
        """Compute precision, recall, F1, accuracy."""
        # Precision: TP / (TP + FP)
        if self.true_positives + self.false_positives > 0:
            self.precision = self.true_positives / (self.true_positives + self.false_positives)

        # Recall: TP / (TP + FN)
        if self.true_positives + self.false_negatives > 0:
            self.recall = self.true_positives / (self.true_positives + self.false_negatives)

        # F1
        if self.precision + self.recall > 0:
            self.f1 = 2 * (self.precision * self.recall) / (self.precision + self.recall)

        # Accuracy
        total_non_ambiguous = self.same_pairs + self.different_pairs
        if total_non_ambiguous > 0:
            self.accuracy = (self.true_positives + self.true_negatives) / total_non_ambiguous

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "threshold": self.threshold,
            "n_clusters": self.n_clusters,
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
                "same_cluster": self.ambiguous_same_cluster,
                "different_cluster": self.ambiguous_different_cluster,
            },
            "metrics": {
                "precision": round(self.precision, 4),
                "recall": round(self.recall, 4),
                "f1": round(self.f1, 4),
                "accuracy": round(self.accuracy, 4),
            },
            "pair_results": self.pair_results,
        }


def run_query(sql: str) -> List[Tuple]:
    """Run a SQL query via psql and return results."""
    result = subprocess.run(
        ['psql', '-h', 'localhost', '-d', 'feedforward', '-t', '-A', '-F', '\t', '-c', sql],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Query failed: {result.stderr}")

    rows = []
    for line in result.stdout.strip().split('\n'):
        if line:
            rows.append(tuple(line.split('\t')))
    return rows


def fetch_signature_contexts(run_id: int = 95) -> Dict[str, SignatureContext]:
    """
    Fetch all signatures with their full context from Run 95.
    Returns dict mapping signature -> SignatureContext.
    """
    logger.info(f"Fetching signature contexts from run {run_id}...")

    query = f"""
    SELECT
        issue_signature,
        product_area,
        component,
        user_intent,
        symptoms::text,
        diagnostic_summary
    FROM themes
    WHERE pipeline_run_id = {run_id}
      AND issue_signature IS NOT NULL
    ORDER BY issue_signature
    """

    rows = run_query(query)

    contexts: Dict[str, SignatureContext] = {}

    for row in rows:
        if len(row) < 6:
            continue

        sig = row[0]
        product_area = row[1] or ""
        component = row[2] or ""
        user_intent = row[3] or ""
        symptoms_json = row[4] or "[]"
        diagnostic_summary = row[5] or ""

        # Parse symptoms
        try:
            symptoms = json.loads(symptoms_json) if symptoms_json else []
        except json.JSONDecodeError:
            symptoms = []

        if sig not in contexts:
            contexts[sig] = SignatureContext(
                signature=sig,
                product_area=product_area,
                component=component,
            )

        ctx = contexts[sig]
        ctx.count += 1

        # Collect samples (up to 3 of each)
        if user_intent and len(ctx.user_intents) < 3:
            ctx.user_intents.append(user_intent[:300])

        if symptoms and len(ctx.symptoms) < 3:
            ctx.symptoms.append(symptoms[:5])

        if diagnostic_summary and len(ctx.diagnostic_summaries) < 3:
            ctx.diagnostic_summaries.append(diagnostic_summary[:500])

    logger.info(f"Found {len(contexts)} unique signatures")
    return contexts


def load_ground_truth() -> List[dict]:
    """Load ground truth dataset."""
    if not GROUND_TRUTH_PATH.exists():
        raise FileNotFoundError(f"Ground truth not found at {GROUND_TRUTH_PATH}")

    with open(GROUND_TRUTH_PATH) as f:
        data = json.load(f)

    return data.get("pairs", [])


def build_embedding_text(
    ctx: SignatureContext,
    strategy: str,
) -> str:
    """
    Build text to embed based on strategy.

    Strategies:
    - A: Signature only (human-readable)
    - B: Signature + symptoms
    - C: Signature + symptoms + diagnostic_summary
    """
    # Base: human-readable signature
    sig_readable = ctx.signature.replace('_', ' ')

    if strategy == "A":
        return sig_readable

    parts = [sig_readable]

    # Add product area and component for context
    if ctx.product_area:
        parts.append(f"Product: {ctx.product_area}")
    if ctx.component:
        parts.append(f"Component: {ctx.component}")

    if strategy in ["B", "C"]:
        # Add symptoms
        if ctx.symptoms:
            flat_symptoms = [s for syms in ctx.symptoms for s in syms][:5]
            if flat_symptoms:
                parts.append(f"Symptoms: {', '.join(flat_symptoms)}")

    if strategy == "C":
        # Add diagnostic summary (most informative)
        if ctx.diagnostic_summaries:
            # Use first summary, it's usually most complete
            parts.append(f"Issue: {ctx.diagnostic_summaries[0][:300]}")

    return " | ".join(parts)


def generate_embeddings(texts: List[str], batch_size: int = 50) -> np.ndarray:
    """Generate embeddings using OpenAI."""
    if not texts:
        return np.array([])

    client = OpenAI()
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        # Truncate long texts
        truncated = [t[:8000] for t in batch]

        logger.info(f"Embedding batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")

        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=truncated,
        )

        batch_embeddings = [data.embedding for data in response.data]
        all_embeddings.extend(batch_embeddings)

    return np.array(all_embeddings)


def cluster_signatures(
    embeddings: np.ndarray,
    distance_threshold: float = 0.4,
) -> np.ndarray:
    """
    Cluster signature embeddings using agglomerative clustering.

    Uses cosine distance (1 - similarity).
    Returns cluster labels for each signature.
    """
    if len(embeddings) < 2:
        return np.array([0] * len(embeddings))

    # Compute cosine distance matrix
    similarity_matrix = cosine_similarity(embeddings)
    distance_matrix = 1 - similarity_matrix

    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric='precomputed',
        linkage='average',
        distance_threshold=distance_threshold,
    )

    labels = clustering.fit_predict(distance_matrix)
    return labels


def evaluate_clustering(
    signatures: List[str],
    cluster_labels: np.ndarray,
    ground_truth: List[dict],
    strategy: str,
    threshold: float,
) -> ClusteringResult:
    """
    Evaluate clustering against ground truth pairs.

    For each ground truth pair:
    - If labeled "same": check if they're in the same cluster
    - If labeled "different": check if they're in different clusters
    """
    # Build signature -> cluster mapping
    sig_to_cluster = {sig: int(label) for sig, label in zip(signatures, cluster_labels)}

    result = ClusteringResult(
        strategy=strategy,
        threshold=threshold,
        n_clusters=len(set(cluster_labels)),
        cluster_assignments=sig_to_cluster,
    )

    result.total_pairs = len(ground_truth)

    for pair in ground_truth:
        sig_a = pair["sig_a"]
        sig_b = pair["sig_b"]
        label = pair["label"]

        # Count by label
        if label == "same":
            result.same_pairs += 1
        elif label == "different":
            result.different_pairs += 1
        else:
            result.ambiguous_pairs += 1

        # Get cluster assignments
        cluster_a = sig_to_cluster.get(sig_a)
        cluster_b = sig_to_cluster.get(sig_b)

        if cluster_a is None or cluster_b is None:
            # Signature not found in Run 95 data
            logger.warning(f"Signature not found: {sig_a if cluster_a is None else sig_b}")
            continue

        same_cluster = (cluster_a == cluster_b)

        # Evaluate based on ground truth
        correct = None
        if label == "same":
            correct = same_cluster
            if correct:
                result.true_positives += 1
            else:
                result.false_negatives += 1
        elif label == "different":
            correct = not same_cluster
            if correct:
                result.true_negatives += 1
            else:
                result.false_positives += 1
        else:  # ambiguous
            if same_cluster:
                result.ambiguous_same_cluster += 1
            else:
                result.ambiguous_different_cluster += 1

        result.pair_results.append({
            "sig_a": sig_a,
            "sig_b": sig_b,
            "ground_truth": label,
            "same_cluster": same_cluster,
            "cluster_a": cluster_a,
            "cluster_b": cluster_b,
            "correct": correct,
        })

    result.compute_metrics()
    return result


def print_results(result: ClusteringResult, show_errors: bool = True):
    """Print results in readable format."""
    print("\n" + "=" * 60)
    print(f"STRATEGY {result.strategy}: threshold={result.threshold}")
    print("=" * 60)

    print(f"\nClustering: {result.n_clusters} clusters from {len(result.cluster_assignments)} signatures")

    print(f"\nDataset:")
    print(f"  Total pairs: {result.total_pairs}")
    print(f"  Same: {result.same_pairs}, Different: {result.different_pairs}, Ambiguous: {result.ambiguous_pairs}")

    print(f"\nConfusion Matrix:")
    print(f"                      Predicted")
    print(f"                   Same Clust | Diff Clust")
    print(f"  Actual Same:        {result.true_positives:3d}     |    {result.false_negatives:3d}")
    print(f"  Actual Diff:        {result.false_positives:3d}     |    {result.true_negatives:3d}")

    print(f"\nMetrics:")
    print(f"  Precision: {result.precision:.2%}")
    print(f"  Recall:    {result.recall:.2%}")
    print(f"  F1 Score:  {result.f1:.2%}")
    print(f"  Accuracy:  {result.accuracy:.2%}")

    if show_errors:
        errors = [r for r in result.pair_results if r.get("correct") is False]
        if errors:
            print(f"\nErrors ({len(errors)} pairs):")
            for e in errors:
                status = "merged (shouldn't)" if e["same_cluster"] else "split (shouldn't)"
                print(f"  {e['sig_a'][:30]}")
                print(f"  {e['sig_b'][:30]}")
                print(f"    → {status} | clusters: {e['cluster_a']}, {e['cluster_b']}")
                print()


def run_prototype(
    contexts: Dict[str, SignatureContext],
    ground_truth: List[dict],
    strategy: str,
    threshold: float,
    dry_run: bool = False,
) -> Optional[ClusteringResult]:
    """
    Run the prototype for a single strategy and threshold.
    """
    logger.info(f"Running strategy {strategy} with threshold {threshold}")

    # Get signatures that appear in ground truth
    gt_signatures = set()
    for pair in ground_truth:
        gt_signatures.add(pair["sig_a"])
        gt_signatures.add(pair["sig_b"])

    # Filter to signatures we have context for
    signatures = [s for s in gt_signatures if s in contexts]
    missing = gt_signatures - set(signatures)
    if missing:
        logger.warning(f"Missing {len(missing)} signatures from Run 95 data")

    if dry_run:
        print(f"\nStrategy {strategy}:")
        print(f"  Would embed {len(signatures)} signatures")
        print(f"  Would evaluate {len(ground_truth)} pairs")
        for sig in list(signatures)[:5]:
            text = build_embedding_text(contexts[sig], strategy)
            print(f"  Example: {text[:100]}...")
        return None

    # Build embedding texts
    sig_list = sorted(signatures)  # Consistent ordering
    texts = [build_embedding_text(contexts[sig], strategy) for sig in sig_list]

    # Generate embeddings
    embeddings = generate_embeddings(texts)

    # Cluster
    labels = cluster_signatures(embeddings, distance_threshold=threshold)

    # Evaluate
    result = evaluate_clustering(sig_list, labels, ground_truth, strategy, threshold)

    return result


def compare_with_baselines(results: List[ClusteringResult]):
    """Print comparison with baseline results."""
    print("\n" + "=" * 70)
    print("COMPARISON WITH BASELINES")
    print("=" * 70)

    # Baselines from session handoff
    baselines = {
        "Embedding (0.85)": {"precision": 1.00, "recall": 0.27, "f1": 0.43, "accuracy": 0.58},
        "LLM": {"precision": 0.45, "recall": 0.45, "f1": 0.45, "accuracy": 0.37},
    }

    print(f"\n{'Method':<25} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Accuracy':<12}")
    print("-" * 70)

    for name, metrics in baselines.items():
        print(f"{name:<25} {metrics['precision']:.2%}        {metrics['recall']:.2%}        {metrics['f1']:.2%}        {metrics['accuracy']:.2%}")

    print("-" * 70)

    for r in results:
        name = f"Strategy {r.strategy} (t={r.threshold})"
        print(f"{name:<25} {r.precision:.2%}        {r.recall:.2%}        {r.f1:.2%}        {r.accuracy:.2%}")

    # Find best result
    best = max(results, key=lambda r: r.f1)
    print(f"\nBest: Strategy {best.strategy} with F1={best.f1:.2%}")

    # Check success criteria
    print("\n" + "=" * 70)
    print("SUCCESS CRITERIA CHECK")
    print("=" * 70)

    target_f1 = 0.58
    print(f"\n1. F1 > {target_f1:.0%}? ", end="")
    if best.f1 > target_f1:
        print(f"✅ YES ({best.f1:.2%})")
    else:
        print(f"❌ NO ({best.f1:.2%})")

    # Check false positives on known LLM failure cases
    llm_failure_pairs = [
        ("pinterest_connection_failure", "pinterest_connection_issue"),
        ("smartpin_image_fetch_failure", "smartpin_image_import_failure"),
        ("scheduling_bulk_delete_drafts", "scheduling_bulk_delete_pins"),
    ]

    print(f"\n2. No false positives on LLM failure cases? ", end="")
    fps = []
    for sig_a, sig_b in llm_failure_pairs:
        for r in best.pair_results:
            if (r["sig_a"] == sig_a and r["sig_b"] == sig_b) or \
               (r["sig_a"] == sig_b and r["sig_b"] == sig_a):
                if r["same_cluster"] and r["ground_truth"] == "different":
                    fps.append((sig_a, sig_b))

    if not fps:
        print("✅ YES")
    else:
        print(f"❌ NO ({len(fps)} false positives)")
        for sig_a, sig_b in fps:
            print(f"   - {sig_a} / {sig_b}")

    print(f"\n3. Recall > 27% (embedding baseline)? ", end="")
    if best.recall > 0.27:
        print(f"✅ YES ({best.recall:.2%})")
    else:
        print(f"❌ NO ({best.recall:.2%})")


def save_results(results: List[ClusteringResult]):
    """Save results to JSON file."""
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "results": [r.to_dict() for r in results],
    }

    with open(RESULTS_PATH, 'w') as f:
        json.dump(data, f, indent=2)

    logger.info(f"Results saved to {RESULTS_PATH}")


def main():
    parser = argparse.ArgumentParser(
        description="Signature embedding clustering prototype",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--strategy', type=str, choices=['A', 'B', 'C', 'all'], default='all',
        help='Embedding strategy: A=sig only, B=+symptoms, C=+diagnostic (default: all)'
    )
    parser.add_argument(
        '--threshold', type=float, default=None,
        help='Distance threshold for clustering (default: test multiple)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be done without running'
    )

    args = parser.parse_args()

    # Load data
    contexts = fetch_signature_contexts(run_id=95)
    ground_truth = load_ground_truth()
    logger.info(f"Loaded {len(ground_truth)} ground truth pairs")

    # Determine strategies and thresholds to test
    strategies = ['A', 'B', 'C'] if args.strategy == 'all' else [args.strategy]
    thresholds = [args.threshold] if args.threshold else [0.30, 0.35, 0.40, 0.45]

    if args.dry_run:
        for strategy in strategies:
            run_prototype(contexts, ground_truth, strategy, 0.4, dry_run=True)
        return

    # Run all combinations
    results = []
    for strategy in strategies:
        for threshold in thresholds:
            result = run_prototype(contexts, ground_truth, strategy, threshold)
            if result:
                results.append(result)
                print_results(result, show_errors=True)

    # Compare with baselines
    if results:
        compare_with_baselines(results)
        save_results(results)


if __name__ == "__main__":
    main()
