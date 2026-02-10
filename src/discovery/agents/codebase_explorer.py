"""Codebase Explorer agent for the Discovery Engine.

Reads recently-changed source files via git and reasons openly about patterns —
NOT through predefined categories, NOT using the existing theme vocabulary.
The artifact contracts validate output structure, not the agent's cognitive process.

Two-pass LLM strategy:
  1. Per-batch analysis: open-ended pattern recognition (~10 files per batch)
  2. Synthesis pass: dedup and cross-reference findings across batches

Per Issue #217: Second Stage 0 explorer. Discovers tech debt, architecture
opportunities, and recurring code patterns that the structured pipeline
can't see (because it only looks at customer conversations).
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from src.discovery.agents.base import ExplorerResult, coerce_str
from src.discovery.agents.codebase_data_access import CodebaseItem, CodebaseReader
from src.discovery.agents.prompts import (
    CODEBASE_BATCH_ANALYSIS_SYSTEM,
    CODEBASE_BATCH_ANALYSIS_USER,
    CODEBASE_REQUERY_SYSTEM,
    CODEBASE_REQUERY_USER,
    CODEBASE_SYNTHESIS_SYSTEM,
    CODEBASE_SYNTHESIS_USER,
)
from src.discovery.models.enums import ConfidenceLevel, SourceType

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)


@dataclass
class CodebaseExplorerConfig:
    """Configuration for the Codebase Explorer."""

    time_window_days: int = 30
    max_files: int = 100
    batch_size: int = 10
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_chars_per_file: int = 3000


class CodebaseExplorer:
    """Explorer agent that discovers patterns in recently-changed source code.

    Uses a two-pass LLM strategy: per-batch analysis followed by synthesis.
    """

    def __init__(
        self,
        reader: CodebaseReader,
        openai_client=None,
        config: Optional[CodebaseExplorerConfig] = None,
    ):
        self.reader = reader
        self.config = config or CodebaseExplorerConfig()

        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def explore(self) -> ExplorerResult:
        """Run the full exploration: fetch → batch analyze → synthesize.

        Per-batch errors are caught and recorded (batch skipped, files
        counted as skipped), so one LLM failure doesn't abort the whole run.

        Returns an ExplorerResult with findings and coverage metadata.
        """
        files = self.reader.fetch_recently_changed(
            days=self.config.time_window_days,
            limit=self.config.max_files,
        )

        total_available = self.reader.get_item_count(
            days=self.config.time_window_days,
        )

        if not files:
            logger.info("No source files found for exploration")
            return ExplorerResult(
                coverage={
                    "time_window_days": self.config.time_window_days,
                    "conversations_available": total_available,
                    "conversations_reviewed": 0,
                    "conversations_skipped": total_available,
                    "model": self.config.model,
                    "findings_count": 0,
                    "items_type": "files",
                },
            )

        # Split into batches
        batches = [
            files[i : i + self.config.batch_size]
            for i in range(0, len(files), self.config.batch_size)
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
                    "Batch %d failed (%d files skipped): %s",
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

        # Account for files not fetched (available > fetched)
        not_fetched = max(0, total_available - len(files))

        return ExplorerResult(
            findings=synthesized,
            coverage={
                "time_window_days": self.config.time_window_days,
                "conversations_available": total_available,
                "conversations_reviewed": reviewed_count,
                "conversations_skipped": skipped_count + not_fetched,
                "model": self.config.model,
                "findings_count": len(synthesized),
                "items_type": "files",
            },
            token_usage=total_usage,
            batch_errors=batch_errors,
        )

    def requery(
        self,
        request_text: str,
        previous_findings: List[Dict[str, Any]],
        file_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Handle an explorer:request event with a follow-up question.

        Fetches relevant files if paths provided, then asks the LLM.
        """
        relevant_text = ""
        if file_paths:
            file_contents = []
            for path in file_paths:
                item = self.reader.fetch_file(path)
                if item:
                    file_contents.append(item)
            if file_contents:
                relevant_text = "\n\n".join(
                    self._format_file(f) for f in file_contents
                )

        user_prompt = CODEBASE_REQUERY_USER.format(
            previous_findings_json=json.dumps(previous_findings, indent=2),
            request_text=request_text,
            relevant_files=relevant_text or "(no specific files requested)",
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": CODEBASE_REQUERY_SYSTEM},
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
        structures. Evidence pointers reference file paths (not line offsets),
        so refactoring doesn't break references.
        """
        now = datetime.now(timezone.utc).isoformat()
        findings = []

        for raw_finding in result.findings:
            evidence = []
            for file_path in raw_finding.get("evidence_file_paths", []):
                evidence.append({
                    "source_type": SourceType.CODEBASE.value,
                    "source_id": file_path,
                    "retrieved_at": now,
                    "confidence": ConfidenceLevel.from_raw(
                        raw_finding.get("confidence", "medium")
                    ),
                })

            if not evidence:
                logger.warning(
                    "Dropping finding '%s' — no evidence_file_paths "
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
            "agent_name": "codebase",
            "findings": findings,
            "coverage": result.coverage,
        }

    # ========================================================================
    # Internal methods
    # ========================================================================

    def _analyze_batch(
        self,
        batch: List[CodebaseItem],
        batch_idx: int,
    ) -> tuple:
        """Send one batch to LLM, parse JSON response.

        Returns (findings_list, usage_dict).
        """
        formatted = "\n\n---\n\n".join(
            self._format_file(item) for item in batch
        )

        user_prompt = CODEBASE_BATCH_ANALYSIS_USER.format(
            batch_size=len(batch),
            time_window_days=self.config.time_window_days,
            formatted_files=formatted,
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": CODEBASE_BATCH_ANALYSIS_SYSTEM},
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
        batch_data = []
        for idx, findings in enumerate(all_batch_findings):
            batch_data.append({
                "batch_index": idx,
                "findings": findings,
            })

        user_prompt = CODEBASE_SYNTHESIS_USER.format(
            num_batches=len(all_batch_findings),
            total_files=total_reviewed,
            time_window_days=self.config.time_window_days,
            batch_findings_json=json.dumps(batch_data, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": CODEBASE_SYNTHESIS_SYSTEM},
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

    def _format_file(self, item: CodebaseItem) -> str:
        """Format a file for LLM input with metadata and truncation.

        Metadata line is always present. File content is truncated
        to max_chars_per_file budget.
        """
        budget = self.config.max_chars_per_file

        # Metadata line
        line_count = item.metadata.get("line_count", "?")
        commit_count = item.metadata.get("commit_count", "?")
        last_modified = item.metadata.get("last_modified", "unknown")
        authors = item.metadata.get("authors", [])
        authors_str = ", ".join(authors) if authors else "unknown"

        meta = (
            f"[{item.path}] lines={line_count} commits={commit_count}"
            f" last_modified={last_modified} authors={authors_str}"
        )

        content = item.content
        if not content.strip():
            return f"{meta}\n(empty file)"

        if len(content) > budget:
            content = content[:budget] + "\n[... truncated ...]"

        return f"{meta}\n{content}"


