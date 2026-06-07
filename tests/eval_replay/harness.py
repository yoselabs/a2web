"""Replay harness — freeze every egress, run the real pipeline above it.

Three egress seams, three test-side interceptions (no product surface):

  * `http_fetch.fetch_bytes` — a free function imported by name into the
    tiers/handlers. Patched at every import site via `patch_fetch_bytes`
    (the single centralized chokepoint).
  * `BrowserPool` — DI-provided. Replaced with `CassetteBrowserPool` whose
    `acquire()` yields a fake page serving the frozen `rendered.html`.
  * `LlmExtractorResource` — DI-provided. Replaced with `CassetteLlm`
    serving a recorded provider response from `inputs/llm/*.json`.

A miss on any seam raises `CassetteMiss` naming the case, the missing
tier, and the one-command fix — never a live call.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from eval._capture.corpus import ReplayCase

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import pytest

    from a2web.packages.http_fetch import FetchOutcome


class CassetteMiss(RuntimeError):
    """A replayed case exercised an egress with no frozen entry.

    Loud and fixable: names the case, the missing tier, and the refresh
    command. Never falls through to the network.
    """

    def __init__(self, case: ReplayCase, *, tier: str, detail: str) -> None:
        ref = f"{case.corpus}/{case.slug}" if case.corpus else case.slug
        super().__init__(
            f"cassette miss for case '{ref}' at tier={tier}: {detail}. "
            f"No frozen entry — replay refuses to hit the network. "
            f"Fix: make eval-refresh CASE={ref}"
        )
        self.case = case
        self.tier = tier


# --- raw / jina / archive HTTP egress ------------------------------------- #


def make_replay_fetch_bytes(case: ReplayCase) -> Any:
    """Build a `fetch_bytes` stand-in that serves frozen exchanges by URL."""

    async def _replay_fetch_bytes(url: str, **_: object) -> FetchOutcome:
        outcome = case.inputs.http.get(url)
        if outcome is None:
            raise CassetteMiss(case, tier="raw", detail=f"no frozen HTTP exchange for {url}")
        return outcome

    return _replay_fetch_bytes


def patch_fetch_bytes(monkeypatch: pytest.MonkeyPatch, case: ReplayCase) -> None:
    """Centralized chokepoint patch — every `a2web.*` module that imported
    `fetch_bytes` by name is rebound to the cassette reader."""
    from a2web.packages.http_fetch import fetch as fetch_module

    real = fetch_module.fetch_bytes
    replay_fn = make_replay_fetch_bytes(case)
    monkeypatch.setattr(fetch_module, "fetch_bytes", replay_fn)
    for name, module in list(sys.modules.items()):
        if not name.startswith("a2web.") or module is fetch_module:
            continue
        if getattr(module, "fetch_bytes", None) is real:
            monkeypatch.setattr(module, "fetch_bytes", replay_fn)


# --- browser egress ------------------------------------------------------- #


class _CassettePage:
    """Fake Playwright page serving the frozen rendered DOM."""

    def __init__(self, html: str, url: str) -> None:
        self._html = html
        self.url = url
        self.context = _CassetteContext()

    async def goto(self, *_: object, **__: object) -> None:
        return None

    async def content(self) -> str:
        return self._html

    async def evaluate(self, *_: object, **__: object) -> Any:
        return None

    async def wait_for_load_state(self, *_: object, **__: object) -> None:
        return None

    async def close(self) -> None:
        return None


class _CassetteContext:
    async def add_cookies(self, *_: object, **__: object) -> None:
        return None


class CassetteBrowserPool:
    """Drop-in for `BrowserPool` — never launches Camoufox.

    `acquire()` yields a `_CassettePage` serving the frozen `rendered.html`.
    A browser-tier dispatch with no frozen DOM is a loud `CassetteMiss`.
    """

    def __init__(self, case: ReplayCase) -> None:
        self._case = case

    async def _ensure(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> CassetteBrowserPool:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    @asynccontextmanager
    async def acquire(self, url: str) -> AsyncIterator[_CassettePage]:
        if self._case.inputs.rendered_html is None:
            raise CassetteMiss(self._case, tier="browser", detail="no frozen rendered.html")
        yield _CassettePage(self._case.inputs.rendered_html, url)


# --- LLM egress ----------------------------------------------------------- #


class CassetteLlm:
    """Drop-in for `LlmExtractorResource` — serves a recorded extraction.

    The recorded response (`inputs/llm/<key>.json`) reproduces the answer
    and token cost byte-for-byte, so the deterministic axes can assert
    exact values. A call with no recording is a loud `CassetteMiss`.
    """

    def __init__(self, case: ReplayCase) -> None:
        self._case = case
        # Spy: the exact `content` string the orchestrator fed the extractor on
        # the last call — i.e. what Haiku saw. The deterministic fidelity gate
        # asserts against THIS (the menu), not the wire `content_md` (ADR-0005
        # D7: provability decoupled from the envelope).
        self.last_extract_content: str | None = None

    async def _ensure(self) -> Any:
        return self

    async def close(self) -> None:
        return None

    async def __aenter__(self) -> CassetteLlm:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def extract(self, **kwargs: object) -> Any:
        from a2web.packages.llm_extract.extractor import ExtractionResult

        content = kwargs.get("content")
        self.last_extract_content = content if isinstance(content, str) else None
        records = self._case.inputs.llm
        if not records:
            raise CassetteMiss(self._case, tier="llm", detail="no recorded LLM response")
        # MVP: a single recorded response per case (keyed file). Multi-call
        # keying (prompt-hash) is layered in task 4.2.
        record = next(iter(records.values()))
        return ExtractionResult(
            answer=str(record.get("answer", "")),
            model=str(record.get("model", "cassette")),
            template_name=str(record.get("template_name", "cassette")),
            prompt_tokens=int(record.get("prompt_tokens", 0)),
            completion_tokens=int(record.get("completion_tokens", 0)),
            cost_usd=float(record.get("cost_usd", 0.0)),
            latency_ms=int(record.get("latency_ms", 0)),
            cache_hit=False,
        )
