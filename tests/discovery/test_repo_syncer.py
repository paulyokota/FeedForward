"""Tests for RepoSyncer — target repo auto-pull before exploration."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.discovery.services.repo_syncer import RepoSyncer, SyncResult


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_git_repo(tmp_path):
    """Create a minimal git repo for testing."""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=str(repo),
        capture_output=True,
        env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@t.com",
             "HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    return repo


# ── SyncResult ────────────────────────────────────────────────────────

class TestSyncResult:
    def test_success_when_no_error(self):
        r = SyncResult(repo_path="/tmp/x", previous_branch="main", default_branch="main")
        assert r.success is True

    def test_failure_when_error_set(self):
        r = SyncResult(
            repo_path="/tmp/x", previous_branch="", default_branch="",
            error="something broke",
        )
        assert r.success is False


# ── Non-git paths ─────────────────────────────────────────────────────

class TestRepoSyncerInvalidPaths:
    def test_nonexistent_directory(self, tmp_path):
        syncer = RepoSyncer(str(tmp_path / "nope"), run_id="test123")
        result = syncer.sync()
        assert not result.success
        assert "does not exist" in result.error

    def test_not_a_git_repo(self, tmp_path):
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        syncer = RepoSyncer(str(plain_dir), run_id="test123")
        result = syncer.sync()
        assert not result.success
        assert "Not a git repository" in result.error


# ── Default branch detection ──────────────────────────────────────────

class TestDefaultBranchDetection:
    def test_detect_via_symbolic_ref(self):
        syncer = RepoSyncer("/tmp/fake", run_id="test")
        with patch.object(syncer, "_run_git") as mock:
            mock.return_value = "origin/develop"
            branch = syncer._detect_default_branch()
            assert branch == "develop"

    def test_fallback_to_main(self):
        syncer = RepoSyncer("/tmp/fake", run_id="test")
        call_count = 0

        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # symbolic-ref fails
            if args == ("rev-parse", "--verify", "refs/remotes/origin/main"):
                return "abc123"
            return None

        with patch.object(syncer, "_run_git", side_effect=side_effect):
            branch = syncer._detect_default_branch()
            assert branch == "main"

    def test_fallback_to_master(self):
        syncer = RepoSyncer("/tmp/fake", run_id="test")
        call_count = 0

        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return None  # symbolic-ref fails, main not found
            if args == ("rev-parse", "--verify", "refs/remotes/origin/master"):
                return "abc123"
            return None

        with patch.object(syncer, "_run_git", side_effect=side_effect):
            branch = syncer._detect_default_branch()
            assert branch == "master"

    def test_returns_none_when_nothing_works(self):
        syncer = RepoSyncer("/tmp/fake", run_id="test")
        with patch.object(syncer, "_run_git", return_value=None):
            branch = syncer._detect_default_branch()
            assert branch is None


# ── Stash behavior ────────────────────────────────────────────────────

class TestStashBehavior:
    def test_clean_working_tree_no_stash(self):
        syncer = RepoSyncer("/tmp/fake", run_id="test")
        result = SyncResult(
            repo_path="/tmp/fake",
            previous_branch="main",
            default_branch="main",
        )
        with patch.object(syncer, "_run_git", return_value=""):
            ret = syncer._stash_if_dirty(result)
            assert ret is None  # None means success, continue
            assert not result.stash_created

    def test_dirty_tree_creates_stash(self):
        syncer = RepoSyncer("/tmp/fake", run_id="abc12345")
        result = SyncResult(
            repo_path="/tmp/fake",
            previous_branch="feature/xyz",
            default_branch="main",
        )

        def side_effect(*args):
            if args[0] == "status":
                return " M file1.ts\n?? file2.ts"
            if args[0] == "stash" and args[1] == "push":
                return "Saved working directory"
            if args[0] == "stash" and args[1] == "list":
                return "stash@{0}: On feature/xyz: discovery-run-abc12345"
            return ""

        with patch.object(syncer, "_run_git", side_effect=side_effect):
            ret = syncer._stash_if_dirty(result)
            assert ret is None  # Success
            assert result.stash_created is True
            assert result.stash_ref == "stash@{0}"
            assert len(result.stashed_files) == 2


# ── Full sync with mocked git ────────────────────────────────────────

class TestFullSync:
    def test_sync_already_up_to_date(self, tmp_git_repo):
        syncer = RepoSyncer(str(tmp_git_repo), run_id="test")

        with patch.object(syncer, "_run_git") as mock:
            def side_effect(*args):
                cmd = args[0] if args else ""
                if cmd == "rev-parse" and "--abbrev-ref" in args:
                    return "main"
                if cmd == "symbolic-ref":
                    return "origin/main"
                if cmd == "status":
                    return ""  # clean
                if cmd == "pull":
                    return "Already up to date."
                if cmd == "rev-parse" and args == ("rev-parse", "HEAD"):
                    return "abc123"
                return ""

            mock.side_effect = side_effect
            result = syncer.sync()

        assert result.success
        assert result.already_up_to_date
        assert result.commits_pulled == 0

    def test_sync_pulls_commits(self, tmp_git_repo):
        syncer = RepoSyncer(str(tmp_git_repo), run_id="test")
        head_call_count = 0

        with patch.object(syncer, "_run_git") as mock:
            def side_effect(*args):
                nonlocal head_call_count
                cmd = args[0] if args else ""
                if cmd == "rev-parse" and "--abbrev-ref" in args:
                    return "main"
                if cmd == "symbolic-ref":
                    return "origin/main"
                if cmd == "status":
                    return ""
                if cmd == "pull":
                    return "Updating abc..def\nFast-forward"
                if cmd == "rev-parse" and args == ("rev-parse", "HEAD"):
                    head_call_count += 1
                    return "abc123" if head_call_count == 1 else "def456"
                if cmd == "rev-list":
                    return "15"
                return ""

            mock.side_effect = side_effect
            result = syncer.sync()

        assert result.success
        assert not result.already_up_to_date
        assert result.commits_pulled == 15

    def test_sync_switches_branch(self, tmp_git_repo):
        syncer = RepoSyncer(str(tmp_git_repo), run_id="test")

        with patch.object(syncer, "_run_git") as mock:
            def side_effect(*args):
                cmd = args[0] if args else ""
                if cmd == "rev-parse" and "--abbrev-ref" in args:
                    return "feature/thing"
                if cmd == "symbolic-ref":
                    return "origin/main"
                if cmd == "status":
                    return ""
                if cmd == "checkout":
                    assert args[1] == "main"
                    return "Switched to branch 'main'"
                if cmd == "pull":
                    return "Already up to date."
                if cmd == "rev-parse":
                    return "abc123"
                return ""

            mock.side_effect = side_effect
            result = syncer.sync()

        assert result.success
        assert result.previous_branch == "feature/thing"
        assert result.default_branch == "main"

    def test_sync_fails_on_pull_error(self, tmp_git_repo):
        syncer = RepoSyncer(str(tmp_git_repo), run_id="test")

        with patch.object(syncer, "_run_git") as mock:
            def side_effect(*args):
                cmd = args[0] if args else ""
                if cmd == "rev-parse" and "--abbrev-ref" in args:
                    return "main"
                if cmd == "symbolic-ref":
                    return "origin/main"
                if cmd == "status":
                    return ""
                if cmd == "pull":
                    return None  # Pull failed
                if cmd == "rev-parse":
                    return "abc123"
                return ""

            mock.side_effect = side_effect
            result = syncer.sync()

        assert not result.success
        assert "Failed to pull" in result.error


# ── RunConfig integration ─────────────────────────────────────────────

class TestRunConfigTargetRepo:
    def test_default_config_has_no_target(self):
        from src.discovery.models.run import RunConfig
        config = RunConfig()
        assert config.target_repo_path is None
        assert config.scope_dirs is None
        assert config.doc_paths is None
        assert config.auto_pull is True

    def test_config_with_target(self):
        from src.discovery.models.run import RunConfig
        config = RunConfig(
            target_repo_path="/path/to/aero",
            scope_dirs=["packages/"],
            doc_paths=["tmp/"],
            auto_pull=True,
        )
        assert config.target_repo_path == "/path/to/aero"
        assert config.scope_dirs == ["packages/"]
        assert config.doc_paths == ["tmp/"]
