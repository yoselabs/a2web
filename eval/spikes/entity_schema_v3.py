"""Spike v3 — completeness, cost, and helpfulness of the entity block.

v1/v2 answered "does the schema make a2web say LESS?" (no) and "which
ingredient is harmful?" (only the suppression directive). Both scored the
`answer` field. Neither asked the three questions this one exists for:

    COMPLETENESS  does `entity_fields` actually capture the page, or only a
                  handful of obvious properties?
    COST          what does that completeness cost, per unit delivered?
    HELPFULNESS   does the caller RECEIVE more because the block is there —
                  or does it just restate what the answer already said?

**Helpfulness is measured as delivered coverage, not as a vibe.** The caller
never sees the page. So the honest question is: of the facts the page states,
how many reach the caller through the whole envelope? Scored three ways against
one fixed inventory:

    answer_only    what arm A delivers today
    fields_only    what `entity_fields` alone would deliver
    combined       answer + entity_fields, which is what the caller gets

`combined − answer_only` is the block's actual contribution. Divided by the
extra completion tokens it cost, that is the exchange rate the ship/no-ship
decision needs, and neither previous spike could compute it.

**Arms** — the user's design decisions, now testable:

    A  control        ships today. no entity block.
    B  free           entity block, model picks the type unaided (v2's winner).
    E  recommended    entity block + the page's OWN declared schema.org @type,
                      injected as a RECOMMENDATION, not a rule:
                      "the page declares X; prefer it UNLESS another type is
                      richer." Per the user, 2026-08-03 — a hard override was
                      rejected because a declared type can be poorer than what
                      the page actually is (a product page declaring `WebSite`).

E only differs from B on pages that declare something; on the rest the two are
the same prompt, which is deliberate — it bounds how much of any E-vs-B effect
can possibly come from the recommendation.

**Type stability** is re-measured across reps, since it is the property a
semantic (query-by-meaning) interface would rest on, and v2 found it at 62%.
`entity_type_source` (declared | inferred) is recorded so stability can be read
separately for each — the whole point of the user's rule is that only the
declared half needs to be stable.

**Never drop a field to fit a type** (user, 2026-08-03) is now stated IN the
prompt block rather than only in the findings, so the arm under test embodies
the rule instead of merely being scored against it.

**Cost posture (ADR-0016).** Subscription only, same as the sibling spikes.

Live network + LLM quota. Not part of `make check`. Run:

    uv run python eval/spikes/entity_schema_v3.py [N_PAGES] [REPS]
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import sys
from pathlib import Path
from typing import Any

from anyllm import ProviderName, with_cost_guard
from json_in_html import extract_json_payloads, ld_entries

from a2web.components import build_components
from a2web.packages.llm_extract.prompts import _ROUTER_SCHEMA_DOC, EXTRACT_ROUTER_V1, PromptTemplate
from a2web.settings import AppSettings
from a2web.tiers import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.spikes.entity_schema_v2 import (  # noqa: E402
    _CONTENT_CAP,
    _DEFAULT_PROVIDER,
    _JUDGE_CONTENT_CAP,
    _MAX_ADJACENT,
    _MAX_CORE,
    _PROVIDER_ENV,
    _SCHEMA_ORG_COMMON,
    _complete,
    _INVENTORY_SYSTEM,
    _INVENTORY_USER,
    _loads,
    _paired,
)

_OUT = Path(__file__).resolve().parent / "entity_schema_v3_summary.json"

#: Weighted toward pages that DECLARE a schema.org type, because arm E is
#: inert without them — the v2 corpus had only 5 declaring pages in 26, which
#: would have left the recommendation arm untested on most rows.
CASES: list[tuple[str, str, str]] = [
    (
        "hepsiburada-product",
        "https://www.hepsiburada.com/wilkinson-sword-wilkinson-swrod-hydro-5-ultimate-tirasmakinesi-1-adet-yedek-baslik-p-HBV00000UWKQ2",
        "What is this product, its price and currency, and is it in stock?",
    ),
    (
        "hepsiburada-bic",
        "https://www.hepsiburada.com/bic-flex-5-tiras-bicagi-6-yedek-tiras-bicagi-can-p-HBV00000QN9YB",
        "What is this product and what do the reviews say about it?",
    ),
    (
        "wikipedia-rust",
        "https://en.wikipedia.org/wiki/Rust_(programming_language)",
        "Who created Rust and in what year did it first appear?",
    ),
    ("python-contact", "https://www.python.org/about/help/", "How can I contact them — is there an email or a specific channel?"),
    ("bbc-news", "https://www.bbc.com/news", "What are the main news stories right now?"),
    ("allrecipes", "https://www.allrecipes.com/recipe/213742/cheesy-scalloped-potatoes/", "How do I make this, and what goes in it?"),
    ("pypi-httpx", "https://pypi.org/project/httpx/", "What is httpx, its current version, and which Python versions it supports?"),
    ("hn-item", "https://news.ycombinator.com/item?id=9224", "What is this discussion about, and what is the main disagreement?"),
    ("github-ruff", "https://github.com/astral-sh/ruff", "What is ruff and what are its main features?"),
    ("arxiv-abstract", "https://arxiv.org/abs/2401.05566", "What is the paper's title and its main contribution?"),
]

# --------------------------------------------------------------------------
# The entity block
# --------------------------------------------------------------------------

#: Carries the two rules the user settled on 2026-08-03: the type is a LABEL
#: (never a filter that drops fields), and the official vocabulary is a floor
#: (site-invented properties are the point, not noise).
_ENTITY_BLOCK = """
  entity_type (required, string) — the schema.org @type of the PRIMARY THING this
    page is about: "Product", "Person", "Article", "ScholarlyArticle", "JobPosting",
    "Recipe", "SoftwareApplication", "Organization", "Event", ... Use the schema.org
    vocabulary when one fits. If nothing fits, write the most accurate name you can
    rather than forcing a wrong one — this field is NOT validated against a list.
    If the page is a listing of many things, give the type of the ITEMS.
    NEVER omit this field; write "Thing" if the page is genuinely about no one thing.

  entity_fields (required, object of string -> string) — that entity's properties AS
    STATED ON THE PAGE, flat. Use schema.org property names where one fits (name,
    price, priceCurrency, brand, author, datePublished, version, ...) and the SITE'S
    OWN name for anything schema.org does not cover (discountPrice, couponCode,
    whatever this page invented this quarter).
    THE TYPE IS A LABEL, NEVER A FILTER: never drop a property because it does not
    fit `entity_type`, and never drop one because the official vocabulary has no slot
    for it. If the page states it about this thing, it belongs here. Be EXHAUSTIVE —
    this is the caller's only structured view of a page they will never see.
    Empty object {} when the page is about no particular thing.
