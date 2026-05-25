"""Spike — surface eval v2 — FINAL router-shape design pre-implementation check.

Runs the EXACT prompt design from openspec/changes/refactor-ask-to-router-shape/
on an extended 13-URL corpus. Validates open questions before /opsx:apply:

  - Does Haiku reliably pick `shape=discussion` on thread-style pages?
  - Does the SOFT cap rule recover MDN/wiki/HN-front drilldowns that the
    hard-cap spike v1 lost?
  - Does `genre` get picked sensibly (not always omitted, not over-emitted)?
  - Does omit-empty work cleanly (model emits absent keys, not `null`)?
  - Does the obvious-filler rule still hold with the larger prompt?
  - Are there memory leaks in any answer? (grep for "Denis" / "your interests"
    / personal-context phrases)

Corpus: 13 URLs = v1's 10 + 3 discussion-shape additions
  (reddit-rust-thread, lobste-thread, blog-with-comments)

If this spike surfaces issues, we tighten the proposal cheaply before impl.
If it passes clean, /opsx:apply with evidence.

Run:
    uv run python eval/spikes/surface_eval_v2.py
"""

from __future__ import annotations

import asyncio
import json
import re
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


# (slug, ask, url, expected_shape, expected_genre_or_None)
URLS: list[tuple[str, str, str, str, str | None]] = [
    ("paper-abs",
     "what does the paper claim in 2 sentences?",
     "https://arxiv.org/abs/2402.17753",
     "prose", "paper"),
    ("hn-front",
     "what are the top 3 most-discussed posts right now?",
     "https://news.ycombinator.com/",
     "records", "community"),
    ("hn-thread",
     "what is the most-upvoted criticism in this thread?",
     "https://news.ycombinator.com/item?id=39745700",
     "discussion", "community"),
    ("mdn-array",
     "how do you remove the last element of an array in javascript?",
     "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array",
     "mixed", "official"),
    ("rfc-9110-idempotent",
     "what does the spec say about idempotent methods?",
     "https://datatracker.ietf.org/doc/html/rfc9110",
     "prose", "spec"),
    ("so-yield",
     "what is the accepted answer?",
     "https://stackoverflow.com/questions/231767/what-does-the-yield-keyword-do-in-python",
     "discussion", "community"),
    ("gh-httpx-readme",
     "how do I install httpx and make a basic GET request?",
     "https://github.com/encode/httpx",
     "mixed", "official"),
    ("pydantic-releases",
     "what changed in the latest pydantic release?",
     "https://github.com/pydantic/pydantic/releases",
     "records", "official"),
    ("wiki-rust",
     "when was rust 1.0 released and who created it?",
     "https://en.wikipedia.org/wiki/Rust_(programming_language)",
     "prose", "encyclopedia"),
    ("pypi-httpx",
     "what is the latest version of httpx and its main dependencies?",
     "https://pypi.org/project/httpx/",
     "key-value", "official"),
    # Discussion-shape additions for the new `discussion` value:
    ("lobste-thread",
     "what is the dominant critique in this discussion?",
     "https://lobste.rs/s/n1gytv",
     "discussion", "community"),
    ("blog-julia-comments",
     "what does the author conclude about tailwind?",
     "https://jvns.ca/blog/2026/05/15/moving-away-from-tailwind--and-learning-to-structure-my-css-/",
     "prose", "personal"),  # note: jvns has no comments — fallback test
    ("reddit-rust-thread",
     "what is the most discussed objection in this thread?",
     "https://www.reddit.com/r/rust/comments/1cu4wuc/announcing_rust_1781/",
     "discussion", "community"),
]


# ---------------------------------------------------------------------------
# EXTRACT_ROUTER_V1 prompt — the final design from the openspec proposal
# ---------------------------------------------------------------------------

ROUTER_V1_SYSTEM = (
    "You are an extraction helper. Answer the question concisely, then emit a "
    "tight set of routing hints for the calling agent. Output strict JSON only. "
    "Quality over completeness — fewer high-signal entries beat many obvious ones."
)

