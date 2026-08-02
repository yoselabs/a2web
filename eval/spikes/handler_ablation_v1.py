"""Spike — what is a site handler actually WORTH?

Part two of `I0269`: the user wants site/service knowledge quarantined out of
the generic core. Before deciding WHERE that knowledge lives, this measures
WHETHER it earns its place, per handler, by ablation:

    handler ON   — production path, `site_handler` is tier 0
    handler OFF  — the same URL with `match_handler` forced to None, so the
                   fetch falls through to raw / jina / browser and the generic
                   extractor does all the work

**The hypothesis this is designed to break.** "Handlers" is treated as one
category by the codebase, the manifest surface, and I0269 itself. It is probably
not one category. A handler can be doing any of three very different jobs:

    RETRIEVAL   the site is walled and the handler is the only way in
                (reddit's shape-aware 403 policy, twitter via nitter).
                Ablating it should produce a FAILED fetch, not a worse answer.

    RENDERING   the page retrieves fine generically, and the handler produces a
                better-shaped body (`pre_rendered`) — hn's comment tree,
                github's issue list.
                Ablating it should cost content, not retrieval.

    INDEXING    the body is fine either way, but the handler supplies the
                site-specific `next_links` reasons ("142 points, 88 comments")
                that I0269 §5 is about.
                Ablating it should cost the INDEX only.

    REDUNDANT   generic does as well. The handler is carrying cost, not value.

Those four call for different homes and different maintenance budgets, and the
current organisation cannot express the difference. A per-handler verdict is the
input the organisation decision has been missing.

**Method.** Same blind-judge design as `entity_schema_v2.py`, whose helpers are
imported rather than copied: two curators of the same measurement drifting apart
is a failure this repo has already paid for once (`eval/_capture/capture.py` vs
`tests/eval_replay/bless.py`, 2026-08-02), and numbers from two subtly different
judges would not be comparable across the two spikes.

Metrics per site: core recall (does it still answer), adjacent recall (does it
still relay the remainder), retrieval status, tier used, body size, and the
`next_links` count plus their reasons — the last because I0269 §5's whole
argument is that the handler's `reason` carries signal the generic layer cannot
reconstruct. That claim is checkable here rather than assumed.

**Non-vacuity.** The ablation asserts it actually bit: with handlers off, no
round may report `tier == "site_handler"`, AND every handlers-ON round must.
A one-directional check is not enough: the first draft asserted only the OFF
side and read a field (`tier_used`) that does not exist on the model, so it
returned None on both arms and could never fire. `site_handler.py` binds
`match_handler` as an imported NAME, so patching `a2web.handlers.match_handler`
would silently do nothing and this spike would report a confident "handlers make
no difference" while having tested nothing. That is the exact failure CLAUDE.md
warns about ("cross-module references to a fake-able seam go through the MODULE,
not an imported name"), and the assertion is what keeps it from happening
quietly.

**Cost posture (ADR-0016).** Subscription only, same as the sibling spikes.

Live network + LLM quota. Not part of `make check`. Run:

    uv run python eval/spikes/handler_ablation_v1.py [N_SITES] [REPS]
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

from anyllm import ProviderName, with_cost_guard

from a2web.components import build_components
from a2web.fetcher import fetch
from a2web.fetcher_response import build_ask_response
from a2web.llm_resource import select_provider
from a2web.settings import AppSettings

# Imported, not copied — see "Method" above. These are the same judge, the same
# inventory split, and the same tolerant parse the entity spike used.
#
# `eval/spikes/` has no `__init__.py`, and running this file as a script puts
# `eval/spikes/` on `sys.path` rather than the repo root — so the sibling import
# resolves only after the root is added. Done by path rather than by adding an
# `__init__.py`, because every other spike here is a standalone script and one
# package-ifying file would change how all of them import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.spikes.entity_schema_v2 import (  # noqa: E402
    _CONTENT_CAP,
    _DEFAULT_PROVIDER,
    _PROVIDER_ENV,
    _inventory,
    _paired,
    _score,
)

_OUT = Path(__file__).resolve().parent / "handler_ablation_v1_summary.json"

#: `(handler, url, ask)` — one page per registered handler. Twitter is included
#: knowing it is upstream-walled: "the handler cannot retrieve either" is a
#: RETRIEVAL verdict too, and omitting the case would quietly bias the table
#: toward handlers that happen to work today.
CASES: list[tuple[str, str, str]] = [
    ("wikipedia", "https://en.wikipedia.org/wiki/Rust_(programming_language)", "Who created Rust and in what year did it first appear?"),
    ("arxiv", "https://arxiv.org/abs/2401.05566", "What is the paper's title and its main contribution?"),
    ("github", "https://github.com/astral-sh/ruff", "What is ruff and what are its main features?"),
    ("hn", "https://news.ycombinator.com/item?id=9224", "What is this discussion about, and what is the main disagreement?"),
    (
        "reddit",
        "https://www.reddit.com/r/programming/comments/ddlc78/comments_should_be_sentences/",
        "What is the original post about, and what are the two main counterarguments?",
    ),
    ("discourse", "https://meta.discourse.org/latest", "What is being discussed on this forum right now? Give the top topics."),
    ("v2ex", "https://www.v2ex.com/t/1000000", "What is this thread about, and what do the replies say?"),
    ("habr", "https://habr.com/ru/articles/1032730/", "What does this article describe?"),
    ("twitter", "https://twitter.com/anthropicai/status/1701832836929187894", "What does this tweet say?"),
]


class _Ablation:
    """Force `match_handler` to miss, at the seam the tier actually calls.

    Patches `a2web.tiers.site_handler.match_handler` — NOT
    `a2web.handlers.match_handler`. The tier did `from ..handlers import
    match_handler`, which froze the reference at import time, so patching the
    origin module would leave the tier calling the real function and this whole
    spike would measure nothing.
    """

    def __init__(self) -> None:
        self._saved: Any = None

    def __enter__(self) -> _Ablation:
        from a2web.tiers import site_handler

        self._saved = site_handler.match_handler
        site_handler.match_handler = lambda *_a, **_k: None  # type: ignore[assignment]
        return self

    def __exit__(self, *_exc: object) -> None:
        from a2web.tiers import site_handler

        site_handler.match_handler = self._saved  # type: ignore[assignment]


def _claims(url: str) -> bool:
    """Does a handler claim this URL? Asked at the same seam the tier uses, so
    the answer tracks whatever the ablation is currently doing to it."""
    from a2web.tiers import site_handler

    return site_handler.match_handler(url, AppSettings()) is not None


async def _run(parts: Any, url: str, ask: str) -> dict[str, Any]:
    response = await fetch(
        url,
        ask=ask,
        state=await parts.state(),
        llm_extractor=parts.llm_extractor,
        browser_backend=parts.browser_backend,
        browser_robust_backend=parts.browser_robust_backend,
        cookie_jar=parts.cookie_jar,
    )
    view = build_ask_response(response, include_content=False, debug=True)
    pages = list(view.other_pages or ())
    return {
        "status": view.status or "ok",
        # `FetchResponse.tier`, NOT `tier_used`. The first draft of this spike
        # read `tier_used` via getattr-with-default, which does not exist on the
        # model, so it silently returned None on BOTH arms and the non-vacuity
        # assertion below could never fire. It read as coverage while providing
        # none — caught by noticing `tier_used=None` on the handler-ON arm,
        # where a handler had demonstrably run.
        "tier": response.tier,
        "content_chars": len(response.content_md or ""),
        # Carried so the judge inventory can be built from whichever arm
        # actually retrieved the page, without a third fetch.
        "content_md": (response.content_md or "")[:_CONTENT_CAP],
        "answer": view.answer or "",
        "answer_chars": len(view.answer or ""),
        "also_here": len(view.also_here or ()),
        "other_pages": len(pages),
        # I0269 §5's claim is that the handler's `reason` carries site-specific
        # signal ("142 points, 88 comments") the generic layer cannot rebuild.
        # Carrying the strings out makes that checkable instead of asserted.
        "other_page_reasons": [p.reason for p in pages][:8],
        "hints": [h.code for h in (view.operator_hints or ())],
    }


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(CASES)
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    cases = CASES[:limit]

    settings = AppSettings()
    raw = os.environ.get(_PROVIDER_ENV, "").strip().lower() or _DEFAULT_PROVIDER
    try:
        override = ProviderName(raw)
    except ValueError:
        raise SystemExit(f"handler_ablation_v1: unknown provider id {raw!r}") from None
    provider = select_provider(settings, override=override)
    if provider is None:
        raise SystemExit(f"handler_ablation_v1: no LLM provider available (tried: {raw})")
    provider = with_cost_guard(provider)
    model = settings.llm_model

    parts = build_components(settings=settings)
    rows: list[dict[str, Any]] = []
    try:
        for i, (handler, url, ask) in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {handler}", flush=True)
            row: dict[str, Any] = {"handler": handler, "url": url, "ask": ask, "reps": []}
            try:
                for rep in range(reps):
                    on = await _run(parts, url, ask)
                    with _Ablation():
                        off = await _run(parts, url, ask)

                    # Non-vacuity, in BOTH directions — a one-sided check here is
                    # what failed the first time. The ON arm must show the
                    # handler ran, and the OFF arm must show it did not; an
                    # assertion that can only fire in one direction cannot tell
                    # "the ablation worked" from "the probe reads nothing".
                    # `tier` is `site_handler:<name>` (e.g. `site_handler:wikipedia`),
                    # NOT a bare `site_handler` — an equality check made BOTH
                    # sides false and fired on every case for the wrong reason.
                    #
                    # And `tier` answers "which tier supplied the body", NOT
                    # "did the handler run": reddit's handler matches, runs,
                    # fails, and the walk escalates to `browser`, so `tier` says
                    # `browser` while the handler ran fine. Whether the handler
                    # CLAIMS the URL is a static fact — ask `match_handler`
                    # directly rather than inferring it from an outcome.
                    claims = _claims(url)
                    off_ran = off["tier"].startswith("site_handler")
                    superseded = claims and not on["tier"].startswith("site_handler")
                    # Two different situations, deliberately NOT collapsed.
                    if off_ran:
                        # The patch did not take. Nothing this spike prints can
                        # be trusted, including the other sites — abort loudly.
                        raise SystemExit(
                            f"handler_ablation_v1: the ablation did not take effect for {handler} "
                            f"(OFF tier={off['tier']!r}). "
                            "The patched seam is wrong; every number this spike prints would be meaningless."
                        )
                    if not claims:
                        # The handler does not claim this URL at all, so there
                        # is no ablation to measure. A RESULT about the corpus
                        # entry, not a harness fault — reporting a 0.0 delta
                        # would read as "the handler adds nothing" when the
                        # truth is "it was never asked".
                        row["verdict_override"] = f"NOT CLAIMED — handler does not match this URL (tier={on['tier']!r})"
                        print(f"      -> NO ABLATION: handler does not claim this URL", flush=True)
                        break
                    on["superseded"] = superseded

                    # The inventory comes from whichever arm actually retrieved
                    # MORE body, so a failed arm cannot shrink the target it is
                    # then graded against. Grading a failure against its own
                    # (empty) page would score it a perfect 1.0.
                    src = on if on["content_chars"] >= off["content_chars"] else off
                    body_owner = "on" if src is on else "off"
                    content = src["content_md"]

                    rec: dict[str, dict[str, float]] = {}
                    inv: dict[str, list[str]] = {"core": [], "adjacent": []}
                    if len(content) >= 500:
                        inv = await _inventory(provider, content=content, ask=ask, model=model)
                        for kind in ("core", "adjacent"):
                            if not inv[kind]:
                                continue
                            got = await _score(
                                provider,
                                ask=ask,
                                facts=inv[kind],
                                answers={"on": on["answer"], "off": off["answer"]},
                                model=model,
                            )
                            rec[kind] = {k: round(len(v) / len(inv[kind]), 3) for k, v in got.items()}

                    # Bodies are up to 60k chars each and the summary is read by
                    # hand; keep the measurements, drop the payload.
                    for arm in (on, off):
                        arm.pop("content_md", None)
                    row["reps"].append({"on": on, "off": off, "recall": rec, "inventory_from": body_owner})
                    print(
                        f"      rep{rep + 1} ON[{on['status']}/{on['tier']}/{on['content_chars']}c "
                        f"np={on['other_pages']}] OFF[{off['status']}/{off['tier']}/{off['content_chars']}c "
                        f"np={off['other_pages']}] recall={rec}",
                        flush=True,
                    )
            except SystemExit:
                raise
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                print(f"      -> ERROR {row['error']}", flush=True)
            rows.append(row)
            _OUT.write_text(json.dumps({"partial": True, "rows": rows}, indent=2))
    finally:
        await parts.aclose()

    def _classify(row: dict[str, Any]) -> str:
        """Assign the verdict the organisation decision needs.

        Deliberately ordered: retrieval dominates rendering, which dominates
        indexing. A handler that is the only way IN is not merely a nicer
        renderer, and collapsing the two is how a handler's real job gets
        misfiled.
        """
        if row.get("verdict_override"):
            return row["verdict_override"]
        reps_ = [r for r in row.get("reps", []) if r]
        if not reps_:
            return "unmeasured"
        on_ok = sum(1 for r in reps_ if r["on"]["status"] == "ok")
        off_ok = sum(1 for r in reps_ if r["off"]["status"] == "ok")
        if all(r["on"].get("superseded") for r in reps_):
            # The handler claimed the URL, ran, and was overtaken by escalation.
            # Whatever the deltas say, they are not measuring the handler's
            # output — they are measuring two non-handler tiers.
            return f"SUPERSEDED — handler ran but escalation overtook it (tier={reps_[0]['on']['tier']!r})"
        if on_ok > off_ok:
            return "RETRIEVAL — handler is the only way in"
        if off_ok > on_ok:
            return "HARMFUL — generic retrieves where the handler does not"
        if on_ok == 0:
            return "both-failed (walled either way)"
        adj = [(r["recall"].get("adjacent") or {}) for r in reps_ if r.get("recall")]
        d_adj = statistics.fmean([a["on"] - a["off"] for a in adj if "on" in a and "off" in a]) if adj else 0.0
        body = statistics.fmean([r["on"]["content_chars"] - r["off"]["content_chars"] for r in reps_])
        idx = statistics.fmean([r["on"]["other_pages"] - r["off"]["other_pages"] for r in reps_])
        if d_adj > 0.10 or body > 2000:
            return "RENDERING — handler produces a materially better body"
        if idx >= 1.0:
            return "INDEXING — handler's value is the index, not the body"
        return "REDUNDANT? — generic matches it on this page"

    summary: dict[str, Any] = {
        "provider": str(getattr(provider, "name", raw)),
        "model": model,
        "reps": reps,
        "verdicts": {r["handler"]: _classify(r) for r in rows},
        "rows": rows,
    }
    all_reps = [rep for r in rows for rep in r.get("reps", []) if rep.get("recall")]
    for kind in ("core", "adjacent"):
        rounds = [rep["recall"][kind] for rep in all_reps if rep["recall"].get(kind)]
        summary[f"paired_{kind}_on_minus_off"] = _paired(rounds, "on", "off")
    _OUT.write_text(json.dumps(summary, indent=2))

    print("\n=== summary ===")
    print(f"  provider/model : {summary['provider']} / {model}")
    for kind in ("core", "adjacent"):
        st = summary[f"paired_{kind}_on_minus_off"]
        if st.get("n"):
            half = 1.96 * st["stdev"] / (st["n"] ** 0.5) if st["n"] > 1 else 0.0
            print(
                f"  {kind:8s} ON-OFF : mean={st['mean']:+.4f} 95%CI=[{st['mean'] - half:+.3f},{st['mean'] + half:+.3f}] "
                f"W/T/L={st['wins']}/{st['ties']}/{st['losses']} n={st['n']}"
            )
    print("\n  PER-HANDLER VERDICT  <- the input the organisation decision needs")
    for h, v in summary["verdicts"].items():
        print(f"    {h:11s} {v}")
    print("\n  detail (mean over reps):")
    for r in rows:
        if r.get("error"):
            print(f"    {r['handler']:11s} ERROR {r['error'][:70]}")
            continue
        reps_ = r.get("reps") or []
        if not reps_:
            continue
        on_c = statistics.fmean([x["on"]["content_chars"] for x in reps_])
        off_c = statistics.fmean([x["off"]["content_chars"] for x in reps_])
        on_p = statistics.fmean([x["on"]["other_pages"] for x in reps_])
        off_p = statistics.fmean([x["off"]["other_pages"] for x in reps_])
        print(
            f"    {r['handler']:11s} body {on_c:8.0f} -> {off_c:8.0f}   other_pages {on_p:.1f} -> {off_p:.1f}   "
            f"status {reps_[0]['on']['status']}/{reps_[0]['off']['status']}"
        )
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
