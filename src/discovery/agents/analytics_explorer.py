"""Analytics Explorer agent for the Discovery Engine (Issue #216).

Reads pre-fetched PostHog analytics data and reasons openly about patterns —
NOT through predefined categories, NOT using the existing theme vocabulary.
The artifact contracts validate output structure, not the agent's cognitive process.

Structural batching strategy:
  - Group PostHogDataPoints by data_type (events, dashboards, insights, errors)
  - One LLM batch per data_type group (not by count)
  - Synthesis pass merges findings across data_type groups

Key design: PostHogReader does loss-minimizing compression (format, don't filter).
The LLM decides what's interesting.
"""

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.discovery.agents.base import ExplorerResult
from src.discovery.agents.posthog_data_access import PostHogDataPoint, PostHogReader
from src.discovery.agents.prompts import (
    ANALYTICS_BATCH_ANALYSIS_SYSTEM,
    ANALYTICS_BATCH_ANALYSIS_USER,
    ANALYTICS_REQUERY_SYSTEM,
    ANALYTICS_REQUERY_USER,
    ANALYTICS_SYNTHESIS_SYSTEM,
    ANALYTICS_SYNTHESIS_USER,
)
from src.discovery.models.enums import ConfidenceLevel, SourceType

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsExplorerConfig:
    """Configuration for the Analytics Explorer."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_chars_per_data_point: int = 1000
    max_chars_per_batch: int = 50000


class AnalyticsExplorer:
    """Explorer agent that discovers patterns in PostHog analytics data.

    Uses a structural batching strategy: one LLM batch per data_type group,
    followed by a synthesis pass across all groups.
    """

    def __init__(
        self,
        reader: PostHogReader,
        openai_client=None,
        config: Optional[AnalyticsExplorerConfig] = None,
    ):
        self.reader = reader
        self.config = config or AnalyticsExplorerConfig()

        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def explore(self) -> ExplorerResult:
        """Run the full exploration: fetch → group by type → batch analyze → synthesize.

        Per-batch errors are caught and recorded (batch skipped, data points
        counted as skipped), so one LLM failure doesn't abort the whole run.

        Returns an ExplorerResult with findings and coverage metadata.
        """
        data_points = self.reader.fetch_overview()
        total_available = self.reader.get_data_point_count()

        if not data_points:
            logger.info("No analytics data found for exploration")
            return ExplorerResult(
                coverage={
                    "time_window_days": 1,
                    "conversations_available": total_available,
                    "conversations_reviewed": 0,
                    "conversations_skipped": total_available,
                    "model": self.config.model,
                    "findings_count": 0,
                    "items_type": "analytics_data_points",
                },
            )

        # Group by data_type for structural batching
        groups = self._group_by_type(data_points)

        all_batch_findings: List[List[Dict[str, Any]]] = []
        reviewed_count = 0
        skipped_count = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        batch_errors = []

        for data_type, group_points in groups.items():
            try:
                findings, usage = self._analyze_batch(group_points, data_type)
                all_batch_findings.append(findings)
                reviewed_count += len(group_points)
                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)
            except Exception as e:
                logger.warning(
                    "Batch %s failed (%d data points skipped): %s",
                    data_type, len(group_points), e,
                )
                skipped_count += len(group_points)
                batch_errors.append(f"Batch {data_type}: {e}")

        # Synthesis pass
        if all_batch_findings:
            try:
                synthesized, synth_usage = self._synthesize(
                    all_batch_findings, reviewed_count
                )
                for key in total_usage:
                    total_usage[key] += synth_usage.get(key, 0)
            except Exception as e:
                logger.warning("Synthesis failed, using raw batch findings: %s", e)
                batch_errors.append(f"Synthesis: {e}")
                synthesized = [f for batch in all_batch_findings for f in batch]
        else:
            synthesized = []

        # Account for data points not fetched (available > fetched)
        not_fetched = max(0, total_available - len(data_points))

        return ExplorerResult(
            findings=synthesized,
            coverage={
                "time_window_days": 1,
                "conversations_available": total_available,
                "conversations_reviewed": reviewed_count,
                "conversations_skipped": skipped_count + not_fetched,
                "model": self.config.model,
                "findings_count": len(synthesized),
                "items_type": "analytics_data_points",
            },
            token_usage=total_usage,
            batch_errors=batch_errors,
        )

    def requery(
        self,
        request_text: str,
        previous_findings: List[Dict[str, Any]],
        source_refs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Handle an explorer:request event with a follow-up question.

        Fetches relevant data points if source_refs provided, then asks the LLM.
        """
        relevant_text = ""
        if source_refs:
            # Search for data points matching the source_refs
            all_points = self.reader.fetch_overview()
            matching = [p for p in all_points if p.source_ref in source_refs]
            if matching:
                relevant_text = "\n\n---\n\n".join(
                    p.result_summary for p in matching
                )

        user_prompt = ANALYTICS_REQUERY_USER.format(
            previous_findings_json=json.dumps(previous_findings, indent=2),
            request_text=request_text,
            relevant_data_points=relevant_text or "(no specific data points requested)",
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": ANALYTICS_REQUERY_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    def build_checkpoint_artifacts(
        self, result: ExplorerResult
    ) -> Dict[str, Any]:
        """Convert ExplorerResult into a dict validated against ExplorerCheckpoint.

        Transforms raw LLM findings into typed EvidencePointer + ExplorerFinding
        structures. Evidence pointers reference PostHog source_refs mapped to
        EvidencePointer(source_type=POSTHOG, source_id=ref).
        """
        now = datetime.now(timezone.utc).isoformat()
        findings = []

        for raw_finding in result.findings:
            evidence = []
            for ref in raw_finding.get("evidence_refs", []):
                evidence.append({
                    "source_type": SourceType.POSTHOG.value,
                    "source_id": ref,
                    "retrieved_at": now,
                    "confidence": ConfidenceLevel.from_raw(
                        raw_finding.get("confidence", "medium")
                    ),
                })

            findings.append({
                "pattern_name": raw_finding.get("pattern_name", "unnamed"),
                "description": raw_finding.get("description", ""),
                "evidence": evidence,
                "confidence": ConfidenceLevel.from_raw(
                    raw_finding.get("confidence", "medium")
                ),
                "severity_assessment": raw_finding.get(
                    "severity_assessment", "unknown"
                ),
                "affected_users_estimate": raw_finding.get(
                    "affected_users_estimate", "unknown"
                ),
            })

        return {
            "schema_version": 1,
            "agent_name": "analytics",
            "findings": findings,
            "coverage": result.coverage,
        }

    # ========================================================================
    # Internal methods
    # ========================================================================

    @staticmethod
    def _group_by_type(
        data_points: List[PostHogDataPoint],
    ) -> Dict[str, List[PostHogDataPoint]]:
        """Group data points by data_type for structural batching."""
        groups: Dict[str, List[PostHogDataPoint]] = defaultdict(list)
        for point in data_points:
            groups[point.data_type].append(point)
        return dict(groups)

    def _analyze_batch(
        self,
        data_points: List[PostHogDataPoint],
        data_type: str,
    ) -> tuple:
        """Send one data_type group to LLM, parse JSON response.

        Applies max_chars_per_batch safety valve: if the formatted text
        exceeds the budget, truncate the longest result_summary fields.

        Returns (findings_list, usage_dict).
        """
        # Format data points, respecting per-point truncation
        formatted_points = []
        for point in data_points:
            summary = point.result_summary
            if len(summary) > self.config.max_chars_per_data_point:
                summary = (
                    summary[:self.config.max_chars_per_data_point]
                    + " [... truncated]"
                )
            formatted_points.append(summary)

        formatted = "\n\n---\n\n".join(formatted_points)

        # Safety valve: truncate if total exceeds batch budget
        if len(formatted) > self.config.max_chars_per_batch:
            formatted = (
                formatted[:self.config.max_chars_per_batch]
                + "\n\n[... batch truncated due to size ...]"
            )

        user_prompt = ANALYTICS_BATCH_ANALYSIS_USER.format(
            data_type=data_type,
            formatted_data_points=formatted,
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": ANALYTICS_BATCH_ANALYSIS_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
        )

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        raw = json.loads(response.choices[0].message.content)

        # JSON schema pre-check: must have a findings list
        if not isinstance(raw.get("findings"), list):
            raise ValueError(
                f"Batch {data_type}: LLM response missing 'findings' list"
            )

        return raw["findings"], usage

    def _synthesize(
        self,
        all_batch_findings: List[List[Dict[str, Any]]],
        total_reviewed: int,
    ) -> tuple:
        """Merge findings across data_type groups via LLM.

        Returns (synthesized_findings, usage_dict).
        """
        batch_data = []
        for idx, findings in enumerate(all_batch_findings):
            batch_data.append({
                "batch_index": idx,
                "findings": findings,
            })

        user_prompt = ANALYTICS_SYNTHESIS_USER.format(
            num_batches=len(all_batch_findings),
            total_data_points=total_reviewed,
            batch_findings_json=json.dumps(batch_data, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": ANALYTICS_SYNTHESIS_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
        )

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        raw = json.loads(response.choices[0].message.content)

        if not isinstance(raw.get("findings"), list):
            raise ValueError("Synthesis response missing 'findings' list")

        return raw["findings"], usage
