"""
Unit Tests for CodebaseContextProvider

Tests the explore_for_theme() method with various theme data inputs.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

from src.story_tracking.services.codebase_context_provider import (
    CodebaseContextProvider,
    ExplorationResult,
    FileReference,
    CodeSnippet,
    SyncResult,
    StaticContext,
    MAX_FILE_SIZE_BYTES,
    UNSAFE_GLOB_CHARS,
)


class TestCodebaseContextProvider:
    """Tests for CodebaseContextProvider initialization."""

    def test_init_default_path(self):
        """Should initialize with default repos path."""
        provider = CodebaseContextProvider()
        assert provider.repos_path is not None
        assert isinstance(provider.repos_path, Path)

    def test_init_custom_path(self):
        """Should initialize with custom repos path."""
        custom_path = Path("/tmp/test-repos")
        provider = CodebaseContextProvider(repos_path=custom_path)
        assert provider.repos_path == custom_path


class TestSecurityConstants:
    """Tests for security configuration constants."""

    def test_max_file_size_is_reasonable(self):
        """MAX_FILE_SIZE_BYTES should be reasonable (10 MB)."""
        assert MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024  # 10 MB
        assert MAX_FILE_SIZE_BYTES > 1024 * 1024  # At least 1 MB
        assert MAX_FILE_SIZE_BYTES < 100 * 1024 * 1024  # Less than 100 MB

    def test_unsafe_glob_chars_defined(self):
        """UNSAFE_GLOB_CHARS should include dangerous metacharacters."""
        # Glob metacharacters
        assert '[' in UNSAFE_GLOB_CHARS
        assert ']' in UNSAFE_GLOB_CHARS
        assert '!' in UNSAFE_GLOB_CHARS
        assert '?' in UNSAFE_GLOB_CHARS
        assert '{' in UNSAFE_GLOB_CHARS
        assert '}' in UNSAFE_GLOB_CHARS

        # Shell injection characters
        assert '$' in UNSAFE_GLOB_CHARS
        assert '`' in UNSAFE_GLOB_CHARS
        assert '|' in UNSAFE_GLOB_CHARS
        assert ';' in UNSAFE_GLOB_CHARS
        assert '&' in UNSAFE_GLOB_CHARS

        # Newlines
        assert '\n' in UNSAFE_GLOB_CHARS
        assert '\r' in UNSAFE_GLOB_CHARS


class TestGlobSanitization:
    """Tests for _sanitize_for_glob() security feature."""

    def test_sanitize_removes_unsafe_chars(self):
        """Should remove glob metacharacters that could cause injection."""
        provider = CodebaseContextProvider()

        # Test various injection attempts
        # The sanitizer first removes unsafe chars, then replaces non-alphanumeric
        assert provider._sanitize_for_glob("[!pattern]") == "pattern"  # removes [ ! ]
        assert provider._sanitize_for_glob("test{a,b}") == "testa_b"  # removes { }, comma -> _
        assert provider._sanitize_for_glob("$HOME") == "HOME"  # removes $
        assert provider._sanitize_for_glob("cmd;rm -rf") == "cmdrm_-rf"  # removes ;, space -> _
        assert provider._sanitize_for_glob("a|b") == "ab"  # removes |

    def test_sanitize_preserves_safe_chars(self):
        """Should preserve alphanumeric, underscore, hyphen, dot."""
        provider = CodebaseContextProvider()

        assert provider._sanitize_for_glob("csv_import") == "csv_import"
        assert provider._sanitize_for_glob("auth-service") == "auth-service"
        assert provider._sanitize_for_glob("config.json") == "config.json"
        assert provider._sanitize_for_glob("MyComponent") == "MyComponent"

    def test_sanitize_limits_length(self):
        """Should limit pattern length to prevent excessively long patterns."""
        provider = CodebaseContextProvider()

        long_input = "a" * 100
        result = provider._sanitize_for_glob(long_input)

        assert len(result) <= 50

    def test_sanitize_handles_empty(self):
        """Should handle empty input."""
        provider = CodebaseContextProvider()

        assert provider._sanitize_for_glob("") == ""

    def test_build_patterns_sanitizes_input(self):
        """Should sanitize theme_data before building patterns."""
        provider = CodebaseContextProvider()

        # Malicious input that tries glob injection
        theme_data = {
            "product_area": "auth[!a-z]",
            "component": "$(whoami)",
        }
        patterns = provider._build_search_patterns(theme_data)

        # Should not contain raw injection patterns
        assert not any("[!a-z]" in p for p in patterns)
        assert not any("$(whoami)" in p for p in patterns)

        # Should contain sanitized versions
        # auth[!a-z] -> autha-z (unsafe chars removed)
        # $(whoami) -> _whoami_ (unsafe chars removed, parens -> _)
        assert any("autha-z" in p for p in patterns)
        assert any("_whoami_" in p for p in patterns)


class TestBuildSearchPatterns:
    """Tests for _build_search_patterns() method."""

    def test_basic_patterns(self):
        """Should include Tailwind-specific file type patterns."""
        provider = CodebaseContextProvider()
        theme_data = {}
        patterns = provider._build_search_patterns(theme_data)

        # Should include TypeScript monorepo patterns (aero, charlotte)
        assert "packages/**/*.ts" in patterns
        assert "packages/**/*.tsx" in patterns
        # Should include service patterns (tack, zuck, ghostwriter)
        assert "service/**/*.py" in patterns
        assert "client/**/*.ts" in patterns

    def test_product_area_patterns(self):
        """Should add patterns for product_area."""
        provider = CodebaseContextProvider()
        theme_data = {"product_area": "scheduling"}
        patterns = provider._build_search_patterns(theme_data)

        assert any("scheduling" in p for p in patterns)
        assert "**/scheduling/**/*" in patterns

    def test_component_patterns(self):
        """Should add patterns for component."""
        provider = CodebaseContextProvider()
        theme_data = {"component": "csv_import"}
        patterns = provider._build_search_patterns(theme_data)

        assert any("csv_import" in p for p in patterns)
        assert "**/csv_import/**/*" in patterns

    def test_space_replacement(self):
        """Should replace spaces with underscores."""
        provider = CodebaseContextProvider()
        theme_data = {"product_area": "user management"}
        patterns = provider._build_search_patterns(theme_data)

        assert any("user_management" in p for p in patterns)


class TestExtractKeywords:
    """Tests for _extract_keywords() method."""

    def test_extract_from_component(self):
        """Should extract keywords from component name."""
        provider = CodebaseContextProvider()
        theme_data = {"component": "csv_import"}
        keywords = provider._extract_keywords(theme_data)

        assert "csv" in keywords or "import" in keywords
        assert len(keywords) > 0

    def test_extract_from_symptoms(self):
        """Should extract keywords from symptoms."""
        provider = CodebaseContextProvider()
        theme_data = {
            "symptoms": [
                'Error message: "Failed to parse CSV"',
                "ERR_INVALID_FORMAT encountered",
            ]
        }
        keywords = provider._extract_keywords(theme_data)

        assert "Failed to parse CSV" in keywords
        assert "ERR_INVALID_FORMAT" in keywords

    def test_extract_from_user_intent(self):
        """Should extract keywords from user_intent."""
        provider = CodebaseContextProvider()
        theme_data = {"user_intent": "User wants to import scheduling data"}
        keywords = provider._extract_keywords(theme_data)

        # Should extract longer words
        assert any(len(k) >= 4 for k in keywords)

    def test_deduplication(self):
        """Should deduplicate keywords."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "csv_import",
            "user_intent": "import csv files",
        }
        keywords = provider._extract_keywords(theme_data)

        # Should not have duplicates
        assert len(keywords) == len(set(keywords))


