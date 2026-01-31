#!/usr/bin/env python3
"""
Phase 1: Extract Terms from Conversations (Issue #153)

Extracts object types, actions, and stages from theme diagnostic summaries.
Finds candidate object pairs using semantic similarity (co-occurrence, name similarity).

Usage:
    python scripts/vocabulary_extract_terms.py
    python scripts/vocabulary_extract_terms.py --limit 50

Field Extraction Approach (Issue #154):
----------------------------------------
This script uses SINGLE-FIELD extraction (diagnostic_summary only).

Rationale:
- diagnostic_summary is a pre-processed, LLM-generated summary that already
  captures the essential context from the full conversation
- It provides higher signal-to-noise ratio than raw source_body text
- The diagnostic_summary is specifically designed to highlight the user's
  intent and the core issue, making term extraction more precise

Alternative (MULTI-FIELD) approach would include:
- user_intent: Already captured in diagnostic_summary
- source_body: Raw text, often noisy with greetings/pleasantries
- product_area: Categorical, not useful for term extraction
- issue_signature: Derived field, redundant with diagnostic_summary

Tradeoffs:
- Single-field: Cleaner extraction, faster processing, lower API costs
- Multi-field: More recall, but higher noise and potential duplicates

If extraction precision degrades, consider adding user_intent as secondary field.
"""

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Retry configuration for OpenAI API (follows IntercomClient pattern)
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds, exponential backoff: 2s, 4s, 8s

# Extraction configuration
BATCH_SIZE = 20  # Themes per OpenAI API call
MAX_SUMMARY_CHARS = 400  # Truncate diagnostic summaries to this length
MIN_OBJECT_COUNT = 5  # Minimum theme count to consider object for pairing

DATA_DIR = Path(__file__).parent.parent / "data" / "vocabulary_enhancement"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ==================== NORMALIZATION UTILITIES ====================

# Words ending in 's' that are NOT plurals (should not be singularized)
NON_PLURAL_S_WORDS = frozenset({
    "status", "bus", "analysis", "canvas", "focus", "virus", "bonus",
    "census", "corpus", "genus", "nexus", "radius", "cactus", "fungus",
    "stimulus", "apparatus", "consensus", "prospectus", "syllabus",
    "campus", "circus", "citrus", "chorus", "cosmos", "crisis",
    "diagnosis", "emphasis", "hypothesis", "oasis", "parenthesis",
    "synopsis", "thesis", "metamorphosis", "process", "success",
    "access", "address", "express", "impress", "progress", "compress",
})

# Words ending in -ves that become -fe (not -f)
VES_TO_FE_WORDS = {
    "wives": "wife",
    "knives": "knife",
    "lives": "life",
}

# Words ending in -ves that become -f (true f->ves plurals)
# Using allowlist to avoid false positives like "archives" -> "archif"
VES_TO_F_WORDS = {
    "leaves": "leaf",
    "halves": "half",
    "shelves": "shelf",
    "calves": "calf",
    "wolves": "wolf",
    "loaves": "loaf",
    "scarves": "scarf",
    "selves": "self",
    "elves": "elf",
}


def singularize(word: str) -> str:
    """
    Convert a plural English word to singular form.

    Uses common pluralization rules. For domain-specific terms like
    'pins', 'boards', 'drafts', this handles the standard cases.

    Issue #154: Post-processing normalization to prevent variations
    like 'pins' vs 'pin' from inflating pair counts.

    Note: This is a simplified singularizer for domain-specific vocabulary.
    It handles common English patterns but not all edge cases. For
    comprehensive singularization, consider the `inflect` library.

    Args:
        word: Word to singularize (assumed lowercase)

    Returns:
        Singular form of the word
    """
    if not word or len(word) < 3:
        return word

    # Check non-plural words ending in 's' first (status, bus, analysis, etc.)
    if word in NON_PLURAL_S_WORDS:
        return word

    # Handle irregular plurals
    irregulars = {
        "children": "child",
        "people": "people",  # Keep as-is for "people"
        "data": "data",  # Keep as-is
        "media": "media",  # Keep as-is
        "indices": "index",
        "analyses": "analysis",
    }
    if word in irregulars:
        return irregulars[word]

    # -ves -> -f/-fe: Use allowlists to avoid false positives
    # Words like "archives" should become "archive", not "archif"
    if word in VES_TO_FE_WORDS:
        return VES_TO_FE_WORDS[word]
    if word in VES_TO_F_WORDS:
        return VES_TO_F_WORDS[word]

    # Common plural endings
    # -ies -> -y (e.g., stories -> story, categories -> category)
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    # -es after sibilants (e.g., boxes -> box, matches -> match)
    if word.endswith("es"):
        if word.endswith(("sses", "xes", "ches", "shes", "zes")):
            return word[:-2]
        # -oes -> -o (e.g., heroes -> hero)
        if word.endswith("oes"):
            return word[:-2]

    # Standard -s plural (e.g., pins -> pin, boards -> board)
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]

    return word


