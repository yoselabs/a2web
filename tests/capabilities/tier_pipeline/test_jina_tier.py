"""JinaTier tests — auth header, deny-list, wrapper unwrap, pre_rendered payload.

The transport seam moved on 2026-08-02: jina used to hand-roll an
`httpx.AsyncClient`, and these tests patched `httpx.AsyncClient`. It now goes
through the shared `http_fetch.fetch_bytes` primitive (browser TLS
impersonation, the `FetchVerdict` closed enum, and a real circuit breaker), so
the fake is installed one layer down at `http_fetch.fetch.cr.AsyncSession` —
the same seam `tests/capabilities/raw_tier/test_raw_tier.py` uses. Everything
above the transport is the tier's own code, unchanged and still under test.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from curl_cffi.requests import exceptions as ce
from purgatory import AsyncCircuitBreakerFactory

from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.tiers.jina import JinaTier
from tests.conftest import make_default_state

if TYPE_CHECKING:
    from a2web.state import AppState


def _state(**kwargs: object) -> AppState:
    return make_default_state(settings=AppSettings(**kwargs))


class _FakeSession:
    """Stands in for `curl_cffi.requests.AsyncSession` inside `fetch_bytes`."""

    def __init__(self, payload: SimpleNamespace | BaseException) -> None:
        self._payload = payload
        self.requests: list[dict[str, Any]] = []

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> SimpleNamespace:
        self.requests.append({"url": url, **kwargs})
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


def _response(*, text: str = "md", status: int = 200) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=status,
        content=text.encode("utf-8"),
        url="https://r.jina.ai/x",
        headers={"content-type": "text/markdown"},
    )


def _mock_jina(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text: str = "md",
    status: int = 200,
    raises: BaseException | None = None,
) -> _FakeSession:
    fake = _FakeSession(raises if raises is not None else _response(text=text, status=status))
    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", lambda **_: fake)
    return fake


# --- transport plumbing ---


async def test_free_tier_omits_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _mock_jina(monkeypatch, text="# Hello\n\nbody")

    result = await JinaTier().fetch("https://example.com/", state=_state(jina_key=""))

    sent = fake.requests[0]["headers"]
    assert "authorization" not in {k.lower() for k in sent}
    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None
    assert result.pre_rendered.content_md == "# Hello\n\nbody"


async def test_authorized_tier_sends_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _mock_jina(monkeypatch)

    await JinaTier().fetch("https://example.com/", state=_state(jina_key="secret123"))

    assert fake.requests[0]["headers"]["Authorization"] == "Bearer secret123"


async def test_the_reader_is_asked_for_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `X-Return-Format` header survived the transport swap.

    Not decoration: this header is what inflates a wrapper-stub body past any
    fixed size, which is how the retired `_STUB_MAX_BODY` ceiling came to disarm
    the unwrap. Losing it silently would change what the unwrap tests below are
    even testing.
    """
    fake = _mock_jina(monkeypatch)

    await JinaTier().fetch("https://example.com/page", state=_state())

    request = fake.requests[0]
    assert request["url"] == "https://r.jina.ai/https://example.com/page"
    assert request["headers"]["X-Return-Format"] == "markdown"


async def test_final_url_is_target_not_jina_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """`final_url` must be the requested TARGET, never the r.jina.ai wrapper.

    Regression guard: leaking `https://r.jina.ai/<url>` as final_url both
    surfaced the wrapper on the response `url` and misdirected browser
    escalation onto r.jina.ai instead of the real page. The primitive returns
    its own `final_url` (always the wrapper), so the tier must keep overriding
    it — the swap made this MORE load-bearing, not less.
    """
    _mock_jina(monkeypatch, text="thin")

    target = "https://www.incehesap.com/arama/?kelime=deepcool"
    result = await JinaTier().fetch(target, state=_state())

    assert result.final_url == target
    assert "r.jina.ai" not in result.final_url


