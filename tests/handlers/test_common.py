"""Unit tests for `handlers._common` — the shared FetchVerdict → Verdict helper."""

from __future__ import annotations

from a2web.handlers._common import empty_result, map_non_ok
from a2web.models import Verdict
from a2web.packages.http_fetch import FetchOutcome, FetchVerdict


def _outcome(verdict: FetchVerdict, *, status: int = 200) -> FetchOutcome:
    return FetchOutcome(
        body=b"",
        content_type="text/html",
        status_code=status,
        final_url="https://example.com/",
        verdict=verdict,
    )


def test_empty_result_shape() -> None:
    r = empty_result("https://x.com/p", Verdict.not_found)
    assert r.body == b""
    assert r.content_type == ""
    assert r.status_code == 0
    assert r.final_url == "https://x.com/p"
    assert r.verdict is Verdict.not_found


def test_map_non_ok_ok_returns_none() -> None:
    assert map_non_ok(_outcome(FetchVerdict.ok), url="https://x.com/") is None


def test_map_non_ok_timeout() -> None:
    r = map_non_ok(_outcome(FetchVerdict.timeout), url="https://x.com/")
    assert r is not None
    assert r.verdict is Verdict.timeout


def test_map_non_ok_not_found() -> None:
    r = map_non_ok(_outcome(FetchVerdict.not_found), url="https://x.com/")
    assert r is not None
    assert r.verdict is Verdict.not_found


def test_map_non_ok_rate_limited() -> None:
    r = map_non_ok(_outcome(FetchVerdict.rate_limited), url="https://x.com/")
    assert r is not None
    assert r.verdict is Verdict.rate_limited


def test_map_non_ok_connection_error_other() -> None:
    r = map_non_ok(_outcome(FetchVerdict.connection_error), url="https://x.com/")
    assert r is not None
    assert r.verdict is Verdict.connection_error


def test_map_non_ok_proxy_unavailable_maps_to_connection_error() -> None:
    r = map_non_ok(_outcome(FetchVerdict.proxy_unavailable), url="https://x.com/")
    assert r is not None
    assert r.verdict is Verdict.connection_error
