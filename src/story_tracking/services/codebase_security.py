"""
Codebase Security Module

Path validation, command injection protection, and secrets redaction
for the codebase context system.

Reference: docs/architecture/dual-format-story-architecture.md
GitHub Issue: #37
"""

import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import List, Set

logger = logging.getLogger(__name__)

# Configuration from environment variables with secure defaults
REPO_BASE_PATH = Path(os.environ.get("FEEDFORWARD_REPOS_PATH", "/Users/paulyokota/Documents/GitHub"))
APPROVED_REPOS: Set[str] = {
    repo.strip()
    for repo in os.environ.get("FEEDFORWARD_APPROVED_REPOS", "aero,tack,charlotte,ghostwriter,zuck").split(",")
    if repo.strip()
}

# Sensitive file patterns to filter from exploration results
BLACKLIST_PATTERNS: List[str] = [
    ".env*",
    "*secrets*",
    "*credentials*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*password*",
    "*.keystore",
    "*.jks",
    "*private*key*",
    ".aws/*",
    ".ssh/*",
]

# Noisy file patterns to filter from code exploration (not secrets, just noise)
# These are paths that match glob patterns but aren't useful for code context
# Note: Uses simple substring/fnmatch patterns (not full glob ** syntax)
NOISE_EXCLUSION_PATTERNS: List[str] = [
    # Build outputs (match as substrings in path)
    "*/build/*",
    "/build/",
    "*/dist/*",
    "/dist/",
    "*/.next/*",
    "*/__pycache__/*",
    "*.pyc",

    # Compiled/minified assets
    "*.min.js",
    "*.min.css",
    "*.bundle.js",
    "*.chunk.js",
    "*.map",

    # Public/static assets (not source code)
    "*/public/*",
    "/public/",
    "*/static/*",
    "/static/",

    # Dependencies
    "*/node_modules/*",
    "/node_modules/",
    "*/.venv/*",
    "*/venv/*",

    # Generated files
    "*.generated.ts",
    "*.d.ts",
    "*/coverage/*",
    "/coverage/",
    "*/.coverage/*",

    # Lock files
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",

    # Legacy/compiled directories (Tailwind-specific)
    "tailwindapp-legacy/app/build/*",
    "tailwindapp-legacy/app/public/*",
    "*/compacted/*",
    "/compacted/",
]

# Regex patterns for redacting secrets in code content
# Matches common secret assignment patterns:
#   - api_key = "sk-1234..."     (quoted)
#   - password: "secret123"      (YAML/JSON style, quoted)
#   - AUTH_TOKEN = 'token'       (single quoted)
#   - API_KEY=sk-1234567890      (unquoted, env var style)
#   - export TOKEN=abc123        (shell export, unquoted)
# Does NOT match multi-line strings or complex nested structures
REDACTION_REGEX = re.compile(
    r"(api[_-]?key|password|token|secret|auth[_-]?token|access[_-]?key|private[_-]?key)"
    r"\s*[=:]\s*"
    r"(?:"
    r"['\"]([^'\"]+)['\"]"  # Quoted values
    r"|"
    r"([^\s;,\n\r]+)"  # Unquoted values (until whitespace, semicolon, comma, newline)
    r")",
    flags=re.IGNORECASE,
)


def validate_repo_name(repo_name: str) -> bool:
    """
    Check if repo name is in the approved allowlist.

    Args:
        repo_name: Name of the repository to validate

    Returns:
        True if repo is approved, False otherwise

    Example:
        >>> validate_repo_name("aero")
        True
        >>> validate_repo_name("malicious-repo")
        False
    """
    is_valid = repo_name in APPROVED_REPOS
    if not is_valid:
        logger.warning(
            f"Repo validation failed: '{repo_name}' not in approved list",
            extra={"repo_name": repo_name, "approved_repos": list(APPROVED_REPOS)},
        )
    return is_valid


def validate_path(path: str) -> bool:
    """
    Ensure path is within approved repo directories and prevents path traversal attacks.

    This function resolves the path and checks it's contained within REPO_BASE_PATH,
    preventing attacks like "../../../etc/passwd".

    Args:
        path: File system path to validate

    Returns:
        True if path is within approved directories, False otherwise

    Example:
        >>> validate_path("/Users/paulyokota/repos/aero/src/app.py")
        True
        >>> validate_path("/etc/passwd")
        False
        >>> validate_path("../../../etc/passwd")
        False
    """
    # Reject empty or whitespace-only paths
    if not path or not path.strip():
        logger.warning("Path validation failed: empty or whitespace path")
        return False

    try:
        resolved = Path(path).resolve()
        is_valid = resolved.is_relative_to(REPO_BASE_PATH)

        if not is_valid:
            logger.warning(
                f"Path validation failed: '{path}' not within base path",
                extra={
                    "path": str(path),
                    "resolved": str(resolved),
                    "base_path": str(REPO_BASE_PATH),
                },
            )

        return is_valid
    except (ValueError, TypeError, OSError) as e:
        logger.error(
            f"Path validation error: {e}",
            extra={"path": str(path), "error": str(e)},
        )
        return False


