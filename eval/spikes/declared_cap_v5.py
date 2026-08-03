"""Spike v5 — how many declared fields are worth SENDING?

v4 settled that reading the page's own JSON-LD adds real coverage
(`answer+declared − answer` = +0.083 all / +0.095 subject, both significant)
and costs **zero completion tokens**. That framing was incomplete, and the gap
matters: zero to GENERATE is not zero to SEND. The fields land on the wire and
the caller pays context tokens to read them.

    coursera        71 fields  ~1993 tokens
    bbcgoodfood     49         ~1127
    goodreads       11          ~120
    median ~501 · mean ~704   vs an answer of ~155 tokens

So the declared payload is ~4x the answer it accompanies, for +0.083. On raw
token efficiency that is WORSE than the LLM block v4 rejected (~280 tokens for
+0.152). The declared path's real advantages are elsewhere — deterministic,
exact, 100% stable, no latency — but "ship all 71 fields" is not defensible on
those alone.

**The question this spike answers:** does coverage saturate? If the first N
fields carry most of the lift, a cap buys nearly all the benefit at a fraction
of the wire cost, and the efficiency objection dissolves. If coverage rises
linearly to the tail, it does not, and the honest answer is that rich pages are
genuinely expensive to relay.

**Order under the cap is the publisher's own order, subject entities first.**
Not a relevance ranking — a2web does not rank (ADR-0012), and a ranked cap
would be measuring the ranker, not the cap. Truncation is DECLARED in the
payload (`... +N more fields`) so a caller can tell "the page states only this"
from "a2web stopped relaying" (ADR-0009 / ADR-0015).

Reuses v4's corpus, ladder, and inventory so the numbers are directly
comparable — same pages, same fixed fact inventory, same judge.

**Cost posture (ADR-0016).** Subscription only.

Live network + LLM quota. Not part of `make check`. Run:

    uv run python eval/spikes/declared_cap_v5.py [N_PAGES] [REPS]
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
from a2web.settings import AppSettings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.spikes.entity_schema_v2 import (  # noqa: E402
    _CONTENT_CAP,
    _DEFAULT_PROVIDER,
    _PROVIDER_ENV,
    _paired,
)
from eval.spikes.entity_schema_v3 import (  # noqa: E402
    _build_arms,
    _fields_as_text,
    _inventory2,
    _run_arm,
    _score_payloads,
)
from eval.spikes.declared_entity_v4 import (  # noqa: E402
    CASES,
    _declared,
    _html_via_ladder,
)

_OUT = Path(__file__).resolve().parent / "declared_cap_v5_summary.json"

#: The caps swept. `None` = uncapped, the v4 behaviour, kept as the control so
#: every capped arm is a paired delta against the thing it would replace.
_CAPS: tuple[int | None, ...] = (5, 10, 20, 40, None)

#: Rough chars-per-token for the wire-cost estimate. Deliberately a constant and
#: deliberately named as an estimate: the exact tokeniser is the caller's, not
#: a2web's, and the decision here turns on a ratio, not on an exact count.
_CHARS_PER_TOKEN = 3.8


def _cap_fields(fields: dict[str, str], cap: int | None) -> dict[str, str]:
    """First `cap` fields in publisher order. No ranking (ADR-0012)."""
    if cap is None or len(fields) <= cap:
        return dict(fields)
    return dict(list(fields.items())[:cap])


def _payload(fields: dict[str, str], cap: int | None) -> str:
    """Render a capped payload, DECLARING the truncation.

    A caller that cannot tell "the page states only this" from "a2web stopped
    relaying" will read the first into the second (ADR-0009). The dropped count
    is real and differs from the kept count by construction, so the note can
    actually fire — unlike `hn`'s unreachable one.
    """
    kept = _cap_fields(fields, cap)
    text = _fields_as_text(kept)
    dropped = len(fields) - len(kept)
    if dropped:
        text += f"\n... +{dropped} more fields declared by the page, not shown"
    return text


def _tokens(text: str) -> int:
    return round(len(text) / _CHARS_PER_TOKEN)


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(CASES)
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    cases = CASES[:limit]

    settings = AppSettings()
    raw_name = os.environ.get(_PROVIDER_ENV, "").strip().lower() or _DEFAULT_PROVIDER
    from a2web.llm_resource import select_provider

    provider = select_provider(settings, override=ProviderName(raw_name))
    if provider is None:
        raise SystemExit(f"declared_cap_v5: no LLM provider available (tried: {raw_name})")
    provider = with_cost_guard(provider)
    model = settings.llm_model

    def _key(cap: int | None) -> str:
        return f"cap_{cap if cap is not None else 'all'}"

    parts = build_components(settings=settings)
    rows: list[dict[str, Any]] = []
    try:
        for i, (slug, url, ask) in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {slug}", flush=True)
            row: dict[str, Any] = {"slug": slug, "url": url, "ask": ask}
            try:
                html, tier, ladder_errors = await _html_via_ladder(parts, url)
                fields, types, _per = _declared(html)
                row |= {
                    "html_tier": tier,
                    "ladder_errors": ladder_errors,
                    "declared_types": types,
                    "declared_field_count": len(fields),
                }
                if not fields:
                    row["skipped"] = "no declared fields"
                    rows.append(row)
                    print("      -> SKIP (no declaration)", flush=True)
                    continue

                wire = {_key(c): _tokens(_payload(fields, c)) for c in _CAPS}
                row["wire_tokens"] = wire
                print(f"      {len(fields)} fields via {tier}  wire={wire}", flush=True)

                response = await fetch(
                    url,
                    state=await parts.state(),
                    llm_extractor=parts.llm_extractor,
                    browser_backend=parts.browser_backend,
                    browser_robust_backend=parts.browser_robust_backend,
                    cookie_jar=parts.cookie_jar,
                )
                content = (response.content_md or "")[:_CONTENT_CAP]
                if len(content) < 500:
                    row["skipped"] = f"content too thin ({len(content)}c)"
                    rows.append(row)
                    print(f"      -> SKIP ({len(content)}c)", flush=True)
                    continue

                inv = await _inventory2(provider, content=content, ask=ask, model=model)
                allf = inv["core"] + inv["adjacent"]
                if not allf:
                    row["skipped"] = "no inventory"
                    rows.append(row)
                    continue
                row["inventory_size"] = len(allf)

                arms = _build_arms([])
                reps_out = []
                for rep in range(reps):
                    a = await _run_arm(provider, arms["A"], content=content, ask=ask, model=model)
                    payloads = {"answer": a["answer"]} | {
                        _key(c): a["answer"] + "\n\n" + _payload(fields, c) for c in _CAPS
                    }
                    got = await _score_payloads(provider, ask=ask, facts=allf, payloads=payloads, model=model)
                    cov = {k: round(len(v) / len(allf), 3) for k, v in got.items()}
                    reps_out.append({"coverage": cov, "a_tokens": a["completion_tokens"]})
                    shown = "  ".join(f"{_key(c).replace('cap_', '')}={cov[_key(c)]:.2f}" for c in _CAPS)
                    print(f"      rep{rep + 1} ans={cov['answer']:.2f}  {shown}", flush=True)
                row["reps"] = reps_out
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                print(f"      -> ERROR {row['error'][:110]}", flush=True)
            rows.append(row)
            _OUT.write_text(json.dumps({"partial": True, "rows": rows}, indent=2))
    finally:
        await parts.aclose()

    scored = [r for r in rows if r.get("reps")]
    rounds = [rep["coverage"] for r in scored for rep in r["reps"]]

    def _m(k: str) -> float | None:
        v = [x[k] for x in rounds if k in x]
        return round(statistics.fmean(v), 3) if v else None

    base = _m("answer") or 0.0
    tok_a = statistics.fmean([rep["a_tokens"] for r in scored for rep in r["reps"]]) if scored else 0.0

    table: dict[str, dict[str, Any]] = {}
    for c in _CAPS:
        k = _key(c)
        wire = statistics.fmean([r["wire_tokens"][k] for r in scored]) if scored else 0.0
        cov = _m(k) or 0.0
        st = _paired(rounds, k, "answer")
        half = 1.96 * st["stdev"] / (st["n"] ** 0.5) if st.get("n", 0) > 1 else 0.0
        table[k] = {
            "coverage": cov,
            "lift_over_answer": round(cov - base, 4),
            "ci_half": round(half, 4),
            "signif": bool(abs(st.get("mean", 0.0)) > half > 0),
            "mean_wire_tokens": round(wire, 1),
            "median_wire_tokens": statistics.median([r["wire_tokens"][k] for r in scored]) if scored else 0,
            # Coverage points bought per 1k wire tokens. The whole cap question
            # is whether this rises as the cap falls.
            "lift_per_1k_wire": round((cov - base) / wire * 1000, 4) if wire else None,
        }

    summary = {
        "provider": str(getattr(provider, "name", raw_name)),
        "model": model,
        "reps": reps,
        "n_scored": len(scored),
        "chars_per_token_estimate": _CHARS_PER_TOKEN,
        "answer_coverage": base,
        "answer_completion_tokens": round(tok_a, 1),
        "caps": table,
        "declared_field_count": {r["slug"]: r.get("declared_field_count") for r in rows},
        "rows": rows,
    }
    _OUT.write_text(json.dumps(summary, indent=2))

    print("\n=== summary ===")
    print(f"  pages scored: {len(scored)}/{len(rows)}   answer coverage: {base}  ({round(tok_a)} completion tokens)")
    print(f"\n  {'cap':>6} {'coverage':>9} {'lift':>8} {'+/-':>7} {'wire~tok':>9} {'median':>7} {'lift/1k':>9}")
    for c in _CAPS:
        t = table[_key(c)]
        name = str(c) if c is not None else "all"
        sig = "*" if t["signif"] else " "
        print(
            f"  {name:>6} {t['coverage']:>9.3f} {t['lift_over_answer']:>+8.3f}{sig}{t['ci_half']:>6.3f} "
            f"{t['mean_wire_tokens']:>9.0f} {t['median_wire_tokens']:>7.0f} {t['lift_per_1k_wire']:>9.3f}"
        )
    print("\n  * = paired lift over `answer` is significant at 95%")
    print("  lift/1k = coverage points bought per 1000 wire tokens; RISING as the cap")
    print("            falls means the tail is dead weight and a cap is justified.")
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
