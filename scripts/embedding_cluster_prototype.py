#!/usr/bin/env python3
"""
Embedding Clustering Prototype (Hybrid: Embeddings + Facet Extraction)

Compares embedding-based clustering vs signature-based grouping for conversations.
Uses hybrid approach: embeddings for broad clustering, then LLM facet extraction
for fine-grained sub-grouping within clusters.

Usage:
    python scripts/embedding_cluster_prototype.py [--limit N] [--output report.md]
    python scripts/embedding_cluster_prototype.py --hybrid  # Enable facet extraction
"""

import argparse
import json
import logging
import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
from openai import OpenAI

# Clustering
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ConversationFacets:
    """Extracted facets for a conversation."""
    action_type: str  # inquiry, complaint, delete_request, how_to, feature_request, bug_report
    direction: str    # excess, deficit, creation, deletion, modification, performance, neutral
    symptom: str      # Brief description of what user is experiencing
    user_goal: str    # What the user is trying to accomplish


@dataclass
class ConversationData:
    """Data for a single conversation."""
    id: str
    source_body: str  # Full conversation text
    signature: str    # Current issue_signature from theme extraction
    product_area: str
    component: str
    excerpt: Optional[str] = None  # From story_evidence if available
    facets: Optional[ConversationFacets] = None  # Extracted facets for hybrid clustering


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


def fetch_conversations(limit: int = 100) -> List[ConversationData]:
    """
    Fetch conversations with their theme signatures from recent pipeline runs.
    """
    logger.info(f"Fetching up to {limit} conversations with signatures...")

    # Get conversations that have been processed through theme extraction
    query = f"""
    SELECT DISTINCT ON (c.id)
        c.id,
        c.source_body,
        t.issue_signature,
        t.product_area,
        t.component
    FROM conversations c
    JOIN themes t ON t.conversation_id = c.id
    WHERE t.issue_signature IS NOT NULL
      AND c.source_body IS NOT NULL
      AND c.source_body != ''
    ORDER BY c.id, t.extracted_at DESC
    LIMIT {limit}
    """

    rows = run_query(query)

    conversations = []
    for row in rows:
        if len(row) >= 5:
            conversations.append(ConversationData(
                id=row[0],
                source_body=row[1],
                signature=row[2],
                product_area=row[3] or '',
                component=row[4] or '',
            ))

    logger.info(f"Fetched {len(conversations)} conversations")
    return conversations


def fetch_excerpts(conversation_ids: List[str]) -> Dict[str, str]:
    """
    Fetch excerpts from story_evidence for given conversation IDs.
    Returns dict mapping conversation_id -> excerpt.
    """
    if not conversation_ids:
        return {}

    logger.info(f"Fetching excerpts for {len(conversation_ids)} conversations...")

    # story_evidence has conversation_ids as an array, excerpts as jsonb
    query = """
    SELECT conversation_ids, excerpts
    FROM story_evidence
    WHERE excerpts IS NOT NULL
    """

    rows = run_query(query)

    excerpts_map = {}
    for row in rows:
        if len(row) >= 2:
            try:
                conv_ids = json.loads(row[0].replace("'", '"'))  # Array format
                excerpts_json = json.loads(row[1])

                # excerpts is typically {conversation_id: {excerpt: ...}}
                if isinstance(excerpts_json, dict):
                    for cid, data in excerpts_json.items():
                        if cid in conversation_ids:
                            if isinstance(data, dict) and 'excerpt' in data:
                                excerpts_map[cid] = data['excerpt']
                            elif isinstance(data, str):
                                excerpts_map[cid] = data
            except (json.JSONDecodeError, TypeError):
                continue

    logger.info(f"Found excerpts for {len(excerpts_map)} conversations")
    return excerpts_map


def generate_embeddings(texts: List[str], batch_size: int = 50) -> np.ndarray:
    """Generate embeddings for a list of texts using OpenAI."""
    if not texts:
        return np.array([])

    client = OpenAI()
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        # Truncate very long texts
        max_chars = 8000 * 4
        truncated = [t[:max_chars] if len(t) > max_chars else t for t in batch]

        logger.info(f"Generating embeddings for batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")

        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=truncated,
        )

        batch_embeddings = [data.embedding for data in response.data]
        all_embeddings.extend(batch_embeddings)

    return np.array(all_embeddings)


