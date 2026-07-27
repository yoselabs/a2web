# Design — a2web shelf sweep (Phases B–D complete, E–F pending)

The full read-only substrate inventory and per-candidate verdict, produced per
`shelf/docs/runbooks/onboard-a-consumer.md`. Phases B (inventory), C (classify
against the CATALOG, never against another consumer) and D (the four directions)
are **done**; this document is their output and the input to Phase E.

Verdict vocabulary: **PROMOTE** (generic, catalog lacks it — valid at n=1) ·
**ADOPT** (shelf has it, passes DEEP·STABLE·WINS) · **EVOLVE** (a shelf piece
almost fits; grow its contract) · **KEEP** (product moat, or evolving would
distort the piece).

## The verdict table

| # | Candidate | Capability | Stop-caring | Catalog gap? | Direction |
|---|---|---|---|---|---|
| 1 | `_plugin.py:1-179` | Declarative plugin discovery + graceful "not configured" degradation | **Yes** — 5 unrelated surfaces already share it | Nothing for extension-point discovery | **PROMOTE** |
| 2 | `packages/llm_extract/wobble/` | Tolerant-but-auditable LLM JSON parsing, per-field policy, opaque parsed token | **Yes** | `anyllm` returns `Completion.text` and stops | **PROMOTE** |
| 3 | `packages/llm_cost_guard.py` | Refuse an expensive `(provider, model)` before the call | **Yes** | `anyllm` already owns the price table + the `LLMProvider` Protocol this wraps | **EVOLVE `anyllm`** |
| 4 | `packages/browser_backends/` | Render a URL with a real JS engine, engine-agnostic | **Yes** (seam) | No browser piece at all | **PROMOTE seam now** / **HOLD drivers** (real-launch gate, §5.2b) / **KEEP** stealth policy |
| 5 | `packages/llm_extract/cache.py` | Memoize a completion on `(content, prompt, model, template)` with TTL | **Yes** | `http-cache` is the HTTP analogue; nothing caches completions | **PROMOTE** |
| 6 | `packages/llm_extract/prompts.py:33-80` (`PromptTemplate` only) | Render a versioned prompt into cache-breakpoint-aware parts | **Yes** | `anyllm` **already owns `PromptParts`** | **EVOLVE `anyllm`** |
| 7a | `domain.py` rendering (`_render_rows`, `_rows_to_md_*`, `_normalize_commerce_row`, `_is_commerce_shaped`) | Render rows as a surface **a2web's extractor LLM** reads well | **No** — the consumer is a2web's own prompt | — | **KEEP** (Q3, answered 2026-07-22) |
| 7b | `domain.py` normalization (`_collect_ld_entries`, `_find_product_or_item_list`, `_microdata_to_ld_shape`, `_opengraph_to_markdown`) | LD-JSON / microdata / OpenGraph → uniform row dicts | **Yes** | `json-in-html` extracts and stops | **EVOLVE `json-in-html`** — deferred, needs boundary design |
| 8 | `packages/block_detector.py` | Bot-wall / challenge fingerprinting | **No** | — | **KEEP** — named moat; the pattern catalogue *is* the value |
| 9 | `packages/proxy_routing.py` | Host/tier route table + per-proxy quarantine | **No** (doctrine) | — | **KEEP** — but see open Q4 |
| 10 | `packages/escalation.py` | Typed escalation signal | **No** | — | **KEEP** — the `Literal` *is* a2web's tier vocabulary |
| 11 | `llm_extract/{extractor,judge,router_payload,errors}.py` | Answer extraction, router payload, LLM-as-judge | **No** | — | **KEEP** — prompts + payload schema are the product |
| 12 | `_manifests/**` | The plugins themselves | **No** | — | **KEEP** — only the framework (#1) is substrate |
| 13 | `cache.py` | a2web's cache-dir + schema-migration policy | **No** | Already an adopted seam | **KEEP** — this is what a post-adoption seam should look like |
| 14 | `actions/{playbook,terminal,empty}.py` | Escalation planning, terminal classification, empty promotion | **No** | — | **KEEP** — ADR-0009/0012/0015 *are* the product |
| 15 | `state.py:218-243` (`ResourceUnavailable`, `unavailable_lazy`) | Uniform "optional resource not provisioned" failure | Weak yes | — | **KEEP (sighting)** — ~25 lines, and `sunset-a2kit-dependency` is reshaping its substrate |
| 16 | `handlers/_common.py` | `FetchVerdict → Verdict` mapping | **No** | — | **KEEP** |
| 17 | `domain.py` remainder (`compute_profile_hash`, `is_live_only`, `rewrite_captcha_host`, `strip_reader_prefix`, `is_search_shaped`) | Captcha pre-routing, reader-prefix stripping | **No** | — | **KEEP** — DuckDuckGo rewriting and jina-prefix stripping are the fetch product |

## Proposed package boundaries

### 1. `plugin-surface` (T1 primitive)

Name per resolution 0008 — `_plugin`/`PluginManifest` says nothing to a reader who
has never seen a2web; "plugin surface" names the deliverable.

> **Capability:** Stop caring how an app discovers its own extension points —
> declare one `MANIFEST` per plugin file, get back a ready-to-use registry, with
> "not configured" plugins dropped before they reach it.

```python
class Unavailable(NamedTuple): reason: str          # a VALUE, not an exception
@dataclass(frozen=True, slots=True)
class PluginManifest(Generic[T]):
    name: str; protocol: type[T]; factory: Callable[..., T | Unavailable]
    requires: tuple[str, ...] = (); priority: int = 0
def load_surface(surface_path: str, protocol: type[T], context: object) -> dict[str, T]
def load_surface_sorted(surface_path: str, protocol: type[T], context: object) -> list[tuple[str, T]]
```

**Extraction note:** drop `settings_prefix` — `_plugin.py:70-73` documents it as
"no-op today", i.e. an invented field. The promote gate is *extracted, never
invented*.

### 2. `llm-wobble` (T1 primitive; stdlib only)

> **Capability:** Stop caring that an LLM's JSON envelope arrives fenced,
> prose-wrapped, or missing fields — one funnel decodes it, applies a per-field
> recovery policy, logs every recovery, and hands back a token no hand-rolled
> parse can forge.

```python
class WobbleTolerance(StrEnum): STRICT | DERIVE | DEFAULT | SKIP
@dataclass(frozen=True, slots=True)
class WobblePolicy: tolerance: WobbleTolerance; default: Any = None; derive: Callable | None = None
Wobbled = NewType("Wobbled", _Parsed[Any])          # opaque; the funnel is the ONLY constructor
def parse_with_policy(raw, *, policies, into, boundary, model) -> Wobbled
def parse_list_with_policy(raw, *, item, boundary, model, strip_fences=True) -> Wobbled
def unwrap(w) -> Any
def recovered_fields(w) -> tuple[str, ...]
```

**Two extraction decisions:** (a) `apply_policy` (`_internal.py:186`) is
self-declared "back-compat shim" — **do not carry it across**; (b) `emit_wobble`
hardcodes `logging.getLogger("a2kit")` — parameterize the logger name.
`_policies.py`'s tables are a2web product and stay home.

### 3. `anyllm` evolution (one tag, monotonic — adds, removes nothing)

> **Capability delta:** Stop caring whether the model you are about to call is one
> you can afford; and stop caring how a versioned prompt becomes
> cache-breakpoint-aware `PromptParts`.

```python
# anyllm.cost
class CostViolation(RuntimeError): ...
@dataclass(frozen=True, slots=True)
class CostPolicy:
    allow: tuple[tuple[str, tuple[str, ...]], ...]
    def permits(self, provider_id: str, model: str) -> bool
def assert_within_budget(provider_id, model, policy=DEFAULT_POLICY) -> None
def with_cost_guard(provider_id, provider: LLMProvider, policy=DEFAULT_POLICY) -> LLMProvider

# anyllm.prompt
@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str; version: int; system: tuple[str, ...] = ()
    user_template: str = ""; cache_prefix_template: str = ""; tail_template: str = ""
    def render(self, *, content: str, ask: str) -> PromptParts
```

**One re-key required.** a2web's `DEFAULT_POLICY` (`llm_cost_guard.py:61-67`) is
keyed on a2web's *manifest* names (`"claude-code"`, `"anthropic"`,
`"openai_compatible"`) — the exact vocabulary drift `ProviderName`
(`anyllm/base.py:29-45`) was added to end. Inside anyllm the policy keys on
`ProviderName`; a2web then closes the shelf backlog's open "adopt
`anyllm.ProviderName`" item as a side effect.

