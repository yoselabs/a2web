"""Spike v4 — is the page's OWN declared entity data worth building on?

v3 measured the LLM-generated entity block and it lost: 4.6 sparse fields, 11%
coverage, no lift over the answer, ~76 tokens. But v3 measured the WRONG HALF
well and the right half badly — it read declared JSON-LD via a single cheap
`raw` fetch, which anti-bot blocks on exactly the sites with the richest
subject-level declarations (commerce `Product` with price / currency / stock /
sku / brand / rating). Those pages reported `declared=(none)` and the arm meant
to test the user's actual instinct ran with nothing to test.

**This spike fixes that one thing.** HTML comes from an ESCALATING ladder
(`raw` → `browser` → `browser_robust`), the way production retrieves, so a
blocked cheap fetch is no longer mistaken for a page that publishes nothing.

**The question.** Of the facts a page states, how many reach a caller through:

    answer            what ships today
    llm_fields        the v3 block (measured again here, same inventory,
                      so the two paths are compared apples-to-apples rather
                      than across runs)
    declared_fields   what the PAGE published, parsed, zero tokens
    answer+declared   what a caller would actually get if we shipped it

`answer+declared − answer` is the deterministic path's contribution, and unlike
the LLM path it costs **no tokens and has no wobble** — a deterministic parse
is trivially 100% stable across reps, which is the property the LLM path failed
at (58%). So even a small lift is bought at a very different price.

**Document types vs subject types.** v3 found most declared `@type`s describe
the DOCUMENT (`Article`, `WebPage`, `WebSite` — publisher / logo / sameAs
metadata), not the subject. Those belong on a2web's existing `structural_form`
axis. This spike labels each declared type so the two are never mixed, and
reports coverage separately for subject-level declarations — the case the whole
idea rests on.

The subject/document split is a **label table, never a gate** (ADR-0018): an
unrecognised type is reported as `unknown`, counted, and its fields still
scored. A closed list here would rebuild `_ENTITY_TYPES` inside the very spike
sent to measure it.

**Cost posture (ADR-0016).** Subscription only.

Live network + LLM quota. Not part of `make check`. Run:

    uv run python eval/spikes/declared_entity_v4.py [N_PAGES] [REPS]
"""

from __future__ import annotations

import asyncio
import collections
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

from anyllm import ProviderName, with_cost_guard
from json_in_html import extract_json_payloads, ld_entries

from a2web.components import build_components
from a2web.fetcher import fetch
from a2web.settings import AppSettings
from a2web.tiers import REGISTRY

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

_OUT = Path(__file__).resolve().parent / "declared_entity_v4_summary.json"

#: The escalation used to GET the HTML. Mirrors production's shape (cheap
#: first, browser when blocked) so "the page publishes nothing" and "we were
#: blocked" stop being the same observation — which is precisely the confusion
#: that made v3's declared arm inert.
_LADDER = ("raw", "browser", "browser_robust")

#: Weighted toward pages expected to declare SUBJECT-level entities — commerce,
#: recipe, job, event. v3's corpus was editorial-heavy, which is where declared
#: types are document metadata and the idea looks worst.
CASES: list[tuple[str, str, str]] = [
    (
        "hepsiburada-product",
        "https://www.hepsiburada.com/wilkinson-sword-wilkinson-swrod-hydro-5-ultimate-tirasmakinesi-1-adet-yedek-baslik-p-HBV00000UWKQ2",
        "What is this product, its price and currency, and is it in stock?",
    ),
    ("allrecipes", "https://www.allrecipes.com/recipe/213742/cheesy-scalloped-potatoes/", "How do I make this, and what goes in it?"),
    ("trendyol-product", "https://www.trendyol.com/apple/iphone-15-128-gb-p-751012800", "What is this product, its price, and its rating?"),
    ("bbc-article", "https://www.bbc.com/news", "What are the main news stories right now?"),
    ("pypi-httpx", "https://pypi.org/project/httpx/", "What is httpx, its current version, and which Python versions it supports?"),
    (
        "wikipedia-rust",
        "https://en.wikipedia.org/wiki/Rust_(programming_language)",
        "Who created Rust and in what year did it first appear?",
    ),
    ("imdb-title", "https://www.imdb.com/title/tt0111161/", "What is this film, who directed it, and what is its rating?"),
    (
        "booking-hotel",
        "https://www.marriott.com/en-us/hotels/istmc-istanbul-marriott-hotel-asia/overview/",
        "What hotel is this, where is it, and what does it offer?",
    ),
]