def extract_facets_batch(conversations: List[ConversationData], batch_size: int = 10) -> None:
    """
    Extract facets from conversations using LLM.
    Modifies conversations in place, adding facets attribute.
    """
    client = OpenAI()

    FACET_PROMPT = """Analyze this customer support conversation and extract structured facets.

Conversation:
{conversation}

Extract these facets:
1. action_type: One of [inquiry, complaint, delete_request, how_to_question, feature_request, bug_report, account_change]
2. direction: The polarity/direction of the issue or request. One of:
   - excess: Something is happening too much (duplicates, too many items, spam)
   - deficit: Something is missing or not appearing (items not showing, features not working)
   - creation: User wants to add/create something new
   - deletion: User wants to remove/delete something
   - modification: User wants to change existing behavior or settings
   - performance: Something is slow or degraded
   - neutral: None of the above clearly applies
3. symptom: Brief description (10 words max) of what the user is experiencing or reporting
4. user_goal: What the user is trying to accomplish (10 words max)

Respond in JSON format:
{{"action_type": "...", "direction": "...", "symptom": "...", "user_goal": "..."}}"""

    for i in range(0, len(conversations), batch_size):
        batch = conversations[i:i+batch_size]
        logger.info(f"Extracting facets for batch {i//batch_size + 1}/{(len(conversations)-1)//batch_size + 1}")

        for conv in batch:
            try:
                # Truncate long conversations
                text = conv.source_body[:2000] if len(conv.source_body) > 2000 else conv.source_body

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "user", "content": FACET_PROMPT.format(conversation=text)}
                    ],
                    temperature=0,
                    max_tokens=150,
                )

                content = response.choices[0].message.content.strip()
                # Parse JSON response
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]

                facets_data = json.loads(content)
                conv.facets = ConversationFacets(
                    action_type=facets_data.get("action_type", "unknown"),
                    direction=facets_data.get("direction", "neutral"),
                    symptom=facets_data.get("symptom", "unknown"),
                    user_goal=facets_data.get("user_goal", "unknown"),
                )
            except Exception as e:
                logger.warning(f"Failed to extract facets for {conv.id}: {e}")
                conv.facets = ConversationFacets(
                    action_type="unknown",
                    direction="neutral",
                    symptom="extraction_failed",
                    user_goal="unknown",
                )


def create_hybrid_subclusters(
    conversations: List[ConversationData],
    cluster_labels: np.ndarray,
) -> Dict[int, Dict[str, List[ConversationData]]]:
    """
    Create sub-clusters within each embedding cluster based on facets.
    Returns: {cluster_id: {subcluster_key: [conversations]}}
    """
    # Group by embedding cluster
    cluster_groups = defaultdict(list)
    for conv, label in zip(conversations, cluster_labels):
        cluster_groups[label].append(conv)

    # Sub-cluster by action_type + direction within each cluster
    hybrid_clusters = {}
    for cluster_id, convs in cluster_groups.items():
        subclusters = defaultdict(list)
        for conv in convs:
            if conv.facets:
                # Key by action_type AND direction for finer grouping
                key = f"{conv.facets.action_type} | {conv.facets.direction}"
            else:
                key = "unknown | neutral"
            subclusters[key].append(conv)
        hybrid_clusters[cluster_id] = dict(subclusters)

    return hybrid_clusters


def cluster_embeddings(
    embeddings: np.ndarray,
    n_clusters: Optional[int] = None,
    distance_threshold: float = 0.4
) -> np.ndarray:
    """
    Cluster embeddings using Agglomerative Clustering.

    Uses cosine distance, which works well for text embeddings.
    If n_clusters is None, uses distance_threshold to determine cluster count.
    """
    if len(embeddings) < 2:
        return np.array([0] * len(embeddings))

    # Convert to cosine distance (1 - similarity)
    similarity_matrix = cosine_similarity(embeddings)
    distance_matrix = 1 - similarity_matrix

    clustering = AgglomerativeClustering(
        n_clusters=n_clusters,
        metric='precomputed',
        linkage='average',
        distance_threshold=distance_threshold if n_clusters is None else None,
    )

    labels = clustering.fit_predict(distance_matrix)
    return labels