### 4. `any-browser` (T1 any-lib)

> **Capability:** Stop caring which JS engine renders a page — one `render()`
> across the Playwright-API family and raw CDP, returning a rich `RenderedPage`
> (html + final URL + status + wall time + bytes + JS-executed +
> challenged-subresource count), never raising for routine failure.

```python
class RenderOutcome(StrEnum): ok | timeout | error | unavailable
@dataclass(frozen=True, slots=True) class BackendCookie: ...
@dataclass(frozen=True, slots=True)
class RenderedPage:
    outcome: RenderOutcome; html=""; final_url=""; status_code=0; js_executed=False
    wall_ms=0; bytes_transferred=0; detail=""; subresource_blocks=0
@runtime_checkable
class BrowserBackend(Protocol):
    name: str
    async def render(url, *, cookies, budget_s, js_heavy, scroll_to_stable=False) -> RenderedPage
    async def __aenter__/__aexit__
class PlaywrightBackend: ...   # launch_fn-parameterized; host-LRU context pool, idle reaper, stderr capture
class ZendriverBackend: ...    # CDP family
def chromium_launch(async_playwright_fn); def patchright_launcher(); def camoufox_launcher()
```

**Stays in a2web (the moat):** `select_backend*` (`state.py:116-150`), the
`_manifests/browser_backends/*` gating, the fast/robust rung split, the
`RenderOutcome → Verdict/OperatorHint` mapping, and every escalation decision.
The seam is not the moat.

