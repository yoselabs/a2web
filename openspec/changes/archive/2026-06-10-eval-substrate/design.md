## Context

The extraction-fidelity program (`docs/architecture/extraction-fidelity-program.md`)
makes a series of hypotheses about extraction quality (ADRs 0004–0007) that must be
**measured before they are cemented**. Today there is no deterministic instrument:
`make bench` (`python -m a2web.llm_eval`, corpus `eval/corpus.yaml`) is live-network
and LLM-judged, capability tests use small hand-authored fixtures with a *faked* LLM,
and there is no replay/VCR layer. This change builds the instrument.

The design is shaped by two corrections from the design session:

- **Evals are tests, not product.** No `a2web eval` CLI verb, no MCP tool. The replay
  substrate lives in the test + `eval/` layer and is driven by `make` targets. Nothing
  eval-specific ships in the wheel's product surface.
- **The instrument must out-live routing changes.** A case frozen today may resolve at
  the raw-HTML tier; a later code change may make it escalate to browser. If only the
  raw layer was frozen, replay would have nothing to give the browser tier. Two distinct
  problems follow: (1) a **coverage gap** when routing outruns what was frozen, and (2) a
  **re-capture confound** — when you re-freeze, the site has also drifted, so you cannot
  tell whether *your code* or *the world* changed the answer.

Current egress chokepoints (confirmed in code) are few and clean:

| Tier   | Egress                                         | Freezable unit                              | DI-provided? |
|--------|------------------------------------------------|---------------------------------------------|--------------|
| raw    | `packages/http_fetch.fetch_bytes()`            | `FetchOutcome` (body, ct, status, final_url, headers, verdict, conditional_hit) | no (free fn) |
| jina   | HTTP via the same `fetch_bytes` chokepoint     | `FetchOutcome`                              | no (free fn) |
| browser| `BrowserPool.acquire(url)` → `page.content()`  | rendered `html` (str)                       | **yes** (`BrowserPool`) |
| archive| HTTP (Wayback CDX / archive.ph)                | `FetchOutcome` / response bytes             | no (free fn) |
| llm    | `LlmExtractorResource` → provider call         | provider request/response                   | **yes** (`LlmExtractorResource`) |

## Goals / Non-Goals

**Goals:**

- Deterministic, bit-reproducible replay of the **real** orchestrator/gate/ladder/escalation
  logic against frozen egress — so tier routing and escalation are exercised, not stubbed.
- A cassette that survives routing changes for the page-classes that escalate (the coverage-gap fix).
- A re-capture flow that separates *inputs* (drift with the site) from *expectations* (what we assert),
  and surfaces a **diff for re-blessing** instead of silently overwriting (the confound fix).
- Multiple corpuses with a failure-class taxonomy (A clean-schema / B source-omits-or-JS / C schema-lies),
  plus the existing happy-pass regression set.
- An explicit `make check` (deterministic, gates) vs `make bench` (LLM-judged, informational) split,
  with the judge model pinned and recorded.
- A one-command add-a-case workflow, because many cases will be added over time.

**Non-Goals:**

- The architectural changes themselves (changes 2–5). This is the instrument only.
- A product-facing CLI/MCP surface for evals.
- Re-rendering the browser at replay time (snapshots are frozen, never re-rendered — see Decisions).
- Full cross-source atomization, WebMCP, price provenance (program backlog).

## Decisions

### D1 — Freeze at the egress boundary; replay the real logic above it

The cassette records *every external interaction the pipeline could make for a URL* — a
multi-protocol VCR. Replay reads frozen bytes at each tier's egress; **everything above
the egress (orchestrator, gate, extraction ladder, escalation decisions) runs unmodified.**

