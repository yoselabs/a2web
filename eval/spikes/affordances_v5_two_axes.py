"""Spike v5 — two-axis rubric: page_kind_confidence + content_value.

Background (rubric research, 2026-05-24):

v4 found that `page_kind_confidence` was conflating two orthogonal things:

  - How sure am I about the LABEL I assigned? (epistemic, about the kind)
  - How useful is what I extracted to a downstream agent? (about the content)

A 404 page is HIGH confidence (it's clearly a 404) but ZERO content value.
A status page misclassified as `product-page` is LOW confidence (two close
labels) but MEDIUM content value (some signal present).

RAG-eval best practice (Braintrust, Deepchecks, ResearchRubrics paper) splits
these into separate fields. We adopt the same shape.

Envelope discipline: when `page_kind` is an obstacle kind, the `content_value`
field would always be `none` — so we OMIT it. Matches a2web's `_prune_wire`
omit-empty pattern. Same for `follow_up_questions` (always empty on obstacle)
and `shapes` (always describes the obstacle, redundant with page_kind).

Iteration loop: 14 weak cases from v2 first; full 30 only if confidence
distribution improves and no easy-case regressions appear.

Run:
    uv run python eval/spikes/affordances_v5_two_axes.py [--full]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, cast

from purgatory import AsyncCircuitBreakerFactory

from a2web.fetcher import fetch
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider
from a2web.packages.proxy_routing import ProxyPool, ProxyEntryShape, RouteRuleShape
from a2web.server import build_browser_pool, build_llm_extractor
from a2web.settings import AppSettings
from a2web.state import SqliteResource, build_state


PRIMER_ASK = "Give a 2-3 sentence summary of what this page is."


URLS_FULL: list[tuple[str, str, str]] = [
    ("tiny-arxiv", "article-short", "https://arxiv.org/abs/2402.17753"),
    ("tiny-gh-gist", "code-snippet", "https://gist.github.com/jboner/2841832"),
    ("tiny-status-page", "status", "https://status.openai.com/"),
    ("huge-wikipedia", "encyclopedia", "https://en.wikipedia.org/wiki/Rust_(programming_language)"),
    ("huge-mdn-array", "api-reference", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array"),
    ("huge-changelog", "changelog", "https://github.com/pydantic/pydantic/releases"),
    ("listing-hn", "listing", "https://news.ycombinator.com/"),
    ("listing-lobste", "listing", "https://lobste.rs/active"),
    ("listing-gh-trending", "listing", "https://github.com/trending/python?since=daily"),
    ("listing-pypi", "package-page", "https://pypi.org/project/httpx/"),
    ("comments-hn-item", "threaded", "https://news.ycombinator.com/item?id=39745700"),
    ("comments-lobste", "threaded", "https://lobste.rs/s/n1gytv"),
    ("docs-fastapi", "tutorial", "https://fastapi.tiangolo.com/tutorial/first-steps/"),
    ("docs-postgres", "api-reference", "https://www.postgresql.org/docs/current/sql-select.html"),
    ("docs-anthropic", "api-reference", "https://docs.claude.com/en/api/messages"),
    ("ref-rfc", "spec", "https://datatracker.ietf.org/doc/html/rfc9110"),
    ("ref-mdn-fetch", "api-reference", "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API"),
    ("news-bbc", "news-article", "https://www.bbc.com/news/articles/cjwp82ye4y3o"),
    ("blog-julia-evans", "blog-post", "https://jvns.ca/blog/2026/05/15/moving-away-from-tailwind--and-learning-to-structure-my-css-/"),
    ("forum-so-question", "qa", "https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python"),
    ("code-gh-file", "source-file", "https://github.com/pydantic/pydantic/blob/main/pydantic/main.py"),
    ("code-gh-readme", "readme", "https://github.com/encode/httpx"),
    ("product-amazon", "product-page", "https://www.amazon.com/dp/B0BSHF7WHW"),
    ("media-yt-video", "video-page", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    (
        "gov-sec-filing",
        "filing",
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type=10-K&dateb=&owner=include&count=40",
    ),
    ("spa-react-dev", "spa", "https://react.dev/learn"),
    ("data-json-feed", "json-feed", "https://hnrss.org/frontpage.jsonfeed"),
    ("gated-nyt", "paywalled", "https://www.nytimes.com/2024/03/04/us/politics/biden-trump-2024.html"),
    ("paper-arxiv-pdf-stub", "pdf-stub", "https://arxiv.org/pdf/2402.17753"),
    ("docs-cf-page", "marketing", "https://www.cloudflare.com/products/registrar/"),
]

WEAK_SLUGS = {
    "tiny-arxiv",
    "tiny-gh-gist",
    "tiny-status-page",
    "huge-changelog",
    "comments-lobste",
    "docs-anthropic",
    "news-bbc",
    "blog-julia-evans",
    "code-gh-readme",
    "media-yt-video",
    "spa-react-dev",
    "gated-nyt",
    "paper-arxiv-pdf-stub",
    "docs-cf-page",
}

OBSTACLE_KINDS = {"error", "paywalled", "blocked", "empty"}


V_CTX_V3_SYSTEM = (
    "You are an extraction helper. You classify the page TYPE and emit affordances. "
    "Two orthogonal signals matter to the calling agent:\n"
    "  - page_kind_confidence — how sure you are about the LABEL\n"
    "  - content_value — how useful the extracted content is to use downstream\n"
    "These are independent. A 404 page is HIGH confidence (it is clearly a 404) "
    "but the content_value is implicitly NONE — for obstacle pages you OMIT "
    "content_value entirely (its absence carries the meaning). Be honest about "
    "uncertainty. Output strict JSON only."
)

V_CTX_V3_TEMPLATE = """Web page content (chars={n_chars}):
{content}

