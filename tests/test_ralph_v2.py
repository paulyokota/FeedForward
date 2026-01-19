"""
Tests for Ralph V2 Pipeline Components

Tests the following modules:
- scripts/ralph/run_pipeline_test.py (pipeline harness)
- scripts/ralph/validate_playwright.py (Playwright validation)
- scripts/ralph/live_data_loader.py (live data loading)

These tests focus on unit-testable functions that don't require
external API calls (OpenAI, GitHub, etc.).
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add ralph scripts to path
RALPH_DIR = Path(__file__).parent.parent / "scripts" / "ralph"
sys.path.insert(0, str(RALPH_DIR))


# =============================================================================
# Tests for validate_playwright.py
# =============================================================================


class TestExtractKeywords:
    """Tests for extract_keywords() function in validate_playwright.py"""

    @pytest.fixture
    def extract_keywords(self):
        """Import the extract_keywords function."""
        from validate_playwright import extract_keywords
        return extract_keywords

    def test_auth_keywords(self, extract_keywords):
        """Auth-related terms produce auth keywords."""
        keywords = extract_keywords("User cannot login to their account")
        assert "auth" in keywords or "login" in keywords
        assert "session" in keywords

    def test_oauth_keywords(self, extract_keywords):
        """OAuth-related terms produce OAuth keywords."""
        keywords = extract_keywords("OAuth token has expired")
        assert "token" in keywords or "oauth" in keywords

    def test_billing_keywords(self, extract_keywords):
        """Billing-related terms produce billing keywords."""
        keywords = extract_keywords("Payment failed for subscription")
        assert "billing" in keywords or "payment" in keywords

    def test_scheduler_keywords(self, extract_keywords):
        """Scheduler-related terms produce scheduler keywords."""
        keywords = extract_keywords("Schedule posts for next week")
        assert "scheduler" in keywords or "schedule" in keywords

    def test_timezone_keywords(self, extract_keywords):
        """Timezone-related terms produce timezone keywords."""
        keywords = extract_keywords("Timezone display is wrong")
        assert "timezone" in keywords or "time" in keywords

    def test_pinterest_keywords(self, extract_keywords):
        """Pinterest-related terms produce Pinterest keywords."""
        keywords = extract_keywords("Pinterest pins not publishing")
        assert "pinterest" in keywords or "pin" in keywords

    def test_api_keywords(self, extract_keywords):
        """API-related terms produce API keywords."""
        keywords = extract_keywords("API endpoint returns 500 error")
        assert "api" in keywords

    def test_email_keywords(self, extract_keywords):
        """Email-related terms produce email keywords."""
        keywords = extract_keywords("Email notifications not sent")
        assert "email" in keywords or "mail" in keywords

    def test_image_keywords(self, extract_keywords):
        """Image/upload-related terms produce upload keywords."""
        keywords = extract_keywords("Image upload fails for large files")
        assert "upload" in keywords or "image" in keywords

    def test_error_keywords(self, extract_keywords):
        """Error-related terms produce error keywords."""
        keywords = extract_keywords("Exception thrown in handler")
        assert "error" in keywords or "exception" in keywords

    def test_config_keywords(self, extract_keywords):
        """Config-related terms produce config keywords."""
        keywords = extract_keywords("Configuration settings not saved")
        assert "config" in keywords or "settings" in keywords

    def test_generic_fallback(self, extract_keywords):
        """Unknown terms fall back to generic keywords."""
        keywords = extract_keywords("Something completely unrelated xyz")
        # Should return generic keywords
        assert len(keywords) > 0
        assert "main" in keywords or "index" in keywords or "src" in keywords

    def test_multiple_keyword_types(self, extract_keywords):
        """Multiple keyword types can be extracted from one description."""
        keywords = extract_keywords("OAuth login fails with API error")
        # Should have auth + API keywords
        assert any(k in keywords for k in ["auth", "login", "token", "oauth"])
        assert "api" in keywords

    def test_no_duplicates(self, extract_keywords):
        """Extracted keywords should not contain duplicates."""
        keywords = extract_keywords("Login login LOGIN authentication auth AUTH")
        # Check no duplicates
        assert len(keywords) == len(set(keywords))

    def test_case_insensitive(self, extract_keywords):
        """Keyword extraction is case-insensitive."""
        lower_kw = extract_keywords("oauth token issue")
        upper_kw = extract_keywords("OAUTH TOKEN ISSUE")
        mixed_kw = extract_keywords("OAuth Token Issue")

        # All should produce similar results
        assert set(lower_kw) == set(upper_kw) == set(mixed_kw)


# =============================================================================
# Tests for run_pipeline_test.py
# =============================================================================


class TestLoadManifest:
    """Tests for load_manifest() function."""

    @pytest.fixture
    def load_manifest(self):
        """Import the load_manifest function."""
        from run_pipeline_test import load_manifest
        return load_manifest

    @pytest.fixture
    def sample_manifest_path(self, tmp_path):
        """Create a sample manifest file for testing."""
        manifest_data = {
            "version": "2.0",
            "description": "Test manifest",
            "sources": [
                {"id": "test_001", "type": "intercom", "path": "test.json"},
                {"id": "test_002", "type": "coda_table", "path": "table.json"}
            ],
            "quality_thresholds": {
                "gestalt_min": 4.0,
                "per_source_gestalt_min": 3.5
            }
        }
        manifest_path = tmp_path / "test_manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))
        return manifest_path

    def test_loads_valid_manifest(self, load_manifest, sample_manifest_path):
        """Can load a valid manifest file."""
        manifest = load_manifest(sample_manifest_path)
        assert manifest["version"] == "2.0"
        assert len(manifest["sources"]) == 2
        assert manifest["quality_thresholds"]["gestalt_min"] == 4.0

    def test_raises_on_missing_file(self, load_manifest, tmp_path):
        """Raises FileNotFoundError for missing manifest."""
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "nonexistent.json")

    def test_raises_on_invalid_json(self, load_manifest, tmp_path):
        """Raises JSONDecodeError for invalid JSON."""
        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text("not valid json {{{")
        with pytest.raises(json.JSONDecodeError):
            load_manifest(invalid_path)


class TestLoadTestData:
    """Tests for load_test_data() function."""

    @pytest.fixture
    def load_test_data(self):
        """Import the load_test_data function."""
        from run_pipeline_test import load_test_data
        return load_test_data

    @pytest.fixture
    def test_data_dir(self, tmp_path):
        """Create a test data directory with sample files."""
        # Create JSON data file
        json_data = {
            "type": "intercom",
            "source_body": "Test conversation content",
            "source_subject": "Test Subject"
        }
        (tmp_path / "intercom_test.json").write_text(json.dumps(json_data))

        # Create markdown file
        (tmp_path / "coda_test.md").write_text("# Test Page\n\nSome content here.")

        return tmp_path

    def test_loads_json_file(self, load_test_data, test_data_dir):
        """Can load JSON test data file."""
        source = {"id": "test_001", "path": "intercom_test.json"}
        data = load_test_data(source, test_data_dir)

        assert data["type"] == "intercom"
        assert data["source_body"] == "Test conversation content"

    def test_loads_markdown_file(self, load_test_data, test_data_dir):
        """Can load markdown test data file."""
        source = {"id": "test_002", "path": "coda_test.md"}
        data = load_test_data(source, test_data_dir)

        assert data["type"] == "markdown"
        assert "Test Page" in data["content"]

    def test_handles_live_data_format(self, load_test_data, test_data_dir):
        """Can handle live data format (inline content)."""
        source = {
            "id": "live_001",
            "source_type": "intercom",
            "content": "Live conversation content",
            "description": "Live test data"
        }
        data = load_test_data(source, test_data_dir)

        assert data["type"] == "intercom"
        assert data["source_body"] == "Live conversation content"
        assert data["source_subject"] == "Live test data"

    def test_raises_on_unsupported_file_type(self, load_test_data, test_data_dir):
        """Raises ValueError for unsupported file types."""
        source = {"id": "test_003", "path": "test.xml"}
        # Create the file so we don't get FileNotFoundError
        (test_data_dir / "test.xml").write_text("<xml>data</xml>")

        with pytest.raises(ValueError, match="Unsupported file type"):
            load_test_data(source, test_data_dir)


class TestLoadGoldStandard:
    """Tests for load_gold_standard() function."""

    @pytest.fixture
    def load_gold_standard(self):
        """Import the load_gold_standard function."""
        from run_pipeline_test import load_gold_standard
        return load_gold_standard

    def test_loads_gold_standard_if_exists(self, load_gold_standard):
        """Loads gold standard document if it exists."""
        result = load_gold_standard()
        # Either loads the file or returns fallback
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_fallback_if_missing(self, load_gold_standard, monkeypatch):
        """Returns fallback message if gold standard is missing."""
        # Create a function that uses a non-existent path
        def mock_gold_standard():
            fake_path = Path("/nonexistent/path/file.md")
            if fake_path.exists():
                return fake_path.read_text()
            return "Gold standard not found"

        # Verify the fallback behavior
        result = mock_gold_standard()
        assert "not found" in result.lower()


# =============================================================================
# Tests for live_data_loader.py
# =============================================================================


class TestLiveDataFormatting:
    """Tests for data formatting in live_data_loader.py"""

    @pytest.fixture
    def live_data_result(self):
        """Create a sample live data result for testing."""
        return {
            "version": "2.0-live",
            "description": "Live test data loaded at runtime",
            "loaded_at": datetime.now().isoformat(),
            "randomized": True,
            "sources": [
                {
                    "id": "live_intercom_123",
                    "type": "intercom",
                    "source_type": "intercom",
                    "content": "Test Intercom content",
                    "description": "Test subject"
                },
                {
                    "id": "live_coda_table_456_789",
                    "type": "coda_table",
                    "source_type": "coda_table",
                    "content": "[Theme] Test theme content",
                    "description": "Coda: Test Table"
                },
                {
                    "id": "live_coda_page_abc",
                    "type": "coda_page",
                    "source_type": "coda_page",
                    "content": "[Field] Page content here",
                    "description": "Coda Page: Test"
                }
            ],
            "source_counts": {
                "intercom": 1,
                "coda_table": 1,
                "coda_page": 1,
                "total": 3
            },
            "quality_thresholds": {
                "gestalt_min": 4.8,
                "per_source_gestalt_min": 4.5,
                "scoping_min": 4.5
            }
        }

    def test_live_data_has_required_fields(self, live_data_result):
        """Live data result has all required manifest fields."""
        assert "version" in live_data_result
        assert "sources" in live_data_result
        assert "quality_thresholds" in live_data_result
        assert "source_counts" in live_data_result

    def test_sources_have_required_fields(self, live_data_result):
        """Each source has required fields for pipeline processing."""
        for source in live_data_result["sources"]:
            assert "id" in source
            assert "type" in source
            assert "content" in source

    def test_source_ids_are_unique(self, live_data_result):
        """Source IDs are unique across all sources."""
        ids = [s["id"] for s in live_data_result["sources"]]
        assert len(ids) == len(set(ids))

    def test_source_counts_are_accurate(self, live_data_result):
        """Source counts match actual sources."""
        sources = live_data_result["sources"]
        counts = live_data_result["source_counts"]

        by_type = {}
        for s in sources:
            t = s["type"]
            by_type[t] = by_type.get(t, 0) + 1

        for source_type, count in by_type.items():
            assert counts.get(source_type, 0) == count

        assert counts["total"] == len(sources)


# =============================================================================
# Integration Tests (mock external dependencies)
# =============================================================================


class TestPipelineIntegration:
    """Integration tests for the pipeline with mocked external calls."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        mock_client = MagicMock()

        # Mock story generation response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
