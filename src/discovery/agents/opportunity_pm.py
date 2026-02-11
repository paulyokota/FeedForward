"""Opportunity PM agent for the Discovery Engine (Issue #219).

Reads Stage 0 explorer findings and synthesizes them into OpportunityBriefs —
problem-focused artifacts with evidence pointers and counterfactual framing.

Single-pass LLM strategy: explorer findings are already structured JSON
(typically 3-10 findings), so batch processing isn't needed. One LLM call
receives all findings and produces multiple distinct OpportunityBriefs.

Critical constraint: NO solution direction. The Opportunity Brief describes
what's broken and who it affects. Solutions emerge in Stage 2.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.discovery.agents.base import coerce_str
from src.discovery.agents.prompts import (
    OPPORTUNITY_FRAMING_SYSTEM,
    OPPORTUNITY_FRAMING_USER,
    OPPORTUNITY_REFRAME_SYSTEM,
    OPPORTUNITY_REFRAME_USER,
    OPPORTUNITY_REQUERY_SYSTEM,
    OPPORTUNITY_REQUERY_USER,
)
from src.discovery.models.artifacts import InputRejection
from src.discovery.models.enums import ConfidenceLevel, SourceType

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)

# Known stage hints for adaptive routing (Issue #261).
# Unknown hints from LLM output are filtered out with a warning.
KNOWN_STAGE_HINTS = {"skip_experience", "internal_risk_framing"}


@dataclass
class OpportunityPMConfig:
    """Configuration for the Opportunity PM agent."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.5  # Lower than explorer for more structured output


@dataclass
class FramingResult:
    """Result of an opportunity framing run, before checkpoint formatting."""

    opportunities: List[Dict[str, Any]] = field(default_factory=list)
    framing_notes: str = ""
    explorer_findings_count: int = 0
    coverage_summary: str = ""
    token_usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })


