"""The per-host circuit breaker actually opens — witnessed by a real purgatory.

CLAUDE.md has said "`purgatory` for circuit breakers (per-host, per-proxy,
global)" since before the shelf existed. Until 2026-08-02 it was false, and
nothing in either repo would have noticed: `fetch_bytes` ran its work inside
`async with breaker`, but that work never raised (mapping every transport
failure to a `FetchVerdict` and returning normally is its whole contract), so
the breaker's `__aexit__` saw `exc_type=None` on every call. Five consecutive
connection failures at `default_threshold=2` left it `closed` with
`failure_count=0`.

**The witness here is `purgatory` itself, not a fake.** http-fetch's own suite
pins the mechanism with a counting fake — correct at that layer, since the
package must not depend on one breaker library. But the claim a2web makes is
about the breaker a2web actually ships, and a fake cannot witness that: a fake
breaker is written by the same person, at the same moment, encoding the same
assumption as the code. The pre-existing `_FakeBreaker` asserted `entered is
True` and passed for the entire life of the defect.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from curl_cffi.requests import exceptions as ce
from purgatory import AsyncCircuitBreakerFactory

from a2web.models import Verdict
from a2web.tiers.raw import RawTier
from tests.conftest import make_default_state

if TYPE_CHECKING:
    from a2web.state import AppState

_HOST = "brokenhost.test"
_URL = f"https://{_HOST}/page"
_THRESHOLD = 3


class _AlwaysFails:
    """A curl_cffi session that raises a connection error on every GET."""

    def __init__(self) -> None:
        self.gets = 0

    async def __aenter__(self) -> _AlwaysFails:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str, **_: Any) -> Any:
        self.gets += 1
        msg = "connection refused"
        raise ce.ConnectionError(msg)


def _state_with_breakers() -> AppState:
    state = make_default_state()
    state.breakers = AsyncCircuitBreakerFactory(default_threshold=_THRESHOLD, default_ttl=300.0)
    return state


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> _AlwaysFails:
    fake = _AlwaysFails()
    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", lambda **_: fake)
    return fake


async def test_repeated_failures_open_the_host_breaker(session: _AlwaysFails) -> None:
    """The claim, end to end: fetch → tier → primitive → real purgatory."""
    state = _state_with_breakers()
    tier = RawTier()

    for _ in range(_THRESHOLD):
        result = await tier.fetch(_URL, state=state)
        assert result.verdict is Verdict.connection_error

    breaker = await state.breakers.get_breaker(_HOST)
    assert breaker.context.state == "opened", "the breaker never recorded a failure"


async def test_an_open_breaker_stops_dialling_the_host(session: _AlwaysFails) -> None:
    """What the breaker is FOR — and the half a state assertion alone misses.

    A breaker that reports `opened` while the transport keeps dialling has
    bought nothing. The observable is the GET count: once open, further fetches
    must short-circuit without touching the network.
    """
    state = _state_with_breakers()
    tier = RawTier()

    for _ in range(_THRESHOLD):
        await tier.fetch(_URL, state=state)
    dialled_before = session.gets
    assert dialled_before == _THRESHOLD

    result = await tier.fetch(_URL, state=state)

    assert session.gets == dialled_before, "an open breaker still dialled the host"
    # Still a domain verdict, not a raise — an open breaker is a routing input
    # the tier ladder continues past, not an error that escapes the tier.
    assert result.verdict is Verdict.connection_error


async def test_a_served_404_never_opens_the_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    """The anti-vacuity half, and a real policy statement.

    Without it, "count every non-ok outcome" would pass both tests above — and
    would be a different bug: a 404 is the SERVER ANSWERING, so one missing URL
    would take a healthy host out of service for every other URL on it.
    """

    class _NotFound(_AlwaysFails):
        async def get(self, url: str, **_: Any) -> Any:
            self.gets += 1

            return SimpleNamespace(
                status_code=404,
                content=b"",
                url=_URL,
                headers={"content-type": "text/html"},
            )

    fake = _NotFound()
    monkeypatch.setattr("http_fetch.fetch.cr.AsyncSession", lambda **_: fake)
    state = _state_with_breakers()
    tier = RawTier()

    for _ in range(_THRESHOLD * 2):
        result = await tier.fetch(_URL, state=state)
        assert result.verdict is Verdict.not_found

    breaker = await state.breakers.get_breaker(_HOST)
    assert breaker.context.state == "closed"
    assert fake.gets == _THRESHOLD * 2, "a 404 must not stop the host being dialled"
