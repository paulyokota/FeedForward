"""PostHog data access layer for the Analytics Explorer (Issue #216).

Pure data transformer: accepts pre-fetched raw Python dicts from PostHog MCP
tool calls (done at the agent/orchestrator layer) and formats them into
LLM-readable PostHogDataPoints.

Design principle: loss-minimizing compression — format, don't filter.
Every item gets a record. Nothing is dropped. The LLM decides what's interesting.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum characters for any single text field before truncation
DEFAULT_FIELD_TRUNCATION = 300


@dataclass
class PostHogDataPoint:
    """A single formatted data point from PostHog.

    Each data_type (event_definition, dashboard, insight, error) gets its
    own formatting, but they all produce this same shape.
    """

    data_type: str  # "event_definition" | "dashboard" | "insight" | "error"
    name: str  # human-readable name
    result_summary: str  # LLM-readable formatted text
    raw_data: Dict[str, Any] = field(default_factory=dict)  # original dict
    source_ref: str = ""  # e.g., "dashboard_1160029", "event_Added_draft"


class PostHogReader:
    """Formats raw PostHog API payloads into LLM-readable data points.

    Constructor accepts raw Python dicts (the JSON payloads from PostHog MCP
    tools). The reader does NOT make MCP calls — that happens at the
    agent/orchestrator layer.

    fetch_overview() returns a flat list of PostHogDataPoints, sorted by
    data_type then name for deterministic ordering.
    """

    def __init__(
        self,
        event_definitions: Optional[List[Dict[str, Any]]] = None,
        dashboards: Optional[List[Dict[str, Any]]] = None,
        insights: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
    ):
        self._event_definitions = event_definitions or []
        self._dashboards = dashboards or []
        self._insights = insights or []
        self._errors = errors or []

    def fetch_overview(self) -> List[PostHogDataPoint]:
        """Format ALL raw data into a flat list of PostHogDataPoints.

        Sorted by data_type then name for deterministic LLM input.
        Every item gets a record — nothing dropped.
        """
        points: List[PostHogDataPoint] = []
        points.extend(self._format_event_definitions())
        points.extend(self._format_dashboards())
        points.extend(self._format_insights())
        points.extend(self._format_errors())

        # Deterministic ordering: sort by data_type then name
        points.sort(key=lambda p: (p.data_type, p.name.lower()))
        return points

    def fetch_specific(self, query: str) -> List[PostHogDataPoint]:
        """Case-insensitive substring search across name and result_summary.

        For requery: find data points matching a specific query.
        Does NOT search raw_data.
        """
        all_points = self.fetch_overview()
        query_lower = query.lower()
        return [
            p for p in all_points
            if query_lower in p.name.lower()
            or query_lower in p.result_summary.lower()
        ]

    def get_data_point_count(self) -> int:
        """Total number of raw items across all data types."""
        return (
            len(self._event_definitions)
            + len(self._dashboards)
            + len(self._insights)
            + len(self._errors)
        )

    # ========================================================================
    # Private formatters — one per data type
    # ========================================================================

    def _format_event_definitions(self) -> List[PostHogDataPoint]:
        """Format event definitions: name, type, last_seen, volume."""
        points = []
        for evt in self._event_definitions:
            name = evt.get("name", "unknown_event")
            last_seen = evt.get("last_seen_at", "never")
            volume = evt.get("volume_30_day", evt.get("volume", "?"))
            event_type = evt.get("event_type", "custom")

            summary = (
                f"Event: {name}\n"
                f"  Type: {event_type}\n"
                f"  Last seen: {last_seen}\n"
                f"  Volume (30d): {volume}"
            )

            # Sanitize name for source_ref
            safe_name = name.replace(" ", "_").replace("/", "_")[:50]
            points.append(PostHogDataPoint(
                data_type="event_definition",
                name=name,
                result_summary=summary,
                raw_data=evt,
                source_ref=f"event_{safe_name}",
            ))
        return points

    def _format_dashboards(self) -> List[PostHogDataPoint]:
        """Format dashboards: name, id, description, tags."""
        points = []
        for dash in self._dashboards:
            name = dash.get("name", "Untitled Dashboard")
            dash_id = dash.get("id", "?")
            description = dash.get("description", "") or ""
            tags = dash.get("tags", []) or []

            # Truncate description
            if len(description) > DEFAULT_FIELD_TRUNCATION:
                description = description[:DEFAULT_FIELD_TRUNCATION] + " [... truncated]"

            tags_str = ", ".join(str(t) for t in tags) if tags else "none"

            summary = (
                f"Dashboard: {name} (id={dash_id})\n"
                f"  Tags: {tags_str}\n"
                f"  Description: {description or '(none)'}"
            )

            points.append(PostHogDataPoint(
                data_type="dashboard",
                name=name,
                result_summary=summary,
                raw_data=dash,
                source_ref=f"dashboard_{dash_id}",
            ))
        return points

    def _format_insights(self) -> List[PostHogDataPoint]:
        """Format insights: name, id, query type, filters summary, description."""
        points = []
        for ins in self._insights:
            name = ins.get("name", "Untitled Insight")
            ins_id = ins.get("id", ins.get("short_id", "?"))
            description = ins.get("description", "") or ""
            query_kind = self._extract_query_kind(ins)

            # Truncate description
            if len(description) > DEFAULT_FIELD_TRUNCATION:
                description = description[:DEFAULT_FIELD_TRUNCATION] + " [... truncated]"

            filters_summary = self._summarize_insight_filters(ins)

            summary = (
                f"Insight: {name} (id={ins_id})\n"
                f"  Query type: {query_kind}\n"
                f"  Filters: {filters_summary}\n"
                f"  Description: {description or '(none)'}"
            )

            points.append(PostHogDataPoint(
                data_type="insight",
                name=name,
                result_summary=summary,
                raw_data=ins,
                source_ref=f"insight_{ins_id}",
            ))
        return points

    def _format_errors(self) -> List[PostHogDataPoint]:
        """Format errors: type, message, occurrences, sessions, users, status."""
        points = []
        for err in self._errors:
            err_type = err.get("type", "UnknownError")
            message = err.get("value", err.get("message", ""))
            occurrences = err.get("occurrences", "?")
            sessions = err.get("sessions", "?")
            users = err.get("users", "?")
            status = err.get("status", "unresolved")
            fingerprint = err.get("fingerprint", [])
            err_id = err.get("id", "?")

            # Truncate message
            if isinstance(message, str) and len(message) > DEFAULT_FIELD_TRUNCATION:
                message = message[:DEFAULT_FIELD_TRUNCATION] + " [... truncated]"

            fp_str = " > ".join(str(f) for f in fingerprint) if fingerprint else "none"

            summary = (
                f"Error: {err_type}\n"
                f"  Message: {message}\n"
                f"  Occurrences: {occurrences}, Sessions: {sessions}, Users: {users}\n"
                f"  Status: {status}\n"
                f"  Fingerprint: {fp_str}"
            )

            points.append(PostHogDataPoint(
                data_type="error",
                name=f"{err_type}: {str(message)[:60]}",
                result_summary=summary,
                raw_data=err,
                source_ref=f"error_{err_id}",
            ))
        return points

    # ========================================================================
    # Helpers
    # ========================================================================

    @staticmethod
    def _extract_query_kind(insight: Dict[str, Any]) -> str:
        """Extract the query type from an insight's nested structure."""
        # Try query.kind first (newer PostHog format)
        query = insight.get("query", {})
        if isinstance(query, dict):
            kind = query.get("kind", "")
            if kind:
                return kind

        # Fall back to filters.insight (older format)
        filters = insight.get("filters", {})
        if isinstance(filters, dict):
            return filters.get("insight", "unknown")

        return "unknown"

    @staticmethod
    def _summarize_insight_filters(insight: Dict[str, Any]) -> str:
        """Summarize insight filters into a compact LLM-readable string."""
        parts = []

        # Try query-based format first
        query = insight.get("query", {})
        if isinstance(query, dict):
            # Events/actions
            series = query.get("series", [])
            if series and isinstance(series, list):
                event_names = []
                for s in series[:5]:  # Cap at 5 to keep it compact
                    if isinstance(s, dict):
                        event_names.append(s.get("event", s.get("name", "?")))
                if event_names:
                    parts.append(f"events=[{', '.join(event_names)}]")
                if len(series) > 5:
                    parts.append(f"(+{len(series) - 5} more)")

            # Breakdowns
            breakdown = query.get("breakdownFilter", {})
            if isinstance(breakdown, dict):
                breakdowns = breakdown.get("breakdowns", [])
                if breakdowns:
                    bp = [b.get("property", "?") for b in breakdowns if isinstance(b, dict)]
                    if bp:
                        parts.append(f"breakdown=[{', '.join(bp)}]")

            # Date range
            date_range = query.get("dateRange", {})
            if isinstance(date_range, dict):
                date_from = date_range.get("date_from", "")
                if date_from:
                    parts.append(f"from={date_from}")

        # Fall back to filters-based format
        if not parts:
            filters = insight.get("filters", {})
            if isinstance(filters, dict):
                events = filters.get("events", [])
                if events:
                    event_names = [e.get("id", "?") for e in events[:5] if isinstance(e, dict)]
                    if event_names:
                        parts.append(f"events=[{', '.join(event_names)}]")

        return ", ".join(parts) if parts else "(no filters)"
