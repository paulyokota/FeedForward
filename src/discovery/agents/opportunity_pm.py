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
    OPPORTUNITY_REQUERY_SYSTEM,
    OPPORTUNITY_REQUERY_USER,
)
from src.discovery.models.enums import ConfidenceLevel, SourceType

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)


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

    def build_checkpoint_artifacts(
        self,
        result: FramingResult,
        valid_evidence_ids: Optional[set] = None,
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
                evidence.append({
                    "source_type": SourceType.INTERCOM.value,
                    "source_id": conv_id,
                    "retrieved_at": now,
                    "confidence": ConfidenceLevel.from_raw(
                        raw_opp.get("confidence", "medium")
                    ),
                })

            briefs.append({
                "schema_version": 1,
                "problem_statement": coerce_str(raw_opp.get("problem_statement"), fallback=""),
                "evidence": evidence,
                "counterfactual": coerce_str(raw_opp.get("counterfactual"), fallback=""),
                "affected_area": coerce_str(raw_opp.get("affected_area"), fallback=""),
                "explorer_coverage": result.coverage_summary,
                "source_findings": raw_opp.get("source_findings", []),
            })

        return {
            "schema_version": 1,
            "briefs": briefs,
            "framing_metadata": {
                "explorer_findings_count": result.explorer_findings_count,
                "opportunities_identified": len(briefs),
                "model": self.config.model,
            },
            "framing_notes": result.framing_notes,
        }


def extract_evidence_ids(explorer_checkpoint: Dict[str, Any]) -> set:
    """Extract all conversation IDs referenced in explorer findings.

    Returns a set of conversation IDs that can be used as valid_evidence_ids
    when building checkpoint artifacts.
    """
    ids = set()
    for finding in explorer_checkpoint.get("findings", []):
        for ev in finding.get("evidence", []):
            source_id = ev.get("source_id", "")
            if source_id:
                ids.add(source_id)
        for conv_id in finding.get("evidence_conversation_ids", []):
            ids.add(conv_id)
    return ids


