"""
Azure credential helpers for dashboard services.

Authentication order is:
1. DefaultAzureCredential (Managed Identity, Azure CLI, etc.)
2. ClientSecretCredential (when service principal env vars are configured)
"""
from __future__ import annotations

from azure.core.credentials import TokenCredential
from azure.identity import ChainedTokenCredential, ClientSecretCredential, DefaultAzureCredential

from dashboard import config


def _service_principal_configured() -> bool:
    return all(
        [
            config.AZURE_TENANT_ID,
            config.AZURE_CLIENT_ID,
            config.AZURE_CLIENT_SECRET,
        ]
    )


def get_azure_credential() -> TokenCredential:
    """
    Build an Azure credential with a safe fallback chain.

    DefaultAzureCredential is attempted first. If service principal values are
    configured, ClientSecretCredential is chained as a fallback.
    """
    default_credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)

    if not _service_principal_configured():
        return default_credential

    service_principal_credential = ClientSecretCredential(
        tenant_id=config.AZURE_TENANT_ID,
        client_id=config.AZURE_CLIENT_ID,
        client_secret=config.AZURE_CLIENT_SECRET,
    )
    return ChainedTokenCredential(default_credential, service_principal_credential)
