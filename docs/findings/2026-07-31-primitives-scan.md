# Findings — primitives & elevation scan, 2026-07-31

Evidence for the **T7** backlog track. Five parallel agents on five axes: shelf
adopt-gaps, hand-rolled stdlib primitives, failure-handling vocabularies,
concurrency & lifecycle, and a rule-of-three promotion ledger.

The question asked: *where is a2web engineering up from low primitives something
that a pattern, a helper, a library, or the shelf should own?*

**This file is the evidence, not the queue.** The actionable list and its
dependency order live in [`BACKLOG.md`](../../BACKLOG.md). Line numbers are as of
2026-07-31 — re-check before acting.

---

## The shape of the answer

Three recurring failures, in order of how much they cost:

1. **Adopted, then reimplemented by hand.** A shelf primitive is a declared
   dependency — sometimes imported and re-exported — and the job it owns is done
   inline somewhere else anyway.
2. **Named once, spelled N times.** One concept, N independent implementations,
   which then drift. The drift is the promotion signal: it proves nobody is
   maintaining them as one thing.
3. **A bound present in some copies and absent in others.** The most dangerous
   variant of (2), because the missing bound is invisible next to N siblings
   that have it.

---

## Adopted, then reimplemented

### `prune_dict` — imported, re-exported, never called

`wire.py:64` imports `prune_dict` from the shelf `lean_wire`; `wire.py:74`
re-exports it in `__all__`. **It is called from nowhere in `src/` or `tests/`.**

Meanwhile `models.py:786` hand-writes the same omit-empty predicate inline —
`value is None or value == "" or value == [] or value == {}` — 700 lines away,
inside `_prune_wire`. And `models.py:678` separately inherits `PruneEmpty`, whose
`_is_empty` is a third answer to the same question in the same file.

Same shape: `cli.py:134` hand-writes `model_dump(mode="json")` while
`lean_wire.dump_model_for_wire` — documented as the *"single substrate helper for
wire dumps"* — goes unused.

### `fmt_dur` — adopted, then bypassed one import away

`fmt_dur` is correctly elevated to the shelf `timefmt` and used at
`fetcher_response.py:183, 185, 187, 504` — **5 call sites, all in one file.**

`llm_eval/live_sink.py:176` renders a duration as `f"{total_ms/1000:.1f}s"`,
which **disagrees with `fmt_dur` for every value ≥ 7s** (`fmt_dur` drops the
decimal there).

### `http_fetch` — bypassed by jina, and by three tiers generally

`tiers/jina.py:18, 133-155` builds its own `httpx.AsyncClient` for a plain GET to
`r.jina.ai` — no impersonation, no conditional GET, hand-mapped verdicts, and
therefore no circuit breaker and no `FetchVerdict` closed enum.

`tiers/zyte.py:104` and `tiers/firecrawl.py:60` also construct clients inline.
Those two are POSTs to JSON APIs and `http_fetch` is GET-only, so they are a
legitimate gap — but `handlers/README.md:17` bans hand-rolled
`httpx.AsyncClient` and the ban is scoped to `handlers/` only. `tiers/` does it
freely.

### `lean-wire` — not used where its whole reason applies

`llm_eval/report.py:135-136` writes `results.tsv` with stdlib
`csv.DictWriter(delimiter="\t")` — precisely the QUOTE_MINIMAL
raw-`\n`-inside-a-field behaviour that `pyproject.toml:50-56` cites as the reason
lean-wire replaced a2kit's codec.

Also: `lean_wire.encode_tsv` is called bare at `models.py:735, 748, 758` inside
`_prune_wire`, outside the presence / already-a-string / shape guards that
`wire.py:124-175` wraps around the same function. By design — but the shape guard
has no analogue there.

### `a2effect` — adopted at one boundary, taxonomy unused

**LIVE wire defect.** `AppError` appears in exactly one file (`error_wire.py`, as
an import at `:35`, a type hint at `:69`, and the `except` at `:97`). **No
`AppError` subclass exists anywhere in `src/` or the venv** — verified by grep.

Therefore `guard_tool`'s `except AppError` branch (`:97`) is **dead in
production**. Every exception escaping a tool body takes the `except Exception`
path (`:99`) and is quarantined into `UnexpectedDefect`, kind `"bug"`. A missing
LLM key (`ResourceUnavailable`, `state.py:186`) and a genuine null-deref render
identically as `"Internal error (UnexpectedDefect): …"`. Four of the five entries
in `_KIND_LABELS` (`:48-54`) are unreachable.

Four more `a2effect` surfaces sit unused in the venv while a2web hand-rolls them:

- **`a2effect.translate.raises_as`** (`translate.py:15-38`) — awaits with a
  `{foreign_exc: AppError}` mapping, chaining `__cause__`. Exactly the shape
  hand-written at `handlers/github.py:191-209` (9 branches),
  `tiers/jina.py:139-161`, `zyte.py:106-109`, `firecrawl.py:62-65`.
- **`a2effect.enrichers.pydantic_validation_error_enricher`**
  (`enrichers.py:10-23`) — maps a pydantic `ValidationError` to an `InputError`
  carrying per-field `loc`/`type`/`msg`. `fetcher_response.py:85-100` re-derives
  the offending field by hand via `getattr(exc, "errors", None)` with an
  `"unknown"` fallback.
