#!/usr/bin/env python3
"""
Signature Ground Truth Labeling Tool (Issue #152)

Creates a ground truth dataset for validating signature canonicalization approaches.
Identifies candidate duplicate signature pairs and presents them for human labeling.

Candidate identification strategies:
1. String similarity (Levenshtein) - catches typos, underscore variations
2. Embedding similarity - catches semantic equivalence
3. Same-prefix grouping - catches fragmentation within product areas

Usage:
    # Identify candidates and start labeling
    python scripts/signature_ground_truth.py --run-id 95

    # Resume labeling from existing file
    python scripts/signature_ground_truth.py --run-id 95 --resume

    # Generate candidates only (no labeling)
    python scripts/signature_ground_truth.py --run-id 95 --candidates-only

    # Show stats on existing ground truth
    python scripts/signature_ground_truth.py --stats
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Output paths
DATA_DIR = Path(__file__).parent.parent / "data"
GROUND_TRUTH_PATH = DATA_DIR / "signature_ground_truth.json"
CANDIDATES_PATH = DATA_DIR / "signature_candidates.json"


@dataclass
class SignatureContext:
    """Context for a signature from themes."""
    signature: str
    count: int
    product_area: str
    component: str
    # Aggregated from all themes with this signature
    sample_intents: List[str] = field(default_factory=list)
    sample_symptoms: List[List[str]] = field(default_factory=list)
    sample_summaries: List[str] = field(default_factory=list)
    conversation_ids: List[str] = field(default_factory=list)


@dataclass
class CandidatePair:
    """A candidate pair of signatures that might be duplicates."""
    sig_a: str
    sig_b: str
    string_similarity: float
    embedding_similarity: Optional[float] = None
    same_prefix: bool = False
    # Context for review
    context_a: Optional[SignatureContext] = None
    context_b: Optional[SignatureContext] = None
    # Combined score for ranking
    combined_score: float = 0.0


@dataclass
class LabeledPair:
    """A human-labeled signature pair."""
    sig_a: str
    sig_b: str
    label: str  # "same", "different", "ambiguous"
    reasoning: str
    confidence: str  # "high", "medium", "low"
    labeled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class GroundTruthDataset:
    """The complete ground truth dataset."""
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    run_id: int = 95
    labeled_by: str = "human"
    pairs: List[LabeledPair] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "run_id": self.run_id,
            "labeled_by": self.labeled_by,
            "pairs": [asdict(p) for p in self.pairs]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GroundTruthDataset":
        pairs = [LabeledPair(**p) for p in data.get("pairs", [])]
        return cls(
            version=data.get("version", "1.0"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            run_id=data.get("run_id", 95),
            labeled_by=data.get("labeled_by", "human"),
            pairs=pairs
        )


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


def fetch_signature_contexts(run_id: int) -> Dict[str, SignatureContext]:
    """
    Fetch all signatures with their context from a pipeline run.

    Returns dict mapping signature -> SignatureContext with aggregated info.
    """
    logger.info(f"Fetching signatures from run {run_id}...")

    query = f"""
    SELECT
        issue_signature,
        product_area,
        component,
        user_intent,
        symptoms::text,
        diagnostic_summary,
        conversation_id
    FROM themes
    WHERE pipeline_run_id = {run_id}
      AND issue_signature IS NOT NULL
    ORDER BY issue_signature
    """

    rows = run_query(query)

    # Aggregate by signature
    contexts: Dict[str, SignatureContext] = {}

    for row in rows:
        if len(row) < 7:
            continue

        sig = row[0]
        product_area = row[1] or ""
        component = row[2] or ""
        user_intent = row[3] or ""
        symptoms_json = row[4] or "[]"
        diagnostic_summary = row[5] or ""
        conv_id = row[6] or ""

        # Parse symptoms JSON
        try:
            symptoms = json.loads(symptoms_json) if symptoms_json else []
        except json.JSONDecodeError:
            symptoms = []

        if sig not in contexts:
            contexts[sig] = SignatureContext(
                signature=sig,
                count=0,
                product_area=product_area,
                component=component,
            )

        ctx = contexts[sig]
        ctx.count += 1

        if user_intent and len(ctx.sample_intents) < 3:
            ctx.sample_intents.append(user_intent[:200])

        if symptoms and len(ctx.sample_symptoms) < 3:
            ctx.sample_symptoms.append(symptoms[:5])

        if diagnostic_summary and len(ctx.sample_summaries) < 3:
            ctx.sample_summaries.append(diagnostic_summary[:300])

        if conv_id and len(ctx.conversation_ids) < 5:
            ctx.conversation_ids.append(conv_id)

    logger.info(f"Found {len(contexts)} unique signatures")
    return contexts


def string_similarity(a: str, b: str) -> float:
    """
    Compute string similarity using SequenceMatcher.
    Returns 0.0-1.0 where 1.0 is identical.
    """
    return SequenceMatcher(None, a, b).ratio()


def get_signature_prefix(sig: str, depth: int = 2) -> str:
    """Extract first N components of a signature."""
    parts = sig.split('_')
    return '_'.join(parts[:depth])


def compute_embedding_similarities(
    signatures: List[str],
    contexts: Dict[str, SignatureContext],
    batch_size: int = 50
) -> Dict[Tuple[str, str], float]:
    """
    Compute embedding similarities for signatures using their context.

    Embeds: signature + product_area + sample symptoms + sample summary
    Returns dict mapping (sig_a, sig_b) -> similarity score
    """
    from openai import OpenAI

    logger.info(f"Computing embeddings for {len(signatures)} signatures...")

    client = OpenAI()

    # Build text for each signature
    sig_texts = {}
    for sig in signatures:
        ctx = contexts.get(sig)
        if ctx:
            # Combine signature with context
            parts = [
                sig.replace('_', ' '),
                f"Product: {ctx.product_area}",
                f"Component: {ctx.component}",
            ]

            if ctx.sample_symptoms:
                flat_symptoms = [s for syms in ctx.sample_symptoms for s in syms][:5]
                parts.append(f"Symptoms: {', '.join(flat_symptoms)}")

            if ctx.sample_summaries:
                parts.append(f"Summary: {ctx.sample_summaries[0][:200]}")

            sig_texts[sig] = " | ".join(parts)
        else:
            sig_texts[sig] = sig.replace('_', ' ')

    # Generate embeddings in batches
    embeddings = {}
    sig_list = list(sig_texts.keys())

    for i in range(0, len(sig_list), batch_size):
        batch_sigs = sig_list[i:i+batch_size]
        batch_texts = [sig_texts[s] for s in batch_sigs]

        # Truncate long texts
        batch_texts = [t[:8000] for t in batch_texts]

        logger.info(f"Embedding batch {i//batch_size + 1}/{(len(sig_list)-1)//batch_size + 1}")

        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch_texts,
        )

        for j, data in enumerate(response.data):
            embeddings[batch_sigs[j]] = np.array(data.embedding)

    # Compute pairwise similarities (only for pairs with string sim > 0.5 to save time)
    logger.info("Computing pairwise embedding similarities...")
    similarities = {}

    for i, sig_a in enumerate(sig_list):
        for sig_b in sig_list[i+1:]:
            # Only compute embedding similarity if string similarity > 0.5
            # or if they share a prefix
            str_sim = string_similarity(sig_a, sig_b)
            same_prefix = get_signature_prefix(sig_a) == get_signature_prefix(sig_b)

            if str_sim > 0.5 or same_prefix:
                emb_a = embeddings[sig_a]
                emb_b = embeddings[sig_b]

                # Cosine similarity
                sim = np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b))
                similarities[(sig_a, sig_b)] = float(sim)

    logger.info(f"Computed {len(similarities)} embedding similarities")
    return similarities


def identify_candidate_pairs(
    contexts: Dict[str, SignatureContext],
    string_threshold: float = 0.6,
    embedding_threshold: float = 0.80,
    compute_embeddings: bool = True,
) -> List[CandidatePair]:
    """
    Identify candidate duplicate pairs using multiple strategies.

    Returns list of CandidatePair sorted by combined score (most likely duplicates first).
    """
    signatures = list(contexts.keys())
    logger.info(f"Identifying candidates from {len(signatures)} signatures...")

    # Compute embedding similarities if requested
    embedding_sims = {}
    if compute_embeddings:
        embedding_sims = compute_embedding_similarities(signatures, contexts)

    # Find candidate pairs
    candidates = []
    seen_pairs = set()

    for i, sig_a in enumerate(signatures):
        for sig_b in signatures[i+1:]:
            # Normalize pair order
            pair_key = tuple(sorted([sig_a, sig_b]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Compute string similarity
            str_sim = string_similarity(sig_a, sig_b)

            # Check same prefix
            same_prefix = get_signature_prefix(sig_a) == get_signature_prefix(sig_b)

            # Get embedding similarity
            emb_sim = embedding_sims.get((sig_a, sig_b)) or embedding_sims.get((sig_b, sig_a))

            # Determine if this is a candidate
            is_candidate = False

            # Strategy 1: High string similarity
            if str_sim >= string_threshold:
                is_candidate = True

            # Strategy 2: High embedding similarity
            if emb_sim is not None and emb_sim >= embedding_threshold:
                is_candidate = True

            # Strategy 3: Same prefix (always include for review)
            if same_prefix and str_sim >= 0.4:
                is_candidate = True

            if is_candidate:
                # Compute combined score for ranking
                combined = str_sim * 0.3
                if emb_sim is not None:
                    combined += emb_sim * 0.5
                if same_prefix:
                    combined += 0.2

                candidates.append(CandidatePair(
                    sig_a=sig_a,
                    sig_b=sig_b,
                    string_similarity=str_sim,
                    embedding_similarity=emb_sim,
                    same_prefix=same_prefix,
                    context_a=contexts.get(sig_a),
                    context_b=contexts.get(sig_b),
                    combined_score=combined,
                ))

    # Sort by combined score (highest first = most likely duplicates)
    candidates.sort(key=lambda c: c.combined_score, reverse=True)

    logger.info(f"Identified {len(candidates)} candidate pairs")
    return candidates


def display_pair_for_labeling(pair: CandidatePair, index: int, total: int) -> None:
    """Display a candidate pair for human review."""
    print("\n" + "=" * 70)
    print(f"PAIR {index + 1} of {total}")
    print("=" * 70)

    print(f"\n📊 Similarity Scores:")
    print(f"   String: {pair.string_similarity:.2f}")
    if pair.embedding_similarity:
        print(f"   Embedding: {pair.embedding_similarity:.2f}")
    print(f"   Same prefix: {'Yes' if pair.same_prefix else 'No'}")
    print(f"   Combined: {pair.combined_score:.2f}")

    # Signature A
    print(f"\n🔹 SIGNATURE A: {pair.sig_a}")
    if pair.context_a:
        ctx = pair.context_a
        print(f"   Count: {ctx.count} | Area: {ctx.product_area} | Component: {ctx.component}")
        if ctx.sample_intents:
            print(f"   Intent: {ctx.sample_intents[0][:100]}...")
        if ctx.sample_symptoms:
            print(f"   Symptoms: {ctx.sample_symptoms[0][:3]}")
        if ctx.sample_summaries:
            print(f"   Summary: {ctx.sample_summaries[0][:150]}...")

    # Signature B
    print(f"\n🔸 SIGNATURE B: {pair.sig_b}")
    if pair.context_b:
        ctx = pair.context_b
        print(f"   Count: {ctx.count} | Area: {ctx.product_area} | Component: {ctx.component}")
        if ctx.sample_intents:
            print(f"   Intent: {ctx.sample_intents[0][:100]}...")
        if ctx.sample_symptoms:
            print(f"   Symptoms: {ctx.sample_symptoms[0][:3]}")
        if ctx.sample_summaries:
            print(f"   Summary: {ctx.sample_summaries[0][:150]}...")

    print("\n" + "-" * 70)


def get_label_input() -> Tuple[str, str, str]:
    """Get label input from user. Returns (label, reasoning, confidence)."""
    print("\nLabel options:")
    print("  [s] SAME - These should be merged (one fix would address both)")
    print("  [d] DIFFERENT - These are distinct issues")
    print("  [a] AMBIGUOUS - Unclear, needs more context")
    print("  [k] SKIP - Skip this pair for now")
    print("  [q] QUIT - Save and exit")

    while True:
        choice = input("\nYour choice [s/d/a/k/q]: ").strip().lower()

        if choice == 'q':
            return 'quit', '', ''

        if choice == 'k':
            return 'skip', '', ''

        if choice in ['s', 'd', 'a']:
            label_map = {'s': 'same', 'd': 'different', 'a': 'ambiguous'}
            label = label_map[choice]

            reasoning = input("Brief reasoning (optional): ").strip()

            conf_input = input("Confidence [h]igh/[m]edium/[l]ow (default: medium): ").strip().lower()
            conf_map = {'h': 'high', 'm': 'medium', 'l': 'low', '': 'medium'}
            confidence = conf_map.get(conf_input, 'medium')

            return label, reasoning, confidence

        print("Invalid choice. Please enter s, d, a, k, or q.")


def run_labeling_session(
    candidates: List[CandidatePair],
    existing_dataset: Optional[GroundTruthDataset] = None,
    run_id: int = 95,
) -> GroundTruthDataset:
    """Run interactive labeling session."""
    # Initialize or use existing dataset
    if existing_dataset:
        dataset = existing_dataset
        # Get already-labeled pairs
        labeled_keys = {(p.sig_a, p.sig_b) for p in dataset.pairs}
        labeled_keys |= {(p.sig_b, p.sig_a) for p in dataset.pairs}
    else:
        dataset = GroundTruthDataset(run_id=run_id)
        labeled_keys = set()

    # Filter out already-labeled pairs
    remaining = [
        c for c in candidates
        if (c.sig_a, c.sig_b) not in labeled_keys and (c.sig_b, c.sig_a) not in labeled_keys
    ]

    if not remaining:
        print("\n✅ All candidate pairs have been labeled!")
        return dataset

    print(f"\n📝 Starting labeling session")
    print(f"   Candidates to label: {len(remaining)}")
    print(f"   Already labeled: {len(dataset.pairs)}")
    print("\n   Press Ctrl+C at any time to save and exit.\n")

    try:
        for i, pair in enumerate(remaining):
            display_pair_for_labeling(pair, i, len(remaining))

            label, reasoning, confidence = get_label_input()

            if label == 'quit':
                print("\nSaving and exiting...")
                break

            if label == 'skip':
                print("Skipped.")
                continue

            # Add labeled pair
            labeled_pair = LabeledPair(
                sig_a=pair.sig_a,
                sig_b=pair.sig_b,
                label=label,
                reasoning=reasoning,
                confidence=confidence,
            )
            dataset.pairs.append(labeled_pair)

            print(f"✓ Labeled as: {label.upper()}")

            # Save after each label (in case of crash)
            dataset.updated_at = datetime.utcnow().isoformat()
            save_ground_truth(dataset)

    except KeyboardInterrupt:
        print("\n\nInterrupted. Saving progress...")

    return dataset


def save_ground_truth(dataset: GroundTruthDataset) -> None:
    """Save ground truth dataset to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(GROUND_TRUTH_PATH, 'w') as f:
        json.dump(dataset.to_dict(), f, indent=2)

    logger.info(f"Saved {len(dataset.pairs)} labeled pairs to {GROUND_TRUTH_PATH}")


