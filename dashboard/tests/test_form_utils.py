"""
Unit tests for dashboard.services.form_utils.

Covers the parse_int_form_field helper, extracted from the previously
duplicated ``_int`` closures in app.py's alarm config routes.
"""

from __future__ import annotations

from werkzeug.datastructures import ImmutableMultiDict

from dashboard.services.form_utils import parse_int_form_field


class TestParseIntFormField:
    def test_returns_submitted_value_when_valid(self) -> None:
        form = ImmutableMultiDict({"gap": "30"})
        assert parse_int_form_field(form, "gap", 60) == 30

    def test_returns_default_when_field_missing(self) -> None:
        form = ImmutableMultiDict({})
        assert parse_int_form_field(form, "gap", 60) == 60

    def test_returns_default_when_value_not_an_integer(self) -> None:
        form = ImmutableMultiDict({"gap": "not-a-number"})
        assert parse_int_form_field(form, "gap", 60) == 60

    def test_clamps_to_default_minimum_of_one(self) -> None:
        form = ImmutableMultiDict({"gap": "0"})
        assert parse_int_form_field(form, "gap", 60) == 1

    def test_clamps_to_explicit_minimum(self) -> None:
        form = ImmutableMultiDict({"threshold": "-5"})
        assert parse_int_form_field(form, "threshold", 1, minimum=0) == 0

    def test_allows_zero_when_minimum_is_zero(self) -> None:
        form = ImmutableMultiDict({"threshold": "0"})
        assert parse_int_form_field(form, "threshold", 60, minimum=0) == 0
