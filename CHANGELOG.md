# Changelog

All notable changes to **a2web** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> First tagged release; entries summarize the full PR1–PR10 build.

## [Unreleased]

## [0.45.0] — 2026-07-16

> The honest terminal-story arc: a fetch that does not fully retrieve a URL now
> tells the truth about WHY — dead vs walled vs thin vs empty — with confidence
> encoded in hint severity, and a genuinely-empty search is a first-class answer.
> Bundles three changes (`fetch-failure-semantics`, `thin-not-wall`,
> `empty-vs-wall-discrimination`).

### Added

- **`classify_terminal(observations, resolved_verdict)`** — a single pure, total
  terminal-story classifier over the decision log, replacing the inverse
  `_is_genuine_gone` / `_prescribe_browser_on_wall` predicate pair. Closed
  `TerminalOutcome` enum: `wall`, `gone_confirmed`, `gone_unverified`,
  `thin_unverified`, `empty_unverified`, `operator_error`, `unreachable`. Reads
  the OBSERVATIONS (whole-log scan), so corroborating evidence survives a mis-won
  resolved verdict.
- **Browser subresource-block evidence** — the browser backend counts page
  XHR/fetch responses challenged (401/403/429) during render
  (`RenderedPage.subresource_blocks` → `TierResult` → `Observation`). Classifies
  the walled-API fake-empty (a benign "0 results" shell whose data API was 403'd)
  as a `wall` — the case no body-text reader can catch.
- **`content_thin` / `content_empty` operator hints + `thin_content` envelope
  field** — a retrieved thin body rides the wire (wire-only, never cached) so the
  blind caller can resolve empty-vs-wall itself (ADR-0015).
- **Empty-result gate marker + bespoke-wall fingerprints** — a conservative
  `_EMPTY_RESULT_PATTERNS` annotation (`subsystem="empty_result"`, never an
  authority) and PerimeterX / Incapsula additions to `_BLOCK_PATTERNS`.

### Changed

- **A genuinely-empty search is promoted to `ok` "no results"** (⚠ BREAKING wire
  change: a class of URL that returned `status: failed` now returns `status: ok`).
  Promotion is guarded by the pure `is_confirmed_empty` conjunction — an
  independent browser render also read empty + an HTTP tier returned a body + no
  4xx/challenge/subresource-block/hard-wall evidence anywhere + a search-shaped
  URL. The synthetic answer asserts only the absence (never fabricated items),
  `confidence: low`, body attached, and is never cached.
- **Terminal confidence is corroboration-keyed, encoded in hint severity**
  (`info` = verified dead/empty, `warning` = unverified/ambiguous residual,
  `critical` = a wall). A `404` and a thin `200` are NEVER `critical`. A thin 200
  with no wall evidence is `thin_unverified` (agnostic — does not assert "empty").

### Fixed

- **Tier truthfulness** — a reader-wrapper tier (jina) that masks an upstream
  error surfaces the real status itself; the gate no longer launders a wrapped
  404 into `ok`, and the `try_user_browser` anti-bot klaxon no longer fires on a
  dead URL or an empty search result.

## [0.44.1] — 2026-07-11

> Stop the site footer from leaking onto the `query` wire as null-url options.

### Fixed

- **`options` is now gated on `structural_form == "listing"`** (mirroring the
  existing `refinement_axes` gate). The DOM record-miner is a pure structural
  heuristic that fires on **any** repeated DOM — including a product/article
  page's site-wide footer megamenu — so on a narrow price/stock ask against a
  `product` page it was mining ~10 footer categories ("Kurumsal", "Bizi Takip
  Edin", …) and leaking them onto the wire as `options` with `url: null`. The
  shelf is now trusted only when the LLM agrees the page is a listing;
  `_prune_wire` drops the empty list otherwise. Surfaced by a live hepsiburada
  product query. Regression coverage:
  `test_product_page_footer_records_do_not_leak_as_options` (identical body, two
  classifications) + corpus `hepsiburada-product-no-footer-options`.

## [0.44.0] — 2026-07-11

> Make the withheld-body index fire on rich pages under a narrow ask.

### Changed

- **`EXTRACT_ROUTER_V1` → version 7**: strengthened the `also_here` clause so
  **"covered"** means *relayed everything the page holds on the topic* — NOT
  merely *answered the asked question*. A narrow factual ask (one price, one
  date, one status) on a `product` / `article` / `reference` / `thread` almost
  never covers the page, so the model indexes the unsurfaced sections instead of
  emitting an empty `also_here`. The `listing` carve-out (defer to `options` /
  `refinement_axes`) and the genuinely-thin-page escape are unchanged. Validated
  live on a rich Wikipedia article (narrow ask → 7 query-grammar index entries
  where it was previously empty). Surfaced by a Koçtaş probe that turned out to
  be a separate SPA under-fetch (`eval/findings_2026-07-11-also-here-underfires.md`).

## [0.43.0] — 2026-07-11

> Cache economy: relocate the router-shape schema into the cacheable bucket.

### Changed

- **`EXTRACT_ROUTER_V1` → version 6**: the ~5.8k-char static router-shape schema
  and its 4 worked examples move OUT of `tail_template` (resent on every `query`
  call) INTO the cacheable `system` bucket (`_ROUTER_SCHEMA_DOC`). `tail_template` is
  now only the per-call `"\nQuestion: {ask}\n"`. Pure relocation — zero wording
  change; the rendered aggregate prompt is byte-equivalent, only the
  `system`/`tail` split moved. Because `system` is emitted verbatim (never
  `.format()`d), the schema is single-braced there and `{{n}}` handle markers
  stay double-braced (the inverse of the old `{{{{n}}}}` tail-escaping).
  `cache_prefix_template` is untouched — the v0.19 cache-prefix invariant
  (byte-identity with `EXTRACT_CACHEABLE_V1`) holds. Saves the schema block on
  every repeat `query` within the provider's cache window.

## [0.42.0] — 2026-07-11

> **BREAKING (MCP + parsers).** The `ask` response contract v2 lands ADR-0015
> (the withheld-body index): when `query` withholds the page body for token
> economy, it MUST leave a faithful cheap index of what it withheld, so the
> caller — itself an agent that never sees the body — is never blind to
> recoverable on-page content. Applied after `unify-escalation-executor`.

### Changed — tool + envelope rename (BREAKING)

- **Tool `ask` → `query`**, parameter `question` → `query`
  (`canonical_name_override="query"`; CLI `a2web web query --url=... --query=...`).
  The `query` param teaches a terse **query grammar** (deletion rule: drop the
  verb frame + known page entity; keep the target noun + one operator —
  `,` list · `vs` contrast · `/` alternatives; CAPS the decider; `?` only to
  DECIDE). Installed MCP clients + `~/.claude.json` must update the tool name.
- **`ask_here` → `also_here`** on `AskResponse` — the same-page index, now
  emitted as query-grammar strings (not full questions). On a `listing` it
  defers to `options` + `refinement_axes` and never restates a heading / option
  / axis (ADR-0015 orthogonality).
- **`next_links` + `try_url` → `other_pages`** on `AskResponse` — one
  kind-tagged list (`structural` continuation | `drilldown` question-conditioned),
  rendered as a single TSV block (`url` / `reason` / `kind`). `NextUrl` →
  `OtherPage`; the package boundary `NextUrlBoundary` → `OtherPageBoundary`
  (with a `kind` field). ADR-0014 grounding is preserved in full (`{{n}}`
  closed-set rehydration, `off_domain` flag, question-conditioned drilldown
  reasons). `fetch_raw`'s own `FetchResponse.next_links` is unchanged — the
  fold is scoped to the `query` envelope.
- **`EXTRACT_ROUTER_V1` bumped to version 5**: emits `also_here` in query
  grammar + a unified `other_pages` shape (per-item `kind`), preserving the
  "LINKS · HARD RULE" clause and `{{{{n}}}}` marker discipline.

### Added

- **ADR-0015** (the withheld-body index) — product tenet, sibling to
  ADR-0009 / ADR-0012 / ADR-0014; mirrored as a "Never" line in `CLAUDE.md`.

## [0.41.0] — 2026-07-08

> Externalize substrate to **the shelf**. Ten in-tree `packages/` modules that
> were generic, ownable micro-software — not a2web's fetching moat — were
> promoted to `github.com/yoselabs/shelf`, catalogued as born candidates, and
> adopted back by git tag. a2web sheds **~2.1k lines of production source**
> (~3.7k with tests) and now leans on contract-guaranteed substrate that a2kay
> can share, in exchange for ten git-tag dep pins plus thin domain seams. The
> code didn't vanish — it moved once to the shelf instead of being copied per
> consumer. Two round-trips caught real bugs (a cache-schema migration crash, a
> hard dependency conflict) before they shipped.

### Changed — adopt the shelf; delete the in-tree copies

- **http-fetch** (`http-fetch-v0.1.0`): the shared HTTP GET primitive (browser
  TLS impersonation, conditional GET, injected proxy + breaker, closed-verdict
  mapping). Was `packages/http_fetch`.
- **sqlite-resource** + **http-cache** (`…-v0.1.0`): the lazy sqlite connection
  lifecycle and the conditional-GET cache mechanics. a2web composes them at a new
  `src/a2web/cache.py` seam (default-path policy + schema + the `(url,
  profile_hash)` accessor). Was `packages/http_cache.py`. **Migration fix:** the
  promoted schema renamed a2web's `profile_hash` column to the generic `variant`;
  the seam drops a legacy-shaped `cache` table so existing installs (and the
  global `~/.a2web/cache.sqlite`) **rebuild instead of crashing** with `no such
  column: variant` — the never-crash invariant held.
- **json-in-html** (`json-in-html-v0.1.0`): mine embedded structured data
  (LD-JSON / microdata / OpenGraph / `window.__X__` / raw JSON). Was
  `packages/json_in_script`.
- **html-fragment** (`html-fragment-v0.1.0`): `to_markdown`/`to_text` over a
  server-supplied HTML fragment. Was `packages/html_fragment`.
- **record-mine** (`record-mine-v0.1.0`): locate + depth-render the dominant
  repeated-record region on listing/thread pages. Was `packages/record_extract`.
- **browser-cookies** (`browser-cookies-v0.1.0`): read the local browser cookie
  store; `browser-cookie3` stays a lazily-imported optional engine (a2web keeps
  it in its own `[cookies]` extra). Was `packages/cookie_store`.
- **content-extract** (`content-extract-v0.1.1`): page → structured content. Its
  body markdown now **composes convert-md's `convert_html`** instead of a
  hand-rolled trafilatura call (behavior-equivalent). Was
  `packages/content_extract`.
- **timefmt** (`timefmt-v0.1.0`): the `fmt_dur` adaptive duration formatter. Was
  `utils/time.py`.
- **settings-base** (`settings-base-v0.1.0`): the generic env/YAML machinery
  (`${VAR}` resolution, secret-stripping YAML source, config-path resolution).
  a2web keeps its `AppSettings` schema, its `_SECRET_FIELDS` set, and its path
  defaults and composes the primitive.
- **convert-md** grown to `v0.3.0`: gained a url-aware in-memory `convert_html`
  string door (`v0.2.0`), then split its heavy document engines
  (docling/pandoc/office) into a `[documents]` extra so an HTML-only consumer no
  longer drags them. a2web adopts the **light base** (trafilatura + html2text) —
  which also sidesteps a hard lock conflict (docling's `typer<0.13` vs a2kit's
  Typer CLI). a2kay stays correct on `convert-md-v0.1.0`; it re-pins
  `convert-md[documents]` when it adopts.

### Changed — adopt anyllm; delete the in-tree LLM providers

- **anyllm** (`anyllm[anthropic,openai,claude-code-sdk]>=0.2,<1`): the LLM
  provider contract (Protocol + Completion + PromptParts) moves to the shelf;
  a2web deletes `packages/llm_extract/providers/` and composes anyllm's provider
  surface via the `_manifests` seam.

> Reddit reliability + a browser-lifecycle leak found while fixing it. The
> keyless `.rss` channel is the mission-critical Reddit path, and it was walling
> on a *transient* per-IP rate-limit. Fixes: ride out the transient throttle at
> the handler; restore the missing browser rung so a walled render-request
> escalates paid-scraper → real-browser → hint; and — surfaced by the browser
> rung firing more often — bound the browser backend so a stuck launch can't hang
> the tool call and an idle browser can't leak for hours. The 2026-07-07 bench
> caught the Reddit wall (`reddit-listing` → `tier=none
> verdict=block_page_detected`); the leak was caught live (orphaned chromium alive
> 3-8h from the MCP server, plus a 20-min launch hang).

### Fixed — bound the browser backend: launch timeout + idle reaper (`browser-lifecycle-no-hang-no-leak`)

- `packages/browser_backends/playwright.py`: three unbounded awaits are now
  bounded. **Launch** (`_ensure`) is wrapped in `browser_launch_budget_s` (45s
  default) — a wedged engine spawn returns `unavailable` and unblocks the caller
  instead of hanging the tool call indefinitely; the half-open launch is torn
  down so it can't leak. **`page.content()`** is bounded by the remaining page
  budget (a page that never settles times out, not hangs). An **idle reaper**
  background task closes the launched browser *process* after
  `browser_idle_timeout_s` idle (was: only per-host contexts got trimmed, lazily
  on the next acquire — the browser process lived until the whole server exited,
  so a long-lived/leaked MCP server orphaned hours-old chromium). The reaper
  sleeps the engine re-openably; the next render transparently re-launches.
- New settings: `browser_launch_budget_s` (45), `browser_reaper_interval_s` (30).
- Root cause of the observed 20-min hang: no launch timeout, aggravated by
  resource contention from already-leaked browsers. Both are now bounded.

### Fixed — restore the browser rung on a walled render-request (`render-escalation-tries-browser`)

- `fetcher.py`: when a handler asks for a direct site render (`escalate_to_render`
  — Reddit search/listing throttle, HN Algolia failure) and no paid tier is
  keyed, the orchestrator now dispatches the **own-browser** rung before emitting
  the never-silently-miss hint. Previously it tried only the paid tier, then
  `return`ed straight to the `try_user_browser` hint — the intended
  paid → browser → hint ladder was missing its middle rung, so an un-keyed
  deployment conceded Reddit throttling with `tier=none`. A real (anti-detect)
  browser passes soft per-IP walls the HTTP client cannot; a missing backend is a
  cheap unavailable no-op that still falls through to the loud hint.

### Fixed — ride out Reddit's transient RSS rate-limit (`reddit-rss-ratelimit-reset`)

- `handlers/reddit.py::_fetch_rss` now honors Reddit's `x-ratelimit-reset`
  header on a `429`: it waits the exact reset window (plus a 1s margin, capped at
  `_RSS_RATELIMIT_MAX_WAIT_S = 40s`) and retries once, landing the retry in a
  fresh budget. A reset past the ceiling is **not** ridden out — the handler
  declines to block the tool call for a minute and fails loud (search/listing
  escalate to a render — now including the browser rung above; thread/permalink
  surface the wall with the eager `try_user_browser` hint). The old blind
  `_RSS_BACKOFF_S = (0.5, 1.5)` schedule remains as the fallback only when no
  reset header is present.
- Root cause was the too-short backoff, **not** a permanent block: a cooled-down
  IP serves the feed `200`. Known residual gap (follow-up, not in this change):
  the Reddit handler fetches **direct, unproxied** (`proxy: "direct"` in the
  decision log), so a genuinely IP-blocked address can't be dodged by waiting —
  routing the RSS fetch through the proxy pool (as every other tier does) is the
  robust long-term answer, but is inert until proxies are configured.

## [0.39.0] — 2026-07-08

> Harness-only: make a bench run legible and cheap. Every run now writes a
> machine-readable `results.json` with the real cost/token totals the SDK already
> reports, and `--only <class>` runs a crucial subset instead of the full 22×3
> matrix. Plus a "which is best?" corpus case so a run actually exercises the
> answer-neutrality change (ADR-0012).

### Added — structured eval results + crucial subset (`eval-results-json-and-subset`)

- **`results.json` per run** — `{summary, rows}`: one object per (corpus × system)
  cell plus a rollup of `total_cost_usd` and prompt/completion tokens, overall and
  per-system. Values come straight from the provider (the claude-code SDK's
  `ResultMessage` on the subscription path), so a run's spend is legible without
  parsing markdown. `results.tsv` / `manifest.json` / `cost.md` unchanged.
- **`--only <class>` subset filter** — run only cases of a class (e.g.
  `--only listing`) to save quota; an unknown class fails loudly ("0 cases match…")
  and exits non-zero, so an empty run is never mistaken for a pass.
- **Selection-question corpus case** (`gh-trending-best`) — a "which is best?" task
  over a listing whose criteria reward presenting options + criteria and forbid an
  unqualified single "best", so the bench exercises answer neutrality.
- Harness-only; no product-wire change, `make check` green with stubs (no live LLM
  calls to build or test).

## [0.38.0] — 2026-07-07

> `ask` stopped **manufacturing a verdict it can't own**. Asked "which is best?"
> it used to crown a winner by review count — a criterion a2web invented — while
> its own hint said the sample was unrepresentative. "Best" is criteria-less to a
> fetcher; criteria belong to the caller. a2web now **presents & relays; it never
> selects.** New product tenet: ADR-0012.

### Added — answer neutrality for selection questions (`answer-neutrality-for-selection`)

- **Neutral answer on selection questions.** On a which/best/compare question over
  a set, `ask` no longer asserts its own unqualified "best". It presents the option
  space, offers only **criterion-disclosed leads** ("by rating, X leads; by price,
  Y"), and **relays any source-stated preference attributed to the page** ("the site
  marks WhatsApp as preferred") — never as a2web's own verdict. Single-fact asks
  (a phone number, a date) are unchanged and stay lean.
- **Neutral is not lazy.** The answer stays exhaustive — declining to crown is not
  license to under-deliver. Guarded by the four pillars: Exhaustive · Faithful ·
  Neutral · One-shot (never force a same-page re-fetch for data already in hand; the
  scarce cost is the proxy fetch, not tokens).
- **Criteria decoupled from completeness.** `refinement_axes` (the judgable
  dimensions of the option set — including ones read from the item *names*: power,
  class, connector type) now surface on **any** listing selection question, not only
  truncated ones. Criteria and partialness are orthogonal.
- **Product tenet recorded** as ADR-0012 + a CLAUDE.md "Never" line (not
  CONSTITUTION.md — per ADR-0009's placement precedent; a product invariant, not
  substrate governance).
- No new wire fields, no tool-signature change — a behavioral change validated by
  `make bench` (the neutrality change is measured, not assumed).

## [0.37.0] — 2026-07-07

> "Best" over a listing was a *destructive* answer: `ask` crowned a
> popularity-ranked winner and **deleted every other option** off the wire —
> so the premium/niche tool (fewer reviews, lower crowd rating *by nature*) was
> exactly what got thrown away. Ranking is fair; skipping the field is not.
> `ask` now keeps the ranked verdict **and** the shelf it came from.

### Added — ask retains the listing option set (`ask-retains-listing-options`)

- **`ask` carries a neutral `options` list on a listing.** When the record
  detector parses a listing, the `ask` envelope now includes one entry per
  fetched record (`title`, `url`, `detail` carrying price/rating as extracted),
  in **page order** — a2web does not re-rank. The ranked pick stays in `answer`;
  the shelf stays visible, so a lower-ranked premium option is no longer deleted.
- **The structured `RecordSet` is retained** on `FetchContext` instead of being
  discarded after markdown rendering, and projected into `options` at the ask
  seam. `detail` strips the duplicated title prefix and is whitespace-collapsed +
  length-capped (no semantic edit); the set is capped at 50.
- **Gated + honest:** `options` appears only on a listing, is absent on
  articles/single entities, rides the `_prune_wire` omit-empty path, and never
  appears on the `fetch_raw` wire **or its schema** (a `PrivateAttr` carrier —
  `fetch_raw` already returns the record block in `content_md`). It carries the
  fetched sample only and makes no completeness claim (`listing_partial` still
  owns that).
- **Explicit non-goal:** retrieval diversity — fetching the premium tail excluded
  by a cheapest-first sort — is a stratified/preference-driven fetch and stays
  with the shopping caller, not a2web.

## [0.36.0] — 2026-07-07

> A truncated listing was often not just partial but **biased** — a
> price-ascending search returned the cheapest N of 1123, and any "best
> product" judgment over that batch was systematically wrong. `ask` now reasons
> over the content in hand (never a per-site parser) to hand the agent generic
> levers to escape the truncation. Motivating case: a Hepsiburada crimping-tool
> search sorted `siralama=artanFiyat` returned 36 of 1123 with no way to narrow.

### Added — Content-aware refinement guidance (`content-aware-refinement-guidance`)

- **Dimensional refinement axes on a partial listing.** On the `ask` path the
  extractor proposes *axes to re-query on* (add a price floor, sort by rating,
  narrow by brand) — never specific values drawn from the biased sample, so a
  truncated read can't launder into a biased recommendation. Rides `AskResponse`
  as a conditional `refinement_axes` field, omitted from the wire unless the
  listing is partial (gated on `items_loaded`).
- **LLM-side partialness detection.** The extractor reports `item_total_seen`
  (the total it *read* off the page, in any language), used as an oracle
  fallback when the regex noun list misses the page's language (RU `товаров`,
  JP `件`). A strict superset of the regex oracle — only ever adds a partial
  signal, never overrides a regex verdict. Closes the region-coverage gap for a
  distributed tool.
- **Content-type guidance.** A per-**kind** (never per-site) "what matters"
  line surfaces as an info `content_guidance` operator hint, keyed off the
  closed `structural_form` enum (`listing` → completeness + selection bias;
  `thread` → consensus vs dissent; `product` → price/specs/availability).
- **Context bundle.** `parse_query_params` surfaces a URL's query string as
  opaque, uninterpreted `key=value` pairs (a2web never decodes `artanFiyat` —
  that would be per-site scar tissue); the reasoning model decodes meaning.
- **Non-goal, explicit:** no deterministic per-site pagination (`page` /
  `offset` / cursor) — paging contracts are per-site chaos.
- Additive wire fields only (no tool-signature change); the static MCP tool
  description is unchanged. New architecture invariant:
  `KIND_GUIDANCE` carries no site/host string.

## [0.35.0] — 2026-07-07

> Thin pages whose answer lives only in structured data (company contact
> pages, org/event pages) now **answer** instead of failing. A `LocalBusiness`
> JSON-LD carrying a phone + email is a complete answer, not a truncated shell
> — the length floor no longer deletes it. Motivating case:
> `veito.com/iletisim-EN.html` moved from `failed`/`null` to the phone + email
> answered.

### Added — Answer thin structured-data pages (`structured-data-answers`)

- **Quality-gate small-but-complete exemption.** A bare `length_floor`
  promotes to `ok` when the content menu carries an answer-bearing structured
  candidate — mirroring the existing `is_json` exemption. Scoped to the bare
  `length_floor` (`subsystem is None`), so `js_required` / `thin_browser` SPA
  shells keep escalating to the browser tier; no wall is masked.
- **Contact / org / event schemas are first-class.** `LocalBusiness`,
  `Organization`, `ContactPoint`, `Event`, `Recipe` join `_PREFERRED_LD_TYPES`;
  new `is_answer_bearing(payload)` predicate marks strong structured payloads.
  The single-entity JSON-LD renderer dispatch is widened to these types (it
  previously returned an empty string for `LocalBusiness`).
- **`ContentCandidate.answer_bearing`.** Set by the `json_synth` rung; drives
  the gate exemption and the display pick.
- **Display pick prefers structured over sub-floor prose.** When the prose pick
  is below the length floor and an answer-bearing structured candidate exists,
  `content_md` surfaces the structured answer — so `fetch_raw` (no LLM) carries
  it too.

### Fixed — Structured-grounded answers not flagged incomplete (`structured-grounded-completeness`)

- **No self-contradicting envelope.** A thin structured page promoted to `ok`
  answered correctly but the extractor still self-reported `obstacle: empty`,
  driving `retrieval_incomplete: true` + a critical "do not answer as if it
  does" hint. Now an `empty` obstacle on a `structured_grounded` page with a
  non-empty answer does not flag incompleteness. `confidence` stays `low` (the
  honest hedge); `blocked` / non-grounded pages / empty answers are unaffected.
- **ADR-0009 gap closed.** The `extraction_empty` guard's `content_md > 500`
  threshold assumed thin pages already failed at the length floor; the promotion
  broke that. Extended with `or structured_grounded` so a promoted thin page
  with an empty extraction hard-fails instead of returning a silent `ok` empty
  answer.

## [0.34.0] — 2026-07-06

> Listing completion now prefers the **free own-browser** scroll before paid
> egress (spec: own-browser preferred). Closes the last listing-completeness
> backlog item — a partial listing is completed for free where a browser is
> available, and only falls to paid Zyte when it is not.

### Added — Free own-browser scroll-to-stable (`listing-completeness` Slice 2b)

- **`BrowserBackend.render(scroll_to_stable=…)`.** A scroll-to-completion loop
  (scroll → settle → re-snapshot, keep the largest capture, terminate when
  growth stalls or an 8-pass safety cap is hit) — distinct from the single
  thin-triggered `_scroll_and_retry`. Implemented in the Playwright engine
  (Camoufox / Patchright) and the zendriver CDP engine.
- **`_phase_listing_render` prefers the free browser.** When `browser_enabled`,
  a free browser render scrolls the listing to stable first; the paid Zyte scroll
  fires only if that changed nothing and the single paid-dispatch budget remains.
  Both paths re-count records via the shared extraction escalation and re-assess:
  complete → the `listing_partial` signal clears; still short → it stands loud
  with the updated count.
- Stub-tested in `make check`: the scroll-to-stable loop (termination, pass cap,
  exception safety), the tier→backend passthrough, and the free-first
  orchestration. The engine loop's real multi-item loading is live-verify only
  (bench / manual) — the documented Slice 2b caveat.

## [0.33.0] — 2026-07-06

> Closes the listing-completeness coverage gap: a partial listing with **no
> printed count** was silent. "Partial listings signal" was only true for pages
> advertising a numeric total — a pure infinite-scroll listing (the Hepsiburada
> case minus the visible number) passed as complete.

### Added — Structural "more exists" fallback (`listing-completeness` follow-up)

- **`listing_has_more(html)` structural detector.** When a confirmed listing (a
  `RecordSet`) carries no numeric oracle, strong pagination markers (`rel=next`,
  load-more / next-page controls, Turkish `daha fazla` / `sonraki sayfa`) are
  evidence that items exist beyond the rendered batch. Consulted ONLY on a
  record-bearing page with no numeric oracle — the record-set gate keeps a stray
  "next article" link on an ordinary page from firing it.
- **New `listing_more` operator hint.** On a structural hit, `items_loaded` is
  set (the parsed count) while `items_total` stays absent (honestly unknown), and
  a distinct `listing_more` info hint surfaces the "more exists, total unknown"
  sample signal — never a wall, never `retrieval_incomplete`.
- **Numeric oracle keeps precedence.** A count that meets the oracle within
  tolerance stays silent even with a co-present `rel=next` (a leftover control on
  a complete last page is not a truncation).
- **Signal-only, no scroll.** An unknown total can't bound a render, so the
  structural case raises the floor loudly and leaves completion to the caller
  (the bounded paid scroll stays numeric-only).
- Regression pinned under `tests/capabilities/listing_completeness/`: oracle
  unit tests + `fetch_raw` / `ask` surfacing + numeric-precedence + silent-when-complete.

## [0.32.2] — 2026-07-06

> The v0.32.1 marker guard wasn't enough — SSR framework sites (Next/Nuxt) carry
> SPA markers yet already contain their content. Adds a content-length ceiling as
> the real distinguisher, so content-rich pages never render on `obstacle: empty`.

### Fixed — Obstacle-render SSR content ceiling (`obstacle-render-ssr-ceiling`)

- **Content-length ceiling is the load-bearing guard.** Live testing found that
  the v0.32.1 marker check still rendered rfc-editor.org (a Nuxt SSR app): SSR
  sites carry `id="__nuxt"` / `__NUXT_DATA__` markers but already contain their
  full content, and markers can't tell an SSR page from a CSR shell. The
  obstacle-driven render now also requires the already-extracted `content_md` to
  be THIN (`< 2000` chars) — substantial content means the page is complete and
  the answer's absence is real, so a render can't help. Only a thin result (in
  the `(length_floor, 2000)` window) is plausibly an unrendered shell.
- Widened the SPA mount markers to include Nuxt (`id="__nuxt"`, `__NUXT_DATA__`,
  `__NEXT_DATA__`); the ceiling, not the markers, now carries the SSR exclusion.
- Live-verified: rfc-editor.org (Nuxt) + a Wikipedia off-topic ask no longer
  render — both flag `retrieval_incomplete` (loud miss) with zero paid egress.
  Behavior-narrowing only; the never-silently-miss floor is unchanged.

## [0.32.1] — 2026-07-06

> Follow-up to v0.32.0, from live testing. Guards the obstacle-driven render
> against a false-positive cost: an unanswerable question on a complete static
> page no longer burns a paid render.

### Fixed — Obstacle-render false-positive guard (`obstacle-render-false-positive-guard`)

- **Only render when a render could actually add content.** Live testing found
  that `obstacle: empty` conflates "the page is a shell / didn't load" (a render
  helps) with "the page loaded fully but doesn't contain the answer" (a render is
  waste — e.g. asking RFC 2616 for a cookie recipe rendered pointlessly). The
  obstacle-driven render now additionally requires: the content did NOT come from
  a JS-executing tier (`jina`/`browser`/`browser_robust` — a re-render is
  redundant), AND the raw body shows unrendered-SPA markers (a root mount +
  `<script>`, via the new length-independent `block_detector.looks_like_unrendered_spa`).
  A complete static page with no such markers no longer triggers paid egress on
  `obstacle: empty`.
- Behavior-narrowing only: strictly fewer renders. The never-silently-miss floor
  is unchanged — a surviving obstacle still flags `retrieval_incomplete`. No
  wire-shape change.

## [0.32.0] — 2026-07-06

> The extractor's own "the answer isn't here" signal now drives a re-fetch. When
> an `ask` reports `obstacle ∈ {empty, blocked}` over content that passed the
> gate (a fat SPA shell), the orchestrator renders the page and re-extracts
> before declaring the retrieval incomplete — instead of just downgrading
> confidence. Closes the confabulation loophole generically, for any host.

### Added — Obstacle-driven render escalation (`obstacle-driven-render-escalation`)

- **`obstacle` drives a render, not just a confidence downgrade.** A new
  `_phase_obstacle_render` runs after answer extraction: when the LLM reports
  `obstacle ∈ {empty, blocked}` (a fat SPA shell / stale render that slipped the
  length floor), it dispatches one paid render of the original URL (Zyte
  `browserHtml`), re-extracts the answer over the real content, and only then
  falls back to `retrieval_incomplete`. Previously (v0.29.0) the obstacle only
  capped confidence + flagged incomplete — it declared defeat.
- **Generic SPA-host coverage falls out for free.** Because the trigger is the
  LLM's obstacle signal rather than a per-host rule, ANY host where the extractor
  sees an empty/blocked shell escalates — no per-site `escalate_to_render` wiring.
- **Strict, shared cost cap.** Fires only on the `ask` path, only for
  `empty`/`blocked` obstacles (not `paywalled`/`error` — a render won't clear a
  paywall), and only when no paid render was already spent (`paid_dispatches < 1`,
  shared with the gate-wall and handler triggers). Bounded to one render + one
  extra LLM call. Un-keyed deployments no-op and keep the loud
  `retrieval_incomplete` miss.
- **Never-silently-miss preserved.** If no paid tier is keyed, the render adds
  nothing, or the re-extraction still reports the obstacle, the v0.29.0
  `retrieval_incomplete` + critical hint stands. `_phase_cache_write` moved after
  the render phase so the final body is cached once and a confabulated shell never
  enters the cache. No wire-shape change, no new tool params.

## [0.31.0] — 2026-07-06

> Two residual retrieval-miss holes closed: JSON served under a lying
> content-type is now recovered, and a rate-limited Reddit search/listing takes
> the fast render path instead of the slow ladder. No wire-shape change.

### Fixed — JSON body-sniff + Reddit 429 render shortcut (`json-body-sniff-and-reddit-429-render`)

- **JSON served under a non-JSON content-type is recovered.** v0.30.0 routes
  JSON responses directly, but keyed on the content-type header. A misconfigured
  API returning JSON as `text/html` / `text/plain` slipped through (trafilatura
  over JSON, or jina-mangled → false `length_floor`). The raw tier now sniffs a
  2xx body and, when it parses as JSON, normalizes the content-type to
  `application/json` so the v0.30.0 synthesis path handles it. Prefix-guarded on
  `{`/`[` within a bounded window (large HTML/binary bodies are never decoded);
  HTML never parses as JSON, so the sniff only ever upgrades a genuine JSON body.
- **Reddit search/listing `429` → paid site render.** A rate-limited (429)
  Reddit search or listing RSS surface now escalates straight to a paid render
  (like the v0.29.0 `403` wall case) instead of returning `rate_limited` and
  walking the slow ladder (which still reached Zyte, just later). Thread/permalink
  `429` is unchanged — still fails loud with `rate_limited`.
- Both are correctness/latency hardening: no wire-shape change, no new tool
  params, `json.loads` stays funnelled in the `json_in_script` package.

## [0.30.0] — 2026-07-06

> JSON API endpoints stop being mangled. A JSON response is now first-class
> content — synthesized to markdown in-place — instead of being escalated to the
> jina HTML reader (which read JSON as a webpage and produced a false
> `length_floor` failure). Closes Issue 3 from the 2026-07-05 Reddit/HN feedback
> report. No wire-shape change, no new tool params.

### Fixed — JSON endpoints route directly, never through the jina HTML reader (`json-endpoint-direct-routing`)

- **Raw tier: a JSON response is `ok`, not a mismatch.** A 2xx response with a
  JSON-family content-type (`application/json`, `application/<x>+json`,
  `text/json`) maps to `Verdict.ok` instead of `content_type_mismatch`. The raw
  tier wins, the JSON body reaches extraction, and jina is never consulted.
  Non-JSON mismatches (PDF, octet-stream, `text/plain`) keep escalating as before.
- **Extract phase synthesizes JSON response bodies.** When the won tier's
  content-type is JSON, `_phase_extract` parses the body and renders it via the
  existing `json_to_markdown_rows` synthesis (the same renderer the JSON-in-script
  path uses) — known shapes (`products` / `items` / Product / Article / ItemList)
  become tables/records.
- **Never-lose fallback for unknown JSON shapes.** An arbitrary API shape that
  synthesis doesn't recognize falls back to the JSON text itself — pretty-printed,
  capped at 20 000 chars — so a valid-but-unrecognized payload still reaches the
  caller and the `ask` extractor (never a silent empty miss).
- **JSON bypasses the thin-shell length floor.** A small-but-complete JSON body
  (`{"count": 42}`) is a valid answer, not a truncated SPA shell; the exemption
  keys strictly on the JSON content-type, so HTML shells keep the full floor and
  the v0.29.0 confabulation guard is untouched.
- **`json.loads` stays funnelled.** Response-body parsing lives in the
  `json_in_script` package as `parse_json_response` (which already owns
  `json.loads` for the in-script path); the json-loads-funnel arch invariant
  holds — no new `json.loads` outside the package.
- Live-verified: `web fetch_raw` and `web ask` over
  `jsonplaceholder.typicode.com/users/1` (a JSON endpoint that previously
  false-failed via jina) now return the data and a correct extracted answer.

## [0.29.0] — 2026-07-05

> Community-site search retrieval + a confabulation guard. HN/Algolia search
> resolves via the API, `ask` confidence reconciles with the extractor's
> `obstacle` signal, SPA/walled search escalates to a paid Zyte render, and the
> HN + Reddit handlers de-escalate to that render on failure. All grounded in
> live-verified probes; no wire-shape change (correctness tightening only).

### Added — Community-site search retrieval + confabulation guard (`search-retrieval-and-confabulation-guard`)

- **HN Algolia search** (`hn.algolia.com/?q=…`): the HN handler now claims the
  Algolia search-UI URL and resolves it through the public
  `/api/v1/search?query=…&tags=story` API (reusing the existing hit-list render +
  next-link discovery) instead of letting the generic ladder render the
  client-side SPA shell. Fixes the silent-wrong-content case where the SPA URL
  returned an unrelated page at `confidence: high`.
- **Confabulation guard** on `ask`: `confidence` now reconciles with the
  extractor's own `obstacle` signal (previously derived only from verdict +
  content length). An `obstacle` of `empty`/`blocked`/`paywalled`/`error` caps
  `confidence` to `low`; `empty`/`blocked` also set `retrieval_incomplete` + a
  critical `retrieval_incomplete` operator hint. Closes the gap the
  `extraction_empty` guard leaves for a fluent-but-unfounded (non-empty) answer.
  Applied at the ask projection (where `obstacle` reaches the wire); `fetch_raw`
  is unaffected.
- **Paid render for SPA shells**: the paid last-resort planner now treats a
  post-browser `length_floor` with subsystem `js_required` as a wall worth a
  paid render (Zyte `browserHtml`), so a JS-shell SPA that the browser rung can't
  render escalates instead of dying as `length_floor`. Cost-gated on the
  `js_required` subsystem (never bare `length_floor`) and the single-paid-dispatch
  cap.
- **Escalate to a paid site render**: a new typed `escalate_to_render` signal on
  `TierResult`. A handler sets it when its rewritten fetch fails (HN's
  `hn.algolia.com/?q=` → the Algolia API) **or** its surface is walled (Reddit
  search/listing behind a 403). The orchestrator records the attempt as a
  diagnostic, **stops the free ladder** (raw/jina get fooled — an SPA shell can
  exceed the 500-char length floor and pass the gate as `ok`; the own-browser is
  unreliable on these), and renders the ORIGINAL URL directly via the paid tier
  (Zyte `browserHtml`). Even a `404` (normally authoritative for a site handler)
  no longer ends the run before the real page is rendered. No paid key / render
  failure → loud never-silently-miss (`retrieval_incomplete` + critical
  `try_user_browser`). Built generically; HN and Reddit are the first adopters.

## [0.28.0] — 2026-07-05

> Config-gated Google OAuth on the HTTP MCP endpoint (`a2web-serve`) — closes the
> open-endpoint gap. No new dependency; a2kit stays auth-agnostic on MCP by
> design. **BREAKING** container change: the image ENTRYPOINT is now `a2web-serve`
> (unconfigured → still open, so behavior is unchanged unless `GOOGLE_*` is set).

### Added — Config-gated Google OAuth on the HTTP MCP endpoint (`google-oauth-endpoint-auth`)

- The published container now serves via **`a2web-serve`**, which turns on Google
  OAuth when `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_BASE_URL` are
  set — a FastMCP `GoogleProvider` passed through
  `serve_process(mcp_options={"auth": provider})` (a2kit's blessed MCP-auth
  recipe; a2kit stays auth-agnostic on the MCP surface by design, ADR 0010). No
  new dependency: `fastmcp` + `key_value` already ship.
- **Unconfigured → open, unchanged** (ship behind Tailscale/LAN). **Partial config
  fails loud** at boot (id without secret/base_url) rather than silently serving
  open. `GOOGLE_BASE_URL` must be the **public** URL (the OAuth redirect derives
  from it), never the bind host.
- OAuth sessions persist in an off-the-shelf **FileTree** token store under
  `/data/oauth` (survives restarts; optional Fernet-at-rest via
  `A2WEB_OAUTH_ENCRYPTION_KEY`). `GOOGLE_JWT_SIGNING_KEY` recommended for
  cross-restart token validity. `GOOGLE_*` are env-only (never in repo or image).
- a2kit pin bumped `v0.49.1 → v0.49.2` (MCP-auth recipe + honest auth docstrings).
- Supersedes `deployable-container-ci` group 5.

## [0.27.0] — 2026-07-05

> Deployable container arc: OpenAI-compatible LLM backend (DeepSeek prescribed),
> a slim published image (2.05 GB → 391 MB via optional extras + multi-stage),
> a GHCR release pipeline, hardened fail-loud guardrails, and a complete
> deployment env-var reference. **BREAKING** packaging: `claude-agent-sdk`,
> `patchright`/`zendriver`, and `browser-cookie3` are now optional extras.

### Added — OpenAI-compatible LLM backend (`openai-compatible-llm-provider`)

- **Third extraction backend** alongside `anthropic` and `claude-code`, reached
  through the `openai` SDK's **standard** env vars — `OPENAI_API_KEY`,
  `OPENAI_BASE_URL`, `OPENAI_MODEL` — not custom `A2WEB_LLM_*` ones. Presence of
  `OPENAI_API_KEY` gates availability and derives the backend as the
  last-resort fallback in auto order (never shadows Claude/Anthropic). Unset
  base URL → OpenAI proper; set it for DeepSeek / Gemini / OpenRouter / local.
  Model resolves from `OPENAI_MODEL`, else a host-keyed recommendation, else a
  loud failure. Validate a custom model with the data-contract axis as the
  pass/fail gate — see the `eval/model_benchmark/` reference experiment.
- **Reference model benchmark** committed at `eval/model_benchmark/`
  (methodology-as-code + provenance-stamped results). Verdict: **DeepSeek V4
  Flash** is the cheapest backend clearing the router-shape contract at
  Haiku-class quality (~1/14th the cost).
- **Model-agnostic router-shape parsing:** the wobble funnel now recovers a
  leading JSON object when a verbose model appends a trailing `next_links`
  fence, and a critical `extraction_empty` operator hint fires when real
  content is fetched but the LLM returns an empty answer (ADR-0009 at
  extraction granularity).
- **`ask` fails hard when it delivers no answer (structured, every route).** At
  the single response chokepoint, an `ask` whose fetch succeeded but produced no
  answer is escalated from a hint-on-`ok` to a full `status: failed` +
  `retrieval_incomplete: true`, with a critical operator hint naming the fix.
  Covers the three misconfiguration/quality cases a homelab deploy will hit:
  no LLM backend configured (`llm_unavailable`, now **critical**), a bad LLM
  key/model (the provider returns empty text → `extraction_empty`), and an
  off-contract/empty model response (the model-swap risk). A status-checking
  agent can never read an answerless response as complete. (A bad **paid-tier**
  key — Zyte/Firecrawl — already failed loud via `paid_auth_error`.) `fetch_raw`
  is unaffected: it needs no answer.

### Changed — BREAKING packaging: heavy deps are now optional extras (`deployable-container-ci`)

- **`claude-agent-sdk` moved out of baseline deps** into the optional
  `a2web[claude-code]` extra. It bundles a ~210MB Claude Code binary the slim
  server container has no use for, and the container's default backend is now
  OpenAI-compatible (DeepSeek). `plain pip install a2web` no longer brings the
  SDK — install `a2web[claude-code]` for the Claude Code OS-session piggyback.
  When the SDK is absent, the `claude-code` provider reports `Unavailable` and
  auto-select falls through to `anthropic` / `openai_compatible` (loud `None`
  if nothing is keyed) — no crash on first use.
- **`patchright` + `zendriver` moved out of baseline** into the optional
  `a2web[browser]` extra. The baked Chromium + its desktop system-lib tree were
  ~1.35 GB of a 2 GB image, yet the browser tier is escalation-only. When the
  extra is absent, the browser-backend manifests report `Unavailable` and a
  browser-only site degrades to a critical `try_user_browser` operator hint —
  never a crash or silent miss. The published container is slim (~390 MB,
  browserless, multi-stage build); bake the browser with
  `--build-arg INSTALL_BROWSER=true`.
- **`browser-cookie3` moved out of baseline** into the optional `a2web[cookies]`
  extra (drops `lz4` + `pycryptodome` from the default image). The cookie mirror
  reads the *local* machine's browser store, so it is inherently local-only and
  useless in a server container. Absent → `cookies_refresh` returns a loud
  "install a2web[cookies]" note; normal fetches read the sqlite mirror unchanged.
- **New `expose_cookies_tool` toggle (default `false`, BREAKING for local cookie
  users).** The `cookies_refresh` tool is no longer registered by default — a
  network MCP server has no local browser to mirror. Set
  `A2WEB_EXPOSE_COOKIES_TOOL=true` for local `serve` where you want it. This is
  independent of the extra: the toggle controls *exposure*, the extra controls
  *function*.
- `make install-global` installs `a2web[claude-code,browser,cookies]`, so the
  local tool keeps every extra — set `A2WEB_EXPOSE_COOKIES_TOOL=true` to surface
  the cookies tool in a local serve.

## [0.26.0] — 2026-07-04

### Added — Reddit via Zyte: scored/nested comments + honest-partial contract (`reddit-via-zyte`)

- **Reddit threads are now reachable with real depth.** When a Zyte key is
  configured, the Reddit handler normalizes any thread URL to
  `old.reddit.com/r/<sub>/comments/<id>/<slug>/?limit=500&sort=top` and fetches
  it through Zyte's cheap raw (`httpResponseBody`) mode — old.reddit is
  server-rendered, so ~top-500 **scored, nested** comments come back in one
  load. This bypasses the free tier ladder (raw/jina provably lose on Reddit)
  and is strictly richer than the keyless RSS channel (flat, scoreless, ~25
  recent). A dedicated selectolax parser (`handlers/_reddit_html.py`) reads the
  post + comments (author / score / nesting depth) with no shreddit
  web-components and no trafilatura. Listings/search stay on RSS.
- **Availability-gated tier policy, never hard-disabled.** New
  `A2WEB_REDDIT_TIER_POLICY` (`robustness` default = Zyte→RSS; `privacy` =
  RSS-only, no third party sees the URL). Un-keyed or `privacy` deployments keep
  the exact keyless behavior. A bad Zyte key fails loud (`paid_auth_error`),
  never a silent downgrade; a transient Zyte miss falls through to RSS.
- **content-expectations: honest "top-N of M" comment signal (ADR-0009 at
  comment granularity).** A new oracle-driven readiness seam
  (`content_expectations.assess`) compares parsed comments against the
  authoritative old.reddit `N comments` count. A shortfall emits
  `OperatorHint(code="comments_partial", severity="info")` plus **additive**
  `comments_loaded` / `comments_total` fields on `AskResponse` + `FetchResponse`
  (omitted from the wire when empty) — an agent is always told when it holds a
  ranked sample, never the whole thread. Golden tool-schema contracts re-blessed
  additive-only (+2 fields per envelope, zero removals).
- **Zyte tier gains a fetch-mode toggle.** `ZyteTier` now supports
  `httpResponseBody` (raw proxy, base64 body — cheap, for server-rendered
  targets) alongside `browserHtml` (rendered). The auth/billing fail-loud
  mapping is identical in both modes.
- **Deferred + recorded, not re-litigated.** The self-hosted stealth-browser
  rung (Camoufox/zendriver) is designed into the ladder as an `Unavailable`-
  gated rung ahead of Zyte but **not built** — the blocker is a residential-IP
  requirement, not the engine (both pass headless from a residential IP; both
  are blocked through datacenter egress). Recorded in ADR-0011 (superseding
  update) + BACKLOG. **Limitation:** the Zyte path is public-read only; logged-
  in / NSFW / personalized Reddit needs the deferred rung.

## [0.25.0] — 2026-07-04

### Added — Reddit reachability + "never tolerate ANY unfetched URL" tenet (`reddit-reachability-never-silent-miss`)

- **Reddit is reachable again, keyless.** The Reddit handler now projects
  `search` / `listing` / `thread` URLs to their `.rss` (Atom) equivalents and
  parses them with stdlib `xml.etree.ElementTree` — the `.rss` endpoints are NOT
  behind Datadome (every `.json` shape is 403-walled from a datacenter/remote
  IP). All listing sorts project (bare/`hot`/`best` → `/r/<sub>/.rss`;
  `top`/`new`/`rising`/`controversial` → `/r/<sub>/<sort>.rss`, preserving
  `?t=`). RSS output is a **degraded projection by design** — flat comment
  *sample* (recent-ordered, no scores, no nesting), explicitly labeled "not
  scored, not ranked, not complete." `429` backs off (`_RSS_BACKOFF_S`) then
  fails loud; search/listing `403` fires the critical browser hint eagerly (the
  full tier ladder is proven to lose on Reddit).
- **Never-silently-miss is now a first-class product invariant (ADR-0009).** A
  walled or failed fetch can no longer masquerade as a complete answer:
  `FetchResponse`/`AskResponse` carry `retrieval_incomplete: bool` (omitted from
  the wire when `false`), and a terminal wall emits
  `OperatorHint(code="try_user_browser", severity="critical")` — imperative and
  capability-generic (names no browser product): *this URL was NOT retrieved; do
  not answer as if you have it; open it in a real browser tool OR tell the user
  it could not be retrieved.* Reddit emits it eagerly from the handler; other
  hosts emit it late (after the tier ladder exhausts), deduped by
  `_has_browser_hint` so there is never a double-emit. The CLAUDE.md tenet line
  was strengthened from "Never silently drop a fetch" to "**Never tolerate ANY
  unfetched URL**."
- **Env-gated paid last-resort tiers: Zyte + Firecrawl.** New out-of-band tiers
  (`tiers/zyte.py`, `tiers/firecrawl.py`; manifests `priority=-1`) keyed by
  `A2WEB_ZYTE_KEY` / `A2WEB_FIRECRAWL_KEY` (env-only secrets, added to the YAML
  `EXCLUDE` set). Un-keyed → the manifest returns `Unavailable` and the tier
  never registers, so zero-config fetches never incur cost. Dispatched by a new
  `EscalatePaid` planner action (the lowest-priority rule, declared last) **only
  after** the free/proxied ladder (raw → jina → browser → archive) hits a wall —
  never speculative, capped at one paid attempt per fetch. A keyed-but-failing
  service (bad key / exhausted billing) maps to the new **authoritative**
  `Verdict.paid_auth_error` (rank 12 — outranks every wall) and **STOPs**
  escalation: no silent fall-through to a sibling paid tier or a cheaper result.
- **Dependency memory (Constitution Article VIII).** ADR-0009 (tenet) + ADR-0010
  (every Reddit access path tried/adopted/rejected/deferred, with re-evaluation
  triggers) + `src/a2web/tiers/_deps.md` record the Zyte/Firecrawl adoptions and
  the Redlib / PullPush / Reddit-OAuth / proxy-through-Shen / local-cookie-CLI
  rejections so none is re-litigated.
- **Envelope change is additive.** New fields only — `retrieval_incomplete`,
  `OperatorHint.severity`, and one new `Verdict` value (`paid_auth_error`); no
  removals. Golden contracts (`tests/contracts/`) re-blessed additive-only.

## [0.24.0] — 2026-06-28

### Changed — MCP surface: code-mode off by default; named tools advertised directly (a2kit 0.46)

- **a2web opts out of a2kit's `code_mode=True` default.** `A2Web` now declares
  `config = A2kitConfig(mcp=McpConfig(code_mode=False))`. a2web is a few-tool,
  lean-payload server — `ask`/`fetch_raw`/`refresh` distill content server-side,
  so the code-execution sandbox (`search`/`get_schema`/`execute` meta-tools) was
  pure tax on the ~95% single-`ask` path. With it off, MCP `list_tools`
  advertises the bare-name tools directly and the `canonical_name_override` pins
  in `routers.py` go live as the wire contract.
- **Requires a2kit ≥0.46**, which lifted `code_mode` into `McpConfig` as a
  per-server-shape knob (a2web round-14 feedback, `docs/history/A2KIT_FEEDBACK_v0.44.md`).
  The `serve` flag is tri-state (`--code-mode/--no-code-mode`; omit → consult
  config); env still wins, so `A2KIT_MCP__CODE_MODE=true` re-enables the sandbox
  per-deployment. The `a2kit[code-mode]` extra stays installed so that escape
  hatch + the `a2web code` subcommand remain buildable on demand.

### Changed — two-tier browser rendering: patchright (fast) → zendriver (robust), Camoufox retired (`browser-backend-bakeoff`)

- **Bake-off, then keep two.** A live render-layer bake-off
  (`eval/findings_2026-06-27.md`) scored three engines behind the
  `BrowserBackend` seam on SPA-read + robustness + speed. Result: the Chromium
  drop-ins (patchright, rebrowser) are fast but **fail the Trendyol/Hepsiburada
  SPAs** that motivated this; **zendriver** (CDP) reads them but is ~4-5x slower.
  They're complementary, so we keep **both** — patchright as the fast rung,
  zendriver as the robust rung — and **prune rebrowser** (the strict loser).
- **Two browser tiers on the existing escalation, not a new mechanism.** A new
  out-of-band `browser_robust` tier (zendriver) joins `browser` (patchright) in
  `REGISTRY`. The fast→robust ladder is the **existing** `gate_browser_signal`
  playbook rule firing twice — its cap widened `1→2`; the single
  `_escalate_browser` handler picks the rung from the per-fetch dispatch count.
  No new action, no new rule, no TIER_ORDER change. Fixed a latent gap:
  `_regate_after_escalation` now carries the escalation signal, so a still-thin
  fast render can re-trigger the playbook (it couldn't before).
- **`browser_robust_backend` seam.** A second `Lazy[RobustBrowserBackend]` tool
  seam + provider (distinct DI key via a marker sub-Protocol), entered only when
  the robust rung fires. Decision-log `engine=` is now the real engine/tier name
  (`browser`/`browser_robust`, `patchright`/`zendriver`), not a hardcoded label.
- **Camoufox gated, deps modernized.** Camoufox is gated to `Unavailable` (its
  build lacks juggler #625 / `b05563291d`); its launcher code is retained for a
  one-line re-enable. `patchright` + `zendriver` are promoted to baseline deps;
  **`camoufox` + the transitive `playwright` (and the `<1.60` version-skew
  exposure) are dropped**, along with the bake-off-loser `rebrowser`.
- New CDP adapter `ZendriverBackend` proves the `BrowserBackend` interface spans
  engine *families*, not just the Playwright API. Real-browser smoke covers both
  rungs (`make test-browser`).

### Changed — extracted a swappable `BrowserBackend` interface (`browser-backend-interface`)

- The browser tier no longer drives a Playwright `Page` directly — it delegates
  rendering to a selected `BrowserBackend` and owns only the engine-agnostic
  tail (trafilatura → markdown, the `RenderOutcome` → `Verdict`/`OperatorHint`
  mapping, `TierResult` assembly). Pure refactor: **no behavior or response-
  envelope change** (`tests/contracts/` unchanged), all browser tests + the
  real-browser smoke check stay green.
- New domain-free package `packages/browser_backends/` (mirrors the `Provider`
  seam): `BrowserBackend` Protocol + the neutral value objects `RenderedPage`
  / `RenderOutcome` / `BackendCookie` (no `OperatorHint`/`Verdict`/`Cookie` on
  the boundary — `RenderedPage`/`BackendCookie` are frozen). `PlaywrightBackend`
  (parameterized by a `launch_fn`) absorbs the former `BrowserPool` (per-host
  LRU contexts, idle eviction, driver-stderr capture) plus the page-driving
  render mechanics; Camoufox is `PlaywrightBackend(camoufox_launcher)`.
- Engine selection is settings-driven: `settings.browser_backend` (default
  `"camoufox"`) + `select_backend` over `_manifests/browser_backends/`. The
  `BrowserBackend` replaces `BrowserPool` as the registered resource; the tool-
  seam kwarg type is now `Lazy[BrowserBackend]` (internal DI type — the MCP wire
  is unchanged). Keystone for the Chromium backends (patchright/rebrowser) and
  the engine comparison that follow.

### Fixed — browser tier leaked driver stderr + swallowed errors (`surface-browser-internal-errors-as-hints`)

- The browser tier (Camoufox/Firefox) no longer leaks raw Node.js driver
  stack traces to the operator's terminal. Playwright's driver inherits
  `sys.stderr`'s fileno at spawn (`_transport.py`); the pool now swaps in a
  pipe-backed `sys.stderr` shim across the launch so **only the driver
  subprocess** is redirected (the parent's fd 2 and all `StreamHandler`s stay
  intact). Captured lines surface as typed `BrowserSubprocessStderr` log
  events via `await a2kit.log.info(...)` — zero events on the happy path.
- Internal navigation/driver exceptions are no longer swallowed. The tier's
  catch site that did `del exc` now attaches a structured
  `OperatorHint(code="browser_internal_error", ...)` with a single-line cause
  summary and an actionable `fix`, surfaced on the response `operator_hints`.
- Closes the test gap that let this ship: the `browser-tier` spec already
  required stderr capture, but it was specced (against the retired LDD
  substrate) and **never implemented** — invisible because every browser test
  was stubbed. Added an opt-in real-browser smoke check (`make test-browser`,
  marker `browser`, excluded from `make check`) that launches real Camoufox
  against a deterministic local JS-rendering fixture and asserts JS executes
  and content returns. Auto-skips when the Camoufox binary is absent.
- The driver-stderr capture lives in the (domain-free) `BrowserPool` via an
  injected async sink — the typed-event emission is wired on the domain side,
  preserving the packages-independence boundary. No envelope or tool-signature
  change; the only contract delta is the `OperatorHint` description gaining
  `browser_internal_error`. Explicitly **not** adding a Chromium fallback —
  a second engine, if ever needed, will be a new tier.

### Changed — a2kit v0.43 → v0.44 (clean no-op pin bump, `a2kit-v044-migration`)

- Pin moved `a2kit` `v0.43.0` → `v0.44.0` (`pyproject.toml` + `uv.lock`). No
  source edits: `make check` green out of the box (845 tests, 90% coverage).
- v0.44 (ADR 0029 internal spoke) touched **nothing a2web consumes** — the
  internal-spoke / `TokenAuth` / `spoke.client` additions, the `serve
  --transport=http` MCP+API multiplex (BREAKING), and the removed
  `packages.mcp.cli` / `build_api_key_middleware` are all surfaces a2web does
  not import. a2web serves over **stdio**, so the http-multiplex change is moot.
  `a2kit.log` is byte-identical across the bump, so the LDD layer is untouched.
- **Internal spoke not adopted** — a2web has no sandboxed-job / single-writer
  core to use it; pulling in unused surface is out per the Constitution's magic
  budget.

### Fixed — bench shutdown hang (`bench-shutdown-thread-leak`)

- `make bench` no longer hangs after the stats dump. A non-daemon background
  thread (curl_cffi / SDK worker parked on `queue.SimpleQueue.get`) blocked
  `Py_FinalizeEx`, requiring a manual SIGKILL — and left the Camoufox browser
  subprocess lingering while the parent hung. `llm_eval/__main__.py::main()` now
  flushes stdout/stderr and `os._exit(rc)`s after `asyncio.run` returns: the
  bench is a one-shot CLI with no graceful-shutdown contract, so skipping
  interpreter finalize is safe, and the immediate parent death lets Camoufox
  reap via its parent-death pipe. Upstream root-cause (which dep leaks the
  thread) stays open. Bench-tooling only; no `src/` runtime path affected.

### Changed — a2kit v0.41 → v0.43 migration (framework surface only)

- Bumped `a2kit` to `v0.43.0`. Adopts two breaking minors with no change to
  fetch/extraction behavior, tier routing, the response envelope, or handlers.
- **ADR-0028 (unified surface):** `server.py` now authors the App by subclassing
  (`class A2Web(a2kit.App): name = "a2web"; routers = (WebRouter, CookiesRouter)`)
  instead of `a2kit.App("a2web")` + `add_router(...)` (both removed). Routers drop
  their `tools` ClassVar — verbs auto-collect from the `@a2kit.read/write` markers.
- **Tool names preserved.** ADR-0028 flat naming would rename the MCP tools to
  `web_ask` / `web_fetch_raw` / `cookies_refresh`; pinned back to the bare
  `ask` / `fetch_raw` / `refresh` via `canonical_name_override=` so the installed
  MCP contract and the nested CLI (`a2web web ask`) are unchanged.
- **ADR-0027 (LDD refound):** `a2kit.ldd` retired for stdlib logging. Typed events
  emit via `await a2kit.log.info(...)`; the `OtelHandler` and bench `LiveSink`
  became `logging.Handler`s attached via `app.log.add_handler(...)`. The bench
  runner attaches handlers to `logging.getLogger("a2kit")` for the matrix run and
  raises that logger to `INFO` (no app-boot to set it).
- Tests reworked for the new sink shape (synthetic `LogRecord`s, handler `emit`);
  added a regression test pinning the canonical tool names. `make check` green
  (845 tests, 90% coverage).

### Fixed — test-resource lifecycle teardown (ADR-0008)

- Eliminated intermittent suite failures (`RuntimeError: Event loop is closed`
  from aiosqlite's worker thread + 17 `PytestUnhandledThreadExceptionWarning`s
  per run). Root cause was a class: the "AppState without an app" unit-test seam
  constructs lifecycle resources but, unlike `async with app:` / the TestClient,
  never closed them, so a `SqliteResource`'s loop-bound worker thread outlived
  the test's event loop.
- `tests/conftest.py` now tracks every `SqliteResource` (wrapping `__init__`,
  covering both `make_default_bundle` and direct construction) and an autouse
  `_sqlite_lifecycle` fixture closes each in the test's own loop, then asserts
  none was left open — a **deterministic** state-based fitness function (proven
  load-bearing: 71 errors x 3 runs when close is skipped; 20/20 clean with it).
- Test-only; no `src/` change. The principled framework-owned fix is filed
  upstream as an a2kit wish (`docs/history/A2KIT_FEEDBACK_v0.42.md`).

### Fixed — JSON-LD Recipe rendering + default-keep entity projection (ADR-0004 json half)

- The JSON-LD → markdown synthesis adapter (`domain.json_to_markdown_rows`) now
  renders the `Recipe` type, including its `nutrition` (`NutritionInformation`)
  subobject — calories, sugar/fat/carb/protein, yield, times. Previously a
  `Recipe` entry matched no branch and rendered nothing, so recipe answers
  (calories, sugar) never reached the extractor even with the multi-source menu.
- Single-entity rendering (`_single_entity_md`) is now **default-keep**: it
  surfaces every answer-bearing scalar / shallow field, dropping only a known
  noise denylist (`@`-machinery, image/media URLs, oversized values), instead of
  gating against a hardcoded `interesting_keys` allowlist. An answer-bearing
  field the author didn't anticipate (a `Product.gtin`, a `Recipe.recipeYield`)
  is no longer silently dropped — eliminating the value-blind structural-filter
  projection (ADR-0003) on the JSON-LD path. Confirms the `json-extract` half of
  ADR-0004. Validated against `regression/recipe-nutrition-volume-gate`: the
  judged answer flipped from "the page has no nutrition, it's a listing" to
  "268 calories, 24 grams sugar"; `tests/architecture/test_json_entity_render_is_default_keep.py`
  locks the class out.

### Fixed — extractor fed the full multi-source menu (ADR-0005)

- The server-side extractor (Haiku) is now fed *every* coarsely-selected
  source — trafilatura prose, **all** renderable embedded-JSON/JSON-LD
  payloads, and structural records — assembled into one deterministic menu
  (`fetcher.assemble_menu`), instead of a single source chosen by a value-blind
  length proxy. The old rule ("a source replaces `content_md` only when its
  render is *longer*") meant a short-but-correct structured payload silently
  lost, and a longer *wrong* one (e.g. a sidebar widget list) could clobber the
  answer-bearing content. The proxy is retired from the extractor-input path; it
  survives only as the wire `content_md` display heuristic, so the **default wire
  is byte-identical** (no parser impact). The JSON rung also stopped collapsing
  to its top-ranked payload — it now emits all renderable payloads, so a
  non-top-ranked one (a `Recipe` among `ItemList`s) is no longer lost (the same
  single-source class, one level down). Coarse subset-suppression drops
  duplicate/substring renders; menu assembly is pure + byte-stable so the
  `cache_prefix = {content}` prompt-cache invariant holds across asks. Proven by
  `tests/capabilities/extraction/test_menu_assembly.py` +
  `tests/architecture/test_menu_assembly_is_pure.py`. Confirms ADR-0005.

### Added — debug `content_candidates` on FetchResponse

- Under `debug=True`, `FetchResponse` carries `content_candidates[]`
  (`{source, content_md}` per rung) regrouped under the `debug` object — the
  exact menu the extractor saw, inspectable without changing the default
  envelope. The eval replay harness asserts against this menu (what Haiku was
  fed), independent of the wire (ADR-0005 D7).

### Fixed — record_extract value-blind projection (list-vs-sale fidelity)

- Listing records whose price cell rendered adjacent inline values with no
  separating whitespace (`<del>890 TL</del><span>%21</span><span>700 TL</span>`)
  no longer fuse into a single token. `record_extract._own_text` previously
  flattened a record's descendant text with a no-separator join, producing
  `890 TL%21700 TL`; the extractor then reported the **list** price as the
  selling price and fabricated a list price from the fused digits, at
  `confidence: high`. The projection now separates distinct DOM text nodes at
  element boundaries (content-agnostic — no price/percent special-casing) and
  preserves strikethrough markup (`<del>`/`<s>`/`<strike>` → markdown `~~…~~`)
  so a struck list price is distinguishable from the live sale price. Validated
  against the frozen regression `eval/corpus/regression/hepsiburada-listing-price`:
  the answer flipped from "890 TL … 1,700 TL list, 48% off" to the correct
  "700 TL, discounted 21% from 890 TL". Executes ADR-0003 and confirms the
  `record_extract` half of ADR-0004. (CSS-`line-through` struck prices without a
  semantic tag remain future work under ADR-0007.)

### Added — eval substrate (egress-boundary replay; instrument-first)

- A multi-egress replay harness that freezes every external interaction at
  its boundary — the `http_fetch.fetch_bytes` HTTP outcome, the
  `BrowserPool`-rendered DOM, and the `LlmExtractorResource` response — and
  re-runs the real orchestrator, gate, tier ladder, and escalation above it.
  The LLM is a *recorded* egress (byte-exact answer + token cost), never a
  fake. Lives in the non-packaged `eval/_capture/` (cassette format, corpus
  loader, `make eval-capture` / `make eval-refresh`) and `tests/eval_replay/`
  (deterministic replay + contract asserts); an arch fitness function
  forbids `a2web.*` from importing the harness (evals are tests).
- Cases split a frozen `inputs/` (snapshot of the world, MAY drift) from an
  asserted `baseline/` (`contract.json` shape gates `make check`; `answer.md`
  reference is the LLM-judged axis under `make bench`). `make eval-refresh`
  re-captures inputs and shows a diff against the blessed baseline, blessing
  only under `A2WEB_BLESS_EVAL=1` (mirrors `A2WEB_BLESS_CONTRACTS`). Fixtures
  commit plain (git already zlib-packs; plain keeps the bless diff readable).
- First `regression` case: `hepsiburada-listing-price`, discovered through
  real a2web interaction. A Hepsiburada listing renders discounted items as
  `890 TL%21700 TL`; the record renderer's value-blind text projection fuses
  the −21% badge into the price digits and the extractor confidently answers
  with the *list* price as the selling price. Frozen as the class-C anchor
  for the extraction-fidelity program (`docs/architecture/extraction-fidelity-program.md`).
- Completed (eval-substrate change closed): the `breaking` corpus now carries
  class **A** (`arxiv-attention-clean-schema`, `allrecipes-nutrition`) and class
  **B** (`wikipedia-absent-fact` — honest "not disclosed", no fabrication),
  replayed by `tests/eval_replay/test_breaking_corpus.py` in `make check`; class
  **C** is covered by the `regression` cases (a fresh non-Cloudflare-walled C is
  impractical). Confirmed the `make bench` (live, judged) vs `make check`
  (offline) lane split and that the judge model is pinned + recorded in
  `manifest.json`. The LLM-recording key is one response per case (documented).

### Fixed — listing offer-lift (JSON-LD `ItemList` synthesis)

- Product-listing pages whose data is JSON-LD `ItemList` + `Product.offers`
  (e.g. Hepsiburada) no longer extract to a useless answer. The synthetic-
  markdown adapter (`domain.json_to_markdown_rows`) previously dropped every
  nested field — for a `Product` row only `name` + `image` survived, so the
  extractor saw no prices and no product URLs, could not answer price
  questions, could not emit `try_url` drilldowns, and mislabeled a data-rich
  page as `obstacle: empty`. The adapter now lifts `offers.price` +
  `offers.priceCurrency` (combined, e.g. `3690 TRY`), `offers.url`, and
  `aggregateRating.ratingValue`, and renders commerce-shaped lists as linked
  markdown records (`- [name](url) — 3690 TRY ⭐ 4.7`) with the product URL
  preserved verbatim and un-truncated. The `image` field is dropped (token
  noise). Non-commerce `ItemList` payloads keep the existing table rendering.
  Scope: JSON-LD shape only — non-LD app-state (Trendyol/Yandex) and
  bot-walled raw (Amazon) are separate, tracked changes.

### Added — Constitution + cross-surface lint stack (from a2kit)

- **`CONSTITUTION.md`** — verbatim copy of a2kit's Constitution (the
  rules above the rules: substrate/product, placement hierarchy,
  adopt-before-build, magic budget, dependency memory). Canonical
  source is a2kit; drift between copies is a bug.
- **`policies/data.json`** — a2web-specific allowlist seeded for
  conventional-name patterns (`_ensure` across resources, `_render_*` across
  handlers, etc.) overlayed on a2kit's bundled REGO-BODY-DUP, REGO-NAME-COLLISION,
  REGO-GHA-PIN-SHA / PERMISSIONS / VENDOR-ALLOW, and REGO-PYPROJECT-UPPER-BOUND
  policies. As of a2kit v0.41.1 the policy bundle ships inside the package
  (`a2kit/packages/lint/_bundle/`); a2web no longer vendors `.rego` files
  or the fact extractor.
- **`.pymarkdown.json`** — markdown lint config (line-length / inline-html
  / etc. disabled to match a2kit's tolerance).
- **`.pre-commit-config.yaml`** — local hooks: ruff check + format,
  pymarkdown (README/CHANGELOG/CLAUDE only), actionlint (when workflows
  exist), `a2kit lint rego src/ pyproject.toml`, and ty on pre-push.
- **`pymarkdownlnt` + `pre-commit`** added as dev deps.
- **Makefile `lint`** target wires ruff + pymarkdown + `a2kit lint rego`.

`aiofiles` runtime dep gained an upper bound (`>=25.1,<26`) to satisfy
REGO-PYPROJECT-UPPER-BOUND. Three pre-existing pymarkdown violations
(CHANGELOG + CLAUDE) fixed in place.

### Changed — a2kit v0.41.1 upgrade

- Bump `a2kit>=0.41,<1` (pinned to `v0.41.1`). The Rego policy bundle
  and AST fact extractor now ship inside the package; a2web's vendored
  `policies/*.rego` and `scripts/extract_facts.py` (~1000 LOC) deleted.
  `policies/data.json` (project allowlist) is now the only Rego file
  a2web ships. `uv run a2kit lint rego src/ pyproject.toml` invocation
  unchanged.
- **`AskExtraction` inherits `PruneEmpty`** (a2kit v0.40.1) instead of
  carrying its own `model_serializer`. Pydantic cascades the parent's
  serializer through `AskResponse._envelope_discipline` automatically.
  `truncated: bool` (required, non-empty even when False) survives the prune.
- Imports migrated to the promoted top-level surface: `from a2kit import Lazy`
  / `from a2kit import LddEmission` (was `a2kit.packages.di.Lazy` /
  `a2kit.packages.ldd.LddEmission`).
- **Removed `settings.ask_only`** (env `A2WEB_ASK_ONLY`). a2kit v0.40 ships
  first-class runtime tool selection: `A2KIT_TOOLS=ask a2web serve` or
  `a2web serve --tools=ask`. `WebRouter.__init__` no longer rewrites its own
  `tools` tuple — the class-level declaration is the single source of truth.
- **Test plumbing: `client.override()` → `app.provide()`** per a2kit v0.40
  ADR 0017 (post-seal mutation removed). New `a2web.server.build_app()` factory;
  tests construct a fresh `App` per call and pass fakes as last-write-wins
  factories.
- Substrate gap (partially closed in v0.40.1): `_prune_wire` on
  `AskResponse` / `FetchResponse` stays — it's deviation/required/failure_only/
  debug-regrouping/TSV business logic that can't be substrate (Constitution
  Article V).

### Changed (internal — no public API changes)

- **`make bench` is no longer silent.** Per `openspec/changes/bench-live-sink-v1/`:
  every (corpus × system) cell now emits `CellStarted` / `CellEnded` LDD events
  bracketing its run. A new `LiveSink` (`src/a2web/llm_eval/live_sink.py`)
  subscribes to those events and renders one line per cell to stdout, plus a
  30s heartbeat while cells are in flight. `_ldd_ambient` in
  `llm_eval/runner.py` flips from `events_enabled=False` to
  `events_enabled=True`; the sink filters by name so the production
  `StageStarted`/`StageEnded` chatter is dropped at the subscriber level.
  No change to trace files, response envelopes, or production behavior.

## [0.23.0] — 2026-05-25

### Changed (internal — no public API changes)

Per `openspec/changes/fetcher-orchestrator-refactor-v1/` — 7-phase
structural refactor following the 2026-05-25 parallel-agent architecture
audit. NO MCP wire / `ask` / `fetch_raw` envelope changes; pure internal
discipline.

- **Single source of truth for resource construction** (`bootstrap_state`).
  `Resources` frozen bundle (browser_pool + llm_extractor + cookie_jar)
  alongside `AppState`; production providers, eval CLI, and tests all
  delegate to the same per-resource factories. Closes the class of
  regression that caused the v0.22 bench-harness gap — adding a resource
  reaches every construction path automatically.
- **Decision log is the single source of truth for verdict.**
  `FetchContext.gate_verdict` / `gate_subsystem` mutable snapshots are
  gone; reads project from the log via `last_gate_outcome()` →
  `GateOutcomeProjection` frozen view.
- **Non-optional `Lazy[T]` resources** on FetchContext. `fetch()` kwargs
  stay `Lazy[T] | None = None` for caller convenience; normalization to
  `unavailable_lazy(...)` happens at the entrypoint. Phases uniformly
  `await + try/except ResourceUnavailable`.
- **Typed `EscalationSignal`** replaces `suggested_tier: str | None` on
  `Observation` and `BlockResult`. `NextTier = Literal["browser",
  "tls_impersonate", "archive"]` — closed-enum dispatch in the planner,
  no string compares. New `packages/escalation.py` package boundary type.
- **DRY handlers**: 9 byte-identical copies of `_empty_result` consolidated
  into `handlers/_common.empty_result`. 5 handlers use new
  `handlers/_common.map_non_ok(outcome, url)` for the standard
  FetchVerdict → Verdict block. Reddit's shape-aware 403 policy stays
  inline (only handler that needs it).
- **Pure extraction escalators**: `_escalate_via_json` and
  `_escalate_via_records` return immutable `ContentCandidate | None`
  instead of mutating `fc.content_md`. Single assignment site in
  `_run_extraction_escalation`. Same sequential ladder + same policy.
- **Frozen boundary dataclasses**: `ExtractedContent`, `CacheRow`,
  `BlockResult`, `CookieRow`, `EscalationSignal`. New
  `tests/architecture/test_packages_boundary_frozen.py` invariant.

Coverage: 88.4% → 89.3% (less code to cover from DRY). 796 tests pass
(was 780).

## [0.22.0] — 2026-05-25

### Added

- **Quality gate recognizes two new JS-required categories** (per
  `openspec/changes/expand-js-shell-markers/`). When `content_md` is
  below `LENGTH_FLOOR` AND `<script>` is present AND any of these
  markers match, the gate emits `suggested_tier="browser"` so the
  planner escalates:
  - **Reddit JS-challenge interstitial** — hidden form-field markers
    `name="js_challenge"` and `name="jsc_orig_r"`. Fixes Reddit
    listings returning `length_floor` on raw tier (the captured 8KB
    body is an anti-bot challenge, not a content shell). Empirically
    validated against `tests/fixtures/reddit_shreddit_shell.html`.
  - **Web-component SPA shell** — generic custom-element regex
    `<[a-z][a-z0-9]*-[a-z][a-z0-9-]*` (per HTML5 §4.13, custom-element
    tag names MUST contain a hyphen). Pre-covers Lit-based SPAs and
    any other web-component shell we encounter.

### Fixed

- **Reddit listings now reach the browser tier** instead of failing
  silently with `tier=raw verdict=length_floor`. Probe in
  `eval/spikes/reddit_with_cookies_probe.py` proved Camoufox loads
  Reddit successfully (1MB DOM, 68 post-link references); the only
  missing piece was the marker recognition that triggers escalation.

## [0.21.0] — 2026-05-25

**BREAKING — one-release supersession of v0.20.0's `affordances` surface.**
The v0.20 design surfaced, three exploration spikes refined it, and the
router-shape envelope below replaces affordances wholesale. If you're
integrating against v0.20, jump straight to v0.21.

### Added

- **Router-shape envelope on `ask`.** Seven new fields replace the single
  `affordances` payload, decomposed across two orthogonal axes plus drilldown
  hints:
  - **Required (always present when extraction succeeded):** `answer` (renamed
    from `extracted_answer` on `AskResponse` — cleaner since we're already
    breaking), `structural_form` (Literal of 9: `article | thread | listing |
    reference | tutorial | changelog | code | product | media | other`),
    `shape` (Literal of 7: `prose | records | key-value | code | table |
    discussion | mixed`).
  - **Conditional (omitted from the wire when empty/null via `_prune_wire`):**
    `genre` (Literal of 7: `news | encyclopedia | spec | paper | personal |
    official | community`), `obstacle` (Literal of 4: `paywalled | blocked |
    empty | error`), `ask_here: list[str]`, `try_url: list[NextUrl]`.
- **New `discussion` shape value** captures thread-style pages (HN thread,
  reddit thread, lobste, blog with comments) where both authored content AND
  reply structure carry signal. The prompt instructs higher `ask_here`
  generosity on `shape=discussion` (5+ acceptable) because thread pages
  support more useful follow-ups about positions, dissent, consensus.
- **`include_routing: bool = True` kwarg on `ask`** replaces
  `include_affordances`. Default ON. Opt out for the lean v0.14 envelope.
- **`EXTRACT_ROUTER_V1` prompt template** replaces `EXTRACT_WITH_AFFORDANCES_V1`.
  Tail ~−35% smaller (loses cluster-rule prose; gains explicit omit-empty
  discipline). `cache_prefix_template` is byte-identical to
  `EXTRACT_CACHEABLE_V1.cache_prefix_template` — the v0.19 byte-stable cache
  invariant survives the swap.
- **`RouterPayload` + `NextUrlBoundary` boundary types** in
  `src/a2web/packages/llm_extract/router_payload.py` (frozen
  `@dataclass(slots=True)`), with closed-`Literal` pydantic mirrors
  `RouterPayload` + `NextUrl` in `src/a2web/models.py`. Closed-enum violations
  are caught at the seam in `fetcher_response._project_routing` — invalid
  payloads drop the 7 router fields but `answer` text still reaches the wire.
- **Claude Code provider hardening.** `mcp_servers={}`, `strict_mcp_config=True`,
  and `agents={}` added to `ClaudeAgentOptions`. Closes the leak path where the
  host CLI's saved MCP servers (including memory-bearing servers like
  `hub_memory_recall`) could otherwise contaminate extraction subprocesses.
  `num_turns` surfaces in `ProviderResponse.raw` for paranoid verification.

### Removed

- `AffordancesPayload`, `AffordanceShape`, `PageKind` (29-value),
  `PageKindConfidence`, `ContentValue`, `ShapeLabel` (8-value),
  `_OBSTACLE_PAGE_KINDS` — wholesale.
- `EXTRACT_WITH_AFFORDANCES_V1` template + `_split_answer_and_affordances`
  parser + `_OBSTACLE_KINDS` frozenset — replaced by `EXTRACT_ROUTER_V1` +
  `_split_answer_and_routing`.
- `include_affordances` / `request_affordances` kwargs — renamed
  `include_routing` / `request_routing`.
- `AskResponse.extracted_answer` field — renamed `answer`.
  (`FetchResponse.extracted_answer` is unchanged — only the `ask` envelope
  rename.)
- Seven confusable-cluster rules (A–G) — the tighter 9-value `structural_form`
  enum has no synonym pairs, so nothing to disambiguate.
- `page_kind_confidence` and `content_value` — paraphrased by behavioral
  signal (presence of `ask_here` ≈ "content has more questions to ask";
  presence of `try_url` ≈ "elsewhere is better"; absence of `obstacle` ≈
  "healthy page").

### Decisions

Design captured in `openspec/changes/refactor-ask-to-router-shape/design.md`
(D1–D8). Empirical validation in
`eval/findings_2026-05-25-router-shape-pre-impl.md` (0 parse failures, 0
envelope violations, 0 memory leaks, 10/12 shape matches, 100% closed-enum
compliance across 12 URLs).

## [0.20.0] — 2026-05-24

### Added

- **`affordances` field on `AskResponse`.** New default-on payload that surfaces what else the page offers beyond the direct answer: `page_kind` (closed 29-value taxonomy: 24 content + 4 obstacle + `other`), `page_kind_confidence` (low/medium/high), `reasoning`, `content_value` (low/medium/high — *omitted on obstacle pages*), `shapes[]` (closed 8-label vocabulary: list, timeline, key-value, table, code, comments, citations, comparison) each with `where` + `size`, and 3-5 `follow_up_questions`. Designed for consumption by AI agents reasoning about next moves. Consumer decides whether to use the data; a2web's job is to surface signal.
- **`include_affordances: bool = True` kwarg on `ask`.** Opt out to preserve the lean v0.14 envelope shape and save ~500 completion tokens (~18%) per call on high-volume flows.
- **`AffordancesPayload` boundary type** (`src/a2web/packages/llm_extract/affordances.py`) + pydantic mirror in `src/a2web/models.py` with closed `Literal` enums enforced at the API edge.
- **`EXTRACT_WITH_AFFORDANCES_V1` prompt template.** Two-axis rubric (`page_kind_confidence` separated from `content_value`) per RAG-eval best practices (Braintrust / Deepchecks / ResearchRubrics arXiv 2511.07685). Hard cluster trigger forces confidence ≤ medium when label falls in any of 7 confusable clusters (academic / landing / dashboard / changelog / feed / longform / commerce). The `EXTRACT_CACHEABLE_V1` template is unchanged and still active when `include_affordances=False`.
- **Envelope discipline** (matches a2web's `_prune_wire` pattern): when `page_kind` is `paywalled`/`error`/`empty`/`blocked`, the wire-side serializer omits `content_value`, `shapes`, and `follow_up_questions`. Their absence carries the meaning.
- **Cache-prefix integrity**: `EXTRACT_WITH_AFFORDANCES_V1.cache_prefix_template` is byte-identical to `EXTRACT_CACHEABLE_V1.cache_prefix_template` — the v0.19 byte-stable cache invariant survives the new template (guarded by `test_affordances_template_cache_prefix_matches_base_template`).
- **`request_affordances: bool = False` on `Extractor.extract`** with fence-tolerant JSON envelope parser (`_split_answer_and_affordances`). Mirrors the existing `request_next_links` pattern. Parse failures degrade gracefully — `extracted_answer` falls back to the raw text; `affordances` is `None`.
- **`ClaudeCodeProvider` cost reduction (v0.20-pre).** Three new opt-outs strip ~22-27k tokens per call from the Claude Code CLI subprocess: `setting_sources=[]` (skip CLAUDE.md auto-discovery), `skills=[]` (skip skill registry), `extra_args={"disable-slash-commands": None}`. Net session cost ~41% lower. Eval at `eval/findings_2026-05-24-claude-code-cli-flag-sweep.md`.

### Decisions

- **Default ON, opt-out via kwarg.** Consumer decides whether to use the data. Captured in `openspec/changes/add-affordances-to-ask/design.md` §D3.
- **Field name `affordances` chosen via empirical name-bench.** 4-name × 6-run benchmark (`eval/spikes/affordances_v6_name_bench.py`): `affordances` scored highest behavioral grounding (2.67/5 vs 2.33 for alternatives). `leads` was ruled out (CRM connotation pulled the model into the wrong domain); `hints` was ruled out (RAG-provenance connotation). Findings: `eval/findings_2026-05-24-affordances-v5-two-axes.md`.
- **Two-axis rubric instead of one.** v4 spike found a single `confidence` field was degenerate (always `high`, even on wrong labels). Splitting into `page_kind_confidence` (epistemic, about the LABEL) + `content_value` (about the extracted CONTENT) followed RAG-eval literature. Confidence calibration on 30 URLs: 25 high / 5 medium / 0 low — the medium hits are honest cluster ambiguity.
- **Two templates, not one conditional.** Keeps cache-key reasoning local to template constants. Detailed in design.md §D1.
- **`fetch_raw` does NOT surface affordances** — it does not run the LLM. Defer the LDD telemetry on affordances field usage; defer auto-browser-tier escalation on `content_value=low`.

### Spike trail

- `eval/spikes/affordances_v{1,2,3_lean,4_calibrate,5_two_axes,6_name_bench}.py` — six spike rounds across the design space.
- `eval/findings_2026-05-24-affordances-{v1,v2-v3,v5-two-axes}.md` — quality / cost / calibration findings.
- `openspec/changes/add-affordances-to-ask/` — proposal + design + specs (`ask-response`, `extraction`) + tasks.

### Performance

- Marginal cost when affordances are on: ~500 extra completion tokens per `ask` (~$0.002/URL standalone, ~18% on top of existing extraction). Cost is dominated by prompt tokens (page content) which the existing extraction already pays — affordances are essentially free completion-side.

## [0.19.0] — 2026-05-23

### Added

- **Cache-friendly prompt template `EXTRACT_CACHEABLE_V1`.** Static rules in `system`, page content in `cache_prefix_template`, user question in `tail_template`. Production `Extractor` (built by `build_llm_extractor`) now defaults to it; `WebFetchBaseline` continues to use the byte-frozen `WEBFETCH_DEFAULT_V1` eval anchor.
- **`PromptParts` boundary type** + `PromptTemplate.render(content, ask) -> PromptParts`. Providers consume the three named fields (`system`, `cache_prefix`, `tail`) to place cache breakpoints in the right places.
- **`AnthropicProvider` cache markers.** When given a non-degenerate `parts`, the provider sends `system` as `[{type:"text", text:..., cache_control:{type:"ephemeral"}}]` and user content as two blocks (prefix block carries `cache_control`, tail block does not). Two breakpoints used out of Anthropic's 4-block budget. Cost accounting (`extract_token_counts` + 1.25× / 0.10× cache-tier pricing) was already wired — the moment markers fire, cache_read/cache_write tokens appear in `response.usage` and `cost_usd` reflects the savings.
- **Prefix byte-stability snapshot test** (`tests/packages/llm_extract/test_prompt_cache_stability.py`). Asserts `system + cache_prefix` is byte-identical across three different `{ask}` values and that the tails differ. Guards against future prefix drift in any template body edit.

### Decisions

- **No marker code for `ClaudeCodeProvider`.** Probe of installed `claude-agent-sdk` (≥0.1.80) showed zero `cache_control` references. The SDK shells out to the `claude` CLI subprocess and sends `{"role":"user","content": <flat string>}` — there is no API surface to insert breakpoints. The CLI binary applies caching internally given a byte-stable prefix; the new `EXTRACT_CACHEABLE_V1` template guarantees that stability by construction. So the SDK path is compliant via template discipline alone — no code change beyond unpacking `parts.cache_prefix + parts.tail` for the concatenation.
- **`WEBFETCH_DEFAULT_V1` kept byte-frozen.** Reshaping it would forfeit its value as an eval anchor (byte-equality with Claude Code's WebFetch sub-call). A second named template at +20 LoC was the right trade.
- **OpenAI / OpenRouter need no code change.** OpenAI auto-caches prefixes ≥1024 tokens with no opt-in; the template reshape alone unlocks it. OpenRouter passes through to the backend.

### Performance

- Multi-Q sessions against the same URL within Anthropic's 5-minute TTL: Q1 pays cache-write (1.25× input price), Q2-N pay cache-read (0.10× input price) on the page-content tokens — which dominate any long-page extraction. Expected ~60-70% reduction in input-token cost on multi-Q traces; ~zero change on single-Q traces.

## [0.18.0] — 2026-05-23

### Added

- **Microdata extraction.** `packages/json_in_script.py` now walks HTML5 microdata (`itemscope` / `itemprop` / `itemtype`) directly off the selectolax tree it already loads for the script-tag detectors. Output flows through the same `JsonPayload` boundary type with `source="microdata"`; `domain.py` flattens it into the existing LD-JSON markdown adapter (same schema.org type set). Lift: Shopify-class storefronts and other long-tail product pages that don't ship LD-JSON now surface structured data to the LLM extractor instead of falling back to trafilatura's body text.
- **OpenGraph extraction.** Companion walker for `<meta property="og:*">` plus the `article:*` / `product:*` / `book:*` / `profile:*` namespaces. Emits a flat `{property: content}` payload; `domain.py` renders it as a two-column markdown table. Sits at bucket 3 in `rank_payloads` (after `next_data` / `nuxt_data` — OG is metadata, not body).
- **Ranking buckets** in `rank_payloads` extended: strong-microdata sits at bucket 1 (right after strong LD-JSON), weak-microdata joins weak-LD-JSON at bucket 4, OpenGraph at bucket 3.

### Decisions

- **Rejected extruct mid-implementation; rolled the walker on selectolax.** Initial design called for `extruct` (microdata + RDFa + OpenGraph + JSON-LD + microformats + Dublin Core in one library). Mid-implementation revision: the rdflib transitive weight (~MB-scale) is only justified by RDFa coverage, and RDFa hit rate on the a2web eval corpus is zero — the only segment that ships it heavily (academic publishing) is already covered by the `arxiv` handler. Dropped extruct (and its `rdflib` / `pyrdfa3` / `mf2py` / `w3lib` / `pyparsing` / `webencodings` transitive set) and wrote ~60 LoC of selectolax-native walker + ~80 LoC of adapters. Net new dep surface: zero.
- **RDFa is out of scope.** Reversible — add a dedicated path if a real RDFa-shaped failure surfaces in a future eval run. Full rationale in `openspec/changes/archive/2026-05-23-add-microdata-rdfa-extraction/design.md` D1.

## [0.17.0] — 2026-05-23

### Changed

- **GitHub handler REST plumbing swapped to `gidgethub`.** The hand-rolled `_get_json` / `_check_rate_limited` / manual `Link:` pagination / base64 README decode in `handlers/github.py` is gone — replaced by a `_CurlCffiGitHubAPI` adapter (subclass of `gidgethub.abc.GitHubAPI`) that routes every request through the existing `fetch_bytes` primitive. gidgethub owns auth-header injection, status-code → exception mapping (`RateLimitExceeded` on 403+remaining=0, `BadRequest(404)`, etc), URI-template expansion, and response decoding. curl_cffi keeps owning the transport — JA3/JA4 impersonation, breakers, proxies all inherited.
- **Auth header format**: gidgethub uses GitHub's canonical `Authorization: token <pat>` instead of v0.16's `Authorization: Bearer <pat>`. Both are accepted by `api.github.com`; the change is invisible to operators.

### Removed

- ~150 LoC of hand-rolled REST plumbing inside `handlers/github.py` (URL-template constructors, `_get_json`, `_check_rate_limited`, manual `Link:` header pagination parser, manual base64 README decoder).

### Dependencies

- `+gidgethub>=5.4,<6` direct. `+uritemplate` transitive (pure-Python, small).

## [0.16.0] — 2026-05-23

### Changed

- **Browser cookie extraction swapped to `browser-cookie3`.** The hand-rolled `packages/cookie_store/chrome.py` (macOS-only AES-GCM + Keychain CLI) and `firefox.py` (plaintext sqlite) readers are gone — replaced by a thin adapter in `packages/cookie_store/store.py` over [`browser-cookie3`](https://github.com/borisbabic/browser_cookie3). The `CookieJarResource` shape, the `CookiesRouter(slug="cookies")` MCP surface, the `cookies_refresh` tool, the v0.8 "Keychain prompt only on refresh" UX, and the `OperatorHint(code="cookies_stale", ...)` semantics are all preserved.
- **`AppSettings.cookie_source` Literal widened** to `none | chrome | chromium | brave | edge | firefox | safari | vivaldi | opera | opera_gx`. Pre-existing `chrome` / `firefox` env/YAML values continue to parse.

### Added

- **Cross-platform cookie support.** Chrome / Chromium / Brave / Edge / Vivaldi / Opera / Opera GX on macOS, Linux, and Windows. Safari on macOS. Firefox everywhere. The OS × browser matrix is now `browser-cookie3`'s problem, not ours.

### Removed

- `src/a2web/packages/cookie_store/chrome.py` (~191 LoC) and `firefox.py` (~100 LoC) — the hand-rolled readers and their per-OS file-discovery and decryption code paths. The boundary type (`CookieRow`) and the historical `ChromeCookieAccessError` alias are preserved for callers.

### Dependencies

- `+browser-cookie3>=0.20,<1` direct. `+pycryptodomex`, `+lz4`, `+shadowcopy` (Windows), `+wmi` (Windows) transitive.

## [0.15.0] — 2026-05-23

### Added

- **Handler subsystem unification.** The `handler-subsystem-unification` change resolves three issues surfaced in live evaluation of the just-shipped forum/listing-extraction work: DiscourseHandler failing on Cloudflare-fronted hosts (`linux.do` got an anti-AI banner), HTML entities surfacing raw in Discourse titles (`&rsquo;`), and the generic record renderer flattening the heading the detector had already located.
- **`packages/http_fetch/` — shared `fetch_bytes` primitive.** One async callable — `fetch_bytes(url, *, headers, timeout_s, proxy_url=None, cookies=None, conditional_extras=None, breaker=None) -> FetchOutcome` — owns every HTTP fetch for `RawTier`, `ArchiveTier`, and all nine site handlers. Backed by `curl_cffi.AsyncSession` with Chrome JA3/JA4 impersonation, proxy plumbing, per-host circuit-breaker context, conditional-GET via `If-None-Match` / `If-Modified-Since`, and closed-verdict mapping on the returned `FetchOutcome`. Handlers no longer construct `httpx.AsyncClient`; the test seam now is the transport seam, so monkeypatching cannot hide a transport-layer regression.
- **`packages/html_fragment/` — shared HTML-fragment converter.** `to_markdown(html, *, base_url=None)` and `to_text(html)`, lxml-backed, link-preserving, entity-decoded, nbsp-folded. Replaces four hand-rolled regex strippers (discourse `_cooked_to_md`, habr `_html_to_md` + `_text_of`, v2ex `_html_to_md`, hn `_strip_html`). Fixes the `fancy_title` entity-decode class of bug everywhere at once.
- **Live handler probe — `make handler-probe`.** Async entrypoint walking `_HANDLERS` against a representative URL per handler via real network (no monkeypatching), asserting `verdict == ok` AND non-empty `pre_rendered.content_md`. Loud-failure when a registered handler is missing from the `_PROBE_URLS` map. Deliberately not in `make check` — runs when you change transport, render, or handler routing. `linux.do` PASSES, demonstrating the architectural fix.
- **Structure-aware `Record` rendering.** The record-extract `Record` boundary type gains `heading_text: str | None` and renames `primary_link` → `heading_link`. The renderer leads with `- [heading_text](heading_link)` (or `- heading_text` when no link), then the body (heading text peeled from the smush), then the remaining links. Lobste-style records read as `[title](url)\n  meta` instead of the flat smush; sites without a detected heading fall back to the legacy text-led row.
- **Output benchmark — re-runnable, package-resident.** The `benchmark-harness` change folds the benchmark into the maintained `src/a2web/llm_eval/` harness so it survives envelope changes instead of rotting as dated throwaway scripts. Each (URL, system) cell is scored on four axes: answer quality (judge), token cost (per-field tokens of the response envelope the agent reads), output clarity (judge), and data-contract conformance (deterministic envelope field-presence check). A `next_links_picked_correctly` judge axis is applied to listing URLs. The corpus at `eval/corpus.yaml` emphasizes the tricky cases — Reddit comment threads, Hacker News comment/item pages, index/listing pages — alongside clean/gated/SPA controls. The run produces an `axes.md` report with a per-system table and a vs-WebFetch delta summary.
- **`make bench`** runs the benchmark; `make eval` is kept as an alias. The benchmark prefers the Claude Code OS session (OAuth subscription — no `ANTHROPIC_API_KEY` required); `A2WEB_BENCH_PROVIDER` forces the provider.

### Removed

- Retired the stale `benchmarks/vs-webfetch/2026-05-11/` runnable scripts (`runner.py`, `judge.py`, `aggregate.py`, `multi_model.py`, `phase4_ask.py`, `reliability_runner.py`) — they predated the v0.11/v0.14 envelopes and could no longer run. The `findings_*.md` notes are kept as history.

## [0.14.0] — 2026-05-22

The `envelope-deviation-trim` change: one rule across both tool envelopes — *a field appears on the wire only when it deviates from the default*. A trivial successful `ask` collapses to `{confidence, extracted_answer}`; a trivial `fetch_raw` to `{confidence, content_md}`.

### Changed

- **BREAKING — debug observability is a single `debug` sub-object.** `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, and `extraction` no longer appear as scattered top-level keys; they regroup into one `debug` object present only when the tool is called with `debug=True`. Applies to both `ask` and `fetch_raw`.
- **BREAKING — `tier` is deviation-only.** Omitted from the wire when its value is `raw` (the plain-HTTP default); present for `site_handler:*` / `jina` / `archive` / `browser`. Absence means a plain raw fetch.
- **BREAKING — `url` is redirect-only.** Omitted when the fetched URL equals the requested URL; present (carrying the final URL) only after an HTTP redirect or captcha-host rewrite.

### Removed

- **BREAKING — `original_url` deleted from both envelopes.** The caller already holds the requested URL; the surviving `url` (when present) is the deviation. The internal `FetchContext.original_url` field is gone too — a new `FetchContext.requested_url` captures the caller's input for the `url` deviation comparison.

## [0.13.0] — 2026-05-22

The `fetch-response-diet` change: `fetch_raw` / `FetchResponse` get the same lean wire treatment `ask` already received. A typical `fetch_raw` payload drops from ~22 keys (most of them `null` / `[]` / `{}`) to the handful that carry signal. The omit-empty + TSV serialization logic is now shared with `AskResponse` via a common helper.

### Changed

- **BREAKING — `fetch_raw` omits empty/null optional fields from the wire.** `title`, `byline`, `published`, `original_url`, `meta`, `links`, `headings`, `next_links`, `operator_hints`, `extraction`, and `extracted_answer` are absent when empty rather than serialized as `null` / `[]` / `{}`. On `fetch_raw` the LLM fields (`extraction`, `extracted_answer`) are always empty and simply disappear.
- **BREAKING — `status` is failure-only on `fetch_raw`.** Omitted when the fetch succeeds; present on `failed` / `partial`. Absence of `status` means success.
- **BREAKING — `narrative` / `diagnostics_summary` are failure-only on `fetch_raw`**; `started_at`, `total_ms`, `cache`, `tokens`, and `diagnostics` are `debug`-only. `tokens` joined the `debug` tier — the agent already holds `content_md` and can measure it.
- **BREAKING — `fetch_raw` `links` and `next_links` render as TSV blocks** (header row + one tab-separated row per entry) instead of JSON arrays of objects. `links` columns are `anchor` / `href` / `role`; `next_links` drops its `kind` column when every row is `drilldown`.

`ask` / `AskResponse` are unaffected — the wire shape was already lean; only its serializer implementation is refactored onto the shared `_prune_wire` helper.

## [0.12.0] — 2026-05-22

Follow-up to `ask-response-diet` (`ask-response-trim`): three further trims to the `ask` wire envelope.

### Changed

- **BREAKING — `extraction` is `debug`-only on `ask`.** The `extraction` object no longer appears on the default wire (it was `{"truncated": false}` — zero information — on nearly every response). When the extractor truncated an over-cap page, that now surfaces as an `operator_hint` with `code: "answer_truncated"`. Full extraction metadata still appears under `debug=True` and on LDD events.
- **BREAKING — `status` is failure-only on `ask`.** Omitted when the fetch succeeds; present on `failed` / `partial`. Absence of `status` means success. Joins `narrative` / `diagnostics_summary` in the failure-only tier.
- **BREAKING — `ask` `next_links` renders as a TSV block** (header row + one tab-separated row per link) instead of a JSON array of objects. The `kind` column is dropped when every link is `drilldown` and kept when the list mixes kinds.

`fetch_raw` / `FetchResponse` are unaffected by all three.

## [0.11.0] — 2026-05-22

The `ask-response-diet` change: the `ask` tool returns a lean answer-shaped
envelope instead of the page-shaped `FetchResponse`. Cuts ~70% of the wire
payload on a typical fetch — `ask` carries the extracted answer, not the page.

### Changed

- **BREAKING — `ask` returns the new `AskResponse` envelope.** `content_md`, `headings`, `tokens`, and `is_user_authored` are no longer on the `ask` surface. `content_md` (with the `headings` index) returns only when the caller passes the new `include_content=True` parameter. The page-shaped `FetchResponse` is unchanged and still returned by `fetch_raw`.
- **`ask` omits empty/null optional fields from the wire.** `byline`, `published`, `operator_hints`, `next_links`, `original_url`, and `meta` are absent when empty rather than serialized as `null` / `[]` / `{}`.
- **`ask` `narrative` / `diagnostics_summary` are failure-only**; `started_at`, `total_ms`, `cache`, and `diagnostics` are `debug`-only.
- **`ask` `extraction` metadata is slimmed to `truncated`** on the default wire path; full metadata (`model`, token counts, cost, latency, cache) is `debug`-only and stays on LDD events.
- **HN front page renders both URLs.** External-link stories now expose the article URL *and* the `news.ycombinator.com/item?id=` discussion URL in `content_md`.
- **`Heading` serializes as a compact `[level, text]` tuple** on the wire.

### Removed

- **BREAKING — `FetchResponse.fit_md` deleted.** Unconditionally `None` since v0.3; the pruning filter it reserved space for never shipped (superseded by JSON-synth and the LLM extractor). `TokenCounts.fit` removed with it.
- **`FetchResponse.is_user_authored` deleted** — a constant-`False` flag carrying no information.

### Added

- **Golden API-contract tests** (`tests/test_contracts.py` + `tests/contracts/`). Scenario goldens for the `ask` / `fetch_raw` wire envelopes, invoked through the in-process MCP client; `make bless-contracts` re-blesses after an intentional envelope change.

## [0.10.0] — 2026-05-19

Cycle bundles the harsh-test-session-fixes change + carry-over work that
accumulated on the branch (v0.39 a2kit migration, v0.7 link-discovery,
v0.8 cookie jar). All shipped together because they touched overlapping
files. v0.11 follow-up + post-release docs landed same day; see
sub-sections.

### Added (v0.10 harsh-test-session-fixes, 2026-05-19)

- **JSON-in-script extractor** (`src/a2web/packages/json_in_script.py`). Detects `__NEXT_DATA__`, `__NUXT_DATA__`, `application/ld+json`, and generic `application/json` script blobs; ranks LD-JSON `Product` / `Article` / `ItemList` (with >=3 populated fields) above framework app-state. Boundary type `JsonPayload`; package-independent. Synthesizes a markdown table at the a2web seam (`domain.py::json_to_markdown_rows`) — only known shapes are converted, do-no-harm on unknown JSON. JSON path runs only when trafilatura output is thin (<2KB OR <3 sentences) and replaces only when synthetic is >=2x original. Emits `json_synth` LDD events.
- **Paywall classifier — jina stub recognition.** Gate now recognizes jina-tier responses carrying `Target URL returned error 40[13]` stubs (NYT, WSJ shape) as `Verdict.paywall` instead of `Verdict.length_floor`. Archive escalation playbook now fires on these (previously a silent failure).
- **Thin-browser-response heuristic.** When the browser tier returns 200 OK with <1KB content from a host in the `JS_HEAVY_HOSTS` set (x.com, twitter.com, instagram.com, tiktok.com, trendyol.com, aliexpress.com — operator-extensible via `A2WEB_JS_HEAVY_HOSTS_EXTRA`), the gate downgrades to `length_floor` so escalation continues instead of returning a thin success.
- **Browser tier: scroll-on-thin retry.** After `wait_until="networkidle"`, if the first DOM capture is <4KB and the host is JS-heavy, scroll to bottom + wait 2s + re-snapshot. Keeps the larger capture. Never raises — page-eval errors fall back to the original. Emits `browser_scroll_retry` LDD events with outcome (larger / smaller / timeout).
- **`--max-content-chars` CLI flag + MCP kwarg on `ask`.** Caps content sent to the extractor LLM per-fetch. `None` (default) preserves the 100,000-char default. Reduces cost on pages dumping JSON app state — verified Hepsiburada drop 53,842 -> 11,964 prompt tokens (-78%) on a real benchmark.

### Changed (v0.10 — same cycle)

- **`camoufox` moved to baseline dependencies.** Previously `[browser]` extra; an uninstalled browser dep produced uncaught `ImportError` on the first browser-tier escalation. Install size grows ~150MB; first browser use still requires `python -m camoufox fetch` (runtime asset, not a wheel dep).
- **`playwright` dropped as explicit dep.** Transitive via camoufox, was a redundant pin.
- **`claude-agent-sdk` provider always passes explicit `system_prompt` (even empty).** SDK treats `None` as "load the claude_code preset" (~23k tokens of agentic system prompt). Explicit empty string opts out → drops ~12k tokens / ~50-77% per Haiku call. Verified on arXiv re-fetch ($0.0132 -> $0.0032).

### Added (v0.11, 2026-05-19 — small follow-up)

- **JSON synth now runs against browser-tier rendered DOM.** `_escalate_browser` previously installed browser output directly and re-gated without calling the JSON-in-script path. Now the synth runs against the rendered HTML (`browser_result.body`) before the re-gate, so sites that expose `__NEXT_DATA__` / LD-JSON only post-hydration get the same treatment as raw-tier SSR. Closes the v0.10 known limitation.

### Known Limitations (post-v0.11)

- **Camoufox subprocess stderr leak unfixed.** Spike (`docs/history/spike-camoufox-stderr-2026-05-19.md`) confirmed no supported knob in camoufox / playwright to redirect the Node child process's stderr without monkey-patching internals or `os.dup2`. Operators can redirect at shell level: `a2web ... 2>/tmp/a2web.stderr.log`.
- **Trendyol is a fingerprint-blocked target, not a CSR-architecture issue.** Diagnostic probe (camoufox headless against `/sr?q=...`): DOM contains zero products, no `__NEXT_DATA__`, no `__APOLLO_STATE__`, no state globals. Only analytics stubs and a custom "Mergen" loader. Trendyol detects headless via TLS/canvas/WebGL fingerprinting and serves an empty React shell intentionally. Same bucket as X.com / Instagram — out of scope without authenticated cookies or a non-headless approach. Building a site handler doesn't help (handler still needs a browser, browser still gets the empty shell).

### Added (v0.7 link-discovery — `next_links`, 2026-05-18)

- **New response field `FetchResponse.next_links: list[NextLink]`.** Up to 10 curated "what to fetch next" links per response. Each entry carries `anchor`, `url`, `reason` (one phrase, ≤80 chars), and `kind` (`drilldown` / `related` / `source`). Empty when no drilldown layer exists. Replaces the agent's "scan `links[]` and guess" pattern on listing-style pages.
- **Tier 1 — site handlers populate candidates from structured upstream payloads.**
  - **Reddit:** subreddit listings (`/r/<sub>/`, `/r/<sub>/hot/`, etc.) emit up to 10 permalinks with `reason="<score> score, <num_comments> comments"`. NSFW posts filtered when the subreddit's own `over18` flag is False.
  - **HN:** front page (`news.ycombinator.com/` and `/news`) — now matched (previously unmatched) — emits up to 10 stories; external-URL stories drill to the external link, text-only stories drill to the discussion page.
  - **arXiv:** category listings (`/list/<cat>/<window>`) — newly matched — emit up to 10 abs URLs with authors as `reason`.
  - **GitHub:** repo URLs emit up to 5 top open issues + 5 top open PRs as `kind="related"`. Issue/PR URLs return empty (terminal).
  - **Wikipedia:** up to 10 deduped outbound wikilinks parsed from Parsoid HTML as `kind="related"`. `File:`/`Category:` namespace links filtered. Same source-language host invariant.
- **Tier 2 — LLM curation in the `ask=` extraction call.** When `ask=` is set, the extraction prompt asks the LLM to also return up to 10 candidates inside a fenced JSON block (`` ```next_links ``` ``). Same provider call, no second round-trip. Boundary type `LlmNextLink` lives in `packages/llm_extract`; conversion to the domain `NextLink` happens at the a2web seam.
- **Hallucination defense.** LLM-supplied URLs are validated against the markdown content the LLM was given; absent URLs are dropped with an `extraction_drift` diagnostic. Handler-supplied URLs (Tier 1+2 re-rank) are exempt.
- **Tier 1+2 composition.** When both fire, the handler's candidate list is passed into the `ask=` prompt as context and the LLM re-ranks, filters, and rewrites each `reason` against the user's question. The LLM-returned list replaces (not unions with) the handler's list.
- **New tool parameter `next_links: bool = True`** on both `fetch` (ask=) and `fetch_raw` tools. Default-on; pass `False` on terminal fetches to suppress the field.
- **Out of scope (deferred):** alias-addressed URLs (`alias=` parameter for short-ID drilldown — only worth it once we measure full-URL pass-through as the actual bottleneck), server-side recursive drilldown (`follow_depth=N`).

### Added (v0.8 browser cookies, 2026-05-18)

- **Opt-in browser cookie source.** New settings `cookie_source: Literal["none","chrome","firefox"]` (default `none`), `cookie_profile: str` (default `Default`), `cookie_stale_after_hours: int` (default `24`). When enabled, a2web reads cookies from the user's local Chrome (macOS) or Firefox profile and threads them through the raw (curl_cffi) and browser (Playwright) tiers. Jina tier intentionally skips (third-party reader — would leak the session). Default `none` keeps the subsystem inert with zero observable change.
- **New tool + CLI: `a2web cookies refresh`.** Reads the configured browser profile, decrypts any encrypted values (macOS Keychain via `security` CLI + AES-GCM via `cryptography`), and atomically replaces the mirror inside the existing `SqliteResource` (new tables `a2web_cookies`, `cookies_meta`). The macOS Keychain prompt only appears here, not per fetch — Chrome can keep running.
- **Staleness signal as `OperatorHint(code="cookies_stale", ...)`.** Every fetch where the mirror is older than `cookie_stale_after_hours` (or has never been refreshed) gets one operator hint with the age + threshold + fix command. Agents can branch on `code == "cookies_stale"`. An `a2kit.ldd.event(CookiesStale(...))` is emitted in parallel for operator-facing observability.
- **`OperatorHint` docstring updated.** The `code` field is now explicitly an agent-readable branch point. Existing codes (`llm_unavailable`, `browser_unavailable`, `captcha_redirect`) already served both audiences; the prior "agents never read these" claim was descriptive of original intent, not a constraint. Schema unchanged.
- **`cryptography` promoted to direct dependency** (already transitive via curl_cffi). Used only for PBKDF2-HMAC-SHA1 and AES-GCM decrypt in the Chrome reader.
- **Hand-written cookie readers under `packages/cookie_store/`.** No third-party cookie-extraction library — `rookiepy` and `browser-cookie3` both audited YELLOW (dormant single-maintainer projects, no PyPI Trusted Publishing). Our macOS Chrome path is ~120 LOC; Firefox is plaintext sqlite. Less third-party trust surface, fewer moving parts on Chrome encryption changes.
- **Redaction discipline.** Cookie values never appear in LDD event payloads, structlog records, or diagnostic rows. Helper `redact_cookie_for_event(cookie)` returns `{name, host_key, path, value_length}`. The `CookiesAttached` event carries cookie *names* only.
- **Out of scope (v0.8):** LDD severity levels (upstream a2kit ask — emit at single level today, swap to `warn` when supported); Camoufox `user_data_dir=` profile inheritance; Linux/Windows Chrome; multi-profile merge; automatic background refresh; Safari / Edge / Brave / Arc.

### Changed (a2kit v0.38 → v0.39 migration, 2026-05-16)

- **a2kit pin: v0.38.0 → v0.39.0.** Adopts round-10 friction fixes shipped upstream on 2026-05-16. No wire-surface change; all 414 tests green at 89% coverage.
- **Drop `ctx: a2kit.ToolContext` from `WebRouter.fetch`.** v0.39 binds ambient ctx unconditionally inside any framework dispatch — the `ctx` parameter is no longer needed in tools that don't read ctx in the body. `del ctx` is gone.
- **Drop `await sqlite._ensure()` from `_check_sqlite`.** v0.39 `OPERATIONAL_CONTRACTS Q-HealthChecks` pins the contract: kwarg resolution enters the resource. The health probe receiving `sqlite` is the readiness assertion; no internal probe call needed. The surrounding try/except is gone too — sqlite open-time failures are catastrophic and should crash the probe loudly, not soften to a "degraded" check.
- **`conftest.py` helpers swapped to `a2kit.testing.*`:**
  - `lazy_of(value)` → `a2kit.testing.lazy(value)` (deleted from conftest; tests import directly).
  - Local `_ambient_ldd` autouse fixture → re-export `a2kit.testing.ambient_for_tests` under `pytest.fixture(autouse=True)` using the documented `__wrapped__` unwrap pattern.
  - `make_default_state(...)` kept as-is — it's the deliberate "AppState without an app" test seam (not boilerplate; `a2kit.testing.resolve` is for the orthogonal "AppState inside an app scope" use case, which a2web does not currently use).
- **Round-10 Friction E retracted.** v0.39 shipped `Lazy[T]` recognition in factory parameters (closes a real spec drift), enabling `AppState` to absorb `Lazy[BrowserPool]` / `Lazy[LlmExtractorResource]` as fields. a2web reviewed and **did not adopt** — the architectural split (`AppState` for always-on data, separate `Lazy[T]` DI kwargs at the tool seam for orthogonal services) is correct design, not friction. Mixing services into the data bundle would blur the seam and force tests to fake services they don't exercise. Tool signature stays at three injectables (`state`, `browser_pool`, `llm_extractor`).
- **CLAUDE.md updated** to reflect v0.39 invariants: unconditional ambient ctx; no `_ensure()` in health bodies; canonical `a2kit.testing.*` import path; `ToolContext` is now a `@runtime_checkable typing.Protocol`.

### Added (v0.7 MCP feature wave, 2026-05-15)

- **Reddit search URL handler.** `RedditHandler` now claims `/r/<sub>/search/?q=...` and unscoped `/search/?q=...`. Rewrites to `.json`, renders a terse markdown list (`# Search: <q>` + `## Results (N)` + per-result `**title** (r/sub · u/author, score N, M comments, age) <permalink>`). Caps at 25 entries. Closes the highest-value research gap from v0.6 feedback (search was 100% fail across raw/jina/archive previously).
- **Captcha-host pre-routing.** Google/Bing `/search?q=...` URLs are rewritten to `https://duckduckgo.com/html/?q=<urlencoded-q>` before tier dispatch. New pure function `a2web.domain.rewrite_captcha_host(url)` is the single source of truth. `FetchResponse.original_url` preserves the URL the caller originally asked for so diagnostics stay honest. Non-search paths on captcha hosts (Maps, Drive, Images) pass through unchanged.
- **`FetchResponse.original_url` field** — set when an upfront URL rewrite occurred (e.g. captcha → DDG); `None` when no rewrite. `response.url` always reflects the URL actually fetched.

### Breaking (v0.7 LLM extras → core, 2026-05-15)

- **`[llm]` install extra REMOVED.** `pip install a2web[llm]` now errors loudly. `anthropic` + `claude-agent-sdk` are baseline deps. `--ask` works out of the box. Install size jumps from ~30MB to ~240MB (claude-agent-sdk bundles ~210MB Claude Code binary in `_bundled/`) — the bundling is intentional: most a2web callers run inside Claude Code and rely on the OAuth piggyback. Migration: drop `[llm]` from your install command.
- `LLMNotAvailable` only fires now for "no API key AND no Claude Code OAuth session" — the "SDK not installed" branch is dead. Operator hints updated.

### Changed (a2kit v0.32 → v0.38 migration, 2026-05-15)

- **a2kit pin: v0.32.0 → v0.38.0.** Six upstream releases on 2026-05-13 → 2026-05-15 closed feedback rounds 7, 8, and 9 — most importantly, the round-8 MCP `ctx`-binding bug that 100%-broke `mcp__a2web__fetch` in a2web v0.6.0. POC-verified: tool returns structured `FetchResponse` over MCP stdio, LDD events stream as `notifications/message` on the wire, no `TypeError`.
- **DI re-architected for v0.36+ native shape.** Each long-lived resource is now its own provider via `app.provide(...)`. Per-resource singletons enter lazily on first resolution (lazy first-use, replaces eager `async with app:` entry). Resources expose `__aenter__`/`__aexit__` as thin wrappers around existing idempotent `_ensure()` / `close()` methods — both surfaces kept; framework drives the CM protocol while internal lazy callers keep using `_ensure()`.
- **`AppState` slimmed to always-on resources** (settings, breakers, proxy_pool, sqlite). `browser_pool` and `llm_extractor` moved off `AppState` — they're independently provided and surfaced at the tool seam via `Lazy[T]`. The orchestrator awaits the Lazy callable only at the consuming phase (`_escalate_browser` for browser, `_phase_extract_answer` for LLM). Browser pool never enters on the happy path; LLM resource never enters when `ask=` is not passed.
- **`server.py` rewritten** for v0.38: no `@asynccontextmanager` lifespan, no `lifespan=` kwarg, no `health_tool=`. Imperative per-resource `app.provide(...)` registrations in deps-first order (Settings → Breakers → ProxyPool → SqliteResource → BrowserPool → LlmExtractor → AppState). Named factory functions; no lambdas.
- **`@a2kit.read(idempotent=True)`** dropped from `routers.py` per v0.33 — reads are spec-idempotent.
- **`Router.slug`** declaration switched from `ClassVar[str] = "web"` to plain `slug = "web"` per v0.36's `slug: str` instance-variable annotation.
- **BrowserTier signature** gains `pool: BrowserPool | None = None`. The orchestrator's `_escalate_browser` resolves `Lazy[BrowserPool]` and threads it.
- **`Tier` protocol** gains `**kwargs: Any` for protocol-uniform dispatch.
- **`@app.health_check`** signature changed from `(state: AppState)` to `(sqlite: SqliteResource)` — DI resolves the resource directly, the framework enters it for the probe.

### Removed (a2kit v0.32 → v0.38 migration)

- **`@asynccontextmanager` lifespan** in `server.py`. `App(lifespan=cm)` was removed in a2kit v0.35; resource lifecycle now flows through each resource's `__aenter__`/`__aexit__`.
- **`app.singleton(...)`** — replaced by `app.provide(...)` in v0.36.
- **Eager-warm-on-startup pattern** — v0.36 made all resource entry lazy. Sqlite misconfig now surfaces as a structured `ToolError` envelope on the first fetch instead of crashing at server boot. `a2web health` still warms sqlite eagerly via the health-check path.
- **`browser_pool: BrowserPool`** and **`llm_extractor: LlmExtractorResource`** fields from `AppState`. They live as independent providers, surfaced via `Lazy[T]` at the tool seam.

---

### Previously changed (a2kit v0.28.0 → v0.32.0 migration, 2026-05-13)

- **a2kit pin: v0.28.0 → v0.32.0.** Six upstream releases on 2026-05-12 → 2026-05-13 closed every open ergonomic gap from a2web feedback rounds 5 + 6 plus fixed the FastMCP 3.x compatibility break that was blocking `a2web serve` as a global Claude Code MCP server.
- **Lifespan over lifecycle hooks.** `@app.on_startup` / `@app.on_shutdown` (removed in a2kit v0.31) replaced by a single `lifespan=` async context manager in `server.py`. Pre-`yield` warms sqlite (fail-fast); `finally` block closes resources LIFO with each close error-isolated.
- **Explicit Router contract.** `WebRouter` declares `slug = "web"` and `tools = (fetch,)` ClassVars per a2kit v0.31's removal of `_derive_slug` and the `dir(self)` walk.
- **`a2kit.Param` → `pydantic.Field`.** Six call sites in `routers.py` migrated. The `Param` wrapper was removed in a2kit v0.31 (was a one-line forwarder); explicit `Annotated[T, pydantic.Field(description="...")]` is now the canonical form.
- **Ambient `ctx` for LDD primitives.** Per a2kit v0.29.0+, `a2kit.ldd.event(...)` reads ctx from a `ContextVar` set by the dispatcher. Stripped `ctx` kwarg from 9 phase / helper signatures in `fetcher.py` and 16 `a2kit.ldd.event(ctx, ...)` call sites. The tool body still declares `ctx: a2kit.ToolContext` for the dispatcher to bind ambient (per OPERATIONAL_CONTRACTS Q8).
- **`null_context()` import + branch removed** from `fetcher.py::fetch()`.
- **LDD import path** in `events/sinks.py`: `from a2kit.ldd import LddEmission` → `from a2kit.packages.ldd import LddEmission` (v0.32 namespace trim).

### Added

- **`tests/conftest.py::_ambient_ldd` autouse fixture.** Wraps every test in `ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)` so direct `fetch()` calls from tests don't raise `AmbientContextMissing` (a2kit v0.29+ requires LDD primitives to run inside an active dispatch scope).

### Removed

- **`SqliteResource` / `BrowserPool` / `LlmExtractorResource` close-from-`@on_shutdown` ceremony.** Cleanup now lives inside the App lifespan's `finally` block.

### Notes

- Free wins inherited on the bump: CLI cold-start −75% (v0.27.1/2), WARN_ONCE on five framework-internal silent-swallow sites (v0.31.0), `@a2kit.list_` parameter parity (v0.32.0).
- The docstring `Args:` auto-pull shipped in a2kit v0.29.0 was reverted in v0.30.0 — our round-5 caution about silent description-loss drift was vindicated by upstream removal within 24 hours of release. Param descriptions stay in `Annotated[T, pydantic.Field(description=...)]`.
- Two original round-3 wishes (streaming response API, `@a2kit.read(timeout="60s")` decorator kwarg) remain deferred — see `docs/history/A2KIT_WISHES_DEFERRED.md` along with three new round-7 candidates surfaced during the migration (singleton teardown kwarg, `tools` tuple completeness lint, sharper `AmbientContextMissing` message for no-ctx tools).
- Acceptance: `make check` green (387 tests, 89.45% coverage); `claude mcp list` shows `a2web: ✓ Connected`; CLI smokes (example.com, news.ycombinator.com, arxiv.org) return populated `FetchResponse` with diagnostics.

## [0.6.0] - 2026-05-12

Post-v0.5.0 simplification sweep. The codebase finished v0.5.0 still
carrying a per-domain seam-shim layer (`cache/`, `gate/`, `proxy/`,
`log/`, `extract/`, `llm/`) — one-line re-exports preserving import
paths from before the packages migration. This sweep deletes them
outright; consumer compat is explicitly disclaimed pre-1.0.

### Structural

- **Seam-shim layer nuked.** Six per-domain seam directories (~580 LOC
  of one-line re-exports) deleted. Surviving domain-coupled glue
  (`compute_profile_hash`, `is_live_only`, `log_from_response`) lives
  in `domain.py`. The AppSettings-aware `LlmExtractorResource` lives
  in `llm_resource.py`. `llm_eval/` promoted to top level.
- **Single-purpose packages flattened to `.py` files.** `browser_pool/`,
  `block_detector/`, `ndjson_log/`, `http_cache/`, `proxy_routing/`,
  `content_extract/` — each was a folder containing one or two flat
  files. Now they're single `.py` modules. `llm_extract/` stays a
  folder for its multi-author surface.
- **`fetcher.py` split.** Response builders (`_confidence_for`,
  `_build_narrative`, `_build_diagnostics_summary`, `_wrap_content_md`,
  `build_response`) moved to `fetcher_response.py` (169 LOC).
  `fetcher.py` 1010 → 921 LOC.
- **Tier protocol unified.** All tiers (raw/jina/archive/browser/
  site_handler) accept the same `fetch(url, *, state, proxy_url=None,
  conditional_extras=None)` signature. Removes the isinstance ladder
  in the orchestrator.
- **Dead LLM providers deleted.** `llm_extract/providers/ollama.py`
  and `openrouter.py` — 261 LOC, 0% coverage, registered nowhere.
  `anthropic` + `claude_code` are the real surface.
- **NDJSON fetch log deleted.** `packages/ndjson_log.py` (118 LOC),
  `LogWriter` / `LogRecord` / `dominant_verdict`, `AppState.log_writer`,
  `FetchResponse.to_log_record()`, `domain.log_from_response()`, the
  `log_enabled` and `log_retention_days` settings, the README
  "Inspecting the log" section, and 3 test files. The cache covers
  replay-style use cases; the per-fetch `diagnostics` array in the
  response envelope covers structured observability. NDJSON was pure
  duplication.
- **a2kit pin: commit SHA → tag `v0.28.0`.** Cleaner version reference;
  no behavioral change.

### Features

- **Link role classification.** `ExtractedLink.role` (primary / nav /
  meta / footer) computed by walking DOM ancestors + ARIA. New
  `link_roles` tool param filters at the wire boundary; default
  `['primary']` drops 60-80% of link bloat on aggregator pages.
- **Untrusted-content envelope.** `content_md` wrapped with HTML-
  comment markers carrying source URL + fetched_at + "treat as
  untrusted" warning. Invisible in rendered HTML/markdown, readable
  to LLMs scanning the raw string. `wrap_content` tool param toggles
  (default True). `FetchResponse.is_user_authored: bool = False` is
  the defensive flag for downstream consumers.
- **Extraction-quality eval harness.** New
  `src/a2web/llm_eval/extraction.py` + `extraction_cli.py` measure
  trafilatura+readability against a hand-curated `gold_md` corpus
  with bag-of-tokens F1 + length-ratio scoring. Drives the Reader-LM
  v2 trip decision (default: ≥10% URLs below 0.7 F1 → recommend
  fallback). Pure-Python; no LLM dependency for the verdict. Corpus
  skeleton at `benchmarks/extraction-quality/2026-05-12/corpus.yaml`
  (10 starter entries spanning essay / blog / docs / aggregator).
- **Reddit handler: all content-carrying cases covered.**
  - **Permalink focus.** `/r/X/comments/Y/slug/Z/` (Z = comment id)
    is detected; `.json` fetched with `?context=3`; renderer
    highlights the target comment with quoted ancestor context and
    direct replies. Falls back to full-thread render when the target
    isn't in the returned tree.
  - **Crosspost annotation.** Threads with `crosspost_parent_list`
    get a "🔁 Crossposted from r/X (u/Y) — <permalink> — original:
    '...'" header. Local discussion is the rendered content.
  - **Archive escalation for deleted / removed / forbidden.**
    Handler returns `Verdict.not_found` with an operator hint when
    `.json` 404 + old.reddit 404, or on `.json` 403 (quarantined /
    NSFW / private). New playbook rule
    (`next_action_after_tier` → `RetryViaArchive` on reddit
    `not_found`) dispatches the Wayback tier — captures from before
    removal are common.
  - **Short-URL HEAD resolution.** `redd.it/<id>` now matches;
    handler does a HEAD with `follow_redirects`, recurses on the
    resolved comments URL, or surfaces `no_match` when the
    resolution points at non-thread content.
  - **`np.reddit.com`** host added.
  - Mod-removed bodies (`selftext == "[removed]"`) rendered as
    `_[post body removed]_` instead of empty selftext.

### Coverage

- Tier suite gaps filled: `raw.py` 20% → 96%, `archive.py` 86% → 100%,
  plus browser/jina/site_handler closeouts.
- Reddit handler coverage: 13 new tests (permalink detection +
  focused render, crosspost annotation, removed-body marker,
  archive-escalation signal on 404 + 403, short-URL HEAD resolution,
  and non-thread no_match, playbook escalation rule).
- Test count 320 → 387; coverage 85.90% → 89.71%
  (NDJSON suite removed; extraction-eval + reddit suites added).

### Docs

- `docs/history/A2KIT_FEEDBACK_v0.27.md` — 358-line feedback doc on four
  ergonomic ceilings that would unlock another ~175 LOC of deletion
  upstream (async resources, ambient ctx threading, test resource
  override, Param verbosity).
- `BACKLOG.md` updated to match reality — removed stale references to
  seam shims, marked twitter handler as shipped (v0.3 Nitter).
- `CLAUDE.md` refreshed for the radical clean-up.

## [0.5.0] - 2026-05-12

Simplification + structural cleanup release. Three themes:

1. **a2kit v0.27.2 migration** (step 1). Resource pattern for every
   long-lived async resource — sync `__init__`, internal lock, lazy
   `_ensure()`, idempotent `close()`. Non-Optional AppState. DI-aware
   lifecycle hooks. Typed-event direct emit. ~-95 LOC.
2. **Seven in-tree microsofware packages** (steps 2, 4–9). New
   `src/a2web/packages/` directory with a strict contract: no
   `a2web.<domain>` imports allowed inside. Promoted: `browser_pool`,
   `block_detector`, `ndjson_log`, `http_cache`, `proxy_routing`,
   `llm_extract`, `content_extract`. The `test_packages_independence`
   invariant fails CI on drift.
3. **Fetcher decomposition** (step 10). The 180-LOC tier loop is
   split into a coordinator + three named helpers driven by an
   `_AfterTier` enum. Shared tier-emit and regate-after-escalation
   helpers centralize previously-duplicated boilerplate.

Plus a micro-cleanups bundle (step 3) that collapsed `*_hint` fields
to a single `fc.operator_hints` accumulator, deleted YAGNI parameter
stubs, dropped non-loadbearing `@runtime_checkable` decorators, and
moved `_resolve_env` to a pydantic validator.

320 tests passing at 85.90% coverage on release.

### v0.5 step 10 — fetcher decomposition (2026-05-12)

Plan: `openspec/changes/archive/2026-05-12-v0.5-fetcher-decomposition/`.

- **Step 10a — `_emit_tier_started` / `_emit_tier_ended` helpers.** The
  TierStarted/TierEnded emission pattern was duplicated at three sites
  (tier loop, archive escalation, browser escalation). Centralized
  into two small async helpers above the archive section. Removes a
  stale in-band `tier_dur_ms` calc — TierEnded.dur_ms and Diagnostic
  share exactly one source now.
- **Step 10b — split `_phase_tier_loop` into named helpers.** The
  180-LOC tier loop now coordinates over three named helpers with an
  `_AfterTier` enum driving control flow: `_install_won_tier`,
  `_install_archive_payload`, `_apply_after_tier_action`. Outer loop
  body drops from ~150 to ~85 LOC and reads top-to-bottom without
  flag variables (`restart_loop`, `archive_break_payload`).
- **Step 10c — `_regate_after_escalation` helper.** Browser and
  gate-path archive escalators both ran the same 7-line regate block
  after installing pre-rendered content; now one helper, one source
  of truth.

### v0.5 step 9 — content_extract promoted to packages/ (2026-05-12)

Closes Stage 2b — the original deferred-with-reason item that needed
boundary types before it could move.

- **`packages/content_extract/`** — seventh in-tree microsofware. Owns
  the trafilatura wrapper (`extract_markdown`) + OG/Twitter/JSON-LD
  metadata parser (`parse_metadata`). Boundary types `ExtractedHeading`
  / `ExtractedLink` / `ExtractedContent` are frozen `dataclass(slots=True)`,
  package-owned. Zero `a2web.<domain>` imports.
- **`extract/trafilatura_ext.py` reduced to seam.** Calls the package
  and maps `ExtractedHeading` → `models.Heading`, `ExtractedLink` →
  `models.Link`. Preserves the existing `ExtractResult` shape so
  `fetcher.py` and tests need zero changes.
- **`extract/metadata.py` reduced to one-line re-export.**
- `test_packages_independence` auto-validates the new module.

### v0.5 step 8 — llm_extract promoted to packages/ (2026-05-12)

- **`packages/llm_extract/`** — sixth in-tree microsofware. Owns the
  whole LLM extraction + judge surface: `Extractor`, `ModelSpec`,
  `ExtractionResult`, `ExtractionCache` + `hash_text`, `Judge` +
  `JudgeVerdict` + `JudgeParseError`, `PromptTemplate` + the
  WEBFETCH/TERSE/JUDGE prompts, `LLMNotAvailable`, plus the four
  providers (`anthropic`, `claude_code`, `openrouter`, `ollama`) and
  `Provider` Protocol. Zero `a2web.<domain>` imports.
- **`llm/*.py` reduced to seam shims.** `llm/__init__.py` re-exports
  the package's public surface. `llm/{cache,errors,extractor,judge,prompts}.py`
  and `llm/providers/*.py` are one-line re-exports each. Existing test
  imports (`from a2web.llm.extractor import Extractor, ModelSpec`,
  `from a2web.llm.providers.claude_code import ClaudeCodeProvider`, etc.)
  keep working unmodified.
- **`llm/resource.py` stays at the seam.** `LlmExtractorResource`
  remains the domain-coupled wiring — it pulls provider selection from
  `AppSettings.llm_provider`, plumbs `SqliteResource` into
  `ExtractionCache`, and gates construction on the optional `[llm]`
  install extra.
- **`llm/eval/` stays at the seam.** The eval harness imports
  `AppSettings`, `FetchResponse`, `build_state` — domain-coupled by
  definition.
- `test_packages_independence` auto-validates all new modules.

### v0.5 step 7 — proxy_routing promoted to packages/ (2026-05-12)

- **`packages/proxy_routing/`** — fifth in-tree microsofware. Owns
  `ResolvedRoute`, `ProxyHandle`, `ProxyPool`, `resolve_route`, plus
  Protocol-shaped boundary types `ProxyEntryShape` / `RouteRuleShape`.
  Zero `a2web.<domain>` imports — the package reads route/proxy data
  via the Protocols, so any duck-typed source (pydantic, dataclass)
  works without conversion.
- **`proxy/policy.py` + `proxy/pool.py` reduced to seams.**
  `resolve_route(host, tier, AppSettings)` forwards `settings.routes` /
  `settings.proxies` into the package. `ProxyPool(settings=...)` is a
  subclass shim with a back-compat `.settings` property. Existing test
  and consumer imports (`from a2web.proxy.policy import resolve_route`,
  `from a2web.proxy.pool import ProxyPool, ProxyHandle`) unchanged.
- `test_packages_independence` auto-validates the new module.

### v0.5 step 6 — http_cache promoted to packages/ (2026-05-12)

- **`packages/http_cache/`** — fourth in-tree microsofware. Owns
  `CacheRow` (boundary type), `SqliteResource` (lazy aiosqlite + schema
  bootstrap), `cache_get`/`cache_put` primitives, `open_sqlite_with_schema`,
  `cache_dir`. Zero `a2web.<domain>` imports — the package takes a
  `db_path: Path | None` instead of `AppSettings`.
- **`cache/sqlite_cache.py` reduced to seam.** Keeps the domain-coupled
  bits: `compute_profile_hash(AppSettings)`, `is_live_only(url,
  AppSettings)`, and a `SqliteResource(settings)` subclass shim that
  forwards to the package. Re-exports the package primitives so
  existing imports (`from a2web.cache.sqlite_cache import …`) keep
  working unmodified.
- `test_packages_independence` auto-validates the new module.

### v0.5 step 5 — ndjson_log promoted to packages/ (2026-05-12)

- **`packages/ndjson_log/`** — third in-tree microsofware. Owns
  `LogRecord` (boundary type), `LogWriter` (lazy-open + size-based
  rotation + gzip on rollover), `paths.py`, `rotation.py`. Zero
  `a2web.<domain>` imports.
- **`log/*.py` reduced to seam shims.** `log/record.py` keeps the
  domain-coupled `from_response(FetchResponse) -> LogRecord` adapter;
  `log/paths.py` / `log/writer.py` / `log/rotation.py` are one-line
  re-exports from the package. Test imports (`from a2web.log.record
  import LogRecord, from_response`, etc.) keep working unmodified.
- `test_packages_independence` auto-validates the new module.

### v0.5 step 4 — block_detector promoted to packages/ (2026-05-12)

- **`packages/block_detector.py`** — second in-tree microsofware after
  `browser_pool`. Defines package-local `BlockVerdict` enum + `BlockResult`
  dataclass; no `a2web.<domain>` imports. Values intentionally match
  `a2web.models.Verdict` strings so the seam adapter is a one-liner.
- **`gate/block_detector.py` → thin seam adapter** (~52 LOC). Imports the
  package, calls it, maps `BlockVerdict → Verdict`, returns `GateResult`
  for the pipeline. Public signature (`evaluate(...) -> GateResult`,
  `LENGTH_FLOOR` re-export) unchanged — fetcher and gate tests pass
  unmodified.
- `test_packages_independence` invariant validates the new module
  automatically.

### v0.5 step 3 — micro-cleanups bundle (2026-05-12)

- **Three `*_hint` fields collapsed to `fc.operator_hints` accumulator.**
  Anywhere in the pipeline can append; `_build_response` consumes the list
  uniformly. Removes the pattern-duplication smell across `llm_unavailable_hint`
  / `browser_unavailable_hint` / any future "X unavailable" field.
- **`del settings` / `del ms` reserved-for-future stubs deleted.** Three
  parameters removed across `playbook.next_action_after_gate`,
  `playbook.next_action_after_tier`, and `ProxyPool.report`. YAGNI code
  gone.
- **`@runtime_checkable` dropped on `Tier` and `Handler` protocols** (kept
  on `Provider` and `EvalSystem` where contract tests rely on isinstance
  against the Protocol). Less decorator noise; static typing covers the
  rest.
- **`_resolve_env` moved into `ProxyEntry.url` pydantic validator.** Env
  interpolation (`${VAR}` → `os.environ[VAR]`) happens once at settings
  load instead of repeatedly at proxy-resolution time. `proxy/policy.py`
  and `proxy/pool.py` both gain trivial code (read `entry.url` directly).
  Kills a private-import `# type: ignore[attr-defined]` in `pool.py`.
- **`record_from_response` alias replaced** by `FetchResponse.to_log_record()`
  method. Lives next to the model it converts from. Caller goes from
  `await state.log_writer.write_record(record_from_response(response, input_url=url))`
  to `await state.log_writer.write_record(response.to_log_record(input_url=url))`.

### v0.5 step 2 — `packages/` scaffold (2026-05-12)

- **New `src/a2web/packages/` directory** with the microsofware contract:
  modules under `packages/` MUST NOT import from `a2web.<domain>`. Boundary
  types are owned by the package itself. Lives next to a `README.md` that
  documents the rule.
- **`tests/test_packages_independence.py`** — load-bearing invariant test
  that walks every `.py` under `packages/` and asserts zero domain imports.
  Catches drift in CI.
- **`browser_pool.py` relocated** from `src/a2web/browser/pool.py` to
  `src/a2web/packages/browser_pool.py`. First in-tree microsofware,
  validates the scaffold contract.

### v0.5 step 1 — a2kit v0.27.2 migration (2026-05-12)

**Resource pattern adopted (a2kit v0.27 canonical).** Every long-lived async
resource is now a class with sync `__init__`, internal `asyncio.Lock`, lazy
`_ensure()`, and idempotent `close()`. AppState fields are all non-Optional;
locks no longer leak to state.

- **New `SqliteResource`** wrapping `aiosqlite.Connection` + schema bootstrap.
  Replaces the previous Optional `state.sqlite` + startup-hook-opens dance.
- **New `LlmExtractorResource`** wrapping the Extractor + provider auto/anthropic
  fallback + ExtractionCache wiring. Returns `None` on permanent unavailability;
  caller branches and populates an operator hint without retrying construction.
- **`BrowserPool._ensure()`** — idempotent under internal lock with
  double-check. `start()` retained as deprecated alias.
- **DI-aware lifecycle hooks.** `@app.on_startup` / `@app.on_shutdown` take
  typed kwargs (`state: AppState`) — no `container.resolve(...)` ceremony,
  no `connection=None`, no `_app: a2kit.App` parameter.
- **Typed-event direct emit** via `await a2kit.ldd.event(ctx, EventInstance(...))`
  (a2kit 0.26.1). The `_emit` + `_event_payload` adapter shim is gone (~30 LOC).
- **`a2kit.testing.null_context()`** swapped in for direct `fetch(ctx=None)`
  callers; phase functions take non-Optional `ctx: a2kit.ToolContext`.
- **`Param("desc")` positional shorthand** on the URL parameter.

Closes all four gaps + both soft notes from `docs/history/A2KIT_FEEDBACK_v0.26.md`.
Net ~-95 LOC across `state.py` + `server.py` + `fetcher.py` (state.py alone
drops from 136 → 63 LOC).

### Added

- **`ClaudeCodeProvider`** — runs prompts through the user's Claude Code
  OS session via `claude-agent-sdk`. No `ANTHROPIC_API_KEY` required:
  inherits whatever the local `claude` CLI is logged into (OAuth
  subscription or API key). Implements the same `Provider` Protocol as
  `AnthropicProvider`, so the Extractor and Judge accept it
  transparently. Tools are disabled and `max_turns=1` so the model
  produces a single text completion — no file edits or MCP calls.

- **`llm_provider="auto"` default** — `AppState.ensure_llm_extractor`
  now tries `ClaudeCodeProvider` first and falls back to
  `AnthropicProvider` when the SDK or CLI is missing. Set
  `A2WEB_LLM_PROVIDER=anthropic` to skip the OS-session path and use
  the API key directly, or `A2WEB_LLM_PROVIDER=claude-code` to require
  it.

- **`claude-agent-sdk` added to the `[llm]` extra.** Installing
  `a2web[llm]` now ships both `anthropic` (for the API-key path) and
  `claude-agent-sdk` (for the OS-session path).

- **`benchmarks/.../judge.py`** prefers `ClaudeCodeProvider` by default;
  set `A2WEB_BENCH_PROVIDER=anthropic` to force the API-key path.

## [0.4.0] - 2026-05-11

The `a2web.llm` module — optional server-side LLM extraction +
LLM-as-judge primitive + matrix eval suite. Gated by the `[llm]` install
extra; bare `pip install a2web` is unchanged.

The headline trick (research/123): Claude Code's WebFetch runs Haiku
over the fetched markdown server-side and returns only the answer.
v0.4 makes a2web do the same — caller passes `ask=...` to the `fetch`
tool, gets back a tiny `extracted_answer` envelope. Calling agent's
context stays tiny.

### Added

- **`ask=` parameter on the `fetch` tool.** When set, a2web invokes an
  LLM extractor server-side after the existing content extract phase
  and populates `FetchResponse.extracted_answer` + `extraction`
  metadata. Default model is `claude-haiku-4-5-20251001` (matches
  Claude Code's WebFetch sub-call per research/123). Graceful when
  the `[llm]` extra is missing or `ANTHROPIC_API_KEY` is unset — the
  fetch still succeeds, `extracted_answer` stays None, and an operator
  hint with code `llm_unavailable` surfaces the actionable reason.

- **`src/a2web/llm/` module** — Extractor, Judge, prompts, providers,
  cache. Public surface:
  - `Extractor(provider, model, template, cache?)` — wraps a Provider
    with a frozen prompt template; returns `ExtractionResult`.
  - `Judge(provider, model)` — LLM-as-judge over (task, criteria,
    answer) tuples; returns `JudgeVerdict` (scores, overall, reached,
    reasoning, cost). Robust JSON parsing tolerates markdown fences
    and prose wrappers; `JudgeParseError` carries raw text on failure.
  - `Provider` Protocol + `AnthropicProvider` reference implementation
    with hardcoded pricing table for Haiku 4.5 / Sonnet 4.6 / Opus 4.7
    (populates `cost_usd`). Empty system content + thinking_disabled
    are first-class for WebFetch behavioral parity.
  - `PromptTemplate` frozen dataclasses: `WEBFETCH_DEFAULT_V1`
    (byte-for-byte the `Rb9` template from Claude Code's binary),
    `TERSE_V1` (compact variant), `JUDGE_V1` (strict-JSON judge).
  - `ExtractionCache` — sqlite-backed (content_hash, ask_hash,
    model_id, template_name) → answer LRU. Mirrors WebFetch's 15-min
    TTL (`sg5 = 900000ms`). Lives in the same sqlite file as the HTTP
    cache; schema created lazily so the no-extra install is unaffected.

- **`src/a2web/llm/eval/` module + `make eval`** — deterministic eval
  harness. EvalSuite runs (corpus × systems × judge) with bounded
  concurrency, writes dated `eval/runs/<timestamp>/` directories
  containing `results.tsv`, `manifest.json`, `leaderboard.md`,
  `cost.md`, `findings.md`, `corpus.frozen.yaml`, and per-cell trace
  dirs. Three systems out of the box:
  - `WebFetchBaseline` — faithful local reproduction of Claude Code
    WebFetch using the binary-extracted constants. Runs offline (no
    Claude Code session needed). Documented divergences: no domain
    preflight, no cross-host redirect break, no preapproved-host fast
    path, markdownify ≠ Turndown.
  - `A2WebDetail` — a2web `fetch(url)` without `ask=`; measures the
    "agent reads envelope, extracts in its own context" path.
  - `A2WebExtract` — a2web `fetch(url, ask=...)`; matches WebFetch's
    answer-only shape via server-side extraction.

- **`[llm]` install extra** — adds `anthropic`, `openai` (reserved for
  v0.5 OpenRouter), and `markdownify` (Turndown neighbor for
  WebFetchBaseline). `pip install a2web[llm]` enables `ask=` and the
  eval suite.

- **New Makefile targets**: `make eval` (full matrix), `make
  eval-baseline` (WebFetchBaseline only, drift detection), `make
  eval-detail` (a2web systems only, engine-only validation).

- **New settings on `AppSettings`**: `llm_provider` ("anthropic" in
  v0.4), `llm_model` (default `claude-haiku-4-5-20251001`),
  `llm_api_key_env`, `extraction_max_chars` (default 100,000 — matches
  WebFetch's `BD_`), `extraction_cache_ttl_s` (default 900 — matches
  WebFetch's `sg5`).

- **New models**: `ExtractionMeta` carrying per-fetch LLM metadata
  (model, template_name, tokens, cost, latency, cache_hit, truncated).
  `FetchResponse.extracted_answer: str | None` and `extraction:
  ExtractionMeta | None` (both default None — no schema change for
  callers not using `ask=`).

### Tests

- 50+ new scenarios across `test_llm_module.py`, `test_llm_judge.py`,
  `test_llm_eval_systems.py`, `test_llm_eval_suite.py`,
  `test_llm_cache.py`, `test_fetcher_ask.py`. All isolated via mock
  providers + in-memory sqlite + httpx MockTransport — no real API
  calls in the test suite.

### Migration notes

- Bare `pip install a2web` keeps working unchanged; `ask=` simply
  surfaces an `llm_unavailable` operator hint without the extra.
- Callers wanting `ask=` should `pip install a2web[llm]` and set
  `ANTHROPIC_API_KEY` (or whatever `llm_api_key_env` points at).

## [0.3.0] - 2026-05-11

Engine improvements driven by `benchmarks/vs-webfetch/2026-05-11/`.
Five of seven planned sections shipped (envelope diet + reach
reliability + Twitter handler); the last two (v0.4 benchmark code
migration, verification re-run) deferred. Remaining tracker:
`openspec/changes/v0.3-engine-improvements/`.

### Changed (response envelope — opt-in for prior defaults)

- **`fit_md` no longer duplicates `content_md`.** v0.2 populated `fit_md` as
  a byte-for-byte copy of `content_md` (pruning filter is gone since v0.2;
  field was preserved for forward-compat). Reality: 19% of total payload
  tokens across the benchmark corpus, zero quality benefit. v0.3 returns
  `fit_md=None` until a future pruning filter ships. Field stays on the
  model.
- **`links` is opt-in via new `include_links: bool = False` param.** Was
  the largest line item (49% of total payload), dominated by aggregator/UI
  noise. Pass `include_links=True` for list-extraction tasks. Default-off
  saves ~50% of tokens on link-heavy pages with judge-score parity on
  17/20 benchmark URLs.
- **`diagnostics` is opt-in via new `debug: bool = False` param.** A new
  always-populated `diagnostics_summary: str` field carries a one-line
  `tier=X verdict=Y total_ms=Z` summary. Pass `debug=True` to get the
  full per-tier diagnostic trace. Default-off saves ~3% always-on tokens.
- **Net result on the benchmark corpus: 72% fewer tokens per fetch by
  default** (127k → 35.5k across 20 URLs; gh-trending alone dropped from
  27,167 to 1,011 tokens).

### Added

- **Twitter / X handler via Nitter rotation.** New site handler matching
  `x.com` / `twitter.com` status URLs. Reads `nitter_instances` from
  `AppSettings` (env `A2WEB_NITTER_INSTANCES`, comma-separated; also from
  YAML). Empty list = handler effectively disabled (matches the URL but
  `fetch` returns `no_match=True` so the orchestrator falls through to
  raw + browser tiers without errors). When configured, the handler
  shuffles the instance list per fetch and probes in order, with per-
  instance circuit breakers reusing the existing `purgatory` infra.
  First HTTP 200 with extractable content wins; all-fail → returns the
  last verdict (typically `connection_error`) for the orchestrator to
  escalate. Closes the X auth-wall gap that the gate fix exposed — the
  browser tier now dispatches on X status URLs but hits the login wall;
  Nitter sidesteps both problems.

### Fixed

- **Gate: block-page markers no longer false-positive on pages with substantive
  extracted content.** Real interstitial / block pages by definition return
  empty bodies; previously a "cf-chl-bypass" or "Just a moment" string anywhere
  in the HTML (security pages, cookie banners, compliance copy) was enough to
  flag the page. v0.3 requires `content_md < LENGTH_FLOOR` for any block-marker
  verdict to fire — the same length-gated rule Anubis already used. Surfaces on
  the benchmark as the Linear false-positive (1,152 chars extracted, marked
  `status=failed`).
- **Gate: broader JS-shell escalation to browser tier.** Previously the
  length_floor → browser path required the narrow `<noscript>enable JavaScript</noscript>`
  marker plus three `<script>` tags. v0.3 also escalates on any of: `id="__next"`
  (Next.js), `id="root"` (React), `id="app"` (Vue / generic), `id="react-root"`
  (Twitter / X), `window.__data__`, `window.__INITIAL_STATE__`, or any
  `<noscript>` tag — provided extracted content is below the floor and at
  least one `<script>` tag is present. Closes the "browser tier fires 0/20
  times" benchmark finding for the SPA-shell case.
- **Reddit handler now falls back to `old.reddit.com` on `.json` failure.**
  Reddit's `.json` endpoint frequently 404s for threads that remain
  readable on old.reddit (UA gating, removed/quarantined quirks). The
  handler now: (a) attempts the JSON path first as before, (b) on 404 or
  empty thread (no title + no selftext + no comments), retries against
  `old.reddit.com<path>` with trafilatura extraction. Single extra GET
  only when the JSON path is empty/missing.

### Migration notes

Callers that relied on `links` or full `diagnostics` being present without
explicit opt-in must pass the new params. The `fit_md` change is purely a
defect fix — callers that read `fit_md` got the same content as
`content_md` and should switch to `content_md` directly.

## [0.2.0] - 2026-05-11

### Changed (internal architecture; wire surface unchanged)

- Migrated to a2kit v0.26: imperative `App` composition (no fluent
  builder chain), typed `app.singleton(T, factory=...)` DI,
  `@app.on_startup` / `@app.on_shutdown` / `@app.health_check`
  decorators replace the bespoke lazy+`atexit` lifecycle pattern.
- Typed LDD event registry — emit via `a2kit.ldd.event(PayloadType(...))`
  / `a2kit.ldd.report(...)` from anywhere in the pipeline; subscribe
  external consumers (OTel exporter, etc.) via `app.ldd.add_sink(...)`.
  The custom `anyio.MemoryObjectStream` fan-out bus and
  `mcp_progress_sink` helper are removed; `events/sinks.py` shrinks to
  the OTel forwarder.
- `TierResult` is now a typed `dataclass(slots=True)` with named fields
  (`pre_rendered: Rendered`, `from_archive`, `from_browser`,
  `js_executed`, `browser_wall_ms`, `browser_bytes`,
  `snapshot_age_days`, `operator_hint`, `no_match`, `skipped`,
  `handler_name`, `conditional_hit`, `archive_source`). The
  `tier_extras: dict[str, Any]` bag is removed across all call sites.
- Orchestrator (`fetcher.py`) split into a 12-line `_run_pipeline`
  coordinator + six named phase functions (`_phase_cache_check`,
  `_phase_tier_loop`, `_phase_extract`, `_phase_gate_and_escalate`,
  `_phase_cache_write`) with a single `FetchContext`
  `dataclass(slots=True)` threading state instead of 20+ locals.
- Tests use a2kit's in-process client (`a2kit.testing.client(app)` +
  `a2kit.testing.peek`) instead of the prior `bootstrap_state_for_test`
  / `teardown_state_for_test` helpers.

### Added

- Architecture retrospective at
  `openspec/changes/archive/2026-05-11-migrate-to-a2kit-v026-and-simplify/retrospective.md`
  capturing the four OSS swaps researched-but-deferred (hishel,
  aiometer, purgatory-for-proxy, stdlib-RotatingFileHandler) and the
  lesson: hand-rolled async tends to beat sync-wrapped stdlib even when
  the library nominally covers the use case.

### Removed

- `htmldate` dependency — `trafilatura.extract_metadata()` now returns
  the published date alongside title/author in one call.
- `src/a2web/extract/pruning_filter.py` (in-tree block-density `fit_md`
  builder) — the `FetchResponse.fit_md` field remains for forward-compat
  but is now always `None` until a replacement ships in v0.3.
- `src/a2web/events/bus.py`, the `mcp_progress_sink` helper, and the
  `bootstrap_state_for_test` / `teardown_state_for_test` test helpers —
  all superseded by a2kit v0.26 surface.

### Deferred (see `BACKLOG.md`)

- Phase D workspace packaging (proxy-pool, browser-pool, block-detector).
  All three are sensible extraction candidates but no external reuse
  signal yet justifies the mechanical cost.
- Four OSS swaps (above) — each documented with the specific
  API/semantic mismatch that killed it.

## [0.1.0] - 2026-05-10

### Added

- Single-tool MCP/CLI surface `WebRouter.fetch(url)` returning a typed
  `FetchResponse` (envelope + LDD diagnostics + operator hints) (PR1, PR2).
- Tier cascade orchestrator with closed-enum verdicts, per-fetch action
  caps, and pluggable Strategy + Registry tiers (PR3, PR4).
- `raw` tier (curl_cffi TLS impersonation) and `jina` tier (r.jina.ai
  reader, bearer-optional, deny-list short-circuit) (PR3, PR7a).
- Site handlers as tier-0: `reddit` (`.json?limit=500`), `hn` (Algolia)
  (PR5); `arxiv` (export.arxiv.org Atom), `wikipedia` (REST page/html),
  `github` (REST API, optional `A2WEB_GITHUB_TOKEN`) (PR8).
- Quality gate with closed-enum verdicts and `suggested_tier` hints
  (`browser`, `tls_impersonate`) covering paywall / block-page /
  anti-bot / length-floor / content-type / cf_iuam / anubis / turnstile
  / akamai_bmp / js_required signals (PR3, PR7c).
- `archive` tier dispatched out-of-band on playbook `RetryViaArchive`:
  Wayback CDX + archive.ph hedged via anyio task group; Wayback chrome
  stripped before trafilatura; results carry `from_archive=True` and
  `snapshot_age_days` (PR7b).
- `browser` tier dispatched out-of-band on gate `suggested_tier="browser"`:
  Camoufox via lazy `BrowserPool`, page-per-fetch, persistent per-host
  context, LRU + idle eviction, 30s page budget; missing dep group
  surfaces as a graceful `connection_error` rather than a crash (PR7c).
- Trafilatura + htmldate extraction with OG/JSON-LD metadata and an
  in-tree block-density `fit_md` pruning filter; sync work wrapped in a
  single `asyncio.to_thread` chokepoint (PR3, PR6).
- Conditional-GET sqlite cache (etag / last-modified / content-hash
  dedup); cache writes gated on quality verdict; archive results never
  cached (PR4, PR7b).
- Proxy pool with first-match-wins route policy, host-glob + tier match,
  AND-composition, `${ENV_VAR}` resolution, alive/quarantined/dead
  health states, and per-tier retry walks (PR7d).
- Autonomous-action playbook (paywall→archive, block→archive,
  cf-403→archive, arxiv-pdf→abs, `RewriteUrl` capped at 1) with the
  after-tier no-op closed (PR7b, PR7d).
- Diagnostic event bus (`anyio.MemoryObjectStream` fan-out): MCP
  progress sink (`ctx.event` + `ctx.report_progress`) and an OTel sink
  emitting one span per `*Ended` event (no-op when SDK absent) (PR6,
  PR7a).
- Lazy + `atexit` lifecycle pattern for sqlite, browser pool, and proxy
  pool — required because a2kit v0.23 exposes no lifespan hook (PR7a,
  PR7c, PR7d).
- NDJSON request log with size-based rotation and gzip on rollover; one
  record per fetch; lazy-open writer; best-effort writes that surface
  failures via `operator_hints[code=log_write_failed]` (PR9).
- Settings layer: `AppSettings(BaseSettings)` from `A2WEB_*` env + optional
  YAML at `$A2WEB_CONFIG` or `~/.a2web/config.yaml`; secrets are env-only
  (PR1, PR7a, PR7d).
- Optional `[browser]` extras for Camoufox / Playwright; bootstrap via
  `make bootstrap` (`uv sync --all-extras`) (PR7c).
- `CHANGELOG.md` and `BACKLOG.md` at repo root; `BACKLOG.md` consolidates
  every known deferred item across PR7e / PR8b / PR10b / v0.2 / v0.3+.

### Removed

- The pre-release `LogsRouter` MCP/CLI surface (`replay` / `tail` / `grep`)
  and its supporting `log/reader.py` + duration parser. The on-disk
  NDJSON log itself is unchanged; operators inspect it directly with
  `tail` / `grep` / `jq`. Replay-from-cache is deferred to PR10b — see
  `BACKLOG.md`.

[0.1.0]: https://github.com/yoselabs/a2web/releases/tag/v0.1.0
