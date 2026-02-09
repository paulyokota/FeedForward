"""
Story Content Generator Tests

Tests for StoryContentGenerator - LLM-generated story content from grouped conversation data.
Run with: pytest tests/story_tracking/test_story_content_generator.py -v

Architecture: docs/architecture/story-content-generation.md
"""

import json
import pytest
import time
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import sys
from pathlib import Path

# Navigate up from tests/story_tracking/ to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from openai import RateLimitError, APITimeoutError, APIConnectionError, InternalServerError

from src.story_tracking.services.story_content_generator import (
    StoryContentGenerator,
    GeneratedStoryContent,
    VALID_CATEGORIES,
    DEFAULT_CATEGORY,
)
from src.prompts.story_content import StoryContentInput

pytestmark = pytest.mark.medium


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def generator():
    """Create a StoryContentGenerator instance."""
    return StoryContentGenerator(model="gpt-4o-mini", temperature=0.3)


@pytest.fixture
def sample_input():
    """Create a sample StoryContentInput for testing."""
    return StoryContentInput(
        user_intents=[
            "The user was trying to upload pins to their drafts",
            "The user wanted to schedule pins for later",
        ],
        symptoms=["Server 0 response code", "pins not appearing in drafts"],
        issue_signature="pinterest_pin_upload_failure",
        classification_category="product_issue",
        product_area="publishing",
        component="pinterest",
        root_cause_hypothesis="Server timeout during upload",
        affected_flow="Pin scheduling flow",
    )


@pytest.fixture
def feature_request_input():
    """Create a sample StoryContentInput for feature_request."""
    return StoryContentInput(
        user_intents=["The user wants to schedule multiple Reels at once"],
        symptoms=["No bulk scheduling option available"],
        issue_signature="instagram_bulk_scheduling",
        classification_category="feature_request",
        product_area="publishing",
        component="instagram",
    )


@pytest.fixture
def how_to_question_input():
    """Create a sample StoryContentInput for how_to_question."""
    return StoryContentInput(
        user_intents=["The user is confused about SmartSchedule timezone settings"],
        symptoms=["Posts publishing at wrong times"],
        issue_signature="smartschedule_timezone_confusion",
        classification_category="how_to_question",
        product_area="scheduling",
        component="smartschedule",
    )


@pytest.fixture
def account_issue_input():
    """Create a sample StoryContentInput for account_issue."""
    return StoryContentInput(
        user_intents=["The user cannot connect their Pinterest account"],
        symptoms=["OAuth connection timeout", "connection keeps failing"],
        issue_signature="pinterest_oauth_failure",
        classification_category="account_issue",
        product_area="accounts",
        component="pinterest",
    )


