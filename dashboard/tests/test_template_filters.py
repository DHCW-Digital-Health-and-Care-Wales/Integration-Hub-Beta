"""
Unit tests for dashboard.template_filters — the Jinja2 filters extracted
from dashboard/app.py as the final step of the app.py route/filter split.
"""

from __future__ import annotations

import pytest

from dashboard.template_filters import format_bytes, health_badge


class TestFormatBytes:
    def test_zero_bytes(self) -> None:
        assert format_bytes(0) == "0.0 B"

    def test_bytes_below_1024_stays_in_bytes(self) -> None:
        assert format_bytes(512) == "512.0 B"

    def test_boundary_value_1024_rolls_over_to_kb(self) -> None:
        assert format_bytes(1024) == "1.0 KB"

    def test_value_just_below_1024_boundary_stays_in_bytes(self) -> None:
        assert format_bytes(1023) == "1023.0 B"

    def test_megabytes(self) -> None:
        assert format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self) -> None:
        assert format_bytes(1.4 * 1024 * 1024 * 1024) == "1.4 GB"

    def test_terabytes(self) -> None:
        assert format_bytes(2 * 1024 * 1024 * 1024 * 1024) == "2.0 TB"

    def test_accepts_float_input(self) -> None:
        assert format_bytes(1536.0) == "1.5 KB"


class TestHealthBadge:
    @pytest.mark.parametrize(
        ("health", "expected"),
        [
            ("healthy", "success"),
            ("warning", "warning"),
            ("critical", "danger"),
            ("unknown", "secondary"),
        ],
    )
    def test_known_health_values_map_to_expected_colour(self, health: str, expected: str) -> None:
        assert health_badge(health) == expected

    def test_unrecognised_health_string_defaults_to_secondary(self) -> None:
        assert health_badge("not-a-real-status") == "secondary"

    def test_empty_string_defaults_to_secondary(self) -> None:
        assert health_badge("") == "secondary"
