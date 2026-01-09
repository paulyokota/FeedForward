"""
Coda API Client
Wrapper for Coda REST API to fetch research content.
"""
import os
import time
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
import requests

load_dotenv()

logger = logging.getLogger(__name__)


class CodaClient:
    """Client for interacting with Coda API to fetch research data."""

    def __init__(self):
        self.api_key = os.getenv("CODA_API_KEY")
        self.doc_id = os.getenv("CODA_DOC_ID")
        self.base_url = "https://coda.io/apis/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._rate_limit_delay = 0.1  # seconds between requests (faster)

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make a rate-limited request to the Coda API."""
        url = f"{self.base_url}{endpoint}"
        time.sleep(self._rate_limit_delay)

        response = requests.request(method, url, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response.json()

    def list_pages(self, max_pages: int = 500) -> List[Dict]:
        """List all pages in the doc using multiple strategies."""
        pages = []
        seen_ids = set()

        # Strategy 1: Direct pagination (may fail after first page)
        page_token = None
        for attempt in range(10):  # Max 10 pagination attempts
            params = {"limit": 50}
            if page_token:
                params["pageToken"] = page_token

            try:
                result = self._request(
                    "GET", f"/docs/{self.doc_id}/pages", params=params
                )
                for page in result.get("items", []):
                    pid = page.get("id")
                    if pid and pid not in seen_ids:
                        pages.append(page)
                        seen_ids.add(pid)

                page_token = result.get("nextPageToken")
                if not page_token:
                    break
            except Exception as e:
                logger.debug(f"Pagination stopped at {len(pages)} pages: {e}")
                break

        # Strategy 2: Recursively get children of known pages
        def get_children_recursive(parent_id: str, depth: int = 0):
            if depth > 5 or len(pages) >= max_pages:
                return
            try:
                parent = self.get_page(parent_id)
                children = parent.get("children", [])
                for child in children:
                    cid = child.get("id")
                    if cid and cid not in seen_ids:
                        try:
                            full_child = self.get_page(cid)
                            pages.append(full_child)
                            seen_ids.add(cid)
                            get_children_recursive(cid, depth + 1)
                        except Exception:
                            pass
            except Exception:
                pass

        # Get children of all pages we found
        for page in list(pages):  # Copy to avoid modification during iteration
            if len(pages) < max_pages:
                get_children_recursive(page.get("id", ""))

        logger.info(f"Found {len(pages)} pages in Coda doc")
        return pages

    def get_page(self, page_id: str) -> Dict:
        """Get page metadata."""
        return self._request("GET", f"/docs/{self.doc_id}/pages/{page_id}")

    def get_page_content(self, page_id: str) -> str:
        """
        Get rich text content from a page.

        Tries multiple approaches:
        1. /content endpoint for structured content
        2. /export endpoint for HTML
        3. Page metadata subtitle/description
        """
        import re

        # Try the content endpoint first
        try:
            result = self._request(
                "GET",
                f"/docs/{self.doc_id}/pages/{page_id}/content",
            )
            # Content endpoint returns structured data
            content = result.get("content", "")
            if content and len(str(content)) > 50:
                if isinstance(content, dict):
                    # Extract text from structured content
                    return self._extract_text_from_content(content)
                return str(content)
        except Exception as e:
            logger.debug(f"Content endpoint failed for {page_id}: {e}")

        # Try export endpoint
        try:
            result = self._request(
                "GET",
                f"/docs/{self.doc_id}/pages/{page_id}/export",
                params={"outputFormat": "html"},
            )
            html_content = result.get("html", "")
            if html_content:
                text = re.sub(r"<[^>]+>", " ", html_content)
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) > 50:
                    return text
        except Exception as e:
            logger.debug(f"Export endpoint failed for {page_id}: {e}")

        # Try page metadata
        try:
            page = self.get_page(page_id)
            parts = []
            if page.get("subtitle"):
                parts.append(page.get("subtitle"))
            # Check for any text content in the page response
            if page.get("contentText"):
                parts.append(page.get("contentText"))
            return " ".join(parts)
        except Exception as e:
            logger.debug(f"Page metadata failed for {page_id}: {e}")

        return ""

    def _extract_text_from_content(self, content: dict) -> str:
        """Extract plain text from Coda structured content."""
        texts = []

        def extract_recursive(obj):
            if isinstance(obj, str):
                texts.append(obj)
            elif isinstance(obj, dict):
                # Check for text fields
                for key in ["text", "content", "value", "name"]:
                    if key in obj:
                        extract_recursive(obj[key])
                # Recurse into other fields
                for key, value in obj.items():
                    if isinstance(value, (dict, list)):
                        extract_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_recursive(item)

        extract_recursive(content)
        return " ".join(texts)

    def list_tables(self) -> List[Dict]:
        """List all tables in the doc."""
        tables = []
        page_token = None

        while True:
            params = {"limit": 100}
            if page_token:
                params["pageToken"] = page_token

            result = self._request(
                "GET", f"/docs/{self.doc_id}/tables", params=params
            )
            tables.extend(result.get("items", []))

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Found {len(tables)} tables in Coda doc")
        return tables

    def get_table_columns(self, table_id: str) -> List[Dict]:
        """Get column definitions for a table."""
        columns = []
        page_token = None

        while True:
            params = {"limit": 100}
            if page_token:
                params["pageToken"] = page_token

            result = self._request(
                "GET", f"/docs/{self.doc_id}/tables/{table_id}/columns", params=params
            )
            columns.extend(result.get("items", []))

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return columns

    def get_table_rows(
        self, table_id: str, limit: Optional[int] = None
    ) -> List[Dict]:
        """Get all rows from a table."""
        rows = []
        page_token = None

        while True:
            params = {"limit": min(limit or 500, 500)}
            if page_token:
                params["pageToken"] = page_token

            result = self._request(
                "GET", f"/docs/{self.doc_id}/tables/{table_id}/rows", params=params
            )
            rows.extend(result.get("items", []))

            if limit and len(rows) >= limit:
                rows = rows[:limit]
                break

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Found {len(rows)} rows in table {table_id}")
        return rows

    def get_ai_summary_pages(self) -> List[Dict]:
        """
        Find and return AI Summary pages.

        AI Summary pages are typically named with participant emails and contain
        structured research insights.
        """
        pages = self.list_pages()
        ai_summary_pages = []

        for page in pages:
            name = page.get("name", "").lower()
            # AI Summary pages often contain "ai summary" or are participant summaries
            if (
                "ai summary" in name
                or "summary" in name
                or "@" in page.get("name", "")  # Email in name
            ):
                ai_summary_pages.append(page)

        logger.info(f"Found {len(ai_summary_pages)} potential AI Summary pages")
        return ai_summary_pages

    def get_synthesis_tables(self) -> List[Dict]:
        """
        Find synthesis tables containing research data.

        Target tables:
        - Participant Research Synthesis
        - P4 Synth
        - Beta Call Synthesis
        """
        tables = self.list_tables()
        synthesis_tables = []

        target_patterns = [
            "synthesis",
            "synth",
            "participant",
            "research",
            "beta",
            "call",
        ]

        for table in tables:
            name = table.get("name", "").lower()
            if any(pattern in name for pattern in target_patterns):
                synthesis_tables.append(table)

        logger.info(f"Found {len(synthesis_tables)} synthesis tables")
        return synthesis_tables


# Quick connectivity test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = CodaClient()

    print("Testing Coda API connection...")
    pages = client.list_pages()
    print(f"Connected: {len(pages)} pages found")

    tables = client.list_tables()
    print(f"Tables: {len(tables)} found")

    # Show page names
    print("\nPages:")
    for page in pages[:10]:
        print(f"  - {page.get('name', 'Unnamed')}")

    print("\nTables:")
    for table in tables[:10]:
        print(f"  - {table.get('name', 'Unnamed')}")