- **`a2effect.register_error_kind`** — would make `retrieval_incomplete` /
  `wall` a first-class wire *kind* rather than a boolean plus a hint-code string
  match.
- **`a2effect.lint`** (`lint.py`, `_lint/uncovered.py`, `_lint/not_typed.py`,
  `_lint/closure.py`) — a declared-error-closure checker, unused, in a repo that
  records losing `a2kit lint rego` as *"a real loss"*.

Making `ResourceUnavailable`, `LLMNotAvailable` (`packages/llm_extract/errors.py:6`)
and `JudgeParseError` (`judge.py:63`) `AppError`s with proper kinds immediately
activates the four unreachable labels.

---

## Named once, spelled N times

### Elapsed-time arithmetic — 30 copies, 3 clocks

`int((time.perf_counter() - <start>) * 1000)` appears **30 times**: `fetcher.py`
×22, `llm_eval/systems.py` ×4, `llm_eval/extraction.py` ×2,
`fetcher_response.py:365`, `llm_eval/runner.py:397`.

A second-order "span = now − mark" shape is written **9 more times** with 6
different local names (`start_ms`, `t_ms`, `extract_dur_start`, `gate_dur_start`,
`cache_dur_start`, `phase_start_ms`) at `fetcher.py:742, 1357, 1379, 1700, 1724,
1869, 2292, 2508, 2573`.

**Three clocks are used for the same purpose and nothing says which is right:**
`perf_counter` (30 sites), `time.monotonic` (`handler_probe.py:223, 237`;
`packages/proxy_routing.py:195, 223`), `time.time()` (`uptake.py:71, 95`;
`cookie_jar.py:216, 273, 330`).

The arithmetic exists only because every phase re-derives what
`FetchContext.start_perf` (`fetcher.py:590`) already knows. Missing concept: a
phase stopwatch owned by the context — `fc.elapsed_ms()` /
`with fc.span("gate") as s: … s.dur_ms`.

### "How long ago" — 4 impls, 4 input units, 3 renderings

| impl | file:line | input | output | empty case |
|---|---|---|---|---|
| `human_age` | `handlers/reddit.py:681-692` | seconds | `45s/2m/2h/3d/2y` | clamps to `0s` |
| `_format_age` | `fetcher.py:803-808` | **hours** | `30m/5h` | `"never"` |
| `_snapshot_age_days` | `tiers/archive.py:103-109` | `%Y%m%d%H%M%S` str | **int days** | `None` |
| inline | `cookie_jar.py:330` | epoch | float hours, unformatted | — |

`fmt_dur` ("how long did it take") is already a shelf `timefmt` export. The
sibling concept — `age_since(epoch|datetime) -> str`, unit-free at the call site
— has no owner and belongs next to it.

### Upstream-API JSON — no owner, and 5 copies of one misunderstanding

The `packages/llm_extract/wobble/` funnel owns **LLM** JSON only, by design and
enforced by `tests/architecture/test_json_loads_funnel.py`. Upstream-API JSON has
no owner: 5 independent parse sites, each with its own try/except and failure
policy — `tiers/archive.py:82`, `handlers/hn.py:100`, `handlers/habr.py:127`,
`handlers/discourse.py:78`, `handlers/v2ex.py:110`.

**All five write `except (ValueError, json.JSONDecodeError)` — redundant, since
`JSONDecodeError` subclasses `ValueError`.** Five identical copies of the same
misunderstanding is the copy-paste fingerprint.

`habr.py:115-130` `_fetch_json` and `v2ex.py:99-112` `_fetch_json` are **the same
function**, down to a shared verbatim docstring — *"Never raises — a per-task
failure must not cancel its sibling in the task group, so each fetch isolates its
own errors"* — differing only in habr's trailing `isinstance(payload, dict)`
guard. The concurrent fan-in wrapper around them is duplicated verbatim too
(`habr.py:87-95`, `v2ex.py:70-78`).

Missing concept: `fetch_json(url, …) -> Any | None` on `handlers/_common.py` —
which must route through `map_non_ok` so the transport verdict survives. Today
habr and v2ex are **the only two handlers that discard it entirely**: a habr 429
and a habr malformed-JSON are the same `None`.

### The never-raises pattern — 7 claimed, 5 impls, all disagree

Seven docstrings claim "never raises" (`domain.py:44, 112, 321`,
`listing_oracle.py:9`, `log.py:187`, `habr.py:119`, `v2ex.py:104`). Five
implementations of "async fetch → parse → failure":

| impl | non-200 | parse error | logged |
|---|---|---|---|
| `habr.py:115-130` | `None` | `None` | no |
| `v2ex.py:99-112` | `None` | `None` | no |
| `discourse.py:67-86` | `map_non_ok` → typed | `empty_result(not_found)` | no |
| `hn.py:85-104` | `map_non_ok` | `empty_result(...)` **+ `escalate_to_render`** | no |
| `arxiv.py:84-101` | `map_non_ok` | `empty_result(content_type_mismatch)` | no |
| `tiers/archive.py:78-108` | `None` | `None` | no |

hn invents a fourth response (`escalate_to_render`) that no other handler uses
for the same condition. `_common.map_non_ok` exists to unify this and habr,
v2ex, and archive do not call it.