ROUTER_V1_TEMPLATE = """Web page content:
{content}

Primary question: {ask}

Emit strict JSON with three REQUIRED top-level fields:

  answer            string — 2-3 sentences answering the question. If the page
                    does not contain the answer, say so plainly. If the question
                    asks for a list (top N stories, all methods, etc.), the
                    answer IS the list, as compact markdown.

  structural_form   ONE of these 9 values — what the page IS structurally:
                      article    single long-form prose body (blog post, news,
                                 essay, encyclopedia entry)
                      thread     originating post + replies (HN/Reddit/forum
                                 item, QA accepted-answer page)
                      listing    feed of items, possibly paginated (HN front,
                                 search results, store rows, release lists)
                      reference  lookup-style (API ref, spec, RFC, dictionary,
                                 encyclopedia infobox)
                      tutorial   ordered steps / walkthrough / how-to
                      changelog  versioned release entries
                      code       source file, gist, snippet, README
                      product    single offering (product, package, profile,
                                 marketing page)
                      media      PDF / video / audio as primary
                      other      fits none

  shape             ONE of these 7 values — the data shape of the answer-
                    bearing content:
                      prose        flowing paragraphs (article body, blog)
                      records      list of similar items (listing, release
                                   entries, search results)
                      key-value    entity profile (product specs, package
                                   metadata, person info)
                      code         code-dominant (source file, gist)
                      table        structured grid is the primary signal
                      discussion   comment/reply tree, usually with originating
                                   post or link above. Common high-signal shape
                                   on HN items, Reddit threads, lobste, blog
                                   comments — the agent should expect MANY
                                   useful follow-up questions about positions,
                                   dissent, consensus, top voices.
                      mixed        genuine multi-shape (prose + tables + code)

And FOUR OPTIONAL top-level fields. Omit the key entirely when the value is
empty / null / not-applicable (do NOT emit `"key": null` or `"key": []`):

  genre             ONE of these 7 values, OR OMIT entirely when none clearly
                    applies — what the page is ABOUT:
                      news          current events, journalism
                      encyclopedia  neutral background knowledge
                      spec          normative standard or formal definition
                      paper         academic publication
                      personal      blog post, opinion, individual voice
                      official      vendor / product / first-party docs
                      community     UGC, forum, comments, collaborative

  obstacle          ONE of these 4 values, OR OMIT on healthy pages — page-
                    level failure mode:
                      paywalled | blocked | empty | error

  ask_here          array of follow-up questions about THIS URL, OR OMIT when
                    none. Emit ONLY questions whose answer requires reading the
                    body — NEVER obvious-from-title/headings/byline questions.
                    Context decides count: 3 good, 5 great, more if warranted.
                    When shape=discussion the page typically supports 5+
                    useful follow-ups (positions, dissent, top voices) — lean
                    higher. Empty/obvious → OMIT the key.

  try_url           array of {{"url": "...", "reason": "..."}}, OR OMIT when
                    nothing better elsewhere. The agent will fetch the URL and
                    re-ask the SAME question. Each `reason` MUST be question-
                    conditioned (WHY this URL likely has what THIS question
                    needs, ≤120 chars). Examples:
                      Good: "PDF of same paper — section 4 has the experiment setup"
                      Good: "discussion thread for this article — top-rated critique likely here"
                      Bad:  "PDF version"
                      Bad:  "comments"
                    Context decides count: 3 good, 5 great, up to 10 fine on
                    rich pages (large docs, listings, encyclopedias); on simple
                    pages (status, short blog, clean API answer) OMIT entirely
                    when the agent has nowhere better to go.

Output strict JSON. Example shapes:

  // healthy article, complete answer, nothing more to suggest:
  {{"answer":"...","structural_form":"article","shape":"prose","genre":"personal"}}

  // rich reference, complete answer, drilldowns help:
  {{"answer":"...","structural_form":"reference","shape":"mixed","genre":"official",
   "try_url":[{{"url":"...","reason":"..."}}]}}

  // discussion page, expected many follow-ups:
  {{"answer":"...","structural_form":"thread","shape":"discussion","genre":"community",
   "ask_here":["...","...","...","...","..."]}}

  // paywalled, suggesting archive:
  {{"answer":"page is paywalled","structural_form":"article","shape":"prose",
   "genre":"news","obstacle":"paywalled",
   "try_url":[{{"url":"...","reason":"..."}}]}}
"""


