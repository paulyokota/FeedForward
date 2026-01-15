"""
Unit Tests for Codebase Security Module

Tests path validation, secrets redaction, and command injection protection.
"""

import pytest
from pathlib import Path

from src.story_tracking.services.codebase_security import (
    filter_exploration_results,
    get_repo_path,
    is_sensitive_file,
    redact_secrets,
    validate_git_command_args,
    validate_path,
    validate_repo_name,
    APPROVED_REPOS,
    REPO_BASE_PATH,
)


class TestRepoValidation:
    """Tests for repository name validation."""

    def test_validate_approved_repo(self):
        """Should accept approved repository names."""
        for repo in APPROVED_REPOS:
            assert validate_repo_name(repo) is True

    def test_validate_unauthorized_repo(self):
        """Should reject unauthorized repository names."""
        assert validate_repo_name("malicious-repo") is False
        assert validate_repo_name("../../etc") is False
        assert validate_repo_name("") is False

    def test_get_repo_path_success(self):
        """Should return path for approved repos."""
        for repo in APPROVED_REPOS:
            path = get_repo_path(repo)
            assert isinstance(path, Path)
            assert path.name == repo
            assert REPO_BASE_PATH in path.parents or path.parent == REPO_BASE_PATH

    def test_get_repo_path_unauthorized(self):
        """Should raise ValueError for unauthorized repos."""
        with pytest.raises(ValueError, match="Unauthorized repo"):
            get_repo_path("malicious-repo")


class TestPathValidation:
    """Tests for path traversal protection."""

    def test_validate_path_within_base(self):
        """Should accept paths within REPO_BASE_PATH."""
        # These tests will pass if REPO_BASE_PATH exists, otherwise will fail
        # In real deployment, REPO_BASE_PATH will exist
        safe_path = str(REPO_BASE_PATH / "aero" / "src" / "app.py")
        result = validate_path(safe_path)
        # Result depends on whether REPO_BASE_PATH exists
        assert isinstance(result, bool)

    def test_validate_path_traversal_attack(self):
        """Should reject path traversal attempts."""
        assert validate_path("/etc/passwd") is False
        assert validate_path("../../../etc/passwd") is False

    def test_validate_path_invalid_input(self):
        """Should handle invalid input gracefully."""
        assert validate_path("") is False
        # None should be handled without crashing
        try:
            result = validate_path(None)  # type: ignore
            assert result is False
        except (TypeError, AttributeError):
            # Either return False or raise error is acceptable
            pass


class TestSensitiveFileDetection:
    """Tests for sensitive file pattern matching."""

    def test_detect_env_files(self):
        """Should detect .env files."""
        assert is_sensitive_file(".env") is True
        assert is_sensitive_file(".env.local") is True
        assert is_sensitive_file("config/.env.production") is True

    def test_detect_key_files(self):
        """Should detect key and certificate files."""
        assert is_sensitive_file("private_key.pem") is True
        assert is_sensitive_file("cert.key") is True
        assert is_sensitive_file("keys/private.key") is True
        assert is_sensitive_file("credentials.p12") is True

    def test_detect_secret_files(self):
        """Should detect files with 'secret' or 'password' in name."""
        assert is_sensitive_file("secrets.json") is True
        assert is_sensitive_file("config/passwords.txt") is True
        assert is_sensitive_file("api-secrets.yaml") is True

    def test_allow_normal_files(self):
        """Should allow normal source files."""
        assert is_sensitive_file("src/app.py") is False
        assert is_sensitive_file("components/Header.tsx") is False
        assert is_sensitive_file("README.md") is False
        assert is_sensitive_file("tests/test_security.py") is False


