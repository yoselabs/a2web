"""v0.4 step 6: ExtractionCache + Extractor wire-up tests.

Exercises:
- ExtractionCache get/put/evict happy paths against an in-memory sqlite.
- TTL eviction surfaces a stale row as a miss + evicts lazily.
- Different model_id keys never collide.
- Extractor uses the cache transparently: 2nd call is a hit with cost=0
  and original_cost_usd populated.
- Empty model response is NOT cached.
"""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest

from a2web.llm import (
    ExtractionCache,
    Extractor,
    ModelSpec,
    PromptTemplate,
    ProviderResponse,
    hash_text,
)

# --------------------------------------------------------------------- #
# In-memory sqlite fixture
# --------------------------------------------------------------------- #


@pytest.fixture
async def sqlite():
    conn = await aiosqlite.connect(":memory:")
    try:
        yield conn
    finally:
        await conn.close()


# --------------------------------------------------------------------- #
# Cache primitives
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cache_get_miss_returns_none(sqlite) -> None:
    cache = ExtractionCache(sqlite, ttl_s=900)
    hit = await cache.get(
        content_hash="abc",
        ask_hash="xyz",
        model_id="m",
        template_name="t",
    )
    assert hit is None


@pytest.mark.asyncio
async def test_cache_put_then_get_round_trip(sqlite) -> None:
    cache = ExtractionCache(sqlite, ttl_s=900)
    await cache.put(
        content_hash=hash_text("hello"),
        ask_hash=hash_text("what?"),
        model_id="claude-haiku-4-5",
        template_name="webfetch_default_v1",
        answer="world",
        prompt_tokens=10,
        completion_tokens=2,
        cost_usd=0.0005,
        latency_ms=120,
    )
    hit = await cache.get(
        content_hash=hash_text("hello"),
        ask_hash=hash_text("what?"),
        model_id="claude-haiku-4-5",
        template_name="webfetch_default_v1",
    )
    assert hit is not None
    assert hit.answer == "world"
    assert hit.prompt_tokens == 10
    assert hit.completion_tokens == 2
    assert hit.cost_usd == pytest.approx(0.0005)
    assert hit.latency_ms == 120


@pytest.mark.asyncio
async def test_cache_keys_isolate_by_model_id(sqlite) -> None:
    """Same content + ask but different model → independent cache slots."""
    cache = ExtractionCache(sqlite, ttl_s=900)
    common = {
        "content_hash": hash_text("hi"),
        "ask_hash": hash_text("q"),
        "template_name": "webfetch_default_v1",
    }
    await cache.put(
        **common,
        model_id="haiku",
        answer="haiku says hi",
        prompt_tokens=5,
        completion_tokens=3,
        cost_usd=0.0001,
        latency_ms=80,
    )
    sonnet_hit = await cache.get(**common, model_id="sonnet")
    assert sonnet_hit is None
    haiku_hit = await cache.get(**common, model_id="haiku")
    assert haiku_hit is not None
    assert haiku_hit.answer == "haiku says hi"


@pytest.mark.asyncio
async def test_cache_keys_isolate_by_template(sqlite) -> None:
    """Same (content, ask, model) but different template name → distinct
    cache slots so a future prompt change doesn't bleed."""
    cache = ExtractionCache(sqlite, ttl_s=900)
    common = {
        "content_hash": hash_text("c"),
        "ask_hash": hash_text("a"),
        "model_id": "m",
    }
    await cache.put(
        **common,
        template_name="webfetch_default_v1",
        answer="A",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
        latency_ms=0,
    )
    hit_terse = await cache.get(**common, template_name="terse_v1")
    assert hit_terse is None
    hit_default = await cache.get(**common, template_name="webfetch_default_v1")
    assert hit_default is not None


@pytest.mark.asyncio
async def test_cache_expired_row_is_evicted_on_read(sqlite) -> None:
    """TTL=0 means every put is born expired; the next get evicts it."""
    cache = ExtractionCache(sqlite, ttl_s=0)
    await cache.put(
        content_hash="c",
        ask_hash="a",
        model_id="m",
        template_name="t",
        answer="stale",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
        latency_ms=0,
    )
    # Force the cache's clock past the row's expires_at by reading a moment later.
    await asyncio.sleep(1.1)
    hit = await cache.get(content_hash="c", ask_hash="a", model_id="m", template_name="t")
    assert hit is None
    assert await cache.size() == 0


