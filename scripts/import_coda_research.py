#!/usr/bin/env python3
"""
Import Coda Research Data

Imports research data from Coda doc:
- AI Summary pages (participant research insights)
- Synthesis tables (Participant Research Synthesis, P4 Synth)
- Discovery Learnings page (JTBD framework)

Extracts themes and stores in database with data_source='coda'.
"""
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.coda_client import CodaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# Import ALL tables dynamically - no hardcoded list
# Will fetch all tables from Coda and import research-relevant data
SYNTHESIS_TABLES = None  # Will be populated dynamically

# AI Summary page pattern
AI_SUMMARY_PAGE_NAME = "AI Summary"

# Discovery Learnings page
DISCOVERY_LEARNINGS_ID = "canvas-y5vCjY0Okl"


class CodaResearchImporter:
    """Imports and processes research data from Coda."""

    def __init__(self):
        self.client = CodaClient()
        self.themes: List[Dict] = []
        self.import_stats = {
            "ai_summaries_imported": 0,
            "synthesis_rows_imported": 0,
            "discovery_items_imported": 0,
            "total_themes_extracted": 0,
            "pages_with_content": 0,
            "pages_empty": 0,
        }

    def import_all_pages(self) -> List[Dict]:
        """
        Import ALL pages from Coda and extract themes.

        Processes every page in the document to extract research insights.
        """
        logger.info("Importing ALL Coda pages...")
        pages = self.client.list_pages()
        logger.info(f"Total pages found: {len(pages)}")

        summaries = []
        processed_ids = set()

        # Process ALL pages
        total_pages = len(pages)
        for idx, page in enumerate(pages):
            page_id = page.get("id")
            if page_id in processed_ids:
                continue
            processed_ids.add(page_id)

            page_name = page.get("name", "")

            # Progress logging every 50 pages
            if idx % 50 == 0:
                logger.info(f"Progress: {idx}/{total_pages} pages processed, {len(self.themes)} themes extracted")

            try:
                content = self.client.get_page_content(page_id)

                # Get parent page for context
                parent_id = page.get("parent", {}).get("id")
                parent_name = ""
                if parent_id:
                    try:
                        parent = self.client.get_page(parent_id)
                        parent_name = parent.get("name", "")
                    except Exception:
                        pass

                if not content or len(content.strip()) < 20:
                    self.import_stats["pages_empty"] += 1
                    continue

                self.import_stats["pages_with_content"] += 1

                # Determine page type for better theme extraction
                page_type = "general"
                if page_name == AI_SUMMARY_PAGE_NAME:
                    page_type = "ai_summary"
                    self.import_stats["ai_summaries_imported"] += 1
                elif "@" in page_name and "." in page_name:
                    page_type = "participant"
                elif any(kw in page_name.lower() for kw in ["discovery", "learning", "insight", "finding", "research"]):
                    page_type = "research"

                # Extract themes
                themes = self._extract_themes_from_ai_summary(content, parent_name or page_name)

                if themes:
                    logger.info(f"Extracted {len(themes)} themes from {page_type} page: {page_name[:50]}")

                summary = {
                    "page_id": page_id,
                    "page_name": page_name,
                    "page_type": page_type,
                    "parent_name": parent_name,
                    "content_length": len(content),
                    "themes_count": len(themes),
                }
                summaries.append(summary)

                for theme in themes:
                    theme["source_page_id"] = page_id
                    theme["source_page_name"] = page_name
                    theme["page_type"] = page_type
                    theme["participant"] = parent_name if page_type == "ai_summary" else page_name
                    self.themes.append(theme)

            except Exception as e:
                logger.debug(f"Failed to process page {page_id} ({page_name}): {e}")

        logger.info(
            f"Processed {len(pages)} pages: "
            f"{self.import_stats['pages_with_content']} with content, "
            f"{self.import_stats['pages_empty']} empty, "
            f"{self.import_stats['ai_summaries_imported']} AI Summaries"
        )
        return summaries

    # Keep old method name for compatibility
    def import_ai_summaries(self) -> List[Dict]:
        """Alias for import_all_pages for backwards compatibility."""
        return self.import_all_pages()

    def _extract_themes_from_ai_summary(
        self, content: str, participant: str = ""
    ) -> List[Dict]:
        """Extract themes from AI Summary content."""
        themes = []

        # Common section patterns in AI summaries
        section_patterns = [
            (r"(?:loves?|positive|likes?)[:\s]+([^.!?]+[.!?])", "positive_feedback"),
            (r"(?:pain\s*points?|frustrat|problems?|issues?)[:\s]+([^.!?]+[.!?])", "pain_point"),
            (r"(?:feature\s*requests?|wish|wants?|needs?)[:\s]+([^.!?]+[.!?])", "feature_request"),
            (r"(?:workflow|process)[:\s]+([^.!?]+[.!?])", "workflow_insight"),
            (r'"([^"]{10,})"', "user_quote"),  # Quoted text
        ]

        for pattern, theme_type in section_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches[:5]:  # Limit per section
                if len(match.strip()) > 20:  # Skip very short matches
                    themes.append({
                        "type": theme_type,
                        "text": match.strip()[:500],
                        "source": "ai_summary",
                        "data_source": "coda",
                    })

        # If no structured themes found, extract key sentences
        if not themes:
            sentences = re.split(r"[.!?]+", content)
            for sentence in sentences[:10]:
                sentence = sentence.strip()
                if len(sentence) > 30 and len(sentence) < 300:
                    # Classify based on keywords
                    sentence_lower = sentence.lower()
                    if any(w in sentence_lower for w in ["love", "great", "amazing", "helpful"]):
                        theme_type = "positive_feedback"
                    elif any(w in sentence_lower for w in ["pain", "frustrat", "difficult", "confus", "issue", "problem"]):
                        theme_type = "pain_point"
                    elif any(w in sentence_lower for w in ["wish", "want", "need", "would be nice", "should"]):
                        theme_type = "feature_request"
                    else:
                        theme_type = "insight"

                    themes.append({
                        "type": theme_type,
                        "text": sentence,
                        "source": "ai_summary",
                        "data_source": "coda",
                    })

        return themes

    def import_synthesis_tables(self) -> List[Dict]:
        """
        Import ALL tables from Coda and extract themes.

        Dynamically discovers all tables and imports data from each one.
        """
        logger.info("Importing ALL Coda tables...")
        all_rows = []

        # Get ALL tables from Coda
        all_tables = self.client.list_tables()
        logger.info(f"Found {len(all_tables)} total tables in Coda doc")

        # Filter to primary tables (grid-) to avoid duplicate views
        primary_tables = {
            t.get("name"): t.get("id")
            for t in all_tables
            if t.get("id", "").startswith("grid-")
        }
        logger.info(f"Processing {len(primary_tables)} primary tables (excluding views)")

        tables_with_data = 0
        for table_name, table_id in primary_tables.items():
            try:
                # Get columns first to understand structure
                columns = self.client.get_table_columns(table_id)
                col_map = {c.get("id"): c.get("name") for c in columns}
                col_names = [c.get("name", "").lower() for c in columns]

                # Check if table has research-relevant columns
                research_columns = [
                    "takeaway", "theme", "goal", "shocker", "wish", "pain",
                    "feedback", "quote", "insight", "finding", "confusion",
                    "blocker", "feature", "request", "problem", "issue",
                    "mvp", "priority", "jtbd", "job", "need", "want"
                ]
                has_research_columns = any(
                    any(rc in col for rc in research_columns)
                    for col in col_names
                )

                # Get rows (limit per table to avoid timeout)
                rows = self.client.get_table_rows(table_id, limit=500)

                if not rows:
                    continue

                tables_with_data += 1
                logger.info(f"Processing {table_name}: {len(rows)} rows, {len(columns)} columns")

                for row in rows:
                    row_data = {
                        "table_name": table_name,
                        "table_id": table_id,
                        "row_id": row.get("id"),
                        "values": {},
                    }

                    # Extract values using column names
                    values = row.get("values", {})
                    for col_id, value in values.items():
                        col_name = col_map.get(col_id, col_id)
                        row_data["values"][col_name] = value

                    all_rows.append(row_data)

                    # Extract themes from this row
                    themes = self._extract_themes_from_row(row_data)
                    for theme in themes:
                        theme["source_table"] = table_name
                        theme["source_row_id"] = row.get("id")
                        self.themes.append(theme)

                self.import_stats["synthesis_rows_imported"] += len(rows)

            except Exception as e:
                logger.debug(f"Skipped table {table_name}: {e}")

        logger.info(
            f"Imported {self.import_stats['synthesis_rows_imported']} rows "
            f"from {tables_with_data} tables"
        )
        return all_rows

    def _extract_themes_from_row(self, row_data: Dict) -> List[Dict]:
        """Extract themes from a synthesis table row - capture ALL text content."""
        themes = []
        values = row_data.get("values", {})

        # Key fields to look for (case-insensitive matching)
        # Maps partial field names to theme types
        theme_fields = {
            "takeaway": "insight",
            "theme": "insight",
            "goal": "user_goal",
            "shocker": "pain_point",
            "shocking": "pain_point",
            "game changer": "pain_point",
            "wishlist": "feature_request",
            "wish list": "feature_request",
            "wish": "feature_request",
            "confusion": "pain_point",
            "feedback": "feedback",
            "quote": "user_quote",
            "wtp": "willingness_to_pay",
            "willingness": "willingness_to_pay",
            "blocker": "blocker",
            "dealbreaker": "blocker",
            "mvp": "mvp_feature",
            "chosen plan": "pricing_insight",
            "creation time": "workflow_metric",
            "insight": "insight",
            "finding": "insight",
            "note": "note",
            "summary": "insight",
            "comment": "note",
            "description": "insight",
            "detail": "insight",
            "observation": "insight",
            "learning": "insight",
            "pain": "pain_point",
            "problem": "pain_point",
            "issue": "pain_point",
            "request": "feature_request",
            "feature": "feature_request",
            "need": "user_goal",
            "want": "user_goal",
        }

        matched_fields = set()

        # First pass: match specific field patterns
        for field_key, theme_type in theme_fields.items():
            for col_name, value in values.items():
                col_lower = col_name.lower()
                if field_key in col_lower and value:
                    text = str(value) if not isinstance(value, (list, dict)) else json.dumps(value)
                    text = text.strip()

                    # Skip empty, very short, or just link values
                    if len(text) < 10 or text.startswith('/_su') or text.startswith('http'):
                        continue

                    themes.append({
                        "type": theme_type,
                        "text": text[:500],
                        "source": "synthesis_table",
                        "field": col_name,
                        "table": row_data.get("table_name", "unknown"),
                        "data_source": "coda",
                    })
                    matched_fields.add(col_name)

        # Second pass: capture ANY text content >= 50 chars that wasn't matched
        for col_name, value in values.items():
            if col_name in matched_fields:
                continue

            if value:
                text = str(value) if not isinstance(value, (list, dict)) else json.dumps(value)
                text = text.strip()

                # Only capture substantial text content
                if len(text) >= 50 and not text.startswith('/_su') and not text.startswith('http'):
                    # Skip purely numeric or date-like content
                    if not text.replace('.', '').replace('-', '').replace('/', '').isdigit():
                        themes.append({
                            "type": "raw_content",
                            "text": text[:500],
                            "source": "synthesis_table",
                            "field": col_name,
                            "table": row_data.get("table_name", "unknown"),
                            "data_source": "coda",
                        })

        return themes

    def import_discovery_learnings(self) -> Dict:
        """
        Import Discovery Learnings page.

        Contains:
        - Jobs to Be Done (JTBD) framework
        - MVP feature priorities
        - User needs mapping
        """
        logger.info("Importing Discovery Learnings page...")

        try:
            content = self.client.get_page_content(DISCOVERY_LEARNINGS_ID)
            if not content or len(content.strip()) < 50:
                logger.warning("Discovery Learnings page is empty")
                return {}

            learnings = {
                "page_id": DISCOVERY_LEARNINGS_ID,
                "content": content,
                "themes": [],
            }

            # Extract JTBD patterns
            jtbd_patterns = [
                r"(?:job|jtbd|when\s+i)[:\s]+([^.!?]+[.!?])",
                r"(?:users?\s+want|need)\s+to\s+([^.!?]+[.!?])",
                r"(?:so\s+that|in\s+order\s+to)\s+([^.!?]+[.!?])",
            ]

            for pattern in jtbd_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches[:5]:
                    if len(match.strip()) > 20:
                        theme = {
                            "type": "jtbd",
                            "text": match.strip()[:500],
                            "source": "discovery_learnings",
                            "data_source": "coda",
                        }
                        learnings["themes"].append(theme)
                        self.themes.append(theme)

            # Extract MVP priorities
            mvp_patterns = [
                r"(?:mvp|priority|p1|must\s*have)[:\s]+([^.!?]+[.!?])",
                r"(?:critical|essential|important)[:\s]+([^.!?]+[.!?])",
            ]

            for pattern in mvp_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches[:5]:
                    if len(match.strip()) > 20:
                        theme = {
                            "type": "mvp_priority",
                            "text": match.strip()[:500],
                            "source": "discovery_learnings",
                            "data_source": "coda",
                        }
                        learnings["themes"].append(theme)
                        self.themes.append(theme)

            self.import_stats["discovery_items_imported"] = len(learnings["themes"])
            logger.info(f"Extracted {len(learnings['themes'])} themes from Discovery Learnings")

            return learnings

        except Exception as e:
            logger.error(f"Failed to import Discovery Learnings: {e}")
            return {}

    def run_full_import(self) -> Tuple[List[Dict], Dict]:
        """Run complete import from all Coda sources."""
        logger.info("=" * 60)
        logger.info("Starting Coda Research Import")
        logger.info("=" * 60)

        # Import tables FIRST (this is where the real data is)
        # Coda canvas pages don't expose content via API
        synthesis_rows = self.import_synthesis_tables()

        # Try pages but expect limited results from canvas pages
        ai_summaries = self.import_ai_summaries()

        # Discovery learnings is also a canvas page
        discovery = self.import_discovery_learnings()

        # Update total theme count
        self.import_stats["total_themes_extracted"] = len(self.themes)

        logger.info("=" * 60)
        logger.info("Import Complete")
        logger.info(f"  AI Summaries: {self.import_stats['ai_summaries_imported']}")
        logger.info(f"  Synthesis Rows: {self.import_stats['synthesis_rows_imported']}")
        logger.info(f"  Discovery Items: {self.import_stats['discovery_items_imported']}")
        logger.info(f"  Total Themes: {self.import_stats['total_themes_extracted']}")
        logger.info("=" * 60)

        return self.themes, self.import_stats

    def generate_report(self, output_path: Optional[str] = None) -> str:
        """Generate markdown report of imported data."""
        if not output_path:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_path = f"reports/coda_import_{date_str}.md"

        # Count themes by type
        type_counts = {}
        source_counts = {}
        for theme in self.themes:
            theme_type = theme.get("type", "unknown")
            type_counts[theme_type] = type_counts.get(theme_type, 0) + 1

            source = theme.get("source", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1

        report = f"""# Coda Research Import Report

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Summary

| Metric | Count |
|--------|-------|
| AI Summaries Imported | {self.import_stats['ai_summaries_imported']} |
| Synthesis Rows Imported | {self.import_stats['synthesis_rows_imported']} |
| Discovery Items Imported | {self.import_stats['discovery_items_imported']} |
| **Total Themes Extracted** | **{self.import_stats['total_themes_extracted']}** |
| Pages with Content | {self.import_stats['pages_with_content']} |
| Empty Pages | {self.import_stats['pages_empty']} |

## Theme Breakdown by Type

| Theme Type | Count | Source |
|------------|-------|--------|
"""
        for theme_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            report += f"| {theme_type} | {count} | Mixed |\n"

        report += """
## Theme Breakdown by Source

| Source | Count |
|--------|-------|
"""
        for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
            report += f"| {source} | {count} |\n"

        # High-value themes with examples
        report += """
## High-Value Themes (Examples)

"""
        # Group by type and show examples
        type_examples = {}
        for theme in self.themes:
            theme_type = theme.get("type", "unknown")
            if theme_type not in type_examples:
                type_examples[theme_type] = []
            if len(type_examples[theme_type]) < 3:
                type_examples[theme_type].append(theme)

        for theme_type, examples in sorted(type_examples.items()):
            report += f"### {theme_type.replace('_', ' ').title()}\n\n"
            for i, ex in enumerate(examples, 1):
                text = ex.get("text", "")[:200]
                source = ex.get("source", "unknown")
                report += f"{i}. \"{text}...\" *(from {source})*\n"
            report += "\n"

        report += """
## Recommendations

Based on this research data import:

1. **Pain Points** should be cross-referenced with Intercom support themes
2. **Feature Requests** from research have higher confidence than support-only themes
3. **User Quotes** can be used as evidence in Shortcut stories
4. **JTBD themes** inform product area prioritization

---
*Auto-generated by FeedForward Coda Import*
"""

        # Write report
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)

        logger.info(f"Report written to {output_path}")
        return output_path


def main():
    """Run the import."""
    importer = CodaResearchImporter()
    themes, stats = importer.run_full_import()

    # Generate report
    report_path = importer.generate_report()
    print(f"\nReport: {report_path}")

    # Output themes as JSON for further processing
    themes_output = Path("reports") / f"coda_themes_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(themes_output, "w") as f:
        json.dump(themes, f, indent=2, default=str)
    print(f"Themes JSON: {themes_output}")

    return themes, stats


if __name__ == "__main__":
    main()
