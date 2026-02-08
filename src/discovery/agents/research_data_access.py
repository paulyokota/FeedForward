"""Data access for the Research Explorer agent (Issue #218).

Reads internal markdown documentation from configurable directories
(default: docs/, reference/) and classifies each doc into a purpose-based
bucket using path heuristics. No external API dependencies — just the
local filesystem.

Design principle: loss-minimizing compression — format, don't filter.
Every doc gets a record. The LLM decides what's interesting.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Bucket classification: path prefix -> bucket name.
# Checked in order; first match wins.
BUCKET_RULES: List[tuple] = [
    ("docs/session/", "session_notes"),
    ("docs/process-playbook/", "process"),
    ("docs/runbook/", "process"),
    ("docs/testing/", "process"),
    ("docs/architecture/", "architecture"),
    ("docs/prompts/", "architecture"),
    ("docs/features/", "architecture"),
    ("docs/webapp/", "architecture"),
    ("docs/plans/", "strategy"),
    ("docs/acceptance-", "strategy"),
    ("docs/status", "strategy"),
    ("docs/proposed_roadmap", "strategy"),
    ("docs/changelog", "strategy"),
    ("docs/story-", "architecture"),
    ("docs/search-", "architecture"),
    ("docs/issue-", "architecture"),
    ("docs/multi-source/", "architecture"),
    ("reference/", "reference"),
]

# Directories to always exclude
EXCLUDED_PREFIXES = frozenset({
    "docs/_archive/",
    "docs/agent-conversation-archive/",
})


@dataclass
class ResearchItem:
    """A document as the research explorer sees it.

    Raw markdown content plus metadata. No analysis, no filtering —
    just what's on disk.
    """

    path: str  # Repo-relative path (e.g., "docs/architecture.md")
    content: str  # Markdown text (may be truncated by explorer)
    item_type: str = "internal_doc"
    bucket: str = "general"
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata keys: char_count, line_count, title


class ResearchReader:
    """Reads internal documentation for the Research Explorer.

    Walks configured directories, reads .md files, classifies each
    into a purpose-based bucket using path heuristics.
    """

    def __init__(
        self,
        doc_paths: Optional[List[str]] = None,
        repo_root: Optional[str] = None,
    ):
        self.doc_paths = doc_paths or ["docs/", "reference/"]
        self.repo_root = Path(repo_root) if repo_root else None
        self._docs: Optional[List[ResearchItem]] = None

    def fetch_docs(self) -> List[ResearchItem]:
        """Read all markdown files from configured directories.

        Returns ResearchItems sorted by bucket then path for
        deterministic LLM input. Caches result for repeated calls
        within the same reader instance.
        """
        if self._docs is not None:
            return self._docs

        items: List[ResearchItem] = []
        skipped = 0

        for doc_dir in self.doc_paths:
            base = self.repo_root / doc_dir if self.repo_root else Path(doc_dir)
            if not base.exists() or not base.is_dir():
                logger.info("Doc path %s does not exist, skipping", doc_dir)
                continue

            for md_file in sorted(base.rglob("*.md")):
                if not md_file.is_file():
                    continue

                # Build repo-relative path
                if self.repo_root:
                    rel_path = str(md_file.relative_to(self.repo_root))
                else:
                    rel_path = str(md_file)

                # Normalize to forward slashes
                rel_path = rel_path.replace("\\", "/")

                if self._is_excluded(rel_path):
                    skipped += 1
                    continue

                try:
                    content = md_file.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError) as e:
                    logger.warning("Could not read %s: %s", rel_path, e)
                    skipped += 1
                    continue

                bucket = self._classify_bucket(rel_path)
                title = self._extract_title(content)
                line_count = content.count("\n") + (1 if content else 0)

                items.append(ResearchItem(
                    path=rel_path,
                    content=content,
                    bucket=bucket,
                    metadata={
                        "char_count": len(content),
                        "line_count": line_count,
                        "title": title,
                    },
                ))

        if skipped > 0:
            logger.info("Skipped %d files (excluded or unreadable)", skipped)

        # Deterministic ordering: bucket then path
        items.sort(key=lambda item: (item.bucket, item.path))
        self._docs = items
        return items

    def fetch_doc(self, path: str) -> Optional[ResearchItem]:
        """Fetch a single document by repo-relative path (for requery)."""
        # Check cache first
        if self._docs is not None:
            for doc in self._docs:
                if doc.path == path:
                    return doc

        # Read from disk
        if self.repo_root:
            full_path = self.repo_root / path
        else:
            full_path = Path(path)

        if not full_path.exists() or not full_path.is_file():
            return None

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Could not read %s: %s", path, e)
            return None

        bucket = self._classify_bucket(path)
        title = self._extract_title(content)
        line_count = content.count("\n") + (1 if content else 0)

        return ResearchItem(
            path=path,
            content=content,
            bucket=bucket,
            metadata={
                "char_count": len(content),
                "line_count": line_count,
                "title": title,
            },
        )

    def get_doc_count(self) -> int:
        """Total number of documents across all configured directories."""
        docs = self.fetch_docs()
        return len(docs)

    def get_bucket_counts(self) -> Dict[str, int]:
        """Per-bucket document counts."""
        docs = self.fetch_docs()
        counts: Counter = Counter()
        for doc in docs:
            counts[doc.bucket] += 1
        return dict(counts)

    # ========================================================================
    # Internal methods
    # ========================================================================

    @staticmethod
    def _is_excluded(rel_path: str) -> bool:
        """Check if file should be excluded based on path prefix."""
        for prefix in EXCLUDED_PREFIXES:
            if rel_path.startswith(prefix):
                return True
        # Skip hidden directories
        parts = Path(rel_path).parts
        for part in parts:
            if part.startswith("."):
                return True
        return False

    @staticmethod
    def _classify_bucket(rel_path: str) -> str:
        """Classify a document into a bucket using path heuristics.

        Checks BUCKET_RULES in order; first match wins.
        Falls back to "general".
        """
        for prefix, bucket in BUCKET_RULES:
            if rel_path.startswith(prefix):
                return bucket
        return "general"

    @staticmethod
    def _extract_title(content: str) -> str:
        """Extract the first markdown heading as the document title.

        Returns empty string if no heading found.
        """
        for line in content.split("\n", 20):  # Check first 20 lines
            line = line.strip()
            match = re.match(r"^#+\s+(.+)", line)
            if match:
                return match.group(1).strip()
        return ""
