#!/usr/bin/env python3
"""
Run coherence evaluation on frozen artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import importlib.util
import math
import re
from typing import Dict, List, Optional, Tuple
import inspect

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

_hybrid_path = ROOT / "src" / "services" / "hybrid_clustering_service.py"
HybridClusteringService = None

try:
    from src.story_tracking.services.pm_review_service import (
        PMReviewService,
        ReviewDecision,
        ConversationContext,
    )
    PM_REVIEW_AVAILABLE = True
except Exception:
    PM_REVIEW_AVAILABLE = False
    PMReviewService = None
    ReviewDecision = None
    ConversationContext = None


MIN_GROUP_SIZE = 3
DEFAULT_SIMILARITY_THRESHOLD = 0.5
EVIDENCE_WEIGHT = float(os.environ.get("EVIDENCE_WEIGHT", "0.0"))
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "have", "has", "was", "were",
    "into", "onto", "about", "your", "you", "but", "not", "are", "can", "cannot",
    "how", "what", "why", "when", "where", "who", "which", "a", "an", "to", "of",
    "in", "on", "is", "it", "as", "at", "by", "or", "if", "be", "we", "our",
}


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # psql row_to_json output can contain double-escaped quotes (\\"),
                # which is invalid JSON. Collapse to a single escape and retry.
                fixed = line.replace("\\\\\"", "\\\"")
                rows.append(json.loads(fixed))
    return rows


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True))


def _build_pack_index(manifest: dict) -> Dict[str, str]:
    pack_by_conv: Dict[str, str] = {}
    for pack in manifest.get("packs", []):
        pack_id = pack.get("pack_id")
        for cid in pack.get("conversation_ids", []):
            pack_by_conv[str(cid)] = pack_id
    return pack_by_conv


def _build_shared_error_index(manifest: dict) -> Dict[str, Optional[str]]:
    errors = {}
    for pack in manifest.get("packs", []):
        errors[pack.get("pack_id")] = pack.get("shared_error")
    return errors


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)

def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _evidence_tokens(theme: dict, convo: dict) -> List[str]:
    parts: List[str] = []
    if theme:
        for key in ("user_intent", "affected_flow"):
            value = theme.get(key) or ""
            if isinstance(value, str):
                parts.append(value)
        symptoms = theme.get("symptoms") or []
        if isinstance(symptoms, list):
            parts.append(" ".join(str(s) for s in symptoms))
    if convo:
        digest = convo.get("customer_digest") or ""
        if isinstance(digest, str):
            parts.append(digest)
    return _tokenize(" ".join(parts))


def _simple_cluster(
    embeddings_by_id: Dict[str, List[float]],
    conv_ids: List[str],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> List[List[str]]:
    # Greedy clustering by cosine similarity to a running centroid.
    clusters: List[List[str]] = []
    centroids: List[List[float]] = []

    for cid in conv_ids:
        vec = embeddings_by_id.get(cid)
        if not vec:
            continue
        best_idx = None
        best_sim = -1.0
        for idx, centroid in enumerate(centroids):
            sim = _cosine_similarity(vec, centroid)
            if sim > best_sim:
                best_sim = sim
                best_idx = idx
        if best_idx is not None and best_sim >= threshold:
            clusters[best_idx].append(cid)
            # Update centroid (simple mean)
            centroid = centroids[best_idx]
            count = len(clusters[best_idx])
            centroids[best_idx] = [
                (c * (count - 1) + v) / count for c, v in zip(centroid, vec)
            ]
        else:
            clusters.append([cid])
            centroids.append(list(vec))
    return clusters


def _group_conversations(
    embeddings: List[dict],
    facets: List[dict],
    conv_ids: List[str],
    pm_review: bool,
    theme_by_conv: Dict[str, dict],
    convo_by_id: Dict[str, dict],
) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}

    global HybridClusteringService
    if HybridClusteringService is None:
        try:
            spec = importlib.util.spec_from_file_location(
                "hybrid_clustering_service", _hybrid_path
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Failed to load hybrid_clustering_service module")
            hybrid_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(hybrid_module)
            HybridClusteringService = hybrid_module.HybridClusteringService
        except Exception:
            HybridClusteringService = None

    if HybridClusteringService is None:
        # Fallback clustering when sklearn is unavailable.
        if os.environ.get("COHERENCE_EVAL_STRICT") == "1":
            raise RuntimeError("HybridClusteringService unavailable; strict mode requires sklearn.")
        embeddings_by_id: Dict[str, List[float]] = {}
        for row in embeddings:
            cid = str(row.get("conversation_id"))
            vec = row.get("embedding")
            if isinstance(vec, str):
                vec = json.loads(vec)
            if vec:
                embeddings_by_id[cid] = vec

        facet_by_id: Dict[str, Tuple[str, str]] = {}
        for row in facets:
            cid = str(row.get("conversation_id"))
            action = row.get("action_type") or "unknown"
            direction = row.get("direction") or "unknown"
            facet_by_id[cid] = (action, direction)

        buckets: Dict[Tuple[str, str], List[str]] = {}
        for cid in conv_ids:
            buckets.setdefault(facet_by_id.get(cid, ("unknown", "unknown")), []).append(cid)

        cluster_idx = 0
        for (action, direction), ids in buckets.items():
            for cluster in _simple_cluster(embeddings_by_id, ids):
                group_id = f"emb_simple_{cluster_idx}_facet_{action}_{direction}"
                groups[group_id] = cluster
                cluster_idx += 1
        # Skip PM review in fallback mode to avoid reintroducing unavailable deps.
        return groups

    service = HybridClusteringService()
    if hasattr(service, "cluster_from_data"):
        result = service.cluster_from_data(embeddings, facets, conversation_ids=conv_ids)
    elif hasattr(service, "cluster_with_data"):
        # Filter inputs for API
        allowed = set(conv_ids)
        filtered_embeddings = [e for e in embeddings if str(e.get("conversation_id")) in allowed]
        filtered_facets = [f for f in facets if str(f.get("conversation_id")) in allowed]
        # Pass themes if available (enables product_area splitting)
        themes_list = [theme_by_conv[cid] for cid in conv_ids if cid in theme_by_conv]
        try:
            params = inspect.signature(service.cluster_with_data).parameters
        except (TypeError, ValueError):
            params = {}
        if "themes" in params:
            result = service.cluster_with_data(
                filtered_embeddings, filtered_facets, themes=themes_list
            )
        else:
            result = service.cluster_with_data(filtered_embeddings, filtered_facets)
    else:
        raise RuntimeError("HybridClusteringService lacks in-memory clustering method")

    if not result.success:
        return groups

    if not pm_review:
        for cluster in result.clusters:
            groups[cluster.cluster_id] = list(cluster.conversation_ids)
        return groups

    if not PM_REVIEW_AVAILABLE:
        raise RuntimeError("PM review requested but service is unavailable")

    reviewer = PMReviewService()
    for cluster in result.clusters:
        conv_contexts = []
        for cid in cluster.conversation_ids:
            theme = theme_by_conv.get(cid, {})
            convo = convo_by_id.get(cid, {})
            conv_contexts.append(
                ConversationContext(
                    conversation_id=cid,
                    user_intent=theme.get("user_intent") or "",
                    symptoms=theme.get("symptoms") or [],
                    affected_flow=theme.get("affected_flow") or "",
                    excerpt=(
                        (convo.get("customer_digest") or convo.get("source_body") or "")[:500]
                    ),
                    product_area=theme.get("product_area") or "",
                    component=theme.get("component") or "",
                )
            )

        pm_result = reviewer.review_group(cluster.cluster_id, conv_contexts)
        if pm_result.decision == ReviewDecision.SPLIT:
            for sg in pm_result.sub_groups:
                groups[sg.suggested_signature] = list(sg.conversation_ids)
        elif pm_result.decision == ReviewDecision.REJECT:
            # Rejected groups are ignored for coherence scoring
            continue
        else:
            groups[cluster.cluster_id] = list(cluster.conversation_ids)

    return groups


def _compute_metrics(
    groups: Dict[str, List[str]],
    pack_by_conv: Dict[str, str],
    shared_error_by_pack: Dict[str, Optional[str]],
    convo_by_id: Dict[str, dict],
    theme_by_conv: Dict[str, dict],
) -> dict:
    group_metrics = []
    over_merge_count = 0
    over_merge_scheduling = 0
    over_merge_non_scheduling = 0
    pack_purities = []
    error_matches = []
    evidence_overlaps = []

    for gid, convs in groups.items():
        if len(convs) < MIN_GROUP_SIZE:
            continue

        pack_counts: Dict[str, int] = {}
        for cid in convs:
            pack = pack_by_conv.get(cid)
            if not pack:
                pack = "unassigned"
            pack_counts[pack] = pack_counts.get(pack, 0) + 1

        if len(pack_counts) > 1:
            over_merge_count += 1
            packs = list(pack_counts.keys())
            if packs and all(p.startswith("scheduling_") for p in packs):
                over_merge_scheduling += 1
            else:
                over_merge_non_scheduling += 1

        top_pack, top_count = sorted(pack_counts.items(), key=lambda x: x[1], reverse=True)[0]
        purity = top_count / len(convs)
        pack_purities.append(purity)

        # Error match: only if pack has shared_error
        shared_error = shared_error_by_pack.get(top_pack)
        if shared_error:
            matched = 0
            for cid in convs:
                text = (convo_by_id.get(cid, {}).get("customer_digest") or
                        convo_by_id.get(cid, {}).get("source_body") or "")
                if shared_error.lower() in text.lower():
                    matched += 1
            error_matches.append(matched / len(convs))

        token_sets = []
        for cid in convs:
            theme = theme_by_conv.get(cid, {})
            convo = convo_by_id.get(cid, {})
            tokens = set(_evidence_tokens(theme, convo))
            if tokens:
                token_sets.append(tokens)
        if token_sets:
            shared = set.intersection(*token_sets)
            union = set.union(*token_sets)
            if union:
                evidence_overlaps.append(len(shared) / len(union))

        group_metrics.append(
            {
                "group_id": gid,
                "size": len(convs),
                "top_pack": top_pack,
                "pack_purity": round(purity, 3),
                "pack_counts": pack_counts,
            }
        )

    pack_recall = {}
    for pack_id in set(pack_by_conv.values()):
        pack_convs = [cid for cid, p in pack_by_conv.items() if p == pack_id]
        best = 0.0
        for convs in groups.values():
            if len(convs) < MIN_GROUP_SIZE:
                continue
            overlap = len(set(convs) & set(pack_convs))
            best = max(best, overlap / max(1, len(pack_convs)))
        pack_recall[pack_id] = round(best, 3)

    pack_recall_avg = sum(pack_recall.values()) / max(1, len(pack_recall))
    scheduling_recalls = [
        v for k, v in pack_recall.items() if k.startswith("scheduling_")
    ]
    scheduling_recall_avg = sum(scheduling_recalls) / max(1, len(scheduling_recalls))
    pack_purity_avg = sum(pack_purities) / max(1, len(pack_purities))
    error_match_rate = sum(error_matches) / max(1, len(error_matches))
    evidence_overlap_avg = sum(evidence_overlaps) / max(1, len(evidence_overlaps))

    score = (
        0.4 * pack_purity_avg
        + 0.3 * pack_recall_avg
        + 0.3 * error_match_rate
        - 1.0 * over_merge_count
        + EVIDENCE_WEIGHT * evidence_overlap_avg
    )

    return {
        "summary": {
            "groups_scored": len(group_metrics),
            "over_merge_count": over_merge_count,
            "over_merge_scheduling": over_merge_scheduling,
            "over_merge_non_scheduling": over_merge_non_scheduling,
            "pack_purity_avg": round(pack_purity_avg, 3),
            "pack_recall_avg": round(pack_recall_avg, 3),
            "scheduling_recall_avg": round(scheduling_recall_avg, 3),
            "error_match_rate": round(error_match_rate, 3),
            "evidence_overlap_avg": round(evidence_overlap_avg, 3),
            "score": round(score, 3),
        },
        "pack_recall": pack_recall,
        "groups": group_metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run coherence evaluation")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-dir", default="data/coherence_eval")
    parser.add_argument("--output-dir", default="data/coherence_eval/outputs")
    parser.add_argument("--pm-review", action="store_true")
    parser.add_argument("--baseline", default=None)
    args = parser.parse_args()

    manifest = _load_manifest(Path(args.manifest))
    pack_by_conv = _build_pack_index(manifest)
    shared_error_by_pack = _build_shared_error_index(manifest)

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    conversations = _load_jsonl(data_dir / "conversations.jsonl")
    themes = _load_jsonl(data_dir / "themes.jsonl")
    embeddings = _load_jsonl(data_dir / "embeddings.jsonl")
    facets = _load_jsonl(data_dir / "facets.jsonl")

    convo_by_id = {str(c["conversation_id"]): c for c in conversations}
    theme_by_conv = {str(t["conversation_id"]): t for t in themes}

    conv_ids = list(pack_by_conv.keys())

    # Normalize embeddings: allow string vectors from SQL export
    for e in embeddings:
        emb = e.get("embedding")
        if isinstance(emb, str) and emb.startswith("[") and emb.endswith("]"):
            parts = [p for p in emb[1:-1].split(",") if p]
            try:
                e["embedding"] = [float(p) for p in parts]
            except ValueError:
                e["embedding"] = []

    groups = _group_conversations(
        embeddings=embeddings,
        facets=facets,
        conv_ids=conv_ids,
        pm_review=args.pm_review,
        theme_by_conv=theme_by_conv,
        convo_by_id=convo_by_id,
    )

    metrics = _compute_metrics(
        groups=groups,
        pack_by_conv=pack_by_conv,
        shared_error_by_pack=shared_error_by_pack,
        convo_by_id=convo_by_id,
        theme_by_conv=theme_by_conv,
    )

    stories = []
    for gid, convs in groups.items():
        if len(convs) < MIN_GROUP_SIZE:
            continue
        stories.append({"group_id": gid, "conversation_ids": convs})

    _write_json(output_dir / "groups.json", groups)
    _write_json(output_dir / "stories.json", {"stories": stories})
    _write_json(output_dir / "metrics.json", metrics)

    print(json.dumps(metrics["summary"], indent=2))

    if args.baseline:
        baseline_path = Path(args.baseline)
        baseline = json.loads(baseline_path.read_text())
        base_summary = baseline.get("summary", {})
        new_summary = metrics.get("summary", {})
        if new_summary.get("over_merge_count", 0) > base_summary.get("over_merge_count", 0):
            print("FAIL: over_merge_count increased vs baseline")
            return 2
        if new_summary.get("score", 0) <= base_summary.get("score", 0):
            print("FAIL: coherence score did not improve vs baseline")
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
