"""
Unit tests for Azure credential selection.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

from dashboard.services import credentials


@pytest.fixture(autouse=True)
def _fresh_credential_cache() -> Iterator[None]:
    credentials._reset_credential_for_tests()
    yield
    credentials._reset_credential_for_tests()


class TestAzureCredentialSelection:
    def test_uses_default_credential_when_service_principal_not_configured(self) -> None:
        with (
            patch("dashboard.services.credentials.DefaultAzureCredential") as default_cls,
            patch("dashboard.services.credentials.ClientSecretCredential") as client_secret_cls,
            patch("dashboard.services.credentials.ChainedTokenCredential") as chained_cls,
            patch.object(credentials.config, "AZURE_TENANT_ID", ""),
            patch.object(credentials.config, "AZURE_CLIENT_ID", ""),
            patch.object(credentials.config, "AZURE_CLIENT_SECRET", ""),
        ):
            default_instance = object()
            default_cls.return_value = default_instance

            result = credentials.get_azure_credential()

            assert result is default_instance
            assert credentials.get_azure_credential() is default_instance
            default_cls.assert_called_once()
            client_secret_cls.assert_not_called()
            chained_cls.assert_not_called()

    def test_uses_chained_credential_when_service_principal_is_configured(self) -> None:
        with (
            patch("dashboard.services.credentials.DefaultAzureCredential") as default_cls,
            patch("dashboard.services.credentials.ClientSecretCredential") as client_secret_cls,
            patch("dashboard.services.credentials.ChainedTokenCredential") as chained_cls,
            patch.object(credentials.config, "AZURE_TENANT_ID", "tenant"),
            patch.object(credentials.config, "AZURE_CLIENT_ID", "client"),
            patch.object(credentials.config, "AZURE_CLIENT_SECRET", "secret"),
        ):
            default_instance = object()
            sp_instance = object()
            chained_instance = object()
            default_cls.return_value = default_instance
            client_secret_cls.return_value = sp_instance
            chained_cls.return_value = chained_instance

            result = credentials.get_azure_credential()

            assert result is chained_instance
            client_secret_cls.assert_called_once_with(
                tenant_id="tenant",
                client_id="client",
                client_secret="secret",
            )
            chained_cls.assert_called_once_with(default_instance, sp_instance)

    def test_uses_default_credential_when_service_principal_is_partially_configured(self) -> None:
        with (
            patch("dashboard.services.credentials.DefaultAzureCredential") as default_cls,
            patch("dashboard.services.credentials.ClientSecretCredential") as client_secret_cls,
            patch("dashboard.services.credentials.ChainedTokenCredential") as chained_cls,
            patch.object(credentials.config, "AZURE_TENANT_ID", "tenant"),
            patch.object(credentials.config, "AZURE_CLIENT_ID", "client"),
            patch.object(credentials.config, "AZURE_CLIENT_SECRET", ""),
        ):
            default_instance = object()
            default_cls.return_value = default_instance

            result = credentials.get_azure_credential()

            assert result is default_instance
            client_secret_cls.assert_not_called()
            chained_cls.assert_not_called()
