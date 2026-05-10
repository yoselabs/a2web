"""Duration parsing for `a2web logs tail --since=...`."""

from __future__ import annotations

from datetime import timedelta

import pytest

from a2web.utils.duration import parse_duration


def test_seconds() -> None:
    assert parse_duration("30s") == timedelta(seconds=30)


def test_minutes() -> None:
    assert parse_duration("15m") == timedelta(minutes=15)


def test_hours() -> None:
    assert parse_duration("1h") == timedelta(hours=1)


def test_days() -> None:
    assert parse_duration("7d") == timedelta(days=7)


def test_case_insensitive() -> None:
    assert parse_duration("1H") == timedelta(hours=1)


def test_whitespace_tolerated() -> None:
    assert parse_duration("  30 m  ") == timedelta(minutes=30)


def test_invalid_unit() -> None:
    with pytest.raises(ValueError, match="Invalid duration"):
        parse_duration("1y")


def test_no_unit() -> None:
    with pytest.raises(ValueError):
        parse_duration("30")


def test_empty() -> None:
    with pytest.raises(ValueError):
        parse_duration("")