### Handler page-rendering — the largest un-elevated shape in `src/`

There is no "render a page" concept; nine handlers each rebuild one from string
primitives.

- **Markdown assembly**: `parts: list[str]` + `"\n".join(parts).strip() + "\n"` —
  **17 sites** (`arxiv:211,304`, `habr:167`, `hn:153,226`, `v2ex:149`,
  `discourse:172,239`, `reddit:582,615,671`, `_reddit_html:268`). github uses
  `"".join(...)` at `:411,447,479` — a silent disagreement on separator.
- **Headings register**: 8 sites, 31 `Heading(level=…)` literals.
- **Blockquote comment tree**: 4 recursive impls with a byte-identical 3-line
  core (`hn.py:242-246`, `habr.py:217-226`, `discourse.py:183-192`,
  `_reddit_html.py:273-275` which uses `"> " * (depth+1)`), plus `reddit.py:666`
  with a hardcoded single `>`.
- **Untyped intermediary**: 10 `_render_*` functions return
  `dict[str, Any]`/`dict[str, object]` purely to be re-typed at 9
  `Rendered.from_dict(...)` sites, which needs **four `# type: ignore[arg-type]`**
  to launder the dict back into a real slotted dataclass
  (`tiers/__init__.py:24-44`). **Reddit alone builds a typed `_RenderResult`
  (`reddit.py:515`) and skips the dict — proving it is unnecessary.**
  `discourse._render_index:238-243` smuggles a **fifth key `next_links`** through
  the same bag and unpacks it at `:95`.

### Truncate-to-cap — 6 impls, 4 markers

| file:line | marker | returns flag |
|---|---|---|
| `models.py:389-399` | none, hard cut ×2 | no |
| `fetcher_response.py:230` | `cap-1` + `…`, rstrip first | no |
| `fetcher_response.py:254` | `[:80].rstrip()`, no marker | no |
| `llm_eval/live_sink.py:192-197` | `cap-1` + `…`, guards `width<=1` | no |
| `packages/llm_extract/extractor.py:371-376` | `\n\n[Content truncated to N chars]\n` | **yes** |
| `domain.py:71` | `\n… (truncated)` | no |

`models.py:389` and `:396` are the same nine lines twice in one class, differing
only by `120` vs `80`. Missing concept: `clip(text, cap, *, marker=…) -> (str, bool)`
— one place that decides whether truncation is *visible*.

### Whitespace collapse — 6 impls, 2 mechanisms

`" ".join(text.split())` at `fetcher_response.py:228, 251`, `domain.py:430`,
`fetcher.py:1646` (`_normalize_ws` — already a named function that **nothing
imports**); regex at `packages/block_detector.py:37`, `handlers/arxiv.py:172`.

### Host matching — 6 impls that disagree on case and `www.`

Five sites write `(parsed.hostname or "").lower() not in _X_HOSTS`
(`arxiv:46,55`, `habr:58`, `v2ex:47`, `github:90`). `reddit.py:120` and
`twitter.py:44` omit `.lower()`. `hn.py:52` uses a bare `!=` against a single
host and accepts **no `www.` variant at all**. `wikipedia.py` uses a regex;
`discourse.py:60` lowercases the settings side instead.

Both branches work — which is the tell that **nobody knows
`urlparse().hostname` already lowercases** (verified:
`urlparse('https://WWW.ArXiv.ORG/…').hostname == 'www.arxiv.org'`). Five sites
carry a redundant defensive `.lower()`; three omit it correctly by accident.
Six `_X_HOSTS` frozensets hand-enumerate the `www.` twin as data.

Related: **`_WALL_VERDICTS` is defined twice with different member types** —
`handlers/_common.py:77` (`BlockVerdict`) and `handlers/twitter.py:126`
(`Verdict`).

### Four double-checked-lock bodies for one idea

`scope.memoized` (`scope.py:96-110`, list-slot), `CookieJarResource`
(`cookie_jar.py:178-192`, `_tables_ready` bool), `LlmExtractorResource`
(`llm_resource.py:214-227`, `is not None` sentinel), shelf `SqliteResource`
(`:63`, its own). `scope.memoized` is already the right shape; the two a2web
resources predate it.

Three schema-idempotency strategies also coexist in the same sqlite file: an
`on_open` hook (`cache.py:60`), a `_tables_ready` flag (`cookie_jar.py:181`), and
**unconditional re-execute** — `uptake.py:53` re-runs `CREATE TABLE IF NOT
EXISTS` + `CREATE INDEX` on *every* `record_suggestions` (`:75`) and *every*
`note_visit` (`:92`), with no readiness flag and no lock.

---

## Bounds present in some copies, absent in others

### `hn.py:233` recurses on untrusted input with no depth cap — LIVE

`_MAX_DEPTH = 20` exists in `habr.py:48` and `discourse.py:41`. `hn.py:233`
recurses on `node["children"]` straight from the Algolia API body **with no depth
cap at all**. Only habr carries a node budget (`_MAX_COMMENTS = 400`, `:49`).

### No per-fetch deadline anywhere — LIVE

All 23 `perf_counter` reads in `fetcher.py` are for *reporting* into events.
`fc.start_perf` (`:590`) is never compared against a budget. The only per-fetch
caps are count-based (`url_rewrites`, `archive_dispatches`, `browser_dispatches`,
`paid_dispatches`, `:368-371`).