**Scope (Q1, corrected 2026-07-26): promote the SEAM now; HOLD the drivers
behind a real-launch gate.** There is no open bakeoff — it closed 2026-06-27
keeping *two complementary* engines. But the first answer ("seam AND both
drivers") inferred driver safety from a suite that days later passed a fully
dead robust rung (zendriver couldn't launch on the pinned version; CHANGELOG
[Unreleased] 2026-07-25). The seam (`BrowserBackend`, `RenderedPage`,
`BackendCookie`, `RenderOutcome`) is pure types — promote now. The drivers
(`PlaywrightBackend`, `ZendriverBackend`, launchers) promote only once a shelf
CI lane launches BOTH engines against a real page with skips forbidden. See the
Q1 correction in `proposal.md`. Q2 (`subresource_blocks`) is answered (keep +
neutralize).

### 5. `llm-cache` (T1 primitive, on `sqlite-resource` + `anyllm`)

> **Capability:** Stop caring how to memoize an LLM completion — a TTL'd sqlite
> table keyed on `(content, prompt, model, template)` that shares the caller's
> connection and preserves the call's token/cost/latency accounting.

```python
def hash_text(text: str) -> str
class LlmCache:
    def __init__(self, conn: aiosqlite.Connection, *, ttl_s: int = 900)
    async def ensure_schema() -> None
    async def get(content_hash, ask_hash, model_id, template_name) -> Completion | None
    async def put(...) -> None
    async def evict_expired() -> int
    async def size() -> int
```

**Shape change at extraction** (generic-first, resolution 0010): return an
`anyllm.Completion` rather than a bespoke `ExtractionCacheRow` — the row's fields
already *are* `Completion`'s.

### 6. `structured-data-md` (T2 composite on `json-in-html`) — see open Q3

```python
def render_markdown(payload: JsonPayload) -> str
def json_fallback(data: dict | list, *, cap: int = 20_000) -> str
```

## What the shelf gains

- **A plugin/extension-point primitive it has none of** — the highest
  future-leverage item here. Every future app with providers, backends, handlers
  or sinks gets discovery + graceful degradation instead of re-inventing `pkgutil`
  walking and a "not configured" convention.
- **The missing half of the LLM stack** (see `proposal.md` Why).
- **A browser tier the catalog completely lacks** — the natural sibling of
  `http-fetch`, plugging into `browser-cookies` (which already produces the cookie
  rows) and `content-extract` (which consumes the html).
- **Closure of the `json-in-html` half-story** — extraction without rendering
  leaves every consumer writing the same schema.org walker.

## Method notes

- Compared against the **CATALOG**, never against another consumer, per the
  runbook. Cross-consumer overlap is optional confirmation, not a gate.
- Where a2web's version is a **richer superset** of an existing package, the
  arrow reverses and the superset is promoted (resolution 0007 monotonicity) —
  that is why `llm_cost_guard` and `PromptTemplate` are EVOLVE, not PROMOTE.
- ~~The shelf catalog on `main` is currently **stale**~~ — **resolved
  2026-07-22.** `work/a2kay` merged (shelf `8fbed17`), so `lean-wire`,
  `page-tsv`, `mcp-result-wire` and `a2effect` are all on `main` and in the
  catalog. a2web has since adopted `lean-wire` and repointed `a2effect` off the
  a2kit repo. Re-checked: none overlap the candidates above, so the verdict
  table stands unchanged.
- **Prose is the one artifact nothing tests, and this sweep leaned on it.**
  Three of the four open questions turned out to be about docstrings, not
  design. Q4 asked whether a2web ran two overlapping health mechanisms — it
  does not; `build_breakers` claimed "per-host / per-proxy / global" and only
  the first has ever had a call site. Q1 asked when to promote the browser
  drivers "mid-bakeoff" — the bakeoff closed 2026-06-27 keeping both engines,
  but three of four headers still said `TRANSIENT … deleted if it loses`, and
  one named an extra that had been deleted. Q3 cut the other way: the candidate
  was settled *by* a docstring that told the truth (`json_to_markdown_rows`
  naming the extractor LLM as its consumer), which is what exposed the
  rendering half as product.

  The pattern is the same one the sunset kept hitting from the other side:
  **a golden proves a surface has not changed; a docstring does not even prove
  that.** An audit that reads module headers as evidence will manufacture
  questions from finished work. Verify a prose claim against a call site, a
  setting, or an archived change before letting it gate a decision — every one
  of these three took a single grep to settle.

## The witness rule (Fable-5 review, 2026-07-26)

A council review of this sweep's whole arc named the failure the accidental
finds keep exposing: **oracle endogeneity** — when a check is derived from the
same beliefs as the artifact it checks, their errors are correlated and the
comparison is structurally blind to the error they share. It splits into two
mechanisms, and the project has only ever defended against one:

- **Mechanism B — unknowns resolve to green.** Skips, vacuous walks, the absent
  container surface: "couldn't verify" silently becomes "verified." Every guard
  rule already in `CLAUDE.md` (`_walk` floors, "a guard must find something",
  accepted-delta liveness) attacks B.
- **Mechanism A — endogenous oracles.** Golden, fake, docstring: the oracle is a
  formalized copy of the author's belief, so it agrees with the author's bug.
  The zendriver fake appended `--no-sandbox`; the code passed `--no-sandbox`;
  both encoded one wrong belief, and the test agreed with the dead rung. **No
  rule in the project defends against A** — and every A-failure was fixed by
  authoring *more* artifacts of the same belief, the one move that cannot help.

The durable rule, paired with the existing non-vacuity rule:

> **Every load-bearing claim needs at least one witness of independent
> provenance.** A golden is never a witness (it is a snapshot of the artifact).
> A fake is never a witness (it is the author's belief about the dependency). A
> docstring is anti-witness. A witness is: a second mechanical renderer of the
> same source (the derived-CLI catch), the real substrate in an environment
> *obligated* to run it (CI-with-Chromium, container smoke), or a second
> consumer (a shelf adopter, a second MCP client). "Found by accident" is the
> system reporting where detection actually comes from — provenance diversity,
> not test volume.

Shelf consequences, adopted into the tasks above:
- `any-browser` **drivers** wait for a real-launch CI lane, skips forbidden (§5.2b).
- Pure-Python promotions (`plugin-surface`, `llm-wobble`, `llm-cache`, the
  `anyllm` evolutions) each get a **foreign-soil gate**: the shelf CI installs
  the package STANDALONE, with a2web NOT importable, and runs its acceptance
  suite there — the first time any of this code is verified off its home soil,
  and the cheapest available exogenous witness for the genericity claim.
- **Consumer-zero:** "generic" stays an unverified claim until a second real
  project adopts the package. Promotion order should follow adopter readiness —
  a tagged package with zero external adopters is an untagged belief in a
  registry accruing authority. (Prefer promoting first whatever `insights-trail`
  or `a2kay` will actually consume next.)

## Spike: how many "greens that prove nothing" exist today? (2026-07-26)

The witness rule above is only worth adopting if it *finds* things, so it was
run as a falsifiable spike against the live suite before any promotion. Three
sub-hypotheses, each checked against a foreign-provenance witness (grep of real
call sites + the real installed dependency APIs, never a belief):

- **H1 — skips resolve to green. CONFIRMED, severe.** `addopts = -m "not
  browser"` deselects the browser marker from the default run; `make check`
  uses that default; CI runs only `make check`; and there is no
  `make test-browser` step anywhere in CI. So the *entire browser tier's*
  real-launch behaviour was verified by zero automated runs — the four smokes
  skipped locally on missing binary and never ran in CI. Not a zendriver
  quirk; the whole floor. FIXED this session: the `browser-gate` CI job +
  `A2WEB_REQUIRE_BROWSER=1` skip→fail policy (commit `14aeef1`).
- **H2 — permissive fakes (laxer than the real dependency). CLEAN.** A sweep
  of all 10 external-dependency test doubles, each verified against the
  installed library's real signatures/raise-conditions, found no instance
  beyond the already-fixed zendriver `Config`. The promotion candidates
  specifically (`llm_cost_guard`, `wobble`, `cache`, `_plugin`,
  `browser_backends`) are clean — the scariest class for the shelf (a
  permissive fake travelling with a promoted package) is absent. This is the
  single biggest risk-reducer for the promotion: it says the endogeneity
  finding was one bug, not a pervasive habit.
- **H3 — shipped-surface has no witness. PARTIALLY CONFIRMED.** The publish job
  DOES now run `version()` inside the actual built image (a real foreign
  witness, added after the `__version__`-stale-by-47-releases bug). But the
  running-container surface — `/health` answering, `a2web-serve` starting, the
  browser launching *inside* the image — has no CI witness; the `/health` test
  is source-level (asserts the Dockerfile path string, does not run the
  container). Deferred, filed as follow-up: a container smoke that boots the
  image and curls `/health` + drives one real `query` over HTTP.

Net: the rule found one severe standing gap (H1, now closed) and one deferred
one (H3), and cleared the highest-stakes worry (H2). The promotion can proceed
on the pure-Python pieces with real confidence; the browser drivers wait for
the shelf-side port of the H1 fix (§5.2b).
