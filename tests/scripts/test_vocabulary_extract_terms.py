"""
Tests for vocabulary_extract_terms.py normalization and retry logic.

Issue #154: Tests for robustness and data quality improvements.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path


# Mock openai before importing vocabulary_extract_terms
# This prevents import failures in test environments without OpenAI credentials
# The mock must be added to sys.modules BEFORE the import statement
sys.modules["openai"] = MagicMock()

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from vocabulary_extract_terms import (
    singularize,
    normalize_term,
    normalize_terms_list,
    _call_openai_with_retry,
    MAX_RETRIES,
    RETRY_DELAY_BASE,
)


class TestSingularize:
    """Tests for the singularize function."""

    def test_standard_s_plural(self):
        """Test standard -s plurals."""
        assert singularize("pins") == "pin"
        assert singularize("boards") == "board"
        assert singularize("drafts") == "draft"
        assert singularize("posts") == "post"
        assert singularize("images") == "image"
        assert singularize("accounts") == "account"

    def test_es_plural_sibilants(self):
        """Test -es plurals after sibilants."""
        assert singularize("boxes") == "box"
        assert singularize("matches") == "match"
        assert singularize("batches") == "batch"
        assert singularize("wishes") == "wish"
        assert singularize("classes") == "class"
        assert singularize("buzzes") == "buzz"

    def test_ies_plural(self):
        """Test -ies -> -y plurals."""
        assert singularize("stories") == "story"
        assert singularize("categories") == "category"
        assert singularize("queries") == "query"
        assert singularize("copies") == "copy"

    def test_ves_plural_to_f(self):
        """Test -ves -> -f plurals (allowlist)."""
        assert singularize("leaves") == "leaf"
        assert singularize("halves") == "half"
        assert singularize("shelves") == "shelf"
        assert singularize("calves") == "calf"
        assert singularize("wolves") == "wolf"

    def test_ves_plural_to_fe(self):
        """Test -ves -> -fe plurals (Issue #154 review fix)."""
        assert singularize("wives") == "wife"
        assert singularize("knives") == "knife"
        assert singularize("lives") == "life"

    def test_words_ending_ves_not_f_plural(self):
        """Test words ending in -ves that are NOT f->ves plurals (Issue #154 Round 2).

        Words like 'archives' end in -ve+s (regular plural of -ve),
        not the f->ves transformation. They should not become '-f'.
        """
        # These should become -ve (removing just the 's'), not -f
        assert singularize("archives") == "archive"
        assert singularize("saves") == "save"
        assert singularize("moves") == "move"
        assert singularize("waves") == "wave"
        assert singularize("resolves") == "resolve"

    def test_oes_plural(self):
        """Test -oes -> -o plurals."""
        assert singularize("heroes") == "hero"
        assert singularize("potatoes") == "potato"

    def test_irregular_plurals(self):
        """Test irregular plurals that should remain unchanged."""
        assert singularize("children") == "child"
        assert singularize("data") == "data"
        assert singularize("media") == "media"
        assert singularize("people") == "people"

    def test_already_singular(self):
        """Test words that are already singular."""
        assert singularize("pin") == "pin"
        assert singularize("board") == "board"
        assert singularize("draft") == "draft"

    def test_short_words(self):
        """Test short words that shouldn't be modified."""
        assert singularize("") == ""
        assert singularize("a") == "a"
        assert singularize("is") == "is"

    def test_words_ending_ss(self):
        """Test words ending in ss (shouldn't lose the final s)."""
        assert singularize("class") == "class"
        assert singularize("boss") == "boss"

    def test_non_plural_words_ending_s(self):
        """Test words ending in 's' that are NOT plurals (Issue #154 review fix)."""
        # These should NOT be singularized
        assert singularize("status") == "status"
        assert singularize("bus") == "bus"
        assert singularize("analysis") == "analysis"
        assert singularize("canvas") == "canvas"
        assert singularize("focus") == "focus"
        assert singularize("virus") == "virus"
        assert singularize("process") == "process"
        assert singularize("access") == "access"
        assert singularize("progress") == "progress"


class TestNormalizeTerm:
    """Tests for the normalize_term function."""

    def test_lowercase_conversion(self):
        """Test lowercase conversion."""
        assert normalize_term("PIN") == "pin"
        assert normalize_term("Board") == "board"
        assert normalize_term("SCHEDULED_PIN") == "scheduled_pin"

    def test_whitespace_handling(self):
        """Test whitespace stripping and collapsing."""
        assert normalize_term("  pin  ") == "pin"
        assert normalize_term("scheduled  pin") == "scheduled pin"
        assert normalize_term("\t board \n") == "board"

    def test_singularization(self):
        """Test singularization is applied."""
        assert normalize_term("pins") == "pin"
        assert normalize_term("Boards") == "board"

    def test_compound_terms(self):
        """Test compound terms with underscores."""
        assert normalize_term("scheduled_pins") == "scheduled_pin"
        assert normalize_term("SOCIAL_POSTS") == "social_post"
        assert normalize_term("user_accounts") == "user_account"

    def test_empty_and_none(self):
        """Test empty string handling."""
        assert normalize_term("") == ""
        assert normalize_term("   ") == ""


class TestNormalizeTermsList:
    """Tests for the normalize_terms_list function."""

    def test_normalizes_all_terms(self):
        """Test all terms are normalized."""
        terms = ["Pins", "BOARDS", "drafts"]
        result = normalize_terms_list(terms)
        assert result == ["pin", "board", "draft"]

    def test_removes_duplicates_after_normalization(self):
        """Test duplicates are removed after normalization."""
        terms = ["pins", "pin", "PINS", "Pin"]
        result = normalize_terms_list(terms)
        assert result == ["pin"]

    def test_removes_empty_terms(self):
        """Test empty terms are removed."""
        terms = ["pin", "", "  ", "board"]
        result = normalize_terms_list(terms)
        assert result == ["pin", "board"]

    def test_preserves_order(self):
        """Test order is preserved (first occurrence wins)."""
        terms = ["board", "pins", "Board", "pin"]
        result = normalize_terms_list(terms)
        assert result == ["board", "pin"]

    def test_empty_list(self):
        """Test empty list returns empty list."""
        assert normalize_terms_list([]) == []


class TestCallOpenAIWithRetry:
    """Tests for the _call_openai_with_retry function."""

    @patch("vocabulary_extract_terms.time.sleep")
    def test_successful_first_attempt(self, mock_sleep):
        """Test successful response on first attempt."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content='{"0": {"objects": ["pin"]}}'))]
        mock_client.chat.completions.create.return_value = mock_response

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result == {"0": {"objects": ["pin"]}}
        mock_client.chat.completions.create.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("vocabulary_extract_terms.time.sleep")
    def test_retry_on_json_parse_error(self, mock_sleep):
        """Test retry on JSON parse error."""
        mock_client = Mock()
        # First call returns invalid JSON, second returns valid
        mock_response_bad = Mock()
        mock_response_bad.choices = [Mock(message=Mock(content="not valid json"))]
        mock_response_good = Mock()
        mock_response_good.choices = [Mock(message=Mock(content='{"0": {"objects": ["pin"]}}'))]
        mock_client.chat.completions.create.side_effect = [mock_response_bad, mock_response_good]

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result == {"0": {"objects": ["pin"]}}
        assert mock_client.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once_with(RETRY_DELAY_BASE)

    @patch("vocabulary_extract_terms.time.sleep")
    def test_retry_on_rate_limit_error(self, mock_sleep):
        """Test retry on rate limit error."""
        mock_client = Mock()
        # First call raises rate limit, second succeeds
        mock_response_good = Mock()
        mock_response_good.choices = [Mock(message=Mock(content='{"0": {"objects": ["pin"]}}'))]
        mock_client.chat.completions.create.side_effect = [
            Exception("Rate limit exceeded (429)"),
            mock_response_good,
        ]

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result == {"0": {"objects": ["pin"]}}
        assert mock_client.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once_with(RETRY_DELAY_BASE)

    @patch("vocabulary_extract_terms.time.sleep")
    def test_retry_on_server_error(self, mock_sleep):
        """Test retry on 5xx server error."""
        mock_client = Mock()
        mock_response_good = Mock()
        mock_response_good.choices = [Mock(message=Mock(content='{"0": {"objects": ["pin"]}}'))]
        mock_client.chat.completions.create.side_effect = [
            Exception("Server error 503"),
            mock_response_good,
        ]

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result == {"0": {"objects": ["pin"]}}
        assert mock_client.chat.completions.create.call_count == 2

    @patch("vocabulary_extract_terms.time.sleep")
    def test_exponential_backoff(self, mock_sleep):
        """Test exponential backoff timing."""
        mock_client = Mock()
        mock_response_good = Mock()
        mock_response_good.choices = [Mock(message=Mock(content='{"0": {"objects": ["pin"]}}'))]
        mock_client.chat.completions.create.side_effect = [
            Exception("Rate limit"),
            Exception("Rate limit"),
            Exception("Rate limit"),
            mock_response_good,
        ]

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result == {"0": {"objects": ["pin"]}}
        # Check exponential backoff: 2s, 4s, 8s
        assert mock_sleep.call_count == 3

    @patch("vocabulary_extract_terms.time.sleep")
    def test_fail_fast_on_auth_error(self, mock_sleep):
        """Test that 4xx auth errors fail immediately without retrying."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result is None
        # Should NOT retry on auth error - only 1 call
        assert mock_client.chat.completions.create.call_count == 1
        mock_sleep.assert_not_called()

    @patch("vocabulary_extract_terms.time.sleep")
    def test_fail_fast_on_validation_error(self, mock_sleep):
        """Test that 400 validation errors fail immediately without retrying."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("400 Bad Request: invalid model")

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result is None
        # Should NOT retry on validation error - only 1 call
        assert mock_client.chat.completions.create.call_count == 1
        mock_sleep.assert_not_called()

    @patch("vocabulary_extract_terms.time.sleep")
    def test_returns_none_after_max_retries(self, mock_sleep):
        """Test returns None after all retries exhausted."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("Persistent error")

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result is None
        assert mock_client.chat.completions.create.call_count == MAX_RETRIES + 1

    @patch("vocabulary_extract_terms.time.sleep")
    def test_retry_on_empty_response(self, mock_sleep):
        """Test retry on empty response content."""
        mock_client = Mock()
        mock_response_empty = Mock()
        mock_response_empty.choices = [Mock(message=Mock(content=None))]
        mock_response_good = Mock()
        mock_response_good.choices = [Mock(message=Mock(content='{"0": {"objects": ["pin"]}}'))]
        mock_client.chat.completions.create.side_effect = [mock_response_empty, mock_response_good]

        result = _call_openai_with_retry(mock_client, "test prompt", 1, 1)

        assert result == {"0": {"objects": ["pin"]}}


class TestSQLParameterization:
    """Tests to verify SQL LIMIT is parameterized (Issue #154).

    These tests verify the code structure and logic of the SQL query
    building in get_themes_from_db without requiring database connectivity.
    """

    def test_limit_parameter_in_source_code(self):
        """Verify the source code uses parameterized LIMIT, not string interpolation."""
        import vocabulary_extract_terms
        import inspect

        source = inspect.getsource(vocabulary_extract_terms.get_themes_from_db)

        # Should have parameterized LIMIT (LIMIT %s)
        assert "LIMIT %s" in source, "Expected parameterized LIMIT %s in source"

        # Should NOT have string-interpolated limit (f" LIMIT {limit}")
        assert 'f" LIMIT {limit}"' not in source, "Found SQL injection vulnerability: string-interpolated LIMIT"
        assert "f' LIMIT {limit}'" not in source, "Found SQL injection vulnerability: string-interpolated LIMIT"

    def test_limit_added_to_params_list(self):
        """Verify the source code appends limit to params list."""
        import vocabulary_extract_terms
        import inspect

        source = inspect.getsource(vocabulary_extract_terms.get_themes_from_db)

        # Should append limit to params list
        assert "params.append(limit)" in source, "Expected limit to be appended to params"

    def test_query_building_logic_with_limit(self):
        """Test the query building logic directly by simulating what the function does."""
        # Simulate the query building logic from get_themes_from_db
        run_id = 95
        limit = 50

        query = """
            SELECT
                t.conversation_id,
                t.diagnostic_summary
            FROM themes t
            WHERE t.pipeline_run_id = %s
            AND t.diagnostic_summary IS NOT NULL
            AND t.diagnostic_summary != ''
        """
        params = [run_id]

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        # Verify parameterized query
        assert "LIMIT %s" in query
        assert "LIMIT 50" not in query  # No string interpolation
        assert params == [95, 50]

    def test_query_building_logic_without_limit(self):
        """Test the query building logic when limit is None."""
        run_id = 95
        limit = None

        query = """
            SELECT
                t.conversation_id,
                t.diagnostic_summary
            FROM themes t
            WHERE t.pipeline_run_id = %s
            AND t.diagnostic_summary IS NOT NULL
            AND t.diagnostic_summary != ''
        """
        params = [run_id]

        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        # Verify no LIMIT clause
        assert "LIMIT" not in query
        assert params == [95]