**13 independent per-call timeouts**, two spellings (`_TIMEOUT_S` vs
`_DEFAULT_TIMEOUT_S`), and six are the literal value `10` redeclared per module.
The "site-handler API fetch" timeout is `10` (hn, habr, discourse, reddit, v2ex),
`10.0` (arxiv, wikipedia), `15.0` (github), `5` (twitter) — int/float disagree.
**None is operator-tunable**; `AppSettings` exposes no handler timeout.

**The LLM has no timeout at all** — verified: zero `timeout` hits across
`src/a2web/packages/llm_extract/` and `llm_resource.py`. In the installed
`anyllm`, the single hit is `providers/claude_code_sdk.py:118: timeout=5`, a
subprocess probe, not a completion budget. An `extract()` on a 100 000-char page
(`settings.py:229`) can hang the whole tool call indefinitely.

Bounded worst case on a walled fetch:

```
reddit handler  10 + 40 ratelimit sleep + 10 retry + 10 old.reddit  =  70s
raw tier                                                            =  10s
jina tier                                                           =  15s
browser fast    launch 45 + page 30                                 =  75s
browser robust  launch 45 + page 30                                 =  75s
archive         cdx 12 + snapshot 12 (hedged)                       =  24s
paid (zyte)                                                         =  60s
                                                        subtotal    ≈ 329s
LLM extraction                                       NO TIMEOUT — unbounded
```

Name the missing concept by purpose: **fetch budget**, not "timeout manager".

### 45 caps, no declaration site

22 are bare unnamed literals: `[:25]` (`arxiv:297`, `reddit:559`), `[:10]`
(`arxiv:317`, `reddit:612`), `[:30]` (`hn:130`, duplicating
`_ALGOLIA_SEARCH_HITS_PER_PAGE = 30` at `hn:30`), `[:50]` (`domain:285,439,548`),
`[:5]`, `[:8]`, `[:80]`, `[:120]`, `[:200]`, `[:20]`, `[:60]`, `[:16]`.

**Six different ceilings on one wire field** (`next_links`): `_NEXT_LINKS_CAP=10`
(`fetcher_response.py:215`), `_WIKILINK_CAP=10` (`wikipedia:149`),
`_MAX_TOPICS=50` (`discourse:43`), `[:25]`/`[:10]` (arxiv), `[:10]` (reddit),
`[:30]` (hn).

Missing concept: one `limits.py` naming each cap by purpose
(`WIRE_NEXT_LINKS`, `COMMENT_TREE_DEPTH`, `HANDLER_HTTP_TIMEOUT_S`), with the
operator-relevant subset promoted onto `AppSettings` the way browser budgets
already are (`settings.py:168-176`).

### `github.py` degrades silently six times — ADR-0009 leak, LIVE

`handlers/github.py:226, 263, 291, 330, 358, 367` — six
`except gidgethub.GitHubException: x = None`. Each silently degrades the rendered
page (missing README / issues / PRs / reviews / comments) and still returns
`Verdict.ok`. **A GitHub outage produces a thinner-but-`ok` page with nothing
recording that a sub-fetch failed.** Plus `:233`, base64 decode failure →
`readme_md = ""`.

That is the silent-partial shape ADR-0009 exists to forbid. Missing concept: an
**optional sub-fetch that leaves an observation when it fails**, not a `None`.

### Silent swallows — 16 total, 11 on a retrieval path

Beyond github's six: `habr.py:128`, `v2ex.py:111`, `reddit.py:427, 474`,
`tiers/archive.py:83, 107`, `fetcher.py:784, 823` (`ResourceUnavailable` → bare
`return`; cookies silently absent, no observation, no hint), `llm_resource.py:246`
(sqlite open failure → extraction cache silently off, and `del exc` **deliberately
destroys the cause**), `log.py:92` (`TypeError` → `payload = {}`; a
non-serializable event vanishes), `packages/llm_extract/extractor.py:478`
(`ParseError` → `return answer, []`; the next_links index is lost with **no
`llm_wobble` emission**, unlike its sibling at `:626` which does log).

### Degrade-to-default that can mask a rename

`fetcher.py:267-268` — `getattr(settings_obj, "cache_ttl_article_h", 24)` /
`"cache_ttl_static_h", 168`, against a deliberately untyped `settings_obj: object`.
A settings rename silently reverts to 24h/168h TTLs; no test can catch it and
`ty` cannot see it. **The only `getattr` in the tree reading a field the codebase
owns.**

Also `packages/llm_extract/extractor.py:297, 306` —
`getattr(exc, "retryable", False)`: an `AnyLLMError` that stops carrying
`retryable` silently downgrades every provider error to non-retryable, flipping
the `llm_error` hint's advice text (`models.py:362-364`).

---

## The failure-vocabulary census

**Ten parallel vocabularies**, with **~21 hand-written conversion sites** between
them:

