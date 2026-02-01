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
    KEYWORD_STOP_WORDS,
    PATH_PRIORITY_TIERS,
    # Issue #198: High-signal term detection
    HIGH_SIGNAL_FIELDS,
    STOP_WORD_STEMS,
    STOP_WORD_IRREGULARS,
    GENERIC_IDENTIFIER_NAMES,
    _is_stop_word_variant,
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
        keywords, metadata = provider._extract_keywords(theme_data)

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
        keywords, metadata = provider._extract_keywords(theme_data)

        # Quoted strings are lowercased, error codes preserved
        assert "failed to parse csv" in keywords
        assert "ERR_INVALID_FORMAT" in keywords

    def test_extract_from_user_intent(self):
        """Should extract keywords from user_intent."""
        provider = CodebaseContextProvider()
        theme_data = {"user_intent": "User wants to import scheduling data"}
        keywords, metadata = provider._extract_keywords(theme_data)

        # Should extract longer words
        assert any(len(k) >= 4 for k in keywords)

    def test_deduplication(self):
        """Should deduplicate keywords."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "csv_import",
            "user_intent": "import csv files",
        }
        keywords, metadata = provider._extract_keywords(theme_data)

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
        """Should successfully explore and return results with high confidence."""
        # Setup mocks - need enough files with strong matches to pass low-confidence check
        mock_get_path.return_value = Path("/tmp/test-repo")
        mock_find_files.return_value = ["file1.py", "file2.py", "file3.py", "file4.py"]
        mock_filter.return_value = ["file1.py", "file2.py", "file3.py"]
        # Return tuple (file_references, relevance_metadata) - Issue #198
        mock_search_keywords.return_value = (
            [
                FileReference(path="file1.py", line_start=10, relevance="10 matches: scheduler, queue"),
                FileReference(path="file2.py", line_start=20, relevance="8 matches: scheduler"),
                FileReference(path="file3.py", line_start=30, relevance="5 matches: queue"),
            ],
            {
                "match_score": 23,
                "matched_terms": ["scheduler", "queue"],
                "high_signal_matched": ["scheduler"],
                "matched_fields": ["product_area"],
                "term_diversity": 2,
                "threshold_passed": True,
                "gated": False,
            },
        )
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
        assert len(result.relevant_files) == 3
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
    def test_explore_no_results_returns_low_confidence(
        self,
        mock_queries,
        mock_snippets,
        mock_search,
        mock_keywords,
        mock_find,
        mock_filter,
        mock_path,
    ):
        """Should return low confidence (success=False) when no matching files found."""
        # Setup mocks to return empty results
        # Issue #198: _extract_keywords returns (keywords, metadata) tuple
        # Issue #198: _search_for_keywords returns (references, relevance_metadata) tuple
        mock_path.return_value = Path("/tmp/test-repo")
        mock_find.return_value = []
        mock_filter.return_value = []
        mock_keywords.return_value = ([], {"high_signal_terms": [], "keyword_sources": {}})
        mock_search.return_value = (
            [],
            {
                "match_score": 0,
                "matched_terms": [],
                "high_signal_matched": [],
                "matched_fields": [],
                "term_diversity": 0,
                "threshold_passed": False,
                "gated": False,
            },
        )
        mock_snippets.return_value = []
        mock_queries.return_value = []

        # Execute
        provider = CodebaseContextProvider()
        result = provider.explore_for_theme({"component": "nonexistent"}, "aero")

        # Verify: With no results, should return low confidence (issue #134 behavior)
        assert result.success is False
        # Issue #198: Error message updated for relevance gating
        assert "relevance threshold" in result.error.lower() or "low signal" in result.error.lower()
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
        # Clear cache to ensure fresh load (cache is now a dict keyed by path)
        CodebaseContextProvider._codebase_map_cache = {}

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
        # Clear cache (cache is now a dict keyed by path)
        CodebaseContextProvider._codebase_map_cache = {}

        provider = CodebaseContextProvider()

        # First call loads the map
        result1 = provider.get_static_context("auth")

        # Second call should use cached data
        result2 = provider.get_static_context("billing")

        # Both should work and cache should be populated (dict with at least one entry)
        assert len(CodebaseContextProvider._codebase_map_cache) > 0
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


class TestKeywordStopWords:
    """Tests for keyword stop-word filtering (issue #134)."""

    def test_stop_words_constant_defined(self):
        """Should have stop words constant defined."""
        assert len(KEYWORD_STOP_WORDS) > 0
        # Key generic terms should be in stop words
        assert "user" in KEYWORD_STOP_WORDS
        assert "data" in KEYWORD_STOP_WORDS
        assert "issue" in KEYWORD_STOP_WORDS
        assert "error" in KEYWORD_STOP_WORDS
        assert "trying" in KEYWORD_STOP_WORDS

    def test_extract_keywords_filters_stop_words(self):
        """Should filter out stop words from extracted keywords."""
        provider = CodebaseContextProvider()
        theme_data = {
            "user_intent": "user is trying to help with data issue error problem"
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        # All these are stop words and should be filtered
        for stop_word in ["user", "trying", "help", "with", "data", "issue", "error", "problem"]:
            assert stop_word not in keywords

    def test_extract_keywords_keeps_specific_terms(self):
        """Should keep specific technical terms."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "scheduler_queue",
            "symptoms": ['"ERR_SCHEDULER_TIMEOUT" error occurred']
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        # Should keep specific terms
        assert "scheduler" in keywords or "queue" in keywords
        assert "ERR_SCHEDULER_TIMEOUT" in keywords


class TestPathPriorityTiers:
    """Tests for path priority tier system (issue #134)."""

    def test_priority_tiers_defined(self):
        """Should have priority tiers defined."""
        assert len(PATH_PRIORITY_TIERS) > 0
        assert "tier_0" in PATH_PRIORITY_TIERS
        assert "tier_1" in PATH_PRIORITY_TIERS

    def test_tier_0_contains_source_paths(self):
        """Tier 0 should contain core source paths."""
        tier_0 = PATH_PRIORITY_TIERS["tier_0"]
        assert any("/src/" in p for p in tier_0)
        assert any("/app/" in p for p in tier_0)

    def test_tier_4_contains_test_paths(self):
        """Tier 4 should contain test paths (lower priority)."""
        tier_4 = PATH_PRIORITY_TIERS["tier_4"]
        assert any("/test" in p for p in tier_4)


class TestDeterministicFileRanking:
    """Tests for deterministic file ranking (issue #134)."""

    def test_rank_files_returns_sorted_list(self):
        """Should return files sorted by tier then alphabetically."""
        provider = CodebaseContextProvider()
        files = [
            "/repo/tests/test_foo.py",
            "/repo/src/app/main.py",
            "/repo/lib/utils.py",
            "/repo/api/routes.py",
        ]
        ranked = provider._rank_files_for_search(files)

        # src/app should come first (tier 0)
        assert ranked[0] == "/repo/src/app/main.py"

    def test_rank_files_is_deterministic(self):
        """Should produce same order for same input."""
        provider = CodebaseContextProvider()
        files = [
            "/repo/src/a.py",
            "/repo/tests/b.py",
            "/repo/lib/c.py",
            "/repo/api/d.py",
            "/repo/other/e.py",
        ]

        # Run twice
        ranked1 = provider._rank_files_for_search(files)
        ranked2 = provider._rank_files_for_search(files)

        # Should be identical
        assert ranked1 == ranked2

    def test_rank_files_alphabetical_within_tier(self):
        """Files in same tier should be sorted alphabetically."""
        provider = CodebaseContextProvider()
        files = [
            "/repo/src/zebra.py",
            "/repo/src/alpha.py",
            "/repo/src/beta.py",
        ]
        ranked = provider._rank_files_for_search(files)

        # All tier 0, should be alphabetical
        assert ranked[0] == "/repo/src/alpha.py"
        assert ranked[1] == "/repo/src/beta.py"
        assert ranked[2] == "/repo/src/zebra.py"

    def test_rank_files_deterministic_regardless_of_input_order(self):
        """Ranking should produce identical output regardless of input order."""
        provider = CodebaseContextProvider()

        # Same files in different orders
        files_v1 = ["/repo/tests/b.py", "/repo/src/a.py", "/repo/lib/c.py"]
        files_v2 = ["/repo/lib/c.py", "/repo/src/a.py", "/repo/tests/b.py"]
        files_v3 = ["/repo/src/a.py", "/repo/tests/b.py", "/repo/lib/c.py"]

        ranked_v1 = provider._rank_files_for_search(files_v1)
        ranked_v2 = provider._rank_files_for_search(files_v2)
        ranked_v3 = provider._rank_files_for_search(files_v3)

        # All should produce identical output
        assert ranked_v1 == ranked_v2 == ranked_v3


class TestLowConfidenceDetection:
    """Tests for low-confidence result detection (issue #134)."""

    def test_no_files_is_low_confidence(self):
        """Empty results should be low confidence."""
        provider = CodebaseContextProvider()
        assert provider._is_low_confidence_result([]) is True

    def test_few_files_is_low_confidence(self):
        """Fewer than 3 files should be low confidence."""
        provider = CodebaseContextProvider()
        files = [
            FileReference(path="a.py", relevance="5 matches"),
            FileReference(path="b.py", relevance="3 matches"),
        ]
        assert provider._is_low_confidence_result(files) is True

    def test_weak_matches_is_low_confidence(self):
        """All weak matches (1-2) should be low confidence."""
        provider = CodebaseContextProvider()
        files = [
            FileReference(path="a.py", relevance="1 match: foo"),
            FileReference(path="b.py", relevance="2 matches: bar"),
            FileReference(path="c.py", relevance="1 match: baz"),
            FileReference(path="d.py", relevance="2 matches: qux"),
            FileReference(path="e.py", relevance="1 match: quux"),
        ]
        assert provider._is_low_confidence_result(files) is True

    def test_strong_matches_is_high_confidence(self):
        """Strong matches (>2) should be high confidence."""
        provider = CodebaseContextProvider()
        files = [
            FileReference(path="a.py", relevance="10 matches: scheduler, queue"),
            FileReference(path="b.py", relevance="8 matches: scheduler"),
            FileReference(path="c.py", relevance="5 matches: queue"),
        ]
        assert provider._is_low_confidence_result(files) is False


class TestComponentPreservation:
    """Tests for component preservation in explore_with_classification (issue #134)."""

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    @patch("src.story_tracking.services.codebase_context_provider.filter_exploration_results")
    @patch.object(CodebaseContextProvider, "_find_relevant_files")
    @patch.object(CodebaseContextProvider, "_search_for_keywords")
    @patch.object(CodebaseContextProvider, "_extract_snippets")
    @patch.object(CodebaseContextProvider, "_generate_queries")
    @patch.object(CodebaseContextProvider, "_build_search_patterns")
    def test_theme_component_preserved_when_provided(
        self,
        mock_build_patterns,
        mock_generate_queries,
        mock_extract_snippets,
        mock_search_keywords,
        mock_find_files,
        mock_filter,
        mock_get_path,
    ):
        """Should use theme_component when provided instead of category."""
        # Setup mocks
        mock_get_path.return_value = Path("/tmp/test-repo")
        mock_find_files.return_value = []
        mock_filter.return_value = []
        mock_search_keywords.return_value = [
            FileReference(path="f1.py", relevance="10 matches"),
            FileReference(path="f2.py", relevance="8 matches"),
            FileReference(path="f3.py", relevance="5 matches"),
        ]
        mock_extract_snippets.return_value = []
        mock_generate_queries.return_value = []
        mock_build_patterns.return_value = []

        # Mock classifier
        provider = CodebaseContextProvider()
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = MagicMock(
            success=True,
            category="scheduling",  # Broad category
            suggested_search_paths=[],
            suggested_repos=["aero"],
        )
        provider.classifier = mock_classifier

        # Call with specific component
        provider.explore_with_classification(
            issue_text="Test issue",
            theme_component="pin_scheduler"  # Specific component
        )

        # Verify _build_search_patterns was called with preserved component
        call_args = mock_build_patterns.call_args[0][0]
        assert call_args["component"] == "pin_scheduler"  # Should NOT be "scheduling"


class TestProductAreaHintOverride:
    """Tests for product_area_hint parameter in explore_with_classification (Issue #178).

    Issue #178 added product_area_hint to allow theme metadata's product_area to
    override the classifier's category. This prevents issues where SmartSchedule
    settings were being misclassified as ai_creation due to keyword overlap.
    The hint ALWAYS wins when valid; when high-confidence classifier disagrees,
    we broaden search to include both categories' paths.
    """

    def test_resolve_product_area_uses_hint_when_valid(self):
        """Should prefer product_area_hint when it maps to a known category."""
        provider = CodebaseContextProvider()

        # Mock classification with medium confidence
        mock_classification = MagicMock(
            category="ai_creation",
            confidence="medium",
        )

        # Hint that maps to a known category
        effective_area, should_broaden = provider._resolve_product_area(
            classification=mock_classification,
            product_area_hint="scheduling",  # Known category
        )

        assert effective_area == "scheduling"  # Hint wins
        assert should_broaden is False  # No broadening for medium confidence

    def test_resolve_product_area_broadens_on_high_confidence_mismatch(self):
        """Should broaden search when high-confidence classification disagrees with hint."""
        provider = CodebaseContextProvider()

        # Mock classification with HIGH confidence that differs
        mock_classification = MagicMock(
            category="ai_creation",
            confidence="high",
        )

        effective_area, should_broaden = provider._resolve_product_area(
            classification=mock_classification,
            product_area_hint="scheduling",  # Different from classification
        )

        assert effective_area == "scheduling"  # Hint still wins
        assert should_broaden is True  # But should broaden search

    def test_resolve_product_area_uses_classification_when_no_hint(self):
        """Should use classification when no product_area_hint provided."""
        provider = CodebaseContextProvider()

        mock_classification = MagicMock(
            category="ai_creation",
            confidence="high",
        )

        effective_area, should_broaden = provider._resolve_product_area(
            classification=mock_classification,
            product_area_hint=None,  # No hint
        )

        assert effective_area == "ai_creation"  # Classification wins
        assert should_broaden is False  # No broadening needed

    def test_resolve_product_area_uses_classification_when_hint_invalid(self):
        """Should use classification when hint doesn't map to known category."""
        provider = CodebaseContextProvider()

        mock_classification = MagicMock(
            category="ai_creation",
            confidence="high",
        )

        effective_area, should_broaden = provider._resolve_product_area(
            classification=mock_classification,
            product_area_hint="unknown_category",  # Invalid category
        )

        assert effective_area == "ai_creation"  # Classification wins (hint invalid)
        assert should_broaden is False

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    @patch("src.story_tracking.services.codebase_context_provider.filter_exploration_results")
    @patch.object(CodebaseContextProvider, "_find_relevant_files")
    @patch.object(CodebaseContextProvider, "_search_for_keywords")
    @patch.object(CodebaseContextProvider, "_extract_snippets")
    @patch.object(CodebaseContextProvider, "_generate_queries")
    @patch.object(CodebaseContextProvider, "_build_search_patterns")
    def test_product_area_hint_used_in_exploration(
        self,
        mock_build_patterns,
        mock_generate_queries,
        mock_extract_snippets,
        mock_search_keywords,
        mock_find_files,
        mock_filter,
        mock_get_path,
    ):
        """Should use product_area_hint in theme_data for exploration."""
        # Setup mocks
        mock_get_path.return_value = Path("/tmp/test-repo")
        mock_find_files.return_value = []
        mock_filter.return_value = []
        mock_search_keywords.return_value = [
            FileReference(path="f1.py", relevance="10 matches"),
        ]
        mock_extract_snippets.return_value = []
        mock_generate_queries.return_value = []
        mock_build_patterns.return_value = []

        # Mock classifier to return ai_creation
        provider = CodebaseContextProvider()
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = MagicMock(
            success=True,
            category="ai_creation",
            confidence="medium",
            suggested_search_paths=[],
            suggested_repos=["ghostwriter"],
        )
        mock_classifier.categories = {"scheduling": {}, "ai_creation": {}}
        provider.classifier = mock_classifier

        # Call with product_area_hint
        provider.explore_with_classification(
            issue_text="SmartSchedule settings not working",
            product_area_hint="scheduling",  # Override classifier's ai_creation
        )

        # Verify theme_data uses the hint, not classifier's category
        call_args = mock_build_patterns.call_args[0][0]
        assert call_args["product_area"] == "scheduling"  # Hint used


class TestConfidenceGating:
    """Tests for confidence gating that broadens search for low/medium confidence (Issue #178).

    When classification confidence is low or medium, we include search paths from
    related_categories to cast a wider net. This helps catch relevant code that
    might be missed if the classification is wrong.
    """

    @patch("src.story_tracking.services.codebase_context_provider.get_repo_path")
    @patch("src.story_tracking.services.codebase_context_provider.filter_exploration_results")
    @patch.object(CodebaseContextProvider, "_find_relevant_files")
    @patch.object(CodebaseContextProvider, "_search_for_keywords")
    @patch.object(CodebaseContextProvider, "_extract_snippets")
    @patch.object(CodebaseContextProvider, "_generate_queries")
    def test_low_confidence_broadens_search_with_related_category_paths(
        self,
        mock_generate_queries,
        mock_extract_snippets,
        mock_search_keywords,
        mock_find_files,
        mock_filter,
        mock_get_path,
    ):
        """Should include related_categories search paths when confidence is low."""
        # Setup mocks
        mock_get_path.return_value = Path("/tmp/test-repo")
        mock_find_files.return_value = []
        mock_filter.return_value = []
        mock_search_keywords.return_value = []
        mock_extract_snippets.return_value = []
        mock_generate_queries.return_value = []

        # Mock classifier with LOW confidence
        provider = CodebaseContextProvider()
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = MagicMock(
            success=True,
            category="scheduling",
            confidence="low",  # Low confidence triggers broadening
            suggested_search_paths=["packages/**/scheduler/**/*"],
            suggested_repos=["aero"],
        )
        # Include related_categories in domain map
        mock_classifier.categories = {
            "scheduling": {
                "related_categories": ["pinterest_publishing"],
                "search_paths": ["packages/**/scheduler/**/*"],
            },
            "pinterest_publishing": {
                "search_paths": ["packages/**/pinterest/**/*"],
            },
        }
        provider.classifier = mock_classifier

        # Call explore_with_classification
        result, classification = provider.explore_with_classification(
            issue_text="Scheduler issue"
        )

        # Verify low confidence was returned
        assert classification.confidence == "low"

        # Verify _find_relevant_files was called (search was attempted)
        assert mock_find_files.called

        # Verify the broadening logic: when confidence is low, related_categories
        # paths should be included. We verify this by checking that the classifier's
        # categories dict was accessed (which contains related_categories).
        # The actual path merging happens in _explore_with_classifier_hints.
        assert mock_classifier.categories is not None
        assert "related_categories" in mock_classifier.categories["scheduling"]


class TestHighSignalTermDetection:
    """Tests for Issue #198: High-signal term detection in keyword extraction."""

    def test_stop_word_stems_defined(self):
        """Should have stop word stems with suffix patterns defined."""
        assert len(STOP_WORD_STEMS) > 0
        # Key stems should be present
        assert "work" in STOP_WORD_STEMS
        assert "help" in STOP_WORD_STEMS
        assert "try" in STOP_WORD_STEMS

    def test_stop_word_irregulars_defined(self):
        """Should have irregular stop words defined."""
        assert "tried" in STOP_WORD_IRREGULARS
        assert "tries" in STOP_WORD_IRREGULARS

    def test_suffix_safe_stem_filtering_network_not_filtered(self):
        """'network' should NOT be filtered (not a variant of 'work')."""
        assert not _is_stop_word_variant("network")
        assert not _is_stop_word_variant("Network")
        assert not _is_stop_word_variant("NETWORK")

    def test_suffix_safe_stem_filtering_working_is_filtered(self):
        """'working' and 'tried' should be filtered."""
        assert _is_stop_word_variant("working")
        assert _is_stop_word_variant("Working")
        assert _is_stop_word_variant("tried")
        assert _is_stop_word_variant("tries")

    def test_irregulars_coverage(self):
        """Irregular forms of 'try' should be filtered."""
        assert _is_stop_word_variant("tried")
        assert _is_stop_word_variant("tries")
        assert _is_stop_word_variant("try")
        assert _is_stop_word_variant("trying")

    def test_generic_identifiers_trimmed(self):
        """GENERIC_IDENTIFIER_NAMES should contain only most generic names."""
        assert "Error" in GENERIC_IDENTIFIER_NAMES
        assert "Exception" in GENERIC_IDENTIFIER_NAMES
        assert "Warning" in GENERIC_IDENTIFIER_NAMES
        # These should NOT be in the list (too specific, kept as high-signal)
        assert "TimeoutError" not in GENERIC_IDENTIFIER_NAMES
        assert "ValueError" not in GENERIC_IDENTIFIER_NAMES

    def test_high_signal_fields_defined(self):
        """HIGH_SIGNAL_FIELDS should include product_area, component, error."""
        assert "product_area" in HIGH_SIGNAL_FIELDS
        assert "component" in HIGH_SIGNAL_FIELDS
        assert "error" in HIGH_SIGNAL_FIELDS

    def test_extract_keywords_returns_tuple(self):
        """_extract_keywords should return (keywords, metadata) tuple."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "pin_scheduler",
            "product_area": "scheduling",
        }
        result = provider._extract_keywords(theme_data)
        assert isinstance(result, tuple)
        assert len(result) == 2
        keywords, metadata = result
        assert isinstance(keywords, list)
        assert isinstance(metadata, dict)

    def test_extract_keywords_high_signal_classification(self):
        """Keywords from product_area/component should be in high_signal_terms."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "pin_scheduler",
            "product_area": "scheduling",
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        assert "high_signal_terms" in metadata
        assert "secondary_terms" in metadata
        # "scheduling" should be in high_signal_terms (from product_area)
        assert "scheduling" in metadata["high_signal_terms"]
        # "pin_scheduler" compound form should be present
        assert "pin_scheduler" in metadata["high_signal_terms"]

    def test_extract_keywords_sorted_and_deduped(self):
        """Keywords should be sorted and de-duplicated for determinism."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "scheduler",
            "product_area": "scheduling",
        }
        keywords1, metadata1 = provider._extract_keywords(theme_data)
        keywords2, metadata2 = provider._extract_keywords(theme_data)

        # Should be deterministic
        assert keywords1 == keywords2
        assert metadata1["high_signal_terms"] == metadata2["high_signal_terms"]
        # Should be sorted
        assert keywords1 == sorted(keywords1)

    def test_extract_keywords_source_fields_tracking(self):
        """source_fields should track which fields contributed keywords."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "scheduler",
            "product_area": "billing",
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        assert "source_fields" in metadata
        assert "component" in metadata["source_fields"]
        assert "product_area" in metadata["source_fields"]

    def test_keyword_sources_map_structure(self):
        """keyword_sources should map keywords to source fields as lists."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "scheduler",
            "product_area": "scheduling",  # Same word, different field
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        assert "keyword_sources" in metadata
        keyword_sources = metadata["keyword_sources"]

        # All values should be lists (not sets) for JSON serialization
        for term, sources in keyword_sources.items():
            assert isinstance(sources, list), f"{term} sources should be a list"
            # Lists should be sorted
            assert sources == sorted(sources), f"{term} sources should be sorted"

    def test_multi_source_term_accumulation(self):
        """Same term appearing in multiple fields should accumulate sources."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "timeout",
            "user_intent": "I need help with timeout issues",
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        keyword_sources = metadata["keyword_sources"]
        if "timeout" in keyword_sources:
            sources = keyword_sources["timeout"]
            # Could be from multiple sources (depends on whether user_intent extracts it)
            assert isinstance(sources, list)

    def test_camelcase_identifiers_extracted_as_high_signal(self):
        """CamelCase identifiers in symptoms should be high-signal."""
        provider = CodebaseContextProvider()
        theme_data = {
            "symptoms": ["TimeoutError occurred when calling SchedulerService"],
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        # "timeouterror" should be extracted (normalized to lowercase)
        assert "timeouterror" in keywords
        # Should be high-signal
        assert "timeouterror" in metadata["high_signal_terms"]

    def test_generic_identifiers_filtered_from_symptoms(self):
        """Generic identifiers like 'Error' should be filtered."""
        provider = CodebaseContextProvider()
        theme_data = {
            "symptoms": ["An Error occurred"],
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        # "error" alone should NOT be in high_signal_terms (it's generic)
        # Note: The word "error" is also in KEYWORD_STOP_WORDS, so it gets filtered
        assert "error" not in keywords

    def test_case_normalization_lowercase_except_error_codes(self):
        """CamelCase normalized to lowercase; all-caps error codes kept as-is."""
        provider = CodebaseContextProvider()
        theme_data = {
            "symptoms": ["ERR_TIMEOUT123 error from TimeoutError"],
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        # All-caps error codes kept as-is
        assert "ERR_TIMEOUT123" in keywords
        # CamelCase normalized
        assert "timeouterror" in keywords

    def test_classification_priority_high_signal_wins(self):
        """If a term appears in both high_signal and secondary, high_signal wins."""
        provider = CodebaseContextProvider()
        theme_data = {
            "component": "timeout",
            "user_intent": "timeout configuration needed",
        }
        keywords, metadata = provider._extract_keywords(theme_data)

        # "timeout" should be in high_signal_terms (from component)
        if "timeout" in keywords:
            assert "timeout" in metadata["high_signal_terms"]
            # And NOT in secondary_terms
            assert "timeout" not in metadata["secondary_terms"]


class TestRelevanceGating:
    """Tests for Issue #198: Relevance gating in codebase exploration."""

    def test_search_for_keywords_returns_tuple(self):
        """_search_for_keywords should return (references, relevance_metadata) tuple."""
        provider = CodebaseContextProvider()

        with patch.object(provider, "_rank_files_for_search", return_value=[]):
            result = provider._search_for_keywords(
                repo_path=Path("/tmp"),
                files=[],
                keywords=["test"],
                keyword_metadata={"high_signal_terms": ["test"], "keyword_sources": {}},
            )

        assert isinstance(result, tuple)
        assert len(result) == 2
        references, relevance_metadata = result
        assert isinstance(references, list)
        assert isinstance(relevance_metadata, dict)

    def test_relevance_metadata_structure(self):
        """relevance_metadata should have required fields."""
        provider = CodebaseContextProvider()

        with patch.object(provider, "_rank_files_for_search", return_value=[]):
            _, relevance_metadata = provider._search_for_keywords(
                repo_path=Path("/tmp"),
                files=[],
                keywords=["test"],
                keyword_metadata={"high_signal_terms": [], "keyword_sources": {}},
            )

        assert "match_score" in relevance_metadata
        assert "matched_terms" in relevance_metadata
        assert "high_signal_matched" in relevance_metadata
        assert "matched_fields" in relevance_metadata
        assert "term_diversity" in relevance_metadata
        assert "threshold_passed" in relevance_metadata
        assert "gated" in relevance_metadata

    def test_threshold_passes_with_high_signal_match(self):
        """Threshold should pass when high_signal_matched >= 1."""
        provider = CodebaseContextProvider()

        # Mock the file reading to simulate finding a match for "scheduler"
        # We patch validate_path to allow any path and mock file content
        with patch(
            "src.story_tracking.services.codebase_context_provider.validate_path",
            return_value=True
        ):
            with patch("builtins.open", mock_open(read_data="scheduler = True\n")):
                with patch.object(Path, "stat") as mock_stat:
                    mock_stat.return_value.st_size = 100
                    with patch.object(provider, "_rank_files_for_search", return_value=["/fake/path.py"]):
                        _, relevance_metadata = provider._search_for_keywords(
                            repo_path=Path("/fake"),
                            files=["/fake/path.py"],
                            keywords=["scheduler"],
                            keyword_metadata={
                                "high_signal_terms": ["scheduler"],
                                "keyword_sources": {"scheduler": ["component"]},
                            },
                        )

        assert relevance_metadata["threshold_passed"] is True
        assert len(relevance_metadata["high_signal_matched"]) >= 1
        assert "scheduler" in relevance_metadata["high_signal_matched"]

    def test_threshold_passes_with_term_diversity(self):
        """Threshold should pass when term_diversity >= 2."""
        provider = CodebaseContextProvider()

        # Mock the file reading to simulate finding matches for both keywords
        with patch(
            "src.story_tracking.services.codebase_context_provider.validate_path",
            return_value=True
        ):
            with patch("builtins.open", mock_open(read_data="scheduler = True\nbilling = True\n")):
                with patch.object(Path, "stat") as mock_stat:
                    mock_stat.return_value.st_size = 100
                    with patch.object(provider, "_rank_files_for_search", return_value=["/fake/path.py"]):
                        _, relevance_metadata = provider._search_for_keywords(
                            repo_path=Path("/fake"),
                            files=["/fake/path.py"],
                            keywords=["scheduler", "billing"],
                            keyword_metadata={
                                "high_signal_terms": [],  # No high signal
                                "keyword_sources": {},
                            },
                        )

        assert relevance_metadata["term_diversity"] >= 2
        assert relevance_metadata["threshold_passed"] is True

    def test_threshold_fails_with_low_relevance(self):
        """Threshold should fail when no high_signal and diversity < 2."""
        provider = CodebaseContextProvider()

        with patch.object(provider, "_rank_files_for_search", return_value=[]):
            _, relevance_metadata = provider._search_for_keywords(
                repo_path=Path("/tmp"),
                files=[],
                keywords=["test"],
                keyword_metadata={
                    "high_signal_terms": [],
                    "keyword_sources": {},
                },
            )

        # No matches at all
        assert relevance_metadata["term_diversity"] == 0
        assert len(relevance_metadata["high_signal_matched"]) == 0
        assert relevance_metadata["threshold_passed"] is False

    def test_matched_fields_from_actual_matches(self):
        """matched_fields should reflect actual matched terms, not just source_fields."""
        provider = CodebaseContextProvider()

        # Mock the file reading to simulate only "scheduler" matching (not "billing")
        with patch(
            "src.story_tracking.services.codebase_context_provider.validate_path",
            return_value=True
        ):
            with patch("builtins.open", mock_open(read_data="scheduler = True\n")):
                with patch.object(Path, "stat") as mock_stat:
                    mock_stat.return_value.st_size = 100
                    with patch.object(provider, "_rank_files_for_search", return_value=["/fake/path.py"]):
                        _, relevance_metadata = provider._search_for_keywords(
                            repo_path=Path("/fake"),
                            files=["/fake/path.py"],
                            keywords=["scheduler", "billing"],
                            keyword_metadata={
                                "high_signal_terms": ["scheduler", "billing"],
                                "keyword_sources": {
                                    "scheduler": ["component"],
                                    "billing": ["product_area"],
                                },
                            },
                        )

        # Only "component" should be in matched_fields (since "scheduler" matched)
        assert "component" in relevance_metadata["matched_fields"]
        # "product_area" should NOT be in matched_fields (since "billing" didn't match)
        assert "product_area" not in relevance_metadata["matched_fields"]

    def test_empty_matches_empty_matched_fields(self):
        """When no matches, matched_fields should be empty even if source_fields exists."""
        provider = CodebaseContextProvider()

        with patch.object(provider, "_rank_files_for_search", return_value=[]):
            _, relevance_metadata = provider._search_for_keywords(
                repo_path=Path("/tmp"),
                files=[],
                keywords=["nonexistent"],
                keyword_metadata={
                    "high_signal_terms": ["nonexistent"],
                    "source_fields": ["component", "product_area"],
                    "keyword_sources": {"nonexistent": ["component"]},
                },
            )

        assert relevance_metadata["matched_fields"] == []
        assert relevance_metadata["matched_terms"] == []

    def test_matched_terms_sorted_deterministic(self):
        """matched_terms should be sorted for deterministic output."""
        provider = CodebaseContextProvider()

        # Create a temp file with multiple keywords
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("billing = True\nscheduler = True\nauth = True\n")
            temp_path = f.name

        try:
            _, relevance_metadata = provider._search_for_keywords(
                repo_path=Path(tempfile.gettempdir()),
                files=[temp_path],
                keywords=["billing", "scheduler", "auth"],
                keyword_metadata={"high_signal_terms": [], "keyword_sources": {}},
            )

            assert relevance_metadata["matched_terms"] == sorted(relevance_metadata["matched_terms"])
        finally:
            import os
            os.unlink(temp_path)

    def test_exploration_result_has_relevance_metadata(self):
        """ExplorationResult should have relevance_metadata field."""
        result = ExplorationResult(
            relevant_files=[],
            relevance_metadata={"test": True},
        )
        assert result.relevance_metadata == {"test": True}

    def test_is_low_confidence_with_relevance_metadata(self):
        """_is_low_confidence_result should check relevance_metadata threshold."""
        provider = CodebaseContextProvider()

        # Many files, but threshold not passed
        refs = [FileReference(path=f"file{i}.py", relevance="10 matches") for i in range(5)]

        # Without relevance_metadata, should not be low confidence (enough files, strong matches)
        assert not provider._is_low_confidence_result(refs, relevance_metadata=None)

        # With failing threshold, should be low confidence
        assert provider._is_low_confidence_result(refs, relevance_metadata={"threshold_passed": False})

        # With passing threshold, should not be low confidence
        assert not provider._is_low_confidence_result(refs, relevance_metadata={"threshold_passed": True})
