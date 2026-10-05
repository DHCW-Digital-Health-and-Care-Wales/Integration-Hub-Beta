from __future__ import annotations

from fastapi import Request

from lookup_service.config import Settings
from lookup_service.errors import StoreNotReadyError
from lookup_service.resolver import LookupResolver


def get_resolver(request: Request) -> LookupResolver:
    resolver: LookupResolver | None = getattr(request.app.state, "resolver", None)
    if resolver is None:
        raise StoreNotReadyError("Lookup tables are not loaded yet")
    return resolver


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