class TestSqlSanitization:
    """Tests for _sanitize_sql_identifier() security feature."""

    def test_sanitize_removes_sql_injection_chars(self):
        """Should remove characters that could enable SQL injection."""
        provider = CodebaseContextProvider()

        # SQL injection attempts
        assert provider._sanitize_sql_identifier("users; DROP TABLE users--") == "usersDROPTABLEusers"
        assert provider._sanitize_sql_identifier('users" OR "1"="1') == "usersOR11"
        assert provider._sanitize_sql_identifier("users/* comment */") == "userscomment"

    def test_sanitize_preserves_valid_identifiers(self):
        """Should preserve valid SQL identifier characters."""
        provider = CodebaseContextProvider()

        assert provider._sanitize_sql_identifier("users") == "users"
        assert provider._sanitize_sql_identifier("user_preferences") == "user_preferences"
        assert provider._sanitize_sql_identifier("Table123") == "Table123"

    def test_sanitize_handles_leading_digit(self):
        """Should prefix underscore if identifier starts with digit."""
        provider = CodebaseContextProvider()

        assert provider._sanitize_sql_identifier("123table") == "_123table"

    def test_sanitize_limits_length(self):
        """Should limit identifier to PostgreSQL max length (63)."""
        provider = CodebaseContextProvider()

        long_input = "a" * 100
        result = provider._sanitize_sql_identifier(long_input)

        assert len(result) <= 63

    def test_sanitize_handles_empty(self):
        """Should handle empty input."""
        provider = CodebaseContextProvider()

        assert provider._sanitize_sql_identifier("") == ""


