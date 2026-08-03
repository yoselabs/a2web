"""Spike v6 — how OFTEN does a page declare a subject entity?

v4 and v5 settled the conditional: *given* a page declares a subject-level
schema.org entity, relaying the first ~20 fields adds real coverage for ~360
wire tokens. The feature's actual value is that lift times **how often the
antecedent holds** — and that multiplier has never been measured. Every prior
number came from a corpus deliberately selected FOR declaring.

This spike measures the rate over a2web's own regression corpus
(`eval/corpus.yaml`, 44 URLs), which was assembled for fetch difficulty and
answer quality, not for structured data — so it is not selected on the variable
being measured.

**No LLM.** Fetch, parse JSON-LD, label the types, count. `make bench`-class
network cost only.

**The number is only readable alongside the retrieval failures.** This machine
has no proxies, no paid-tier keys, and an unreachable jina; a hard-walled page
returns no JSON-LD for a reason that has nothing to do with whether the
publisher emits it. v3 already produced a wrong verdict by conflating those two,
so every URL is bucketed:

    subject     declares a KNOWN subject-level entity -> the feature fires
    unknown     declares a type absent from both label tables. Counted
                SEPARATELY and never folded into `document`: the first run of
                this spike did fold them, and buried Nike's `ProductGroup` (74
                fields), v2ex's `DiscussionForumPosting` (51) and Reuters'
                `NewsMediaOrganization` (35) as "document metadata, no lift".
                That is ADR-0018's exact failure -- a2web's closed vocabulary
                acting as a GATE rather than a LABEL -- committed inside the
                spike sent to measure it, and it understated the rate by more
                than half. `unknown` is the reason the headline is a RANGE.
    document    declares only Article/WebPage/... -> structural_form, no lift
    none        retrieved fine, publishes no JSON-LD
    unreachable retrieval failed or returned a wall/stub

`none` is a fact about the web. `unreachable` is a fact about this machine, and
the honest rate is reported over the retrieved denominator with the excluded
count stated, never silently folded in.

Run:

    uv run python eval/spikes/declaration_rate_v6.py [N_URLS]
"""

from __future__ import annotations

import asyncio
import collections
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from a2web.components import build_components
from a2web.settings import AppSettings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.spikes.declared_entity_v4 import (  # noqa: E402
    _declared,
    _html_via_ladder,
    _label,
)

_CORPUS = Path(__file__).resolve().parents[1] / "corpus.yaml"
_OUT = Path(__file__).resolve().parent / "declaration_rate_v6_summary.json"

#: Below this a "retrieved" body is a stub, a challenge interstitial, or an
#: error page — not a page that chose not to publish JSON-LD. Bucketing those as
#: `none` is exactly the conflation this spike exists to avoid.
_MIN_HTML = 2000


async def main() -> None:
    urls = yaml.safe_load(_CORPUS.read_text())["urls"]
    if len(sys.argv) > 1:
        urls = urls[: int(sys.argv[1])]

    parts = build_components(settings=AppSettings())
    rows: list[dict[str, Any]] = []
    try:
        for i, case in enumerate(urls, 1):
            slug, url = case["slug"], case["url"]
            row: dict[str, Any] = {"slug": slug, "url": url, "class": case.get("class")}
            try:
                html, tier, errors = await _html_via_ladder(parts, url)
                fields, types, _per = _declared(html)
                labels = [_label(t) for t in types]
                if len(html) < _MIN_HTML:
                    bucket = "unreachable"
                elif "subject" in labels:
                    bucket = "subject"
                elif "unknown" in labels:
                    # NOT `document`. See the module docstring: folding these in
                    # is the closed-vocabulary-as-gate defect ADR-0018 forbids,
                    # and it halved this spike's own headline on the first run.
                    bucket = "unknown"
                elif labels:
                    bucket = "document"
                else:
                    bucket = "none"
                row |= {
                    "bucket": bucket,
                    "html_tier": tier,
                    "html_chars": len(html),
                    "ladder_errors": errors,
                    "declared_types": types,
                    "type_labels": labels,
                    "field_count": len(fields),
                    # What a cap-20 payload would actually cost on this page.
                    "capped_field_count": min(len(fields), 20),
                }
            except Exception as exc:
                row |= {"bucket": "unreachable", "error": f"{type(exc).__name__}: {exc}"}
            rows.append(row)
            print(
                f"[{i}/{len(urls)}] {slug:26s} {row['bucket']:12s} "
                f"{row.get('html_chars', 0):>8}c  {row.get('field_count', 0):>3} fields  "
                f"{row.get('declared_types') or ''}",
                flush=True,
            )
            _OUT.write_text(json.dumps({"partial": True, "rows": rows}, indent=2))
    finally:
        await parts.aclose()

    buckets = collections.Counter(r["bucket"] for r in rows)
    retrieved = [r for r in rows if r["bucket"] != "unreachable"]
    subject = [r for r in rows if r["bucket"] == "subject"]
    # The upper bound: `unknown` types are overwhelmingly subject-level in
    # practice (ProductGroup, DiscussionForumPosting), so the true rate sits
    # between the two and neither bound may be quoted alone.
    fires = [r for r in rows if r["bucket"] in ("subject", "unknown")]
    n_ret = len(retrieved) or 1

    by_class: dict[str, dict[str, int]] = collections.defaultdict(collections.Counter)  # type: ignore[arg-type]
    for r in rows:
        by_class[r.get("class") or "?"][r["bucket"]] += 1  # type: ignore[index]

    summary = {
        "n_urls": len(rows),
        "buckets": dict(buckets),
        "n_retrieved": len(retrieved),
        # THE number, as a RANGE: rate over what was actually retrieved, with
        # the excluded count kept adjacent so it can never be quoted without its
        # denominator, and the closed-list lower bound kept adjacent to the
        # open upper bound so it can never be quoted as the whole answer.
        "subject_rate_of_retrieved": round(len(subject) / n_ret, 3),
        "subject_or_unknown_rate_of_retrieved": round(len(fires) / n_ret, 3),
        "n_excluded_unreachable": buckets["unreachable"],
        "distinct_hosts_firing": sorted({r["url"].split("/")[2] for r in fires}),
        "mean_fields_when_subject": round(sum(r["field_count"] for r in subject) / len(subject), 1) if subject else None,
        "mean_capped_fields_when_subject": round(sum(r["capped_field_count"] for r in subject) / len(subject), 1)
        if subject
        else None,
        "by_class": {k: dict(v) for k, v in by_class.items()},
        "rows": rows,
    }
    _OUT.write_text(json.dumps(summary, indent=2))

    print("\n=== summary ===")
    print(f"  urls           : {len(rows)}")
    for b in ("subject", "unknown", "document", "none", "unreachable"):
        print(f"    {b:12s} {buckets[b]:>3}")
    print(f"\n  retrieved      : {len(retrieved)}   (unreachable excluded: {buckets['unreachable']})")
    print(
        f"  SUBJECT RATE   : {summary['subject_rate_of_retrieved']:.1%} .. "
        f"{summary['subject_or_unknown_rate_of_retrieved']:.1%}  of retrieved pages"
    )
    print(f"    (lower = a2web's closed list; upper = counting `unknown` declared types)")
    print(f"  distinct hosts : {len(summary['distinct_hosts_firing'])}  {summary['distinct_hosts_firing']}")
    print(f"  fields when it fires: {summary['mean_fields_when_subject']} raw, {summary['mean_capped_fields_when_subject']} after cap-20")
    print("\n  by corpus class:")
    for k, v in sorted(by_class.items()):
        print(f"    {k:14s} {dict(v)}")
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
