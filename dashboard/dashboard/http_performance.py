"""HTTP-level performance settings: response compression and static asset caching.

Static URLs get a ``?v=<mtime>`` fingerprint so they can be cached for a year; the
fingerprint changes whenever the file does (the image build sets the mtime), so a
deploy never serves stale CSS/JS.
"""

from __future__ import annotations

import os
from typing import Any

from flask import Flask, Response, request
from flask_compress import Compress
from werkzeug.security import safe_join

# Fingerprinted URLs never change content for a given ?v=, so they are safe to mark immutable.
_FINGERPRINTED_CACHE_CONTROL = "public, max-age=31536000, immutable"
# Un-fingerprinted static URLs (e.g. fonts referenced from CSS) keep a short cache.
_DEFAULT_STATIC_CACHE_CONTROL = "public, max-age=3600"


def _asset_version(app: Flask, filename: str, cache: dict[str, str]) -> str | None:
    """Return a short fingerprint for a static file, or None if it cannot be resolved."""
    if filename in cache:
        return cache[filename]
    if not app.static_folder:
        return None
    path = safe_join(app.static_folder, filename)
    if path is None or not os.path.isfile(path):
        return None
    version = str(int(os.path.getmtime(path)))
    cache[filename] = version
    return version


def register(app: Flask) -> None:
    """Enable response compression and fingerprinted, long-lived static asset caching."""
    Compress(app)

    version_cache: dict[str, str] = {}

    @app.url_defaults
    def _add_asset_version(endpoint: str, values: dict[str, Any]) -> None:
        if endpoint != "static" or "v" in values:
            return
        filename = values.get("filename")
        if not isinstance(filename, str):
            return
        version = _asset_version(app, filename, version_cache)
        if version:
            values["v"] = version

    @app.after_request
    def _static_cache_headers(response: Response) -> Response:
        if request.endpoint != "static" or response.status_code not in (200, 304):
            return response
        if "v" in request.args:
            response.headers["Cache-Control"] = _FINGERPRINTED_CACHE_CONTROL
        else:
            response.headers["Cache-Control"] = _DEFAULT_STATIC_CACHE_CONTROL
        return response