class TestDetectLanguage:
    """Tests for _detect_language() method."""

    def test_python_detection(self):
        """Should detect Python files."""
        provider = CodebaseContextProvider()
        assert provider._detect_language("src/app.py") == "python"

    def test_javascript_detection(self):
        """Should detect JavaScript files."""
        provider = CodebaseContextProvider()
        assert provider._detect_language("src/app.js") == "javascript"
        assert provider._detect_language("src/component.jsx") == "javascript"

    def test_typescript_detection(self):
        """Should detect TypeScript files."""
        provider = CodebaseContextProvider()
        assert provider._detect_language("src/app.ts") == "typescript"
        assert provider._detect_language("src/Component.tsx") == "typescript"

    def test_unknown_extension(self):
        """Should default to 'text' for unknown extensions."""
        provider = CodebaseContextProvider()
        assert provider._detect_language("README.md") == "text"
        assert provider._detect_language("config.yaml") == "text"


class TestGenerateQueries:
    """Tests for _generate_queries() method."""

    def test_component_query(self):
        """Should generate SQL query from component."""
        provider = CodebaseContextProvider()
        theme_data = {"component": "csv_import"}
        queries = provider._generate_queries(theme_data, [])

        assert len(queries) > 0
        assert any("csv_import" in q.lower() for q in queries)

    def test_symptom_query(self):
        """Should generate grep query from symptoms."""
        provider = CodebaseContextProvider()
        theme_data = {"symptoms": ['Error: "Connection timeout"']}
        queries = provider._generate_queries(theme_data, [])

        assert any("grep" in q for q in queries)

    def test_file_based_query(self):
        """Should generate file-based query when files provided."""
        provider = CodebaseContextProvider()
        theme_data = {"component": "csv_import"}
        files = [FileReference(path="src/csv/parser.py", relevance="test")]
        queries = provider._generate_queries(theme_data, files)

        assert len(queries) > 0