# Memory-leak patterns to grep for in answer / ask_here strings.
LEAK_PATTERNS = [
    re.compile(r"\bdenis\b", re.IGNORECASE),
    re.compile(r"your (interests?|preferences?|knowledge)", re.IGNORECASE),
    re.compile(r"based on your", re.IGNORECASE),
    re.compile(r"as we discussed", re.IGNORECASE),
    re.compile(r"\biorlas\b", re.IGNORECASE),
    re.compile(r"your memory", re.IGNORECASE),
    re.compile(r"your context", re.IGNORECASE),
    re.compile(r"appeal (most )?to (your|denis)", re.IGNORECASE),
]


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


def _grep_leaks(parsed: dict) -> list[str]:
    """Return list of {field}: {snippet} hits for memory-contamination patterns."""
    leaks: list[str] = []
    answer = parsed.get("answer", "") or ""
    for pat in LEAK_PATTERNS:
        m = pat.search(answer)
        if m:
            leaks.append(f"answer: '...{answer[max(0, m.start()-20):m.end()+30]}...'")
    for i, q in enumerate(parsed.get("ask_here", []) or []):
        if not isinstance(q, str):
            continue
        for pat in LEAK_PATTERNS:
            if pat.search(q):
                leaks.append(f"ask_here[{i}]: '{q}'")
                break
    return leaks


def _check_envelope(parsed: dict) -> list[str]:
    """Verify omit-empty discipline + closed-enum compliance."""
    v: list[str] = []
    if "_parse_error" in parsed:
        return ["PARSE FAILURE"]
    # Required fields
    for f in ("answer", "structural_form", "shape"):
        if f not in parsed:
            v.append(f"missing required `{f}`")
    # Omit-empty discipline: model should NOT emit explicit null/empty for optionals
    for f in ("genre", "obstacle"):
        if f in parsed and parsed[f] is None:
            v.append(f"emitted `{f}: null` instead of omitting key")
    for f in ("ask_here", "try_url"):
        if f in parsed and parsed[f] == []:
            v.append(f"emitted `{f}: []` instead of omitting key")
    # Enum compliance
    sf_ok = {"article", "thread", "listing", "reference", "tutorial",
             "changelog", "code", "product", "media", "other"}
    sh_ok = {"prose", "records", "key-value", "code", "table", "discussion", "mixed"}
    ge_ok = {"news", "encyclopedia", "spec", "paper", "personal", "official", "community"}
    ob_ok = {"paywalled", "blocked", "empty", "error"}
    if parsed.get("structural_form") and parsed["structural_form"] not in sf_ok:
        v.append(f"unknown structural_form: `{parsed['structural_form']}`")
    if parsed.get("shape") and parsed["shape"] not in sh_ok:
        v.append(f"unknown shape: `{parsed['shape']}`")
    if parsed.get("genre") and parsed["genre"] not in ge_ok:
        v.append(f"unknown genre: `{parsed['genre']}`")
    if parsed.get("obstacle") and parsed["obstacle"] not in ob_ok:
        v.append(f"unknown obstacle: `{parsed['obstacle']}`")
    return v


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


