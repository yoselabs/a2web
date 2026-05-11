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

from a2web.cache.sqlite_cache import SqliteResource
from a2web.llm.resource import LlmExtractorResource
from a2web.packages.browser_pool import BrowserPool
from a2web.settings import AppSettings

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
    settings = AppSettings()
    resource = SqliteResource(settings)
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
    settings = AppSettings()
    resource = SqliteResource(settings)

    results = await asyncio.gather(*[resource._ensure() for _ in range(20)])
    assert all(r is results[0] for r in results)

    await resource.close()


@pytest.mark.asyncio
async def test_sqlite_resource_close_is_idempotent(cache_dir: Path) -> None:
    """Calling close() twice is safe and a no-op the second time."""
    del cache_dir
    resource = SqliteResource(AppSettings())
    await resource._ensure()
    await resource.close()
    await resource.close()  # must not raise
    assert resource._conn is None


@pytest.mark.asyncio
async def test_sqlite_resource_ensure_after_close_reopens(cache_dir: Path) -> None:
    """After close(), a subsequent _ensure() opens a fresh connection."""
    del cache_dir
    resource = SqliteResource(AppSettings())
    conn1 = await resource._ensure()
    await resource.close()
    conn2 = await resource._ensure()
    assert conn2 is not conn1
    await resource.close()


@pytest.mark.asyncio
async def test_sqlite_resource_get_put_roundtrip(cache_dir: Path) -> None:
    """get/put go through _ensure transparently."""
    del cache_dir
    resource = SqliteResource(AppSettings())
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


@pytest.mark.asyncio
async def test_llm_resource_init_does_no_work() -> None:
    """__init__ doesn't touch the SDK or env."""
    resource = LlmExtractorResource(AppSettings(), SqliteResource(AppSettings()))
    assert resource._extractor is None
    assert resource.unavailable_reason is None


@pytest.mark.asyncio
async def test_llm_resource_missing_api_key_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing key → _ensure returns None and sets unavailable_reason once."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = AppSettings(llm_provider="anthropic")
    resource = LlmExtractorResource(settings, SqliteResource(settings))
    result = await resource._ensure()
    assert result is None
    assert resource.unavailable_reason is not None
    # Subsequent calls return cached None without retrying construction.
    assert await resource._ensure() is None


@pytest.mark.asyncio
async def test_llm_resource_extract_returns_none_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """extract() short-circuits to None when LLM is permanently unavailable."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = AppSettings(llm_provider="anthropic")
    resource = LlmExtractorResource(settings, SqliteResource(settings))
    result = await resource.extract(content="hello", ask="what?")
    assert result is None


@pytest.mark.asyncio
async def test_llm_resource_close_is_noop() -> None:
    """close() is a no-op today; verify symmetric for lifecycle hooks."""
    resource = LlmExtractorResource(AppSettings(), SqliteResource(AppSettings()))
    await resource.close()  # must not raise
    await resource.close()


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

    pool = BrowserPool(max_pool=2, idle_timeout_s=10, page_budget_s=5)
    with pytest.raises(ImportError):
        await pool._ensure()


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

    pool = BrowserPool()
    with pytest.raises(ImportError):
        await pool.start()
