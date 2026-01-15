"""
Coda Search Source Adapter

Extracts searchable content from Coda pages and themes.
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from .base import SearchSourceAdapter
from ..models import SearchableContent

logger = logging.getLogger(__name__)

# Path to the existing Coda content database
CODA_DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "coda_raw" / "coda_content.db"


class CodaSearchAdapter(SearchSourceAdapter):
    """
    Adapter for Coda research data.

    Supports two source types:
    - coda_page: AI Summary pages and research pages
    - coda_theme: Extracted themes from synthesis tables
    """

    def __init__(self, source_type: str = "coda_page", db_path: Optional[Path] = None):
        """
        Initialize the Coda adapter.

        Args:
            source_type: 'coda_page' or 'coda_theme'
            db_path: Path to SQLite database (defaults to standard location)
        """
        if source_type not in ("coda_page", "coda_theme"):
            raise ValueError(f"Invalid source_type: {source_type}. Must be 'coda_page' or 'coda_theme'")

        self._source_type = source_type
        self._db_path = db_path or CODA_DB_PATH
        self._doc_id = os.getenv("CODA_DOC_ID", "")

    def get_source_type(self) -> str:
        """Returns 'coda_page' or 'coda_theme'."""
        return self._source_type

    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection with row factory."""
        if not self._db_path.exists():
            raise FileNotFoundError(f"Coda database not found: {self._db_path}")

        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def extract_content(self, source_id: str) -> Optional[SearchableContent]:
        """Extract content for a specific Coda item."""
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            if self._source_type == "coda_page":
                return self._extract_page(cur, source_id)
            else:
                return self._extract_theme(cur, source_id)
        except Exception as e:
            logger.error(f"Failed to extract Coda content {source_id}: {e}")
            return None
        finally:
            conn.close()

    def extract_all(self, limit: Optional[int] = None) -> Iterator[SearchableContent]:
        """Extract all content from Coda."""
        try:
            conn = self._get_connection()
            cur = conn.cursor()

            if self._source_type == "coda_page":
                yield from self._extract_all_pages(cur, limit)
            else:
                yield from self._extract_all_themes(cur, limit)
        except FileNotFoundError:
            logger.warning(f"Coda database not found: {self._db_path}")
            return
        except Exception as e:
            logger.error(f"Failed to extract all Coda content: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

    def get_source_url(self, source_id: str) -> str:
        """Get Coda URL for a source item."""
        if self._source_type == "coda_page":
            return f"https://coda.io/d/{self._doc_id}/_/{source_id}"
        else:
            # Themes link to the doc with theme anchor
            return f"https://coda.io/d/{self._doc_id}#theme_{source_id}"

    # --- Page extraction methods ---

    def _extract_page(self, cur: sqlite3.Cursor, page_id: str) -> Optional[SearchableContent]:
        """Extract a single page."""
        cur.execute("""
            SELECT canvas_id, name, content, parent_id
            FROM pages
            WHERE canvas_id = ?
        """, (page_id,))
        row = cur.fetchone()

        if not row:
            return None

        return self._row_to_page_content(row)

    def _extract_all_pages(self, cur: sqlite3.Cursor, limit: Optional[int]) -> Iterator[SearchableContent]:
        """Extract all pages."""
        query = """
            SELECT canvas_id, name, content, parent_id
            FROM pages
            WHERE content IS NOT NULL AND LENGTH(content) > 50
            ORDER BY canvas_id
        """
        if limit:
            query += f" LIMIT {limit}"

        cur.execute(query)
        for row in cur.fetchall():
            content = self._row_to_page_content(row)
            if content:
                yield content

    def _row_to_page_content(self, row: sqlite3.Row) -> Optional[SearchableContent]:
        """Convert page row to SearchableContent."""
        content = row["content"]
        if not content or len(content.strip()) < 50:
            return None

        page_id = row["canvas_id"]
        title = row["name"] or f"Page {page_id}"

        # Extract participant info from title if present
        participant = None
        if "@" in title:
            import re
            match = re.search(r'[\w\.-]+@[\w\.-]+', title)
            if match:
                participant = match.group(0)

        # Detect page type from title
        page_type = "general"
        title_lower = title.lower()
        if "ai summary" in title_lower or "summary" in title_lower:
            page_type = "ai_summary"
        elif "synthesis" in title_lower:
            page_type = "synthesis"
        elif "interview" in title_lower:
            page_type = "interview"

        return SearchableContent(
            source_type="coda_page",
            source_id=page_id,
            title=title,
            content=content,
            url=self.get_source_url(page_id),
            metadata={
                "page_type": page_type,
                "participant": participant,
                "parent_id": row["parent_id"],
            }
        )

    # --- Theme extraction methods ---

    def _extract_theme(self, cur: sqlite3.Cursor, theme_id: str) -> Optional[SearchableContent]:
        """Extract a single theme from theme_aggregates in PostgreSQL."""
        # Note: Themes are in PostgreSQL, not SQLite
        # This method uses PostgreSQL for theme extraction
        try:
            from src.db.connection import get_connection

            with get_connection() as conn:
                with conn.cursor() as pg_cur:
                    pg_cur.execute("""
                        SELECT issue_signature, product_area, component,
                               sample_user_intent, sample_symptoms, occurrence_count
                        FROM theme_aggregates
                        WHERE issue_signature = %s
                    """, (theme_id,))
                    row = pg_cur.fetchone()

                    if not row:
                        return None

                    return self._pg_row_to_theme_content(row)
        except Exception as e:
            logger.error(f"Failed to extract theme {theme_id}: {e}")
            return None

    def _extract_all_themes(self, cur: sqlite3.Cursor, limit: Optional[int]) -> Iterator[SearchableContent]:
        """Extract all themes from PostgreSQL theme_aggregates."""
        try:
            from src.db.connection import get_connection

            with get_connection() as conn:
                with conn.cursor() as pg_cur:
                    query = """
                        SELECT issue_signature, product_area, component,
                               sample_user_intent, sample_symptoms, occurrence_count
                        FROM theme_aggregates
                        ORDER BY occurrence_count DESC
                    """
                    if limit:
                        query += f" LIMIT {limit}"

                    pg_cur.execute(query)
                    for row in pg_cur.fetchall():
                        content = self._pg_row_to_theme_content(row)
                        if content:
                            yield content
        except Exception as e:
            logger.error(f"Failed to extract themes: {e}")
            return

    def _pg_row_to_theme_content(self, row: tuple) -> Optional[SearchableContent]:
        """Convert PostgreSQL theme row to SearchableContent."""
        import json

        signature, product_area, component, intent, symptoms_json, count = row

        # Build searchable content from theme data
        parts = [
            f"Theme: {signature.replace('_', ' ')}",
            f"Product Area: {product_area}",
            f"Component: {component}",
        ]

        if intent:
            parts.append(f"User Intent: {intent}")

        if symptoms_json:
            try:
                symptoms = symptoms_json if isinstance(symptoms_json, list) else json.loads(symptoms_json)
                if symptoms:
                    parts.append(f"Symptoms: {', '.join(symptoms)}")
            except (json.JSONDecodeError, TypeError):
                pass

        content = "\n".join(parts)

        return SearchableContent(
            source_type="coda_theme",
            source_id=signature,  # Use signature as ID
            title=signature.replace("_", " ").title(),
            content=content,
            url=self.get_source_url(signature),
            metadata={
                "product_area": product_area,
                "component": component,
                "occurrence_count": count,
            }
        )


# Convenience factory for both types
def get_coda_adapters() -> list[CodaSearchAdapter]:
    """Get both Coda adapters (pages and themes)."""
    return [
        CodaSearchAdapter(source_type="coda_page"),
        CodaSearchAdapter(source_type="coda_theme"),
    ]