Primary question: {ask}

STEP 1 — Classify the page. Pick the ONE best `page_kind` from this closed set:

  Content kinds:
    listing | thread | reference | api-reference | tutorial | article-short |
    article-long | changelog | code-snippet | source-file | readme | qa | spec |
    filing | news-article | blog-post | product-page | video-page | json-feed |
    marketing | encyclopedia | package-page | pdf-stub | spa
  Obstacle kinds (page exists but has no usable body):
    paywalled    — clear paywall, partial content visible
    error        — 404, 500, "not found", broken page
    empty        — nav + footer only, no real body
    blocked      — captcha, bot wall, cloudflare interstitial
  Catch-all:
    other        — page exists but doesn't fit any label above

STEP 2 — `page_kind_confidence` (epistemic uncertainty about the LABEL).

  HARD RULE: if your chosen page_kind appears in any of these confusable
  clusters, you MUST set confidence to `low` or `medium` — never `high`.
  Claiming `high` while picking from a cluster is a contract violation:

    Cluster A (academic / short articles):
      article-short, reference, pdf-stub, article-long
    Cluster B (project landing pages):
      readme, package-page, marketing, product-page
    Cluster C (status / dashboard / monitoring):
      status, product-page
    Cluster D (versioned release lists):
      changelog, listing
    Cluster E (structured feed of items):
      listing, json-feed
    Cluster F (long-form web content):
      blog-post, news-article, article-long

  Decision rule inside a cluster:
    low    — you considered 2+ labels from the same cluster and the
             distinction is genuinely ambiguous
    medium — one label is clearly stronger but a sibling is defensible

  Use `high` ONLY when:
    - the page_kind is NOT in any cluster above, AND
    - structural signals are unambiguous (clear headings, shape, content
      flow that maps to exactly one label)

STEP 3 — `content_value` (how useful the extracted content is downstream):

  Emit this field ONLY when page_kind is a content kind.
  For obstacle kinds (error / paywalled / blocked / empty), OMIT it entirely.

  high   — substantial body content (> 2000 chars), on-topic, can ground
           multiple follow-up asks
  medium — usable body present but partial, noisy, or only partially on-topic
  low    — body very thin, mostly chrome/nav/footer, off-topic, or
           heavily truncated

