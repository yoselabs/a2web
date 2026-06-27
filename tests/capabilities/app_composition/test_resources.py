"""Resource pattern tests — SqliteResource, LlmExtractorResource, BrowserPool._ensure.

Verifies the canonical a2kit v0.27 Resource shape:
- Sync __init__ (no I/O).
- `_ensure()` opens lazily under internal lock; concurrent first calls race-safe.
- `close()` is idempotent; `_ensure()` after `close()` reopens.
- AppState fields stay non-Optional in callers — Resource owns the None handling.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from a2web.llm_resource import LlmExtractorResource
from a2web.packages.browser_backends import PlaywrightBackend, camoufox_launcher
from a2web.packages.http_cache import SqliteResource
from a2web.packages.llm_extract import Provider
from a2web.settings import AppSettings
from a2web.state import (
    ResourceUnavailable,
    build_selected_provider,
    select_backend,
    select_backend_named,
    unavailable_lazy,
)

# --------------------------------------------------------------------- #
# SqliteResource
# --------------------------------------------------------------------- #


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("A2WEB_CACHE_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_sqlite_resource_lazy_open(cache_dir: Path) -> None:
    """__init__ does no I/O; _ensure opens the connection."""
    resource = SqliteResource(db_path=None)
    assert resource._conn is None
    assert not (cache_dir / "cache.sqlite").exists()

    conn = await resource._ensure()
    assert conn is not None
    assert resource._conn is conn
    assert (cache_dir / "cache.sqlite").exists()

    await resource.close()


@pytest.mark.asyncio
async def test_sqlite_resource_concurrent_first_calls_share_connection(cache_dir: Path) -> None:
    """Double-checked lock: 20 concurrent _ensure calls open exactly one connection."""
    del cache_dir
    resource = SqliteResource(db_path=None)

    results = await asyncio.gather(*[resource._ensure() for _ in range(20)])
    assert all(r is results[0] for r in results)

    await resource.close()


@pytest.mark.asyncio
async def test_sqlite_resource_close_is_idempotent(cache_dir: Path) -> None:
    """Calling close() twice is safe and a no-op the second time."""
    del cache_dir
    resource = SqliteResource(db_path=None)
    await resource._ensure()
    await resource.close()
    await resource.close()  # must not raise
    assert resource._conn is None


@pytest.mark.asyncio
async def test_sqlite_resource_ensure_after_close_reopens(cache_dir: Path) -> None:
    """After close(), a subsequent _ensure() opens a fresh connection."""
    del cache_dir
    resource = SqliteResource(db_path=None)
    conn1 = await resource._ensure()
    await resource.close()
    conn2 = await resource._ensure()
    assert conn2 is not conn1
    await resource.close()


@pytest.mark.asyncio
async def test_sqlite_resource_get_put_roundtrip(cache_dir: Path) -> None:
    """get/put go through _ensure transparently."""
    del cache_dir
    resource = SqliteResource(db_path=None)
    await resource.put(
        "https://example.com/x",
        "profile",
        etag=None,
        last_modified=None,
        status_code=200,
        content_type="text/html",
        body=b"<html>hi</html>",
        ttl_s=3600,
    )
    row = await resource.get("https://example.com/x", "profile")
    assert row is not None
    assert row.body == b"<html>hi</html>"
    assert row.status_code == 200
    await resource.close()


# --------------------------------------------------------------------- #
# LlmExtractorResource
# --------------------------------------------------------------------- #


def _unavailable(reason: str = "no provider") -> object:
    return unavailable_lazy(Provider, reason=reason)


@pytest.mark.asyncio
async def test_llm_resource_init_does_no_work() -> None:
    """__init__ doesn't touch the SDK or env — no extractor built."""
    resource = LlmExtractorResource(AppSettings(), SqliteResource(db_path=None), _unavailable())
    assert resource._extractor is None


@pytest.mark.asyncio
async def test_llm_resource_missing_provider_raises() -> None:
    """No provider configured → awaiting the injected provider during _ensure
    raises ResourceUnavailable (the shared seam)."""
    resource = LlmExtractorResource(AppSettings(), SqliteResource(db_path=None), _unavailable("no API key"))
    with pytest.raises(ResourceUnavailable):
        await resource._ensure()


@pytest.mark.asyncio
async def test_llm_resource_extract_raises_when_unavailable() -> None:
    """extract() propagates ResourceUnavailable when no provider is configured."""
    resource = LlmExtractorResource(AppSettings(), SqliteResource(db_path=None), _unavailable())
    with pytest.raises(ResourceUnavailable):
        await resource.extract(content="hello", ask="what?")


@pytest.mark.asyncio
async def test_build_selected_provider_raises_without_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """The DI Provider factory raises ResourceUnavailable when nothing resolves
    (anthropic pinned, no API key in env)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ResourceUnavailable):
        build_selected_provider(AppSettings(llm_provider="anthropic"))


@pytest.mark.asyncio
async def test_llm_resource_close_is_noop() -> None:
    """close() is a no-op today; verify symmetric for lifecycle hooks."""
    resource = LlmExtractorResource(AppSettings(), SqliteResource(db_path=None), _unavailable())
    await resource.close()  # must not raise
    await resource.close()


# --------------------------------------------------------------------- #
# Backend selection — two-rung defaults + gated Camoufox
# (browser-backend-bakeoff). Resolves selectors only; no browser launch.
# --------------------------------------------------------------------- #


def test_fast_rung_defaults_to_patchright() -> None:
    """Unset `browser_backend` resolves the fast Chromium rung, not Camoufox."""
    backend = select_backend(AppSettings())
    assert backend.name == "patchright"


def test_robust_rung_defaults_to_zendriver() -> None:
    """Unset `browser_backend_robust` resolves the robust CDP rung."""
    s = AppSettings()
    backend = select_backend_named(s, s.browser_backend_robust)
    assert backend.name == "zendriver"


def test_camoufox_is_gated_unavailable() -> None:
    """Camoufox is gated off (#625 unreleased) — selecting it degrades, not crashes."""
    with pytest.raises(ResourceUnavailable, match="camoufox"):
        select_backend_named(AppSettings(), "camoufox")


def test_unknown_backend_degrades() -> None:
    with pytest.raises(ResourceUnavailable):
        select_backend_named(AppSettings(), "nope-engine")


# --------------------------------------------------------------------- #
# BrowserPool._ensure
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_browser_pool_ensure_propagates_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When camoufox is missing, _ensure raises ImportError under the lock.

    Mirrors today's `start()` behavior; BrowserTier catches at the call site.
    """
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("camoufox"):
            raise ImportError("No module named 'camoufox'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    backend = PlaywrightBackend(camoufox_launcher, max_pool=2, idle_timeout_s=10, page_budget_s=5)
    with pytest.raises(ImportError):
        await backend._ensure()


@pytest.mark.asyncio
async def test_browser_pool_start_alias_calls_ensure(monkeypatch: pytest.MonkeyPatch) -> None:
    """`start()` is preserved as a deprecated alias during migration."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("camoufox"):
            raise ImportError("No module named 'camoufox'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    backend = PlaywrightBackend(camoufox_launcher)
    with pytest.raises(ImportError):
        await backend.start()
