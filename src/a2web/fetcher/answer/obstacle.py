"""The two re-render decisions — an unretrieved obstacle, and a partial listing."""

from __future__ import annotations

from ...fetcher_response import _INCOMPLETE_OBSTACLES
from ...packages.block_detector import looks_like_unrendered_spa
from ...settings import AppSettings
from ...state import AppState
from ..context import FetchContext
from ..retrieval.escalate.paid import paid_budget_available
from ..retrieval.escalate.seam import Rung, escalate

# Tiers that already execute JavaScript, so re-rendering their output via the
# paid tier would return the same content — the obstacle render is redundant.
_JS_EXECUTED_TIERS = frozenset({"jina", "browser", "browser_robust"})

# Above this much extracted content, the page is treated as complete (SSR /
# static): the answer's absence is real and a render can't add it. Only a THIN
# result (in the (LENGTH_FLOOR, ceiling) window) is plausibly an unrendered
# shell worth a render. This is the load-bearing guard for SSR framework sites
# (Next/Nuxt), which carry SPA mount markers yet already contain their content —
# markers alone can't tell an SSR page from a CSR shell.
_RENDER_CONTENT_CEILING = 2000


def _obstacle_wants_render(fc: FetchContext) -> bool:
    """True when the extractor's obstacle should drive one paid render.

    Gated hard on cost:
    - the ask path (obstacle exists only there);
    - an `empty`/`blocked` obstacle (`_INCOMPLETE_OBSTACLES` — shared with the
      retrieval-completeness logic so the trigger stays in lockstep;
      `paywalled`/`error` are excluded — a render won't clear a paywall);
    - an unspent paid budget (`paid_dispatches < 1`, so a prior gate/handler
      render suppresses this);
    - **evidence a render would actually add content** (the false-positive
      guard): the content did NOT come from a JS-executing tier (jina/browser
      already ran JS, so a render is redundant); the extracted content is THIN
      (`< _RENDER_CONTENT_CEILING`, so plausibly an unrendered shell rather than
      a complete SSR/static page that merely lacks the answer — the load-bearing
      check for Next/Nuxt SSR sites, which carry SPA markers yet already contain
      their content); AND the raw body shows unrendered-SPA markers. A complete
      page (a spec doc, a book, any content-rich SSR page) is NOT re-rendered.
    """
    if fc.inputs.ask is None or fc.routing is None:
        return False
    if not paid_budget_available(fc):
        return False
    if fc.routing.obstacle not in _INCOMPLETE_OBSTACLES:
        return False
    if fc.tier_used in _JS_EXECUTED_TIERS:
        return False
    if len(fc.content_md) >= _RENDER_CONTENT_CEILING:
        return False
    raw = fc.body.decode("utf-8", errors="replace") if fc.body else ""
    return looks_like_unrendered_spa(raw)


async def _phase_obstacle_render(fc: FetchContext, *, state: AppState) -> bool:
    """Attempt one paid render when the extractor flagged an unretrieved obstacle.

    The extractor is the only component that can say "the answer isn't in this
    content" (a fat SPA shell that passed the gate). When it reports
    `obstacle ∈ {empty, blocked}`, dispatch one paid render of the original URL —
    `escalate` installs the rendered content and comprehends it. If the render
    produced nothing new (no paid tier keyed, failure, or an identical body), the
    v0.29.0 `retrieval_incomplete` signal stands (never-silently-miss). Bounded
    to one render + one extra LLM call.

    Returns whether the content changed. It does NOT re-run the answer itself:
    `_phase_answer` owns that, so the number of LLM calls a fetch makes is
    countable at one place instead of being a property of which render phases
    happened to fire.
    """
    if not _obstacle_wants_render(fc):
        return False
    prev_md = fc.content_md
    await escalate(fc, Rung.paid, state=state)
    # No new content (unavailable / failed / paid_auth_error hard-stop /
    # identical shell) — leave the obstacle-flagged answer; the surviving
    # obstacle drives retrieval_incomplete in build_ask_response.
    return fc.content_md != prev_md


def _listing_wants_render(fc: FetchContext, *, settings: AppSettings) -> bool:
    """True when a partial listing should drive one bounded scrolling render.

    Gated on cost + product surface (listing-completeness Slice 2):
    - `complete_listings` is enabled (the operator opted into paid egress on
      the common listing path);
    - the ask path is active (scroll-to-complete is the distilled-answer
      product; `fetch_raw` is signal-only);
    - the listing was flagged partial (`items_total` set by
      `_phase_listing_completeness`);
    - the shared paid budget is unspent (`paid_dispatches < 1` — one render per
      fetch, shared with the gate-wall and obstacle triggers);
    - the content did NOT come from a JS-executing tier (jina/browser already
      ran JS, so a scroll render is redundant);
    - the oracle is within the completeness ceiling (`listing_scroll_max`) —
      above it (a broad search with thousands of hits) the response steers
      toward a narrower query rather than scrolling the universe.
    """
    if not settings.complete_listings:
        return False
    if fc.inputs.ask is None:
        return False
    if fc.items_total is None:
        return False
    if not paid_budget_available(fc):
        return False
    if fc.tier_used in _JS_EXECUTED_TIERS:
        return False
    return fc.items_total <= settings.listing_scroll_max


async def _phase_listing_render(fc: FetchContext, *, state: AppState) -> bool:
    """Complete a partial listing with one bounded scrolling render (Slice 2 / 2b).

    Free own-browser first, paid egress second (spec: own-browser preferred).
    When `browser_enabled`, a free browser render scrolls the original URL to
    stable; only if that changed nothing (browser off / unavailable / failed) and
    the single paid budget remains does the paid Zyte scroll fire. Either render
    re-counts the records the fuller page yields (via the shared extraction
    escalation) and the listing is re-assessed: complete → the `listing_partial`
    signal is dropped (fields nulled); still short (a capped or DOM-virtualised
    scroll) → the signal stands with the updated count, the miss loud. If nothing
    rendered, the Slice 1 signal stands unchanged.
    """
    if not _listing_wants_render(fc, settings=state.settings):
        return False
    prev_md = fc.content_md
    # Free own-browser scroll first — no egress cost, just latency.
    if state.settings.browser_enabled:
        await escalate(fc, Rung.browser, state=state, scroll=True)
    # Paid fallback only if the free attempt changed nothing and budget remains.
    if fc.content_md == prev_md and paid_budget_available(fc):
        await escalate(fc, Rung.paid, state=state, scroll=True)
    if fc.content_md == prev_md:
        return False  # nothing rendered → the partial signal stands (never-silently-miss).
    # The re-assessment is NOT re-implemented here any more. `escalate` ran
    # `_comprehend`, which re-ran `_phase_listing_completeness` over the fuller
    # page: complete → the signal is cleared, still short → it stands with the
    # updated count. This block existed only because there was no loop head to
    # return to, and it read the OLD `fc.items_total` where the loop head reads
    # the re-rendered page's own oracle.
    return True
