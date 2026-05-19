"""Models smoke tests — module-scope rule + closed-enum validation."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from a2web.models import (
    CacheState,
    Confidence,
    Diagnostic,
    FetchResponse,
    FetchStatus,
    Heading,
    Link,
    NextLink,
    OperatorHint,
    TokenCounts,
    Verdict,
)


def test_all_types_module_scope_importable() -> None:
    """Every public model is importable from `a2web.models` (antipattern #2)."""
    types = [
        Verdict,
        FetchStatus,
        Confidence,
        CacheState,
        Diagnostic,
        Heading,
        Link,
        OperatorHint,
        TokenCounts,
        FetchResponse,
    ]
    for t in types:
        assert t.__module__ == "a2web.models"


def test_verdict_enum_is_closed() -> None:
    with pytest.raises(ValidationError):
        Diagnostic(t_ms=0, step="raw", verdict="bogus_verdict", dur_ms=0)  # type: ignore[arg-type]


def test_fetch_status_enum_is_closed() -> None:
    from datetime import UTC, datetime

    with pytest.raises(ValidationError):
        FetchResponse(
            url="x",
            status="bogus",  # type: ignore[arg-type]
            tier="stub",
            confidence=Confidence.low,
            started_at=datetime.now(UTC),
            total_ms=0,
            cache=CacheState.miss,
        )


def test_diagnostic_accepts_subsystem() -> None:
    d = Diagnostic(
        t_ms=0,
        step="raw",
        verdict=Verdict.anti_bot,
        subsystem="cloudflare",
        dur_ms=120,
    )
    assert d.subsystem == "cloudflare"


def test_next_link_caps_anchor_and_reason() -> None:
    """Over-cap `anchor` and `reason` truncate (not raise) per spec."""
    c = NextLink(
        anchor="x" * 200,
        url="https://example.com/post",
        reason="y" * 200,
        kind="drilldown",
    )
    assert len(c.anchor) == 120
    assert len(c.reason) == 80
    assert c.kind == "drilldown"


def test_next_link_rejects_invalid_kind() -> None:
    """`kind` is a closed enum — anything outside the literal set raises."""
    with pytest.raises(ValidationError):
        NextLink(
            anchor="x",
            url="https://example.com/post",
            reason="y",
            kind="other",  # type: ignore[arg-type]
        )


def test_fetch_response_next_links_defaults_empty() -> None:
    """`FetchResponse.next_links` defaults to [] (not None)."""
    from datetime import datetime

    r = FetchResponse(
        url="https://example.com",
        status=FetchStatus.ok,
        tier="raw",
        confidence=Confidence.high,
        started_at=datetime.now(UTC),
        total_ms=10,
        cache=CacheState.miss,
    )
    assert r.next_links == []