#: LABEL TABLE, NOT A GATE (ADR-0018). Used only to report which declarations
#: are about the SUBJECT vs about the DOCUMENT. An unlisted type is reported as
#: `unknown` and its fields are still parsed and scored — a closed list here
#: would rebuild `_ENTITY_TYPES` inside the spike sent to measure it.
_DOCUMENT_TYPES = frozenset(
    {
        "Article",
        "NewsArticle",
        "BlogPosting",
        "WebPage",
        "WebSite",
        "BreadcrumbList",
        "CollectionPage",
        "ItemPage",
        "SearchResultsPage",
        "ImageObject",
        "Organization",
        "SiteNavigationElement",
    }
)
_SUBJECT_TYPES = frozenset(
    {
        "Product",
        "Recipe",
        "JobPosting",
        "Event",
        "Person",
        "Movie",
        "TVSeries",
        "Book",
        "Course",
        "Dataset",
        "SoftwareApplication",
        "SoftwareSourceCode",
        "Hotel",
        "LocalBusiness",
        "Restaurant",
        "Place",
        "MusicRecording",
        "Offer",
        "AggregateRating",
        "Review",
        "Episode",
        "VideoObject",
    }
)


def _label(t: str) -> str:
    if t in _SUBJECT_TYPES:
        return "subject"
    if t in _DOCUMENT_TYPES:
        return "document"
    return "unknown"


def _flatten(entry: dict, prefix: str = "", depth: int = 0) -> dict[str, str]:
    """Flatten one JSON-LD entity to `key: value` pairs.

    Flat because the consumer is an agent reading a dict, not a schema.org
    validator — and because schema.org's own `additionalProperty` nesting
    carries a documented caveat that consumers expecting `price` will not look
    inside it. Depth-capped: JSON-LD graphs can self-reference.
    """
    out: dict[str, str] = {}
    if depth > 3:
        return out
    for k, v in entry.items():
        if k.startswith("@"):
            continue
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + ".", depth + 1))
        elif isinstance(v, list):
            scalars = [str(x) for x in v if not isinstance(x, dict | list)]
            if scalars:
                out[key] = "; ".join(scalars[:12])[:400]
            else:
                for i, item in enumerate(v[:6]):
                    if isinstance(item, dict):
                        out.update(_flatten(item, f"{key}[{i}].", depth + 1))
        elif v is not None:
            out[key] = str(v)[:400]
    return out


async def _html_via_ladder(parts: Any, url: str) -> tuple[str, str]:
    """Return `(html, tier)` from the first ladder rung that yields JSON-LD.

    Falls through on a blocked/empty rung instead of concluding the page
    publishes nothing — the v3 defect this spike exists to fix.
    """
    state = await parts.state()
    best_html, best_tier = "", "none"
    for name in _LADDER:
        tier = REGISTRY.get(name)
        if tier is None:
            continue
        try:
            result = await tier.fetch(url, state=state)
        except Exception:
            continue
        html = (result.body or b"").decode("utf-8", "replace")
        if not html:
            rendered = getattr(result, "pre_rendered", None)
            html = getattr(rendered, "content_md", "") or "" if rendered else ""
        if len(html) > len(best_html):
            best_html, best_tier = html, name
        if any(p.source == "ld_json" for p in extract_json_payloads(html)):
            return html, name
    return best_html, best_tier