class OpportunityPM:
    """Agent that synthesizes explorer findings into OpportunityBriefs.

    Pure transform: takes explorer checkpoint data, produces opportunity briefs.
    Does NOT interact with ConversationService directly — the orchestration
    layer handles reading checkpoints and submitting results.
    """

    def __init__(
        self,
        openai_client=None,
        config: Optional[OpportunityPMConfig] = None,
    ):
        self.config = config or OpportunityPMConfig()

        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def frame_opportunities(
        self,
        explorer_checkpoint: Dict[str, Any],
    ) -> FramingResult:
        """Synthesize explorer findings into OpportunityBriefs.

        Takes the explorer checkpoint artifact (ExplorerCheckpoint schema)
        and produces distinct opportunity briefs via a single LLM call.

        Returns a FramingResult with opportunities and metadata.
        """
        findings = explorer_checkpoint.get("findings", [])
        coverage = explorer_checkpoint.get("coverage", {})

        coverage_summary = (
            f"{coverage.get('conversations_reviewed', '?')} conversations reviewed "
            f"over {coverage.get('time_window_days', '?')} days "
            f"({coverage.get('conversations_available', '?')} available, "
            f"{coverage.get('conversations_skipped', '?')} skipped)"
        )

        if not findings:
            logger.info("No explorer findings to frame — returning empty result")
            return FramingResult(
                explorer_findings_count=0,
                coverage_summary=coverage_summary,
            )

        user_prompt = OPPORTUNITY_FRAMING_USER.format(
            num_findings=len(findings),
            explorer_findings_json=json.dumps(findings, indent=2),
            coverage_summary=coverage_summary,
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": OPPORTUNITY_FRAMING_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
        )

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        raw = json.loads(response.choices[0].message.content)

        if not isinstance(raw.get("opportunities"), list):
            raise ValueError("LLM response missing 'opportunities' list")

        return FramingResult(
            opportunities=raw["opportunities"],
            framing_notes=raw.get("framing_notes", ""),
            explorer_findings_count=len(findings),
            coverage_summary=coverage_summary,
            token_usage=usage,
        )

    def requery_explorer(
        self,
        request_text: str,
        current_briefs: List[Dict[str, Any]],
        explorer_findings: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Handle a follow-up query to explorer agents.

        This is a pure LLM function — the orchestration layer handles
        posting explorer:request events and reading explorer:response events.
        """
        user_prompt = OPPORTUNITY_REQUERY_USER.format(
            current_briefs_json=json.dumps(current_briefs, indent=2),
            explorer_findings_json=json.dumps(explorer_findings, indent=2),
            request_text=request_text,
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": OPPORTUNITY_REQUERY_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    def reframe_rejected(
        self,
        rejected_briefs: List[Dict[str, Any]],
        rejections: List[InputRejection],
        explorer_checkpoint: Dict[str, Any],
    ) -> FramingResult:
        """Revise rejected OpportunityBriefs using rejection feedback.

        Each rejected brief is paired with its InputRejection by index.
        Makes one LLM call per rejected brief using OPPORTUNITY_REFRAME prompts.

        Args:
            rejected_briefs: Original OpportunityBrief dicts that were rejected.
            rejections: Corresponding InputRejection objects (same order/length).
            explorer_checkpoint: Explorer checkpoint for additional evidence context.

        Returns:
            FramingResult with revised opportunities and aggregated token usage.
        """
        if len(rejected_briefs) != len(rejections):
            raise ValueError(
                f"rejected_briefs ({len(rejected_briefs)}) and rejections "
                f"({len(rejections)}) must have the same length"
            )

        if not rejected_briefs:
            return FramingResult()

        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        revised_opportunities: List[Dict[str, Any]] = []
        findings_json = json.dumps(
            explorer_checkpoint.get("findings", []), indent=2
        )

        for i, (brief, rejection) in enumerate(zip(rejected_briefs, rejections)):
            rejection_dict = {
                "item_id": rejection.item_id,
                "rejection_reason": rejection.rejection_reason,
                "suggested_improvement": rejection.suggested_improvement,
            }

            user_prompt = OPPORTUNITY_REFRAME_USER.format(
                original_brief_json=json.dumps(brief, indent=2),
                rejection_json=json.dumps(rejection_dict, indent=2),
                explorer_findings_json=findings_json,
            )

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": OPPORTUNITY_REFRAME_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.temperature,
                response_format={"type": "json_object"},
            )

            if response.usage:
                total_usage["prompt_tokens"] += response.usage.prompt_tokens
                total_usage["completion_tokens"] += response.usage.completion_tokens
                total_usage["total_tokens"] += response.usage.total_tokens

            try:
                revised = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError:
                wasted = response.usage.total_tokens if response.usage else 0
                logger.warning(
                    "reframe_rejected: JSON decode failed for item %d "
                    "(item_id=%s, wasted_tokens=%d) — skipping",
                    i,
                    rejection.item_id,
                    wasted,
                )
                continue

            revised_opportunities.append(revised)

        return FramingResult(
            opportunities=revised_opportunities,
            token_usage=total_usage,
        )

    def build_checkpoint_artifacts(
        self,
        result: FramingResult,
        valid_evidence_ids: Optional[set] = None,
        evidence_source_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Convert FramingResult into OpportunityFramingCheckpoint schema.

        Transforms raw LLM opportunities into typed OpportunityBrief structures
        with EvidencePointers. Evidence IDs are validated against the set of
        known IDs from explorer findings — unknown IDs are filtered out and
        logged as warnings.

        Args:
            result: The FramingResult from frame_opportunities()
            valid_evidence_ids: Set of conversation IDs known to exist in
                explorer findings. If provided, any LLM-generated ID not in
                this set is filtered out. If None, all IDs are accepted
                (for backward compatibility / testing).
        """
        now = datetime.now(timezone.utc).isoformat()
        briefs = []

        for raw_opp in result.opportunities:
            evidence = []
            for conv_id in raw_opp.get("evidence_conversation_ids", []):
                if valid_evidence_ids is not None and conv_id not in valid_evidence_ids:
                    logger.warning(
                        "Filtering unknown evidence ID '%s' from opportunity '%s' "
                        "(not found in explorer findings)",
                        conv_id,
                        raw_opp.get("problem_statement", "?")[:50],
                    )
                    continue
                source_type = None
                if evidence_source_map is not None:
                    source_type = evidence_source_map.get(conv_id)
                    if source_type is None:
                        logger.warning(
                            "Unknown source_type for evidence ID '%s' in opportunity '%s' "
                            "(defaulting to SourceType.OTHER)",
                            conv_id,
                            raw_opp.get("problem_statement", "?")[:50],
                        )
                if not source_type:
                    source_type = SourceType.OTHER.value
                evidence.append({
                    "source_type": source_type,
                    "source_id": conv_id,
                    "retrieved_at": now,
                    "confidence": ConfidenceLevel.from_raw(
                        raw_opp.get("confidence", "medium")
                    ),
                })

            # Validate and filter stage_hints (Issue #261)
            raw_hints = raw_opp.get("stage_hints") or []
            if not isinstance(raw_hints, list):
                raw_hints = []
            validated_hints = []
            for hint in raw_hints:
                if not isinstance(hint, str):
                    continue
                if hint in KNOWN_STAGE_HINTS:
                    validated_hints.append(hint)
                else:
                    logger.warning(
                        "Filtering unknown stage_hint '%s' from opportunity '%s'",
                        hint,
                        raw_opp.get("problem_statement", "?")[:50],
                    )

            brief = {
                "schema_version": 1,
                "problem_statement": coerce_str(raw_opp.get("problem_statement"), fallback=""),
                "evidence": evidence,
                "counterfactual": coerce_str(raw_opp.get("counterfactual"), fallback=""),
                "affected_area": coerce_str(raw_opp.get("affected_area"), fallback=""),
                "explorer_coverage": result.coverage_summary,
                "source_findings": raw_opp.get("source_findings", []),
            }

            # Adaptive routing fields (Issue #261)
            nature = raw_opp.get("opportunity_nature")
            if nature is not None:
                brief["opportunity_nature"] = coerce_str(nature)
            response = raw_opp.get("recommended_response")
            if response is not None:
                brief["recommended_response"] = coerce_str(response)
            if validated_hints:
                brief["stage_hints"] = validated_hints

            briefs.append(brief)

        quality_flags = {
            "briefs_produced": len(briefs),
            "validation_rejections": 0,
            "validation_retries": 0,
        }

        checkpoint: Dict[str, Any] = {
            "schema_version": 1,
            "briefs": briefs,
            "framing_metadata": {
                "explorer_findings_count": result.explorer_findings_count,
                "opportunities_identified": len(briefs),
                "model": self.config.model,
                "quality_flags": quality_flags,
            },
            "framing_notes": result.framing_notes,
        }

        return checkpoint


def extract_evidence_source_map(explorer_checkpoint: Dict[str, Any]) -> Dict[str, str]:
    """Extract evidence source types keyed by source_id from explorer findings."""
    source_map: Dict[str, str] = {}
    for finding in explorer_checkpoint.get("findings", []):
        for ev in finding.get("evidence", []):
            source_id = ev.get("source_id") or ev.get("id")
            source_type = ev.get("source_type")
            if source_id and source_type and source_id not in source_map:
                source_map[source_id] = source_type
        for conv_id in finding.get("evidence_conversation_ids", []):
            if conv_id and conv_id not in source_map:
                source_map[conv_id] = SourceType.OTHER.value
    return source_map


def extract_evidence_ids(explorer_checkpoint: Dict[str, Any]) -> set:
    """Extract all conversation IDs referenced in explorer findings."""
    ids = set()
    for finding in explorer_checkpoint.get("findings", []):
        for ev in finding.get("evidence", []):
            source_id = ev.get("source_id") or ev.get("id")
            if source_id:
                ids.add(source_id)
        for conv_id in finding.get("evidence_conversation_ids", []):
            if conv_id:
                ids.add(conv_id)
    return ids

