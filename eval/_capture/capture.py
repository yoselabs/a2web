"""`make eval-capture` — freeze a new case from a live run.

Runs the *real* in-process pipeline once against a live URL and tees every
egress into a cassette: the `fetch_bytes` HTTP outcomes, the
browser-rendered DOM (when the run uses the browser tier, or eagerly for
`commerce`/`js`/`spa`-tagged cases), and the LLM extraction response. Then
writes a curated `baseline/` and `meta.yaml`.

Usage:

    python -m eval._capture.capture \
        --url https://example.com/x --question "..." \
        --corpus regression --id some-slug [--tags commerce] [--all-tiers]

This is live-network and spends LLM quota — driven deliberately by the
`make eval-capture` target, never by `make check`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from a2kit.ldd import ldd_state_for_call
from a2kit.packages.testing.null_context import null_context

from a2web import fetcher
from http_fetch import FetchOutcome
from a2web.settings import AppSettings
from a2web.state import bootstrap_state

from .cassette import serialize_exchanges

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORPUS_ROOT = _REPO_ROOT / "eval" / "corpus"


@contextlib.contextmanager
def _tee_fetch_bytes(recorder: dict[str, FetchOutcome]) -> Iterator[None]:
    """Record every `fetch_bytes` egress (URL→outcome) at all import sites."""
    from http_fetch import fetch as fetch_module

    real = fetch_module.fetch_bytes

    async def _teed(url: str, **kwargs: Any) -> FetchOutcome:
        outcome = await real(url, **kwargs)
        recorder[url] = outcome
        return outcome

    sites = [fetch_module]
    sites += [m for n, m in list(sys.modules.items()) if n.startswith("a2web.") and getattr(m, "fetch_bytes", None) is real]
    for mod in sites:
        mod.fetch_bytes = _teed  # type: ignore[attr-defined]
    try:
        yield
    finally:
        for mod in sites:
            mod.fetch_bytes = real  # type: ignore[attr-defined]


class _TeePool:
    """Wrap a real BrowserPool, capturing the last rendered DOM."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.rendered_html: str | None = None

    async def _ensure(self) -> None:
        await self._inner._ensure()

    @contextlib.asynccontextmanager
    async def acquire(self, url: str) -> Any:
        async with self._inner.acquire(url) as page:
            yield _TeePage(page, self)


class _TeePage:
    def __init__(self, inner: Any, pool: _TeePool) -> None:
        self._inner = inner
        self._pool = pool

    async def content(self) -> str:
        html = await self._inner.content()
        self._pool.rendered_html = html
        return html

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @property
    def url(self) -> Any:
        return self._inner.url

    @property
    def context(self) -> Any:
        return self._inner.context


