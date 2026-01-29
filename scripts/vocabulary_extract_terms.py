#!/usr/bin/env python3
"""
Phase 1: Extract Domain TERMS from Conversations (Issue #153 - CORRECT VERSION)

This extracts actual TERMS (not signatures) from conversation data:
- Object types: drafts, pins, boards, posts, images, accounts, etc.
- Actions: delete, schedule, unschedule, connect, import, create, etc.
- Stages: selection, generation, publishing, etc.
- Timing: during, after, before, etc.

Then finds candidate TERM PAIRS that might need distinction validation.

Usage:
    python scripts/vocabulary_extract_terms.py
    python scripts/vocabulary_extract_terms.py --min-count 3
"""

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data" / "vocabulary_enhancement"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Known domain terms to look for (seed list - LLM will expand)
SEED_TERMS = {
    "object_type": [
        "drafts", "draft", "pins", "pin", "boards", "board", "posts", "post",
        "images", "image", "videos", "video", "accounts", "account", "profiles", "profile",
        "slots", "slot", "queues", "queue", "schedules", "schedule",
        "connections", "connection", "tokens", "token",
    ],
    "action": [
        "delete", "remove", "schedule", "unschedule", "reschedule",
        "create", "add", "edit", "update", "modify",
        "connect", "disconnect", "reconnect", "sync", "refresh",
        "import", "export", "fetch", "upload", "download",
        "generate", "publish", "post", "share",
        "lock", "unlock", "enable", "disable",
    ],
    "stage": [
        "selection", "generation", "publishing", "importing", "uploading",
        "authentication", "authorization", "validation", "processing",
        "creation", "editing", "preview", "confirmation",
    ],
    "timing": [
        "during", "after", "before", "while", "when",
    ],
}


@dataclass
class ExtractedTerms:
    """Terms extracted from a single conversation/theme."""
    conversation_id: str
    object_types: list[str]
    actions: list[str]
    stages: list[str]
    timing: list[str]
    raw_text: str  # The diagnostic summary used


@dataclass
class TermCandidate:
    """A candidate term pair that might need distinction."""
    category: str  # object_type, action, stage, timing
    term_a: str
    term_b: str
    co_occurrence_count: int  # How often they appear in similar contexts
    example_contexts: list[str]  # Sample diagnostic summaries where both appear


def get_themes_from_db(run_id: int = 95, limit: Optional[int] = None) -> list[dict]:
    """Get themes with diagnostic summaries from database."""
    from src.db.connection import get_connection

    query = """
        SELECT
            t.conversation_id,
            t.issue_signature,
            t.product_area,
            t.diagnostic_summary,
            t.user_intent,
            c.source_body
        FROM themes t
        JOIN conversations c ON t.conversation_id = c.id
        WHERE t.pipeline_run_id = %s
        AND t.diagnostic_summary IS NOT NULL
        AND t.diagnostic_summary != ''
    """
    if limit:
        query += f" LIMIT {limit}"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (run_id,))
            rows = cur.fetchall()

    themes = []
    for row in rows:
        themes.append({
            "conversation_id": row[0],
            "issue_signature": row[1],
            "product_area": row[2],
            "diagnostic_summary": row[3],
            "user_intent": row[4],
            "source_body": row[5][:500] if row[5] else "",
        })

    logger.info(f"Loaded {len(themes)} themes with diagnostic summaries")
    return themes


