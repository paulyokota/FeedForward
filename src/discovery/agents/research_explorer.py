"""Research Explorer agent for the Discovery Engine (Issue #218).

Reads internal documentation and reasons openly about patterns —
NOT through predefined categories, NOT using the existing theme vocabulary.
The artifact contracts validate output structure, not the agent's cognitive process.

Bucket-based batching strategy:
  - Classify docs into purpose buckets (strategy, architecture, process, etc.)
  - One LLM batch per bucket (with size-based sub-batching for large buckets)
  - Synthesis pass merges findings across all buckets

Key design: ResearchReader classifies docs by purpose, not just directory.
The LLM gets sharper context per batch ("you're analyzing architecture docs").

Per Issue #218: Fourth and final Stage 0 explorer. Surfaces latent product
signals in institutional knowledge — unresolved decisions, doc-reality gaps,
recurring blockers.
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
from src.discovery.agents.prompts import (
    RESEARCH_BATCH_ANALYSIS_SYSTEM,
    RESEARCH_BATCH_ANALYSIS_USER,
    RESEARCH_REQUERY_SYSTEM,
    RESEARCH_REQUERY_USER,
    RESEARCH_SYNTHESIS_SYSTEM,
    RESEARCH_SYNTHESIS_USER,
)
from src.discovery.agents.research_data_access import ResearchItem, ResearchReader
from src.discovery.models.enums import ConfidenceLevel, SourceType

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)


@dataclass
class ResearchExplorerConfig:
    """Configuration for the Research Explorer."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_chars_per_doc: int = 4000
    max_docs: int = 100
    max_chars_per_batch: int = 50000
    batch_size: int = 15  # docs per batch within a bucket