`Verdict` (15 members, `models.py:32`) · `BlockVerdict` (6,
`block_detector.py:54`) · `FetchVerdict` (shelf) · `RenderOutcome` (shelf) ·
`TerminalOutcome` (7, `actions/terminal.py:28`) · `FetchStatus` (3,
`models.py:50`) · `Obstacle` (Literal-4, `models.py:445`) · `OperatorHint.code`
(**open string set**, ~18 codes) · booleans (`retrieval_incomplete`, `no_match`,
`skipped`, `escalate_to_render`, `provider_error_retryable`, `authoritative`) ·
**79 `-> X | None` signatures outside `llm_eval`**.

`Verdict` and `BlockVerdict` are kept in sync by **string equality and a
comment** (`block_detector.py:56-61`). No test asserts the member sets agree, and
the string-pun `Verdict(result.verdict.value)` exists in two independent copies
(`handlers/_common.py:129`, `fetcher.py:149`).

Three copies of httpx-exception → Verdict, **two already drifted**:
`tiers/jina.py:139-161` (3 branches, handles `httpx.ProxyError`),
`tiers/zyte.py:106-109` (2 branches, no `ProxyError`),
`tiers/firecrawl.py:62-65` (2 branches, no `ProxyError`). jina reports
`proxy_unavailable` where the other two report `connection_error`.

**`OperatorHint.code` should be a closed enum.** ~18 codes as free strings,
consumed by *identity comparison* at `fetcher_response.py:435, 445, 450` and
`fetcher._has_hint`. A typo'd code silently disables an ADR-0009 incompleteness
rule. Closed-enum discipline exists everywhere else in this codebase (`Verdict`,
`TerminalOutcome`, `Obstacle`); hint codes are the exception. Seven codes exist
only as inline literals with no factory.

---

## Retry: the documented 5 layers do not hold

CLAUDE.md states retries live at 5 layers (connection / HTTP / proxy / tier /
handler). **There are exactly 3 sleep/retry loops in `src/`**, and one is a
heartbeat:

| site | layer | note |
|---|---|---|
| `handlers/reddit.py:322-375` | handler | honours `x-ratelimit-reset`, +1s margin, `_RSS_RATELIMIT_MAX_WAIT_S` ceiling, `_RSS_MAX_RETRIES` bound |
| `handlers/github.py:152-153` | HTTP | overrides gidgethub's `sleep` hook — **a2web hands its retry budget to a third-party library with no cap of its own** |
| `llm_eval/live_sink.py:130` | none | heartbeat timer, not a retry |

Shelf `http_fetch` has **no** retry loop (its own comment at `fetch.py:121` says
so). The proxy layer is rotation + purgatory breakers (`state.py:56-73`), not
backoff. The tier layer is the `TIER_ORDER` cascade — an escalation, not a retry.

**Confirmed gap:** habr, v2ex, discourse, arxiv and hn have **no rate-limit
policy at all**. `_common.map_non_ok:69` maps `FetchVerdict.rate_limited`
straight to a terminal `Verdict.rate_limited` — a 429 reddit would ride out is an
immediate handler failure everywhere else.

**Do not elevate reddit's loop to `tenacity`/`stamina`.** Its comments
(`:84-97`) encode a live-measured Reddit penalty-box model that a generic library
would take the schedule from and lose the reason. It is correctly hand-built — it
just needs to be visible to the fetch-budget concept, because that 40-second
in-band sleep is the single largest unaccounted term in the worst case.

---

## The shelf: what a2web has already paid for

Shelf inventory: **26 packages**, a2web consumes 17 directly + 1 transitively.
**Version drift: none** — every pin is at the newest tag; only `content-extract`
has an unreleased commit (`f7c9b78`, ruff format, cosmetic).