def extract_terms_with_llm(client: OpenAI, text: str) -> dict:
    """Use LLM to extract domain terms from text."""

    prompt = f"""Extract domain-specific terms from this support conversation summary.

TEXT:
{text}

Extract terms in these categories:
1. OBJECT_TYPES: Things being acted on (drafts, pins, boards, posts, images, accounts, etc.)
2. ACTIONS: What the user wants to do (delete, schedule, unschedule, connect, import, etc.)
3. STAGES: Where in the workflow (selection, generation, publishing, authentication, etc.)
4. TIMING: When issues occur (during, after, before connection/publishing/etc.)

Return JSON only:
{{
  "object_types": ["term1", "term2"],
  "actions": ["term1", "term2"],
  "stages": ["term1"],
  "timing": ["during X", "after Y"]
}}

Extract the ACTUAL terms used, normalized to lowercase singular form where appropriate.
Only include terms that are clearly mentioned or implied in the text."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {"object_types": [], "actions": [], "stages": [], "timing": []}


def extract_terms_regex(text: str) -> dict:
    """Fast regex-based term extraction using seed terms."""
    text_lower = text.lower()

    result = {
        "object_types": [],
        "actions": [],
        "stages": [],
        "timing": [],
    }

    for category, terms in SEED_TERMS.items():
        for term in terms:
            if re.search(rf'\b{term}\b', text_lower):
                # Normalize to singular
                normalized = term.rstrip('s') if term.endswith('s') and len(term) > 3 else term
                if normalized not in result[category]:
                    result[category].append(normalized)

    return result


def find_term_pairs(term_counts: dict[str, Counter], min_count: int = 3) -> list[TermCandidate]:
    """Find candidate term pairs within each category that might need distinction."""
    candidates = []

    for category, counts in term_counts.items():
        # Get terms that appear frequently enough
        frequent_terms = [term for term, count in counts.items() if count >= min_count]

        # Find pairs of similar/related terms
        for i, term_a in enumerate(frequent_terms):
            for term_b in frequent_terms[i+1:]:
                # Skip if terms are too similar (singular/plural)
                if term_a.rstrip('s') == term_b.rstrip('s'):
                    continue
                if term_a in term_b or term_b in term_a:
                    continue

                candidates.append(TermCandidate(
                    category=category,
                    term_a=term_a,
                    term_b=term_b,
                    co_occurrence_count=0,  # Will be computed
                    example_contexts=[],
                ))

    return candidates


def compute_co_occurrences(
    candidates: list[TermCandidate],
    extractions: list[ExtractedTerms],
) -> list[TermCandidate]:
    """Compute how often term pairs appear in similar contexts."""

    # Build index: term -> list of conversation_ids
    term_to_convs: dict[str, set[str]] = defaultdict(set)
    conv_to_text: dict[str, str] = {}

    for ext in extractions:
        conv_to_text[ext.conversation_id] = ext.raw_text
        for term in ext.object_types:
            term_to_convs[f"object_type:{term}"].add(ext.conversation_id)
        for term in ext.actions:
            term_to_convs[f"action:{term}"].add(ext.conversation_id)
        for term in ext.stages:
            term_to_convs[f"stage:{term}"].add(ext.conversation_id)
        for term in ext.timing:
            term_to_convs[f"timing:{term}"].add(ext.conversation_id)

    # Compute co-occurrences
    for candidate in candidates:
        key_a = f"{candidate.category}:{candidate.term_a}"
        key_b = f"{candidate.category}:{candidate.term_b}"

        convs_a = term_to_convs.get(key_a, set())
        convs_b = term_to_convs.get(key_b, set())

        # Co-occurrence = conversations mentioning both OR in same product area
        shared = convs_a & convs_b
        candidate.co_occurrence_count = len(shared)

        # Get example contexts
        for conv_id in list(shared)[:3]:
            if conv_id in conv_to_text:
                candidate.example_contexts.append(conv_to_text[conv_id][:200])

    return candidates


def main():
    parser = argparse.ArgumentParser(description="Phase 1: Extract domain TERMS from conversations")
    parser.add_argument("--run-id", type=int, default=95, help="Pipeline run ID")
    parser.add_argument("--min-count", type=int, default=3, help="Minimum term frequency")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM for extraction (slower but better)")
    parser.add_argument("--limit", type=int, help="Limit number of themes to process")
    args = parser.parse_args()

    # Load themes
    themes = get_themes_from_db(args.run_id, args.limit)

    if not themes:
        logger.error("No themes found")
        sys.exit(1)

    # Initialize OpenAI client if using LLM
    client = None
    if args.use_llm:
        client = OpenAI()
        logger.info("Using LLM for term extraction")
    else:
        logger.info("Using regex for term extraction (use --use-llm for better results)")

    # Extract terms from each theme
    extractions: list[ExtractedTerms] = []
    term_counts = {
        "object_type": Counter(),
        "action": Counter(),
        "stage": Counter(),
        "timing": Counter(),
    }

    for i, theme in enumerate(themes):
        if i % 50 == 0:
            logger.info(f"Processing {i}/{len(themes)}...")

        text = theme["diagnostic_summary"]
        if theme["user_intent"]:
            text += " " + theme["user_intent"]

        # Extract terms
        if args.use_llm and client:
            terms = extract_terms_with_llm(client, text)
        else:
            terms = extract_terms_regex(text)

        extraction = ExtractedTerms(
            conversation_id=theme["conversation_id"],
            object_types=terms.get("object_types", []),
            actions=terms.get("actions", []),
            stages=terms.get("stages", []),
            timing=terms.get("timing", []),
            raw_text=text,
        )
        extractions.append(extraction)

        # Count terms
        for term in extraction.object_types:
            term_counts["object_type"][term] += 1
        for term in extraction.actions:
            term_counts["action"][term] += 1
        for term in extraction.stages:
            term_counts["stage"][term] += 1
        for term in extraction.timing:
            term_counts["timing"][term] += 1

    # Show term frequency
    print("\n" + "=" * 60)
    print("TERM FREQUENCIES")
    print("=" * 60)

    for category, counts in term_counts.items():
        print(f"\n{category.upper()} (top 15):")
        for term, count in counts.most_common(15):
            print(f"  {term}: {count}")

    # Find candidate term pairs
    candidates = find_term_pairs(term_counts, args.min_count)
    candidates = compute_co_occurrences(candidates, extractions)

    # Sort by co-occurrence (pairs that appear together might need distinction)
    candidates.sort(key=lambda c: -c.co_occurrence_count)

    print("\n" + "=" * 60)
    print(f"CANDIDATE TERM PAIRS FOR VALIDATION ({len(candidates)} total)")
    print("=" * 60)

    for category in ["object_type", "action", "stage", "timing"]:
        cat_candidates = [c for c in candidates if c.category == category][:10]
        if cat_candidates:
            print(f"\n{category.upper()} distinctions to validate:")
            for c in cat_candidates:
                print(f"  {c.term_a} vs {c.term_b} (co-occur: {c.co_occurrence_count})")

    # Save results
    output = {
        "metadata": {
            "run_id": args.run_id,
            "timestamp": datetime.utcnow().isoformat(),
            "themes_processed": len(themes),
            "extraction_method": "llm" if args.use_llm else "regex",
        },
        "term_counts": {cat: dict(counts) for cat, counts in term_counts.items()},
        "candidate_pairs": [asdict(c) for c in candidates],
    }

    output_path = DATA_DIR / "phase1_terms.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {output_path}")
    print(f"\nNext: Run Phase 2 to validate term distinctions against codebase")


if __name__ == "__main__":
    main()