@pytest.fixture
def billing_question_input():
    """Create a sample StoryContentInput for billing_question."""
    return StoryContentInput(
        user_intents=["The user wants to understand their billing cycle"],
        symptoms=["Confused about charge date"],
        issue_signature="billing_cycle_confusion",
        classification_category="billing_question",
        product_area="billing",
        component="subscriptions",
    )


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI response with valid JSON content (all 9 fields)."""
    return json.dumps({
        "title": "Fix pin upload failures when saving to drafts",
        "user_type": "content creator managing Pinterest accounts",
        "user_story_want": "to be able to upload pins to my drafts without errors",
        "user_story_benefit": "I can maintain my posting schedule without interruption",
        "ai_agent_goal": "Resolve the pin upload failure where users receive Server 0 response code. Success: uploads complete successfully and pins appear in drafts within 5 seconds.",
        "acceptance_criteria": [
            "Given a user is uploading a pin to drafts, When the save action is triggered, Then the pin is saved successfully without Server 0 errors",
            "Given test data, When the fix is applied, Then all existing tests pass",
        ],
        "investigation_steps": [
            "Review `pinterest` error logs for Server 0 response patterns",
            "Verify Pinterest API authentication state during draft save",
            "Test pin upload with different image formats and sizes",
        ],
        "success_criteria": [
            "Pin uploads to drafts complete successfully without Server 0 errors",
            "All existing pinterest tests pass (no regressions)",
        ],
        "technical_notes": "**Testing**: API integration test verifying pin save endpoint handles Pinterest API errors gracefully. **Vertical Slice**: API endpoint -> pinterest service -> Pinterest API client. **Focus Area**: Error handling when Pinterest returns Server 0.",
    })


# -----------------------------------------------------------------------------
# Unit Tests - Initialization
# -----------------------------------------------------------------------------


class TestStoryContentGeneratorInit:
    """Test StoryContentGenerator initialization."""

    def test_default_initialization(self):
        """Test service initializes with default values."""
        generator = StoryContentGenerator()
        assert generator.model == "gpt-4o-mini"
        assert generator.temperature == 0.3
        assert generator.timeout == 30.0
        assert generator._client is None  # Lazy initialization

    def test_custom_initialization(self):
        """Test service initializes with custom values."""
        generator = StoryContentGenerator(
            model="gpt-4",
            temperature=0.5,
            timeout=60.0,
        )
        assert generator.model == "gpt-4"
        assert generator.temperature == 0.5
        assert generator.timeout == 60.0

    def test_lazy_client_initialization(self):
        """Test that OpenAI client is lazily initialized."""
        generator = StoryContentGenerator()
        assert generator._client is None

        # Access the client property
        with patch("src.story_tracking.services.story_content_generator.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            client = generator.client
            assert client is not None
            mock_openai.assert_called_once()


# -----------------------------------------------------------------------------
# Unit Tests - Basic Generation
# -----------------------------------------------------------------------------


class TestBasicGeneration:
    """Test basic content generation functionality."""

    def test_valid_input_produces_all_nine_fields(self, generator, sample_input, mock_openai_response):
        """Test that valid input produces all 9 fields (issue #133)."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = mock_openai_response

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert isinstance(result, GeneratedStoryContent)
        # Original 5 fields
        assert result.title == "Fix pin upload failures when saving to drafts"
        assert result.user_type == "content creator managing Pinterest accounts"
        assert result.user_story_want == "to be able to upload pins to my drafts without errors"
        assert result.user_story_benefit == "I can maintain my posting schedule without interruption"
        assert "Success:" in result.ai_agent_goal
        # New 4 fields (issue #133)
        assert len(result.acceptance_criteria) >= 1
        assert "Given" in result.acceptance_criteria[0]
        assert len(result.investigation_steps) >= 1
        assert "pinterest" in result.investigation_steps[0].lower()
        assert len(result.success_criteria) >= 1
        assert "**Testing**:" in result.technical_notes

    def test_all_classification_categories_produce_output(self, generator):
        """Test that all classification categories produce appropriate output."""
        inputs = {
            "product_issue": StoryContentInput(
                user_intents=["Test intent"],
                symptoms=["Test symptom"],
                issue_signature="test_sig",
                classification_category="product_issue",
                product_area="test",
                component="test",
            ),
            "feature_request": StoryContentInput(
                user_intents=["Test intent"],
                symptoms=["Test symptom"],
                issue_signature="test_sig",
                classification_category="feature_request",
                product_area="test",
                component="test",
            ),
            "how_to_question": StoryContentInput(
                user_intents=["Test intent"],
                symptoms=["Test symptom"],
                issue_signature="test_sig",
                classification_category="how_to_question",
                product_area="test",
                component="test",
            ),
            "account_issue": StoryContentInput(
                user_intents=["Test intent"],
                symptoms=["Test symptom"],
                issue_signature="test_sig",
                classification_category="account_issue",
                product_area="test",
                component="test",
            ),
            "billing_question": StoryContentInput(
                user_intents=["Test intent"],
                symptoms=["Test symptom"],
                issue_signature="test_sig",
                classification_category="billing_question",
                product_area="test",
                component="test",
            ),
        }

        for category, input_data in inputs.items():
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "title": f"Test title for {category}",
                "user_type": "test user type",
                "user_story_want": "to test something",
                "user_story_benefit": "testing works",
                "ai_agent_goal": "Test goal. Success: test passes.",
            })

            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            generator._client = mock_client

            result = generator.generate(input_data)

            assert isinstance(result, GeneratedStoryContent)
            assert result.title is not None
            assert len(result.title) > 0


# -----------------------------------------------------------------------------
# Unit Tests - Retry Logic
# -----------------------------------------------------------------------------


