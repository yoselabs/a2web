## Context

`tiers/raw.py` welds the project's full HTTP capability into `RawTier.fetch` — `curl_cffi.AsyncSession(impersonate="chrome120")`, proxy wiring, exception → closed-verdict mapping, per-host `purgatory` breakers, conditional-GET headers from cached extras. Nothing of it is a callable primitive; it's a closure inside one method on one class.

Handlers, written later, had no shared transport to reach for. Nine handlers (`reddit`, `hn`, `arxiv`, `github`, `wikipedia`, `twitter`, `discourse`, `habr`, `v2ex`) each construct their own `httpx.AsyncClient(timeout=..., follow_redirects=True, headers={"User-Agent": state.settings.default_ua})`. No impersonation, no proxy, no breakers, no block detection.

Probe results from the just-shipped work made the gap visible:

- `linux.do/latest.json` returns `200 application/json` to `curl_cffi` Chrome-impersonated; to plain `httpx` it returns the Cloudflare/anti-AI banner HTML. `DiscourseHandler` is plain `httpx`; the handler returns `not_found` and the cascade falls through to `raw` (which would have impersonated and succeeded — but raw doesn't run if a handler claimed the URL even on failure unless explicitly escalated).
- Four handlers ship a hand-rolled HTML→text regex (`_cooked_to_md`, `_html_to_md`, `_strip_html`, `_text_of`); the Discourse handler renders `fancy_title` without routing it through its own converter, so `&rsquo;` survives.
- The `record_extract` detector computes a heading link (`primary_link`) and knows where headings are (`_own_has_heading` for guard (c)). `Record` carries `primary_link` but the renderer is given only flat `text + links + depth` — the heading text isn't separated from the score / age / tag smush.

Test strategy completes the picture: every handler test monkeypatches `httpx.AsyncClient.get` with a fixture. The `linux.do` failure is invisible to `make check` *by construction*, not by oversight.

## Goals / Non-Goals

**Goals:**
- One transport primitive used by `RawTier`, `ArchiveTier`, and every handler — curl_cffi impersonation, proxy, breakers, closed verdicts.
- One HTML-fragment converter — link-preserving, entity-decoded, lxml-backed — used wherever a handler renders HTML.
- A live-network verification path that exercises transport, so transport bugs can fail a check (not just a manual probe).
- Carry the detector's structural decomposition through to the renderer; quit re-flattening what was just located.
- Zero wire / envelope change. Same `FetchResponse` / `AskResponse` shapes, same `NextLink` kinds.

**Non-Goals:**
- Refactoring handlers into pure renderers with a declarative fetch manifest. Reddit's "`.json` → fall back to `old.reddit` → signal archive" needs imperative control flow; the minimal cut that fixes the symptoms is "handlers call a shared primitive," not "handlers become declarative."
- Removing `httpx` from `pyproject.toml`. Defer — kept-or-dropped decision after migration lands.
- Smarter per-record parsing (a generic "this span is the title, this is the score") for issue 4 beyond surfacing the heading. The detector finds *structure* generically; semantic field-typing is a separate problem.
- A new retry layer. The cascade already retries at five named layers; the primitive must not invent a sixth.
- Cache integration in the primitive. `http_cache` stays at the orchestrator level; the primitive just accepts `conditional_extras` and emits the right headers.

## Decisions

### D1 — The primitive is curl_cffi, full stop
`curl_cffi` defeats Cloudflare / JA3-fingerprint blocking; `httpx` does not. The whole point of `raw`'s transport choice was anti-bot capability; handlers running *before* `raw` and using a weaker client is the structural fault to fix. The primitive ships only the curl_cffi path. **Alternative rejected:** an httpx variant with a richer TLS adapter — chasing a moving target, and curl_cffi already solved it for raw.

### D2 — Primitive shape: callable that returns bytes + closed verdict
```
async def fetch_bytes(
    url, *, headers, timeout_s, proxy_url=None, cookies=None,
    conditional_extras=None, breaker=None,
) -> FetchOutcome
```
`FetchOutcome` is a small dataclass: `body, content_type, status_code, final_url, headers, verdict, conditional_hit`. Crucially **not** `TierResult` — `TierResult` carries orchestrator-shaped fields (`pre_rendered`, `next_links`, `from_archive`, `handler_name`, …) that a primitive has no business filling in. `RawTier` and `ArchiveTier` map `FetchOutcome → TierResult`; handlers map `FetchOutcome → TierResult` too (the small mapping is in the handler, where the handler knows what kind of result it makes). **Alternative rejected:** returning `TierResult` directly — couples the primitive to the orchestrator's domain model and tempts handlers to skip the mapping and fill in fields that aren't theirs.

### D3 — Primitive owns transport, nothing more
In: impersonation, proxy wiring, per-host breaker integration (caller passes a breaker handle, primitive uses it), exception → closed verdict, conditional-GET header building from extras. Out: caching, retry, parsing, content-type policing (the "expect HTML" check stays in `RawTier` because that's raw's policy; handlers expect JSON). One responsibility — get bytes, or a verdict.

### D4 — Handlers stay imperative
A handler is still a class with `matches()` + `fetch()`. `fetch()` now calls `await fetch_bytes(...)` (one or several times, in any order — anyio task groups still work; reddit's old.reddit fallback still works) instead of constructing `httpx.AsyncClient`. The pure-renderer split is a worthwhile future direction; this change deliberately doesn't pull on it because the minimal cut already fixes issues 1 + 2 + 3 and dedups 9 clients. **Alternative rejected:** declarative fetch manifest — kills handler control flow, breaks reddit, larger blast radius than the symptoms warrant.

### D5 — `RawTier` becomes a thin shell over the primitive
Current `RawTier.fetch` keeps its outer signature (orchestrator contract) but its body shrinks to: build headers (with conditional-GET extras), acquire the breaker, call `fetch_bytes(...)`, then either `RawTier`-specific content-type policy (`"html" not in content_type → content_type_mismatch`) or `TierResult(...)`. **Alternative rejected:** keeping raw's inline curl_cffi as the "canonical" use and writing a *second* primitive for handlers — two implementations is exactly the problem we're fixing.

### D6 — `html_fragment` is lxml-backed, not regex
The four hand-rolled strippers all use sequenced regex (`re.sub` for `<p>`, `<br>`, `<a href>`, then strip `<[^>]+>`). Robust enough most of the time, fragile when HTML is malformed or attributes contain `>` etc. The shared converter parses with `lxml.html.fragment_fromstring` and walks the tree. Public surface:
```
def to_markdown(html: str, *, base_url: str | None = None) -> str   # link-preserving
def to_text(html: str) -> str                                      # entity-decoded plain text
```
Both decode entities (no `&rsquo;` ever surviving), fold `\xa0` → space, return `""` on empty. `to_markdown` makes hrefs absolute when `base_url` is given. The four hand-rolled strippers are deleted. **Alternative rejected:** keep regex but extract it — still fragile, doesn't earn the consolidation effort.

### D7 — Title normalization is a spec-level requirement, not a polish
The Discourse title bug was a one-line oversight. To prevent the *class*, the `site-handlers` spec gains: handler-rendered titles SHALL be entity-decoded via the shared converter. The requirement makes the bug a spec violation, not a polish miss. Habr / V2EX / future handlers fall in line by spec, not by remembering.

### D8 — Live-contract probe is a `make` target, not a CI test
`make handler-probe` (parallel to `make bench`, outside `make check`): walks the handler registry, picks a representative URL per handler, runs `await handler.fetch(url, state=...)`, asserts `verdict == Verdict.ok` and `pre_rendered.content_md` non-empty. Live network. **Not** in `make check` because (a) it's flaky by nature (real hosts), (b) it's slow, (c) `make check` must stay deterministic and offline. Probe-discipline written into the spec: a probe finding records the *method* used (`curl_cffi-impersonated`, `httpx-anonymous`, with-cookies, with-auth) — the method is the finding. **Alternative rejected:** mock-real-host fixtures with VCR / cassette — still doesn't catch the live failure mode (linux.do challenges *current* clients; a recorded cassette is a snapshot of past success).

### D9 — `Record` carries the heading; renderer leads with it
Today's `Record(text, links, primary_link, depth, markdown)` → `Record(text, links, heading_text, heading_link, depth, markdown)`. `primary_link` was always the heading link conceptually; the rename makes that explicit and adds `heading_text` (the heading element's own-scope text). `render_record` becomes:
```
- [{heading_text}]({heading_link})        ← lead line (if heading_link else just heading_text)
  {remaining own_text minus heading_text}
  {remaining links}
```
The detector already iterates own-scope elements and finds the heading element (guard (c), `_heading_link`) — exposing its text costs one more `_collapse(_own_text(heading_el, sig))` call.  **Alternative rejected:** keeping `Record` flat and making the renderer parse `text` to find the heading inside it — re-doing the detector's work, fragile.

### D10 — Migration order: primitive → converter → probe → record
Phases are independent enough to apply in any order, but this sequence has the best feedback loop: (1) primitive unblocks anti-bot for all handlers; (2) converter lands the title fix and removes the four hand-rolled strippers; (3) live-probe then validates (1)+(2) against real hosts in one pass — proving the primitive defeats CF on linux.do is the cleanest closing assertion of phase 3; (4) record-structure is independent and can land last as a quality improvement.

## Risks / Trade-offs

- **curl_cffi concurrency from one handler.** Habr/V2EX/Discourse use `anyio` task groups for parallel article + comments fetches. The primitive must support being awaited concurrently — `curl_cffi.AsyncSession` is fine for sequential, but per-session concurrent calls need either separate sessions or session-per-call. → Mitigation: the primitive constructs a fresh `AsyncSession` per call (raw's current pattern). Sessions are cheap; this preserves anyio task-group safety.
- **Per-host breakers now binding on handler hosts.** Reddit, HN, Habr, etc. don't currently touch the breaker space; under the primitive they will. A flaky handler-API host could trip the breaker for the whole host and affect the raw tier on the same host. → Mitigation: this is actually the correct behaviour — if `habr.com` is consistently failing, both handler and raw should back off. The breaker per host is the right granularity.
- **Phase 1 is a wide migration.** 9 handlers + raw + archive touched in one phase. → Mitigation: phase split by file (one commit per ~3 handlers, each `make check` green); the primitive's behaviour is byte-identical to raw's current curl_cffi block, so any regression is a migration bug, not a design one.
- **Renaming `Record.primary_link` → `heading_link`.** Internal type. The only consumer outside the package is `fetcher._records_to_next_links` (already shipped) — migrates with the rename in phase 4. → Mitigation: phase 4 lands atomically; no cross-package transient.
- **lxml fragment parsing perf.** Four hand-rolled regex strippers were chosen for speed on small fragments. lxml is heavier per call. → Mitigation: a topic with 200 comments is 200 small `cooked` fragments → ~milliseconds total, noise next to the network fetch (hundreds of ms). The robustness win is bigger than the per-fragment cost.
- **Handler-probe flake.** Real hosts go down, get rate-limited, change shapes. The probe in CI would flap. → Mitigation: `make handler-probe` is **not** in `make check`. It's an operator tool — run on demand, after handler changes, before release. The spec defines it as a manual probe, not a CI gate.
- **`fetch_bytes` API churn.** Establishing a new primitive locks a surface. → Mitigation: the surface is deliberately the *smallest* useful one (`url, headers, timeout, proxy_url, cookies, conditional_extras, breaker`); these are exactly what raw already passes. New needs become explicit kwargs later.

## Migration Plan

1. **Phase 1 — primitive + tier migration.** `packages/http_fetch/` with `fetch_bytes` + `FetchOutcome`. `tiers/raw.py` and `tiers/archive.py` switch to it. Existing raw / archive tests stay green (behaviour-identical). Then 9 handlers migrate; each handler test stays green (still monkeypatched at the seam — see phase 3). `make check` green.
2. **Phase 2 — converter + handler render cleanup.** `packages/html_fragment/` with `to_markdown` + `to_text`. Discourse / Habr / V2EX / HN drop their hand-rolled strippers. Title-normalization spec requirement enforces `to_text(fancy_title)` etc. `make check` green.
3. **Phase 3 — live-contract probe.** `make handler-probe` target + small Python entrypoint walking the registry. Probe-discipline convention written into the `handler-live-probe` spec. The probe MUST succeed on linux.do (the named target the just-shipped Discourse handler failed on) — that is the closing assertion of phases 1 + 2.
4. **Phase 4 — structure-aware Record.** `Record.heading_text` + `heading_link` (rename of `primary_link`); detector populates both; `render_record` leads with them; `fetcher._records_to_next_links` migrates to the new name; `record-extraction` spec updated. `make check` green; re-run `make bench` (lobste records should read as `[title](url)\n meta` instead of the flat smush).

Rollback per phase: revert the phase's commit. Phase 1's revert restores `tiers/raw.py`'s inline curl_cffi and per-handler `httpx`; the other phases are layered on top and revert cleanly.

## Open Questions

- After phase 1, does `httpx` still pull its weight as a dep? After all handlers migrate, the only remaining `httpx` import would be... none in the project source (handlers were the only callers). Drop from `pyproject.toml`? Defer to a follow-up cleanup change.
- Should the primitive also accept a `block_detector` callback (so a CF challenge page returns `Verdict.blocked` directly instead of `ok` + suspicious HTML)? Tempting — would harden issue 2 further — but it conflates transport with classification. Defer; the gate already classifies on the body in the orchestrator.
- The pure-handler-renderer split (transport vs render fully separated, `RenderHandler` is a pure function over a `FetchedBundle`) is the next logical move once the primitive lands. Worth scoping when the next handler arrives, or sooner if the test-strategy gap reappears.
