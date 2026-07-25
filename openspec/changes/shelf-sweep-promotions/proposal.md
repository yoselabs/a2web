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

> **ANSWERED 2026-07-22 — (a), because the premise is false. There is no open
> bakeoff.** `openspec/changes/archive/2026-06-27-browser-backend-bakeoff/`
> closed a month ago with every task checked. Its verdict was not "one engine
> wins" but **keep two**: patchright as the fast rung (`browser` tier),
> zendriver as the robust rung (`browser_robust`), escalated to only when the
> fast render comes back thin/blocked. `BACKLOG.md`: *"they're complementary,
> not strictly ranked; the Chromium drop-ins fail the Trendyol/Hepsiburada SPAs
> zendriver reads."* The engine that actually lost — `rebrowser` — was deleted
> then, and camoufox was gated. `settings.py:153-159` wires both rungs as
> standing architecture; `pyproject.toml:176` ships both in the `[browser]`
> extra. Nothing is pending.
>
> **Why it read as open: three stale docstrings.** `_manifests/.../patchright.py`
> got the closing edit ("Kept engine after the bake-off"); the other three
> browser-backend headers did not, and still described a finished experiment in
> the present tense — *"Deleted if it loses the bake-off"*, *"Removed if it
> loses"*, *"the bake-off's CDP candidate"*. The zendriver manifest even carried
> a dead behavioural claim (`Unavailable` when the **`bakeoff`** extra is
> absent) for an extra that task 6.2 deleted. Q1 was written by reading those
> three. All four now state the settled two-rung outcome.
>
> **The bake-off's finding strengthens the promotion rather than delaying it.**
> Two engines that fail on *different real sites* is exactly the evidence that
> `BrowserBackend` spans engine families — Playwright API and raw CDP — rather
> than wrapping one vendor. That is the ADOPT case for an `any-*` package, and
> it is now backed by a live comparison instead of a design intuition. Promote
> the seam **and** both drivers.
>
> **Third stale-prose finding in this sweep** (Q4's `build_breakers`
> "per-proxy/global" claim, Q3's resolved-by-docstring rendering half, now Q1).
> Prose is the one artifact here that nothing tests, and the sweep has been
> treating it as evidence. Recorded in "Method notes".

**Q2. `subresource_blocks` on the promoted `RenderedPage`.** The field is generic
(a count of 401/403/429 subresources); its *meaning* ("walled-API fake-empty
signal") is a2web moat. This is the one place product leaked into an otherwise
domain-free boundary. Keep it in the promoted type with a neutral docstring, or
leave it a2web-side?

> **ANSWERED 2026-07-25 — keep the field, neutralize the docstring; and the
> sweep surfaced a real bug behind it.** The FIELD is generic and the producer
> proves it: `_is_challenged_subresource` (`playwright.py:96`) is
> `resource_type in ("xhr","fetch") and status in {401,403,429}` — an
> HTTP-observable fact with no a2web vocabulary in it, and one only a browser
> can observe (it is the only tier that watches subresource responses during a
> render). So it belongs ON the promoted `RenderedPage`. The MEANING — count > 0
> is a wall, blocks the empty→ok promotion, catches the walled-API fake-empty —
> lives entirely a2web-side already (`actions/terminal.py::has_subresource_block_evidence`,
> `actions/empty.py`) and does not cross the boundary. Same split as Q3:
> observation is substrate, interpretation is product.
>
> The only thing that actually leaked is the **docstring**. `base.py:66-70`
> reads *"the walled-API fake-empty signal … render an authentic '0 results'
> while its data API is blocked"* — that is a2web's conclusion sitting inside
> the type to be promoted. The promoted version must describe the observation
> (subresources that returned a challenge status during render), not what a
> consumer concludes from it. Task 5.3 does this on extraction.
>
> **The bug the question uncovered: `zendriver.py` never populates
> `subresource_blocks`** — grep returns zero writes, so it is always `0` on the
> robust rung. The robust rung is the one a2web escalates *to* precisely because
> a page looks walled, and it is blind to the walled-API signal that would
> confirm it. Not a promotion blocker (`0` reads correctly as "not observed"
> through the Protocol, and the field is domain-free either way), but a real
> a2web defect. Filed in `BACKLOG.md` — it is an a2web escalation fix, not
> shelf work, so it does NOT gate the promotion.

**Q3. `structured-data-md` — medium confidence, not proposed above.**
`domain.py:192-550` renders an extracted `json_in_html.JsonPayload` (LD-JSON /
microdata / OpenGraph) to markdown — ~350 lines of schema.org-class logic that any
`json-in-html` consumer will re-hand-roll. But: is it a composite sibling, or does
folding it into `json-in-html` risk the kitchen-sink smell? Secondary doubt:
`_rows_to_md_table` may encode a2web's own wire style rather than a neutral
rendering. Recommend a closer look before extracting.

> **ANSWERED 2026-07-22 — the secondary doubt is CONFIRMED, and it splits the
> candidate in two.** Both options the question offered (composite sibling vs
> fold into `json-in-html`) assumed promoting the ~350 lines as one piece. Read
> closely, they are not one piece.
>
> **The rendering half is product, not substrate.** `json_to_markdown_rows`'s
> own docstring names its consumer: *"a synthetic markdown surface for the
> extractor LLM"* — not "markdown for a reader". Everything downstream is
> shaped by that. `_is_commerce_shaped` routes to linked-record rendering when
> half the rows carry `price`/`url`, and `_rows_to_md_records` preserves those
> URLs verbatim — which is what makes ADR-0014 closed-set handle rehydration
> possible. `_normalize_commerce_row` lifts `offers.price` + `priceCurrency`
> into one `"3690 TRY"` token because that is what a2web's extraction prompt
> reads well. `_rows_to_md_table`'s constants (sample 5 rows, cap 8 columns,
> truncate cells to 80 chars) are token-economy tuning for that same prompt.
> None of it is neutral; a different consumer would want different numbers, and
> some would want no truncation at all. → **KEEP.**
>
> **The normalization half is the real catalog gap.** `_collect_ld_entries`,
> `_find_product_or_item_list`, `_microdata_to_ld_shape` and
> `_opengraph_to_markdown` turn LD-JSON / microdata / OpenGraph into uniform
> row dicts. That is genuinely the missing half of `json-in-html`, whose
> surface today is `extract_json_payloads` / `rank_payloads` / `JsonPayload`
> and stops at "here is the raw payload" — so every consumer writes the same
> schema.org walker, exactly as the "what the shelf gains" section claims.
>
> **Recommendation: drop `structured-data-md` as proposed; open a separate,
> smaller EVOLVE for `json-in-html` covering normalization only.** It needs its
> own boundary design first — `list[dict]` is too vague a return type to
> promote — so it is not a Phase E item. Sweep task 6.x closed on that basis;
> the verdict-table row #7 becomes **KEEP (rendering) + EVOLVE-candidate
> (normalization, deferred pending boundary design)**.

**Q4. `proxy_routing` — KEEP on doctrine, not on analysis.** The runbook names
proxy routing as a2web's moat and the sweep honored that. But read cold,
`resolve_route` is a generic first-match glob router and `_ProxyHealth` is a
generic consecutive-failure quarantine — which **overlaps conceptually with the
`purgatory` circuit breakers a2web already runs alongside it** (`state.py:86-88`).
The real question is not promote-vs-keep, it is: **is a2web running two
independent health-degradation mechanisms?** That is a RECONCILE-pass question and
may be a genuine design smell worth its own investigation.

> **ANSWERED 2026-07-22 — no, and the doubt traces to a docstring.** Every
> `get_breaker` key in the tree was enumerated: exactly two, `host`
> (`tiers/raw.py:92`) and `nitter:{instance}` (`handlers/twitter.py:95`).
> `ProxyPool._ProxyHealth` is keyed on proxy id, one call site
> (`fetcher.py:1140`). **The two mechanisms are disjoint, not redundant** —
> breakers degrade a *destination host*, the pool quarantines an *egress
> proxy*, and a host that fails through a healthy proxy is a different failure
> from a proxy that fails across many hosts.
>
> What was real: `build_breakers`'s docstring advertised "per-host /
> **per-proxy** / **global**" breakers, and neither of the last two has ever
> had a call site. The per-proxy claim is precisely the one that would have
> overlapped the pool — so the design smell was in the prose, not the design.
> Docstring corrected; no code change, no RECONCILE pass needed.
>
> Q4's KEEP verdict stands, and now rests on analysis rather than doctrine.