STEP 4 — Affordances. For content kinds, emit shapes + follow_up_questions
tuned to the kind. For obstacle kinds, OMIT both fields entirely (their
absence is the signal — page_kind already named the obstacle).

Use closed shape vocabulary:
  list | timeline | key-value | table | code | comments | citations | comparison

Respond with strict JSON. Include only the fields that apply:

  Content page response:
  {{
    "page_kind": "<content kind>",
    "page_kind_confidence": "<low|medium|high>",
    "content_value": "<low|medium|high>",
    "reasoning": "<one short sentence justifying kind + confidence + value>",
    "answer": "<2-3 sentence answer to primary question>",
    "shapes": [{{"label": "...", "where": "...", "size": "..."}}],
    "follow_up_questions": ["<3-5 specific questions>"]
  }}

  Obstacle page response (note: no content_value, no shapes, no follow_ups):
  {{
    "page_kind": "<obstacle kind>",
    "page_kind_confidence": "<low|medium|high>",
    "reasoning": "<one short sentence>",
    "answer": "<2-3 sentence statement naming the obstacle>"
  }}
"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        body = text[3:]
        if body.startswith("json"):
            body = body[4:]
        if "```" in body:
            body = body.split("```", 1)[0]
        text = body.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc), "_raw": text[:400]}


async def _build_resources(s: AppSettings) -> tuple[Any, Any, Any]:
    sqlite = SqliteResource()
    state = build_state(
        settings=s,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        proxy_pool=ProxyPool(
            routes=cast("list[RouteRuleShape]", s.routes),
            proxies=cast("dict[str, ProxyEntryShape]", s.proxies),
        ),
        sqlite=sqlite,
    )
    browser_pool = build_browser_pool(settings=s)
    llm = build_llm_extractor(settings=s, sqlite=sqlite)
    return state, browser_pool, llm


def _check_envelope(parsed: dict) -> list[str]:
    """Return list of envelope-discipline violations (empty = compliant)."""
    violations = []
    kind = parsed.get("page_kind")
    if kind in OBSTACLE_KINDS:
        for f in ("content_value", "shapes", "follow_up_questions"):
            if f in parsed:
                violations.append(f"obstacle page leaked `{f}`")
    elif kind is not None:
        for f in ("content_value", "shapes", "follow_up_questions"):
            if f not in parsed:
                violations.append(f"content page missing `{f}`")
    return violations


