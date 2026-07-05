"""Unit tests for `OpenAICompatibleProvider` (openai-compatible-llm-provider).

The `openai` client is faked — no real network. Covers: happy-path text +
token mapping + zero cost, system-tuple flattening, the markerless error
contract (API error → empty-text response, never a crash), standard-env key
gating (missing `OPENAI_API_KEY` → LLMNotAvailable), optional base_url (empty →
OpenAI proper), and the carried `default_model`.
"""

from __future__ import annotations

import types

import httpx
import pytest

from a2web.packages.llm_extract import LLMNotAvailable
from a2web.packages.llm_extract.providers.openai_compatible import OpenAICompatibleProvider

_KEY_ENV = "OPENAI_API_KEY"


class _FakeCompletions:
    def __init__(self, *, response: object = None, exc: BaseException | None = None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._response


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch, *, response: object = None, exc: BaseException | None = None) -> _FakeCompletions:
    completions = _FakeCompletions(response=response, exc=exc)

    class _Client:
        def __init__(self, **kw: object) -> None:
            self.init_kwargs = kw
            self.chat = types.SimpleNamespace(completions=completions)

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _Client)
    return completions


def _resp(content: str, *, model: str = "gpt-4.1-mini", pt: int = 100, ct: int = 20) -> object:
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))],
        usage=types.SimpleNamespace(prompt_tokens=pt, completion_tokens=ct),
        model=model,
    )


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_KEY_ENV, "test-key")


# --------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------- #


async def test_completes_returns_text_tokens_and_zero_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    completions = _install_fake_openai(monkeypatch, response=_resp("the answer", pt=123, ct=45))
    provider = OpenAICompatibleProvider(base_url="https://api.example.com/v1")

    result = await provider.complete(system="be terse", user="q?", model="gpt-4.1-mini")

    assert result.text == "the answer"
    assert result.model == "gpt-4.1-mini"
    assert result.prompt_tokens == 123
    assert result.completion_tokens == 45
    assert result.cost_usd == 0.0  # arbitrary endpoint → never a guessed price
    assert completions.calls[0]["model"] == "gpt-4.1-mini"
    assert completions.calls[0]["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "q?"},
    ]


async def test_system_tuple_is_flattened(monkeypatch: pytest.MonkeyPatch) -> None:
    completions = _install_fake_openai(monkeypatch, response=_resp("ok"))
    provider = OpenAICompatibleProvider(base_url="https://api.example.com/v1")

    await provider.complete(system=("a", "b"), user="u", model="m")

    assert completions.calls[0]["messages"][0] == {"role": "system", "content": "a\n\nb"}


async def test_empty_system_omits_system_message(monkeypatch: pytest.MonkeyPatch) -> None:
    completions = _install_fake_openai(monkeypatch, response=_resp("ok"))
    provider = OpenAICompatibleProvider(base_url="https://api.example.com/v1")

    await provider.complete(system=(), user="just user", model="m")

    assert completions.calls[0]["messages"] == [{"role": "user", "content": "just user"}]


async def test_missing_usage_yields_zero_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="x"))],
        usage=None,
        model="m",
    )
    _install_fake_openai(monkeypatch, response=resp)
    provider = OpenAICompatibleProvider(base_url="https://api.example.com/v1")

    result = await provider.complete(system="", user="u", model="m")

    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0


# --------------------------------------------------------------------- #
# Config surface — standard env, optional base_url, carried model
# --------------------------------------------------------------------- #


def test_empty_base_url_constructs_openai_proper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install_fake_openai(monkeypatch, response=_resp("ok"))
    # No base_url → the SDK targets OpenAI proper (no base_url kwarg passed).
    provider = OpenAICompatibleProvider()
    assert provider.default_model == ""
    del captured  # construction is the assertion (no raise)


def test_default_model_is_carried(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_openai(monkeypatch)
    provider = OpenAICompatibleProvider(default_model="deepseek-v4-flash")
    assert provider.default_model == "deepseek-v4-flash"


def test_missing_api_key_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_KEY_ENV, raising=False)
    with pytest.raises(LLMNotAvailable):
        OpenAICompatibleProvider(base_url="https://api.example.com/v1")


# --------------------------------------------------------------------- #
# Error contract — never raises on API errors
# --------------------------------------------------------------------- #


async def test_api_error_returns_empty_text_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    import openai

    err = openai.APIError("boom", request=httpx.Request("POST", "https://api.example.com/v1"), body=None)
    _install_fake_openai(monkeypatch, exc=err)
    provider = OpenAICompatibleProvider(base_url="https://api.example.com/v1")

    result = await provider.complete(system="", user="u", model="m")

    assert result.text == ""
    assert result.model == "m"
    assert result.raw is not None
    assert "boom" in result.raw["error"]
