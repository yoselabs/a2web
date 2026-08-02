"""Replay runs must not touch the network. Enforced, not asserted.

`CassetteMiss` says "replay refuses to hit the network", and for every egress
routed through `fetch_bytes` that was true. The jina tier was not: it hand-rolled
an `httpx.AsyncClient`, so `patch_fetch_bytes` never saw it and every replay of a
case whose ladder reached jina made a **live HTTPS request to `r.jina.ai`** — in
CI, on every push, for as long as the corpus has existed. The blessed
`jina:paywall` step in the case now split into `regression/akakce-no-current-price`
and `regression/zoro-datadome-bot-wall` was a live
response, not frozen bytes, so that baseline was never reproducible in the sense
the harness advertised.

Measured before believing it: a `socket.getaddrinfo` spy over one replay run
reported exactly one lookup, `r.jina.ai`.

Routing jina through the primitive (2026-08-02) closed that particular hole. This
fixture closes the CLASS: any future tier, handler, or dependency that dials out
during a replay fails loudly here instead of silently making the corpus depend on
today's internet. A guard on the specific hole would have been the same mistake
one layer up.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import pytest

from a2web.tiers import REGISTRY, BrowserTier

if TYPE_CHECKING:
    from collections.abc import Iterator


class ReplayNetworkAccess(AssertionError):
    """A replay attempted a real DNS lookup."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail any name resolution attempted while a replay case is running.

    DNS is the chokepoint rather than `socket.connect`: every outbound client in
    this tree resolves a hostname first, and failing at resolution names the host
    in the error, which is the one fact needed to find the un-frozen egress.
    Loopback literals used by the test process itself never reach `getaddrinfo`.
    """
    real = socket.getaddrinfo

    def _blocked(host: Any, *args: Any, **kwargs: Any) -> Any:
        name = host.decode() if isinstance(host, bytes) else str(host)
        if name in {"localhost", "127.0.0.1", "::1"}:
            return real(host, *args, **kwargs)
        msg = (
            f"replay attempted a live DNS lookup for {name!r}. Some egress is not "
            "served from the cassette — find it and route it through "
            "`http_fetch.fetch_bytes`, which `patch_fetch_bytes` intercepts. "
            "A replay that reaches the network is not a replay."
        )
        raise ReplayNetworkAccess(msg)

    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    yield


@pytest.fixture(autouse=True)
def real_browser_tier_under_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo the root conftest's browser stub — replay serves the browser from the cassette.

    `tests/conftest.py` swaps `REGISTRY["browser"]` for a stub that returns
    `browser_unavailable`, so a unit test can never launch Chromium. Correct
    there, and **wrong here**: replay injects `CassetteBrowserPool`, which
    cannot launch anything and serves the frozen `inputs/rendered.html`. With
    the stub in place the FAST browser rung of every replay never reached the
    cassette at all — it returned the stub's `connection_error` and an extra
    `browser_unavailable` hint, while the ROBUST rung (which the root fixture
    does not stub) served the frozen DOM correctly.

    So the harness advertised "the browser egress is frozen" and delivered that
    for one of the two rungs. No case noticed, because until 2026-08-02 no case
    had a frozen `rendered.html` whose fast-rung result changed the contract;
    `zoro-datadome-bot-wall` is the first, and it failed on the extra hint,
    which is how this was found.

    The cassette pool raises `CassetteMiss` when a case has no frozen DOM, so
    restoring the real tier keeps the no-launch guarantee: a browser dispatch
    with nothing frozen is still loud, just loud about the right thing.
    """
    monkeypatch.setitem(REGISTRY, "browser", BrowserTier())