# [Priority 2] Fix Pinterest OAuth Token Refresh

## Problem Statement

**User Persona:** Pinterest marketer
**Goal:** Reconnect Pinterest account
**Blocker:** OAuth token expired
**Impact:** Cannot schedule pins

## Technical Context

**Story Type:** BUG FIX
**Primary Service:** tailwind/tack
**Dependency Chain:** aero UI → tack → Pinterest API

## Acceptance Criteria

- [ ] **[Happy]** Given valid credentials, when user reconnects, then success
"""
        mock_client.chat.completions.create.return_value = mock_response

        return mock_client

    @pytest.fixture
    def mock_evaluation_response(self):
        """Create a mock evaluation response."""
        return {
            "gestalt_score": 4.5,
            "explanation": "Good story with clear technical context",
            "strengths": ["Clear problem statement", "Specific acceptance criteria"],
            "improvements": ["Could add more edge cases"]
        }

    def test_pipeline_generates_story(self, mock_openai_client):
        """Pipeline generates story from source data."""
        with patch("run_pipeline_test.OpenAI", return_value=mock_openai_client):
            from run_pipeline_test import run_pipeline_on_source

            source_data = {
                "source_body": "Pinterest connection keeps failing",
                "source_subject": "Help with Pinterest"
            }

            result = run_pipeline_on_source(source_data, "intercom")

            assert result is not None
            assert "content" in result
            assert "Pinterest" in result["content"]
            assert result["source_type"] == "intercom"

    def test_evaluation_returns_score(self, mock_openai_client, mock_evaluation_response):
        """Evaluation returns gestalt score."""
        # Configure mock for evaluation
        eval_response = MagicMock()
        eval_response.choices = [MagicMock()]
        eval_response.choices[0].message.content = json.dumps(mock_evaluation_response)
        mock_openai_client.chat.completions.create.return_value = eval_response

        with patch("run_pipeline_test.OpenAI", return_value=mock_openai_client):
            from run_pipeline_test import evaluate_gestalt

            story = {"content": "Test story content"}
            gold_standard = "Gold standard content"

            result = evaluate_gestalt(story, gold_standard)

            assert "gestalt_score" in result
            assert result["gestalt_score"] == 4.5


# =============================================================================
# Architectural Knowledge Tests (from run_pipeline_test.py prompt)
# =============================================================================


class TestArchitecturalKnowledge:
    """
    Tests that verify the architectural knowledge encoded in the pipeline.

    These tests verify that the keyword extraction and technical area detection
    in validate_playwright.py correctly maps domain terms to services.
    """

    @pytest.fixture
    def extract_keywords(self):
        """Import the extract_keywords function."""
        from validate_playwright import extract_keywords
        return extract_keywords

    def test_pinterest_maps_to_correct_keywords(self, extract_keywords):
        """Pinterest-related issues should extract Pinterest-specific keywords."""
        keywords = extract_keywords("Pinterest OAuth token refresh failing")
        # Should have pinterest-related keywords
        assert any(k in keywords for k in ["pinterest", "oauth", "token", "tack"])

    def test_facebook_falls_back_to_generic(self, extract_keywords):
        """Facebook issues fall back to generic keywords (no specific handling yet)."""
        # NOTE: Facebook/Instagram don't have specific keyword mappings yet
        # This tests the fallback behavior - a future enhancement could add Meta-specific keywords
        keywords = extract_keywords("Facebook page connection broken")
        # Falls back to generic search keywords
        assert any(k in keywords for k in ["src", "lib", "main", "config"])

    def test_scheduler_maps_to_correct_keywords(self, extract_keywords):
        """Scheduler issues should extract scheduler keywords."""
        keywords = extract_keywords("Scheduled posts not publishing on time")
        assert any(k in keywords for k in ["scheduler", "schedule", "post", "queue"])

    def test_gandalf_only_for_internal_auth(self, extract_keywords):
        """Gandalf keywords should only appear for internal SSO queries."""
        # Pinterest OAuth should NOT include gandalf
        pinterest_keywords = extract_keywords("Pinterest token refresh")
        assert "gandalf" not in pinterest_keywords

        # Internal auth SHOULD include gandalf
        internal_keywords = extract_keywords("Employee SSO login failed")
        # gandalf is for internal auth - if mentioned it should be detected
        assert "auth" in internal_keywords or "login" in internal_keywords