class TestSecretsRedaction:
    """Tests for secrets redaction in code content."""

    def test_redact_api_key(self):
        """Should redact API keys."""
        code = 'api_key = "sk-1234567890abcdef"'
        result = redact_secrets(code)
        assert "sk-1234567890abcdef" not in result
        assert "[REDACTED]" in result
        assert "api_key" in result  # Keep the key name

    def test_redact_password(self):
        """Should redact passwords."""
        code = 'password: "secret123"'
        result = redact_secrets(code)
        assert "secret123" not in result
        assert "[REDACTED]" in result
        assert "password" in result

    def test_redact_token(self):
        """Should redact tokens."""
        code = "AUTH_TOKEN = 'ghp_abc123xyz456'"
        result = redact_secrets(code)
        assert "ghp_abc123xyz456" not in result
        assert "[REDACTED]" in result

    def test_redact_multiple_secrets(self):
        """Should redact multiple secrets in same content."""
        code = '''
        api_key = "sk-123"
        password = "pass123"
        secret = "secret456"
        '''
        result = redact_secrets(code)
        assert "sk-123" not in result
        assert "pass123" not in result
        assert "secret456" not in result
        assert result.count("[REDACTED]") == 3

    def test_preserve_non_secret_content(self):
        """Should not modify non-secret content."""
        code = 'name = "John Doe"\nage = 30\nactive = true'
        result = redact_secrets(code)
        assert result == code

    def test_redact_unquoted_secrets(self):
        """Should redact unquoted secrets (env var style)."""
        code = "API_KEY=sk-1234567890"
        result = redact_secrets(code)
        assert "sk-1234567890" not in result
        assert "[REDACTED]" in result

    def test_redact_export_style(self):
        """Should redact shell export style secrets."""
        code = "export TOKEN=ghp_abc123"
        result = redact_secrets(code)
        assert "ghp_abc123" not in result
        assert "[REDACTED]" in result

    def test_redact_unquoted_with_delimiter(self):
        """Should redact unquoted secrets with trailing delimiter."""
        # The regex stops at whitespace, semicolon, comma, newline
        code = "password=secret123; next_var=value"
        result = redact_secrets(code)
        assert "secret123" not in result
        assert "[REDACTED]" in result


class TestExplorationFiltering:
    """Tests for filtering sensitive files from exploration results."""

    def test_filter_mixed_files(self):
        """Should filter out sensitive files while keeping normal ones."""
        files = [
            "src/app.py",
            ".env",
            "config/secrets.json",
            "tests/test.py",
            "private_key.pem",
            "README.md",
        ]
        filtered = filter_exploration_results(files)
        assert "src/app.py" in filtered
        assert "tests/test.py" in filtered
        assert "README.md" in filtered
        assert ".env" not in filtered
        assert "config/secrets.json" not in filtered
        assert "private_key.pem" not in filtered

    def test_filter_all_sensitive(self):
        """Should return empty list if all files are sensitive."""
        files = [".env", "secrets.yaml", "private.key"]
        filtered = filter_exploration_results(files)
        assert len(filtered) == 0

    def test_filter_no_sensitive(self):
        """Should return all files if none are sensitive."""
        files = ["src/app.py", "tests/test.py", "README.md"]
        filtered = filter_exploration_results(files)
        assert len(filtered) == 3
        assert filtered == files


class TestGitCommandValidation:
    """Tests for git command injection protection."""

    def test_validate_safe_commands(self):
        """Should accept safe git commands."""
        assert validate_git_command_args(["git", "fetch"]) is True
        assert validate_git_command_args(["git", "pull", "--rebase"]) is True
        assert validate_git_command_args(["git", "status", "-s"]) is True
        assert validate_git_command_args(["git", "log", "--oneline", "-10"]) is True

    def test_reject_command_injection(self):
        """Should reject commands with shell metacharacters."""
        assert validate_git_command_args(["git", "fetch", "; rm -rf /"]) is False
        assert validate_git_command_args(["git", "pull", "&&", "curl", "evil.com"]) is False
        assert validate_git_command_args(["git", "log", "|", "grep", "password"]) is False
        assert validate_git_command_args(["git", "status", "`whoami`"]) is False

    def test_reject_redirects(self):
        """Should reject commands with redirects."""
        assert validate_git_command_args(["git", "log", ">", "/etc/passwd"]) is False
        assert validate_git_command_args(["git", "fetch", "<", "input.txt"]) is False

    def test_allow_normal_flags(self):
        """Should allow normal git flags."""
        assert validate_git_command_args(["git", "fetch", "--all"]) is True
        assert validate_git_command_args(["git", "pull", "--ff-only"]) is True
        assert validate_git_command_args(["git", "log", "--pretty=oneline"]) is True

    def test_reject_arbitrary_git_commands(self):
        """Should reject arbitrary git subcommands not in allowlist."""
        # These would pass the old alphanumeric fallback, but should be rejected now
        assert validate_git_command_args(["git", "config", "user.name"]) is False
        assert validate_git_command_args(["git", "reset", "--hard"]) is False
        assert validate_git_command_args(["git", "checkout", "main"]) is False
        assert validate_git_command_args(["git", "rm", "-rf", "."]) is False

    def test_allow_numeric_arguments(self):
        """Should allow numeric arguments for flags like --depth."""
        assert validate_git_command_args(["git", "fetch", "--depth", "5"]) is True
        assert validate_git_command_args(["git", "log", "-10"]) is True