def _declared(html: str) -> tuple[dict[str, str], list[str], dict[str, dict[str, str]]]:
    """All declared entities, flattened. Returns (merged_fields, types, per_type)."""
    per_type: dict[str, dict[str, str]] = {}
    types: list[str] = []
    for payload in extract_json_payloads(html):
        if payload.source != "ld_json":
            continue
        for entry in ld_entries(payload.data):
            if not isinstance(entry, dict):
                continue
            t = entry.get("@type")
            t = (t[0] if t else None) if isinstance(t, list) else t
            t = str(t) if t else "Thing"
            if t not in types:
                types.append(t)
            fields = _flatten(entry)
            if len(fields) > len(per_type.get(t, {})):
                per_type[t] = fields
    merged: dict[str, str] = {}
    # Subject entities first, so a truncated payload keeps the useful half.
    for t in sorted(types, key=lambda x: 0 if _label(x) == "subject" else 1):
        for k, v in per_type[t].items():
            merged.setdefault(f"{k}" if len(types) == 1 else f"{t}.{k}", v)
    return merged, types, per_type


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(CASES)
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    cases = CASES[:limit]

    settings = AppSettings()
    raw_name = os.environ.get(_PROVIDER_ENV, "").strip().lower() or _DEFAULT_PROVIDER
    from a2web.llm_resource import select_provider

    provider = select_provider(settings, override=ProviderName(raw_name))
    if provider is None:
        raise SystemExit(f"declared_entity_v4: no LLM provider available (tried: {raw_name})")
    provider = with_cost_guard(provider)
    model = settings.llm_model

    parts = build_components(settings=settings)
    rows: list[dict[str, Any]] = []
    try:
        for i, (slug, url, ask) in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {slug}", flush=True)
            row: dict[str, Any] = {"slug": slug, "url": url, "ask": ask}
            try:
                html, tier = await _html_via_ladder(parts, url)
                fields, types, per_type = _declared(html)
                labels = {t: _label(t) for t in types}
                row |= {
                    "html_tier": tier,
                    "html_chars": len(html),
                    "declared_types": types,
                    "type_labels": labels,
                    "declared_field_count": len(fields),
                    "has_subject": any(v == "subject" for v in labels.values()),
                    "declared_fields": fields,
                }
                print(
                    f"      html via {tier} ({len(html)}c)  types={types or '(none)'} -> {list(labels.values()) or []}  fields={len(fields)}",
                    flush=True,
                )

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
                allf = inv["core"] + inv["adjacent"]
                row["inventory"] = inv
                if not allf:
                    row["skipped"] = "no inventory"
                    rows.append(row)
                    continue

                arms = _build_arms([])  # no recommendation clause; v3 settled that it changes nothing
                declared_text = _fields_as_text(fields)

                reps_out = []
                for rep in range(reps):
                    a = await _run_arm(provider, arms["A"], content=content, ask=ask, model=model)
                    b = await _run_arm(provider, arms["B"], content=content, ask=ask, model=model)
                    payloads = {
                        "answer": a["answer"],
                        "llm_fields": _fields_as_text(b["entity_fields"]),
                        "declared_fields": declared_text,
                        "answer_plus_declared": a["answer"] + "\n\n" + declared_text,
                        "answer_plus_llm": b["answer"] + "\n\n" + _fields_as_text(b["entity_fields"]),
                    }
                    got = await _score_payloads(provider, ask=ask, facts=allf, payloads=payloads, model=model)
                    cov = {k: round(len(v) / len(allf), 3) for k, v in got.items()}
                    reps_out.append(
                        {
                            "coverage": cov,
                            "a_tokens": a["completion_tokens"],
                            "b_tokens": b["completion_tokens"],
                            "llm_field_count": b.get("entity_field_count", 0),
                        }
                    )
                    print(
                        f"      rep{rep + 1} ans={cov['answer']:.2f} llm_fld={cov['llm_fields']:.2f} "
                        f"decl_fld={cov['declared_fields']:.2f} ans+decl={cov['answer_plus_declared']:.2f} "
                        f"ans+llm={cov['answer_plus_llm']:.2f}",
                        flush=True,
                    )
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
    subj = [r for r in scored if r.get("has_subject")]
    subj_rounds = [rep["coverage"] for r in subj for rep in r["reps"]]

    def _m(rs: list[dict[str, float]], k: str) -> float | None:
        v = [x[k] for x in rs if k in x]
        return round(statistics.fmean(v), 3) if v else None

    keys = ("answer", "llm_fields", "declared_fields", "answer_plus_declared", "answer_plus_llm")
    tok_a = statistics.fmean([rep["a_tokens"] for r in scored for rep in r["reps"]]) if scored else 0
    tok_b = statistics.fmean([rep["b_tokens"] for r in scored for rep in r["reps"]]) if scored else 0
    lift = (_m(rounds, "answer_plus_declared") or 0) - (_m(rounds, "answer") or 0)

    summary = {
        "provider": str(getattr(provider, "name", raw_name)),
        "model": model,
        "reps": reps,
        "n_pages": len(rows),
        "n_scored": len(scored),
        "n_with_subject_declaration": len(subj),
        "coverage_all": {k: _m(rounds, k) for k in keys},
        "coverage_subject_pages_only": {k: _m(subj_rounds, k) for k in keys},
        "paired": {
            "answer_plus_declared-answer": _paired(rounds, "answer_plus_declared", "answer"),
            "answer_plus_llm-answer": _paired(rounds, "answer_plus_llm", "answer"),
            "declared_fields-llm_fields": _paired(rounds, "declared_fields", "llm_fields"),
            "answer_plus_declared-answer_plus_llm": _paired(rounds, "answer_plus_declared", "answer_plus_llm"),
        },
        "paired_subject_pages": {
            "answer_plus_declared-answer": _paired(subj_rounds, "answer_plus_declared", "answer"),
        },
        "declared_field_count": {r["slug"]: r.get("declared_field_count") for r in rows},
        "declared_types": {r["slug"]: r.get("declared_types") for r in rows},
        "html_tier": {r["slug"]: r.get("html_tier") for r in rows},
        "llm_field_count_mean": round(statistics.fmean([rep["llm_field_count"] for r in scored for rep in r["reps"]]), 1)
        if scored
        else None,
        "tokens": {"A": round(tok_a, 1), "B": round(tok_b, 1), "declared": 0},
        "lift_declared_over_answer": round(lift, 4),
        "type_label_counts": dict(collections.Counter(lbl for r in rows for lbl in (r.get("type_labels") or {}).values())),
        "rows": rows,
    }
    _OUT.write_text(json.dumps(summary, indent=2))

    print("\n=== summary ===")
    print(f"  pages scored : {len(scored)}/{len(rows)}   with a SUBJECT declaration: {len(subj)}")
    print(f"  html tiers   : {summary['html_tier']}")
    print(f"  declared types: {summary['declared_types']}")
    print(f"  type labels  : {summary['type_label_counts']}")
    print("\n  COVERAGE (all scored pages):")
    for k in keys:
        print(f"    {k:22s} {summary['coverage_all'][k]}")
    if subj:
        print("\n  COVERAGE (pages declaring a SUBJECT entity only)  <- the case the idea rests on:")
        for k in keys:
            print(f"    {k:22s} {summary['coverage_subject_pages_only'][k]}")
    print("\n  PAIRED:")
    for k, st in {**summary["paired"], **{f"[subject] {a}": b for a, b in summary["paired_subject_pages"].items()}}.items():
        if st.get("n"):
            half = 1.96 * st["stdev"] / (st["n"] ** 0.5) if st["n"] > 1 else 0.0
            sig = "SIGNIF" if abs(st["mean"]) > half > 0 else "(null)"
            print(f"    {k:42s} {st['mean']:+.4f} 95%CI=[{st['mean'] - half:+.3f},{st['mean'] + half:+.3f}] n={st['n']} {sig}")
    print(f"\n  fields: declared={summary['declared_field_count']}")
    print(f"          llm mean={summary['llm_field_count_mean']}")
    print(f"  tokens: {summary['tokens']}   <- declared costs ZERO, and is 100% stable by construction")
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