class TestExploreForTheme:
    """Tests for explore_for_theme() method."""

    def test_unauthorized_repo(self):
        """Should raise ValueError for unauthorized repo."""
        provider = CodebaseContextProvider()
        theme_data = {"product_area": "test"}

        with pytest.raises(ValueError, match="Unauthorized repo"):
            provider.explore_for_theme(theme_data, "malicious-repo")

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    @patch("src.story_tracking.services.codebase_context_provider.filter_exploration_results")
    @patch.object(CodebaseContextProvider, "_find_relevant_files")
    @patch.object(CodebaseContextProvider, "_search_for_keywords")
    @patch.object(CodebaseContextProvider, "_extract_snippets")
    @patch.object(CodebaseContextProvider, "_generate_queries")
    def test_explore_success(
        self,
        mock_generate_queries,
        mock_extract_snippets,
        mock_search_keywords,
        mock_find_files,
        mock_filter,
        mock_get_path,
    ):
        """Should successfully explore and return results."""
        # Setup mocks
        mock_get_path.return_value = Path("/tmp/test-repo")
        mock_find_files.return_value = ["file1.py", "file2.py"]
        mock_filter.return_value = ["file1.py"]
        mock_search_keywords.return_value = [
            FileReference(path="file1.py", line_start=10, relevance="5 matches")
        ]
        mock_extract_snippets.return_value = [
            CodeSnippet(
                file_path="file1.py",
                line_start=5,
                line_end=15,
                content="def test():\n    pass",
                language="python",
            )
        ]
        mock_generate_queries.return_value = ["SELECT * FROM test;"]

        # Execute
        provider = CodebaseContextProvider()
        theme_data = {
            "product_area": "scheduling",
            "component": "csv_import",
        }
        result = provider.explore_for_theme(theme_data, "aero")

        # Verify
        assert result.success is True
        assert len(result.relevant_files) == 1
        assert len(result.code_snippets) == 1
        assert len(result.investigation_queries) == 1
        assert result.exploration_duration_ms >= 0  # Can be 0 if very fast
        assert result.error is None

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    @patch.object(CodebaseContextProvider, "_find_relevant_files")
    def test_explore_handles_errors(self, mock_find_files, mock_get_path):
        """Should handle errors gracefully and return partial results."""
        # Setup mocks to raise exception
        mock_get_path.return_value = Path("/tmp/test-repo")
        mock_find_files.side_effect = Exception("Test error")

        # Execute
        provider = CodebaseContextProvider()
        theme_data = {"product_area": "test"}
        result = provider.explore_for_theme(theme_data, "aero")

        # Verify error handling
        assert result.success is False
        assert result.error is not None
        assert "Test error" in result.error
        assert result.exploration_duration_ms >= 0  # Can be 0 if very fast

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    @patch("src.story_tracking.services.codebase_context_provider.filter_exploration_results")
    @patch.object(CodebaseContextProvider, "_find_relevant_files")
    @patch.object(CodebaseContextProvider, "_extract_keywords")
    @patch.object(CodebaseContextProvider, "_search_for_keywords")
    @patch.object(CodebaseContextProvider, "_extract_snippets")
    @patch.object(CodebaseContextProvider, "_generate_queries")
    def test_explore_no_results(
        self,
        mock_queries,
        mock_snippets,
        mock_search,
        mock_keywords,
        mock_find,
        mock_filter,
        mock_path,
    ):
        """Should handle case with no matching files."""
        # Setup mocks to return empty results
        mock_path.return_value = Path("/tmp/test-repo")
        mock_find.return_value = []
        mock_filter.return_value = []
        mock_keywords.return_value = []
        mock_search.return_value = []
        mock_snippets.return_value = []
        mock_queries.return_value = []

        # Execute
        provider = CodebaseContextProvider()
        result = provider.explore_for_theme({"component": "nonexistent"}, "aero")

        # Verify
        assert result.success is True
        assert len(result.relevant_files) == 0
        assert len(result.code_snippets) == 0