"""

_ANCHOR_OBSTACLE = "\n  obstacle (optional, ONE of)"


def _recommendation(declared: list[str]) -> str:
    """Arm E's extra clause. Empty when the page declared nothing, so E and B
    are byte-identical there — which bounds how much of an E-vs-B difference
    could possibly be caused by the recommendation."""
    if not declared:
        return ""
    names = " / ".join(declared[:4])
    return (
        f"\nTHIS PAGE DECLARES ITS OWN TYPE in structured data: {names}.\n"
        "PREFER that for `entity_type` — it is the publisher's own statement.\n"
        "Override it ONLY if another type is genuinely RICHER (describes more of what\n"
        "this page actually is). A declared type can be too generic (a product page\n"
        "declaring `WebSite`); richer wins. Either way `entity_fields` stays exhaustive.\n"
    )


def _build_arms(declared: list[str]) -> dict[str, PromptTemplate]:
    doc = _ROUTER_SCHEMA_DOC
    if _ANCHOR_OBSTACLE not in doc:
        raise SystemExit("entity_schema_v3: splice anchor gone from _ROUTER_SCHEMA_DOC; re-derive the arms")
    doc_b = doc.replace(_ANCHOR_OBSTACLE, _ENTITY_BLOCK + _ANCHOR_OBSTACLE, 1)
    doc_e = doc_b + _recommendation(declared)
    if doc_b == doc:
        raise SystemExit("entity_schema_v3: arm B came out identical to the control")

    base = EXTRACT_ROUTER_V1.system[:-1]

    def _arm(name: str, schema_doc: str) -> PromptTemplate:
        return PromptTemplate(
            name=name,
            version=EXTRACT_ROUTER_V1.version,
            system=(*base, schema_doc),
            cache_prefix_template=EXTRACT_ROUTER_V1.cache_prefix_template,
            tail_template=EXTRACT_ROUTER_V1.tail_template,
        )

    return {"A": EXTRACT_ROUTER_V1, "B": _arm("entity_free", doc_b), "E": _arm("entity_recommended", doc_e)}


# --------------------------------------------------------------------------
# Scoring — three deliveries against ONE inventory
# --------------------------------------------------------------------------

_SCORING_SYSTEM = (
    "You score what a reader would learn from each of several delivery payloads, "
    "against a fixed fact list. You do not know which system produced which. "
    "Output strict JSON only."
)

_SCORING_USER = """A user asked this question about a web page:

