"""Domain seam: `{{n}}` handles in `other_pages` rehydrate against the closed digest.

Proves the wiring between the parsed router payload (handles) and the digest
(closed set): known handles become real hrefs + off_domain; unknown handles are
dropped, never guessed; legacy url-bearing entries pass through.
"""

from __future__ import annotations

import pytest
from async_scope import lazy

from a2web.fetcher import _rehydrate_routing_handles, fetch
from a2web.link_digest import _HANDLE_RE, build_digest, strip_handles
from a2web.llm_resource import LlmExtractorResource
from a2web.models import Link
from a2web.packages.llm_extract import OtherPageBoundary, RouterPayload
from a2web.settings import AppSettings
from a2web.state import AppState
from a2web.tiers import REGISTRY, TierResult
from tests._helpers.llm_doubles import DoubleArm, honor_contract
from tests.conftest import make_default_state

PAGE = "https://shop.example.com/p/widget"


def _digest() -> object:
    return build_digest(
        [
            Link(anchor="reviews", href="/p/widget-yorumlari"),
            Link(anchor="partner", href="https://other.example.org/x"),
        ],
        page_url=PAGE,
    )


def _payload(*entries: OtherPageBoundary) -> RouterPayload:
    return RouterPayload(answer="a", structural_form="product", shape="key-value", other_pages=tuple(entries))


def test_known_handle_rehydrates_with_off_domain() -> None:
    digest = _digest()  # handle 1 = same-domain reviews, handle 2 = off-domain
    routing = _payload(
        OtherPageBoundary(url="", reason="reviews here", handle=1),
        OtherPageBoundary(url="", reason="partner", handle=2),
    )
    out = _rehydrate_routing_handles(routing, digest)
    assert out is not None
    assert out.other_pages[0].url == "https://shop.example.com/p/widget-yorumlari"
    assert out.other_pages[0].off_domain is False
    assert out.other_pages[0].handle is None
    assert out.other_pages[1].url == "https://other.example.org/x"
    assert out.other_pages[1].off_domain is True


def test_unknown_handle_dropped() -> None:
    digest = _digest()
    routing = _payload(OtherPageBoundary(url="", reason="nope", handle=99))
    out = _rehydrate_routing_handles(routing, digest)
    assert out is not None
    assert out.other_pages == ()


def test_legacy_url_entry_passes_through() -> None:
    digest = _digest()
    routing = _payload(OtherPageBoundary(url="https://x.example/", reason="legacy"))
    out = _rehydrate_routing_handles(routing, digest)
    assert out is not None
    assert len(out.other_pages) == 1
    assert out.other_pages[0].url == "https://x.example/"


def test_handle_with_no_digest_is_dropped() -> None:
    routing = _payload(OtherPageBoundary(url="", reason="orphan", handle=1))
    out = _rehydrate_routing_handles(routing, None)
    assert out is not None
    assert out.other_pages == ()


def test_none_routing_passes_through() -> None:
    assert _rehydrate_routing_handles(None, _digest()) is None


# --------------------------------------------------------------------- #
# ADR-0013, the no-digest branch — added 2026-08-03, after a real leak
# --------------------------------------------------------------------- #


def test_a_handle_never_survives_without_a_digest() -> None:
    """**The branch that leaked.** A `{{n}}` must not reach the caller, ever.

    `_build_link_digest` returns `None` for a prose-only article — no links, or
    no structured candidate. The `LINKS IN THE ANSWER` clause that teaches the
    model the `{{n}}` convention lives in the BASE prompt and ships
    unconditionally. So on those pages the model was taught the convention,
    given no link list, and `prompt_call.py` passed its answer through
    untouched: a comment reading "no-op when no digest was fed", which sounds
    safe and was not.

    Demonstrated before the fix: `"Reviews are on a separate page: {{1}}"` in,
    the same string out. CLAUDE.md meanwhile claimed the answer prose "is
    rehydrated so a stray `{{n}}` becomes a real URL or is dropped, never
    leaked" — true only in the branch that had a digest.

    Not the ADR-0014 fabricated-URL harm, so worth stating what it IS: a token
    an agent can reasonably mistake for content, emitted by the one subsystem
    whose whole job is not doing that.
    """
    answer = "Reviews are on a separate page: {{1}} and specs at {{2}}."
    assert strip_handles(answer) == "Reviews are on a separate page:  and specs at ."
    assert not _HANDLE_RE.search(strip_handles(answer))