class TestEnsureRepoFresh:
    """Tests for ensure_repo_fresh() repository sync functionality."""

    @patch("src.story_tracking.services.codebase_context_provider.subprocess.run")
    @patch("src.story_tracking.services.codebase_context_provider.validate_git_command_args")
    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    def test_ensure_repo_fresh_success(self, mock_get_path, mock_validate, mock_subprocess):
        """Should successfully sync repository with git fetch and pull."""
        # Setup mocks - use real Path to avoid str conversion issues
        mock_get_path.return_value = Path("/tmp/test-repos/aero")
        mock_validate.return_value = True  # Args are valid

        # Mock successful subprocess calls
        mock_fetch_result = MagicMock()
        mock_fetch_result.returncode = 0
        mock_fetch_result.stderr = ""

        mock_pull_result = MagicMock()
        mock_pull_result.returncode = 0
        mock_pull_result.stderr = ""

        mock_subprocess.side_effect = [mock_fetch_result, mock_pull_result]

        # Execute - need to mock exists() on Path
        with patch.object(Path, "exists", return_value=True):
            provider = CodebaseContextProvider()
            result = provider.ensure_repo_fresh("aero")

        # Verify
        assert result.success is True
        assert result.repo_name == "aero"
        assert result.error is None
        assert result.fetch_duration_ms >= 0
        assert result.pull_duration_ms >= 0
        assert mock_subprocess.call_count == 2  # fetch + pull

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    def test_ensure_repo_fresh_unauthorized(self, mock_get_path):
        """Should raise ValueError for unauthorized repository."""
        mock_get_path.side_effect = ValueError("Unauthorized repo: malicious")

        provider = CodebaseContextProvider()

        with pytest.raises(ValueError, match="Unauthorized repo"):
            provider.ensure_repo_fresh("malicious")

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    def test_ensure_repo_fresh_nonexistent_path(self, mock_get_path):
        """Should return failure when repository path doesn't exist."""
        mock_repo_path = Path("/nonexistent/path")
        mock_get_path.return_value = mock_repo_path

        # Don't mock exists() - let it return False naturally for nonexistent path
        provider = CodebaseContextProvider()
        result = provider.ensure_repo_fresh("aero")

        assert result.success is False
        assert "does not exist" in result.error

    @patch("src.story_tracking.services.codebase_context_provider.subprocess.run")
    @patch("src.story_tracking.services.codebase_context_provider.validate_git_command_args")
    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    def test_ensure_repo_fresh_fetch_fails(self, mock_get_path, mock_validate, mock_subprocess):
        """Should handle git fetch failure gracefully."""
        # Setup mocks
        mock_get_path.return_value = Path("/tmp/test-repos/aero")
        mock_validate.return_value = True

        # Mock failed fetch
        mock_fetch_result = MagicMock()
        mock_fetch_result.returncode = 1
        mock_fetch_result.stderr = "fatal: could not read from remote repository"

        mock_subprocess.return_value = mock_fetch_result

        # Execute
        with patch.object(Path, "exists", return_value=True):
            provider = CodebaseContextProvider()
            result = provider.ensure_repo_fresh("aero")

        # Verify
        assert result.success is False
        assert "Git fetch failed" in result.error
        assert result.fetch_duration_ms >= 0

    @patch("src.story_tracking.services.codebase_context_provider.subprocess.run")
    @patch("src.story_tracking.services.codebase_context_provider.validate_git_command_args")
    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    def test_ensure_repo_fresh_pull_fails(self, mock_get_path, mock_validate, mock_subprocess):
        """Should handle git pull failure gracefully."""
        # Setup mocks
        mock_get_path.return_value = Path("/tmp/test-repos/aero")
        mock_validate.return_value = True

        # Mock successful fetch, failed pull
        mock_fetch_result = MagicMock()
        mock_fetch_result.returncode = 0
        mock_fetch_result.stderr = ""

        mock_pull_result = MagicMock()
        mock_pull_result.returncode = 1
        mock_pull_result.stderr = "fatal: Not possible to fast-forward"

        mock_subprocess.side_effect = [mock_fetch_result, mock_pull_result]

        # Execute
        with patch.object(Path, "exists", return_value=True):
            provider = CodebaseContextProvider()
            result = provider.ensure_repo_fresh("aero")

        # Verify
        assert result.success is False
        assert "Git pull failed" in result.error

    @patch("src.story_tracking.services.codebase_context_provider.subprocess.run")
    @patch("src.story_tracking.services.codebase_context_provider.validate_git_command_args")
    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    def test_ensure_repo_fresh_timeout(self, mock_get_path, mock_validate, mock_subprocess):
        """Should handle subprocess timeout gracefully."""
        import subprocess

        mock_get_path.return_value = Path("/tmp/test-repos/aero")
        mock_validate.return_value = True

        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="git fetch", timeout=30)

        with patch.object(Path, "exists", return_value=True):
            provider = CodebaseContextProvider()
            result = provider.ensure_repo_fresh("aero")

        assert result.success is False
        assert "timed out" in result.error


