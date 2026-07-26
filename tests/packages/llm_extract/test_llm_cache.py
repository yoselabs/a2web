"""a2web's wiring of the shelf `llm-cache` into the Extractor.

The cache MACHINERY (get/put/evict, TTL, key/model isolation, the
Completion round trip) is tested in the shelf package `llm_cache`. What a2web
verifies HERE is the binding: that `Extractor` uses `LlmCache` transparently —
a repeat (content, ask, model, template) is a hit with cost=0 and
`original_cost_usd` populated, a miss calls the provider and persists, an empty
answer is never cached, truncated content drives the key, and the template name
is part of the key (a2web's `make_key(content, ask, template)` composite).
"""

from __future__ import annotations

import aiosqlite
import pytest

from a2web.packages.llm_extract import (
    Extractor,
    LlmCache,
    ModelSpec,
    PromptTemplate,
    ProviderResponse,
)


@pytest.fixture
async def sqlite():
    conn = await aiosqlite.connect(":memory:")
    try:
        yield conn
    finally:
        await conn.close()


class _CountingProvider:
    """Provider that records every call. Returns canned text."""

    name = "count"

    def __init__(self, *, text: str = "the answer", cost: float = 0.002) -> None:
        self.text = text
        self.cost = cost
        self.calls = 0

    async def complete(self, *, system, user, model, max_tokens=1024, temperature=0.0, thinking_disabled=True, parts=None):
        self.calls += 1
        return ProviderResponse(
            text=self.text,
            model=model,
            prompt_tokens=80,
            completion_tokens=10,
            cost_usd=self.cost,
            latency_ms=50,
        )


async def test_extractor_cache_hit_skips_provider(sqlite) -> None:
    """Second extract() with identical (content, ask, model, template) hits
    the cache and does NOT invoke the provider."""
    cache = LlmCache(sqlite, ttl_s=900)
    provider = _CountingProvider(text="first call")
    ex = Extractor(provider=provider, model=ModelSpec("test-model"), cache=cache)

    r1 = await ex.extract(content="the page", ask="what?")
    r2 = await ex.extract(content="the page", ask="what?")

    assert provider.calls == 1
    assert r1.cache_hit is False
    assert r2.cache_hit is True
    assert r2.answer == "first call"
    assert r2.cost_usd == 0.0
    assert r2.original_cost_usd == pytest.approx(0.002)


async def test_extractor_cache_miss_calls_provider_and_persists(sqlite) -> None:
    """Different ask → cache miss → provider called → entry persisted."""
    cache = LlmCache(sqlite, ttl_s=900)
    provider = _CountingProvider()
    ex = Extractor(provider=provider, model=ModelSpec("test-model"), cache=cache)

    await ex.extract(content="page", ask="q1")
    await ex.extract(content="page", ask="q2")

    assert provider.calls == 2
    assert await cache.size() == 2


async def test_extractor_does_not_cache_empty_provider_response(sqlite) -> None:
    """An empty provider response (rate-limit / error path) must NOT be
    cached — a future caller should retry, not see the empty answer."""
    cache = LlmCache(sqlite, ttl_s=900)
    provider = _CountingProvider(text="")
    ex = Extractor(provider=provider, model=ModelSpec("test-model"), cache=cache)

    await ex.extract(content="c", ask="a")
    assert await cache.size() == 0


async def test_extractor_truncates_then_uses_truncated_content_for_cache_key(sqlite) -> None:
    """Two callers with different upstream payloads but the same post-cap
    content share a cache slot (matches WebFetch's behavior)."""
    cache = LlmCache(sqlite, ttl_s=900)
    provider = _CountingProvider(text="shared answer")
    ex = Extractor(provider=provider, model=ModelSpec("m"), max_content_chars=20, cache=cache)

    await ex.extract(content="x" * 100 + "FIRST", ask="q")
    r2 = await ex.extract(content="x" * 100 + "SECOND", ask="q")

    # Both truncated to the same 20-char prefix → same cache key.
    assert r2.cache_hit is True
    assert provider.calls == 1


async def test_custom_template_keyed_separately_from_default(sqlite) -> None:
    """Same (content, ask, model) but different template names → separate
    cache slots (the template name is part of a2web's composite key)."""
    cache = LlmCache(sqlite, ttl_s=900)
    provider = _CountingProvider()
    custom = PromptTemplate(name="custom_v1", version=1, user_template="{content}|{ask}")
    ex_default = Extractor(provider=provider, model=ModelSpec("m"), cache=cache)
    ex_custom = Extractor(provider=provider, model=ModelSpec("m"), template=custom, cache=cache)

    await ex_default.extract(content="c", ask="a")
    r2 = await ex_custom.extract(content="c", ask="a")

    assert r2.cache_hit is False
    assert provider.calls == 2