class _TeeExtractor:
    """Wrap a real LlmExtractorResource, recording its extraction response."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.record: dict[str, Any] | None = None

    async def extract(self, **kwargs: Any) -> Any:
        result = await self._inner.extract(**kwargs)
        if result is not None:
            self.record = {
                "answer": result.answer,
                "model": result.model,
                "template_name": result.template_name,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "cost_usd": result.cost_usd,
                "latency_ms": result.latency_ms,
            }
        return result


def _curate_contract(response: Any) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "tier": response.tier,
        "status": getattr(response.status, "value", response.status),
        "has_content": bool(response.content_md),
    }
    if response.extracted_answer:
        contract["answer_present"] = True
        if response.tokens:
            contract["tokens_full_max"] = int(response.tokens.full) + 50
    if response.next_links:
        contract["next_links_min"] = len(response.next_links)
    hints = sorted(h.code for h in response.operator_hints)
    if hints:
        contract["operator_hints"] = hints
    return contract


@dataclass(slots=True)
class CaptureArtifacts:
    """Raw materials from one live capture run — written by `_write_case`."""

    response: Any
    http: dict[str, FetchOutcome]
    rendered_html: str | None
    llm: dict[str, Any] | None


async def capture_case(
    *,
    url: str,
    question: str | None,
    tags: frozenset[str] = frozenset(),
    all_tiers: bool = False,
) -> CaptureArtifacts:
    """Run the real pipeline once live and tee every egress into a cassette.

    Shared by `make eval-capture` (new case) and `make eval-refresh`
    (re-capture an existing case's inputs). Live-network + LLM quota.
    """
    settings = AppSettings()
    state, resources = await bootstrap_state(settings)

    http_record: dict[str, FetchOutcome] = {}
    tee_pool = _TeePool(resources.browser_pool)
    tee_extractor = _TeeExtractor(resources.llm_extractor)

    async def _lazy_pool() -> Any:
        return tee_pool

    async def _lazy_extractor() -> Any:
        return tee_extractor

    with _tee_fetch_bytes(http_record), ldd_state_for_call(ctx=null_context(), events_enabled=True, reports_enabled=False):
        response = await fetcher.fetch(
            url,
            state=state,
            browser_pool=_lazy_pool,
            llm_extractor=_lazy_extractor,
            ask=question,
            next_links=True,
            debug=True,
        )

        eager = bool(tags & {"commerce", "js", "spa"}) or all_tiers
        if eager and tee_pool.rendered_html is None:
            with contextlib.suppress(Exception):
                async with tee_pool.acquire(url) as page:
                    await page.goto(url, wait_until="networkidle")
                    await page.content()

    return CaptureArtifacts(
        response=response,
        http=http_record,
        rendered_html=tee_pool.rendered_html,
        llm=tee_extractor.record,
    )


async def _run_capture(args: argparse.Namespace) -> int:
    artifacts = await capture_case(
        url=args.url,
        question=args.question,
        tags=frozenset(args.tags or []),
        all_tiers=args.all_tiers,
    )
    case_dir = _CORPUS_ROOT / args.corpus / args.id
    write_inputs(case_dir, artifacts)
    write_baseline(case_dir, artifacts.response)
    write_meta(case_dir, args.url, artifacts)
    _ensure_case_yaml(case_dir, args)
    print(f"captured → {case_dir.relative_to(_REPO_ROOT)}")
    print(
        f"  http exchanges: {len(artifacts.http)} | rendered DOM: "
        f"{'yes' if artifacts.rendered_html else 'no'} | llm: {'yes' if artifacts.llm else 'no'}"
    )
    _warn_if_large(case_dir)
    return 0


_LARGE_BUNDLE_BYTES = 1_000_000  # warn, never silently compress (D6)


def _warn_if_large(case_dir: Path) -> None:
    total = sum(p.stat().st_size for p in (case_dir / "inputs").rglob("*") if p.is_file())
    if total > _LARGE_BUNDLE_BYTES:
        print(
            f"  warning: inputs/ is {total / 1_000_000:.1f} MB — large for a committed fixture. "
            f"Fixtures commit plain (git zlib-packs them; gzip would kill the bless diff). "
            f"If this is mostly inline page state you don't extract from, consider a leaner URL."
        )


def write_inputs(case_dir: Path, artifacts: CaptureArtifacts) -> None:
    """Write the frozen-world `inputs/` — the layer a refresh re-captures."""
    inputs = case_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    if artifacts.http:
        (inputs / "raw.http").write_text(serialize_exchanges(artifacts.http))
    if artifacts.rendered_html is not None:
        (inputs / "rendered.html").write_text(artifacts.rendered_html)
    if artifacts.llm is not None:
        (inputs / "llm").mkdir(exist_ok=True)
        (inputs / "llm" / "extract.json").write_text(json.dumps(artifacts.llm, indent=2, sort_keys=True) + "\n")


def write_baseline(case_dir: Path, response: Any) -> None:
    """Write the asserted `baseline/` — only on initial capture or an explicit bless."""
    baseline = case_dir / "baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    (baseline / "contract.json").write_text(json.dumps(_curate_contract(response), indent=2, sort_keys=True) + "\n")
    if response.extracted_answer:
        (baseline / "answer.md").write_text(response.extracted_answer.rstrip() + "\n")


def write_meta(case_dir: Path, url: str, artifacts: CaptureArtifacts) -> None:
    meta = {
        "captured_at": datetime.now(UTC).isoformat(),
        "source_url": url,
        "layers": {
            "raw": {"frozen": bool(artifacts.http), "exchanges": len(artifacts.http)},
            "browser": {"frozen": artifacts.rendered_html is not None, "bytes": len(artifacts.rendered_html or "")},
            "llm": {"frozen": artifacts.llm is not None},
        },
        "content_sha256": hashlib.sha256((artifacts.response.content_md or "").encode()).hexdigest(),
    }
    (case_dir / "meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))


def _ensure_case_yaml(case_dir: Path, args: argparse.Namespace) -> None:
    """Create case.yaml on first capture; preserve it on a refresh."""
    case_yaml = case_dir / "case.yaml"
    if case_yaml.is_file():
        return
    spec: dict[str, Any] = {"slug": args.id, "url": args.url}
    if args.question:
        spec["question"] = args.question
    if args.failure_class:
        spec["failure_class"] = args.failure_class
    if args.tags:
        spec["tags"] = list(args.tags)
    case_yaml.write_text(yaml.safe_dump(spec, sort_keys=False))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="eval-capture")
    p.add_argument("--url", required=True)
    p.add_argument("--question", default=None)
    p.add_argument("--corpus", default="regression")
    p.add_argument("--id", required=True)
    p.add_argument("--failure-class", dest="failure_class", default=None)
    p.add_argument("--tags", nargs="*", default=None)
    p.add_argument("--all-tiers", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run_capture(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