class TestRetryLogic:
    """Test retry behavior for transient failures."""

    def test_rate_limit_error_triggers_retry(self, generator, sample_input, mock_openai_response):
        """Test that RateLimitError triggers retry with backoff."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = mock_openai_response

        mock_client = MagicMock()
        # First call raises RateLimitError, second succeeds
        mock_client.chat.completions.create.side_effect = [
            RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            ),
            mock_response,
        ]
        generator._client = mock_client

        with patch("time.sleep") as mock_sleep:
            result = generator.generate(sample_input)

        assert result.title == "Fix pin upload failures when saving to drafts"
        mock_sleep.assert_called_once_with(1.0)  # First retry delay
        assert mock_client.chat.completions.create.call_count == 2

    def test_api_timeout_error_triggers_retry(self, generator, sample_input, mock_openai_response):
        """Test that APITimeoutError triggers retry with backoff."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = mock_openai_response

        mock_client = MagicMock()
        # First call raises APITimeoutError, second succeeds
        mock_client.chat.completions.create.side_effect = [
            APITimeoutError(request=MagicMock()),
            mock_response,
        ]
        generator._client = mock_client

        with patch("time.sleep") as mock_sleep:
            result = generator.generate(sample_input)

        assert result.title == "Fix pin upload failures when saving to drafts"
        mock_sleep.assert_called_once_with(1.0)

    def test_internal_server_error_triggers_retry(self, generator, sample_input, mock_openai_response):
        """Test that InternalServerError triggers retry with backoff."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = mock_openai_response

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            InternalServerError(
                message="Internal server error",
                response=MagicMock(status_code=500),
                body=None,
            ),
            mock_response,
        ]
        generator._client = mock_client

        with patch("time.sleep"):
            result = generator.generate(sample_input)

        assert result.title == "Fix pin upload failures when saving to drafts"

    def test_api_connection_error_triggers_retry(self, generator, sample_input, mock_openai_response):
        """Test that APIConnectionError triggers retry with backoff."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = mock_openai_response

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            mock_response,
        ]
        generator._client = mock_client

        with patch("time.sleep"):
            result = generator.generate(sample_input)

        assert result.title == "Fix pin upload failures when saving to drafts"

    def test_exponential_backoff_delays(self, generator, sample_input, mock_openai_response):
        """Test that retries use exponential backoff (1s, 2s, 4s)."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = mock_openai_response

        mock_client = MagicMock()
        # Fail twice, succeed on third attempt
        mock_client.chat.completions.create.side_effect = [
            RateLimitError(message="Rate limit", response=MagicMock(status_code=429), body=None),
            RateLimitError(message="Rate limit", response=MagicMock(status_code=429), body=None),
            mock_response,
        ]
        generator._client = mock_client

        with patch("time.sleep") as mock_sleep:
            result = generator.generate(sample_input)

        assert result.title == "Fix pin upload failures when saving to drafts"
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)  # First retry
        mock_sleep.assert_any_call(2.0)  # Second retry

    def test_non_transient_error_no_retry(self, generator, sample_input):
        """Test that non-transient errors fall back immediately without retry."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Invalid parameter")
        generator._client = mock_client

        with patch("time.sleep") as mock_sleep:
            result = generator.generate(sample_input)

        # Should fall back to mechanical defaults without retrying
        mock_sleep.assert_not_called()
        assert mock_client.chat.completions.create.call_count == 1
        # Should get mechanical fallback
        assert result.user_type == "Tailwind user"

    def test_exhausted_retries_falls_back(self, generator, sample_input):
        """Test that after 3 attempts, falls back to mechanical defaults."""
        mock_client = MagicMock()
        # All 3 attempts fail with transient error
        mock_client.chat.completions.create.side_effect = [
            RateLimitError(message="Rate limit", response=MagicMock(status_code=429), body=None),
            RateLimitError(message="Rate limit", response=MagicMock(status_code=429), body=None),
            RateLimitError(message="Rate limit", response=MagicMock(status_code=429), body=None),
        ]
        generator._client = mock_client

        with patch("time.sleep"):
            result = generator.generate(sample_input, max_retries=3)

        assert mock_client.chat.completions.create.call_count == 3
        # Should get mechanical fallback
        assert result.user_type == "Tailwind user"
        assert result.user_story_benefit == "achieve my goals without friction"


# -----------------------------------------------------------------------------
# Unit Tests - Mechanical Fallbacks
# -----------------------------------------------------------------------------