*Why over the alternative:* the obvious cheaper seam is to freeze the produced
`FetchResponse` and replay *that*. Rejected — it replays the *output*, not the *decision*.
The entire point (and the user's stated fear) is testing the **escalation logic** under
frozen inputs; that requires running the real escalation against frozen tier-inputs, which
only the egress seam allows.

### D2 — The LLM is just another egress; record it, don't fake it

The Anthropic / claude-code provider call is frozen like any other egress. In full-replay
mode the *answer itself* is reproduced byte-for-byte, so the deterministic axes (contract
shape, exact token cost, tier path taken) assert **exactly**.

*Why over the alternative:* "faked LLM" (today's capability-test approach) hand-authors a
response that drifts from reality and can't catch real router-JSON wobble. "Recorded real
LLM" is strictly better — it is a real provider response, frozen. The live LLM only comes
out for `make bench` quality judging.

### D3 — Interception is test-side; production stays clean

- `BrowserPool` and `LlmExtractorResource` are **DI-provided**, so a replay run uses
  `client.override(BrowserPool, CassetteBrowserPool)` / `client.override(LlmExtractorResource, CassetteLlm)`.
  Clean, no monkeypatch.
- `fetch_bytes` is a **free function**, not a resource. It gets **one** centralized patch in the
  replay harness (a `pytest` fixture that points `fetch_bytes` at the cassette reader). It is the
  single documented async chokepoint for HTTP, so the patch surface is one symbol.

*Why over the alternative:* introducing production `Transport` ports purely to serve evals
would push eval concerns into the shipped product — against "evals are tests, not shipped in."
The DI overrides + one chokepoint patch keep all replay machinery test-side.

### D4 — Inputs vs expectations split; refresh = diff + bless

```
  eval/corpus/<corpus>/<case>/
    case.yaml          question · url · class(A/B/C/JS) · tags · expected-tier-path
    inputs/            ← snapshot of the WORLD; drifts with the site; `refresh` updates
      raw.http         frozen FetchOutcome (status/headers/body)
      rendered.html    frozen browser DOM (present iff captured — see D5)
      jina.txt         (on-use)
      archive.json     (on-use)
      llm/*.json       recorded provider request+response
    baseline/          ← what we ASSERT
      contract.json    deterministic shape: fields present, token bounds, tier path  (gates make check)
      answer.md        reference answer for LLM-judged axes        (informational, make bench)
    meta.yaml          per-layer capture timestamp, source URL, content-hash, sizes
```

`refresh` re-captures `inputs/`, re-runs replay, and emits a **diff** of the new
extracted answer vs the blessed `baseline/` — never a silent overwrite. Re-blessing reuses
the repo's existing env-flag idiom: `make bless` does `A2WEB_BLESS_CONTRACTS=1 pytest …`;
the eval analogue is `A2WEB_BLESS_EVAL=1`. This makes re-fixing a reviewed ~30-second
operation and dissolves the confound: you *see* what changed before accepting it.

### D5 — Browser-freeze is a policy knob, not an either/or

Default per page-class, overridable per-case:

- **Always** capture raw HTTP (cheap base).
- **Eager** capture of `rendered.html` for cases tagged `commerce` / `js` / `spa` — exactly
  the classes that escalate, so their browser path is always replayable (the coverage-gap fix
  for the cases that need it).
- **On-use** for static-doc classes (arxiv/wikipedia) and for jina/archive layers.
- `--all-tiers` capture flag forces eager-everywhere when wanted.

The floor is non-negotiable: when replay hits a tier with no frozen entry, it raises a
**loud, structured failure** — `"case <id> escalated to tier=browser but no rendered snapshot;
run: make eval-refresh CASE=<id>"` — and **never** falls through to the network. A coverage
gap is always a red, one-command-fixable test, never silent non-determinism.

### D6 — Storage: commit plain, no gzip

Fixtures are committed under `eval/corpus/` in plain form. Git's packfile already zlib-compresses
blobs, so gzip buys little; worse, it turns fixtures binary and **kills the human-readable diff**
that D4's bless flow depends on. Committed (not gitignored) is required: anything gitignored cannot
deterministically gate `make check` in CI without extra fetch infra. A per-case size warning flags
unusually large bundles.

### D7 — make-check vs make-bench split

- **`make check`** (already runs `test-cov` = pytest): deterministic replay tests assert
  contract shape, exact token cost, and tier-path on frozen fixtures (with recorded LLM). They gate.
- **`make bench`** (`python -m a2web.llm_eval`, unchanged lane): LLM-judged answer-quality/clarity,
  live, informational. The judge model id is **pinned and recorded per run** so quality deltas aren't
  confounded by judge drift.
- New dev-only targets: `make eval-capture URL=… Q=… CORPUS=… ID=…`, `make eval-refresh CASE=…`.

### D8 — Multi-corpus, extends the existing corpus

`eval/corpus.yaml`'s entry shape (slug/url/class/task/needs/criteria/next_links_expected) is the
seed for `case.yaml`. The new layout groups cases into named corpuses (`regression/`, `breaking/`)
and adds the frozen `inputs/`+`baseline/` per case. Hepsiburada is the first regression case.

## Risks / Trade-offs

- **Re-capture confound** → D4 diff+bless makes site-drift visible before acceptance; deterministic
  `contract.json` is robust to cosmetic site changes, so most refreshes don't touch expectations.
- **Browser render is non-deterministic** (fingerprint/timestamps) → we freeze a *snapshot* and replay
  it as a fixed input; the browser is **never** launched at replay time. Determinism holds.
- **`fetch_bytes` patch couples to a symbol location** → acceptable, centralized in one fixture; the
  arch culture already treats it as the single HTTP chokepoint, so it is stable.
- **Cassette staleness** → cases rot as sites change; `make eval-refresh` + the diff is the maintenance
  path. The regression set's value is the *contract shape*, which rots slowly.
- **Cache-prefix interaction** (ADR-0005) → recorded LLM responses must key on the prompt; when content
  changes the recorded response is stale and must be re-recorded. Handled by the refresh flow; the
  cache-prefix byte-equality concern itself is owned by change `multi-source-extraction-input`, not here.
- **Repo growth** → plain-committed HTML is small under git zlib; rendered DOM is the heavy layer and is
  captured eagerly only for the classes that need it (D5), bounding growth.

## Migration Plan

Incremental, each step independently useful:

1. **Raw-tier replay (MVP):** cassette format + `fetch_bytes` patch + `make eval-capture`/`replay` +
   Hepsiburada seeded as the first `regression` case + the deterministic contract test gating `make check`.
2. **Browser override:** `CassetteBrowserPool` via `client.override`, eager-capture policy (D5), loud gap.
3. **LLM recording (D2):** `CassetteLlm` override, byte-exact answer replay, exact token/contract assertions.
4. **breaking/ corpus + refresh/bless:** B/C/JS cases, `make eval-refresh` diff + `A2WEB_BLESS_EVAL=1`.
5. **bench split (D7):** judge-model pinning/recording on the existing `make bench` lane.

Rollback: the substrate is additive and test-side; reverting any step removes tests/fixtures with no
product impact.

## Open Questions

- **Module home:** does the replay harness live under `tests/eval_replay/` (pure test) or a non-packaged
  top-level `eval/` python module reused by both pytest and the capture script? Leaning `tests/` for the
  replay/assert side, a thin `eval/_capture/` dev script for capture (not in the wheel). Resolve in tasks.
- **LLM recording key:** prompt-hash vs (url, tier) tuple — must coexist with the `EXTRACT_*` cache prefix
  without leaking per-page variation into the cached prefix. Coordinate with change 3's constraints.
- **Refresh drift severity:** should `make eval-refresh` classify a diff as cosmetic vs answer-changing
  (auto-accept contract-stable, force-review answer-changing), or always require manual bless? Default to
  always-review for v1; revisit if it becomes a chore.