@pytest.mark.asyncio
async def test_cache_evict_expired_returns_count(sqlite) -> None:
    cache = ExtractionCache(sqlite, ttl_s=0)
    for i in range(3):
        await cache.put(
            content_hash=f"c{i}",
            ask_hash="a",
            model_id="m",
            template_name="t",
            answer=str(i),
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.0,
            latency_ms=0,
        )
    await asyncio.sleep(1.1)
    n = await cache.evict_expired()
    assert n == 3
    assert await cache.size() == 0


# --------------------------------------------------------------------- #
# Extractor wired with cache
# --------------------------------------------------------------------- #


class _CountingProvider:
    """Provider that records every call. Returns canned text."""

    name = "count"

    def __init__(self, *, text: str = "the answer", cost: float = 0.002) -> None:
        self.text = text
        self.cost = cost
        self.calls = 0

    async def complete(self, *, system, user, model, max_tokens=1024, temperature=0.0, thinking_disabled=True):
        self.calls += 1
        return ProviderResponse(
            text=self.text,
            model=model,
            prompt_tokens=80,
            completion_tokens=10,
            cost_usd=self.cost,
            latency_ms=50,
        )


@pytest.mark.asyncio
async def test_extractor_cache_hit_skips_provider(sqlite) -> None:
    """Second extract() with identical (content, ask, model, template) hits
    the cache and does NOT invoke the provider."""
    cache = ExtractionCache(sqlite, ttl_s=900)
    provider = _CountingProvider(text="first call")
    ex = Extractor(
        provider=provider,
        model=ModelSpec("count", "test-model"),
        cache=cache,
    )

    r1 = await ex.extract(content="the page", ask="what?")
    r2 = await ex.extract(content="the page", ask="what?")

    assert provider.calls == 1
    assert r1.cache_hit is False
    assert r2.cache_hit is True
    assert r2.answer == "first call"
    assert r2.cost_usd == 0.0
    assert r2.original_cost_usd == pytest.approx(0.002)


@pytest.mark.asyncio
async def test_extractor_cache_miss_calls_provider_and_persists(sqlite) -> None:
    """Different ask → cache miss → provider called → entry persisted."""
    cache = ExtractionCache(sqlite, ttl_s=900)
    provider = _CountingProvider()
    ex = Extractor(
        provider=provider,
        model=ModelSpec("count", "test-model"),
        cache=cache,
    )

    await ex.extract(content="page", ask="q1")
    await ex.extract(content="page", ask="q2")

    assert provider.calls == 2
    assert await cache.size() == 2


@pytest.mark.asyncio
async def test_extractor_does_not_cache_empty_provider_response(sqlite) -> None:
    """An empty provider response (rate-limit / error path) must NOT be
    cached — a future caller should retry, not see the empty answer."""
    cache = ExtractionCache(sqlite, ttl_s=900)
    provider = _CountingProvider(text="")
    ex = Extractor(
        provider=provider,
        model=ModelSpec("count", "test-model"),
        cache=cache,
    )
    await ex.extract(content="c", ask="a")
    assert await cache.size() == 0


@pytest.mark.asyncio
async def test_extractor_truncates_then_uses_truncated_content_for_cache_key(
    sqlite,
) -> None:
    """Two callers with different upstream payloads but the same post-cap
    content share a cache slot (matches WebFetch's behavior)."""
    cache = ExtractionCache(sqlite, ttl_s=900)
    provider = _CountingProvider(text="shared answer")
    ex = Extractor(
        provider=provider,
        model=ModelSpec("count", "m"),
        max_content_chars=20,
        cache=cache,
    )

    # First caller: 100 chars of "x" + a suffix unique to them.
    first = "x" * 100 + "FIRST"
    await ex.extract(content=first, ask="q")
    # Second caller: 100 chars of "x" + a different suffix.
    second = "x" * 100 + "SECOND"
    r2 = await ex.extract(content=second, ask="q")

    # Both truncated to the same 20-char prefix → same cache key.
    assert r2.cache_hit is True
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_custom_template_keyed_separately_from_default(sqlite) -> None:
    """Same (content, ask, model) but different template names → separate
    cache slots."""
    cache = ExtractionCache(sqlite, ttl_s=900)
    provider = _CountingProvider()
    custom = PromptTemplate(name="custom_v1", version=1, user_template="{content}|{ask}")
    ex_default = Extractor(provider=provider, model=ModelSpec("count", "m"), cache=cache)
    ex_custom = Extractor(provider=provider, model=ModelSpec("count", "m"), template=custom, cache=cache)

    await ex_default.extract(content="c", ask="a")
    r2 = await ex_custom.extract(content="c", ask="a")

    assert r2.cache_hit is False
    assert provider.calls == 2
