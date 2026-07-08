"""max_content_chars override plumbing — unit + extractor-level tests.

Covers openspec/changes/harsh-test-session-fixes/specs/extraction/spec.md
(max_content_chars subset).
"""

from __future__ import annotations

import pytest

from a2web.packages.llm_extract import ProviderResponse
from a2web.packages.llm_extract.extractor import Extractor, ModelSpec


class _RecordingProvider:
    """Records the `user` prompt that was sent so tests can assert truncation."""

    name = "recording"
    last_user: str = ""

    async def complete(self, *, system, user, model, max_tokens, temperature=0.0, thinking_disabled=True, parts=None):
        type(self).last_user = user
        return ProviderResponse(text="ok", model=model, prompt_tokens=0, completion_tokens=0, cost_usd=0.0, latency_ms=0)


def _make_extractor(default_cap: int = 100_000) -> Extractor:
    return Extractor(
        provider=_RecordingProvider(),
        model=ModelSpec("test-model"),
        max_content_chars=default_cap,
    )


@pytest.mark.asyncio
async def test_override_clamps_below_default() -> None:
    """When per-call max_content_chars=1000, content is truncated to 1000."""
    ex = _make_extractor(default_cap=100_000)
    big_content = "x" * 50_000
    await ex.extract(content=big_content, ask="q", max_content_chars=1_000)
    sent_to_llm = _RecordingProvider.last_user
    # The truncation marker is added when content is capped.
    assert "[Content truncated to 1000 chars]" in sent_to_llm
    # The original 50K chars should NOT all be there.
    assert sent_to_llm.count("x") < 50_000


@pytest.mark.asyncio
async def test_override_above_content_size_is_noop() -> None:
    """When override > content length, no truncation marker."""
    ex = _make_extractor(default_cap=100)
    content = "short content"
    await ex.extract(content=content, ask="q", max_content_chars=10_000)
    assert "[Content truncated" not in _RecordingProvider.last_user
    assert content in _RecordingProvider.last_user


@pytest.mark.asyncio
async def test_none_override_uses_instance_default() -> None:
    """max_content_chars=None falls back to the instance default."""
    ex = _make_extractor(default_cap=500)
    content = "x" * 2_000
    await ex.extract(content=content, ask="q", max_content_chars=None)
    sent_to_llm = _RecordingProvider.last_user
    assert "[Content truncated to 500 chars]" in sent_to_llm


@pytest.mark.asyncio
async def test_extractor_kwarg_passthrough_from_resource() -> None:
    """LlmExtractorResource.extract forwards max_content_chars verbatim."""
    from a2web.llm_resource import LlmExtractorResource

    resource = LlmExtractorResource.__new__(LlmExtractorResource)
    extractor = _make_extractor(default_cap=100_000)

    async def _ensure() -> Extractor:
        return extractor

    resource._ensure = _ensure  # type: ignore[attr-defined]

    await resource.extract(content="x" * 5_000, ask="q", max_content_chars=200)
    assert "[Content truncated to 200 chars]" in _RecordingProvider.last_user
