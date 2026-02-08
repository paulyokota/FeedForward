"""Data access for the Codebase Explorer agent.

Reads recently-changed source files via git log + disk read. Deliberately
scoped to production code (src/ by default) and excludes tests, docs,
config, and binary files.

No external API dependencies — just git and the local filesystem.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# File extensions we consider source code (allowlist approach)
SOURCE_EXTENSIONS = frozenset({
    ".py", ".ts", ".js", ".tsx", ".jsx",
    ".json", ".yaml", ".yml",
    ".md", ".sql", ".html", ".css",
    ".sh", ".toml", ".cfg", ".ini",
})

# Directories to always exclude
EXCLUDED_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", ".mypy_cache",
    ".pytest_cache", ".tox", "dist", "build", ".eggs",
    "venv", ".venv", "env",
})


@dataclass
class CodebaseItem:
    """A file as the codebase explorer sees it.

    Raw file content plus git metadata. No classification,
    no analysis — just what's on disk and what git knows.
    """

    path: str  # Relative to repo root
    content: str  # File content (may be truncated by explorer)
    item_type: str = "source_file"
    metadata: Dict[str, Any] = field(default_factory=dict)
    # metadata keys: line_count, commit_count, last_modified, authors


class CodebaseReader:
    """Reads recently-changed source files for explorer agents.

    Uses git log to identify files changed within a time window,
    then reads their contents from disk. Scoped to a configurable
    set of directories (default: src/).
    """

    def __init__(
        self,
        repo_root: str,
        scope_dirs: Optional[List[str]] = None,
    ):
        self.repo_root = Path(repo_root)
        self.scope_dirs = scope_dirs or ["src/"]

    def fetch_recently_changed(
        self,
        days: int = 30,
        limit: Optional[int] = None,
    ) -> List[CodebaseItem]:
        """Fetch files changed in the last N days.

        Returns CodebaseItems ordered by most recent commit first.
        Excludes binary files, test files, and excluded directories.

        Args:
            days: How many days back to look.
            limit: Max files to return. None = no limit.

        Returns:
            List of CodebaseItem with file content and git metadata.
        """
        changed_files = self._get_changed_files(days)

        if not changed_files:
            logger.info("No changed files found in last %d days", days)
            return []

        items = []
        skipped = 0

        for file_path in changed_files:
            if limit is not None and len(items) >= limit:
                break

            full_path = self.repo_root / file_path

            if not full_path.exists() or not full_path.is_file():
                skipped += 1
                continue

            if not self._is_in_scope(file_path):
                skipped += 1
                continue

            if not self._is_source_file(file_path):
                skipped += 1
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Could not read %s: %s", file_path, e)
                skipped += 1
                continue

            metadata = self._get_file_metadata(file_path, days)

            items.append(CodebaseItem(
                path=file_path,
                content=content,
                metadata=metadata,
            ))

        if skipped > 0:
            logger.info(
                "Skipped %d files (out of scope, binary, or unreadable)", skipped
            )

        return items

    def fetch_file(self, path: str) -> Optional[CodebaseItem]:
        """Fetch a single file by path (for requery support)."""
        full_path = self.repo_root / path

        if not full_path.exists() or not full_path.is_file():
            return None

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Could not read %s: %s", path, e)
            return None

        metadata = self._get_file_metadata(path, days=30)

        return CodebaseItem(
            path=path,
            content=content,
            metadata=metadata,
        )

    def get_item_count(self, days: int = 30) -> int:
        """Count of source files changed in the time window.

        Counts only in-scope source files (same filter as fetch).
        """
        changed_files = self._get_changed_files(days)
        count = 0
        for file_path in changed_files:
            full_path = self.repo_root / file_path
            if (
                full_path.exists()
                and full_path.is_file()
                and self._is_in_scope(file_path)
                and self._is_source_file(file_path)
            ):
                count += 1
        return count

    # ========================================================================
    # Internal methods
    # ========================================================================

    def _get_changed_files(self, days: int) -> List[str]:
        """Get list of files changed in git within the time window.

        Returns file paths relative to repo root, ordered by most
        recent commit first. Deduplicates (a file changed in 3 commits
        appears once).
        """
        since_date = f"{days} days ago"

        try:
            result = subprocess.run(
                [
                    "git", "log",
                    f"--since={since_date}",
                    "--name-only",
                    "--pretty=format:",
                    "--diff-filter=ACMR",  # Added, Copied, Modified, Renamed
                ],
                capture_output=True,
                text=True,
                cwd=str(self.repo_root),
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("git log failed: %s", e)
            return []

        if result.returncode != 0:
            logger.warning("git log returned %d: %s", result.returncode, result.stderr)
            return []

        # Deduplicate while preserving order (most recent first)
        seen = set()
        files = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and line not in seen:
                seen.add(line)
                files.append(line)

        return files

    def _is_in_scope(self, file_path: str) -> bool:
        """Check if file falls within configured scope directories."""
        # Check excluded directories
        parts = Path(file_path).parts
        for part in parts:
            if part in EXCLUDED_DIRS:
                return False

        # Check scope directories
        return any(file_path.startswith(scope) for scope in self.scope_dirs)

    def _is_source_file(self, file_path: str) -> bool:
        """Check if file is a recognized source file type."""
        suffix = Path(file_path).suffix.lower()
        return suffix in SOURCE_EXTENSIONS

    def _get_file_metadata(self, file_path: str, days: int) -> Dict[str, Any]:
        """Get git metadata for a file: commit count, authors, last modified."""
        metadata: Dict[str, Any] = {}

        full_path = self.repo_root / file_path
        if full_path.exists():
            with open(full_path, errors="replace") as f:
                metadata["line_count"] = sum(1 for _ in f)

        try:
            result = subprocess.run(
                [
                    "git", "log",
                    f"--since={days} days ago",
                    "--format=%an|%aI",
                    "--", file_path,
                ],
                capture_output=True,
                text=True,
                cwd=str(self.repo_root),
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                metadata["commit_count"] = len(lines)
                authors = set()
                last_modified = None
                for line in lines:
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        authors.add(parts[0])
                        if last_modified is None:
                            last_modified = parts[1]
                metadata["authors"] = sorted(authors)
                if last_modified:
                    metadata["last_modified"] = last_modified
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return metadata
