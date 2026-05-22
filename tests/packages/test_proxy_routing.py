"""proxy_routing — route policy (pure resolution) + ProxyPool health/quarantine."""

from __future__ import annotations

import time

import pytest

from a2web.packages.proxy_routing import ProxyPool, resolve_route
from a2web.settings import AppSettings, ProxyEntry, RouteRule


def _settings(**kw: object) -> AppSettings:
    return AppSettings(
        proxies=kw.get("proxies", {}),  # type: ignore[arg-type]
        routes=kw.get("routes", []),  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------- #
# Route policy — pure resolution, no I/O.
# --------------------------------------------------------------------- #


def test_no_routes_returns_direct() -> None:
    s = _settings()
    out = resolve_route("example.com", "raw", routes=s.routes, proxies=s.proxies)
    assert out.proxy_url is None
    assert out.matched_rule_index is None


def test_exact_host_match() -> None:
    s = _settings(
        proxies={"eu": ProxyEntry(url="socks5://eu.example:1080", region="eu", kind="residential")},
        routes=[RouteRule(host="archive.ph", proxy="eu")],
    )
    out = resolve_route("archive.ph", "raw", routes=s.routes, proxies=s.proxies)
    assert out.proxy_id == "eu"
    assert out.proxy_url == "socks5://eu.example:1080"


def test_glob_host_match() -> None:
    s = _settings(
        proxies={"eu": ProxyEntry(url="http://eu:8080", region="eu", kind="datacenter")},
        routes=[RouteRule(host="*.archive.today", proxy="eu")],
    )
    assert resolve_route("archive.today", "raw", routes=s.routes, proxies=s.proxies).proxy_id == "eu"
    assert resolve_route("foo.archive.today", "raw", routes=s.routes, proxies=s.proxies).proxy_id == "eu"
    assert resolve_route("notarchive.today", "raw", routes=s.routes, proxies=s.proxies).proxy_id is None


def test_tier_match() -> None:
    s = _settings(
        proxies={"us": ProxyEntry(url="http://us:8080", region="us", kind="datacenter")},
        routes=[RouteRule(tier="browser", proxy="us")],
    )
    assert resolve_route("anyhost.com", "browser", routes=s.routes, proxies=s.proxies).proxy_id == "us"
    assert resolve_route("anyhost.com", "raw", routes=s.routes, proxies=s.proxies).proxy_id is None


def test_and_composition() -> None:
    s = _settings(
        proxies={"eu": ProxyEntry(url="http://eu:8080", region="eu", kind="datacenter")},
        routes=[RouteRule(host="archive.ph", tier="raw", proxy="eu")],
    )
    assert resolve_route("archive.ph", "raw", routes=s.routes, proxies=s.proxies).proxy_id == "eu"
    # Same host but different tier doesn't match.
    assert resolve_route("archive.ph", "jina", routes=s.routes, proxies=s.proxies).proxy_id is None


def test_explicit_direct_override() -> None:
    """Explicit `direct` rule placed before the catch-all wins (first-match)."""
    s = _settings(
        proxies={"eu": ProxyEntry(url="http://eu:8080", region="eu", kind="datacenter")},
        routes=[
            RouteRule(host="reddit.com", proxy="direct"),
            RouteRule(host="*", proxy="eu"),
        ],
    )
    out = resolve_route("reddit.com", "raw", routes=s.routes, proxies=s.proxies)
    assert out.proxy_url is None
    assert out.proxy_id == "direct"
    # Other hosts still go through eu.
    assert resolve_route("other.com", "raw", routes=s.routes, proxies=s.proxies).proxy_id == "eu"


def test_first_match_wins() -> None:
    s = _settings(
        proxies={
            "eu": ProxyEntry(url="http://eu:8080", region="eu", kind="datacenter"),
            "us": ProxyEntry(url="http://us:8080", region="us", kind="datacenter"),
        },
        routes=[
            RouteRule(host="archive.ph", proxy="eu"),
            RouteRule(host="archive.ph", proxy="us"),  # never reached
        ],
    )
    assert resolve_route("archive.ph", "raw", routes=s.routes, proxies=s.proxies).proxy_id == "eu"


def test_missing_proxy_returns_direct() -> None:
    """Rule names a proxy that doesn't exist → direct (warn at call site)."""
    s = _settings(routes=[RouteRule(host="archive.ph", proxy="missing")])
    out = resolve_route("archive.ph", "raw", routes=s.routes, proxies=s.proxies)
    assert out.proxy_url is None
    assert out.proxy_id is None


def test_env_var_resolution(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PROXY_PASS", "secret123")
    s = _settings(
        proxies={"eu": ProxyEntry(url="socks5://user:${PROXY_PASS}@eu:1080", region="eu", kind="residential")},
        routes=[RouteRule(host="archive.ph", proxy="eu")],
    )
    out = resolve_route("archive.ph", "raw", routes=s.routes, proxies=s.proxies)
    assert out.proxy_url == "socks5://user:secret123@eu:1080"


def test_env_var_unset_left_literal() -> None:
    s = _settings(
        proxies={"eu": ProxyEntry(url="socks5://${UNSET_VAR}@eu", region="eu", kind="residential")},
        routes=[RouteRule(host="archive.ph", proxy="eu")],
    )
    out = resolve_route("archive.ph", "raw", routes=s.routes, proxies=s.proxies)
    assert out.proxy_url == "socks5://${UNSET_VAR}@eu"


def test_proxy_required_propagates() -> None:
    s = _settings(
        proxies={"eu": ProxyEntry(url="http://eu:8080", region="eu", kind="datacenter")},
        routes=[RouteRule(host="archive.ph", proxy="eu", proxy_required=True, fallback=["us"])],
    )
    out = resolve_route("archive.ph", "raw", routes=s.routes, proxies=s.proxies)
    assert out.proxy_required is True
    assert out.fallback == ("us",)


# --------------------------------------------------------------------- #
# ProxyPool — health/quarantine + acquire/report.
# --------------------------------------------------------------------- #


def test_acquire_direct_when_no_route() -> None:
    s = _settings()
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
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
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
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
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
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
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
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
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
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
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
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
    s = _settings()
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
    await pool.close()
    await pool.close()  # idempotent


def test_quarantine_duration_is_600s() -> None:
    s = _settings(
        proxies={"p1": ProxyEntry(url="http://p1:8080", region="x", kind="datacenter")},
        routes=[RouteRule(host="archive.ph", proxy="p1")],
    )
    pool = ProxyPool(routes=s.routes, proxies=s.proxies)
    h = pool.acquire("archive.ph", "raw")
    assert h is not None
    pool.report(h, success=False)
    pool.report(h, success=False)
    pool.report(h, success=False)
    health = pool.health["p1"]
    assert health.quarantined_until - time.monotonic() > 599