async def main() -> None:
    from a2kit.ldd import ldd_state_for_call
    from a2kit.packages.testing.null_context import null_context
    from a2kit.testing import lazy

    settings = AppSettings()
    state, browser_pool, llm = await _build_resources(settings)
    provider = ClaudeCodeProvider()

    ambient = ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)
    ambient.__enter__()

    out_path = Path("eval/spikes/surface_eval_v2_output.md")
    summary_path = Path("eval/spikes/surface_eval_v2_summary.json")

    lines: list[str] = [
        "# Surface eval v2 — FINAL router-shape design pre-impl check\n\n",
        "Model: `claude-haiku-4-5` · max_tokens=1024 · thinking disabled\n\n",
        "Single prompt (EXTRACT_ROUTER_V1 from refactor-ask-to-router-shape openspec).\n",
        "13 URLs including 4 discussion-shape pages (hn-thread, so-yield, lobste, reddit, blog-julia).\n\n",
    ]
    summary: dict[str, Any] = {
        "per_url": [],
        "totals": {
            "cost": 0.0, "ms": 0,
            "parse_failures": 0, "envelope_violations": 0,
            "memory_leaks": 0,
            "shape_matches": 0, "shape_mismatches": 0,
            "genre_emitted": 0, "genre_omitted": 0,
            "obstacle_emitted": 0,
            "ask_here_emitted": 0, "ask_here_count_total": 0,
            "try_url_emitted": 0, "try_url_count_total": 0,
        },
    }

    try:
        for idx, (slug, ask, url, expected_shape, expected_genre) in enumerate(URLS, 1):
            print(f"\n[{idx}/{len(URLS)}] {slug}", flush=True)
            lines.append(
                f"\n---\n\n## {idx}. {slug}\n\n`{url}`\n\n"
                f"Q: **{ask}**  ·  expected_shape=`{expected_shape}`, "
                f"expected_genre=`{expected_genre}`\n\n"
            )

            per_url: dict[str, Any] = {
                "slug": slug, "url": url, "ask": ask,
                "expected_shape": expected_shape,
                "expected_genre": expected_genre,
            }

            try:
                resp = await fetch(
                    url=url, ask=ask, state=state,
                    browser_pool=lazy(browser_pool), llm_extractor=lazy(llm),
                )
            except Exception as exc:
                lines.append(f"**FETCH RAISED**: `{exc}`\n")
                per_url["fetch_status"] = f"raised: {exc!r}"
                summary["per_url"].append(per_url)
                continue

            content_md = resp.content_md or ""
            lines.append(
                f"Fetch: tier=`{resp.tier}` · status=`{resp.status or 'ok'}` · chars={len(content_md)}\n\n"
            )
            if not content_md:
                lines.append("(no content_md — skipping)\n")
                per_url["fetch_status"] = resp.status or "ok"
                summary["per_url"].append(per_url)
                continue

            content_capped = content_md[:12000]
            t0 = time.perf_counter()
            response = await provider.complete(
                system=ROUTER_V1_SYSTEM,
                user=ROUTER_V1_TEMPLATE.format(content=content_capped, ask=ask),
                model="claude-haiku-4-5", max_tokens=1024, thinking_disabled=True,
            )
            elapsed = int((time.perf_counter() - t0) * 1000)
            parsed = _parse_json(response.text)

            summary["totals"]["cost"] += response.cost_usd
            summary["totals"]["ms"] += elapsed

            envelope_v = _check_envelope(parsed)
            leaks = _grep_leaks(parsed) if "_parse_error" not in parsed else []

            if "_parse_error" in parsed:
                summary["totals"]["parse_failures"] += 1
            if envelope_v:
                summary["totals"]["envelope_violations"] += 1
            if leaks:
                summary["totals"]["memory_leaks"] += 1

            shape_got = parsed.get("shape")
            genre_got = parsed.get("genre")
            obstacle_got = parsed.get("obstacle")
            ask_here = parsed.get("ask_here", []) or []
            try_url = parsed.get("try_url", []) or []

            if shape_got == expected_shape:
                summary["totals"]["shape_matches"] += 1
            else:
                summary["totals"]["shape_mismatches"] += 1
            if genre_got is not None:
                summary["totals"]["genre_emitted"] += 1
            else:
                summary["totals"]["genre_omitted"] += 1
            if obstacle_got:
                summary["totals"]["obstacle_emitted"] += 1
            if ask_here:
                summary["totals"]["ask_here_emitted"] += 1
                summary["totals"]["ask_here_count_total"] += len(ask_here)
            if try_url:
                summary["totals"]["try_url_emitted"] += 1
                summary["totals"]["try_url_count_total"] += len(try_url)

            per_url["fetch_status"] = resp.status or "ok"
            per_url["chars"] = len(content_md)
            per_url["cost"] = response.cost_usd
            per_url["ms"] = elapsed
            per_url["structural_form"] = parsed.get("structural_form")
            per_url["shape"] = shape_got
            per_url["shape_match"] = (shape_got == expected_shape)
            per_url["genre"] = genre_got
            per_url["obstacle"] = obstacle_got
            per_url["ask_here_n"] = len(ask_here)
            per_url["try_url_n"] = len(try_url)
            per_url["envelope_violations"] = envelope_v
            per_url["memory_leaks"] = leaks

            tags = []
            if envelope_v:
                tags.append("⚠ ENVELOPE: " + ", ".join(envelope_v))
            if leaks:
                tags.append("🚨 LEAK: " + " // ".join(leaks))
            if shape_got != expected_shape:
                tags.append(f"shape miss: got `{shape_got}`, expected `{expected_shape}`")
            tag_line = " · ".join(tags)

            lines.append(
                f"### · {elapsed} ms · ${response.cost_usd:.5f}"
                + (f"\n\n{tag_line}\n" if tag_line else "\n")
                + f"\n```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```\n"
            )
            summary["per_url"].append(per_url)

    finally:
        ambient.__exit__(None, None, None)
        try:
            await state.sqlite.__aexit__(None, None, None)
        except Exception:
            pass

    # Compute v0.20-baseline comparison from v1 summary if present
    v1_path = Path("eval/spikes/surface_eval_v1_summary.json")
    v0_20_catalog_cost = None
    if v1_path.exists():
        v1 = json.loads(v1_path.read_text())
        v0_20_catalog_cost = v1.get("totals", {}).get("catalog_cost")

    t = summary["totals"]
    lines.append("\n---\n\n## Aggregate\n\n")
    lines.append(f"- total cost: **${t['cost']:.4f}** over {len(URLS)} URLs ({sum(1 for p in summary['per_url'] if 'cost' in p)} succeeded)\n")
    if v0_20_catalog_cost:
        delta_pct = (t["cost"] - v0_20_catalog_cost) / v0_20_catalog_cost * 100
        lines.append(f"- vs v1 catalog baseline (${v0_20_catalog_cost:.4f} over 10 URLs): {delta_pct:+.1f}%\n")
    lines.append(f"- parse failures: {t['parse_failures']}\n")
    lines.append(f"- envelope violations: {t['envelope_violations']}\n")
    lines.append(f"- **memory leaks: {t['memory_leaks']}**\n")
    lines.append(f"- shape: {t['shape_matches']}/{t['shape_matches']+t['shape_mismatches']} matched expected\n")
    lines.append(f"- genre: emitted {t['genre_emitted']} / omitted {t['genre_omitted']}\n")
    lines.append(f"- obstacle: emitted on {t['obstacle_emitted']} URLs\n")
    lines.append(f"- ask_here: emitted on {t['ask_here_emitted']}, avg count {t['ask_here_count_total']/max(1,t['ask_here_emitted']):.1f}\n")
    lines.append(f"- try_url: emitted on {t['try_url_emitted']}, avg count {t['try_url_count_total']/max(1,t['try_url_emitted']):.1f}\n")

    out_path.write_text("".join(lines))
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nwrote {out_path}\nwrote {summary_path}")
    print(f"\nAggregate:")
    print(f"  cost ${t['cost']:.4f} over {len(URLS)} URLs")
    print(f"  parse_failures={t['parse_failures']}, envelope_violations={t['envelope_violations']}, memory_leaks={t['memory_leaks']}")
    print(f"  shape matches: {t['shape_matches']}/{t['shape_matches']+t['shape_mismatches']}")


if __name__ == "__main__":
    asyncio.run(main())
