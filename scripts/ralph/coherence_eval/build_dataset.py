#!/usr/bin/env python3
"""
Build frozen coherence-eval artifacts from DB for a curated manifest.

Outputs JSONL files to a data directory (default: data/coherence_eval).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

import psycopg2
import psycopg2.extras


def _load_manifest(path: Path) -> Dict[str, List[dict]]:
    data = json.loads(path.read_text())
    packs = data.get("packs", [])
    if not packs:
        raise ValueError("Manifest has no packs")
    return data


def _flatten_conv_ids(manifest: Dict[str, List[dict]]) -> List[str]:
    conv_ids: List[str] = []
    for pack in manifest.get("packs", []):
        conv_ids.extend(pack.get("conversation_ids", []))
    return list(dict.fromkeys(conv_ids))


def _write_jsonl(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build coherence eval dataset")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", default="data/coherence_eval")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)

    manifest = _load_manifest(manifest_path)
    conv_ids = _flatten_conv_ids(manifest)
    if not conv_ids:
        raise ValueError("No conversation_ids found in manifest")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is not set")

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Conversations
            cur.execute(
                """
                SELECT
                  id,
                  created_at,
                  source_body,
                  source_subject,
                  support_insights
                FROM conversations
                WHERE id = ANY(%s)
                """,
                (conv_ids,),
            )
            conversations = []
            for row in cur.fetchall():
                digest = None
                insights = row.get("support_insights") or {}
                if isinstance(insights, dict):
                    digest = insights.get("customer_digest")
                conversations.append(
                    {
                        "conversation_id": row["id"],
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                        "source_body": row.get("source_body") or "",
                        "source_subject": row.get("source_subject"),
                        "customer_digest": digest,
                    }
                )

            # Themes (from run)
            cur.execute(
                """
                SELECT
                  conversation_id,
                  issue_signature,
                  product_area,
                  component,
                  user_intent,
                  symptoms,
                  affected_flow
                FROM themes
                WHERE pipeline_run_id = %s
                  AND conversation_id = ANY(%s)
                """,
                (args.run_id, conv_ids),
            )
            themes = [dict(row) for row in cur.fetchall()]

            # Embeddings (from run)
            cur.execute(
                """
                SELECT conversation_id, embedding::text AS embedding
                FROM conversation_embeddings
                WHERE pipeline_run_id = %s
                  AND conversation_id = ANY(%s)
                """,
                (args.run_id, conv_ids),
            )
            embeddings = []
            for row in cur.fetchall():
                emb_text = row["embedding"] or ""
                if emb_text.startswith("[") and emb_text.endswith("]"):
                    emb = [float(x) for x in emb_text[1:-1].split(",") if x]
                else:
                    emb = []
                embeddings.append(
                    {
                        "conversation_id": row["conversation_id"],
                        "embedding": emb,
                    }
                )

            # Facets (from run)
            cur.execute(
                """
                SELECT conversation_id, action_type, direction, symptom, user_goal
                FROM conversation_facet
                WHERE pipeline_run_id = %s
                  AND conversation_id = ANY(%s)
                """,
                (args.run_id, conv_ids),
            )
            facets = [dict(row) for row in cur.fetchall()]

    finally:
        conn.close()

    _write_jsonl(output_dir / "conversations.jsonl", conversations)
    _write_jsonl(output_dir / "themes.jsonl", themes)
    _write_jsonl(output_dir / "embeddings.jsonl", embeddings)
    _write_jsonl(output_dir / "facets.jsonl", facets)

    print(f"Wrote {len(conversations)} conversations to {output_dir}/conversations.jsonl")
    print(f"Wrote {len(themes)} themes to {output_dir}/themes.jsonl")
    print(f"Wrote {len(embeddings)} embeddings to {output_dir}/embeddings.jsonl")
    print(f"Wrote {len(facets)} facets to {output_dir}/facets.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
