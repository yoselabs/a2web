## Why

One live `query` against a genuinely-dead product URL
(`https://www.bhklima.com/urun/1446_vortice-lineo-125-quiet-sessiz-kanal-tipi-fan`,
a real HTTP 404) returned a success-shaped three-key envelope:

```json
{
  "tier": "jina",
  "confidence": "high",
  "answer": "The page is a 404 error; no product details ... are provided.\n\n```next_links\n[{\"anchor\":\"Tüm Ürünler\",\"url\":\"...\",\"kind\":\"drilldown\"}, ...]\n```"
}
```

Two independent defects landed on that one response, and each breaks a
first-class product invariant that the specs ALREADY state correctly. This is
implementation drift, not a spec redesign — but in both cases the spec's chosen
*mechanism* is what failed, so the requirement text has to change with the code.

**Defect 1 — the routing envelope silently voided, fence leaked into `answer`.**
`query` sends the model two contradictory output contracts. `EXTRACT_ROUTER_V1`
says *"Output strict JSON only"* with `other_pages` as a `{handle, reason, kind}`
field; then `extractor.py:213` UNCONDITIONALLY appends the next-links suffix
telling the model to emit `[{anchor, url, reason, kind}]` *"inside a fenced block,
AFTER your answer"*. The observed fence carries the `anchor`/`url` schema, proving
the suffix was sent on a routing call. The model obeyed the instruction it read
last; `parse_with_policy` then raised, and `except ParseError: return text, None`
(`extractor.py:527`) handed back **the raw model response verbatim, fence
included**, with `routing = None`. So `obstacle`, `also_here` and `other_pages`
were not empty — they were discarded by an exception path. Compounding it, the
only fence-stripper is unreachable on the routing branch: `extractor.py:270-279`
makes it an `elif`, and hard-sets `parsed_next_links = []`.

That is an ADR-0015 violation (*never withhold the body without leaving the
index*) reached by silent degradation, and it puts un-contracted prose in the
one field every caller parses.

**Defect 2 — a real 404 laundered into `ok` with `confidence: high`.** jina DID
report the failure (`Warning: Target URL returned error 404: Not Found`). a2web
missed it because the stub decode is gated on `len(markdown) < _STUB_MAX_BODY`
(2048, `jina.py:148`) — and a2web's own `X-Return-Format: markdown` request header
(`jina.py:101`) inflates that same body past the ceiling:

| request | body bytes | under the 2048 ceiling? |
| --- | --- | --- |
| plain `curl` | 1467 | yes — would decode correctly |
| **with `X-Return-Format: markdown`** (what a2web sends) | **3030** | **no — decode skipped** |

With the decode skipped the verdict stays `ok`, so `_apply_terminal` early-returns
(`fetcher.py:1937`) and no terminal story is attached; `_confidence_for` is purely
`(verdict, len(content_md))` (`fetcher_response.py:144`) and reports `high` on
>2000 chars. There is no `not_found` value in the obstacle enum, so the LLM had no
way to downgrade it either — the deterministic backstop is the only backstop, and
it was disarmed by a request header the guard never accounted for.

That violates tier-truthfulness and ADR-0009 (*never tolerate ANY unfetched URL*);
`retrieval-completeness` already mandates `status: failed` plus a
`content_not_found` hint for a corroborated 404.

The body-length ceiling is the wrong measurement. It exists to stop a long article
that merely QUOTES the stub from being misread — a real hazard — but total body
length is not the discriminator. Position is: jina always emits `Warning:` in its
own header block, before the `Markdown Content:` separator. A quoted string is
always after it.

Both defects also instance the standing CLAUDE.md rule *never add a structural
guard without an assertion that it found something*: `grep -rn "request_routing=True"
tests/` returns **zero hits**, so no test ever exercises the flag combination
`query` uses in production, and the one fence assertion
(`test_llm_module.py:264`) runs `request_next_links` alone.

## What Changes

- Suppress the next-links fence suffix when `request_routing=True` — the router
  schema's `other_pages` already covers that need, and asking for both is what
  produced the contradiction.
- Strip any stray fenced block from `answer` on the routing branch too, defensively,
  so a model that emits one anyway cannot leak it to the wire.
- Stop returning the raw model response as `answer` on a routing `ParseError`.
  Return the sanitized answer text, and make the routing loss observable rather
  than silent.
- **BREAKING (wire, degraded path only)**: a routing parse failure now surfaces as
  a degraded/incomplete signal instead of a clean-looking success. Callers that
  treated a 3-key envelope as success will now see the failure. This is the point.
- Replace the jina stub decode's body-length ceiling with a **header-scoped** guard:
  match the stub only in jina's own header block (before the `Markdown Content:`
  separator), removing the false-negative on verbose wrappers while keeping the
  quoted-string false-positive closed.
- Add the missing coverage: a test at the `request_routing=True` +
  `request_next_links=True` combination, an assertion that `answer` never carries a
  fence on the routing path, and a jina regression pinning a >2048-byte wrapped 404
  to `not_found`.
- Add both live cases to `eval/corpus.yaml` per the never-lose-a-case rule.

## Capabilities

### New Capabilities

None. Both defects are drift against capabilities that already exist.

### Modified Capabilities

- `extraction`: the router path SHALL NOT request a next-links fence; the fence
  stripper SHALL apply on the routing branch; a routing parse failure SHALL return
  sanitized answer text (not the raw response) and SHALL be observable rather than
  silent. Amends the existing "Extractor supports an opt-in request_routing mode"
  and the parse-failure requirement at `extraction/spec.md:281`.
- `tier-pipeline`: the jina wrapper-stub guard changes from a body-length ceiling to
  a header-scoped match. Amends "A retrieved error page surfaces its upstream status"
  (`tier-pipeline/spec.md:413-437`), whose current text explicitly mandates the
  body-length guard that failed.
- `ask-response`: `answer` SHALL never carry a raw fenced block, and a lost routing
  payload SHALL NOT present as an unqualified success.

## Impact

Code:

- `src/a2web/packages/llm_extract/extractor.py` — `_next_links_suffix` call site
  (`:213`), the `if request_routing / elif request_next_links` branch (`:270-279`),
  `_split_answer_and_routing`'s `except ParseError` (`:526-529`).
- `src/a2web/tiers/jina.py` — `_STUB_MAX_BODY` (`:37`) and the decode guard (`:148`).
- `src/a2web/fetcher_response.py` — how a `None` routing payload is reflected in the
  envelope (`_project_routing` `:66-68`, `build_ask_response` `:633`).

Specs: `extraction`, `tier-pipeline`, `ask-response` deltas.

Tests: new coverage at the untested flag combination; jina verbose-wrapper regression;
`eval/corpus.yaml` entries for the dead-URL and fence cases.

Not in scope: `retrieval-completeness` needs no requirement change — its 404 story is
already correct and starts working once jina reports `not_found` truthfully. The
`confidence` heuristic and the absent `not_found` obstacle value are noted as
follow-on hardening, not fixed here.