class TestGetStaticContext:
    """Tests for get_static_context() static map fallback functionality."""

    def test_get_static_context_known_component(self):
        """Should return context for known components."""
        provider = CodebaseContextProvider()
        # Clear cache to ensure fresh load
        CodebaseContextProvider._codebase_map_cache = None

        result = provider.get_static_context("pinterest")

        assert result.component == "pinterest"
        assert result.source == "codebase_map"
        # Should have some context (may be empty if map not found)
        assert isinstance(result.tables, list)
        assert isinstance(result.api_patterns, list)

    def test_get_static_context_unknown_component(self):
        """Should return empty context for unknown components (not raise)."""
        provider = CodebaseContextProvider()

        result = provider.get_static_context("nonexistent_component_xyz")

        assert result.component == "nonexistent_component_xyz"
        assert result.source == "codebase_map"
        assert isinstance(result.tables, list)
        assert isinstance(result.api_patterns, list)
        # Should NOT raise an exception

    def test_get_static_context_caching(self):
        """Should cache the parsed codebase map."""
        # Clear cache
        CodebaseContextProvider._codebase_map_cache = None

        provider = CodebaseContextProvider()

        # First call loads the map
        result1 = provider.get_static_context("auth")

        # Second call should use cached data
        result2 = provider.get_static_context("billing")

        # Both should work and cache should be populated
        assert CodebaseContextProvider._codebase_map_cache is not None
        assert result1.source == "codebase_map"
        assert result2.source == "codebase_map"

    def test_get_static_context_normalized_lookup(self):
        """Should handle various component name formats."""
        provider = CodebaseContextProvider()

        # These should all potentially match similar context
        result1 = provider.get_static_context("e-commerce")
        result2 = provider.get_static_context("ecommerce")
        result3 = provider.get_static_context("E_Commerce")

        # All should return valid StaticContext (not raise)
        assert result1.source == "codebase_map"
        assert result2.source == "codebase_map"
        assert result3.source == "codebase_map"


class TestParseCodebaseMap:
    """Tests for _parse_codebase_map() parsing logic."""

    def test_parse_extracts_api_patterns(self):
        """Should extract API patterns from code blocks."""
        provider = CodebaseContextProvider()

        test_content = """
## Pinterest Scheduling

```
GET tack.tailwindapp.com/users/{userId}/boards
POST tack.tailwindapp.com/users/{userId}/posts
```

## Authentication

```
GET /api/gandalf/issue-token
```
"""
        result = provider._parse_codebase_map(test_content)

        # Should have parsed components
        assert "pinterest" in result
        assert "auth" in result

        # Pinterest should have tack patterns
        pinterest_apis = result["pinterest"]["api_patterns"]
        assert any("tack" in api for api in pinterest_apis)

        # Auth should have gandalf patterns
        auth_apis = result["auth"]["api_patterns"]
        assert any("gandalf" in api for api in auth_apis)

    def test_parse_handles_empty_content(self):
        """Should handle empty content gracefully."""
        provider = CodebaseContextProvider()

        result = provider._parse_codebase_map("")

        # Should return dict with component keys but empty lists
        assert isinstance(result, dict)
        for component_data in result.values():
            assert isinstance(component_data["tables"], list)
            assert isinstance(component_data["api_patterns"], list)
