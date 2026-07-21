## Why

a2web is the shelf's largest consumer (12 of 17 catalog rows name it) and has
already adopted 11 packages. But it **predates the shelf**, so it hand-rolled
generic substrate before it could promote in the moment. The shelf's
`onboard-a-consumer.md` runbook exists precisely for this post-facto catch-up.

Phases B–D (the read-only substrate inventory and per-candidate verdict) are
**complete** — see `design.md` for the full verdict table over ~3,900 lines under
`src/a2web/packages/`, `_plugin.py`, and the top-level modules. This change is
Phase E (extract + tag) and Phase F (record + report).

**The prize is not that a2web shrinks.** Per the runbook: *"The success metric is
future-code-avoided (catalog coverage), NOT existing-repo shrink."* The strategic
gain here is specific:

> **The catalog's LLM story currently stops at "call the model."** `anyllm` returns
> a `Completion.text` and stops. This sweep adds *parse its JSON reliably*
> (`llm-wobble`), *don't overpay for the call* (`anyllm.cost`), *don't repeat the
> call* (`llm-cache`), and *render the prompt cacheably* (`anyllm.prompt`). Any
> next LLM-using app skips four hand-rolls — and one of them has a documented
> $20-per-run failure mode behind it (ADR-0016).

Plus two gaps the catalog has no answer for at all: **extension-point discovery**
(`plugin-surface`) and **browser rendering** (`any-browser`, the natural sibling of
the already-shelved `http-fetch`, turning the fetch story from "HTTP only" into
"HTTP or a real engine").

Every promoted piece arrives with a **portable acceptance suite already written**
(`tests/plugin_framework/`, `tests/packages/llm_extract/test_wobble.py`,
`tests/packages/test_llm_cost_guard.py`, `tests/packages/test_playwright_backend.py`,
`tests/capabilities/json_extract/`) — this is extraction, not authorship.

## What Changes

**PROMOTE (new shelf packages, born `candidate`):**

| Package | Capability |
|---|---|
| **`plugin-surface`** | Stop caring how an app discovers its own extension points — declare one `MANIFEST` per plugin file, get a ready-to-use registry, with "not configured" plugins dropped before they reach it. |
| **`llm-wobble`** | Stop caring that an LLM's JSON envelope arrives fenced, prose-wrapped, or missing fields — one funnel decodes it, applies a per-field recovery policy, logs every recovery, and returns a token no hand-rolled parse can forge. |
| **`llm-cache`** | Stop caring how to memoize an LLM completion — a TTL'd sqlite table keyed on `(content, prompt, model, template)` sharing the caller's connection, preserving token/cost/latency accounting. |
| **`any-browser`** | Stop caring which JS engine renders a page — one `render()` across the Playwright-API family and raw CDP, returning a rich `RenderedPage`, never raising for routine failure. |

**EVOLVE `anyllm`** (one tag, monotonic — adds, removes nothing):
- `anyllm.cost` — `CostPolicy` / `assert_within_budget` / `with_cost_guard`.
  Fixes an active problem: `llm_cost_guard.py:101-124` re-declares anyllm's
  `complete()` signature verbatim and `:93-99` carries a `cast` scar from
  anyllm v0.3.0's `name: str → ProviderName` narrowing. Inside the owner, those
  break at compile time instead of silently.
- `anyllm.prompt` — `PromptTemplate`. anyllm **already owns `PromptParts`**; the
  producer of that type living outside its owner is arbitrary.

**KEEP (product moat — rejecting these is correct, not a miss):**
`block_detector`, `proxy_routing`, `escalation`, `llm_extract/{extractor,judge,
prompts,router_payload,errors}`, `_manifests/**`, `cache.py`, `actions/`,
`handlers/_common.py`, `domain.py`'s fetch-routing half, `state.py`'s
`ResourceUnavailable`.

**Also closes a decided-but-unbuilt backlog item:** *"a2web adopts
`anyllm.ProviderName`"* (shelf `docs/backlog.md`). a2web's `ProviderMode` Literal
(`settings.py:30`) is a different string set from anyllm's `StrEnum` — not
cosmetic drift. The fix is to parse the config string into `ProviderName` once, at
the settings field, so everything downstream is `ProviderName`-typed for free and
an exhaustive `match` with `assert_never` catches future drift statically.

## Impact

- **Shelf** (in worktree `../shelf-a2web`, per the loop): 4 new packages, 1 evolved
  package, catalog regenerated, `use-cases/a2web--*.toml` per adopted piece,
  ledger rows for each delivery and verdict.
- **a2web**: ~1,900 lines deleted if all pieces are adopted back — a side effect,
  not the point.
- **Independent of `sunset-a2kit-dependency`.** No ordering constraint in either
  direction. Should be run as its own dedicated session per the runbook.

## Open questions

**Q1. `any-browser` timing — genuinely unresolved.** `patchright.py` and
`zendriver.py` both carry `TRANSIENT (browser-backend-bakeoff)` headers: the
engine set is still being decided and a loser is slated for deletion. Promoting
mid-bakeoff puts an unresolved experiment on the shelf. The `BrowserBackend`
Protocol + `RenderedPage` are stable enough today; the *engine drivers* arguably
should wait. Options: (a) promote both now (over-reach is cheap per doctrine, and
the drivers are where the 900 lines of hidden complexity live); (b) promote the
seam now, drivers after the bakeoff verdict.

**Q2. `subresource_blocks` on the promoted `RenderedPage`.** The field is generic
(a count of 401/403/429 subresources); its *meaning* ("walled-API fake-empty
signal") is a2web moat. This is the one place product leaked into an otherwise
domain-free boundary. Keep it in the promoted type with a neutral docstring, or
leave it a2web-side?

**Q3. `structured-data-md` — medium confidence, not proposed above.**
`domain.py:192-550` renders an extracted `json_in_html.JsonPayload` (LD-JSON /
microdata / OpenGraph) to markdown — ~350 lines of schema.org-class logic that any
`json-in-html` consumer will re-hand-roll. But: is it a composite sibling, or does
folding it into `json-in-html` risk the kitchen-sink smell? Secondary doubt:
`_rows_to_md_table` may encode a2web's own wire style rather than a neutral
rendering. Recommend a closer look before extracting.

**Q4. `proxy_routing` — KEEP on doctrine, not on analysis.** The runbook names
proxy routing as a2web's moat and the sweep honored that. But read cold,
`resolve_route` is a generic first-match glob router and `_ProxyHealth` is a
generic consecutive-failure quarantine — which **overlaps conceptually with the
`purgatory` circuit breakers a2web already runs alongside it** (`state.py:86-88`).
The real question is not promote-vs-keep, it is: **is a2web running two
independent health-degradation mechanisms?** That is a RECONCILE-pass question and
may be a genuine design smell worth its own investigation.
