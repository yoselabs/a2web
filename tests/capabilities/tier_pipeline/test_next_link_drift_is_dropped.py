"""A URL the model invented never reaches the caller — ADR-0014's wiring half.

`_validate_llm_next_links_against_markdown` drops LLM-supplied `next_links`
whose URL appears neither in the markdown the model was shown nor among the
handler's own links. It has two unit tests, and they are good ones.

**What had no test is that anything CALLS it.** `extraction_drift` — the
diagnostic emitted for each dropped URL — appeared nowhere in the suite.
Deleting the call, or assigning `result.next_links` straight to
`fc.next_links_llm` instead of `validated`, keeps both helper tests green while
a fabricated URL reaches the caller. That is the ADR-0014 harm exactly: *never
surface a URL that isn't on the page.*

This is the fourth instance of that shape found in one session — after the
un-wired `strip_handles`, the archive dispatch faked out of its own test, and
the deadline handler nobody caught. Helper proven, wiring assumed.

**Why an end-to-end case rather than a call-count assertion.** Asserting
`_validate...` was called would pin the implementation, not the property. The
property is that a fabricated URL does not appear on the wire, and it should
survive someone replacing the validator entirely. So the provider fabricates a
URL, the fetch runs for real, and the assertion is about what the caller sees.
"""

from __future__ import annotations

import json

import pytest
from async_scope import lazy

from a2web.fetcher import fetch
from a2web.llm_resource import LlmExtractorResource
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult
from tests._helpers.llm_doubles import DoubleArm
from tests.conftest import make_default_state

_REAL_URL = "https://example.com/real-subpage"
_INVENTED = "https://example.com/reviews"

_PROSE = " ".join(["Ordinary article prose about a topic, long enough to clear the length floor."] * 25)
_PAGE = (
    "<html><head><title>A page</title></head><body><article><p>"
    + _PROSE
    + f"</p><p>See {_REAL_URL} for the real subpage.</p></article></body></html>"
).encode()

# The real URL is page TEXT, not an anchor href, and that is deliberate.
# Trafilatura drops hrefs during extraction, so `fc.content_md` — the string the
# validator checks against — contains no anchor targets at all. A fixture using
# `<a href=...>` has BOTH urls dropped and the "real url survives" assertion
# fails for a reason that has nothing to do with drift. ADR-0014's own wording
# is the guide: traceable means "a URL literally present in the page content".


class _FixedTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        return TierResult(body=_PAGE, content_type="text/html", status_code=200, final_url=url, headers={})


class _FabricatingProvider:
    """Returns one real link and one invented in the classic ADR-0014 shape.

    `…/reviews` is not an arbitrary string — it is the pattern-guessed URL the
    ADR names explicitly ("NEVER guess/construct one by pattern (e.g. appending
    '/reviews')"), and the one measured happening live in
    `findings_2026-07-11-answer-inline-links.md`.
    """

    DOUBLES_ARM = DoubleArm.OFF_CONTRACT
    name = "fabricator"

    @classmethod
    def for_fidelity_check(cls) -> _FabricatingProvider:
        return cls()

    async def complete(self, *, system: str, user: str, model: str, **_: object):
        from a2web.packages.llm_extract import ProviderResponse

        links = [
            {"anchor": "the real subpage", "url": _REAL_URL, "reason": "r", "kind": "drilldown"},
            {"anchor": "reviews", "url": _INVENTED, "reason": "r", "kind": "drilldown"},
        ]
        text = "Here is the answer.\n\n```next_links\n" + json.dumps(links) + "\n```"
        return ProviderResponse(text=text, model=model, prompt_tokens=10, completion_tokens=5, cost_usd=0.0, latency_ms=1)


async def _fetch_with_links(monkeypatch: pytest.MonkeyPatch, *, debug: bool = False):
    monkeypatch.setitem(REGISTRY, "raw", _FixedTier())
    state = make_default_state(settings=AppSettings())
    extractor = LlmExtractorResource(state.settings, state.sqlite, lazy(_FabricatingProvider()))
    return await fetch(
        "https://example.com/page",
        state=state,
        ask="Where are the reviews?",
        next_links=True,
        # The next_links FENCE is only parsed when routing is off: with
        # `include_routing=True` the extractor takes the router-payload path and
        # sets `parsed_next_links = []`, so the drift branch under test never
        # runs. Discovered by this test failing with an `llm_wobble` warning —
        # the double was emitting a fence into a contract expecting a router
        # envelope.
        include_routing=False,
        debug=debug,
        llm_extractor=lazy(extractor),
    )


async def test_the_invented_url_never_reaches_the_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    response = await _fetch_with_links(monkeypatch)
    urls = [nl.url for nl in response.next_links]
    assert _INVENTED not in urls, (
        f"a URL the model invented reached the caller: {_INVENTED!r} in {urls}.\n"
        "ADR-0014: every URL a2web emits must be traceable to the fetched page. This one "
        "is on no page — it is the pattern-guess the ADR names by example."
    )


async def test_the_real_url_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-vacuity, and it is the assertion that matters most here.

    A validator that dropped EVERYTHING would satisfy the test above perfectly
    while destroying link discovery. The defense is only correct if it
    discriminates.
    """
    response = await _fetch_with_links(monkeypatch)
    urls = [nl.url for nl in response.next_links]
    assert _REAL_URL in urls, f"the link that IS on the page was dropped too: {urls}. The validator is not discriminating, it is deleting."


async def test_the_drop_is_recorded_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drop leaves a diagnostic naming the URL.

    Silently discarding is the wrong shape even when the discard is right: an
    operator seeing repeated `extraction_drift` for one host learns the model is
    guessing there, which is a prompt problem. No row, no signal.
    """
    # `debug=True` because `fetch()` clears `response.diagnostics` entirely when
    # it is off (the v0.3 envelope diet, `fetcher/__init__.py`). The row IS
    # recorded either way — this is about the channel an operator can read, and
    # confirming it survives to the boundary rather than being built and binned.
    response = await _fetch_with_links(monkeypatch, debug=True)
    drift = [d for d in response.diagnostics if d.extra.get("event") == "extraction_drift"]
    assert drift, "the invented URL was dropped without a diagnostic — the drop is invisible to an operator"
    assert drift[0].extra.get("url") == _INVENTED
    assert drift[0].step == "extract_answer.next_links"
    assert drift[0].verdict is Verdict.other
