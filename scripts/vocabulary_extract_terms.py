#!/usr/bin/env python3
"""
Phase 1: Extract Terms from Conversations (Issue #153)

Extracts object types, actions, and stages from theme diagnostic summaries.
Finds candidate object pairs using semantic similarity (co-occurrence, name similarity).

Usage:
    python scripts/vocabulary_extract_terms.py
    python scripts/vocabulary_extract_terms.py --limit 50
"""

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "vocabulary_enhancement"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_themes_from_db(run_id: int = 95, limit: int | None = None) -> list[dict]:
    """Get themes with diagnostic summaries from database."""
    from src.db.connection import get_connection

    query = """
        SELECT
            t.conversation_id,
            t.diagnostic_summary
        FROM themes t
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

    logger.info(f"Loaded {len(rows)} themes")
    return [{"conversation_id": row[0], "diagnostic_summary": row[1]} for row in rows]


def extract_terms(client: OpenAI, themes: list[dict]) -> list[dict]:
    """Extract objects, actions, stages from each theme."""

    results = []
    BATCH_SIZE = 20

    for i in range(0, len(themes), BATCH_SIZE):
        batch = themes[i:i + BATCH_SIZE]
        logger.info(f"Batch {i // BATCH_SIZE + 1}/{(len(themes) + BATCH_SIZE - 1) // BATCH_SIZE}...")

        texts = [f"[{j}] {t['diagnostic_summary'][:400]}" for j, t in enumerate(batch)]

        prompt = f"""Extract terms from each support conversation summary.

{chr(10).join(texts)}

For EACH [index], extract:

OBJECTS: Things discussed (nouns, singular, lowercase)
  - Be specific: "scheduled_pin" not "pin" if about scheduled content
  - Examples: draft, scheduled_pin, pin, board, post, image, account, connection

ACTIONS: What user wants to do (verbs, lowercase)
  - Examples: delete, schedule, unschedule, connect, import, generate

STAGES: Workflow position (lowercase)
  - Examples: selection, generation, publishing, authentication

Return JSON:
{{
  "0": {{"objects": ["draft"], "actions": ["delete"], "stages": ["publishing"]}},
  "1": {{"objects": ["scheduled_pin"], "actions": ["schedule"], "stages": []}},
  ...
}}"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )

        try:
            data = json.loads(response.choices[0].message.content)
            for j, t in enumerate(batch):
                terms = data.get(str(j), {})
                results.append({
                    "conversation_id": t["conversation_id"],
                    "objects": terms.get("objects", []),
                    "actions": terms.get("actions", []),
                    "stages": terms.get("stages", []),
                })
        except json.JSONDecodeError:
            logger.warning(f"Parse error batch {i // BATCH_SIZE + 1}")
            for t in batch:
                results.append({"conversation_id": t["conversation_id"], "objects": [], "actions": [], "stages": []})

    return results


def find_candidate_pairs(results: list[dict], object_counts: Counter) -> list[dict]:
    """Find candidate object pairs using semantic similarity."""

    # Build co-occurrence: which objects appear with which actions
    obj_actions = defaultdict(set)
    for r in results:
        for obj in set(r["objects"]):
            for action in set(r["actions"]):
                obj_actions[obj].add(action)

    # Find pairs that share actions (semantic similarity via co-occurrence)
    candidates = []
    objects = [o for o, c in object_counts.items() if c >= 5]

    for i, obj_a in enumerate(objects):
        for obj_b in objects[i + 1:]:
            reasons = []

            # Check shared actions
            shared = obj_actions[obj_a] & obj_actions[obj_b]
            if shared:
                reasons.append(f"shared actions: {', '.join(sorted(shared))}")

            # Check name similarity
            if obj_a in obj_b or obj_b in obj_a:
                reasons.append("name overlap")
            else:
                words_a = set(obj_a.split("_"))
                words_b = set(obj_b.split("_"))
                common = words_a & words_b
                if common:
                    reasons.append(f"shared word: {', '.join(common)}")

            if reasons:
                candidates.append({
                    "object_a": obj_a,
                    "object_b": obj_b,
                    "count_a": object_counts[obj_a],
                    "count_b": object_counts[obj_b],
                    "similarity": reasons,
                })

    # Sort by number of similarity signals, then by frequency
    candidates.sort(key=lambda x: (-len(x["similarity"]), -(x["count_a"] + x["count_b"])))
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, default=95)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    themes = get_themes_from_db(args.run_id, args.limit)
    if not themes:
        logger.error("No themes found")
        sys.exit(1)

    client = OpenAI()
    results = extract_terms(client, themes)

    # Count terms (dedupe within theme)
    object_counts = Counter()
    action_counts = Counter()
    stage_counts = Counter()
    for r in results:
        object_counts.update(set(r["objects"]))
        action_counts.update(set(r["actions"]))
        stage_counts.update(set(r["stages"]))

    # Find candidate pairs
    candidates = find_candidate_pairs(results, object_counts)

    # Output
    print("\n" + "=" * 70)
    print("PHASE 1 RESULTS")
    print("=" * 70)
    print(f"\nThemes processed: {len(themes)}")

    print("\n--- OBJECTS ---")
    for obj, count in object_counts.most_common(20):
        print(f"  {obj}: {count}")

    print("\n--- ACTIONS ---")
    for action, count in action_counts.most_common(15):
        print(f"  {action}: {count}")

    print("\n--- STAGES ---")
    for stage, count in stage_counts.most_common(10):
        print(f"  {stage}: {count}")

    print("\n" + "=" * 70)
    print("CANDIDATE PAIRS (semantic similarity)")
    print("=" * 70)
    print("\nQuestion for each: Are these distinct objects in the codebase?\n")

    for pair in candidates[:20]:
        print(f"  {pair['object_a']} vs {pair['object_b']}")
        print(f"    Themes: {pair['count_a']} vs {pair['count_b']}")
        print(f"    Why similar: {', '.join(pair['similarity'])}")
        print()

    # Save
    output = {
        "metadata": {"run_id": args.run_id, "timestamp": datetime.utcnow().isoformat(), "themes": len(themes)},
        "object_counts": dict(object_counts.most_common()),
        "action_counts": dict(action_counts.most_common()),
        "stage_counts": dict(stage_counts.most_common()),
        "candidate_pairs": candidates,
    }

    output_path = DATA_DIR / "phase1_terms.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
