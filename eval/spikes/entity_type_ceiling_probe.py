"""Probe — how much does `_ENTITY_TYPES`' eight-name allowlist actually cost?

`packages/structured_render.py:96` holds an eight-name schema.org allowlist:

    Product, Article, NewsArticle, LocalBusiness, Organization,
    ContactPoint, Event, Recipe

An `@type` outside it renders as **nothing** — the page's structured data is
read, matched against the list, and dropped. `I0269` calls this the ceiling it
is objecting to, and ADR-0018 proposes demoting it to a label table.

That argument has so far rested on reasoning ("a Person page falls through")
and on LLM-emitted types from `entity_schema_v2`. **This measures the real
thing**: what `@type` values do live pages actually publish, and how many of
them the allowlist discards.

No LLM. No judge. Just fetch, parse the JSON-LD a2web already parses, and count
— so the number is a fact about the web and the allowlist, not about a model.

Deliberately reuses a2web's OWN `ld_entries` extraction rather than a fresh
JSON-LD reader: a probe that parses differently from production measures its own
parser. The allowlist is imported from the module under test for the same
reason — a copied list here could drift from the real one and report a ceiling
that no longer exists (or miss one that does).

Live network, no LLM quota. Run:

    uv run python eval/spikes/entity_type_ceiling_probe.py
"""

from __future__ import annotations

import asyncio
import collections
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from json_in_html import extract_json_payloads, ld_entries

from a2web.components import build_components
from a2web.packages.structured_render import _ENTITY_TYPES
from a2web.settings import AppSettings
from a2web.tiers import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_CORPUS = Path(__file__).resolve().parents[1] / "corpus.yaml"
_OUT = Path(__file__).resolve().parent / "entity_type_ceiling_probe_summary.json"

#: Types the renderer handles OUTSIDE `_ENTITY_TYPES`, via their own branches
#: (`ItemList` rows, `BreadcrumbList` names). Counting them as "discarded" would
#: overstate the ceiling, which is the easiest way to make this probe useless as
#: evidence.
_HANDLED_ELSEWHERE = frozenset({"ItemList", "BreadcrumbList"})


def _types_of(entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return []
    t = entry.get("@type")
    if isinstance(t, list):
        return [str(x) for x in t if x]
    return [str(t)] if t else []


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    urls = yaml.safe_load(_CORPUS.read_text())["urls"]
    seen: set[str] = set()
    cases = []
    for case in urls:
        if case["url"] in seen:
            continue
        seen.add(case["url"])
        cases.append(case)
    cases = cases[:limit]

    parts = build_components(settings=AppSettings())
    rows: list[dict[str, Any]] = []
    kept: collections.Counter[str] = collections.Counter()
    dropped: collections.Counter[str] = collections.Counter()
    elsewhere: collections.Counter[str] = collections.Counter()
    try:
        for i, case in enumerate(cases, 1):
            url = case["url"]
            print(f"[{i}/{len(cases)}] {url[:72]}", flush=True)
            row: dict[str, Any] = {"slug": case.get("slug"), "url": url, "class": case.get("class")}
            try:
                # The `raw` tier, not the full orchestrator: this probe needs the
                # HTML BYTES, and `FetchResponse` only carries rendered markdown.
                # Going through a2web's own tier keeps the transport (proxy pool,
                # UA, stealth) identical to production, so a page that is walled
                # in production is walled here too rather than being silently
                # rescued by a different client.
                result = await REGISTRY["raw"].fetch(url, state=await parts.state())
                row["verdict"] = str(getattr(result.verdict, "value", result.verdict))
                html = (result.body or b"").decode("utf-8", "replace")
                types: list[str] = []
                for payload in extract_json_payloads(html):
                    if payload.source != "ld_json":
                        continue
                    for entry in ld_entries(payload.data):
                        types.extend(_types_of(entry))
                if not html:
                    row["unretrieved"] = True
                row["types"] = sorted(set(types))
                for t in set(types):
                    if t in _ENTITY_TYPES:
                        kept[t] += 1
                    elif t in _HANDLED_ELSEWHERE:
                        elsewhere[t] += 1
                    else:
                        dropped[t] += 1
                row["dropped"] = sorted({t for t in types if t not in _ENTITY_TYPES and t not in _HANDLED_ELSEWHERE})
                print(f"      types={row['types']}  DROPPED={row['dropped']}", flush=True)
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                print(f"      -> ERROR {row['error'][:90]}", flush=True)
            rows.append(row)
            _OUT.write_text(json.dumps({"partial": True, "rows": rows}, indent=2))
    finally:
        await parts.aclose()

    with_ld = [r for r in rows if r.get("types")]
    with_dropped = [r for r in rows if r.get("dropped")]
    summary = {
        "allowlist": sorted(_ENTITY_TYPES),
        "n_pages": len(rows),
        "n_with_ld_json": len(with_ld),
        "n_with_a_dropped_type": len(with_dropped),
        "kept_types": dict(kept.most_common()),
        "dropped_types": dict(dropped.most_common()),
        "handled_elsewhere": dict(elsewhere.most_common()),
        "rows": rows,
    }
    _OUT.write_text(json.dumps(summary, indent=2))

    print("\n=== summary ===")
    print(f"  pages fetched            : {len(rows)}")
    print(f"  pages publishing JSON-LD : {len(with_ld)}")
    print(f"  pages losing >=1 type    : {len(with_dropped)}  <- the ceiling's cost")
    print(f"\n  KEPT (in the allowlist)  : {dict(kept.most_common())}")
    print(f"  DROPPED (rendered as {{}}) : {dict(dropped.most_common())}")
    print(f"  handled by other branches: {dict(elsewhere.most_common())}")
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
