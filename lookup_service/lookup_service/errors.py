from __future__ import annotations


class LookupServiceError(Exception):
    """Base for errors that map to an HTTP response with a consistent JSON body."""

    status_code = 500
    error_code = "internal_error"

    def __init__(self, detail: str, table: str | None = None, errors: list[str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.table = table
        self.errors = errors


class TableNotFoundError(LookupServiceError):
    status_code = 404
    error_code = "table_not_found"


class KeyNotFoundError(LookupServiceError):
    status_code = 404
    error_code = "key_not_found"


class InvalidKeyError(LookupServiceError):
    status_code = 422
    error_code = "invalid_key"


class InvalidUploadError(LookupServiceError):
    status_code = 422
    error_code = "invalid_upload"


class UploadTooLargeError(LookupServiceError):
    status_code = 413
    error_code = "upload_too_large"


class WritesDisabledError(LookupServiceError):
    status_code = 403
    error_code = "writes_disabled"


class ReadOnlyStoreError(LookupServiceError):
    status_code = 409
    error_code = "read_only"


class BackendUnavailableError(LookupServiceError):
    status_code = 503
    error_code = "backend_unavailable"


class StoreNotReadyError(LookupServiceError):
    status_code = 503
    error_code = "not_ready"


class SeedDataError(Exception):
    """Seed data or manifest is invalid; raised at startup so a bad image never serves."""