async def test_deny_list_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Denied host must NOT issue an HTTP call."""
    fake = _mock_jina(monkeypatch)

    state = _state(jina_deny_hosts=["intranet.example.com"])
    result = await JinaTier().fetch("https://wiki.intranet.example.com/page", state=state)

    assert fake.requests == []
    assert result.skipped is True
    assert result.verdict == Verdict.other


# --- the breaker is the READER's, not the target's ---


async def test_the_breaker_is_keyed_on_the_reader_not_the_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """A target-host breaker would be the SAME one the raw tier trips.

    A host that just failed on raw would then short-circuit jina before it was
    tried — the ladder's second rung disabled by the first rung's failure, which
    is the opposite of what a fallback tier is for. Asserted by making the
    TARGET's breaker already open and checking jina still dials.
    """
    fake = _mock_jina(monkeypatch, text="body")
    state = _state()
    state.breakers = AsyncCircuitBreakerFactory(default_threshold=1, default_ttl=300.0)

    target_breaker = await state.breakers.get_breaker("example.com")
    with pytest.raises(RuntimeError):
        async with target_breaker:
            msg = "the raw tier failed this host"
            raise RuntimeError(msg)
    assert target_breaker.context.state == "opened"

    result = await JinaTier().fetch("https://example.com/page", state=state)

    assert len(fake.requests) == 1, "jina was blocked by the TARGET's breaker"
    assert result.verdict == Verdict.ok


async def test_reader_failures_open_the_reader_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    """The anti-vacuity half — jina must still HAVE a breaker, on `r.jina.ai`.

    Without this, "pass `breaker=None`" would satisfy the test above.
    """
    _mock_jina(monkeypatch, raises=ce.ConnectionError("reader down"))
    state = _state()
    state.breakers = AsyncCircuitBreakerFactory(default_threshold=2, default_ttl=300.0)

    for _ in range(2):
        result = await JinaTier().fetch("https://example.com/page", state=state)
        assert result.verdict == Verdict.connection_error

    reader_breaker = await state.breakers.get_breaker("r.jina.ai")
    assert reader_breaker.context.state == "opened"


async def test_conditional_extras_are_never_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cache is keyed `(url, profile_hash)` with no record of which tier
    produced the entry, so an `etag` in hand may have come from a RAW fetch of
    the origin. Sending it to `r.jina.ai` asks a conditional question about a
    different resource. This is not an improvement waiting to be made.
    """
    fake = _mock_jina(monkeypatch)

    await JinaTier().fetch(
        "https://example.com/",
        state=_state(),
        conditional_extras={"etag": '"from-a-raw-fetch"', "last_modified": "Wed, 21 Oct"},
    )

    sent = {k.lower(): v for k, v in fake.requests[0]["headers"].items()}
    assert "if-none-match" not in sent
    assert "if-modified-since" not in sent


# --- Reader-wrapper unwrap: jina 200 masking an upstream error ---


async def test_wrapped_404_surfaces_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """A jina 200 whose body is an upstream-404 stub → tier reports
    not_found/404, does NOT win the loop (no pre_rendered)."""
    body = "Title: x\n\nURL Source: https://x.com/gone\n\nWarning: Target URL returned error 404: Not Found\n\nMarkdown Content:\n# x\n"
    _mock_jina(monkeypatch, text=body)
    result = await JinaTier().fetch("https://x.com/gone", state=_state())
    assert result.verdict == Verdict.not_found
    assert result.status_code == 404
    assert result.pre_rendered is None


async def test_verbose_wrapped_404_is_still_decoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrapped upstream 404 is decoded at ANY body length.

    Non-vacuity guard (design D6): the body is deliberately pushed past 2048
    bytes — the old `_STUB_MAX_BODY` ceiling — so reintroducing a length gate
    fails this test instead of passing it silently. This is the exact shape that
    shipped the bug: a2web's own `X-Return-Format: markdown` header inflates the
    wrapper body (measured 3030 bytes on a real fat 404 page) past the ceiling,
    which disarmed the decode and laundered the 404 into `ok`/`confidence: high`.
    """
    body = (
        "Title: BH Klima\n\n"
        "URL Source: https://example.com/urun/1446\n\n"
        "Warning: Target URL returned error 404: Not Found\n\n"
        "Markdown Content:\n" + ("Nav chrome and footer boilerplate. " * 100)
    )
    assert len(body) > 2048, "Guard must be exercised above the retired ceiling"
    _mock_jina(monkeypatch, text=body)
    result = await JinaTier().fetch("https://example.com/urun/1446", state=_state())
    assert result.verdict == Verdict.not_found
    assert result.status_code == 404
    assert result.pre_rendered is None


async def test_wrapped_403_maps_to_paywall(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrapped 401/403 → paywall, preserving the archive-on-paywall routing."""
    body = "Title: nyt\n\nWarning: Target URL returned error 403: Forbidden\n\nMarkdown Content:\n# nyt\n"
    _mock_jina(monkeypatch, text=body)
    result = await JinaTier().fetch("https://nytimes.com/x", state=_state())
    assert result.verdict == Verdict.paywall
    assert result.status_code == 403


