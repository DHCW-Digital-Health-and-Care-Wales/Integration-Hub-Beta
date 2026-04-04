"""Tests for BusWatch FastAPI routes."""

from __future__ import annotations

from buswatch import main


def test_clear_queue_route_redirects_with_success(monkeypatch) -> None:
    monkeypatch.setattr(main.reader, "clear_queue", lambda queue_name: 4)
    main.queue_cache["training-queue"] = {"name": "training-queue"}

    response = main.clear_queue("training-queue")

    assert response.status_code == 303
    assert response.headers["location"] == "/?refresh_queue=training-queue&cleared_queue=training-queue&cleared_count=4"
    assert "training-queue" not in main.queue_cache


def test_clear_queue_route_redirects_with_error(monkeypatch) -> None:
    def raise_clear_error(queue_name: str) -> int:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(main.reader, "clear_queue", raise_clear_error)

    response = main.clear_queue("training-queue")

    assert response.status_code == 303
    assert response.headers["location"] == "/?refresh_queue=training-queue&cleared_queue=training-queue&clear_error=broker+unavailable"