# ruff: noqa: T201 — CLI tool, print is the output channel
"""Live-contract handler probe — exercises every registered handler against
real URLs, on every shape it serves, with no monkeypatching.

Purpose: catch what unit tests structurally cannot see. Two failure classes,
and the probe missed the second one for months.

**Transport rot.** A handler that hand-rolls its own httpx transport looks green
under tests that monkeypatch the seam while the live network fails (the linux.do
Cloudflare block was invisible until production). Fetching for real catches it.

**Parse rot.** A handler whose selectors stop matching does not raise — it
returns `[]`, renders a body saying so, and reports `Verdict.ok`. The arXiv
listing parser did exactly this while the probe called it healthy, because the
probe asked only "is `content_md` non-empty?" and `## Papers (0)` is non-empty.
Worse, arXiv's dead parser was on `/list/…` and the probe only ever fetched
`/abs/…` — the broken shape was not probed at all.

So each case declares the YIELD a working handler produces at that URL — a
content floor, a candidate floor, and prose naming the property checked — and
every shape a handler serves gets its own case.

Loud-failure invariants:
- Every entry in the `a2web.handlers` manifest registry MUST have at least one
  `_PROBE_CASES` entry. Missing → non-zero exit naming the offender.
- A case below any declared floor FAILS, even at `Verdict.ok`.
- A handler blocked from this network stays declared and stays RED. Removing it
  or zeroing its floors would convert a known-blocked handler into a silently
  unprobed one, which is the condition this whole file exists to prevent.

Floors are set BELOW observed working values, never at them. A floor pinned to
what the site served on the day it was written is a golden: it fails on content
rotation rather than on rot, and it trains its reader to ignore it.

The candidate floors are additionally guarded OFFLINE, in `make check`, by
`tests/capabilities/site_handlers/test_probe_case_table.py` — this file is
live-network and runs on demand, so nothing here stops a floor from being edited
to zero to turn a red probe green. That edit is the same weakening that let the
dead parser pass.

Run with `make handler-probe`. Not wired into `make check`. Live-network.
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .handlers import _registry as _handler_registry
from .models import Verdict
from .settings import AppSettings

if TYPE_CHECKING:
    from .handlers import Handler


@dataclass(frozen=True, slots=True)
class ProbeCase:
    """One handler, one URL, and what a working handler yields there.

    `checks` is required even where the assertion is weak. Its job is to let a
    later reader tell a deliberately weak assertion from an overlooked one —
    which a field nobody had to fill would not do.
    """

    url: str
    shape: str  # "listing" | "detail"
    min_chars: int
    min_candidates: int
    checks: str


# Every registered handler, every shape it serves. Comments carry the value
# OBSERVED on 2026-07-28; the floor sits below it, and the gap is the margin for
# a quiet day on the site.
_PROBE_CASES: dict[str, tuple[ProbeCase, ...]] = {
    "site_handler:reddit": (
        # BLOCKED from this network without a proxy, both shapes, measured
        # 2026-07-28: detail → not_found, listing → block_page_detected. The
        # floors below are what a WORKING reddit yields, and they stay. See the
        # module docstring: a removed case is worse than a red one.
        ProbeCase(
            url="https://www.reddit.com/r/IAmA/comments/z1c9z/i_am_barack_obama_president_of_the_united_states/",
            shape="detail",
            min_chars=2000,
            min_candidates=0,
            checks="comment thread renders; no candidate index on a detail page",
        ),
        ProbeCase(
            url="https://www.reddit.com/r/LocalLLaMA/",
            shape="listing",
            min_chars=1000,
            min_candidates=5,
            checks="subreddit listing yields post drilldown candidates",
        ),
    ),
    "site_handler:hn": (
        ProbeCase(
            url="https://news.ycombinator.com/item?id=39000000",
            shape="detail",
            min_chars=800,  # observed 1841
            min_candidates=0,
            checks="story + comment tree renders via the Algolia item API",
        ),
        ProbeCase(
            url="https://news.ycombinator.com/",
            shape="listing",
            min_chars=2000,  # observed 6836
            min_candidates=5,  # observed 10 (the cap)
            checks="front page yields story drilldown candidates",
        ),
    ),
    "site_handler:arxiv": (
        ProbeCase(
            url="https://arxiv.org/abs/2308.08155",
            shape="detail",
            min_chars=500,  # observed 1139
            min_candidates=0,
            checks="abstract page renders title + abstract",
        ),
        ProbeCase(
            # The shape the dead parser lived on. Never probed before 2026-07-28.
            url="https://arxiv.org/list/cs.CL/recent",
            shape="listing",
            min_chars=1000,  # observed 4971 (was 40 while the parser was dead)
            min_candidates=5,  # observed 10 (the cap); was 0
            checks="dl#articles dt/dd pairs parsed into abs drilldown candidates",
        ),
    ),
    "site_handler:wikipedia": (
        ProbeCase(
            url="https://en.wikipedia.org/wiki/Python_(programming_language)",
            shape="detail",
            min_chars=10000,  # observed 49121
            # Half the wikilink parse is verdict-guarded since 2026-08-02 (the
            # container is `body.mw-parser-output`, so non-Parsoid input is
            # ROT), but the ROW selector cannot be: "an article that links
            # nowhere" is a legitimate page state, so a rotted row selector
            # still reads as EMPTY. This floor is the only LIVE check on that
            # half. Do not zero it.
            min_candidates=5,  # observed 10 (the cap); was 0 while the parser was dead
            checks="article body renders AND rel=mw:WikiLink anchors yield candidates",
        ),
    ),
    "site_handler:github": (
        ProbeCase(
            url="https://github.com/anthropics/anthropic-sdk-python",
            shape="detail",
            min_chars=500,  # observed 1194
            min_candidates=5,  # observed 10 — repo sub-page candidates
            checks="repo metadata renders and sub-page candidates are built",
        ),
    ),
    "site_handler:twitter": (
        # Every public nitter instance tried on 2026-07-28 was dead or walled:
        # nitter.privacydev.net → connection_error, nitter.net → length_floor,
        # xcancel.com → HTTP 200 serving a browser-verification interstitial
        # that the handler reports as Verdict.ok. This floor makes that a
        # failure. The upstream may simply be gone; see BACKLOG.
        ProbeCase(
            url="https://twitter.com/anthropicai/status/1701832836929187894",
            shape="detail",
            min_chars=500,  # the interstitial renders 416 — below this on purpose
            min_candidates=0,
            checks="tweet text renders via a nitter instance (upstream currently walled)",
        ),
    ),
    "site_handler:discourse": (
        # linux.do is unreachable from here (connection_error, measured
        # 2026-07-28). meta.discourse.org is the reference Discourse install and
        # is in the default host allowlist.
        ProbeCase(
            url="https://meta.discourse.org/latest",
            shape="listing",
            min_chars=1000,  # observed 4237
            # Was `min_candidates=10, # observed 30`. Thirty is THREE TIMES the
            # stated cap (`link-discovery` spec: "capped at 10 entries"), and
            # this baseline recorded it as healthy — so the probe pinned the
            # violation green rather than catching it. A baseline that records
            # an out-of-contract observation as the expected one is worse than
            # no baseline: it reads as a decision.
            min_candidates=10,  # observed 10 (== NEXT_LINKS_CAP)
            checks="/latest.json topic list yields topic drilldown candidates",
        ),
        ProbeCase(
            # Topic #1, the pinned welcome topic — durable by construction.
            url="https://meta.discourse.org/t/new-to-discourse-start-here/1",
            shape="detail",
            min_chars=1000,  # observed 2650
            min_candidates=0,
            checks="topic JSON renders the post tree; no index on a topic page",
        ),
    ),
    "site_handler:habr": (
        ProbeCase(
            url="https://habr.com/ru/articles/1032730/",
            shape="detail",
            min_chars=2000,  # observed 20977
            min_candidates=0,
            checks="article body renders; habr handler builds no index",
        ),
    ),
    "site_handler:v2ex": (
        ProbeCase(
            url="https://www.v2ex.com/t/1000000",
            shape="detail",
            min_chars=1000,  # observed 5893
            min_candidates=0,
            checks="topic + replies render; v2ex handler builds no index",
        ),
    ),
}

# The nitter instance that at least answers. The others were measured dead.
_PROBE_SETTINGS = AppSettings(nitter_instances=["xcancel.com"])


async def _probe_one(handler: Handler, case: ProbeCase, *, timeout_s: float = 30.0) -> tuple[bool, str]:
    """Run one case. Returns (ok, summary).

    `ok` requires `verdict == ok` AND both declared floors met — a handler that
    returns `ok` while yielding nothing is the defect, not a pass.
    """
    from tests.conftest import make_default_state

    state = make_default_state(settings=_PROBE_SETTINGS)

    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(handler.fetch(case.url, state=state), timeout=timeout_s)
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
    chars = len(pre.content_md.strip()) if pre is not None and pre.content_md else 0
    candidates = len(result.next_links)
    observed = f"{chars} chars, {candidates} candidates ({wall_ms}ms)"

    # Report BOTH numbers on failure. "below floor" without them is not a usable
    # message — the reader needs to know whether the site moved or the parse died.
    shortfalls: list[str] = []
    if chars < case.min_chars:
        shortfalls.append(f"chars {chars} < {case.min_chars}")
    if candidates < case.min_candidates:
        shortfalls.append(f"candidates {candidates} < {case.min_candidates}")
    if shortfalls:
        return False, f"verdict=ok but {'; '.join(shortfalls)} — {observed}"

    return True, f"ok ({observed})"


async def _main() -> int:
    handlers = _handler_registry(None)
    # Loud-failure: every registered handler MUST have at least one case. An
    # empty tuple counts as missing — it would otherwise satisfy the key check
    # while probing nothing.
    registered = {h.name for h in handlers}
    mapped = {name for name, cases in _PROBE_CASES.items() if cases}
    missing = registered - mapped
    extra = set(_PROBE_CASES) - registered
    if missing or extra:
        if missing:
            print(f"FAIL: registered handler(s) with no probe case: {sorted(missing)}", file=sys.stderr)
        if extra:
            print(f"FAIL: _PROBE_CASES entries with no registered handler: {sorted(extra)}", file=sys.stderr)
        return 2

    failures: list[str] = []
    total = 0
    for handler in handlers:
        for case in _PROBE_CASES[handler.name]:
            total += 1
            ok, summary = await _probe_one(handler, case)
            marker = "PASS" if ok else "FAIL"
            print(f"[{marker}] {handler.name:26s} {case.shape:8s} {case.url}")
            # Print what was ASSERTED, not only whether it held — a green run
            # that does not say what it checked is how this file went stale.
            print(f"        checks: {case.checks}")
            print(f"        floors: >={case.min_chars} chars, >={case.min_candidates} candidates")
            print(f"        {summary}")
            if not ok:
                failures.append(f"{handler.name}[{case.shape}]")

    print()
    if failures:
        print(f"FAILED: {len(failures)}/{total} cases — {failures}", file=sys.stderr)
        return 1
    print(f"OK: {total}/{total} cases green")
    return 0


def main() -> None:
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
