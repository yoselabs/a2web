"""End-to-end smoke — does Reddit reach browser tier in production wiring?

Bench can't verify the v0.22 marker fix because llm_eval/systems.py calls
fetcher.fetch without browser_pool injected. This script wires browser_pool
the way WebRouter does (Lazy[BrowserPool]) and confirms Reddit now escalates
to browser instead of dying at length_floor.

Pure investigation. No production code modified.
"""

from __future__ import annotations

import asyncio

from a2kit.ldd import ldd_state_for_call
from a2kit.packages.testing.null_context import null_context
from a2kit.testing import lazy as lazy_thunk

from typing import cast

from purgatory import AsyncCircuitBreakerFactory

from a2web.fetcher import fetch as a2web_fetch
from a2web.packages.browser_pool import BrowserPool
from a2web.packages.http_cache import SqliteResource
from a2web.packages.proxy_routing import ProxyPool
from a2web.settings import AppSettings
from a2web.state import build_state


async def main() -> None:
    settings = AppSettings()
    state = build_state(
        settings=settings,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        proxy_pool=ProxyPool(
            routes=cast("list", settings.routes),
            proxies=cast("dict", settings.proxies),
        ),
        sqlite=SqliteResource(),
    )
    ambient = ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)
    ambient.__enter__()
    async with state.sqlite:
        pool = BrowserPool()
        async with pool:
            print("Calling fetch with browser_pool wired (production shape)...")
            response = await a2web_fetch(
                "https://www.reddit.com/r/LocalLLaMA/",
                state=state,
                browser_pool=lazy_thunk(pool),
                debug=True,
                include_links=False,
                ask=None,
            )
            print(f"  status:     {response.status.value}")
            print(f"  tier:       {response.tier}")
            print(f"  confidence: {response.confidence.value}")
            print(f"  content_md len: {len(response.content_md)}")
            print(f"  title:      {response.title!r}")
            print(f"  diagnostics ({len(response.diagnostics)}):")
            for d in response.diagnostics:
                print(f"    t={d.t_ms:>5}ms step={d.step!r:<15} verdict={d.verdict.value!r:<18} subsys={d.subsystem!r}")
            if response.operator_hints:
                print(f"  operator_hints:")
                for h in response.operator_hints:
                    print(f"    {h.code}: {h.message}")
            preview = response.content_md[:300].replace("\n", " ⏎ ")
            print(f"  content[:300]: {preview!r}")


if __name__ == "__main__":
    asyncio.run(main())