Adopt gaps are thin, and that is a *good* result: `page-tsv` and
`mcp-result-wire` were **explicitly rejected** in
`openspec/changes/archive/2026-07-26-sunset-a2kit-dependency/design.md:99-104`
("Reject `page-tsv`… Adopting re-imports the problem"; "Reject
`mcp-result-wire` — actively harmful"). `anyembed`, `duckdb-sidecar`,
`git-porcelain`, `managed-region` are genuine non-gaps — zero matching a2web code.

### The largest un-repaid debt: `page-tsv` still ships all three encoder defects

`shelf/packages/page-tsv/src/page_tsv/render.py:96-102` loops the static
`tsv_fields` tuple with:

- **no presence guard** — resurrects a pruned field
- **no already-a-string guard** — `:98`'s `isinstance(raw, (list, tuple)) else []`
  overwrites populated pre-encoded content with the empty marker
- **no shape guard** — `encode_tsv` at `:99` is unwrapped, so one
  `headings`-shaped field voids the encode for the whole envelope

a2web's fixes are at `wire.py:124-133` / `:135-153` / `:155-175`. **`a2kay`
consumes `page-tsv` today** — so a sibling repo is running the bugs a2web filed
and fixed locally.

### Five more shelf gaps a2web paid for

1. **`content-extract` has no `include_comments` / `include_tables`.** Verified
   live: the shelf signature is `extract_markdown(html, url, *, include_links=False)`
   (`content_extract/__init__.py:215`). a2web pays with two funnel exemptions
   (`tests/architecture/test_trafilatura_funnel.py:47-64`, whose own comment says
   *"This is a SHELF GAP, not a permanent a2web exception. The fix is to promote
   the knob"*), a direct `trafilatura>=1.12,<2` dep (`pyproject.toml:143`), and
   those two handlers losing links + headings from the same parse.
2. **`dom-schema` cannot report ROT under a universal container.**
   `handler_probe.py:136-140`: its container is `<body>`, which always matches, so
   a rotted selector reads as EMPTY rather than ROT. a2web pays with a live
   `min_candidates=5` network probe as the only rot detector — defeating the
   package's stated capability.
3. **`record-mine` dropped `[role=heading]`.** `detector.py:62` gates on `h1`-`h6`
   only; a2web's normative spec `openspec/specs/record-extraction/spec.md:15`
   requires `h1`–`h6` **or** `[role=heading]`.
4. **`any-browser` container CDP-connect failure.** zendriver's handshake fails in
   the slim container while patchright launches, so the robust rung silently
   collapses to the same engine. a2web paid with `correlated_witness` — a guard
   that makes the shelf bug *observable* rather than fixed.
5. **`json-in-html` extracts but does not normalize.** The one open EVOLVE with
   real code behind it: ~270 lines of LD/microdata/OG → uniform rows at
   `domain.py:262-292, 383-416, 501-545`.

### Partial adoptions

`dom-schema` is adopted by **2 of 9 handlers** (`arxiv`, `wikipedia`);
`handlers/_reddit_html.py:28, 126` hand-rolls `selectolax.parser.HTMLParser` + CSS
traversal across 294 lines with **no ROT verdict**, and `selectolax` remains a
direct dep (`pyproject.toml:144`).

### Unpromoted a2web substrate with no shelf home

Both written *after* the 2026-07-27 sweep (which inventoried the pre-sunset
tree), so neither appears in its verdict table:

- **`lazy.py` (43) + `scope.py` (109)** — `Lazy[T]`, LIFO `ResourceScope`,
  `memoized`. Generic substrate; the catalog has nothing for it.
- **`cli.py:field_to_typer_annotation`** — MCP-tool → Typer CLI derivation.

### Promote-when-second-caller-appears

**Hedged-race-first-wins** (`tiers/archive.py:130-163`) — 34 lines of genuinely
subtle code: memory-object-stream sizing, a miss counter distinguishing "both
missed" from "still waiting", explicit `cancel_scope.cancel()`, `finally: await
send.aclose()`. Substrate-indifferent, DEEP, STABLE — but exactly one call site.
Not due by rule-of-three; flag it, don't promote it.

---

## Lifecycle: the one thing that IS a single concept

The resource pattern is genuinely singular and correctly enforced — 6 instances,
all with `_lock` / `_ensure()` / idempotent `close()` / `__aenter__`+`__aexit__`.
`ResourceScope.aclose()` is idempotent, records only post-`__aenter__`
(`scope.py:52-56`), and keeps unwinding past a failure (`:69-73`). The
documented hang risk is properly guarded.

**One divergence:** `ProxyPool` (`packages/proxy_routing.py:152-168`) has a
mutable `self.health: dict[str, _ProxyHealth]` (`:161`) mutated across concurrent
fetches **with no lock**, and is not an async CM — so `ResourceScope.enter()`
silently passes it through (`scope.py:57-60` returns the resource unchanged when
`__aenter__` is absent). Benign today because `close()` is a no-op; it is the one
member that would not be torn down if it ever grew a real one.

---

## Doc drift found in this round (CLAUDE.md)

- **"browser … capped at 1/fetch"** — the cap is 2. `fetcher.py:2069`
  (`is_robust = fc.browser_dispatches >= 1`) selects a second robust rung, and
  the docstring at `:2062` says `< 2`. Understates worst-case latency by ~75s.
- **"No globals, no module-level lazy caches"** — three violations:
  `handlers/__init__.py:50` `_REGISTRY_CACHE` (with two `global` statements and a
  test-only `_reset_registry()` escape hatch at `:70-75` — the tell),
  `settings.py:308` `@lru_cache(maxsize=1) get_settings`, `wire.py:68`
  `_ENCODE_FAILURES` (unbounded, never cleared). Also `log.py:71 _WIRE_LEVEL`
  reassigned via `global`, and `tiers/__init__.py:182` runs a **manifest walk at
  import time**.
- **"`asyncio.to_thread` chokepoint per sync module"** — true but now **vacuous**:
  exactly **1** `to_thread` call remains in all of `src/` (`cookie_jar.py:213`),
  both trafilatura and sqlite having moved to the shelf. No architecture test
  covers it; ruff `ASYNC100/210/230` checks a different thing (blocking calls in
  async, not a second entry point for one sync module). Per the project's own
  anti-vacuity rule, this invariant currently has no guard.
- Related: `handlers/reddit.py:865` does `import trafilatura` **inline inside an
  async function** and calls it — a sync CPU call on the event loop with no
  thread hop, reachable via the grandfathered funnel exemption.

---

## Round 2 — the rule-of-three promotion ledger

Fifth agent of the primitives scan, returned after the first write-up. Ranked by
lines deleted per unit of interface added. Two of its findings are LIVE defects
neither of the other four agents reached.

### Calibration: a2web is not uniformly under-named

Recorded because it bounds the rest. `scope.py` (110 lines replacing a 599-line
container), `decision_log.py`, `wire.py`'s literal `_TSV_FIELDS`, `models.py`'s
ten `*_hint()` factories, `_prune_wire`, and `actions/` are already the
named-concept treatment and are good. The un-named regions are **four
neighbourhoods**: the second half of `domain.py`, the render/derive halves of
`handlers/`, the failure arms of `tiers/`, and the escalation paths of
`fetcher.py`.

### Row 1 — `domain.py:188-551` is a renderer with ZERO domain coupling

~360 lines importing only `JsonPayload` (shelf `json_in_html`) and stdlib. The
module docstring says it holds "functions that read `AppSettings` or domain
models"; this half reads neither. A pure lift — the highest ratio in the repo,
and the file it leaves behind finally matches its own docstring.

Three accidental divergences prove nobody maintains it as one thing:

- `_opengraph_to_markdown:531` hand-rolls its own markdown table rather than
  calling `_rows_to_md_table` twelve lines above: cell cap **200** vs **80**, row
  cap **50** vs **none**. Same escaping, same header shape.
- `_single_entity_md:345` is explicitly default-keep and its docstring argues an
  allowlist "silently loses an unanticipated answer-bearing field".
  `_recipe_md:316`, immediately above, **is** that allowlist. The stated
  invariant is violated by its neighbour.
- The cap `50` appears as a bare literal at `:285`, `:439`, `:548` — one of them
  commented "matching `_find_product_or_item_list`", i.e. a documented manual
  sync.

### Row 2 — "the item set" — and a LIVE ADR-0015 gap

One concept, **seven-plus incompatible spellings**, with the four operations
over it (render · derive next-links · cap-and-declare · project to wire)
re-implemented per site: `record_mine.RecordSet` (`fetcher.py:1723`),
`_records_to_next_links:1788`, `_records_to_options`
(`fetcher_response.py:234`), JSON-LD `ItemList` (`domain.py:433`), HN front page
(`hn.py:125,160`), Discourse (`discourse.py:196-244`), arXiv (`arxiv.py:262,311`),
Reddit (`reddit.py:562,610`), GitHub/Wikipedia candidates-only.

**LIVE: the divergence is a product hole.** The DOM record-miner path derives
`next_links` AND `options`; the JSON-LD path renders the *same* item set and
derives **neither**. A listing page whose items live in `ItemList` JSON-LD ships
markdown with an empty `other_pages`, while the identical page mined from the
DOM ships both — an ADR-0015 violation caused purely by two unrelated copies of
one concept.

Caps diverge unowned: markdown 30/50/25/25, candidates 10/**50**/10/10/5.
`discourse.py:227` emits up to 50 `next_links` against a 10 cap everywhere else,
and `handler_probe.py:177` records "observed 30" as healthy — pinning the outlier
green.

Cap-and-declare is the *under*-applied half: only `arxiv.py:283` and
`_reddit_html.py:260` declare truncation. `hn.py`, `discourse.py` and
`reddit.py` listings all truncate **silently**.

### Row 3 — the escalation sequence: five install sites, four sequences

| site | file:line | installs | re-runs ladder | re-gates |
|---|---|---|---|---|
| tier-loop win | `fetcher.py:1254` | transport | yes | later |
| archive, pre-gate | `fetcher.py:1062` | transport | yes | later |
| **archive, post-gate** | **`fetcher.py:1058`** | content+transport | **NEVER** | `:1059` |
| browser | `fetcher.py:2136-2151` | content+transport | conditional | `:2151` |
| paid | `fetcher.py:2236-2253` | content+transport | conditional | `:2253` |

**LIVE, and documented history repeating.** `_install_rendered_fields`'s own
docstring (`:1262-1282`) is a confession: *"THE ONLY PLACE THIS COPY IS WRITTEN.
There were FOUR, and they disagreed."* The field-copy was collapsed; **the
sequence around it was not.** `fetcher.py:1299-1333` documents the identical bug
one level up — skipping the extraction ladder "starved four consumers"
(`content_candidates`, `other_pages`, `record_count`, `record_set`), fixed on the
tier-loop path 2026-07-28. **The archive-post-gate path still skips it.** Same
bug class, fifth copy, still live.

Diagnostics also disagree: appended only-on-success in `_dispatch_archive:899`,
always in browser `:2105` / paid `:2210` / tier loop `:1183`.

### Recurs but SHALLOW — do not promote

- **Empty-failure `TierResult` literal**, 17 sites. Semantics agree; only
  `content_type` on a zero-byte body drifts three ways. `browser.py:120`
  extracted it once and stopped. **Widen `_common.empty_result` and delete**
  (−78 lines, interface ≈ 0). A literal, not a concept.
- **URL matching**, 9 handlers — irreducibly site-specific. But collapse the two
  duplicated reddit path regexes (`reddit.py:65` vs `_reddit_html.py:33`) and the
  two suffix-strippers (`reddit.py:755` vs `_reddit_html.py:72`), which
  **disagree** on trailing slashes.
- **Hint dedup** `any(h.code == X ...)` ×11 — at most a `.has(code)` method.
- **Cap constants**, 25 — each domain-specific. Not a shape.
- **`del cookies` / `del settings` / lazy `from ..tiers import`**, 8+8+18 sites —
  one signal, that `handlers → tiers` is a real import cycle. Moving
  `TierResult`/`Rendered` to `tiers/_types.py` deletes all 18 mechanically.

### The inverse — built once, or more general than any caller needs

| mechanism | file:line | finding |
|---|---|---|
| hedged archive race | `archive.py:130-162` | 33 lines of task-group + memory-object-stream for **two** upstreams, **one** caller. Docstring says "capacity-1"; code says `max_buffer_size=2`. |
| `TierResult` | `tiers/__init__.py:59-108` | 25 fields, ~18 written by exactly one tier. A union type spelled as a wide struct — and why the empty-failure literal has 17 sites each picking 5 of 25. |
| `Tier.fetch(**kwargs)` | `tiers/__init__.py:125-133` | 5 of 7 tiers discard `proxy_url` + `conditional_extras`. `**kwargs: Any` means a misspelled kwarg is silently dropped by every tier. |
| `_load_tier_registry` | `tiers/__init__.py:144-177` | calls `load_surface_sorted`, then **re-walks the same packages with pkgutil** because the shelf loader "sorts but drops priority". Duplicated module walk at import; fix belongs upstream. |
| `listing_has_more` | `listing_oracle.py:73-85` | 13 lines + long rationale, **zero handler call sites**. arXiv, the one handler using `listing_oracle`, ignores it. |
| `PromptTemplate.render` | `prompts.py:58-77` | documents two render modes, ships three template shapes. `JUDGE_V1:409` is 3-slot and **cannot** be rendered — `judge.py:165` calls `.format()` by hand. One accidental `.format()` on `system` would corrupt every `{` in the 5.8 KB `_ROUTER_SCHEMA_DOC`. |
| `ProxyPool.close()` | `proxy_routing.py:167-169` | `async def` returning `None`; docstring "No-op today". |
| `_NitterInstanceFailure` | `twitter.py:96-119,160` | exception raised solely to register a breaker failure, caught one frame up. Reddit's failover (`reddit.py:198-260`) is hand-rolled `if`s. Two failover architectures, one instance each. |
| `budget: list[int]` | `habr.py:189,204,208` | one-element list as a mutable counter box; no sibling tree-renderer has a budget at all. |
| `_RenderResult` | `reddit.py:512-536` | reddit-private clone of `Rendered`, where six handlers use a dict + `Rendered.from_dict`. Third representation of one payload. |
| `_prune_wire` | `models.py:790` | a generic helper with `if key == "retrieval_incomplete"` hardcoded inside it. |
| dead manifests | `_manifests/llm_providers/` | contains **only `__pycache__`** (`openai_compatible.pyc`); likewise `browser_backends/__pycache__/{rebrowser,_common}.pyc`. Sources gone, bytecode a `pkgutil.iter_modules` walk can still see. Verify the loader cannot resurrect them. |

Resource lifecycle is **not** over-built — only two classes hand-roll
`_lock`/`_ensure`/`close` (`cookie_jar.py:173-193`, `llm_resource.py:212-307`);
the third is the shelf's. Correctly below the bar.

### Additional bugs surfaced, independent of any promotion

1. `fetcher.py:1058` — archive-post-gate never runs the extraction ladder (Row 3).
2. `reddit.py:884-923` — no `challenge_verdict`; a snooserv interstitial returns
   `Verdict.ok`. Exactly what `wikipedia.py:87-90` warns about in prose.
   **→ change `close-wire-level-adr-0009-leaks`**
3. `hn.py:128` vs `:150` — `content_md`'s H2 count and `headings[1]`'s count can
   disagree; a title-less hit desynchronises them. Three sibling answers to the
   same problem (`discourse.py:233` `parts.insert`, `reddit.py:580` line-count),
   one wrong.
4. `arxiv.py:283`/`:297` — the cap `25` as two independent literals. Change one
   and the header lies.
5. `jina.py:92-95` and `raw.py:40-43` — `if status >= 500: connection_error`
   followed by `if status >= 400: connection_error`. Dead branch, copy-pasted
   into two files.
6. 401/403 maps four ways across six mappers (`paid_auth_error` / `paywall` /
   `connection_error` ×2); `browser._upstream_error_verdict:89` drops 429 →
   `rate_limited` entirely. **`map_non_ok` returns `body=b""` on non-2xx**, so
   wikipedia/discourse/hn/arxiv discard a 403 challenge body before anything can
   inspect it.
7. `extractor.py:538-595` — wrong-type reporting via `_note_malformed` applied to
   **2 of 8** fields, against that function's own stated invariant. Three
   incompatible LLM-parse failure contracts: log-and-degrade `:610`, **silently**
   degrade `:458`, retry-then-raise `judge.py:204`.
8. `discourse.py:227` — up to 50 `next_links` vs a 10 cap everywhere else,
   pinned green by `handler_probe.py:177`.
9. `github.py:226` catches only `BadRequest` for the README where four sibling
   guards catch `GitHubException` — a rate-limited README aborts the whole repo
   fetch. **→ change `close-wire-level-adr-0009-leaks`**
10. `reddit.py:652` `" ".join` vs `_reddit_html.py:255` `" · ".join` — the same
    thread renders two different header formats depending on whether Zyte or RSS
    served it.

### Ledger verdict

Take one: **Row 1**, the pure lift. Take two: add **Row 3**, not for the lines
but because `fetcher.py:1262-1282` already records that this exact bug happened,
got half-fixed, and is still live in the copy nobody collapsed.
