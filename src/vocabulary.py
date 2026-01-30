"""
Managed vocabulary for theme extraction.

Instead of freeform extraction → canonicalization, this provides:
1. A curated list of known themes
2. Match-first extraction (try to fit to known themes)
3. Explicit "new theme" proposals that require justification
4. Vocabulary management (add, merge, deprecate)

Based on research showing predefined taxonomy significantly improves consistency.
See: Microsoft ISE, Thematic, anyblockers approaches.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VocabularyTheme:
    """A theme in the managed vocabulary."""

    issue_signature: str
    product_area: str
    component: str
    description: str  # Human-readable description
    keywords: list[str]  # Keywords/aliases that map to this theme
    example_intents: list[str]  # Example user intents for few-shot
    engineering_fix: str = ""  # What engineering work would address this
    status: str = "active"  # active, deprecated, merged
    merged_into: Optional[str] = None  # If merged, the target signature
    deprecation_reason: Optional[str] = None  # Why this theme was deprecated
    support_solution: Optional[str] = None  # How support resolved this (for documentation)
    root_cause: Optional[str] = None  # Identified root cause (for engineering)
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat() if self.created_at else None
        d['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'VocabularyTheme':
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
        if isinstance(d.get('updated_at'), str):
            d['updated_at'] = datetime.fromisoformat(d['updated_at'])
        return cls(**d)


class ThemeVocabulary:
    """
    Manages a vocabulary of known themes.

    The vocabulary is stored as a JSON file for easy review and editing.
    It can also be backed by the database for runtime queries.
    """

    def __init__(self, vocab_path: Optional[Path] = None):
        self.vocab_path = vocab_path or Path(__file__).parent.parent / "config" / "theme_vocabulary.json"
        self._themes: dict[str, VocabularyTheme] = {}
        self._url_context_mapping: dict[str, str] = {}
        self._product_area_mapping: dict[str, list[str]] = {}
        self._signature_quality_guidelines: dict = {}
        self._term_distinctions: dict = {}  # Issue #153: Term distinctions for vocabulary enhancement
        self._load()

    def _load(self) -> None:
        """Load vocabulary from file."""
        if self.vocab_path.exists():
            try:
                data = json.loads(self.vocab_path.read_text())
                self._themes = {
                    sig: VocabularyTheme.from_dict(theme)
                    for sig, theme in data.get("themes", {}).items()
                }
                # Load URL context mapping for product area disambiguation
                self._url_context_mapping = data.get("url_context_mapping", {})
                # Remove comment entries
                self._url_context_mapping = {
                    k: v for k, v in self._url_context_mapping.items()
                    if not k.startswith("_")
                }
                # Load product area mapping
                self._product_area_mapping = data.get("product_area_mapping", {})
                # Load signature quality guidelines
                self._signature_quality_guidelines = data.get("signature_quality_guidelines", {})
                # Load term distinctions (Issue #153)
                self._term_distinctions = data.get("term_distinctions", {})
                logger.info(f"Loaded {len(self._themes)} themes, {len(self._url_context_mapping)} URL patterns, and term distinctions from vocabulary")
            except Exception as e:
                logger.error(f"Failed to load vocabulary: {e}")
                self._themes = {}
                self._url_context_mapping = {}
                self._product_area_mapping = {}
        else:
            logger.info("No vocabulary file found, starting fresh")
            self._themes = {}
            self._url_context_mapping = {}
            self._product_area_mapping = {}

    def _save(self) -> None:
        """Save vocabulary to file."""
        self.vocab_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "updated_at": datetime.utcnow().isoformat(),
            "themes": {
                sig: theme.to_dict()
                for sig, theme in self._themes.items()
            }
        }
        self.vocab_path.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved {len(self._themes)} themes to vocabulary")

    def get_all_active(self) -> list[VocabularyTheme]:
        """Get all active themes."""
        return [t for t in self._themes.values() if t.status == "active"]

    def get_by_product_area(self, product_area: str) -> list[VocabularyTheme]:
        """Get active themes for a product area."""
        return [
            t for t in self._themes.values()
            if t.status == "active" and t.product_area == product_area
        ]

    def get(self, signature: str) -> Optional[VocabularyTheme]:
        """Get a theme by signature."""
        theme = self._themes.get(signature)
        if theme and theme.status == "merged" and theme.merged_into:
            return self._themes.get(theme.merged_into)
        return theme

    def add(
        self,
        issue_signature: str,
        product_area: str,
        component: str,
        description: str,
        keywords: list[str] = None,
        example_intents: list[str] = None,
    ) -> VocabularyTheme:
        """Add a new theme to the vocabulary."""
        theme = VocabularyTheme(
            issue_signature=issue_signature,
            product_area=product_area,
            component=component,
            description=description,
            keywords=keywords or [],
            example_intents=example_intents or [],
        )
        self._themes[issue_signature] = theme
        self._save()
        logger.info(f"Added theme to vocabulary: {issue_signature}")
        return theme

    def update(
        self,
        signature: str,
        description: str = None,
        keywords: list[str] = None,
        example_intents: list[str] = None,
    ) -> Optional[VocabularyTheme]:
        """Update an existing theme."""
        theme = self._themes.get(signature)
        if not theme:
            return None

        if description is not None:
            theme.description = description
        if keywords is not None:
            theme.keywords = keywords
        if example_intents is not None:
            theme.example_intents = example_intents
        theme.updated_at = datetime.utcnow()

        self._save()
        return theme

    def merge(self, source_signature: str, target_signature: str) -> bool:
        """Merge source theme into target."""
        source = self._themes.get(source_signature)
        target = self._themes.get(target_signature)

        if not source or not target:
            return False

        # Mark source as merged
        source.status = "merged"
        source.merged_into = target_signature
        source.updated_at = datetime.utcnow()

        # Add source keywords to target
        for kw in source.keywords:
            if kw not in target.keywords:
                target.keywords.append(kw)
        target.keywords.append(source_signature)  # Old signature becomes keyword
        target.updated_at = datetime.utcnow()

        self._save()
        logger.info(f"Merged {source_signature} into {target_signature}")
        return True

    def deprecate(self, signature: str) -> bool:
        """Deprecate a theme (no longer used)."""
        theme = self._themes.get(signature)
        if not theme:
            return False

        theme.status = "deprecated"
        theme.updated_at = datetime.utcnow()
        self._save()
        logger.info(f"Deprecated theme: {signature}")
        return True

    def seed_from_database(self, min_count: int = 2) -> int:
        """
        Seed vocabulary from existing high-count themes in database.

        Returns number of themes added.
        """
        try:
            from db.connection import get_connection
        except ImportError:
            from .db.connection import get_connection

        added = 0

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        issue_signature,
                        product_area,
                        component,
                        occurrence_count,
                        sample_user_intent,
                        sample_symptoms
                    FROM theme_aggregates
                    WHERE occurrence_count >= %s
                    ORDER BY occurrence_count DESC
                """, (min_count,))

                for row in cur.fetchall():
                    sig, area, comp, count, intent, symptoms = row

                    # Skip if already in vocabulary
                    if sig in self._themes:
                        continue

                    # Create description from intent
                    description = intent[:200] if intent else f"{area}/{comp} issue"

                    # Create keywords from symptoms
                    keywords = []
                    if symptoms:
                        keywords = [s.lower() for s in symptoms[:5]]

                    self._themes[sig] = VocabularyTheme(
                        issue_signature=sig,
                        product_area=area,
                        component=comp,
                        description=description,
                        keywords=keywords,
                        example_intents=[intent] if intent else [],
                    )
                    added += 1

        if added > 0:
            self._save()

        logger.info(f"Seeded {added} themes from database (min_count={min_count})")
        return added

    def format_for_prompt(self, product_area: str = None, max_themes: int = 50) -> str:
        """
        Format vocabulary for inclusion in extraction prompt.

        Returns a structured list of known themes for the LLM to match against.
        """
        themes = self.get_by_product_area(product_area) if product_area else self.get_all_active()

        # Sort by relevance (same product_area first, then alphabetically)
        themes = sorted(themes, key=lambda t: (t.product_area != product_area if product_area else False, t.issue_signature))

        lines = []
        for theme in themes[:max_themes]:
            keywords_str = f" (also: {', '.join(theme.keywords[:3])})" if theme.keywords else ""
            lines.append(
                f"- **{theme.issue_signature}** [{theme.product_area}/{theme.component}]: {theme.description[:100]}{keywords_str}"
            )

        return "\n".join(lines)

    def format_signature_examples(self) -> str:
        """
        Format signature quality guidelines for inclusion in extraction prompt.

        Returns examples of good vs bad signatures to guide the LLM.
        """
        if not self._signature_quality_guidelines:
            return ""

        lines = []

        # Good examples
        good_examples = self._signature_quality_guidelines.get("good_examples", [])
        if good_examples:
            lines.append("**Good Signature Examples** (Be specific like these):")
            for ex in good_examples:
                lines.append(f"   ✅ {ex['signature']} - {ex['why']}")
            lines.append("")

        # Bad examples
        bad_examples = self._signature_quality_guidelines.get("bad_examples", [])
        if bad_examples:
            lines.append("**Bad Signature Examples** (Avoid generic terms):")
            for ex in bad_examples:
                lines.append(f"   ❌ {ex['signature']} - {ex['why_bad']}")
                lines.append(f"      → Better: {ex['better']}")
            lines.append("")

        # Add term distinctions if available (Issue #153)
        term_guidance = self.format_term_distinctions()
        if term_guidance:
            lines.append("")
            lines.append(term_guidance)

        return "\n".join(lines)

    def format_term_distinctions(self) -> str:
        """
        Format term distinctions for inclusion in extraction prompt.

        Issue #153: Provides guidance on distinguishing similar-looking terms
        that have different meanings or code paths.
        """
        if not self._term_distinctions:
            return ""

        lines = []
        lines.append("**Term Distinctions** (Clarify these when they appear):")

        # Similar UX pairs - terms that co-occur but need clarification
        similar_ux = self._term_distinctions.get("similar_ux", {})
        if similar_ux and not similar_ux.get("_description"):
            similar_ux = {k: v for k, v in similar_ux.items() if not k.startswith("_")}
        if similar_ux:
            lines.append("")
            lines.append("  *Terms that often appear together - clarify which is affected:*")
            for pair_name, pair_data in similar_ux.items():
                if pair_name.startswith("_"):
                    continue
                terms = pair_data.get("terms", [])
                guidance = pair_data.get("guidance", "")
                if terms and guidance:
                    lines.append(f"   - {' vs '.join(terms)}: {guidance}")

        # Different model pairs - same code but different user concepts
        different_model = self._term_distinctions.get("different_model", {})
        if different_model:
            dm_pairs = {k: v for k, v in different_model.items() if not k.startswith("_")}
            if dm_pairs:
                lines.append("")
                lines.append("  *Same system, different lifecycle states - ask about content state:*")
                for pair_name, pair_data in dm_pairs.items():
                    terms = pair_data.get("terms", [])
                    guidance = pair_data.get("guidance", "")
                    if terms and guidance:
                        lines.append(f"   - {' vs '.join(terms)}: {guidance}")

        # Name confusion pairs - names overlap but different features
        name_confusion = self._term_distinctions.get("name_confusion", {})
        if name_confusion:
            nc_pairs = {k: v for k, v in name_confusion.items() if not k.startswith("_")}
            if nc_pairs:
                lines.append("")
                lines.append("  *Names overlap but these are different features:*")
                for pair_name, pair_data in nc_pairs.items():
                    terms = pair_data.get("terms", [])
                    guidance = pair_data.get("guidance", "")
                    if terms and guidance:
                        lines.append(f"   - {' vs '.join(terms)}: {guidance}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def match_url_to_product_area(self, url: Optional[str]) -> Optional[str]:
        """
        Match a URL to a product area using url_context_mapping.

        Returns the product area if a pattern matches, None otherwise.
        """
        if not url or not self._url_context_mapping:
            return None

        # Check each pattern against the URL
        for pattern, product_area in self._url_context_mapping.items():
            if pattern in url:
                logger.info(f"URL context match: {pattern} -> {product_area}")
                return product_area

        return None

    def get_stats(self) -> dict:
        """Get vocabulary statistics."""
        active = [t for t in self._themes.values() if t.status == "active"]
        by_area = {}
        for t in active:
            by_area[t.product_area] = by_area.get(t.product_area, 0) + 1

        return {
            "total": len(self._themes),
            "active": len(active),
            "deprecated": len([t for t in self._themes.values() if t.status == "deprecated"]),
            "merged": len([t for t in self._themes.values() if t.status == "merged"]),
            "by_product_area": by_area,
            "url_patterns": len(self._url_context_mapping),
        }


# Convenience function
def get_vocabulary() -> ThemeVocabulary:
    """Get the default vocabulary instance."""
    return ThemeVocabulary()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    vocab = ThemeVocabulary()

    print("Current vocabulary stats:")
    print(json.dumps(vocab.get_stats(), indent=2))

    print("\nSeeding from database...")
    added = vocab.seed_from_database(min_count=2)
    print(f"Added {added} themes")

    print("\nUpdated stats:")
    print(json.dumps(vocab.get_stats(), indent=2))

    print("\nSample prompt format:")
    print(vocab.format_for_prompt(product_area="billing", max_themes=10))
