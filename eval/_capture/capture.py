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
from urllib.parse import urlparse

import yaml
from http_fetch import FetchOutcome

from a2web import fetcher
from a2web.components import build_components
from a2web.settings import AppSettings

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


class _TeeBackend:
    """Wrap a real `BrowserBackend`, capturing the last rendered DOM.

    Replaces the old `_TeePool`/`_TeePage` pair, which wrapped a `BrowserPool`
    with an `acquire()`/`page.content()` API that no longer exists: the browser
    half was promoted to the shelf as `any_browser`, whose backend exposes a
    single `render(url, ...) -> RenderedPage`. The old wrapper had been dead
    since the a2kit sunset (2026-07-22) and nothing in `make check` runs this
    harness, so it went unnoticed for five days.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.rendered_html: str | None = None
        self.name = getattr(inner, "name", "tee")

    async def render(self, url: str, **kwargs: Any) -> Any:
        page = await self._inner.render(url, **kwargs)
        if getattr(page, "html", None):
            self.rendered_html = page.html
        return page

    async def __aenter__(self) -> _TeeBackend:
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._inner.__aexit__(*exc)


def _routing_record(routing: Any) -> dict[str, Any] | None:
    """Serialize the routing payload for the cassette, or `None` if truly absent."""
    if routing is None:
        return None
    return {
        "answer": routing.answer,
        "structural_form": routing.structural_form,
        "shape": routing.shape,
        "obstacle": routing.obstacle,
        "also_here": list(routing.also_here or ()),
        "other_pages": [
            {"url": o.url, "reason": o.reason, "kind": o.kind, "handle": getattr(o, "handle", None)} for o in (routing.other_pages or ())
        ],
        "refinement_axes": [{"dimension": a.dimension, "how": a.how} for a in (routing.refinement_axes or ())],
        "item_total_seen": routing.item_total_seen,
    }


class _TeeExtractor:
    """Wrap a real LlmExtractorResource, recording its extraction response."""

    def __init__(self, inner: Any) -> None:
        # `inner` is the `Lazy[LlmExtractorResource]` thunk, not the resource:
        # resolving it here would construct the provider on every capture,
        # including runs that never reach extraction.
        self._inner = inner
        self._resolved: Any = None
        self.record: dict[str, Any] | None = None

    async def extract(self, **kwargs: Any) -> Any:
        if self._resolved is None:
            self._resolved = await self._inner()
        result = await self._resolved.extract(**kwargs)
        if result is not None:
            self.record = {
                "answer": result.answer,
                "model": result.model,
                "template_name": result.template_name,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "cost_usd": result.cost_usd,
                "latency_ms": result.latency_ms,
                # The routing payload, or an explicit null when the model
                # genuinely produced none. Recording only post-parse fields made
                # the cassette structurally unable to express this, so every
                # replayed case silently ran the routing-LOST branch while
                # reporting success. The KEY is always written — its presence is
                # what lets the replay side tell "recorded as lost" from "this
                # cassette predates the field", instead of guessing None.
                "routing": _routing_record(result.routing),
            }
        return result


#: Hand-authored *intent* keys — assertions about the projection rather than
#: observed values. Both curators carry them forward verbatim so a re-bless can
#: never silently drop a case's acceptance gate. Defined HERE, not in
#: `tests/eval_replay/bless.py`, because `eval/` must not import from `tests/`.
_INTENT_KEYS = (
    "content_includes",
    "content_excludes",
    "answer_contains",
    "input_menu_includes",
    "input_menu_excludes",
    "narrative_includes",
)


def _curate_contract(response: Any, *, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    """Curate the asserted contract from a live capture.

    **This is the SECOND curator, and until 2026-08-02 it silently disagreed
    with the first.** `tests/eval_replay/bless.py::curate_contract` blesses
    `steps` unconditionally, blesses `retrieval_incomplete` / `narrative_present`
    on a non-ok status, and carries hand-authored intent keys forward — each with
    a comment explaining that a truthy-gated key would vanish from the baseline
    exactly when it stopped holding. None of that was here, and `make
    eval-refresh` — the command the mismatch message tells you to run — uses
    THIS one. So the documented way to re-bless a baseline stripped every one of
    those assertions.

    That is not hypothetical: it is why two of eight regression baselines
    carried no `steps` while the change that introduced them recorded the work
    as done. The bless code was correct — but only one of the two bless codes,
    and the other was the one operators actually ran.

    `prior` is the existing blessed contract, so hand-authored intent keys
    survive a re-bless.
    """
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
    contract["steps"] = [f"{d.step}:{getattr(d.verdict, 'value', d.verdict)}" for d in response.diagnostics]
    if contract["status"] != "ok":
        contract["retrieval_incomplete"] = bool(getattr(response, "retrieval_incomplete", False))
        contract["narrative_present"] = bool(getattr(response, "narrative", None))
    for key in _INTENT_KEYS:
        if prior and key in prior:
            contract[key] = prior[key]
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
    # A CAPTURE MUST NEVER SEND A CONDITIONAL REQUEST.
    #
    # Capturing a URL already in the operator's cache sends `If-None-Match`, the
    # origin answers `304 Not Modified`, and the cassette freezes a response
    # that BY DEFINITION carries no body. The frozen "input" is then a pointer
    # into `~/.a2web/cache.sqlite` — a file outside the repository — so the
    # replay suite's determinism claim becomes false: green on the capturing
    # machine, `content_len: 0` anywhere else.
    #
    # Not hypothetical. `akakce-no-current-price` was captured this way on
    # 2026-08-02 and shipped a 13-byte body section under a baseline demanding
    # `has_content: true`, and it took a cold-cache run to see it
    # (`eval/findings_2026-08-03-the-cassette-that-froze-a-304.md`).
    #
    # Done by adding this host to `live_only_hosts` rather than by widening
    # `fetch()` with a `bypass_cache=` kwarg: the mechanism already exists and
    # means exactly this ("do not serve this host from cache"), and a capture
    # genuinely IS a live-only fetch. One less public parameter to keep honest.
    host = urlparse(url).hostname or ""
    base = AppSettings()
    settings = (
        base.model_copy(update={"live_only_hosts": [*base.live_only_hosts, host]}) if host else base
    )
    parts = build_components(settings=settings)
    state = await parts.state()

    http_record: dict[str, FetchOutcome] = {}
    tee_extractor = _TeeExtractor(parts.llm_extractor)
    holder: dict[str, _TeeBackend] = {}

    async def _lazy_backend() -> Any:
        # Wrap lazily: resolving the backend eagerly would launch a browser for
        # every capture, including the ones that never escalate.
        if "b" not in holder:
            holder["b"] = _TeeBackend(await parts.browser_backend())
        return holder["b"]

    async def _lazy_extractor() -> Any:
        return tee_extractor

    try:
        with _tee_fetch_bytes(http_record):
            response = await fetcher.fetch(
                url,
                state=state,
                browser_backend=_lazy_backend,
                browser_robust_backend=_lazy_backend,
                llm_extractor=_lazy_extractor,
                ask=question,
                next_links=True,
                debug=True,
            )

            rendered = holder["b"].rendered_html if "b" in holder else None
            eager = bool(tags & {"commerce", "js", "spa"}) or all_tiers
            if eager and rendered is None:
                with contextlib.suppress(Exception):
                    backend = await _lazy_backend()
                    async with backend:
                        await backend.render(url, cookies=[], budget_s=30.0, js_heavy=True)
                    rendered = holder["b"].rendered_html
    finally:
        await parts.aclose()

    return CaptureArtifacts(
        response=response,
        http=http_record,
        rendered_html=rendered,
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
