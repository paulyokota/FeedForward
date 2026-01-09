"""
Coda Source Adapter
Normalizes Coda research data into common conversation format.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from . import SourceAdapter, NormalizedConversation
from coda_client import CodaClient

logger = logging.getLogger(__name__)


class CodaAdapter(SourceAdapter):
    """Adapter for Coda research repository data."""

    def __init__(self):
        self.client = CodaClient()

    @property
    def source_name(self) -> str:
        return "coda"

    def fetch(
        self,
        days: Optional[int] = None,
        max_items: Optional[int] = None,
        include_tables: bool = True,
        include_pages: bool = True,
    ) -> List[Dict]:
        """
        Fetch research data from Coda.

        Args:
            days: Not used for Coda (research data is evergreen)
            max_items: Maximum items to fetch
            include_tables: Include synthesis table rows
            include_pages: Include AI summary pages

        Returns:
            List of raw Coda items (pages and table rows)
        """
        items = []

        if include_tables:
            tables = self.client.list_tables()
            for table in tables:
                table_id = table.get("id", "")
                table_name = table.get("name", "")

                # Focus on synthesis/research tables
                if not self._is_research_table(table_name):
                    continue

                try:
                    columns = self.client.get_table_columns(table_id)
                    rows = self.client.get_table_rows(table_id)

                    for row in rows:
                        items.append({
                            "type": "table_row",
                            "table_id": table_id,
                            "table_name": table_name,
                            "row_id": row.get("id"),
                            "values": row.get("values", {}),
                            "columns": {c["id"]: c["name"] for c in columns},
                            "created_at": row.get("createdAt"),
                            "updated_at": row.get("updatedAt"),
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch table {table_name}: {e}")

        if include_pages:
            pages = self.client.list_pages()
            for page in pages:
                if self._is_ai_summary_page(page.get("name", "")):
                    try:
                        content = self.client.get_page_content(page.get("id", ""))
                        if content and len(content) > 50:
                            items.append({
                                "type": "page",
                                "page_id": page.get("id"),
                                "page_name": page.get("name"),
                                "content": content,
                                "created_at": page.get("createdAt"),
                                "updated_at": page.get("updatedAt"),
                            })
                    except Exception as e:
                        logger.debug(f"Failed to fetch page content: {e}")

        if max_items:
            items = items[:max_items]

        logger.info(f"Fetched {len(items)} items from Coda")
        return items

    def normalize(self, raw_data: Dict) -> NormalizedConversation:
        """
        Normalize Coda data to common conversation format.

        Handles both table rows and page content.
        """
        item_type = raw_data.get("type", "unknown")

        if item_type == "table_row":
            return self._normalize_table_row(raw_data)
        elif item_type == "page":
            return self._normalize_page(raw_data)
        else:
            raise ValueError(f"Unknown Coda item type: {item_type}")

    def _normalize_table_row(self, row_data: Dict) -> NormalizedConversation:
        """Normalize a synthesis table row."""
        row_id = row_data.get("row_id", "unknown")
        table_id = row_data.get("table_id", "unknown")
        table_name = row_data.get("table_name", "")
        values = row_data.get("values", {})
        columns = row_data.get("columns", {})

        # Build readable text from row values
        text_parts = []
        for col_id, value in values.items():
            col_name = columns.get(col_id, col_id)
            if value and str(value).strip():
                # Clean up the value
                clean_value = str(value).strip()
                if len(clean_value) > 20:  # Only include substantial content
                    text_parts.append(f"{col_name}: {clean_value}")

        text = "\n".join(text_parts)

        # Parse timestamp
        created_at = self._parse_timestamp(
            row_data.get("created_at") or row_data.get("updated_at")
        )

        return NormalizedConversation(
            id=f"coda_row_{table_id}_{row_id}",
            text=text,
            data_source="coda",
            source_metadata={
                "type": "table_row",
                "table_id": table_id,
                "table_name": table_name,
                "row_id": row_id,
                "columns": list(columns.values()),
            },
            created_at=created_at,
            url=f"https://coda.io/d/{self.client.doc_id}#row-{row_id}",
        )

    def _normalize_page(self, page_data: Dict) -> NormalizedConversation:
        """Normalize an AI Summary page."""
        page_id = page_data.get("page_id", "unknown")
        page_name = page_data.get("page_name", "")
        content = page_data.get("content", "")

        # Extract participant email from page name
        participant = self._extract_participant(page_name)

        # Parse sections from content
        sections = self._parse_ai_summary_sections(content)

        created_at = self._parse_timestamp(
            page_data.get("created_at") or page_data.get("updated_at")
        )

        return NormalizedConversation(
            id=f"coda_page_{page_id}",
            text=content,
            data_source="coda",
            source_metadata={
                "type": "ai_summary",
                "page_id": page_id,
                "page_name": page_name,
                "participant": participant,
                "sections": list(sections.keys()),
            },
            created_at=created_at,
            url=f"https://coda.io/d/{self.client.doc_id}/_/{page_id}",
        )

    def _is_research_table(self, table_name: str) -> bool:
        """Check if table contains research data."""
        name_lower = table_name.lower()
        research_keywords = [
            "synthesis", "synth", "research", "interview",
            "participant", "beta", "feedback", "takeaway",
            "insight", "discovery", "user", "pain", "quote",
        ]
        return any(kw in name_lower for kw in research_keywords)

    def _is_ai_summary_page(self, page_name: str) -> bool:
        """Check if page is an AI Summary."""
        name_lower = page_name.lower()
        return (
            "ai summary" in name_lower
            or "summary" in name_lower
            or "@" in page_name  # Email indicates participant summary
        )

    def _extract_participant(self, page_name: str) -> Optional[str]:
        """Extract participant identifier from page name."""
        # Look for email pattern
        import re
        email_match = re.search(r'[\w\.-]+@[\w\.-]+', page_name)
        if email_match:
            return email_match.group(0)
        return None

    def _parse_ai_summary_sections(self, content: str) -> Dict[str, str]:
        """Parse AI Summary into sections."""
        sections = {}
        current_section = "general"
        current_content = []

        section_markers = [
            "loves", "pain points", "feature requests",
            "workflow", "quotes", "takeaways", "insights",
        ]

        for line in content.split("\n"):
            line_lower = line.lower().strip()

            # Check for section header
            found_section = None
            for marker in section_markers:
                if marker in line_lower and len(line) < 50:
                    found_section = marker.replace(" ", "_")
                    break

            if found_section:
                # Save previous section
                if current_content:
                    sections[current_section] = "\n".join(current_content)
                current_section = found_section
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections[current_section] = "\n".join(current_content)

        return sections

    def _parse_timestamp(self, timestamp: Optional[str]) -> datetime:
        """Parse timestamp string to datetime."""
        if not timestamp:
            return datetime.now()

        try:
            # Handle ISO format
            if "T" in timestamp:
                return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            # Handle date only
            return datetime.strptime(timestamp[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return datetime.now()
