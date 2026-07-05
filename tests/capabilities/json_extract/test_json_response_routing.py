"""JSON response bodies are synthesized in-place, never routed through jina.

json-endpoint-direct-routing: a JSON API endpoint (`application/json`) wins at
the raw tier and is rendered to markdown in `_phase_extract` — the same
`json_to_markdown_rows` synthesis as the JSON-in-script path — instead of
escalating to the r.jina.ai HTML reader (which mangles JSON into a false
`length_floor`). Unknown shapes fall back to the capped JSON text, and a
small-but-complete JSON body is exempt from the thin-shell length floor.
"""

from __future__ import annotations

import pytest

from a2web.fetcher import evaluate, fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, TierResult
from tests.conftest import make_default_state


class _JsonApiRawTier:
    """A raw tier returning a JSON API response (as real raw now does — the
    JSON content-type maps to Verdict.ok, not content_type_mismatch)."""

    name = "raw"

    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self._body = body
        self._ct = content_type

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=self._body, content_type=self._ct, status_code=200, final_url=url, verdict=Verdict.ok)


class _ExplodingJinaTier:
    """Proves jina is never consulted for a JSON response — if it runs, fail."""

    name = "jina"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del url, state, kwargs
        raise AssertionError("jina tier must not run for a JSON response")


def _stub_tiers(monkeypatch: pytest.MonkeyPatch, raw: _JsonApiRawTier) -> None:
    monkeypatch.setitem(REGISTRY, "raw", raw)
    monkeypatch.setitem(REGISTRY, "jina", _ExplodingJinaTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)


@pytest.mark.asyncio
async def test_recognized_json_shape_synthesizes_and_skips_jina(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"products": [{"name": "Widget A", "price": "9.99"}, {"name": "Widget B", "price": "5.00"}]}'
    _stub_tiers(monkeypatch, _JsonApiRawTier(body))

    result = await fetch("https://api.example.com/data", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert "Widget A" in result.content_md
    assert "Widget B" in result.content_md
    # jina never ran (the exploding stub would have raised) and left no diagnostic.
    assert not any(d.step == "jina" for d in result.diagnostics)
    assert any(d.step == "json_response" for d in result.diagnostics)


@pytest.mark.asyncio
async def test_unrecognized_json_shape_falls_back_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"weather": {"temp": 21, "wind": 4}}'
    _stub_tiers(monkeypatch, _JsonApiRawTier(body))

    result = await fetch("https://api.example.com/weather", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok  # not a length_floor failure
    assert '"temp": 21' in result.content_md  # the JSON text reached the caller


@pytest.mark.asyncio
async def test_small_json_body_bypasses_length_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"count": 42}'  # well below the 500-char length floor
    _stub_tiers(monkeypatch, _JsonApiRawTier(body))

    result = await fetch("https://api.example.com/count", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert "42" in result.content_md


@pytest.mark.asyncio
async def test_json_suffix_content_type_is_synthesized(monkeypatch: pytest.MonkeyPatch) -> None:
    body = b'{"items": [{"title": "Alpha"}, {"title": "Beta"}]}'
    _stub_tiers(monkeypatch, _JsonApiRawTier(body, content_type="application/vnd.api+json"))

    result = await fetch("https://api.example.com/feed", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert "Alpha" in result.content_md
    assert not any(d.step == "jina" for d in result.diagnostics)


# --------------------------------------------------------------------- #
# Length-floor exemption (D5) — focused unit test on the gate wrapper
# --------------------------------------------------------------------- #


def test_gate_exempts_short_json_from_length_floor() -> None:
    # is_json=True → a short JSON render is accepted, not a length_floor.
    result = evaluate(content_md='{"count": 42}', raw_html='{"count": 42}', content_type=None, is_json=True)
    assert result.verdict is Verdict.ok


def test_gate_keeps_length_floor_for_short_non_json() -> None:
    # is_json=False → the thin-shell floor stands (the v0.29.0 guard is untouched).
    result = evaluate(content_md="thin", raw_html="<html><body>thin</body></html>", content_type=None, is_json=False)
    assert result.verdict is Verdict.length_floor
