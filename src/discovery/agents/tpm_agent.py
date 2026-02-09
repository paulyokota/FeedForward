"""TPM (Technical Program Manager) Agent for the Discovery Engine (Issue #222).

Single-agent pass that ranks all opportunities that passed Stage 3 by
weighing impact, effort, risk, dependencies, and strategic alignment.
Produces advisory rankings — the human reviewer in Stage 5 makes the final call.

Pure function: does not interact with ConversationService directly.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.discovery.agents.prompts import (
    TPM_RANKING_SYSTEM,
    TPM_RANKING_USER,
)

logger = logging.getLogger(__name__)


@dataclass
class TPMAgentConfig:
    """Configuration for the TPM Agent."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.3


class TPMAgent:
    """Agent that produces advisory priority rankings for opportunities.

    Pure transform: takes opportunity packages (brief + solution + spec),
    produces a ranked list. Does NOT interact with ConversationService.
    """

    def __init__(
        self,
        openai_client=None,
        config: Optional[TPMAgentConfig] = None,
    ):
        self.config = config or TPMAgentConfig()
        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI

            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def rank_opportunities(
        self,
        opportunity_packages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Rank opportunities by priority.

        Args:
            opportunity_packages: List of dicts, each containing:
                - opportunity_id: str (from technical_spec["opportunity_id"])
                - opportunity_brief: dict from Stage 1
                - solution_brief: dict from Stage 2
                - technical_spec: dict from Stage 3 (feasible only)

        Returns:
            Dict with keys: rankings (normalized), token_usage.

        Raises:
            ValueError: If any package is missing opportunity_id, or if LLM
                response is missing required 'rankings' key.
            json.JSONDecodeError: If LLM returns non-JSON.
        """
        # Validate all packages have opportunity_id
        expected_ids = []
        for i, pkg in enumerate(opportunity_packages):
            oid = pkg.get("opportunity_id")
            if not oid:
                raise ValueError(
                    f"Opportunity package at index {i} is missing 'opportunity_id'"
                )
            expected_ids.append(oid)

        # Empty input — no LLM call needed
        if not opportunity_packages:
            return {
                "rankings": [],
                "token_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }

        user_prompt = TPM_RANKING_USER.format(
            opportunity_packages_json=json.dumps(opportunity_packages, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": TPM_RANKING_SYSTEM},
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

        if "rankings" not in raw:
            raise ValueError(
                "TPM Agent response missing required 'rankings' key"
            )

        normalized = self._normalize_rankings(raw["rankings"], expected_ids)

        return {
            "rankings": normalized,
            "token_usage": usage,
        }

    def build_checkpoint_artifacts(
        self,
        rankings: List[Dict[str, Any]],
        token_usage: Dict[str, int],
    ) -> Dict[str, Any]:
        """Wrap rankings into PrioritizationCheckpoint shape.

        Args:
            rankings: Normalized ranking dicts from rank_opportunities().
            token_usage: Accumulated token counts.

        Returns:
            Dict matching PrioritizationCheckpoint schema.
        """
        return {
            "schema_version": 1,
            "rankings": rankings,
            "prioritization_metadata": {
                "opportunities_ranked": len(rankings),
                "model": self.config.model,
            },
        }

    def _normalize_rankings(
        self,
        raw_rankings: List[Dict[str, Any]],
        expected_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """Normalize LLM rankings into a valid total ordering.

        1. Deduplicate: keep first occurrence of each opportunity_id
        2. Fill missing: append any expected IDs not in LLM output
        3. Re-rank: assign recommended_rank = 1..N by position

        Args:
            raw_rankings: Rankings from LLM (may have gaps, dupes, missing).
            expected_ids: All opportunity_ids from input packages.

        Returns:
            Normalized list with exactly one entry per expected_id,
            sequential recommended_rank values.
        """
        seen = set()
        deduped = []
        for entry in raw_rankings:
            oid = entry.get("opportunity_id", "")
            if oid and oid not in seen:
                seen.add(oid)
                deduped.append(entry)

        # Fill any missing IDs
        for oid in expected_ids:
            if oid not in seen:
                logger.warning(
                    "Opportunity '%s' missing from LLM rankings — appending with fallback",
                    oid,
                )
                deduped.append({
                    "opportunity_id": oid,
                    "rationale": "Not ranked by agent",
                    "dependencies": [],
                    "flags": ["Auto-appended \u2014 missing from LLM output"],
                })

        # Ensure every entry has a non-empty rationale (PrioritizedOpportunity requires min_length=1)
        for entry in deduped:
            if not entry.get("rationale"):
                entry["rationale"] = "No rationale provided by agent"

        # Re-rank sequentially
        for i, entry in enumerate(deduped, start=1):
            entry["recommended_rank"] = i

        return deduped