def normalize_term(term: str) -> str:
    """
    Normalize an extracted term for consistent counting.

    Issue #154: Post-processing normalization to ensure consistent
    term representation regardless of LLM output variations.

    Applies:
    1. Whitespace stripping and collapsing
    2. Lowercase conversion
    3. Singularization

    Args:
        term: Raw term from LLM extraction

    Returns:
        Normalized term
    """
    if not term:
        return ""

    # Strip and collapse whitespace
    normalized = re.sub(r"\s+", " ", term.strip())

    # Lowercase
    normalized = normalized.lower()

    # Singularize (handles compound terms with underscores)
    if "_" in normalized:
        # For compound terms like "scheduled_pins", singularize the last part
        parts = normalized.split("_")
        parts[-1] = singularize(parts[-1])
        normalized = "_".join(parts)
    else:
        normalized = singularize(normalized)

    return normalized


def normalize_terms_list(terms: list[str]) -> list[str]:
    """
    Normalize a list of terms, removing empty results and duplicates.

    Args:
        terms: List of raw terms

    Returns:
        List of normalized, deduplicated terms
    """
    seen = set()
    result = []
    for term in terms:
        normalized = normalize_term(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


# ==================== END NORMALIZATION UTILITIES ====================


def get_themes_from_db(run_id: int = 95, limit: int | None = None) -> list[dict]:
    """Get themes with diagnostic summaries from database.

    Args:
        run_id: Pipeline run ID to fetch themes from
        limit: Maximum number of themes to fetch (parameterized to prevent SQL injection)

    Returns:
        List of theme dicts with conversation_id and diagnostic_summary
    """
    from src.db.connection import get_connection

    # Build query with parameterized LIMIT (Issue #154: prevent SQL injection)
    query = """
        SELECT
            t.conversation_id,
            t.diagnostic_summary
        FROM themes t
        WHERE t.pipeline_run_id = %s
        AND t.diagnostic_summary IS NOT NULL
        AND t.diagnostic_summary != ''
    """

    # Use parameterized LIMIT instead of string interpolation
    params: list = [run_id]
    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    logger.info(f"Loaded {len(rows)} themes")
    return [{"conversation_id": row[0], "diagnostic_summary": row[1]} for row in rows]


def _call_openai_with_retry(
    client: OpenAI,
    prompt: str,
    batch_num: int,
    total_batches: int,
) -> dict | None:
    """
    Call OpenAI API with exponential backoff retry on failures.

    Issue #154: Implements retry logic to prevent empty batch results
    from transiently failed API calls.

    Retries on:
    - Rate limit errors (429)
    - Server errors (5xx)
    - Parse errors (malformed JSON response)
    - Connection/timeout errors

    Args:
        client: OpenAI client instance
        prompt: The prompt to send
        batch_num: Current batch number (for logging)
        total_batches: Total batch count (for logging)

    Returns:
        Parsed JSON dict from response, or None if all retries fail
    """
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response content")

            data = json.loads(content)
            return data

        except json.JSONDecodeError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(
                    f"Parse error batch {batch_num}/{total_batches}, "
                    f"retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"Parse error batch {batch_num}/{total_batches} "
                    f"after {MAX_RETRIES + 1} attempts: {e}"
                )

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Fail fast on non-transient errors (4xx auth/validation errors)
            # These indicate misconfiguration, not transient issues
            is_auth_error = "401" in error_str or "403" in error_str or "authentication" in error_str
            is_validation_error = "400" in error_str or "invalid" in error_str
            if is_auth_error or is_validation_error:
                logger.error(
                    f"Non-transient API error batch {batch_num}/{total_batches}, "
                    f"not retrying: {e}"
                )
                break  # Exit retry loop immediately

            # Retry transient errors with exponential backoff
            # Common transient errors: rate limits (429), server errors (5xx), connection issues
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(
                    f"API error batch {batch_num}/{total_batches}, "
                    f"retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"API error batch {batch_num}/{total_batches} "
                    f"after {MAX_RETRIES + 1} attempts: {e}"
                )

    # All retries exhausted
    logger.error(f"Batch {batch_num}/{total_batches} failed permanently: {last_error}")
    return None


def extract_terms(client: OpenAI, themes: list[dict]) -> list[dict]:
    """
    Extract objects, actions, stages from each theme.

    Issue #154 improvements:
    - Exponential backoff retry on API failures
    - Post-processing normalization for consistent term representation
    """

    results = []
    total_batches = (len(themes) + BATCH_SIZE - 1) // BATCH_SIZE
    failed_batches = 0

    for i in range(0, len(themes), BATCH_SIZE):
        batch = themes[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        logger.info(f"Batch {batch_num}/{total_batches}...")

        texts = [f"[{j}] {t['diagnostic_summary'][:MAX_SUMMARY_CHARS]}" for j, t in enumerate(batch)]

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

        # Call API with retry logic
        data = _call_openai_with_retry(client, prompt, batch_num, total_batches)

        if data is not None:
            for j, t in enumerate(batch):
                terms = data.get(str(j), {})
                # Apply post-processing normalization (Issue #154)
                results.append({
                    "conversation_id": t["conversation_id"],
                    "objects": normalize_terms_list(terms.get("objects", [])),
                    "actions": normalize_terms_list(terms.get("actions", [])),
                    "stages": normalize_terms_list(terms.get("stages", [])),
                })
        else:
            # All retries failed - log and add empty results
            failed_batches += 1
            logger.warning(f"Batch {batch_num} yielded empty results after retries")
            for t in batch:
                results.append({
                    "conversation_id": t["conversation_id"],
                    "objects": [],
                    "actions": [],
                    "stages": [],
                })

    if failed_batches > 0:
        logger.warning(f"Extraction complete with {failed_batches}/{total_batches} failed batches")
    else:
        logger.info(f"Extraction complete: {total_batches} batches processed successfully")

    return results


def find_candidate_pairs(results: list[dict], object_counts: Counter) -> list[dict]:
    """
    Find candidate object pairs that may represent the same concept.

    This function identifies pairs of objects that might be synonyms or
    closely related terms, helping to consolidate vocabulary. It uses
    two signals for semantic similarity:

    1. **Action co-occurrence**: Objects that appear with the same actions
       are likely related. E.g., if "pin" and "post" both have actions
       ["delete", "schedule"], they may represent similar concepts.

    2. **Name similarity**: Objects with overlapping names or shared words
       are likely related. E.g., "scheduled_pin" and "pin" share "pin".

    Args:
        results: List of extraction results, each with 'objects' and 'actions'
        object_counts: Counter of how often each object appears across themes

    Returns:
        List of candidate pairs, sorted by similarity strength then frequency.
        Each pair is a dict with keys:
        - object_a, object_b: The two objects
        - count_a, count_b: How often each appears
        - similarity: List of reasons they're similar
    """
    # Build co-occurrence map: which actions appear with each object
    obj_actions = defaultdict(set)
    for r in results:
        for obj in set(r["objects"]):
            for action in set(r["actions"]):
                obj_actions[obj].add(action)

    # Find pairs among objects that appear often enough to matter
    candidates = []
    objects = [o for o, c in object_counts.items() if c >= MIN_OBJECT_COUNT]

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
