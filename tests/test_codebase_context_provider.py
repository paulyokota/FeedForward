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
        """Should include basic file type patterns."""
        provider = CodebaseContextProvider()
        theme_data = {}
        patterns = provider._build_search_patterns(theme_data)

        assert "**/*.py" in patterns
        assert "**/*.js" in patterns
        assert "**/*.ts" in patterns
        assert "**/*.tsx" in patterns

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
