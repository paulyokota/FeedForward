"""
Intercom Client Retry Logic Tests

Tests for the retry mechanism on transient API errors (5xx).
Run with: pytest tests/test_intercom_retry.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from src.intercom_client import IntercomClient


class TestRetryLogic:
    """Tests for _request_with_retry method."""

    @pytest.fixture
    def client(self):
        """Create client with mocked token."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            return IntercomClient(max_retries=3)

    def test_successful_request_no_retry(self, client):
        """Test that successful requests don't trigger retry."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "success"}

        with patch.object(client.session, "get", return_value=mock_response) as mock_get:
            result = client._get("/test")

        assert result == {"data": "success"}
        assert mock_get.call_count == 1

    def test_retries_on_500_error(self, client):
        """Test retry on 500 Internal Server Error."""
        mock_fail = Mock()
        mock_fail.status_code = 500

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": "recovered"}

        with patch.object(client.session, "get", side_effect=[mock_fail, mock_success]) as mock_get:
            with patch("src.intercom_client.time.sleep"):  # Don't actually sleep in tests
                result = client._get("/test")

        assert result == {"data": "recovered"}
        assert mock_get.call_count == 2

    def test_retries_on_502_error(self, client):
        """Test retry on 502 Bad Gateway."""
        mock_fail = Mock()
        mock_fail.status_code = 502

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": "recovered"}

        with patch.object(client.session, "get", side_effect=[mock_fail, mock_success]) as mock_get:
            with patch("src.intercom_client.time.sleep"):
                result = client._get("/test")

        assert result == {"data": "recovered"}
        assert mock_get.call_count == 2

    def test_retries_on_503_error(self, client):
        """Test retry on 503 Service Unavailable."""
        mock_fail = Mock()
        mock_fail.status_code = 503

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": "recovered"}

        with patch.object(client.session, "get", side_effect=[mock_fail, mock_success]) as mock_get:
            with patch("src.intercom_client.time.sleep"):
                result = client._get("/test")

        assert result == {"data": "recovered"}
        assert mock_get.call_count == 2

    def test_retries_on_504_error(self, client):
        """Test retry on 504 Gateway Timeout."""
        mock_fail = Mock()
        mock_fail.status_code = 504

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": "recovered"}

        with patch.object(client.session, "get", side_effect=[mock_fail, mock_success]) as mock_get:
            with patch("src.intercom_client.time.sleep"):
                result = client._get("/test")

        assert result == {"data": "recovered"}
        assert mock_get.call_count == 2

    def test_no_retry_on_400_error(self, client):
        """Test that 4xx errors are not retried."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.HTTPError("Bad Request")

        with patch.object(client.session, "get", return_value=mock_response) as mock_get:
            with pytest.raises(requests.HTTPError):
                client._get("/test")

        assert mock_get.call_count == 1

    def test_no_retry_on_401_error(self, client):
        """Test that 401 Unauthorized is not retried."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.HTTPError("Unauthorized")

        with patch.object(client.session, "get", return_value=mock_response) as mock_get:
            with pytest.raises(requests.HTTPError):
                client._get("/test")

        assert mock_get.call_count == 1

    def test_exhausts_retries_then_raises(self, client):
        """Test that after max retries, the error is raised."""
        mock_fail = Mock()
        mock_fail.status_code = 500
        mock_fail.raise_for_status.side_effect = requests.HTTPError("Server Error")

        with patch.object(client.session, "get", return_value=mock_fail) as mock_get:
            with patch("src.intercom_client.time.sleep"):
                with pytest.raises(requests.HTTPError):
                    client._get("/test")

        # 1 initial + 3 retries = 4 total attempts
        assert mock_get.call_count == 4

    def test_retries_on_connection_error(self, client):
        """Test retry on connection errors."""
        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": "recovered"}

        with patch.object(
            client.session,
            "get",
            side_effect=[requests.exceptions.ConnectionError("Connection refused"), mock_success]
        ) as mock_get:
            with patch("src.intercom_client.time.sleep"):
                result = client._get("/test")

        assert result == {"data": "recovered"}
        assert mock_get.call_count == 2

    def test_retries_on_timeout_error(self, client):
        """Test retry on timeout errors."""
        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": "recovered"}

        with patch.object(
            client.session,
            "get",
            side_effect=[requests.exceptions.Timeout("Read timed out"), mock_success]
        ) as mock_get:
            with patch("src.intercom_client.time.sleep"):
                result = client._get("/test")

        assert result == {"data": "recovered"}
        assert mock_get.call_count == 2

    def test_exponential_backoff_delays(self, client):
        """Test that retry delays follow exponential backoff."""
        mock_fail = Mock()
        mock_fail.status_code = 500

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"data": "success"}

        sleep_calls = []

        def track_sleep(delay):
            sleep_calls.append(delay)

        with patch.object(
            client.session,
            "get",
            side_effect=[mock_fail, mock_fail, mock_fail, mock_success]
        ):
            with patch("time.sleep", side_effect=track_sleep):
                client._get("/test")

        # Exponential backoff: 2^0 * 2 = 2, 2^1 * 2 = 4, 2^2 * 2 = 8
        # Plus jitter (0-50%), so actual delays are in ranges [2, 3], [4, 6], [8, 12]
        assert len(sleep_calls) == 3
        assert 2 <= sleep_calls[0] <= 3
        assert 4 <= sleep_calls[1] <= 6
        assert 8 <= sleep_calls[2] <= 12

    def test_post_request_with_retry(self, client):
        """Test that POST requests also use retry logic."""
        mock_fail = Mock()
        mock_fail.status_code = 503

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"result": "ok"}

        with patch.object(client.session, "post", side_effect=[mock_fail, mock_success]) as mock_post:
            with patch("src.intercom_client.time.sleep"):
                result = client._post("/search", {"query": "test"})

        assert result == {"result": "ok"}
        assert mock_post.call_count == 2

    def test_custom_max_retries(self):
        """Test that max_retries can be customized."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            client = IntercomClient(max_retries=1)

        mock_fail = Mock()
        mock_fail.status_code = 500
        mock_fail.raise_for_status.side_effect = requests.HTTPError("Server Error")

        with patch.object(client.session, "get", return_value=mock_fail) as mock_get:
            with patch("src.intercom_client.time.sleep"):
                with pytest.raises(requests.HTTPError):
                    client._get("/test")

        # 1 initial + 1 retry = 2 total attempts
        assert mock_get.call_count == 2

    def test_zero_retries_disabled(self):
        """Test that setting max_retries=0 disables retry."""
        with patch.dict("os.environ", {"INTERCOM_ACCESS_TOKEN": "test_token"}):
            client = IntercomClient(max_retries=0)

        mock_fail = Mock()
        mock_fail.status_code = 500
        mock_fail.raise_for_status.side_effect = requests.HTTPError("Server Error")

        with patch.object(client.session, "get", return_value=mock_fail) as mock_get:
            with pytest.raises(requests.HTTPError):
                client._get("/test")

        # Only 1 attempt, no retries
        assert mock_get.call_count == 1