def evaluate_clustering(
    conversations: List[ConversationData],
    cluster_labels: np.ndarray,
    method_name: str
) -> Dict:
    """
    Evaluate clustering quality by comparing to signature-based grouping.
    """
    # Group by signature (current method)
    signature_groups = defaultdict(list)
    for conv in conversations:
        signature_groups[conv.signature].append(conv.id)

    # Group by cluster (embedding method)
    cluster_groups = defaultdict(list)
    for conv, label in zip(conversations, cluster_labels):
        cluster_groups[label].append(conv.id)

    # Calculate metrics
    n_signatures = len(signature_groups)
    n_clusters = len(cluster_groups)

    # Homogeneity: How often are same-signature items in same cluster?
    same_sig_same_cluster = 0
    same_sig_total = 0
    for sig, conv_ids in signature_groups.items():
        if len(conv_ids) > 1:
            for i, cid1 in enumerate(conv_ids):
                for cid2 in conv_ids[i+1:]:
                    same_sig_total += 1
                    idx1 = next(j for j, c in enumerate(conversations) if c.id == cid1)
                    idx2 = next(j for j, c in enumerate(conversations) if c.id == cid2)
                    if cluster_labels[idx1] == cluster_labels[idx2]:
                        same_sig_same_cluster += 1

    homogeneity = same_sig_same_cluster / same_sig_total if same_sig_total > 0 else 1.0

    return {
        'method': method_name,
        'n_groups': n_clusters,
        'n_signatures': n_signatures,
        'homogeneity_with_signatures': homogeneity,
        'avg_cluster_size': len(conversations) / n_clusters if n_clusters > 0 else 0,
    }