def get_repo_path(repo_name: str) -> Path:
    """
    Get full path to a repo, with validation.

    Args:
        repo_name: Name of the repository

    Returns:
        Path object pointing to the repository directory

    Raises:
        ValueError: If repo_name is not in the approved list

    Example:
        >>> get_repo_path("aero")
        PosixPath('/Users/paulyokota/repos/aero')
        >>> get_repo_path("malicious-repo")
        ValueError: Unauthorized repo: malicious-repo
    """
    if not validate_repo_name(repo_name):
        logger.error(
            f"Attempted access to unauthorized repo: '{repo_name}'",
            extra={"repo_name": repo_name},
        )
        raise ValueError(f"Unauthorized repo: {repo_name}")

    repo_path = REPO_BASE_PATH / repo_name
    logger.debug(f"Resolved repo path: {repo_path}", extra={"repo_name": repo_name})
    return repo_path


def is_sensitive_file(filepath: str) -> bool:
    """
    Check if filepath matches sensitive file patterns.

    Uses fnmatch for glob-style pattern matching against BLACKLIST_PATTERNS.

    Args:
        filepath: Path to file (can be relative or absolute)

    Returns:
        True if file matches any sensitive pattern, False otherwise

    Example:
        >>> is_sensitive_file(".env")
        True
        >>> is_sensitive_file("config/secrets.json")
        True
        >>> is_sensitive_file("src/app.py")
        False
        >>> is_sensitive_file("keys/private_key.pem")
        True
    """
    # Normalize path separators for consistent matching
    normalized = filepath.replace("\\", "/")

    # Check against all blacklist patterns
    for pattern in BLACKLIST_PATTERNS:
        # Match against both full path and basename
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(
            Path(normalized).name, pattern
        ):
            logger.info(
                f"Sensitive file detected: '{filepath}' matches pattern '{pattern}'",
                extra={"filepath": filepath, "pattern": pattern},
            )
            return True

    return False


def is_noise_file(filepath: str) -> bool:
    """
    Check if filepath matches noise exclusion patterns.

    These are files that may match search patterns but aren't useful for
    code context (build artifacts, compiled assets, dependencies).

    Args:
        filepath: Path to file (can be relative or absolute)

    Returns:
        True if file matches any noise pattern, False otherwise

    Example:
        >>> is_noise_file("packages/app/build/bundle.js")
        True
        >>> is_noise_file("node_modules/react/index.js")
        True
        >>> is_noise_file("src/components/Button.tsx")
        False
        >>> is_noise_file("app.min.js")
        True
    """
    # Normalize path separators for consistent matching
    normalized = filepath.replace("\\", "/")
    # Ensure path starts with / for consistent substring matching
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    # Check against all noise exclusion patterns
    for pattern in NOISE_EXCLUSION_PATTERNS:
        # For patterns with *, use fnmatch
        if "*" in pattern:
            if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(
                Path(normalized).name, pattern
            ):
                logger.debug(
                    f"Noise file detected: '{filepath}' matches pattern '{pattern}'",
                    extra={"filepath": filepath, "pattern": pattern},
                )
                return True
        else:
            # For simple substring patterns (like "/build/"), check containment
            if pattern in normalized:
                logger.debug(
                    f"Noise file detected: '{filepath}' contains pattern '{pattern}'",
                    extra={"filepath": filepath, "pattern": pattern},
                )
                return True

    return False


def redact_secrets(content: str) -> str:
    """
    Redact potential secrets from code content.

    Replaces secret values with '[REDACTED]' while preserving the key names
    for context. Matches patterns like:
    - api_key = "sk-1234..."
    - password: "mypassword123"
    - AUTH_TOKEN = 'token123'

    Args:
        content: Source code or configuration content

    Returns:
        Content with secrets redacted

    Example:
        >>> code = 'api_key = "sk-1234567890abcdef"'
        >>> redact_secrets(code)
        'api_key = "[REDACTED]"'
        >>> code = 'password: "secret123"'
        >>> redact_secrets(code)
        'password: "[REDACTED]"'
    """
    redaction_count = len(REDACTION_REGEX.findall(content))

    if redaction_count > 0:
        logger.info(
            f"Redacting {redaction_count} potential secret(s) from content",
            extra={"redaction_count": redaction_count},
        )

    redacted = REDACTION_REGEX.sub(r'\1 = "[REDACTED]"', content)
    return redacted