QUESTION: {ask}

Numbered facts the page states:

{facts}

Below are several PAYLOADS a system delivered to a reader who cannot see the page.
For each label, list the NUMBERS of the facts a reader would learn FROM THAT
PAYLOAD ALONE. A fact counts only if the payload states or clearly implies it.
Structured key/value data counts exactly as much as prose — judge the information,
not the format.

{answers}

Strict JSON only, no prose, no markdown fence. One key per label:
{{{keys}}}"""


def _fields_as_text(fields: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in fields.items()) if fields else "(no structured fields)"


async def _score_payloads(provider: Any, *, ask: str, facts: list[str], payloads: dict[str, str], model: str) -> dict[str, list[int]]:
    keys = list(payloads)
    random.shuffle(keys)
    labels = [chr(ord("P") + i) for i in range(len(keys))]
    mapping = dict(zip(labels, keys, strict=True))
    numbered = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(facts))
    blocks = "\n\n".join(f"--- {lab} ---\n{payloads[k] or '(empty)'}" for lab, k in mapping.items())
    key_spec = ", ".join(f'"{lab}": [<numbers>]' for lab in labels)
    text, _ = await _complete(
        provider,
        system=_SCORING_SYSTEM,
        user=_SCORING_USER.format(ask=ask, facts=numbered, answers=blocks, keys=key_spec),
        model=model,
        max_tokens=2048,
    )
    payload = _loads(text) or {}
    out: dict[str, list[int]] = {}
    for lab, k in mapping.items():
        hits = payload.get(lab)
        out[k] = sorted({int(n) for n in hits if isinstance(n, int) and 1 <= n <= len(facts)}) if isinstance(hits, list) else []
    return out


async def _inventory2(provider: Any, *, content: str, ask: str, model: str) -> dict[str, list[str]]:
    text, _ = await _complete(
        provider,
        system=_INVENTORY_SYSTEM,
        user=_INVENTORY_USER.format(content=content[:_JUDGE_CONTENT_CAP], ask=ask, max_core=_MAX_CORE, max_adjacent=_MAX_ADJACENT),
        model=model,
        max_tokens=4096,
    )
    payload = _loads(text) or {}
    out: dict[str, list[str]] = {}
    for key, cap in (("core", _MAX_CORE), ("adjacent", _MAX_ADJACENT)):
        facts = payload.get(key)
        out[key] = [str(f) for f in facts][:cap] if isinstance(facts, list) else []
    return out


async def _run_arm(provider: Any, template: PromptTemplate, *, content: str, ask: str, model: str) -> dict[str, Any]:
    parts = template.render(content=content, ask=ask)
    user = parts.cache_prefix + parts.tail if parts.cache_prefix else parts.tail
    text, tokens = await _complete(provider, system=parts.system, user=user, model=model, max_tokens=4096)
    payload = _loads(text)
    if payload is None:
        return {"parse_failed": True, "completion_tokens": tokens, "answer": "", "entity_fields": {}}
    fields = payload.get("entity_fields")
    fields = {str(k): str(v) for k, v in fields.items()} if isinstance(fields, dict) else {}
    answer = payload.get("answer")
    return {
        "parse_failed": False,
        "answer": answer if isinstance(answer, str) else "",
        "entity_type": payload.get("entity_type"),
        "entity_fields": fields,
        "entity_field_count": len(fields),
        "entity_extra_fields": [k for k in fields if k.lower() not in _SCHEMA_ORG_COMMON],
        "also_here": len(payload.get("also_here") or []) if isinstance(payload.get("also_here"), list) else 0,
        "completion_tokens": tokens,
    }


async def _declared_types(parts: Any, url: str) -> list[str]:
    """The page's OWN schema.org @type values, read from its JSON-LD."""
    result = await REGISTRY["raw"].fetch(url, state=await parts.state())
    html = (result.body or b"").decode("utf-8", "replace")
    types: list[str] = []
    for payload in extract_json_payloads(html):
        if payload.source != "ld_json":
            continue
        for entry in ld_entries(payload.data):
            if isinstance(entry, dict):
                t = entry.get("@type")
                if isinstance(t, list):
                    types.extend(str(x) for x in t if x)
                elif t:
                    types.append(str(t))
    seen: list[str] = []
    for t in types:
        if t not in seen:
            seen.append(t)
    return seen


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(CASES)
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    cases = CASES[:limit]

    settings = AppSettings()
    raw = os.environ.get(_PROVIDER_ENV, "").strip().lower() or _DEFAULT_PROVIDER
    try:
        override = ProviderName(raw)
    except ValueError:
        raise SystemExit(f"entity_schema_v3: unknown provider id {raw!r}") from None
    provider = select_provider_or_die(settings, override)
    model = settings.llm_model

    parts = build_components(settings=settings)
    rows: list[dict[str, Any]] = []
    try:
        for i, (slug, url, ask) in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {slug}", flush=True)
            row: dict[str, Any] = {"slug": slug, "url": url, "ask": ask}
            try:
                declared = await _declared_types(parts, url)
                row["declared"] = declared
                arms = _build_arms(declared)

                from a2web.fetcher import fetch

                response = await fetch(
                    url,
                    state=await parts.state(),
                    llm_extractor=parts.llm_extractor,
                    browser_backend=parts.browser_backend,
                    browser_robust_backend=parts.browser_robust_backend,
                    cookie_jar=parts.cookie_jar,
                )
                content = (response.content_md or "")[:_CONTENT_CAP]
                row["content_chars"] = len(content)
                if len(content) < 500:
                    row["skipped"] = "content too thin"
                    rows.append(row)
                    print(f"      -> SKIP ({len(content)}c)", flush=True)
                    continue

                inv = await _inventory2(provider, content=content, ask=ask, model=model)
                row["core_count"], row["adjacent_count"] = len(inv["core"]), len(inv["adjacent"])
                row["inventory"] = inv
                allf = inv["core"] + inv["adjacent"]
                if not allf:
                    row["skipped"] = "no inventory"
                    rows.append(row)
                    continue
                print(f"      declared={declared or '(none)'}  inventory core={len(inv['core'])} adj={len(inv['adjacent'])}", flush=True)

                reps_out = []
                for rep in range(reps):
                    res = {a: await _run_arm(provider, t, content=content, ask=ask, model=model) for a, t in arms.items()}
                    # Three deliveries per entity arm, one for the control, all
                    # graded against ONE inventory in ONE call so the judge
                    # cannot drift between them.
                    payloads = {
                        "A_answer": res["A"]["answer"],
                        "B_answer": res["B"]["answer"],
                        "B_fields": _fields_as_text(res["B"]["entity_fields"]),
                        "B_combined": res["B"]["answer"] + "\n\n" + _fields_as_text(res["B"]["entity_fields"]),
                        "E_combined": res["E"]["answer"] + "\n\n" + _fields_as_text(res["E"]["entity_fields"]),
                    }
                    got = await _score_payloads(provider, ask=ask, facts=allf, payloads=payloads, model=model)
                    cov = {k: round(len(v) / len(allf), 3) for k, v in got.items()}
                    reps_out.append({"arms": res, "coverage": cov, "covered": got})
                    print(
                        f"      rep{rep + 1} cover A={cov['A_answer']:.2f} B_ans={cov['B_answer']:.2f} "
                        f"B_fld={cov['B_fields']:.2f} B_all={cov['B_combined']:.2f} E_all={cov['E_combined']:.2f} "
                        f"| type B={res['B'].get('entity_type')!r} E={res['E'].get('entity_type')!r}",
                        flush=True,
                    )
                row["reps"] = reps_out
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                print(f"      -> ERROR {row['error'][:100]}", flush=True)
            rows.append(row)
            _OUT.write_text(json.dumps({"partial": True, "rows": rows}, indent=2))
    finally:
        await parts.aclose()

    scored = [r for r in rows if r.get("reps")]
    rounds = [rep["coverage"] for r in scored for rep in r["reps"]]
    runs = [rep["arms"] for r in scored for rep in r["reps"]]

    def _m(key: str) -> float | None:
        v = [rd[key] for rd in rounds if key in rd]
        return round(statistics.fmean(v), 3) if v else None

    def _tok(arm: str) -> float | None:
        v = [x[arm]["completion_tokens"] for x in runs if not x[arm].get("parse_failed")]
        return round(statistics.fmean(v), 1) if v else None

    # Type stability, split by whether the page declared a type — the whole
    # point of the user's rule is that only the declared half must be stable.
    stab: dict[str, dict[str, int]] = {"declared": {"stable": 0, "total": 0}, "inferred": {"stable": 0, "total": 0}}
    for r in scored:
        bucket = "declared" if r.get("declared") else "inferred"
        for arm in ("B", "E"):
            ts = [rep["arms"][arm].get("entity_type") for rep in r["reps"]]
            stab[bucket]["total"] += 1
            if len(set(ts)) == 1:
                stab[bucket]["stable"] += 1

    followed = sum(
        1 for r in scored if r.get("declared") for rep in r["reps"] if rep["arms"]["E"].get("entity_type") in (r["declared"] or [])
    )
    declared_rounds = sum(len(r["reps"]) for r in scored if r.get("declared"))

    delta_tok = (_tok("B") or 0) - (_tok("A") or 0)
    lift = (_m("B_combined") or 0) - (_m("A_answer") or 0)
    summary = {
        "provider": str(getattr(provider, "name", raw)),
        "model": model,
        "reps": reps,
        "n_pages": len(rows),
        "n_scored": len(scored),
        "n_rounds": len(rounds),
        "coverage_mean": {k: _m(k) for k in ("A_answer", "B_answer", "B_fields", "B_combined", "E_combined")},
        "paired": {
            "B_combined-A_answer": _paired(rounds, "B_combined", "A_answer"),
            "B_fields-A_answer": _paired(rounds, "B_fields", "A_answer"),
            "B_answer-A_answer": _paired(rounds, "B_answer", "A_answer"),
            "E_combined-B_combined": _paired(rounds, "E_combined", "B_combined"),
        },
        "completion_tokens_mean": {a: _tok(a) for a in ("A", "B", "E")},
        "delta_tokens_B_minus_A": round(delta_tok, 1),
        "coverage_lift_B_over_A": round(lift, 4),
        "extra_facts_per_1k_tokens": round(1000 * lift / delta_tok, 2) if delta_tok else None,
        "type_stability": stab,
        "E_followed_declared": f"{followed}/{declared_rounds}",
        "entity_field_count_mean": round(statistics.fmean([x["B"].get("entity_field_count", 0) for x in runs]), 1) if runs else None,
        "rows": rows,
    }
    _OUT.write_text(json.dumps(summary, indent=2))

    print("\n=== summary ===")
    print(f"  pages/rounds : {len(scored)}/{len(rows)}, {len(rounds)} rounds (reps={reps})")
    print("\n  COVERAGE of page facts DELIVERED to the caller:")
    for k, v in summary["coverage_mean"].items():
        print(f"    {k:12s} {v}")
    print("\n  PAIRED deltas:")
    for k, st in summary["paired"].items():
        if st.get("n"):
            half = 1.96 * st["stdev"] / (st["n"] ** 0.5) if st["n"] > 1 else 0.0
            sig = "SIGNIF" if abs(st["mean"]) > half > 0 else "(null)"
            print(
                f"    {k:26s} {st['mean']:+.4f} 95%CI=[{st['mean'] - half:+.3f},{st['mean'] + half:+.3f}] W/T/L={st['wins']}/{st['ties']}/{st['losses']} {sig}"
            )
    print(f"\n  tokens        : {summary['completion_tokens_mean']}  (B-A = {summary['delta_tokens_B_minus_A']})")
    print(f"  EXCHANGE RATE : +{summary['coverage_lift_B_over_A']:.3f} coverage for {summary['delta_tokens_B_minus_A']} tokens")
    print(f"                  = {summary['extra_facts_per_1k_tokens']} extra coverage-points per 1k tokens")
    print(f"  entity fields : {summary['entity_field_count_mean']} per page")
    print(f"\n  type stability: {stab}")
    print(f"  E followed the declared type: {summary['E_followed_declared']}")
    print(f"\nwrote {_OUT}")


def select_provider_or_die(settings: AppSettings, override: ProviderName) -> Any:
    from a2web.llm_resource import select_provider

    provider = select_provider(settings, override=override)
    if provider is None:
        raise SystemExit(f"entity_schema_v3: no LLM provider available (tried: {override})")
    return with_cost_guard(provider)


if __name__ == "__main__":
    asyncio.run(main())