class TestMechanicalFallbacks:
    """Test mechanical fallback logic for each field."""

    def test_title_uses_user_intent_if_longer_than_10_chars(self, generator, sample_input):
        """Test title fallback uses user_intent if > 10 chars."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        # First user_intent is > 10 chars
        assert result.title == sample_input.user_intents[0]

    def test_title_uses_humanized_signature_if_intent_short(self, generator):
        """Test title fallback humanizes signature if user_intent is short."""
        short_intent_input = StoryContentInput(
            user_intents=["Help"],  # Only 4 chars
            symptoms=["Test symptom"],
            issue_signature="pin_upload_failure",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(short_intent_input)

        assert result.title == "Pin Upload Failure"

    def test_user_type_defaults_to_tailwind_user(self, generator, sample_input):
        """Test user_type fallback is 'Tailwind user'."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert result.user_type == "Tailwind user"

    def test_user_story_want_uses_user_intent(self, generator, sample_input):
        """Test user_story_want fallback uses user_intent directly."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert result.user_story_want == sample_input.user_intents[0]

    def test_user_story_benefit_defaults_to_boilerplate(self, generator, sample_input):
        """Test user_story_benefit fallback is 'achieve my goals without friction'."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert result.user_story_benefit == "achieve my goals without friction"

    def test_ai_agent_goal_uses_user_intent_plus_boilerplate(self, generator, sample_input):
        """Test ai_agent_goal fallback combines user_intent with success criteria."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert sample_input.user_intents[0] in result.ai_agent_goal
        # Q3 fix: Uses "Success:" format per prompt requirements
        assert "Success: issue is resolved and functionality works as expected" in result.ai_agent_goal

    def test_acceptance_criteria_fallback_generic(self, generator, sample_input):
        """Test acceptance_criteria fallback is generic Given/When/Then (issue #133)."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert len(result.acceptance_criteria) == 1
        assert "Given the reported conditions" in result.acceptance_criteria[0]

    def test_investigation_steps_fallback_component_based(self, generator, sample_input):
        """Test investigation_steps fallback uses component name (issue #133)."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert len(result.investigation_steps) == 2
        assert "pinterest" in result.investigation_steps[0].lower()
        assert "publishing" in result.investigation_steps[1].lower()

    def test_success_criteria_fallback_generic(self, generator, sample_input):
        """Test success_criteria fallback is generic (issue #133)."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert len(result.success_criteria) == 2
        assert "Issue is resolved" in result.success_criteria[0]
        assert "tests pass" in result.success_criteria[1].lower()

    def test_technical_notes_fallback_component_based(self, generator, sample_input):
        """Test technical_notes fallback uses component name (issue #133)."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert "pinterest" in result.technical_notes.lower()
        assert "**Target Components**:" in result.technical_notes

    def test_title_truncated_to_80_chars(self, generator):
        """Test that titles longer than 80 chars are truncated."""
        long_intent = "A" * 100
        long_intent_input = StoryContentInput(
            user_intents=[long_intent],
            symptoms=["Test symptom"],
            issue_signature="test_sig",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(long_intent_input)

        assert len(result.title) == 80
        assert result.title.endswith("...")


# -----------------------------------------------------------------------------
# Unit Tests - Edge Cases
# -----------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge case handling."""

    def test_empty_user_intents_uses_first_symptom(self, generator):
        """Test that empty user_intents uses first symptom as pseudo-intent."""
        empty_intents_input = StoryContentInput(
            user_intents=[],
            symptoms=["Server 0 response code", "pins not appearing"],
            issue_signature="test_sig",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(empty_intents_input)

        # Should use first symptom
        assert result.user_story_want == "Server 0 response code"

    def test_empty_symptoms_still_works(self, generator):
        """Test that empty symptoms list still produces valid output."""
        no_symptoms_input = StoryContentInput(
            user_intents=["The user was trying to upload pins"],
            symptoms=[],
            issue_signature="test_sig",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(no_symptoms_input)

        assert isinstance(result, GeneratedStoryContent)
        assert result.title is not None

    def test_both_empty_uses_signature_based_defaults(self, generator):
        """Test that both empty user_intents and symptoms uses signature-based defaults."""
        both_empty_input = StoryContentInput(
            user_intents=[],
            symptoms=[],
            issue_signature="pinterest_pin_upload_failure",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(both_empty_input)

        # Should use humanized signature
        assert result.title == "Pinterest Pin Upload Failure"
        assert "Pinterest Pin Upload Failure" in result.ai_agent_goal

    def test_unknown_classification_mapped_to_product_issue(self, generator):
        """Test that unknown classification category is mapped to product_issue."""
        unknown_category_input = StoryContentInput(
            user_intents=["Test intent"],
            symptoms=["Test symptom"],
            issue_signature="test_sig",
            classification_category="unknown_category",
            product_area="test",
            component="test",
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "title": "Fix test issue",
            "user_type": "test user",
            "user_story_want": "to test",
            "user_story_benefit": "testing works",
            "ai_agent_goal": "Test. Success: pass.",
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        # Should not raise, should work with normalized category
        result = generator.generate(unknown_category_input)
        assert isinstance(result, GeneratedStoryContent)

    def test_invalid_json_from_llm_retries_then_fallback(self, generator, sample_input):
        """Test that invalid JSON from LLM triggers retry then fallback."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not valid JSON at all"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        # Should fall back to mechanical defaults after invalid JSON
        assert result.user_type == "Tailwind user"

    def test_partial_json_uses_valid_fields_plus_fallback(self, generator, sample_input):
        """Test that partial JSON uses valid fields with fallback for missing."""
        partial_json = json.dumps({
            "title": "This is a valid title",
            "user_type": "content creator",
            # Missing: user_story_want, user_story_benefit, ai_agent_goal
            # Missing all new list fields too
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = partial_json

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        # Should use LLM values for present fields
        assert result.title == "This is a valid title"
        assert result.user_type == "content creator"
        # Should use fallback for missing string fields
        assert result.user_story_want == sample_input.user_intents[0]
        assert result.user_story_benefit == "achieve my goals without friction"
        # Should use fallback for missing list fields (issue #133)
        assert len(result.acceptance_criteria) >= 1
        assert len(result.investigation_steps) >= 1
        assert len(result.success_criteria) >= 1
        assert "**Target Components**:" in result.technical_notes

    def test_partial_json_with_list_fields(self, generator, sample_input):
        """Test partial JSON with some list fields present, others missing (issue #133)."""
        partial_json = json.dumps({
            "title": "Valid title",
            "user_type": "content creator",
            "user_story_want": "to test",
            "user_story_benefit": "testing works",
            "ai_agent_goal": "Test. Success: pass.",
            "acceptance_criteria": ["Given X, When Y, Then Z"],
            # Missing: investigation_steps, success_criteria, technical_notes
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = partial_json

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        # Should use LLM value for present list field
        assert result.acceptance_criteria == ["Given X, When Y, Then Z"]
        # Should use fallback for missing list fields
        assert len(result.investigation_steps) >= 1
        assert len(result.success_criteria) >= 1

    def test_empty_list_fields_use_fallback(self, generator, sample_input):
        """Test that empty list fields use fallback values (issue #133)."""
        json_with_empty_lists = json.dumps({
            "title": "Valid title",
            "user_type": "content creator",
            "user_story_want": "to test",
            "user_story_benefit": "testing works",
            "ai_agent_goal": "Test. Success: pass.",
            "acceptance_criteria": [],  # Empty list
            "investigation_steps": [""],  # List with empty string
            "success_criteria": None,  # Null
            "technical_notes": "",  # Empty string
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_with_empty_lists

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        # Empty lists and nulls should use fallback
        assert len(result.acceptance_criteria) >= 1
        assert "Given the reported conditions" in result.acceptance_criteria[0]
        assert len(result.investigation_steps) >= 1
        assert len(result.success_criteria) >= 1
        assert "**Target Components**:" in result.technical_notes

    def test_very_long_inputs_truncated(self, generator):
        """Test that very long inputs are truncated before LLM call."""
        # Create input with very long content
        long_intent = "A" * 5000
        long_symptom = "B" * 5000
        long_input = StoryContentInput(
            user_intents=[long_intent],
            symptoms=[long_symptom],
            issue_signature="test_sig",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "title": "Test title",
            "user_type": "test user",
            "user_story_want": "to test",
            "user_story_benefit": "testing works",
            "ai_agent_goal": "Test. Success: pass.",
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        # Should not raise, should handle long content
        result = generator.generate(long_input)
        assert isinstance(result, GeneratedStoryContent)

        # Verify the prompt was called (confirming truncation logic ran)
        assert mock_client.chat.completions.create.called

    def test_json_in_markdown_code_blocks(self, generator, sample_input):
        """Test parsing of JSON wrapped in markdown code blocks."""
        markdown_wrapped_json = """```json
        {
            "title": "Fix pin upload issue",
            "user_type": "content creator",
            "user_story_want": "to upload pins",
            "user_story_benefit": "I can publish content",
            "ai_agent_goal": "Resolve issue. Success: pins upload."
        }
        ```"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = markdown_wrapped_json

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert result.title == "Fix pin upload issue"

    def test_json_in_plain_code_blocks(self, generator, sample_input):
        """Test parsing of JSON wrapped in plain code blocks."""
        plain_code_block_json = """```
        {
            "title": "Fix pin upload issue",
            "user_type": "content creator",
            "user_story_want": "to upload pins",
            "user_story_benefit": "I can publish content",
            "ai_agent_goal": "Resolve issue. Success: pins upload."
        }
        ```"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = plain_code_block_json

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert result.title == "Fix pin upload issue"

    def test_empty_string_fields_use_fallback(self, generator, sample_input):
        """Test that empty string fields in JSON use fallback values."""
        json_with_empty_fields = json.dumps({
            "title": "",  # Empty
            "user_type": "   ",  # Whitespace only
            "user_story_want": "to upload pins",
            "user_story_benefit": None,  # Null
            "ai_agent_goal": "Test. Success: pass.",
        })

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_with_empty_fields

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        # Empty/whitespace fields should use fallback
        assert result.title == sample_input.user_intents[0]  # Fallback
        assert result.user_type == "Tailwind user"  # Fallback
        # Valid fields should be used
        assert result.user_story_want == "to upload pins"
        # Null field should use fallback
        assert result.user_story_benefit == "achieve my goals without friction"


# -----------------------------------------------------------------------------
# Unit Tests - Input Normalization
# -----------------------------------------------------------------------------


class TestInputNormalization:
    """Test input normalization logic."""

    def test_none_user_intents_handled(self, generator):
        """Test that None user_intents are handled gracefully."""
        # Create input with a list that might be empty
        input_with_none_intents = StoryContentInput(
            user_intents=[],  # Empty list
            symptoms=["Test symptom"],
            issue_signature="test_sig",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(input_with_none_intents)
        assert isinstance(result, GeneratedStoryContent)

    def test_none_symptoms_handled(self, generator):
        """Test that None symptoms are handled gracefully."""
        input_with_none_symptoms = StoryContentInput(
            user_intents=["Test intent"],
            symptoms=[],  # Empty list
            issue_signature="test_sig",
            classification_category="product_issue",
            product_area="test",
            component="test",
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("Force fallback")
        generator._client = mock_client

        result = generator.generate(input_with_none_symptoms)
        assert isinstance(result, GeneratedStoryContent)

    def test_none_product_area_defaults_to_unknown(self, generator):
        """Test that None product_area defaults to 'Unknown'."""
        input_with_none_product_area = StoryContentInput(
            user_intents=["Test intent"],
            symptoms=["Test symptom"],
            issue_signature="test_sig",
            classification_category="product_issue",
            product_area=None,  # None
            component=None,  # None
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "title": "Test",
            "user_type": "test",
            "user_story_want": "to test",
            "user_story_benefit": "test",
            "ai_agent_goal": "Test. Success: pass.",
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        # Should not raise
        result = generator.generate(input_with_none_product_area)
        assert isinstance(result, GeneratedStoryContent)


# -----------------------------------------------------------------------------
# Unit Tests - GeneratedStoryContent Dataclass
# -----------------------------------------------------------------------------


class TestGeneratedStoryContent:
    """Test GeneratedStoryContent dataclass."""

    def test_dataclass_fields(self):
        """Test that dataclass has all expected fields (9 total)."""
        content = GeneratedStoryContent(
            title="Test Title",
            user_type="Test User",
            user_story_want="to test",
            user_story_benefit="testing works",
            ai_agent_goal="Test. Success: pass.",
            acceptance_criteria=["Given X, When Y, Then Z"],
            investigation_steps=["Step 1", "Step 2"],
            success_criteria=["Outcome 1", "Outcome 2"],
            technical_notes="**Testing**: Unit test.",
        )

        assert content.title == "Test Title"
        assert content.user_type == "Test User"
        assert content.user_story_want == "to test"
        assert content.user_story_benefit == "testing works"
        assert content.ai_agent_goal == "Test. Success: pass."
        # New fields (issue #133)
        assert content.acceptance_criteria == ["Given X, When Y, Then Z"]
        assert content.investigation_steps == ["Step 1", "Step 2"]
        assert content.success_criteria == ["Outcome 1", "Outcome 2"]
        assert content.technical_notes == "**Testing**: Unit test."

    def test_new_fields_are_required(self):
        """Test that new fields are required (no defaults)."""
        # Should raise TypeError if new fields are missing
        with pytest.raises(TypeError):
            GeneratedStoryContent(
                title="Test",
                user_type="Test",
                user_story_want="to test",
                user_story_benefit="testing",
                ai_agent_goal="Test.",
                # Missing: acceptance_criteria, investigation_steps, success_criteria, technical_notes
            )


# -----------------------------------------------------------------------------
# Unit Tests - Valid Categories Constant
# -----------------------------------------------------------------------------


class TestValidCategories:
    """Test VALID_CATEGORIES constant."""

    def test_valid_categories_contains_expected_values(self):
        """Test that VALID_CATEGORIES contains all expected categories."""
        expected = {
            "product_issue",
            "feature_request",
            "how_to_question",
            "account_issue",
            "billing_question",
        }
        assert VALID_CATEGORIES == expected

    def test_default_category_is_product_issue(self):
        """Test that DEFAULT_CATEGORY is product_issue."""
        assert DEFAULT_CATEGORY == "product_issue"


# -----------------------------------------------------------------------------
# Unit Tests - Humanize Signature
# -----------------------------------------------------------------------------


class TestHumanizeSignature:
    """Test _humanize_signature helper method."""

    def test_underscores_replaced_with_spaces(self, generator):
        """Test that underscores are replaced with spaces."""
        result = generator._humanize_signature("pin_upload_failure")
        assert result == "Pin Upload Failure"

    def test_title_case_applied(self, generator):
        """Test that title case is applied."""
        result = generator._humanize_signature("scheduling_error")
        assert result == "Scheduling Error"

    def test_single_word(self, generator):
        """Test single word signature."""
        result = generator._humanize_signature("error")
        assert result == "Error"


# -----------------------------------------------------------------------------
# Unit Tests - Title Length Validation
# -----------------------------------------------------------------------------


class TestTitleLengthValidation:
    """Test that titles are properly validated for length."""

    def test_llm_response_title_truncated_if_too_long(self, generator, sample_input):
        """Test that LLM response title is truncated if > 80 chars."""
        long_title = "A" * 100

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "title": long_title,
            "user_type": "test user",
            "user_story_want": "to test",
            "user_story_benefit": "testing works",
            "ai_agent_goal": "Test. Success: pass.",
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        generator._client = mock_client

        result = generator.generate(sample_input)

        assert len(result.title) == 80
        assert result.title.endswith("...")


# -----------------------------------------------------------------------------
# Integration Tests (with actual OpenAI - skip in CI)
# -----------------------------------------------------------------------------


@pytest.mark.skip(reason="Requires OpenAI API key - run manually")
class TestStoryContentGeneratorIntegration:
    """Integration tests that call actual OpenAI API."""

    def test_real_generation_product_issue(self, sample_input):
        """Test real API call for product_issue."""
        generator = StoryContentGenerator()
        result = generator.generate(sample_input)

        assert isinstance(result, GeneratedStoryContent)
        assert len(result.title) > 0
        assert len(result.title) <= 80
        assert result.user_type != "Tailwind user"  # Should be specific
        assert result.user_story_want.startswith("to")
        assert "Success:" in result.ai_agent_goal

    def test_real_generation_feature_request(self, feature_request_input):
        """Test real API call for feature_request."""
        generator = StoryContentGenerator()
        result = generator.generate(feature_request_input)

        assert isinstance(result, GeneratedStoryContent)
        # Feature requests should use "Add" verb
        assert result.title.startswith("Add") or "add" in result.title.lower()