def test_stripping_leaves_ordinary_prose_alone() -> None:
    """Only the delimited form is touched.

    Braces appear in real page content — code samples, template syntax, JSON.
    A stripper that ate `{n}` or `{{word}}` would corrupt answers about exactly
    the technical pages a2web is most often pointed at.
    """
    for text in ("use {n} for the index", "a dict literal {{'a': 1}}", "f-string {value} here", "no braces at all"):
        assert strip_handles(text) == text


def test_the_two_branches_agree_that_an_unknown_handle_vanishes() -> None:
    """The invariant stated once across both paths.

    With a digest, an unknown handle is dropped by `rehydrate_text`; without
    one, by `strip_handles`. Asserting them together is what makes this a rule
    about the SEAM rather than two coincidentally-similar functions — if a
    future change makes the digest branch leak unknown handles, this fails even
    though that branch's own tests would still pass.
    """
    digest = build_digest([Link(anchor="A", href="https://e.com/a")], page_url="https://e.com/")
    text = "see {{99}}"
    assert not _HANDLE_RE.search(digest.rehydrate_text(text))
    assert not _HANDLE_RE.search(strip_handles(text))


# --------------------------------------------------------------------- #
# The call site, end to end. The three tests above pass with the fix
# REVERTED — they exercise `strip_handles`, not the line that calls it.
# Verified by mutation: swapping `strip_handles(result.answer)` back to
# `result.answer` left all of them green. A helper proven correct and not
# proven wired is the shape this repo keeps finding.
# --------------------------------------------------------------------- #

_PROSE = " ".join(["A paragraph of ordinary article prose with no structured data anywhere in it."] * 30)
_ARTICLE = (
    "<html><head><title>An article</title></head><body><article><p>"
    + _PROSE
    + '</p><p>See <a href="https://e.com/other">another page</a>.</p></article></body></html>'
).encode()


class _FixedTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        return TierResult(body=_ARTICLE, content_type="text/html", status_code=200, final_url=url, headers={})


class _HandleEmittingProvider:
    """A model that uses the `{{n}}` convention it was taught, with no list to draw on.

    Not a contrived double: the `LINKS IN THE ANSWER` clause explaining `{{n}}`
    sits in the BASE prompt and is sent on every extraction, including the ones
    that get no digest. A model emitting a handle here is following its
    instructions.
    """

    DOUBLES_ARM = DoubleArm.ROUTER_FAITHFUL
    name = "handle-emitter"

    @classmethod
    def for_fidelity_check(cls) -> _HandleEmittingProvider:
        return cls()

    async def complete(self, *, system: str, user: str, model: str, **_: object):
        from a2web.packages.llm_extract import ProviderResponse

        answer = "The details are on a separate page: {{1}}"
        return ProviderResponse(
            text=honor_contract(answer, system), model=model, prompt_tokens=10, completion_tokens=5, cost_usd=0.0, latency_ms=1
        )


async def test_no_handle_reaches_the_caller_on_a_page_with_no_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end: prose-only article, model emits `{{1}}`, caller must not see it.

    A prose article has links but no json_synth/record_synth candidate, so
    `_build_link_digest` returns `None` — the branch that used to pass the
    answer through untouched.
    """
    monkeypatch.setitem(REGISTRY, "raw", _FixedTier())
    state = make_default_state(settings=AppSettings())
    provider = _HandleEmittingProvider()
    extractor = LlmExtractorResource(state.settings, state.sqlite, lazy(provider))

    result = await fetch(
        "https://e.com/article",
        state=state,
        ask="Where are the details?",
        llm_extractor=lazy(extractor),
    )

    assert result.extracted_answer is not None, "the stub provider's answer did not reach the response"
    assert not _HANDLE_RE.search(result.extracted_answer), (
        f"a raw `{{{{n}}}}` handle reached the caller: {result.extracted_answer!r}\n"
        "`_build_link_digest` returns None for a prose-only page, and the prompt clause "
        "teaching the handle convention ships unconditionally — so this branch must STRIP, "
        "not pass through."
    )
