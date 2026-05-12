"""Route policy — pure resolution, no I/O."""

from __future__ import annotations

from a2web.packages.proxy_routing import resolve_route
from a2web.settings import AppSettings, ProxyEntry, RouteRule


def _settings(**kw: object) -> AppSettings:
    proxies = kw.pop("proxies", {})
    routes = kw.pop("routes", [])
    return AppSettings(proxies=proxies, routes=routes)  # type: ignore[arg-type]


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
