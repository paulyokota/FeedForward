#!/usr/bin/env python3
"""
Vocabulary management CLI.

Commands:
  list [--area AREA]     List all themes (optionally filter by product area)
  stats                  Show vocabulary statistics
  add                    Add a new theme interactively
  merge SRC TARGET       Merge source theme into target
  deprecate SIG          Deprecate a theme
  seed [--min-count N]   Seed from database (default min_count=2)
  review                 Review proposed new themes (from extraction logs)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vocabulary import ThemeVocabulary


def cmd_list(args):
    """List vocabulary themes."""
    vocab = ThemeVocabulary()

    if args.area:
        themes = vocab.get_by_product_area(args.area)
        print(f"Themes in '{args.area}':")
    else:
        themes = vocab.get_all_active()
        print("All active themes:")

    print("=" * 70)

    # Group by product area
    by_area = {}
    for t in themes:
        by_area.setdefault(t.product_area, []).append(t)

    for area in sorted(by_area.keys()):
        print(f"\n## {area}")
        for t in sorted(by_area[area], key=lambda x: x.issue_signature):
            kw = f" ({', '.join(t.keywords[:2])})" if t.keywords else ""
            print(f"  - {t.issue_signature}: {t.description[:50]}{kw}")


def cmd_stats(args):
    """Show vocabulary statistics."""
    vocab = ThemeVocabulary()
    stats = vocab.get_stats()

    print("Vocabulary Statistics")
    print("=" * 40)
    print(f"Total themes:  {stats['total']}")
    print(f"Active:        {stats['active']}")
    print(f"Deprecated:    {stats['deprecated']}")
    print(f"Merged:        {stats['merged']}")
    print()
    print("By product area:")
    for area, count in sorted(stats['by_product_area'].items(), key=lambda x: -x[1]):
        print(f"  {area}: {count}")


def cmd_add(args):
    """Add a new theme interactively."""
    vocab = ThemeVocabulary()

    print("Add new theme to vocabulary")
    print("=" * 40)

    signature = input("Issue signature (lowercase_underscores): ").strip()
    if not signature:
        print("Cancelled")
        return

    if vocab.get(signature):
        print(f"Error: '{signature}' already exists")
        return

    product_area = input("Product area: ").strip()
    component = input("Component: ").strip()
    description = input("Description: ").strip()
    keywords = input("Keywords (comma-separated): ").strip()
    keywords = [k.strip() for k in keywords.split(",")] if keywords else []

    vocab.add(
        issue_signature=signature,
        product_area=product_area,
        component=component,
        description=description,
        keywords=keywords,
    )
    print(f"Added: {signature}")


def cmd_merge(args):
    """Merge source theme into target."""
    vocab = ThemeVocabulary()

    source = vocab.get(args.source)
    target = vocab.get(args.target)

    if not source:
        print(f"Error: Source '{args.source}' not found")
        return
    if not target:
        print(f"Error: Target '{args.target}' not found")
        return

    print(f"Merge: {args.source}")
    print(f"  -> {args.target}")
    print()
    confirm = input("Confirm? (y/N): ").strip().lower()

    if confirm == 'y':
        vocab.merge(args.source, args.target)
        print("Merged successfully")
    else:
        print("Cancelled")


def cmd_deprecate(args):
    """Deprecate a theme."""
    vocab = ThemeVocabulary()

    theme = vocab.get(args.signature)
    if not theme:
        print(f"Error: '{args.signature}' not found")
        return

    print(f"Deprecate: {args.signature}")
    print(f"  Description: {theme.description}")
    print()
    confirm = input("Confirm? (y/N): ").strip().lower()

    if confirm == 'y':
        vocab.deprecate(args.signature)
        print("Deprecated successfully")
    else:
        print("Cancelled")


def cmd_seed(args):
    """Seed vocabulary from database."""
    vocab = ThemeVocabulary()

    print(f"Seeding from database (min_count={args.min_count})...")
    added = vocab.seed_from_database(min_count=args.min_count)
    print(f"Added {added} new themes")


def cmd_export(args):
    """Export vocabulary to stdout as JSON."""
    vocab = ThemeVocabulary()
    themes = vocab.get_all_active()

    data = [
        {
            "signature": t.issue_signature,
            "product_area": t.product_area,
            "component": t.component,
            "description": t.description,
            "keywords": t.keywords,
        }
        for t in themes
    ]
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Manage theme vocabulary")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # list
    list_parser = subparsers.add_parser("list", help="List themes")
    list_parser.add_argument("--area", help="Filter by product area")

    # stats
    subparsers.add_parser("stats", help="Show statistics")

    # add
    subparsers.add_parser("add", help="Add new theme")

    # merge
    merge_parser = subparsers.add_parser("merge", help="Merge themes")
    merge_parser.add_argument("source", help="Source signature (will be merged)")
    merge_parser.add_argument("target", help="Target signature (will receive)")

    # deprecate
    dep_parser = subparsers.add_parser("deprecate", help="Deprecate theme")
    dep_parser.add_argument("signature", help="Signature to deprecate")

    # seed
    seed_parser = subparsers.add_parser("seed", help="Seed from database")
    seed_parser.add_argument("--min-count", type=int, default=2, help="Min occurrence count")

    # export
    subparsers.add_parser("export", help="Export as JSON")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "deprecate":
        cmd_deprecate(args)
    elif args.command == "seed":
        cmd_seed(args)
    elif args.command == "export":
        cmd_export(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
