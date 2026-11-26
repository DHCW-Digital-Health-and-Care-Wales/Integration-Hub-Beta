"""Unit tests for dashboard.http_performance (compression and static asset caching)."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from flask import Flask, jsonify, render_template_string, url_for
from flask.testing import FlaskClient

from dashboard import http_performance


@pytest.fixture()
def static_dir(tmp_path: Path) -> Path:
    static = tmp_path / "static"
    (static / "js").mkdir(parents=True)
    (static / "js" / "app.js").write_text("console.log('hi');\n" * 100)
    return static


@pytest.fixture()
def client(static_dir: Path) -> Generator[FlaskClient, None, None]:
    flask_app = Flask(__name__, static_folder=str(static_dir))
    http_performance.register(flask_app)

    @flask_app.route("/big")
    def big():  # type: ignore[no-untyped-def]
        return jsonify({"items": ["x" * 50] * 200})

    @flask_app.route("/page")
    def page() -> str:
        return render_template_string("{{ url_for('static', filename='js/app.js') }}")

    with flask_app.test_client() as c:
        yield c


class TestStaticFingerprinting:
    def test_static_url_gets_version_param(self, client: FlaskClient) -> None:
        body = client.get("/page").get_data(as_text=True)
        assert body.startswith("/static/js/app.js?v=")

    def test_editing_a_file_changes_its_fingerprint_in_debug_mode(
        self, client: FlaskClient, static_dir: Path
    ) -> None:
        client.application.debug = True
        before = client.get("/page").get_data(as_text=True)
        asset = static_dir / "js" / "app.js"
        stat = asset.stat()
        os.utime(asset, (stat.st_atime, stat.st_mtime + 100))
        assert client.get("/page").get_data(as_text=True) != before

    def test_non_debug_caches_asset_version_without_restatting(self, client: FlaskClient) -> None:
        from unittest.mock import patch  # noqa: PLC0415

        assert not client.application.debug
        with patch("dashboard.http_performance.os.path.getmtime", wraps=os.path.getmtime) as mock_getmtime:
            first = client.get("/page").get_data(as_text=True)
            second = client.get("/page").get_data(as_text=True)

        assert first == second
        mock_getmtime.assert_called_once()

    def test_missing_file_is_not_fingerprinted(self, client: FlaskClient) -> None:
        with client.application.test_request_context():
            assert url_for("static", filename="js/missing.js") == "/static/js/missing.js"

    def test_path_traversal_filename_is_not_fingerprinted(self, client: FlaskClient) -> None:
        with client.application.test_request_context():
            assert "v=" not in url_for("static", filename="../secret.txt")


class TestStaticCacheHeaders:
    def test_fingerprinted_asset_is_cached_for_a_year(self, client: FlaskClient) -> None:
        url = client.get("/page").get_data(as_text=True)
        cache_control = client.get(url).headers["Cache-Control"]
        assert "max-age=31536000" in cache_control
        assert "immutable" in cache_control

    def test_unversioned_asset_gets_short_cache(self, client: FlaskClient) -> None:
        assert client.get("/static/js/app.js").headers["Cache-Control"] == "public, max-age=3600"

    def test_non_static_responses_are_untouched(self, client: FlaskClient) -> None:
        assert "immutable" not in client.get("/big").headers.get("Cache-Control", "")


class TestCompression:
    def test_large_json_is_compressed_when_client_accepts_gzip(self, client: FlaskClient) -> None:
        response = client.get("/big", headers={"Accept-Encoding": "gzip"})
        assert response.headers["Content-Encoding"] == "gzip"

    def test_no_compression_without_accept_encoding(self, client: FlaskClient) -> None:
        response = client.get("/big", headers={"Accept-Encoding": "identity"})
        assert "Content-Encoding" not in response.headers
