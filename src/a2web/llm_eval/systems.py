"""EvalSystem adapters — one `fetch(url, ask) -> SystemResult` per system.

Three v0.4 systems:

- `WebFetchBaseline`: local reproduction of Claude Code's WebFetch
  (research/123). httpx → markdownify → Haiku 4.5 with WEBFETCH_DEFAULT_V1.
  Known divergences from real WebFetch (documented inline):
    - No `api.anthropic.com/api/web/domain_info` preflight (we always fetch).
    - No cross-host redirect break (httpx follows redirects within reason).
    - No preapproved-host fast path (we always run Haiku).
    - markdownify ≠ Turndown — output is close but not byte-identical.

- `A2WebDetail`: invokes a2web's `fetch(url)` without an extraction prompt.
  Returns the full response envelope (post v0.3 envelope diet). The
  downstream "reader" stage in the eval runner reads this envelope to
  produce an answer; this matches the agent-side cost of using a2web.

- `A2WebExtract`: invokes a2web's `fetch(url, ask=...)` to get the
  server-side extracted answer directly. Matches the v0.4 WebFetch-parity
  use case.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import httpx

from ..packages.llm_extract import WEBFETCH_DEFAULT_V1
from ..packages.llm_extract.providers.base import Provider

if TYPE_CHECKING:
    from ..models import FetchResponse
    from ..state import AppState


# WebFetch constants extracted from Claude Code's binary (research/123).
WEBFETCH_MODEL = "claude-haiku-4-5-20251001"
WEBFETCH_MARKDOWN_CAP = 100_000  # BD_
WEBFETCH_TURNDOWN_CAP = 1_048_576  # om7 (1 MiB)
WEBFETCH_HTTP_TIMEOUT_S = 60.0  # OQ5
WEBFETCH_BODY_MAX_BYTES = 10 * 1024 * 1024  # KQ5 (10 MiB)


@dataclass(slots=True)
class SystemResult:
    """One fetch outcome from an EvalSystem.

    `answer` is the system's final answer string (NL or markdown depending on
    the system). `metadata` carries system-specific fields (tier, cost,
    tokens, etc.) without committing to a shape across systems.
    """

    answer: str
    system: str
    latency_ms: int
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class EvalSystem(Protocol):
    """One system under evaluation. Stateless beyond construction."""

    name: str

    async def fetch(self, *, url: str, ask: str) -> SystemResult: ...


# --------------------------------------------------------------------- #
# WebFetchBaseline — faithful local reproduction
# --------------------------------------------------------------------- #


class WebFetchBaseline:
    """Reproduces Claude Code's WebFetch internals locally.

    Matches the binary-extracted constants (research/123):
      - model = claude-haiku-4-5-20251001
      - system prompt = [] (empty)
      - prompt template = WEBFETCH_DEFAULT_V1 (byte-for-byte the Rb9 template)
      - markdown cap = 100_000 chars (BD_)
      - HTTP timeout = 60 s (OQ5), body cap = 10 MiB (KQ5)
      - thinking disabled, no tools, single turn

    Known divergences (documented for benchmark transparency):
      - No api.anthropic.com domain_info preflight.
      - No cross-host redirect break (httpx follows redirects).
      - No preapproved-host fast path skipping Haiku for text/markdown.
      - markdownify ≠ Turndown — output is similar but not byte-identical.
    """

    name: str = "webfetch_baseline"

    def __init__(
        self,
        *,
        provider: Provider,
        model: str = WEBFETCH_MODEL,
        timeout_s: float = WEBFETCH_HTTP_TIMEOUT_S,
        body_max_bytes: int = WEBFETCH_BODY_MAX_BYTES,
        markdown_cap: int = WEBFETCH_MARKDOWN_CAP,
        turndown_cap: int = WEBFETCH_TURNDOWN_CAP,
        user_agent: str | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._timeout_s = timeout_s
        self._body_max_bytes = body_max_bytes
        self._markdown_cap = markdown_cap
        self._turndown_cap = turndown_cap
        self._user_agent = user_agent or (
            # Roughly mirrors the WebFetch UA shape; Claude Code's is custom.
            "Mozilla/5.0 (compatible; a2web/WebFetchBaseline)"
        )

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        t0 = time.perf_counter()
        try:
            html, fetch_meta = await _http_get(
                url,
                timeout_s=self._timeout_s,
                body_max_bytes=self._body_max_bytes,
                user_agent=self._user_agent,
            )
        except _FetchError as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return SystemResult(
                answer="",
                system=self.name,
                latency_ms=latency_ms,
                error=str(exc),
                metadata={"stage": "http"},
            )

        markdown = _html_to_markdown(html, cap=self._turndown_cap)
        if len(markdown) > self._markdown_cap:
            markdown = markdown[: self._markdown_cap] + "\n\n[Content truncated due to length...]\n"
            truncated = True
        else:
            truncated = False

        user_payload = WEBFETCH_DEFAULT_V1.user_template.format(content=markdown, ask=ask)
        response = await self._provider.complete(
            system=WEBFETCH_DEFAULT_V1.system,
            user=user_payload,
            model=self._model,
            thinking_disabled=True,
        )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        return SystemResult(
            answer=response.text or "No response from model",
            system=self.name,
            latency_ms=latency_ms,
            cost_usd=response.cost_usd,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            error=None if response.text else "empty_model_response",
            metadata={
                "http_status": fetch_meta.get("status"),
                "final_url": fetch_meta.get("final_url"),
                "content_length": len(html),
                "markdown_length_pre_cap": fetch_meta.get("md_len_pre_cap"),
                "truncated": truncated,
                "model": response.model,
            },
        )


# --------------------------------------------------------------------- #
# A2WebDetail / A2WebExtract — invoke our own pipeline as a system
# --------------------------------------------------------------------- #


class A2WebDetail:
    """Invokes a2web's fetch(url) WITHOUT ask=. Returns content_md as the
    answer. Used to measure the cost of "agent reads the envelope and
    extracts the answer in its own context" — i.e. the WebFetch
    counterfactual where the calling LLM does the extraction.
    """

    name: str = "a2web_detail"

    def __init__(self, *, state: AppState) -> None:
        self._state = state

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        from ..fetcher import fetch as a2web_fetch

        t0 = time.perf_counter()
        response: FetchResponse = await a2web_fetch(url, state=self._state, include_links=False, debug=False)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return SystemResult(
            answer=response.content_md or "",
            system=self.name,
            latency_ms=latency_ms,
            error=None if response.status.value == "ok" else response.diagnostics_summary,
            metadata={
                "tier": response.tier,
                "status": response.status.value,
                "diagnostics_summary": response.diagnostics_summary,
                "content_chars": len(response.content_md or ""),
            },
        )


class A2WebExtract:
    """Invokes a2web's fetch(url, ask=...) with server-side extraction.
    Matches the WebFetch use case — caller gets back only the answer."""

    name: str = "a2web_extract"

    def __init__(self, *, state: AppState) -> None:
        self._state = state

    async def fetch(self, *, url: str, ask: str) -> SystemResult:
        from ..fetcher import fetch as a2web_fetch

        t0 = time.perf_counter()
        response: FetchResponse = await a2web_fetch(url, state=self._state, ask=ask, include_links=False, debug=False)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        ex = response.extraction
        cost = ex.cost_usd if ex else 0.0
        prompt_tokens = ex.prompt_tokens if ex else 0
        completion_tokens = ex.completion_tokens if ex else 0
        return SystemResult(
            answer=response.extracted_answer or response.content_md or "",
            system=self.name,
            latency_ms=latency_ms,
            cost_usd=cost,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=None if response.status.value == "ok" else response.diagnostics_summary,
            metadata={
                "tier": response.tier,
                "status": response.status.value,
                "diagnostics_summary": response.diagnostics_summary,
                "extraction_model": ex.model if ex else None,
                "extraction_cache_hit": ex.cache_hit if ex else None,
                "extraction_truncated": ex.truncated if ex else None,
            },
        )


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


class _FetchError(RuntimeError):
    """Internal — wraps HTTP failure modes for the system result."""


async def _http_get(
    url: str,
    *,
    timeout_s: float,
    body_max_bytes: int,
    user_agent: str,
) -> tuple[str, dict[str, Any]]:
    """Local HTTP fetch matching WebFetch's posture: large timeout, body cap,
    follow redirects, prefer markdown/html. Raises _FetchError on failure."""
    headers = {
        "Accept": "text/markdown, text/html, */*",
        "User-Agent": user_agent,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException as exc:
        raise _FetchError(f"timeout after {timeout_s}s") from exc
    except httpx.HTTPError as exc:
        raise _FetchError(f"network error: {exc}") from exc

    if response.status_code >= 400:
        raise _FetchError(f"HTTP {response.status_code}")

    content_bytes = response.content
    if len(content_bytes) > body_max_bytes:
        raise _FetchError(f"body exceeds {body_max_bytes} bytes ({len(content_bytes)} bytes received)")

    return response.text, {
        "status": response.status_code,
        "final_url": str(response.url),
    }


def _html_to_markdown(html: str, *, cap: int) -> str:
    """Convert HTML to markdown via `markdownify` — the Python neighbor of
    WebFetch's Turndown. Removes script/style/noscript/iframe elements
    (including their text content) before conversion — matches WebFetch's
    behavior where Turndown's filter drops the elements entirely, not
    just the tags."""
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    if len(html) > cap:
        html = html[:cap]
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    return md(str(soup), heading_style="ATX")
