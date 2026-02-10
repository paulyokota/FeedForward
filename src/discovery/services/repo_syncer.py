"""Repository syncer for the Discovery Engine.

Ensures target repos are up-to-date before codebase/research exploration.
Stashes local changes, pulls latest from the default branch, and logs
what happened for auditability.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Summary of a repo sync operation."""

    repo_path: str
    previous_branch: str
    default_branch: str
    commits_pulled: int = 0
    stash_created: bool = False
    stash_ref: Optional[str] = None
    stashed_files: List[str] = field(default_factory=list)
    already_up_to_date: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


class RepoSyncer:
    """Syncs a git repository to the latest default branch before exploration.

    Operations:
    1. Detect the default remote branch (not hardcoded to 'main')
    2. Stash any uncommitted changes with a run-labeled message
    3. Checkout the default branch
    4. Pull latest from origin
    5. Return a summary of what happened
    """

    def __init__(self, repo_path: str, run_id: Optional[str] = None):
        self.repo_path = Path(repo_path).resolve()
        self.run_id = run_id or "unknown"

    def sync(self) -> SyncResult:
        """Sync the repo to the latest default branch.

        Returns SyncResult with details of what happened.
        Raises no exceptions — errors are captured in SyncResult.error.
        """
        if not self.repo_path.is_dir():
            return SyncResult(
                repo_path=str(self.repo_path),
                previous_branch="",
                default_branch="",
                error=f"Directory does not exist: {self.repo_path}",
            )

        if not (self.repo_path / ".git").exists():
            return SyncResult(
                repo_path=str(self.repo_path),
                previous_branch="",
                default_branch="",
                error=f"Not a git repository: {self.repo_path}",
            )

        # Detect current branch
        current_branch = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if current_branch is None:
            return SyncResult(
                repo_path=str(self.repo_path),
                previous_branch="",
                default_branch="",
                error="Failed to detect current branch",
            )

        # Detect default remote branch
        default_branch = self._detect_default_branch()
        if default_branch is None:
            return SyncResult(
                repo_path=str(self.repo_path),
                previous_branch=current_branch,
                default_branch="",
                error="Failed to detect default remote branch",
            )

        result = SyncResult(
            repo_path=str(self.repo_path),
            previous_branch=current_branch,
            default_branch=default_branch,
        )

        # Stash uncommitted changes if any
        stash_result = self._stash_if_dirty(result)
        if stash_result is not None:
            return stash_result

        # Checkout default branch if not already on it
        if current_branch != default_branch:
            checkout_out = self._run_git("checkout", default_branch)
            if checkout_out is None:
                result.error = f"Failed to checkout {default_branch}"
                return result
            logger.info(
                "Repo %s: switched from %s to %s",
                self.repo_path.name,
                current_branch,
                default_branch,
            )

        # Pull latest
        pull_result = self._pull(result)
        return pull_result

    def _detect_default_branch(self) -> Optional[str]:
        """Detect the default branch from the remote HEAD reference."""
        # Try symbolic-ref first (most reliable)
        ref = self._run_git(
            "symbolic-ref", "refs/remotes/origin/HEAD", "--short"
        )
        if ref and ref.startswith("origin/"):
            return ref.replace("origin/", "", 1)

        # Fallback: check if 'main' or 'master' exists
        for candidate in ("main", "master"):
            check = self._run_git(
                "rev-parse", "--verify", f"refs/remotes/origin/{candidate}"
            )
            if check is not None:
                return candidate

        return None

    def _stash_if_dirty(self, result: SyncResult) -> Optional[SyncResult]:
        """Stash uncommitted changes if the working tree is dirty.

        Returns None if stash succeeded or wasn't needed.
        Returns SyncResult with error if stash failed.
        """
        status = self._run_git("status", "--porcelain")
        if status is None:
            result.error = "Failed to check git status"
            return result

        if not status.strip():
            return None  # Clean working tree

        # There are uncommitted changes — stash them
        stash_msg = f"discovery-run-{self.run_id[:8]}"
        dirty_files = [
            line[3:] for line in status.strip().splitlines() if len(line) > 3
        ]
        result.stashed_files = dirty_files

        stash_out = self._run_git("stash", "push", "--include-untracked", "-m", stash_msg)
        if stash_out is None:
            result.error = "Failed to stash uncommitted changes"
            return result

        # Get the stash ref
        stash_ref = self._run_git("stash", "list", "--max-count=1")
        if stash_ref:
            result.stash_ref = stash_ref.split(":")[0] if ":" in stash_ref else stash_ref

        result.stash_created = True
        logger.info(
            "Repo %s: stashed %d files as '%s' (ref: %s)",
            self.repo_path.name,
            len(dirty_files),
            stash_msg,
            result.stash_ref,
        )
        return None  # Success, continue

    def _pull(self, result: SyncResult) -> SyncResult:
        """Pull latest from origin and count commits pulled."""
        # Get current HEAD before pull
        head_before = self._run_git("rev-parse", "HEAD")

        pull_out = self._run_git("pull", "origin", result.default_branch)
        if pull_out is None:
            result.error = (
                f"Failed to pull from origin/{result.default_branch}. "
                "Check authentication and network access."
            )
            return result

        if "Already up to date" in (pull_out or ""):
            result.already_up_to_date = True
            result.commits_pulled = 0
            logger.info("Repo %s: already up to date", self.repo_path.name)
        else:
            # Count commits pulled
            head_after = self._run_git("rev-parse", "HEAD")
            if head_before and head_after and head_before != head_after:
                count_str = self._run_git(
                    "rev-list", "--count", f"{head_before}..{head_after}"
                )
                result.commits_pulled = int(count_str) if count_str else 0
            logger.info(
                "Repo %s: pulled %d commits on %s",
                self.repo_path.name,
                result.commits_pulled,
                result.default_branch,
            )

        return result

    def _run_git(self, *args: str) -> Optional[str]:
        """Run a git command in the repo directory.

        Returns stdout on success, None on failure.
        """
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.debug(
                    "git %s failed (rc=%d): %s",
                    " ".join(args),
                    result.returncode,
                    result.stderr.strip(),
                )
                return None
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning("git %s timed out in %s", " ".join(args), self.repo_path)
            return None
        except Exception as e:
            logger.warning("git %s error in %s: %s", " ".join(args), self.repo_path, e)
            return None