async def test_wrapped_401_maps_to_paywall(monkeypatch: pytest.MonkeyPatch) -> None:
    body = "Title: wsj\n\nWarning: Target URL returned error 401: Unauthorized\n\nMarkdown Content:\n# wsj\n"
    _mock_jina(monkeypatch, text=body)
    result = await JinaTier().fetch("https://wsj.com/x", state=_state())
    assert result.verdict == Verdict.paywall
    assert result.status_code == 401


async def test_long_body_quoting_error_string_is_not_unwrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """An article that merely QUOTES the stub string is not misread as a wrapper.

    The quotation sits AFTER the `Markdown Content:` separator — i.e. in the body
    region, never in jina's own header block — which is what makes it safe. The
    body is also well over 2048 bytes, so this passes on the POSITIONAL guard and
    not on any length ceiling.
    """
    body = "Markdown Content:\n" + ("Lorem ipsum dolor sit amet. " * 200) + "\nThe paper cited `Target URL returned error 403`.\n"
    assert len(body) > 2048, "The false-positive guard must hold at large body sizes"
    _mock_jina(monkeypatch, text=body)
    result = await JinaTier().fetch("https://blog.example/post", state=_state())
    assert result.verdict == Verdict.ok
    assert result.pre_rendered is not None


# --- transport verdict mapping ---


async def test_429_maps_to_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_jina(monkeypatch, text="rate", status=429)

    result = await JinaTier().fetch("https://example.com/", state=_state())

    assert result.verdict == Verdict.rate_limited
    assert result.pre_rendered is None


async def test_404_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_jina(monkeypatch, text="", status=404)
    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.not_found


async def test_500_maps_to_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_jina(monkeypatch, text="", status=503)
    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.connection_error


async def test_other_4xx_maps_to_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """403/401/410 etc — only 404 and 429 are special-cased."""
    _mock_jina(monkeypatch, text="", status=403)
    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.connection_error


async def test_timeout_maps_to_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_jina(monkeypatch, raises=ce.Timeout("slow"))
    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.timeout


async def test_generic_connection_error_maps_to_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_jina(monkeypatch, raises=ce.ConnectionError("refused"))
    result = await JinaTier().fetch("https://example.com/", state=_state())
    assert result.verdict == Verdict.connection_error


async def test_proxy_error_maps_to_proxy_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_jina(monkeypatch, raises=ce.RequestException("proxy tunnel refused"))
    result = await JinaTier().fetch(
        "https://example.com/",
        state=_state(),
        proxy_url="http://proxy:8080",
    )
    assert result.verdict == Verdict.proxy_unavailable


async def test_reader_dns_failure_is_not_reported_as_a_dead_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """The verdict this tier must NOT pass through.

    `FetchVerdict.dns_error` means the name being dialled did not resolve — and
    on this tier that name is `r.jina.ai`, never the target. `Verdict.dns_error`
    is TERMINAL by design (the planner leaves it alone: a real browser cannot
    resolve a nonexistent domain either), so passing it through would tell the
    planner the target does not exist, on evidence that says nothing about the
    target. The reader being unreachable is a connection failure of this tier,
    and the ladder must be free to continue past it.

    `raw.py` maps the same verdict straight through, correctly — there the
    unresolvable name IS the target. The two tables differ on purpose.
    """
    _mock_jina(monkeypatch, raises=ce.DNSError("r.jina.ai does not resolve"))

    result = await JinaTier().fetch("https://example.com/", state=_state())

    assert result.verdict == Verdict.connection_error
    assert result.verdict is not Verdict.dns_error


def test_is_denied_handles_url_without_hostname() -> None:
    """A pathological URL with no parseable host — defensive guard."""
    from a2web.tiers.jina import _is_denied

    assert _is_denied("not-a-url", ["example.com"]) is False
    assert _is_denied("", ["example.com"]) is False