def load_ground_truth() -> Optional[GroundTruthDataset]:
    """Load existing ground truth dataset if it exists."""
    if not GROUND_TRUTH_PATH.exists():
        return None

    with open(GROUND_TRUTH_PATH) as f:
        data = json.load(f)

    return GroundTruthDataset.from_dict(data)


def save_candidates(candidates: List[CandidatePair]) -> None:
    """Save candidate pairs to file for inspection."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_candidates": len(candidates),
        "candidates": [
            {
                "sig_a": c.sig_a,
                "sig_b": c.sig_b,
                "string_similarity": c.string_similarity,
                "embedding_similarity": c.embedding_similarity,
                "same_prefix": c.same_prefix,
                "combined_score": c.combined_score,
            }
            for c in candidates
        ]
    }

    with open(CANDIDATES_PATH, 'w') as f:
        json.dump(data, f, indent=2)

    logger.info(f"Saved {len(candidates)} candidates to {CANDIDATES_PATH}")


def show_stats() -> None:
    """Show statistics about existing ground truth dataset."""
    dataset = load_ground_truth()

    if not dataset:
        print("No ground truth dataset found.")
        return

    print("\n" + "=" * 50)
    print("GROUND TRUTH DATASET STATISTICS")
    print("=" * 50)

    print(f"\nVersion: {dataset.version}")
    print(f"Run ID: {dataset.run_id}")
    print(f"Created: {dataset.created_at}")
    print(f"Updated: {dataset.updated_at}")
    print(f"\nTotal labeled pairs: {len(dataset.pairs)}")

    # Count by label
    label_counts = {}
    confidence_counts = {}

    for p in dataset.pairs:
        label_counts[p.label] = label_counts.get(p.label, 0) + 1
        confidence_counts[p.confidence] = confidence_counts.get(p.confidence, 0) + 1

    print("\nBy label:")
    for label, count in sorted(label_counts.items()):
        print(f"  {label}: {count}")

    print("\nBy confidence:")
    for conf, count in sorted(confidence_counts.items()):
        print(f"  {conf}: {count}")

    # Show some examples
    print("\nRecent labels:")
    for p in dataset.pairs[-5:]:
        print(f"  {p.sig_a} <-> {p.sig_b}: {p.label}")
        if p.reasoning:
            print(f"    Reason: {p.reasoning}")


def main():
    parser = argparse.ArgumentParser(
        description="Signature ground truth labeling tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--run-id', type=int, default=95,
        help='Pipeline run ID to analyze (default: 95)'
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='Resume labeling from existing ground truth file'
    )
    parser.add_argument(
        '--candidates-only', action='store_true',
        help='Generate candidates only, do not start labeling'
    )
    parser.add_argument(
        '--stats', action='store_true',
        help='Show statistics about existing ground truth'
    )
    parser.add_argument(
        '--no-embeddings', action='store_true',
        help='Skip embedding computation (faster but less accurate)'
    )
    parser.add_argument(
        '--string-threshold', type=float, default=0.6,
        help='String similarity threshold (default: 0.6)'
    )
    parser.add_argument(
        '--embedding-threshold', type=float, default=0.80,
        help='Embedding similarity threshold (default: 0.80)'
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    # Fetch signature contexts
    contexts = fetch_signature_contexts(args.run_id)

    if not contexts:
        print("No signatures found for this run.")
        return

    # Identify candidate pairs
    candidates = identify_candidate_pairs(
        contexts,
        string_threshold=args.string_threshold,
        embedding_threshold=args.embedding_threshold,
        compute_embeddings=not args.no_embeddings,
    )

    # Save candidates
    save_candidates(candidates)

    if args.candidates_only:
        print(f"\n✅ Generated {len(candidates)} candidate pairs")
        print(f"   Saved to: {CANDIDATES_PATH}")

        # Show top 10
        print("\nTop 10 candidates:")
        for i, c in enumerate(candidates[:10]):
            print(f"  {i+1}. {c.sig_a} <-> {c.sig_b}")
            print(f"      String: {c.string_similarity:.2f}, Emb: {c.embedding_similarity or 0:.2f}, Combined: {c.combined_score:.2f}")
        return

    # Load existing dataset if resuming
    existing_dataset = None
    if args.resume:
        existing_dataset = load_ground_truth()
        if existing_dataset:
            print(f"Resuming from existing dataset with {len(existing_dataset.pairs)} labels")

    # Run labeling session
    dataset = run_labeling_session(candidates, existing_dataset, args.run_id)

    # Final save
    save_ground_truth(dataset)

    print(f"\n✅ Labeling session complete!")
    print(f"   Total labeled: {len(dataset.pairs)}")
    print(f"   Saved to: {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
