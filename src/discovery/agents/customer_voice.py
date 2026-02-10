"""Customer Voice Explorer agent for the Discovery Engine.

Reads raw customer conversations and reasons openly about patterns —
NOT through predefined categories, NOT using the existing theme vocabulary.
The artifact contracts validate output structure, not the agent's cognitive process.

Two-pass LLM strategy:
  1. Per-batch analysis: open-ended pattern recognition (~20 conversations per batch)
  2. Synthesis pass: dedup and cross-reference findings across batches

Per Issue #215: This is the primary capability thesis test. If this agent can't
surface patterns the existing structured pipeline misses, the discovery engine
concept doesn't hold.
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.discovery.agents.base import ExplorerResult, coerce_str
from src.discovery.agents.data_access import ConversationReader, RawConversation
from src.discovery.agents.prompts import (
    BATCH_ANALYSIS_SYSTEM,
    BATCH_ANALYSIS_USER,
    REQUERY_SYSTEM,
    REQUERY_USER,
    SYNTHESIS_SYSTEM,
    SYNTHESIS_USER,
)
from src.discovery.models.enums import ConfidenceLevel, SourceType

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)


@dataclass
class ExplorerConfig:
    """Configuration for the Customer Voice Explorer."""

    time_window_days: int = 14
    max_conversations: int = 200
    batch_size: int = 20
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_chars_per_conversation: int = 2000


class CustomerVoiceExplorer:
    """Explorer agent that discovers patterns in raw customer conversations.

    Uses a two-pass LLM strategy: per-batch analysis followed by synthesis.
    """

    def __init__(
        self,
        reader: ConversationReader,
        openai_client=None,
        config: Optional[ExplorerConfig] = None,
    ):
        self.reader = reader
        self.config = config or ExplorerConfig()

        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def explore(self) -> ExplorerResult:
        """Run the full exploration: fetch → batch analyze → synthesize.

        Per-batch errors are caught and recorded (batch skipped, conversations
        counted as conversations_skipped), so one LLM failure doesn't abort
        the whole run.

        Returns an ExplorerResult with findings and coverage metadata.
        """
        conversations = self.reader.fetch_conversations(
            days=self.config.time_window_days,
            limit=self.config.max_conversations,
        )

        total_available = self.reader.get_conversation_count(
            days=self.config.time_window_days,
        )

        if not conversations:
            logger.info("No conversations found for exploration")
            return ExplorerResult(
                coverage={
                    "time_window_days": self.config.time_window_days,
                    "conversations_available": total_available,
                    "conversations_reviewed": 0,
                    "conversations_skipped": total_available,
                    "model": self.config.model,
                    "findings_count": 0,
                },
            )

        # Split into batches
        batches = [
            conversations[i : i + self.config.batch_size]
            for i in range(0, len(conversations), self.config.batch_size)
        ]

        all_batch_findings: List[List[Dict[str, Any]]] = []
        reviewed_count = 0
        skipped_count = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        batch_errors = []

        for batch_idx, batch in enumerate(batches):
            try:
                findings, usage = self._analyze_batch(batch, batch_idx)
                all_batch_findings.append(findings)
                reviewed_count += len(batch)
                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)
            except Exception as e:
                logger.warning(
                    "Batch %d failed (%d conversations skipped): %s",
                    batch_idx, len(batch), e,
                )
                skipped_count += len(batch)
                batch_errors.append(f"Batch {batch_idx}: {e}")

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

        # Account for conversations not fetched (available > fetched)
        not_fetched = max(0, total_available - len(conversations))

        return ExplorerResult(
            findings=synthesized,
            coverage={
                "time_window_days": self.config.time_window_days,
                "conversations_available": total_available,
                "conversations_reviewed": reviewed_count,
                "conversations_skipped": skipped_count + not_fetched,
                "model": self.config.model,
                "findings_count": len(synthesized),
            },
            token_usage=total_usage,
            batch_errors=batch_errors,
        )

    def requery(
        self,
        request_text: str,
        previous_findings: List[Dict[str, Any]],
        conversation_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Handle an explorer:request event with a follow-up question.

        Fetches relevant conversations if IDs provided, then asks the LLM.
        """
        relevant_text = ""
        if conversation_ids:
            convos = []
            for cid in conversation_ids:
                conv = self.reader.fetch_conversation_by_id(cid)
                if conv:
                    convos.append(conv)
            if convos:
                relevant_text = "\n\n".join(
                    self._format_conversation(c) for c in convos
                )

        user_prompt = REQUERY_USER.format(
            previous_findings_json=json.dumps(previous_findings, indent=2),
            request_text=request_text,
            relevant_conversations=relevant_text or "(no specific conversations requested)",
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": REQUERY_SYSTEM},
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
        structures. Evidence pointers reference conversation_id (not text offsets),
        so truncation doesn't break references.
        """
        now = datetime.now(timezone.utc).isoformat()
        findings = []

        for raw_finding in result.findings:
            evidence = []
            for conv_id in raw_finding.get("evidence_conversation_ids", []):
                evidence.append({
                    "source_type": SourceType.INTERCOM.value,
                    "source_id": conv_id,
                    "retrieved_at": now,
                    "confidence": ConfidenceLevel.from_raw(
                        raw_finding.get("confidence", "medium")
                    ),
                })

            if not evidence:
                logger.warning(
                    "Dropping finding '%s' — no evidence_conversation_ids "
                    "(ExplorerFinding requires min 1 evidence pointer)",
                    raw_finding.get("pattern_name", "unnamed"),
                )
                continue

            findings.append({
                "pattern_name": coerce_str(raw_finding.get("pattern_name"), fallback="unnamed"),
                "description": coerce_str(raw_finding.get("description"), fallback=""),
                "evidence": evidence,
                "confidence": ConfidenceLevel.from_raw(
                    raw_finding.get("confidence", "medium")
                ),
                "severity_assessment": coerce_str(
                    raw_finding.get("severity_assessment"), fallback="unknown"
                ),
                "affected_users_estimate": coerce_str(
                    raw_finding.get("affected_users_estimate"), fallback="unknown"
                ),
            })

        return {
            "schema_version": 1,
            "agent_name": "customer_voice",
            "findings": findings,
            "coverage": result.coverage,
        }

    # ========================================================================
    # Internal methods
    # ========================================================================

    def _analyze_batch(
        self,
        batch: List[RawConversation],
        batch_idx: int,
    ) -> tuple:
        """Send one batch to LLM, parse JSON response.

        Returns (findings_list, usage_dict).
        """
        formatted = "\n\n---\n\n".join(
            self._format_conversation(c) for c in batch
        )

        user_prompt = BATCH_ANALYSIS_USER.format(
            batch_size=len(batch),
            time_window_days=self.config.time_window_days,
            formatted_conversations=formatted,
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": BATCH_ANALYSIS_SYSTEM},
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
                f"Batch {batch_idx}: LLM response missing 'findings' list"
            )

        return raw["findings"], usage

    def _synthesize(
        self,
        all_batch_findings: List[List[Dict[str, Any]]],
        total_reviewed: int,
    ) -> tuple:
        """Merge findings across batches via LLM.

        Returns (synthesized_findings, usage_dict).
        """
        # Build batch findings JSON with batch indices
        batch_data = []
        for idx, findings in enumerate(all_batch_findings):
            batch_data.append({
                "batch_index": idx,
                "findings": findings,
            })

        user_prompt = SYNTHESIS_USER.format(
            num_batches=len(all_batch_findings),
            total_conversations=total_reviewed,
            time_window_days=self.config.time_window_days,
            batch_findings_json=json.dumps(batch_data, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": SYNTHESIS_SYSTEM},
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

    def _format_conversation(self, conv: RawConversation) -> str:
        """Format a conversation for LLM input with deterministic truncation.

        MF2: Keep first customer message in full (opening complaint is almost
        always most important) + last 3 messages (resolution context).
        Metadata line is always outside the truncation boundary.
        Character budget: max_chars_per_conversation (default 2000).
        Evidence pointers reference conversation_id (not text offsets),
        so truncation doesn't break references.
        """
        budget = self.config.max_chars_per_conversation

        # Metadata line — always present, outside truncation boundary
        created_str = (
            conv.created_at.isoformat() if conv.created_at else "unknown"
        )
        meta = (
            f"[{conv.conversation_id}] created={created_str}"
            f" url={conv.source_url or 'none'}"
        )

        text = conv.full_conversation or conv.source_body or ""
        if not text.strip():
            return f"{meta}\n(no conversation text)"

        # Try to split into messages by speaker tags
        messages = _split_messages(text)

        if len(messages) <= 4:
            # Short enough — just truncate by character budget
            truncated = text[:budget]
            if len(text) > budget:
                truncated += "\n[... truncated ...]"
            return f"{meta}\n{truncated}"

        # Deterministic truncation: first message + last 3 messages
        first_msg = messages[0]
        last_three = messages[-3:]
        omitted = len(messages) - 4

        middle_marker = f"\n[... {omitted} messages omitted ...]\n"
        core = first_msg + middle_marker + "\n".join(last_three)

        if len(core) > budget:
            core = core[:budget]
            if not core.endswith("...]"):
                core += "\n[... truncated ...]"

        return f"{meta}\n{core}"


def _split_messages(text: str) -> List[str]:
    """Split conversation text into individual messages by speaker tags.

    Handles patterns like "Customer:", "Agent:", "Support:", etc.
    If no speaker tags found, treats the whole text as a single block.
    """
    # Match lines that start with a speaker tag
    pattern = re.compile(r"^(?:Customer|Agent|Support|User|Bot|Admin)\s*:", re.MULTILINE)
    splits = list(pattern.finditer(text))

    if not splits:
        return [text]

    messages = []
    for i, match in enumerate(splits):
        start = match.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        messages.append(text[start:end].strip())

    return messages