def generate_report(
    conversations: List[ConversationData],
    full_text_labels: np.ndarray,
    excerpt_labels: Optional[np.ndarray],
    full_text_metrics: Dict,
    excerpt_metrics: Optional[Dict],
    hybrid_clusters: Optional[Dict] = None,
) -> str:
    """Generate a human-readable report comparing clustering methods."""

    lines = [
        "# Embedding Clustering Prototype Report",
        f"Generated: {datetime.now().isoformat()}",
        f"Total Conversations: {len(conversations)}",
        "",
        "## Summary Metrics",
        "",
        "| Method | Groups | Homogeneity w/ Signatures | Avg Size |",
        "|--------|--------|---------------------------|----------|",
    ]

    # Signature baseline
    signature_groups = defaultdict(list)
    for conv in conversations:
        signature_groups[conv.signature].append(conv)

    lines.append(f"| Signatures (baseline) | {len(signature_groups)} | 1.00 | {len(conversations)/len(signature_groups):.1f} |")
    lines.append(f"| Full Text Embeddings | {full_text_metrics['n_groups']} | {full_text_metrics['homogeneity_with_signatures']:.2f} | {full_text_metrics['avg_cluster_size']:.1f} |")

    if excerpt_metrics:
        lines.append(f"| Excerpt Embeddings | {excerpt_metrics['n_groups']} | {excerpt_metrics['homogeneity_with_signatures']:.2f} | {excerpt_metrics['avg_cluster_size']:.1f} |")

    lines.extend([
        "",
        "## Signature Groups (Current Method)",
        "",
    ])

    # Show signature groups with sample content
    for sig, convs in sorted(signature_groups.items(), key=lambda x: -len(x[1]))[:10]:
        lines.append(f"### `{sig}` ({len(convs)} conversations)")
        lines.append("")
        for conv in convs[:3]:  # Show first 3
            snippet = conv.source_body[:200].replace('\n', ' ')
            lines.append(f"- **{conv.id[:8]}...**: {snippet}...")
        if len(convs) > 3:
            lines.append(f"- _{len(convs)-3} more..._")
        lines.append("")

    # Show embedding clusters (full text)
    lines.extend([
        "## Full Text Embedding Clusters",
        "",
    ])

    cluster_groups = defaultdict(list)
    for conv, label in zip(conversations, full_text_labels):
        cluster_groups[label].append(conv)

    for label, convs in sorted(cluster_groups.items(), key=lambda x: -len(x[1]))[:10]:
        # Get signature distribution in this cluster
        sig_dist = defaultdict(int)
        for conv in convs:
            sig_dist[conv.signature] += 1
        sig_summary = ", ".join(f"{s}({c})" for s, c in sorted(sig_dist.items(), key=lambda x: -x[1])[:3])

        lines.append(f"### Cluster {label} ({len(convs)} conversations)")
        lines.append(f"**Signatures**: {sig_summary}")
        lines.append("")
        for conv in convs[:3]:
            snippet = conv.source_body[:200].replace('\n', ' ')
            lines.append(f"- **{conv.id[:8]}** [{conv.signature}]: {snippet}...")
        if len(convs) > 3:
            lines.append(f"- _{len(convs)-3} more..._")
        lines.append("")

    # If excerpt clustering was done, show comparison
    if excerpt_labels is not None:
        lines.extend([
            "## Excerpt Embedding Clusters",
            "",
        ])

        excerpt_cluster_groups = defaultdict(list)
        for conv, label in zip(conversations, excerpt_labels):
            excerpt_cluster_groups[label].append(conv)

        for label, convs in sorted(excerpt_cluster_groups.items(), key=lambda x: -len(x[1]))[:10]:
            sig_dist = defaultdict(int)
            for conv in convs:
                sig_dist[conv.signature] += 1
            sig_summary = ", ".join(f"{s}({c})" for s, c in sorted(sig_dist.items(), key=lambda x: -x[1])[:3])

            lines.append(f"### Cluster {label} ({len(convs)} conversations)")
            lines.append(f"**Signatures**: {sig_summary}")
            lines.append("")
            for conv in convs[:3]:
                text = conv.excerpt or conv.source_body
                snippet = text[:200].replace('\n', ' ')
                lines.append(f"- **{conv.id[:8]}** [{conv.signature}]: {snippet}...")
            if len(convs) > 3:
                lines.append(f"- _{len(convs)-3} more..._")
            lines.append("")

    # Hybrid clusters section (if available)
    if hybrid_clusters:
        lines.extend([
            "## Hybrid Clusters (Embeddings + Facet Sub-grouping)",
            "",
            "Each embedding cluster is further split by action_type facet.",
            "",
        ])

        # Count total sub-clusters
        total_subclusters = sum(len(subs) for subs in hybrid_clusters.values())
        lines.append(f"**Total sub-clusters: {total_subclusters}** (from {len(hybrid_clusters)} embedding clusters)")
        lines.append("")

        # Sort clusters by total size
        sorted_clusters = sorted(
            hybrid_clusters.items(),
            key=lambda x: sum(len(convs) for convs in x[1].values()),
            reverse=True
        )

        for cluster_id, subclusters in sorted_clusters[:15]:  # Show top 15
            total_in_cluster = sum(len(convs) for convs in subclusters.values())
            lines.append(f"### Embedding Cluster {cluster_id} ({total_in_cluster} total)")
            lines.append("")

            for action_type, convs in sorted(subclusters.items(), key=lambda x: -len(x[1])):
                lines.append(f"#### → {action_type} ({len(convs)} conversations)")

                # Show facet details for each conversation
                for conv in convs[:3]:
                    snippet = conv.source_body[:150].replace('\n', ' ')
                    facet_info = ""
                    if conv.facets:
                        facet_info = f" | dir: {conv.facets.direction} | {conv.facets.symptom}"
                    lines.append(f"- **{conv.id[:8]}** [{conv.signature}]{facet_info}")
                    lines.append(f"  > {snippet}...")

                if len(convs) > 3:
                    lines.append(f"- _{len(convs)-3} more..._")
                lines.append("")

    # Key observations section
    lines.extend([
        "## Key Observations",
        "",
        "### Where Embeddings Differ from Signatures",
        "",
    ])

    # Find cases where same signature got split into different clusters
    for sig, convs in signature_groups.items():
        if len(convs) >= 2:
            cluster_dist = defaultdict(list)
            for conv in convs:
                idx = next(j for j, c in enumerate(conversations) if c.id == conv.id)
                cluster_dist[full_text_labels[idx]].append(conv)

            if len(cluster_dist) > 1:
                lines.append(f"**Signature `{sig}` split into {len(cluster_dist)} clusters:**")
                for cluster_id, cluster_convs in cluster_dist.items():
                    lines.append(f"  - Cluster {cluster_id}: {len(cluster_convs)} conversations")
                    for conv in cluster_convs[:2]:
                        snippet = conv.source_body[:150].replace('\n', ' ')
                        lines.append(f"    - {snippet}...")
                lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Embedding clustering prototype")
    parser.add_argument('--limit', type=int, default=100, help='Max conversations to analyze')
    parser.add_argument('--output', type=str, default='embedding_cluster_report.md', help='Output report path')
    parser.add_argument('--distance-threshold', type=float, default=0.4, help='Clustering distance threshold')
    parser.add_argument('--hybrid', action='store_true', help='Enable hybrid mode with facet extraction')
    args = parser.parse_args()

    # Fetch data
    conversations = fetch_conversations(limit=args.limit)

    if len(conversations) < 10:
        logger.error("Not enough conversations for meaningful analysis")
        return

    # Fetch excerpts
    conv_ids = [c.id for c in conversations]
    excerpts_map = fetch_excerpts(conv_ids)

    # Add excerpts to conversations
    for conv in conversations:
        conv.excerpt = excerpts_map.get(conv.id)

    has_excerpts = sum(1 for c in conversations if c.excerpt)
    logger.info(f"{has_excerpts}/{len(conversations)} conversations have excerpts")

    # Generate full text embeddings
    logger.info("Generating full text embeddings...")
    full_texts = [c.source_body for c in conversations]
    full_text_embeddings = generate_embeddings(full_texts)

    # Cluster full text embeddings
    logger.info("Clustering full text embeddings...")
    full_text_labels = cluster_embeddings(
        full_text_embeddings,
        distance_threshold=args.distance_threshold
    )
    full_text_metrics = evaluate_clustering(conversations, full_text_labels, "Full Text")

    # Generate and cluster excerpt embeddings if available
    excerpt_labels = None
    excerpt_metrics = None

    if has_excerpts > len(conversations) * 0.3:  # At least 30% have excerpts
        logger.info("Generating excerpt embeddings...")
        # Use excerpt if available, otherwise fall back to first 500 chars of source_body
        excerpt_texts = [c.excerpt or c.source_body[:500] for c in conversations]
        excerpt_embeddings = generate_embeddings(excerpt_texts)

        logger.info("Clustering excerpt embeddings...")
        excerpt_labels = cluster_embeddings(
            excerpt_embeddings,
            distance_threshold=args.distance_threshold
        )
        excerpt_metrics = evaluate_clustering(conversations, excerpt_labels, "Excerpts")
    else:
        logger.info("Not enough excerpts for comparison, using first 500 chars as excerpt proxy...")
        excerpt_texts = [c.source_body[:500] for c in conversations]
        excerpt_embeddings = generate_embeddings(excerpt_texts)

        logger.info("Clustering excerpt proxy embeddings...")
        excerpt_labels = cluster_embeddings(
            excerpt_embeddings,
            distance_threshold=args.distance_threshold
        )
        excerpt_metrics = evaluate_clustering(conversations, excerpt_labels, "Excerpts (500 chars)")

    # Hybrid mode: extract facets and create sub-clusters
    hybrid_clusters = None
    if args.hybrid:
        logger.info("Hybrid mode: extracting facets for sub-clustering...")
        extract_facets_batch(conversations)

        logger.info("Creating hybrid sub-clusters...")
        hybrid_clusters = create_hybrid_subclusters(conversations, full_text_labels)

        # Count sub-clusters
        total_subclusters = sum(len(subs) for subs in hybrid_clusters.values())
        logger.info(f"Created {total_subclusters} hybrid sub-clusters from {len(hybrid_clusters)} embedding clusters")

    # Generate report
    logger.info("Generating report...")
    report = generate_report(
        conversations,
        full_text_labels,
        excerpt_labels,
        full_text_metrics,
        excerpt_metrics,
        hybrid_clusters=hybrid_clusters,
    )

    # Save report
    output_path = args.output
    if not output_path.startswith('/'):
        output_path = os.path.join(os.path.dirname(__file__), '..', output_path)

    with open(output_path, 'w') as f:
        f.write(report)

    logger.info(f"Report saved to {output_path}")

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Conversations analyzed: {len(conversations)}")
    print(f"Unique signatures: {full_text_metrics['n_signatures']}")
    print(f"Full text clusters: {full_text_metrics['n_groups']}")
    if excerpt_metrics:
        print(f"Excerpt clusters: {excerpt_metrics['n_groups']}")
    if hybrid_clusters:
        total_subclusters = sum(len(subs) for subs in hybrid_clusters.values())
        print(f"Hybrid sub-clusters: {total_subclusters}")
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