async def _run(state: Any, browser_pool: Any, llm: Any, urls: list[tuple[str, str, str]], tag: str) -> None:
    from a2kit.testing import lazy

    provider = ClaudeCodeProvider()
    out_path = Path(f"eval/spikes/affordances_v5_{tag}_output.md")
    summary_path = Path(f"eval/spikes/affordances_v5_{tag}_summary.json")

    lines: list[str] = [
        f"# Affordances spike v5 — two-axis rubric ({tag})\n",
        f"Primer ask: `{PRIMER_ASK}` · Model: claude-haiku-4-5\n",
        f"Axes: page_kind + page_kind_confidence + content_value (omitted on obstacle)\n",
        f"Corpus: {len(urls)} URLs\n\n",
    ]
    summary: dict[str, Any] = {
        "per_url": [],
        "totals": {"cost": 0.0, "ms": 0, "fetch_failures": 0, "parse_failures": 0, "envelope_violations": 0},
    }

    for idx, (slug, declared, url) in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] {slug}", flush=True)
        lines.append(f"\n---\n\n## {idx}. {slug} (declared: `{declared}`)\n\n`{url}`\n\n")
        per_url: dict[str, Any] = {"slug": slug, "declared_kind": declared, "url": url}

        try:
            resp = await fetch(
                url=url,
                ask=PRIMER_ASK,
                state=state,
                browser_pool=lazy(browser_pool),
                llm_extractor=lazy(llm),
            )
        except Exception as exc:
            lines.append(f"**FETCH RAISED**: `{exc}`\n")
            summary["totals"]["fetch_failures"] += 1
            per_url["fetch_status"] = f"raised: {exc!r}"
            summary["per_url"].append(per_url)
            continue

        content_md = resp.content_md or ""
        lines.append(f"**Fetch**: tier=`{resp.tier}` · status=`{resp.status or 'ok'}` · chars={len(content_md)}\n\n")
        per_url["fetch_status"] = resp.status or "ok"
        per_url["chars"] = len(content_md)

        if not content_md:
            lines.append("(no content_md)\n")
            summary["totals"]["fetch_failures"] += 1
            summary["per_url"].append(per_url)
            continue

        content_capped = content_md[:12000]
        t0 = time.perf_counter()
        response = await provider.complete(
            system=V_CTX_V3_SYSTEM,
            user=V_CTX_V3_TEMPLATE.format(
                content=content_capped,
                ask=PRIMER_ASK,
                n_chars=len(content_md),
            ),
            model="claude-haiku-4-5",
            max_tokens=1024,
            thinking_disabled=True,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        parsed = _parse_json(response.text)
        summary["totals"]["cost"] += response.cost_usd
        summary["totals"]["ms"] += elapsed
        if "_parse_error" in parsed:
            summary["totals"]["parse_failures"] += 1

        violations = _check_envelope(parsed)
        if violations:
            summary["totals"]["envelope_violations"] += 1

        per_url["v5"] = {
            "cost": response.cost_usd,
            "ms": elapsed,
            "page_kind": parsed.get("page_kind"),
            "confidence": parsed.get("page_kind_confidence"),
            "content_value": parsed.get("content_value"),
            "reasoning": parsed.get("reasoning"),
            "shape_labels": [s.get("label") for s in parsed.get("shapes", []) if isinstance(s, dict)],
            "n_follow_ups": len(parsed.get("follow_up_questions", [])),
            "envelope_violations": violations,
        }
        summary["per_url"].append(per_url)

        lines.append(
            f"**V5** · {elapsed} ms · ${response.cost_usd:.5f} · "
            f"kind=`{parsed.get('page_kind')}` conf=`{parsed.get('page_kind_confidence')}` "
            f"value=`{parsed.get('content_value', '—')}`"
            + (f" · ENVELOPE: {violations}" if violations else "")
            + f"\n\n```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```\n"
        )

    t = summary["totals"]
    from collections import Counter

    conf_dist = Counter(u.get("v5", {}).get("confidence") for u in summary["per_url"] if "v5" in u)
    val_dist = Counter(u.get("v5", {}).get("content_value") for u in summary["per_url"] if "v5" in u)
    kind_dist = Counter(u.get("v5", {}).get("page_kind") for u in summary["per_url"] if "v5" in u)
    lines.append(
        f"\n---\n\n## Totals\n\n"
        f"- Cost: ${t['cost']:.4f} · time: {t['ms'] / 1000:.1f}s\n"
        f"- Fetch failures: {t['fetch_failures']} / {len(urls)}\n"
        f"- Parse failures: {t['parse_failures']}\n"
        f"- Envelope violations: {t['envelope_violations']}\n"
        f"- Confidence dist: {dict(conf_dist)}\n"
        f"- Content_value dist: {dict(val_dist)}\n"
        f"- Page kinds: {dict(kind_dist)}\n"
    )
    out_path.write_text("\n".join(lines))
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Cost: ${t['cost']:.4f}")
    print(f"Confidence: {dict(conf_dist)}")
    print(f"Content_value: {dict(val_dist)}")
    print(f"Envelope violations: {t['envelope_violations']}")


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context

    full = "--full" in sys.argv
    urls = URLS_FULL if full else [u for u in URLS_FULL if u[0] in WEAK_SLUGS]
    tag = "full" if full else "weak"

    s = AppSettings()
    state, browser_pool, llm = await _build_resources(s)
    with ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False):
        try:
            await _run(state, browser_pool, llm, urls, tag)
        finally:
            try:
                await state.sqlite.__aexit__(None, None, None)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
