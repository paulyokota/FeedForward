"""
Repository Sync Service

Background service for keeping local repositories synchronized with remotes.
Runs on a configurable interval (default: 6 hours) and records metrics.

Reference: docs/architecture/dual-format-story-architecture.md
GitHub Issue: #37
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from src.db.connection import get_connection
from src.story_tracking.services.codebase_security import (
    APPROVED_REPOS,
    get_repo_path,
    validate_git_command_args,
)

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_SYNC_INTERVAL_HOURS = 6
GIT_TIMEOUT_SECONDS = 30


@dataclass
class SyncMetrics:
    """Metrics from a single repository sync operation."""

    repo_name: str
    fetch_duration_ms: int = 0
    pull_duration_ms: int = 0
    total_duration_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None
    synced_at: datetime = None

    def __post_init__(self):
        if self.synced_at is None:
            self.synced_at = datetime.utcnow()


class RepoSyncService:
    """
    Background service for repository synchronization.

    Responsibilities:
    - Sync approved repositories on a configurable interval
    - Record timing metrics to database for observability
    - Handle errors gracefully and log for alerting

    Usage:
        service = RepoSyncService()

        # Sync all approved repos (called by scheduler)
        results = service.sync_all_repos()

        # Sync a specific repo
        metrics = service.sync_repo("aero")

    Scheduling:
        # With APScheduler:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(service.sync_all_repos, 'interval', hours=6)
        scheduler.start()

        # With cron:
        # 0 */6 * * * python -m src.services.repo_sync_service
    """

    def __init__(
        self,
        sync_interval_hours: int = DEFAULT_SYNC_INTERVAL_HOURS,
        repos_to_sync: Optional[List[str]] = None,
    ):
        """
        Initialize the sync service.

        Args:
            sync_interval_hours: Hours between sync runs (default: 6)
            repos_to_sync: Optional list of repos to sync. Defaults to APPROVED_REPOS.
        """
        self.sync_interval_hours = sync_interval_hours
        self.repos_to_sync = repos_to_sync or list(APPROVED_REPOS)
        logger.info(
            f"RepoSyncService initialized: interval={sync_interval_hours}h, "
            f"repos={self.repos_to_sync}"
        )

    def sync_repo(self, repo_name: str) -> SyncMetrics:
        """
        Sync a single repository via git fetch and pull.

        Uses subprocess with shell=False for command injection protection.
        Records timing metrics for observability.

        Args:
            repo_name: Name of the repository (must be in APPROVED_REPOS)

        Returns:
            SyncMetrics with timing and success status

        Raises:
            ValueError: If repo_name is not in APPROVED_REPOS
        """
        start_time = time.time()

        try:
            repo_path = get_repo_path(repo_name)

            if not repo_path.exists():
                raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

            logger.info(f"Starting sync for {repo_name} at {repo_path}")

            # Git fetch
            fetch_start = time.time()
            fetch_result = self._run_git_command(
                ["git", "-C", str(repo_path), "fetch", "--all"],
                timeout=GIT_TIMEOUT_SECONDS,
            )
            fetch_duration_ms = int((time.time() - fetch_start) * 1000)

            if fetch_result.returncode != 0:
                raise RuntimeError(f"Git fetch failed: {fetch_result.stderr}")

            # Git pull
            pull_start = time.time()
            pull_result = self._run_git_command(
                ["git", "-C", str(repo_path), "pull", "--ff-only"],
                timeout=GIT_TIMEOUT_SECONDS,
            )
            pull_duration_ms = int((time.time() - pull_start) * 1000)

            total_duration_ms = int((time.time() - start_time) * 1000)

            # Track success and any error message
            success = True
            error_message = None

            if pull_result.returncode != 0:
                # Pull failure means repo is NOT fully synchronized
                success = False
                error_message = f"Git pull failed: {pull_result.stderr}"
                logger.error(f"Git pull failed for {repo_name}: {pull_result.stderr}")

            metrics = SyncMetrics(
                repo_name=repo_name,
                fetch_duration_ms=fetch_duration_ms,
                pull_duration_ms=pull_duration_ms,
                total_duration_ms=total_duration_ms,
                success=success,
                error_message=error_message,
            )

            if success:
                logger.info(
                    f"Successfully synced {repo_name}: "
                    f"fetch={fetch_duration_ms}ms, pull={pull_duration_ms}ms, "
                    f"total={total_duration_ms}ms"
                )
            else:
                logger.warning(
                    f"Partial sync for {repo_name} (fetch succeeded, pull failed): "
                    f"fetch={fetch_duration_ms}ms, pull={pull_duration_ms}ms, "
                    f"total={total_duration_ms}ms"
                )

        except Exception as e:
            total_duration_ms = int((time.time() - start_time) * 1000)
            error_message = str(e)

            metrics = SyncMetrics(
                repo_name=repo_name,
                total_duration_ms=total_duration_ms,
                success=False,
                error_message=error_message,
            )

            logger.error(
                f"Failed to sync {repo_name}: {error_message}",
                extra={"repo_name": repo_name, "error": error_message},
            )

        # Record metrics to database
        self._record_metrics(metrics)

        return metrics

    def sync_all_repos(self) -> Dict[str, SyncMetrics]:
        """
        Sync all configured repositories.

        Called by the background scheduler on the configured interval.

        Returns:
            Dict mapping repo names to their sync metrics
        """
        logger.info(f"Starting sync for all repos: {self.repos_to_sync}")
        results = {}

        for repo_name in self.repos_to_sync:
            try:
                results[repo_name] = self.sync_repo(repo_name)
            except Exception as e:
                logger.error(f"Unexpected error syncing {repo_name}: {e}")
                results[repo_name] = SyncMetrics(
                    repo_name=repo_name,
                    success=False,
                    error_message=str(e),
                )

        # Summary logging
        success_count = sum(1 for m in results.values() if m.success)
        total_count = len(results)
        logger.info(
            f"Sync complete: {success_count}/{total_count} repos successful",
            extra={
                "success_count": success_count,
                "total_count": total_count,
                "results": {k: {"success": v.success, "total_ms": v.total_duration_ms}
                           for k, v in results.items()},
            },
        )

        return results

    def _run_git_command(
        self,
        args: List[str],
        timeout: int = GIT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess:
        """
        Run a git command safely with shell=False.

        Args:
            args: Command arguments as a list
            timeout: Timeout in seconds

        Returns:
            CompletedProcess result

        Raises:
            ValueError: If command args fail validation
            subprocess.TimeoutExpired: If command times out
        """
        # Validate args to prevent injection (defense in depth)
        if not validate_git_command_args(args):
            raise ValueError(f"Git command validation failed: {args}")

        logger.debug(f"Running git command: {' '.join(args)}")

        return subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _record_metrics(self, metrics: SyncMetrics) -> None:
        """
        Record sync metrics to database.

        Args:
            metrics: SyncMetrics to record
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO repo_sync_metrics
                        (id, repo_name, fetch_duration_ms, pull_duration_ms,
                         total_duration_ms, success, error_message, synced_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid4()),
                            metrics.repo_name,
                            metrics.fetch_duration_ms,
                            metrics.pull_duration_ms,
                            metrics.total_duration_ms,
                            metrics.success,
                            metrics.error_message,
                            metrics.synced_at,
                        ),
                    )
            logger.debug(f"Recorded sync metrics for {metrics.repo_name}")

        except Exception as e:
            logger.error(
                f"Failed to record sync metrics: {e}",
                extra={"repo_name": metrics.repo_name, "error": str(e)},
            )

    def get_last_sync_time(self, repo_name: str) -> Optional[datetime]:
        """
        Get the last successful sync time for a repository.

        Args:
            repo_name: Repository name

        Returns:
            Datetime of last successful sync, or None if never synced
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT synced_at FROM repo_sync_metrics
                        WHERE repo_name = %s AND success = true
                        ORDER BY synced_at DESC
                        LIMIT 1
                        """,
                        (repo_name,),
                    )
                    row = cursor.fetchone()
                    return row[0] if row else None

        except Exception as e:
            logger.error(f"Failed to get last sync time: {e}")
            return None

    def is_repo_stale(self, repo_name: str, max_age_hours: int = None) -> bool:
        """
        Check if a repository is stale (needs sync).

        Args:
            repo_name: Repository name
            max_age_hours: Maximum age in hours (defaults to sync_interval_hours)

        Returns:
            True if repo needs sync, False otherwise
        """
        max_age = max_age_hours or self.sync_interval_hours
        last_sync = self.get_last_sync_time(repo_name)

        if last_sync is None:
            return True

        age_hours = (datetime.utcnow() - last_sync).total_seconds() / 3600
        return age_hours > max_age


def run_sync_job():
    """
    Entry point for scheduled sync job.

    Can be invoked directly via:
        python -m src.services.repo_sync_service
    """
    logger.info("Starting scheduled repo sync job")
    service = RepoSyncService()
    results = service.sync_all_repos()

    # Exit with error code if any syncs failed
    failed = [r for r in results.values() if not r.success]
    if failed:
        logger.error(f"{len(failed)} repos failed to sync")
        return 1

    return 0


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sys.exit(run_sync_job())
