#!/usr/bin/env python
"""
Test the canonicalization fix by re-running on existing singletons.

This validates that removing LIMIT 50 would reduce fragmentation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db.connection import get_connection
from theme_extractor import ThemeExtractor


def get_singletons_with_context():
    """Get all singleton themes with their context for re-canonicalization."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    ta.issue_signature,
                    ta.product_area,
                    ta.component,
                    ta.sample_user_intent,
                    ta.sample_symptoms
                FROM theme_aggregates ta
                WHERE ta.occurrence_count = 1
                ORDER BY ta.last_seen_at DESC
            """)
            return [
                {
                    "signature": row[0],
                    "product_area": row[1],
                    "component": row[2],
                    "user_intent": row[3] or "",
                    "symptoms": row[4] or [],
                }
                for row in cur.fetchall()
            ]


def get_all_signatures():
    """Get all signatures for matching."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT issue_signature, product_area, component, occurrence_count
                FROM theme_aggregates
                ORDER BY occurrence_count DESC
            """)
            return [
                {
                    "signature": row[0],
                    "product_area": row[1],
                    "component": row[2],
                    "count": row[3],
                }
                for row in cur.fetchall()
            ]


def main():
    print("Testing canonicalization fix...")
    print("=" * 60)

    singletons = get_singletons_with_context()
    all_sigs = get_all_signatures()

    print(f"Total signatures: {len(all_sigs)}")
    print(f"Singletons to test: {len(singletons)}")
    print(f"Non-singletons (potential matches): {len([s for s in all_sigs if s['count'] > 1])}")
    print()

    extractor = ThemeExtractor()

    # Test each singleton
    would_match = []
    would_stay_new = []

    for i, singleton in enumerate(singletons):
        # Exclude this singleton from candidates
        candidates = [s for s in all_sigs if s['signature'] != singleton['signature']]

        # Build signature list for LLM prompt (simulating what canonicalize_signature does)
        sig_list = "\n".join(
            f"- {s['signature']} ({s['product_area']}/{s['component']}) [{s['count']}x]"
            for s in candidates[:100]  # Reasonable limit for prompt
        )

        from theme_extractor import SIGNATURE_CANONICALIZATION_PROMPT

        prompt = SIGNATURE_CANONICALIZATION_PROMPT.format(
            existing_signatures=sig_list,
            product_area=singleton['product_area'],
            component=singleton['component'],
            proposed_signature=singleton['signature'],
            user_intent=singleton['user_intent'],
            symptoms=", ".join(singleton['symptoms']) if singleton['symptoms'] else "none",
        )

        try:
            response = extractor.client.chat.completions.create(
                model=extractor.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )

            import json
            import re

            content = response.choices[0].message.content.strip()
            # Strip markdown if present
            if content.startswith("```"):
                content = re.sub(r'^```(?:json)?\n?', '', content)
                content = re.sub(r'\n?```$', '', content)

            result = json.loads(content)

            if result.get('matched_existing'):
                matched_sig = result['signature']
                matched_info = next((s for s in candidates if s['signature'] == matched_sig), None)
                matched_count = matched_info['count'] if matched_info else '?'
                would_match.append({
                    "original": singleton['signature'],
                    "matched": matched_sig,
                    "matched_count": matched_count,
                    "reasoning": result.get('reasoning', ''),
                })
                print(f"✓ {singleton['signature'][:35]:<35} → {matched_sig} [{matched_count}x]")
            else:
                would_stay_new.append({
                    "signature": singleton['signature'],
                    "reasoning": result.get('reasoning', ''),
                })
                print(f"  {singleton['signature'][:35]:<35} (genuinely unique)")

        except Exception as e:
            print(f"✗ {singleton['signature'][:35]:<35} ERROR: {e}")

        # Limit for testing
        if i >= 24:  # Test 25 singletons
            break

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Tested: {len(would_match) + len(would_stay_new)}")
    print(f"Would match existing: {len(would_match)} ({100*len(would_match)/(len(would_match)+len(would_stay_new)):.0f}%)")
    print(f"Genuinely unique: {len(would_stay_new)} ({100*len(would_stay_new)/(len(would_match)+len(would_stay_new)):.0f}%)")
    print()

    # Quality check: how many matched high-count vs singleton signatures?
    high_count_matches = [m for m in would_match if isinstance(m['matched_count'], int) and m['matched_count'] > 1]
    singleton_matches = [m for m in would_match if m['matched_count'] == 1]

    print(f"Quality breakdown of matches:")
    print(f"  Matched multi-occurrence (good): {len(high_count_matches)}")
    print(f"  Matched other singleton (okay): {len(singleton_matches)}")

    if high_count_matches:
        print()
        print("High-quality matches (reducing fragmentation):")
        for m in high_count_matches[:10]:
            print(f"  {m['original'][:30]} → {m['matched']} [{m['matched_count']}x]")


if __name__ == "__main__":
    main()
