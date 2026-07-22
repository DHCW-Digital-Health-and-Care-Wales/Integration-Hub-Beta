"""Unit tests for dashboard.services.email_service.

Covers:
  - Key Vault fetch path (cached, TTL-based)
  - Fallback to ACS_CONNECTION_STRING env var when Key Vault is not configured
  - Fallback to env var when a Key Vault fetch fails
  - send_alert_email() guard conditions (disabled, missing config) and success/failure paths
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dashboard.services import email_service


class TestGetAcsConnectionString:
    def setup_method(self) -> None:
        """Reset the module-level secret cache before every test."""
        email_service._secret_cache = None
        email_service._secret_cache_expiry = 0.0

    def test_no_key_vault_url_falls_back_to_env_var(self) -> None:
        with (
            patch.object(email_service.config, "AZURE_KEY_VAULT_URL", ""),
            patch.object(email_service.config, "ACS_CONNECTION_STRING", "endpoint=env-fallback"),
        ):
            assert email_service.get_acs_connection_string() == "endpoint=env-fallback"

    def test_key_vault_fetch_success_is_cached(self) -> None:
        mock_secret = MagicMock(value="endpoint=from-key-vault")
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        with (
            patch.object(email_service.config, "AZURE_KEY_VAULT_URL", "https://kv.vault.azure.net/"),
            patch.object(email_service.config, "ACS_EMAIL_SECRET_NAME", "acs-email-connection-string"),
            patch.object(email_service.config, "ACS_SECRET_CACHE_TTL", 3600),
            patch("azure.keyvault.secrets.SecretClient", return_value=mock_client),
        ):
            first = email_service.get_acs_connection_string()
            second = email_service.get_acs_connection_string()

        assert first == "endpoint=from-key-vault"
        assert second == "endpoint=from-key-vault"
        # Key Vault should only be hit once — second call served from cache.
        mock_client.get_secret.assert_called_once_with("acs-email-connection-string")

    def test_key_vault_fetch_failure_falls_back_to_env_var(self) -> None:
        with (
            patch.object(email_service.config, "AZURE_KEY_VAULT_URL", "https://kv.vault.azure.net/"),
            patch.object(email_service.config, "ACS_CONNECTION_STRING", "endpoint=env-fallback"),
            patch("azure.keyvault.secrets.SecretClient", side_effect=Exception("boom")),
        ):
            assert email_service.get_acs_connection_string() == "endpoint=env-fallback"

    def test_expired_cache_triggers_refetch(self) -> None:
        mock_secret = MagicMock(value="endpoint=refreshed")
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        with (
            patch.object(email_service.config, "AZURE_KEY_VAULT_URL", "https://kv.vault.azure.net/"),
            patch.object(email_service.config, "ACS_SECRET_CACHE_TTL", 3600),
            patch("azure.keyvault.secrets.SecretClient", return_value=mock_client),
        ):
            email_service._secret_cache = "endpoint=stale"
            email_service._secret_cache_expiry = 0.0  # already expired
            result = email_service.get_acs_connection_string()

        assert result == "endpoint=refreshed"
        mock_client.get_secret.assert_called_once()


class TestSendAlertEmail:
    def test_returns_false_when_alert_email_disabled(self) -> None:
        with patch.object(email_service.config, "ALERT_EMAIL_ENABLED", False):
            assert email_service.send_alert_email("subject", "<p>body</p>") is False

    def test_returns_false_when_connection_string_missing(self) -> None:
        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "from@example.com"),
            patch.object(email_service, "get_acs_connection_string", return_value=""),
        ):
            assert email_service.send_alert_email("subject", "<p>body</p>") is False

    def test_returns_false_when_recipient_missing(self) -> None:
        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", ""),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "from@example.com"),
            patch.object(email_service, "get_acs_connection_string", return_value="endpoint=x"),
        ):
            assert email_service.send_alert_email("subject", "<p>body</p>") is False

    def test_sends_successfully_with_expected_message_payload(self) -> None:
        mock_poller = MagicMock()
        mock_poller.result.return_value = {"id": "msg-123"}
        mock_client = MagicMock()
        mock_client.begin_send.return_value = mock_poller

        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "donotreply@guid.azurecomm.net"),
            patch.object(email_service, "get_acs_connection_string", return_value="endpoint=x"),
            patch("azure.communication.email.EmailClient.from_connection_string", return_value=mock_client),
        ):
            result = email_service.send_alert_email("Test Subject", "<p>Test Body</p>")

        assert result is True
        mock_client.begin_send.assert_called_once_with(
            {
                "senderAddress": "donotreply@guid.azurecomm.net",
                "recipients": {"to": [{"address": "to@example.com"}]},
                "content": {"subject": "Test Subject", "html": "<p>Test Body</p>"},
            }
        )

    def test_returns_false_and_logs_on_send_exception(self) -> None:
        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "from@example.com"),
            patch.object(email_service, "get_acs_connection_string", return_value="endpoint=x"),
            patch(
                "azure.communication.email.EmailClient.from_connection_string",
                side_effect=Exception("network error"),
            ),
        ):
            result = email_service.send_alert_email("subject", "<p>body</p>")

        assert result is False


class TestSendAlertEmailRetry:
    """Covers retry-with-backoff on ACS 429 (TooManyRequests) responses."""

    def _throttling_error(self, retry_after: str | None = None) -> Exception:
        exc = Exception("(TooManyRequests) Please try again after 0 seconds.")
        exc.status_code = 429  # type: ignore[attr-defined]
        if retry_after is not None:
            response = MagicMock()
            response.status_code = 429
            response.headers = {"Retry-After": retry_after}
            exc.response = response  # type: ignore[attr-defined]
        return exc

    def test_retries_on_429_and_succeeds(self) -> None:
        mock_poller = MagicMock()
        mock_poller.result.return_value = {"id": "msg-123"}
        mock_client = MagicMock()
        mock_client.begin_send.side_effect = [self._throttling_error("0"), mock_poller]

        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "from@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_MAX_RETRIES", 3),
            patch.object(email_service, "get_acs_connection_string", return_value="endpoint=x"),
            patch("azure.communication.email.EmailClient.from_connection_string", return_value=mock_client),
            patch("dashboard.services.email_service.time.sleep") as mock_sleep,
        ):
            result = email_service.send_alert_email("subject", "<p>body</p>")

        assert result is True
        assert mock_client.begin_send.call_count == 2
        mock_sleep.assert_called_once_with(0.0)

    def test_gives_up_after_max_retries_on_persistent_429(self) -> None:
        mock_client = MagicMock()
        mock_client.begin_send.side_effect = self._throttling_error("1")

        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "from@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_MAX_RETRIES", 2),
            patch.object(email_service, "get_acs_connection_string", return_value="endpoint=x"),
            patch("azure.communication.email.EmailClient.from_connection_string", return_value=mock_client),
            patch("dashboard.services.email_service.time.sleep") as mock_sleep,
        ):
            result = email_service.send_alert_email("subject", "<p>body</p>")

        assert result is False
        # Initial attempt + 2 retries = 3 calls total.
        assert mock_client.begin_send.call_count == 3
        assert mock_sleep.call_count == 2

    def test_non_throttling_error_does_not_retry(self) -> None:
        mock_client = MagicMock()
        mock_client.begin_send.side_effect = Exception("some other ACS error")

        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "from@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_MAX_RETRIES", 3),
            patch.object(email_service, "get_acs_connection_string", return_value="endpoint=x"),
            patch("azure.communication.email.EmailClient.from_connection_string", return_value=mock_client),
            patch("dashboard.services.email_service.time.sleep") as mock_sleep,
        ):
            result = email_service.send_alert_email("subject", "<p>body</p>")

        assert result is False
        mock_client.begin_send.assert_called_once()
        mock_sleep.assert_not_called()

    def test_falls_back_to_exponential_backoff_without_retry_after_header(self) -> None:
        mock_poller = MagicMock()
        mock_poller.result.return_value = {"id": "msg-123"}
        mock_client = MagicMock()
        # No Retry-After header this time — exponential backoff should be used instead.
        mock_client.begin_send.side_effect = [self._throttling_error(), mock_poller]

        with (
            patch.object(email_service.config, "ALERT_EMAIL_ENABLED", True),
            patch.object(email_service.config, "ALERT_EMAIL_TO", "to@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_FROM", "from@example.com"),
            patch.object(email_service.config, "ALERT_EMAIL_MAX_RETRIES", 3),
            patch.object(email_service.config, "ALERT_EMAIL_RETRY_BACKOFF_SECONDS", 2.0),
            patch.object(email_service, "get_acs_connection_string", return_value="endpoint=x"),
            patch("azure.communication.email.EmailClient.from_connection_string", return_value=mock_client),
            patch("dashboard.services.email_service.time.sleep") as mock_sleep,
        ):
            result = email_service.send_alert_email("subject", "<p>body</p>")

        assert result is True
        mock_sleep.assert_called_once_with(2.0)  # 2.0 * 2**0