def filter_exploration_results(
    files: List[str],
    include_noise_filter: bool = True
) -> List[str]:
    """
    Filter out sensitive and optionally noisy files from exploration results.

    Removes files matching sensitive patterns (secrets, credentials) and
    optionally noise patterns (build artifacts, compiled assets) from
    file lists returned by exploration tools (Glob, Grep, etc.).

    Args:
        files: List of file paths from exploration
        include_noise_filter: If True, also filter noise files (default True)

    Returns:
        Filtered list with sensitive and optionally noise files removed

    Example:
        >>> files = ["src/app.py", ".env", "build/bundle.js", "tests/test.py"]
        >>> filter_exploration_results(files)
        ['src/app.py', 'tests/test.py']
        >>> filter_exploration_results(files, include_noise_filter=False)
        ['src/app.py', 'build/bundle.js', 'tests/test.py']
    """
    # Always filter sensitive files
    filtered = [f for f in files if not is_sensitive_file(f)]
    sensitive_removed = len(files) - len(filtered)

    # Optionally filter noise files
    noise_removed = 0
    if include_noise_filter:
        pre_noise_count = len(filtered)
        filtered = [f for f in filtered if not is_noise_file(f)]
        noise_removed = pre_noise_count - len(filtered)

    total_removed = sensitive_removed + noise_removed
    if total_removed > 0:
        logger.info(
            f"Filtered {total_removed} file(s) from exploration results",
            extra={
                "total_files": len(files),
                "filtered_files": len(filtered),
                "sensitive_removed": sensitive_removed,
                "noise_removed": noise_removed,
            },
        )

    return filtered


def validate_git_command_args(args: List[str]) -> bool:
    """
    Validate git command arguments to prevent command injection.

    Uses an allowlist approach for known-safe git commands and flags,
    combined with dangerous character detection for paths.
    This is defense-in-depth since we use shell=False, but adds extra protection.

    Args:
        args: List of command arguments to validate

    Returns:
        True if arguments are safe, False otherwise

    Example:
        >>> validate_git_command_args(["git", "fetch"])
        True
        >>> validate_git_command_args(["git", "fetch", "; rm -rf /"])
        False
        >>> validate_git_command_args(["git", "fetch", "--all"])
        True
    """
    # Allowlist of safe git commands and flags
    ALLOWED_GIT_ARGS = {
        "git", "fetch", "pull", "status", "log", "diff", "branch",
        "--all", "--ff-only", "--prune", "-C", "--depth", "--verbose", "-v",
    }

    # Dangerous shell metacharacters
    dangerous_chars = {";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r"}

    for arg in args:
        # Check for dangerous characters in any argument
        if any(char in arg for char in dangerous_chars):
            logger.error(
                f"Command injection attempt detected in git args: {args}",
                extra={"command_args": args, "suspicious_arg": arg},
            )
            return False

        # For flags with values (--flag=value), validate the value part
        if arg.startswith("-") and "=" in arg:
            flag_value = arg.split("=", 1)[1]
            if any(char in flag_value for char in dangerous_chars):
                logger.error(
                    f"Suspicious flag value in git args: {args}",
                    extra={"command_args": args, "suspicious_arg": arg},
                )
                return False

        # Check argument against allowlist or validate as path
        if arg in ALLOWED_GIT_ARGS:
            continue  # Explicitly allowed

        # Allow absolute paths if they pass validation
        if arg.startswith("/"):
            if not validate_path(arg):
                logger.error(
                    f"Invalid path in git args: {arg}",
                    extra={"command_args": args, "suspicious_arg": arg},
                )
                return False
            continue

        # Allow numeric arguments (for flags like --depth 5)
        if arg.isdigit():
            continue

        # Allow flags we haven't seen (still protected by shell=False)
        # but only if they start with - and have no suspicious content
        if arg.startswith("-"):
            continue  # Already checked for dangerous chars above

        # Reject unknown non-flag, non-path arguments
        # This prevents arbitrary git subcommands like "config", "reset", etc.
        logger.error(
            f"Rejected unknown git argument not in allowlist: {arg}",
            extra={"command_args": args, "suspicious_arg": arg, "allowlist": list(ALLOWED_GIT_ARGS)},
        )
        return False

    return True


# Module-level validation on import
if not REPO_BASE_PATH.exists():
    logger.warning(
        f"REPO_BASE_PATH does not exist: {REPO_BASE_PATH}",
        extra={"base_path": str(REPO_BASE_PATH)},
    )

logger.info(
    f"Codebase security module initialized",
    extra={
        "base_path": str(REPO_BASE_PATH),
        "approved_repos": list(APPROVED_REPOS),
        "blacklist_pattern_count": len(BLACKLIST_PATTERNS),
    },
)
