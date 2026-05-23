# ruff: noqa: T201 — CLI tool, print is the output channel
"""Live-contract handler probe — exercises every registered handler against
a real representative URL with no monkeypatching.

Purpose: catch transport-layer regressions that unit tests miss. When a
handler hand-rolls its own httpx transport, unit tests that monkeypatch
the seam look green while the live network would fail (the linux.do
Cloudflare-block was invisible until production). This probe asserts
each handler completes a real fetch end-to-end through `fetch_bytes`
(curl_cffi Chrome impersonation) and produces non-empty rendered content.

Loud-failure invariants:
- Every entry in `a2web.handlers._HANDLERS` MUST have a `_PROBE_URLS`
  entry. Missing entry → script exits non-zero, names the offender.
- Twitter is skipped when `nitter_instances` is empty (graceful no-op).
- Each handler is given a wall-clock budget per fetch; transport timeouts
  count as failures.

Run with `make handler-probe`. Not wired into `make check`. Live-network.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import TYPE_CHECKING

from .handlers import _HANDLERS
from .models import Verdict
from .settings import AppSettings

if TYPE_CHECKING:
    from .handlers import Handler

# One representative URL per registered handler. Adding a handler MUST
# add an entry here; the probe will fail loudly otherwise.
_PROBE_URLS: dict[str, str] = {
    # Reddit: the Obama AMA — durable, permanently archived since 2012.
    "site_handler:reddit": (
        "https://www.reddit.com/r/IAmA/comments/z1c9z/i_am_barack_obama_president_of_the_united_states/"
    ),
    "site_handler:hn": "https://news.ycombinator.com/item?id=39000000",
    "site_handler:arxiv": "https://arxiv.org/abs/2308.08155",
    "site_handler:wikipedia": "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "site_handler:github": "https://github.com/anthropics/anthropic-sdk-python",
    # Twitter: requires a working `nitter_instances` host. Public nitter is
    # mostly dead in 2026; the probe will FAIL when the configured instance
    # is unreachable. Not a handler regression — the upstream is gone.
    "site_handler:twitter": "https://twitter.com/anthropicai/status/1701832836929187894",
    # Discourse: linux.do — the named target. Phases 1+2 fixed the
    # Cloudflare-block this URL surfaced. MUST pass.
    "site_handler:discourse": "https://linux.do/latest",
    "site_handler:habr": "https://habr.com/ru/articles/1032730/",
    "site_handler:v2ex": "https://www.v2ex.com/t/1000000",
}


async def _probe_one(handler: Handler, url: str, *, timeout_s: float = 30.0) -> tuple[bool, str]:
    """Run one handler against its representative URL.

    Returns (ok, summary). `ok=True` only when verdict==ok AND
    pre_rendered.content_md is non-empty.
    """
    from tests.conftest import make_default_state

    state = make_default_state(settings=AppSettings(nitter_instances=["nitter.privacydev.net"]))

    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(handler.fetch(url, state=state), timeout=timeout_s)
    except TimeoutError:
        return False, f"TIMEOUT after {timeout_s:.0f}s"
    except Exception as exc:
        return False, f"RAISED {type(exc).__name__}: {exc}"
    finally:
        # Best-effort sqlite teardown — make_default_state opens one.
        try:
            await state.sqlite.close()
        except Exception:  # noqa: S110
            pass

    wall_ms = int((time.monotonic() - t0) * 1000)

    if result.verdict != Verdict.ok:
        return False, f"verdict={result.verdict.value} ({wall_ms}ms)"

    pre = result.pre_rendered
    if pre is None or not pre.content_md or not pre.content_md.strip():
        return False, f"verdict=ok but pre_rendered.content_md empty ({wall_ms}ms)"

    return True, f"ok ({wall_ms}ms, {len(pre.content_md)} chars, title={pre.title!r})"


async def _main() -> int:
    # Loud-failure: every registered handler MUST have a probe URL.
    registered = {h.name for h in _HANDLERS}
    mapped = set(_PROBE_URLS.keys())
    missing = registered - mapped
    extra = mapped - registered
    if missing or extra:
        if missing:
            print(f"FAIL: registered handler(s) missing from _PROBE_URLS: {sorted(missing)}", file=sys.stderr)
        if extra:
            print(f"FAIL: _PROBE_URLS entries with no registered handler: {sorted(extra)}", file=sys.stderr)
        return 2

    failures: list[str] = []
    for handler in _HANDLERS:
        url = _PROBE_URLS[handler.name]

        # Twitter is skipped when nitter_instances is unconfigured at the matches
        # layer; our probe state forces one in, so the handler will fetch.
        # Discourse uses the configured host allowlist; linux.do is in defaults.

        ok, summary = await _probe_one(handler, url)
        marker = "PASS" if ok else "FAIL"
        line = f"[{marker}] {handler.name:30s} {url}\n        {summary}"
        print(line)
        if not ok:
            failures.append(handler.name)

    print()
    if failures:
        print(f"FAILED: {len(failures)}/{len(_HANDLERS)} — {failures}", file=sys.stderr)
        return 1
    print(f"OK: {len(_HANDLERS)}/{len(_HANDLERS)} handlers green")
    return 0


def main() -> None:
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
