"""Entra (Azure AD) access-token acquisition for PostgreSQL authentication.

Azure Database for PostgreSQL Flexible Server accepts an Entra access token in place
of a password. Unlike the SQL Server ODBC driver — which handled Managed Identity
internally via ``Authentication=ActiveDirectoryMsi`` — psycopg has no equivalent, so
the token must be fetched explicitly and supplied as the connection password.

Tokens are short-lived, so a fresh one is acquired on every connect rather than being
cached; connections are long-lived and only re-established on failure, so this is
infrequent.
"""

import logging

from azure.identity import ManagedIdentityCredential

logger = logging.getLogger(__name__)

# Resource scope for Azure Database for PostgreSQL Flexible Server Entra authentication.
POSTGRES_AAD_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def fetch_entra_access_token(managed_identity_client_id: str | None = None) -> str:
    """Acquire an Entra access token to use as the PostgreSQL connection password.

    Args:
        managed_identity_client_id: Client ID of a user-assigned Managed Identity.
            When ``None``, the system-assigned identity is used.

    Returns:
        The raw access token string.

    Raises:
        azure.core.exceptions.ClientAuthenticationError: If a token cannot be acquired.
    """
    if managed_identity_client_id:
        credential = ManagedIdentityCredential(client_id=managed_identity_client_id)
    else:
        credential = ManagedIdentityCredential()

    logger.debug("Acquiring Entra access token for PostgreSQL")
    return credential.get_token(POSTGRES_AAD_SCOPE).token


__all__ = ["fetch_entra_access_token", "POSTGRES_AAD_SCOPE"]