class ResearchExplorer:
    """Explorer agent that discovers patterns in internal documentation.

    Uses a bucket-based batching strategy: one LLM batch per document
    purpose bucket, followed by a synthesis pass across all buckets.
    """

    def __init__(
        self,
        reader: ResearchReader,
        openai_client=None,
        config: Optional[ResearchExplorerConfig] = None,
    ):
        self.reader = reader
        self.config = config or ResearchExplorerConfig()

        if openai_client is not None:
            self.client = openai_client
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def explore(self) -> ExplorerResult:
        """Run the full exploration: fetch → group by bucket → batch analyze → synthesize.

        Per-batch errors are caught and recorded (batch skipped, docs
        counted as skipped), so one LLM failure doesn't abort the whole run.

        Returns an ExplorerResult with findings and coverage metadata.
        """
        docs = self.reader.fetch_docs()
        total_available = self.reader.get_doc_count()

        if not docs:
            logger.info("No research documents found for exploration")
            return ExplorerResult(
                coverage={
                    "time_window_days": 1,
                    "conversations_available": total_available,
                    "conversations_reviewed": 0,
                    "conversations_skipped": total_available,
                    "model": self.config.model,
                    "findings_count": 0,
                    "items_type": "research_documents",
                    "bucket_counts": {},
                },
            )

        # Apply max_docs limit
        if len(docs) > self.config.max_docs:
            logger.info(
                "Limiting from %d to %d docs", len(docs), self.config.max_docs
            )
            docs = docs[: self.config.max_docs]

        # Group by bucket for structural batching
        buckets = self._group_by_bucket(docs)
        bucket_counts = {k: len(v) for k, v in buckets.items()}

        all_batch_findings: List[List[Dict[str, Any]]] = []
        reviewed_count = 0
        skipped_count = 0
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        batch_errors = []

        for bucket_name, bucket_docs in buckets.items():
            # Sub-batch large buckets
            sub_batches = [
                bucket_docs[i : i + self.config.batch_size]
                for i in range(0, len(bucket_docs), self.config.batch_size)
            ]

            for sub_batch in sub_batches:
                try:
                    findings, usage, docs_included = self._analyze_batch(
                        sub_batch, bucket_name
                    )
                    all_batch_findings.append(findings)
                    reviewed_count += docs_included
                    skipped_count += len(sub_batch) - docs_included
                    for key in total_usage:
                        total_usage[key] += usage.get(key, 0)
                except Exception as e:
                    logger.warning(
                        "Batch %s failed (%d docs skipped): %s",
                        bucket_name, len(sub_batch), e,
                    )
                    skipped_count += len(sub_batch)
                    batch_errors.append(f"Batch {bucket_name}: {e}")

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

        # Account for docs not fetched (available > fetched due to max_docs)
        not_fetched = max(0, total_available - len(docs))

        return ExplorerResult(
            findings=synthesized,
            coverage={
                "time_window_days": 1,
                "conversations_available": total_available,
                "conversations_reviewed": reviewed_count,
                "conversations_skipped": skipped_count + not_fetched,
                "model": self.config.model,
                "findings_count": len(synthesized),
                "items_type": "research_documents",
                "bucket_counts": bucket_counts,
            },
            token_usage=total_usage,
            batch_errors=batch_errors,
        )

    def requery(
        self,
        request_text: str,
        previous_findings: List[Dict[str, Any]],
        doc_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Handle an explorer:request event with a follow-up question.

        Fetches relevant docs if paths provided, then asks the LLM.
        """
        relevant_text = ""
        if doc_paths:
            doc_contents = []
            for path in doc_paths:
                item = self.reader.fetch_doc(path)
                if item:
                    doc_contents.append(item)
            if doc_contents:
                relevant_text = "\n\n".join(
                    self._format_doc(d) for d in doc_contents
                )

        user_prompt = RESEARCH_REQUERY_USER.format(
            previous_findings_json=json.dumps(previous_findings, indent=2),
            request_text=request_text,
            relevant_docs=relevant_text or "(no specific documents requested)",
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": RESEARCH_REQUERY_SYSTEM},
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
        structures. Evidence pointers reference doc paths mapped to
        EvidencePointer(source_type=RESEARCH, source_id=path).

        Findings without evidence_doc_paths are filtered out (ExplorerFinding
        requires min 1 evidence pointer).
        """
        now = datetime.now(timezone.utc).isoformat()
        findings = []

        for raw_finding in result.findings:
            evidence = []
            for doc_path in raw_finding.get("evidence_doc_paths", []):
                evidence.append({
                    "source_type": SourceType.RESEARCH.value,
                    "source_id": doc_path,
                    "retrieved_at": now,
                    "confidence": ConfidenceLevel.from_raw(
                        raw_finding.get("confidence", "medium")
                    ),
                })

            if not evidence:
                logger.warning(
                    "Dropping finding '%s' — no evidence_doc_paths "
                    "(ExplorerFinding requires min 1 evidence pointer)",
                    raw_finding.get("pattern_name", "unnamed"),
                )
                continue

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
            "agent_name": "research",
            "findings": findings,
            "coverage": result.coverage,
        }

    # ========================================================================
    # Internal methods
    # ========================================================================

    @staticmethod
    def _group_by_bucket(
        docs: List[ResearchItem],
    ) -> Dict[str, List[ResearchItem]]:
        """Group documents by bucket for structural batching."""
        groups: Dict[str, List[ResearchItem]] = defaultdict(list)
        for doc in docs:
            groups[doc.bucket].append(doc)
        return dict(groups)

    def _analyze_batch(
        self,
        batch: List[ResearchItem],
        bucket_name: str,
    ) -> tuple:
        """Send one bucket batch to LLM, parse JSON response.

        Applies max_chars_per_batch safety valve: if the formatted text
        exceeds the budget, drop tail docs (keeps doc boundaries intact).

        Returns (findings_list, usage_dict, docs_included_count).
        """
        formatted_docs = []
        for doc in batch:
            formatted_docs.append(self._format_doc(doc))

        # Safety valve: drop tail docs if total exceeds batch budget
        separator = "\n\n---\n\n"
        total_chars = 0
        included = []
        for fd in formatted_docs:
            needed = len(fd) + (len(separator) if included else 0)
            if total_chars + needed > self.config.max_chars_per_batch:
                logger.info(
                    "Batch %s: dropped %d/%d docs due to size budget",
                    bucket_name, len(formatted_docs) - len(included),
                    len(formatted_docs),
                )
                break
            included.append(fd)
            total_chars += needed

        docs_included = len(included) if included else 1  # fallback always includes 1
        formatted = separator.join(included or formatted_docs[:1])

        user_prompt = RESEARCH_BATCH_ANALYSIS_USER.format(
            batch_size=docs_included,
            bucket_name=bucket_name,
            formatted_docs=formatted,
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": RESEARCH_BATCH_ANALYSIS_SYSTEM.format(
                    bucket_name=bucket_name,
                )},
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
                f"Batch {bucket_name}: LLM response missing 'findings' list"
            )

        return raw["findings"], usage, docs_included

    def _synthesize(
        self,
        all_batch_findings: List[List[Dict[str, Any]]],
        total_reviewed: int,
    ) -> tuple:
        """Merge findings across buckets via LLM.

        Returns (synthesized_findings, usage_dict).
        """
        batch_data = []
        for idx, findings in enumerate(all_batch_findings):
            batch_data.append({
                "batch_index": idx,
                "findings": findings,
            })

        user_prompt = RESEARCH_SYNTHESIS_USER.format(
            num_buckets=len(all_batch_findings),
            total_docs=total_reviewed,
            batch_findings_json=json.dumps(batch_data, indent=2),
        )

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": RESEARCH_SYNTHESIS_SYSTEM},
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

    def _format_doc(self, item: ResearchItem) -> str:
        """Format a document for LLM input with metadata and truncation.

        Metadata line is always present. Content is truncated
        to max_chars_per_doc budget.
        """
        budget = self.config.max_chars_per_doc

        title = item.metadata.get("title", "")
        char_count = item.metadata.get("char_count", "?")
        line_count = item.metadata.get("line_count", "?")

        meta = (
            f"[{item.path}] bucket={item.bucket} chars={char_count}"
            f" lines={line_count}"
        )
        if title:
            meta += f" title=\"{title}\""

        content = item.content
        if not content.strip():
            return f"{meta}\n(empty document)"

        if len(content) > budget:
            content = content[:budget] + "\n[... truncated ...]"

        return f"{meta}\n{content}"
