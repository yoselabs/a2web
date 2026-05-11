"""ProxyPool — health/quarantine + acquire/report."""

from __future__ import annotations

import time

import pytest

from a2web.proxy.pool import ProxyPool
from a2web.settings import AppSettings, ProxyEntry, RouteRule


def _settings(**kw: object) -> AppSettings:
    return AppSettings(
        proxies=kw.get("proxies", {}),  # type: ignore[arg-type]
        routes=kw.get("routes", []),  # type: ignore[arg-type]
    )


def test_acquire_direct_when_no_route() -> None:
    pool = ProxyPool(settings=_settings())
    h = pool.acquire("any.com", "raw")
    assert h is not None
    assert h.proxy_url is None
    assert h.proxy_id == "direct"


def test_acquire_returns_first_healthy() -> None:
    s = _settings(
        proxies={
            "p1": ProxyEntry(url="http://p1:8080", region="x", kind="datacenter"),
            "p2": ProxyEntry(url="http://p2:8080", region="x", kind="datacenter"),
        },
        routes=[RouteRule(host="archive.ph", proxy="p1", fallback=["p2"])],
    )
    pool = ProxyPool(settings=s)
    h = pool.acquire("archive.ph", "raw")
    assert h is not None
    assert h.proxy_id == "p1"


def test_three_failures_quarantine_then_fallback() -> None:
    s = _settings(
        proxies={
            "p1": ProxyEntry(url="http://p1:8080", region="x", kind="datacenter"),
            "p2": ProxyEntry(url="http://p2:8080", region="x", kind="datacenter"),
        },
        routes=[RouteRule(host="archive.ph", proxy="p1", fallback=["p2"])],
    )
    pool = ProxyPool(settings=s)
    h1 = pool.acquire("archive.ph", "raw")
    assert h1 is not None and h1.proxy_id == "p1"
    pool.report(h1, success=False)
    pool.report(h1, success=False)
    pool.report(h1, success=False)
    # Now p1 quarantined; acquire should walk to p2.
    h2 = pool.acquire("archive.ph", "raw")
    assert h2 is not None
    assert h2.proxy_id == "p2"


def test_proxy_required_returns_none_when_all_dead() -> None:
    s = _settings(
        proxies={"p1": ProxyEntry(url="http://p1:8080", region="x", kind="datacenter")},
        routes=[RouteRule(host="archive.ph", proxy="p1", proxy_required=True)],
    )
    pool = ProxyPool(settings=s)
    h = pool.acquire("archive.ph", "raw")
    assert h is not None
    pool.report(h, success=False)
    pool.report(h, success=False)
    pool.report(h, success=False)
    assert pool.acquire("archive.ph", "raw") is None


def test_no_proxy_required_falls_back_to_direct() -> None:
    s = _settings(
        proxies={"p1": ProxyEntry(url="http://p1:8080", region="x", kind="datacenter")},
        routes=[RouteRule(host="archive.ph", proxy="p1", proxy_required=False)],
    )
    pool = ProxyPool(settings=s)
    h = pool.acquire("archive.ph", "raw")
    assert h is not None
    pool.report(h, success=False)
    pool.report(h, success=False)
    pool.report(h, success=False)
    h2 = pool.acquire("archive.ph", "raw")
    assert h2 is not None
    assert h2.proxy_id == "direct"


def test_success_resets_failure_counter() -> None:
    s = _settings(
        proxies={"p1": ProxyEntry(url="http://p1:8080", region="x", kind="datacenter")},
        routes=[RouteRule(host="archive.ph", proxy="p1")],
    )
    pool = ProxyPool(settings=s)
    h = pool.acquire("archive.ph", "raw")
    assert h is not None
    pool.report(h, success=False)
    pool.report(h, success=False)
    pool.report(h, success=True)  # reset
    pool.report(h, success=False)
    pool.report(h, success=False)
    # Still alive — counter was reset by the success.
    h2 = pool.acquire("archive.ph", "raw")
    assert h2 is not None
    assert h2.proxy_id == "p1"


@pytest.mark.asyncio
async def test_close_is_noop() -> None:
    pool = ProxyPool(settings=_settings())
    await pool.close()
    await pool.close()  # idempotent


def test_quarantine_duration_is_600s() -> None:
    s = _settings(
        proxies={"p1": ProxyEntry(url="http://p1:8080", region="x", kind="datacenter")},
        routes=[RouteRule(host="archive.ph", proxy="p1")],
    )
    pool = ProxyPool(settings=s)
    h = pool.acquire("archive.ph", "raw")
    assert h is not None
    pool.report(h, success=False)
    pool.report(h, success=False)
    pool.report(h, success=False)
    health = pool.health["p1"]
    assert health.quarantined_until - time.monotonic() > 599
