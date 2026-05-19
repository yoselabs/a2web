# a2kit feedback — round 11 (v0.39 review)

From: a2web v0.7 on `a2kit v0.39`
Audience: a2kit dev (AI agent or human — written self-contained either way)
Date: 2026-05-16
Context: read after round 10 (`A2KIT_FEEDBACK_v0.38.md`). v0.39 shipped four of the six round-10 frictions in one release. This round is the **adoption report** — what landed clean, what we retracted, plus one small new friction surfaced during the migration.

The v0.39 release was the smoothest single migration of all eleven rounds. The `[ctx-ceremony-drop, testing-helpers, health-contract-pin, Lazy[T]-in-factories]` bundle hit the consumer code as `~80 LOC of deletes` and `~20 LOC of renames`, with **414 tests still green** and **wire surfaces unchanged**. Thanks for the discipline.

---

## Adoption results — round 10 frictions

| Friction | v0.39 status | a2web status |
|---|---|---|
| **A1 — `a2kit.testing.lazy(value)`** | Shipped | Adopted ✓ (4 callsites swapped + helper deleted) |
| **A2 — `a2kit.testing.ambient_for_tests`** | Shipped | Adopted ✓ (autouse re-export, see Note 1 below) |
| **A3 — `a2kit.testing.resolve(app, T)`** | Shipped | **Not adopted** — reconsidered (see Note 2 below) |
| **B — ambient ctx unconditional** | Shipped | Adopted ✓ (`del ctx` ceremony gone everywhere) |
| **E — `Lazy[T]` in factory params** | Shipped | **Retracted by a2web** (see Note 3 below) |
| **F — health-check resource entry** | Shipped (docs + pin) | Adopted ✓ (`_ensure()` + try/except gone) |
| **C — canonical surface promotion** | Not shipped | Restated below |
| **D — `pydantic.Field` description sugar** | Not shipped | Restated below |

---

## Note 1 — `ambient_for_tests` autouse re-export pattern (small new friction)

The docstring on `_ambient_for_tests_impl` documents the consumer-side autouse re-export pattern:

```python
from a2kit.testing import ambient_for_tests as _a
ambient_for_tests = pytest.fixture(autouse=True)(_a.__wrapped__)
```

This works. We adopted it. But two small issues:

1. **`__wrapped__` access is a quirk**, not an obvious API. `ambient_for_tests` is itself a `pytest.fixture(...)`-decorated function; to re-wrap it with `autouse=True`, the consumer reaches through `.__wrapped__` to get the bare function back. This is pytest's documented mechanism, but it reads as "fragile internal-API access" to a reader who hasn't seen the pattern.

2. **The 95% case (autouse) requires consumer ceremony.** Every consumer that wants project-wide ambient writes the same three-line re-export. The docstring even calls this out — "consumers wanting project-wide ambient re-export with `autouse=True` in their own conftest.py" — which suggests the framework knows this is the common case.

### Ask

Either:

**(a) Ship a pre-decorated autouse variant:**
```python
from a2kit.testing import ambient_for_tests_autouse  # one-line consumer import
```
…that's `pytest.fixture(autouse=True)` baked in. Consumers who want non-autouse keep using `ambient_for_tests`. Two flavors, both first-class.

**(b) Ship a tiny helper:**
```python
ambient_for_tests = a2kit.testing.autouse(ambient_for_tests)
```
…a one-arg helper that does the `__wrapped__` dance internally. Consumer doesn't touch `__wrapped__`.

Either way, the pattern collapses from three lines + a quirky import to one line.

Priority: low. The current pattern works. This is friction-removal, not bug.

---

## Note 2 — `a2kit.testing.resolve(app, T)` is right, but A3 was misdirected

We filed Friction A3 as "`make_default_state` boilerplate every consumer reinvents." On v0.39 adoption, we reconsidered and **did not adopt** `resolve(app, T)` for that helper.

The reasoning:

- `resolve(app, T)` is correct for tests inside an `async with app:` scope.
- a2web's `make_default_state(...)` is for tests **outside** any app scope — they construct `AppState` synchronously and call `fetch()` directly without composing an app at all.
- These are **two different use cases**, not one. `resolve` doesn't replace `make_default_state`; it's the right tool for the *other* shape.

The filing was sloppy. We assumed `make_default_state` was boilerplate-to-be-deleted; on closer look, it's the deliberate "AppState without an app" test seam. `resolve` is still useful — for tests we *don't currently have*. If/when a2web grows tests inside an app scope, they'll use `resolve` directly.

### Why this matters for a2kit

Don't conclude from A3 that "a2kit shipped a helper that consumers didn't adopt." `resolve(app, T)` is the right primitive — it just doesn't replace what we said it would replace. Worth keeping in mind for future friction triage: **the consumer's "boilerplate" call-out may be miscategorized; the framework should ship the primitive and let consumers map it to use cases.**

No ask. Recording the lesson.

---

## Note 3 — Friction E retraction (the meta-signal worth flagging)

We filed Friction E ("`AppState` is forced to split into always-on vs lazy") in round 10. v0.39 shipped `Lazy[T]`-in-factory-params recognition, which would have enabled `AppState` to absorb `Lazy[BrowserPool]` + `Lazy[LlmExtractorResource]` as fields.

On v0.39 adoption, we **retracted Friction E**. The architectural split — `AppState` for always-on data, separate `Lazy[T]` DI kwargs at the tool seam for orthogonal services — is correct design, not friction:

- `AppState` is a **data bundle**, not a service locator. Service lifecycles, lazy resolution, and conditional resolution are service concerns; they don't belong on a `@dataclass(slots=True)`.
- Tools declare exactly the services they use as Lazy DI kwargs — the tool signature *is* the contract. Funneling everything through AppState hides which tool needs the browser vs the LLM.
- Every test that constructs `AppState` would otherwise have to fake all six fields (including ones it doesn't exercise). Keeping AppState narrow keeps the test seam narrow.

v0.39's `Lazy[T]`-in-factory shipping is still a real spec drift fix. It just doesn't change a2web.

### Why this matters for a2kit

**The framework correctly shipped the capability.** The friction was a consumer-side misdiagnosis — we mistook a correct architectural split for "forced verbosity." When this lesson generalizes:

- When a consumer files "the framework forces me to write N lines," the framework author should ask: *is the N-line shape correct design, or is it accidental ceremony?* If correct, ship the capability quietly (for consumers who do want it) but **don't pressure adoption**.
- When the framework ships a capability in response to a friction, the consumer should **re-validate the friction was correct** before adopting. v0.39 shipping doesn't mean a2web must adopt; it means a2web *can* adopt if the friction still holds.

a2kit got this right by shipping `Lazy[T]`-in-factory as a quiet capability (no migration nag, no deprecation of the old shape). a2web got the second half right by re-validating before adopting. Worth documenting this contract somewhere — maybe in OPERATIONAL_CONTRACTS or `ANTIPATTERNS.md` — so future round-N filings have a "did we misdiagnose?" checkbox.

No ask. Recording the lesson.

---

## Health-check body shape — small DX note

After dropping `_ensure()`, our body is:

```python
@app.health_check
async def _check_sqlite(sqlite: SqliteResource) -> a2kit.HealthResult:
    """Framework enters sqlite via __aenter__ on kwarg resolution
    (OPERATIONAL_CONTRACTS Q-HealthChecks)."""
    _ = sqlite
    return a2kit.HealthResult.ok()
```

The `_ = sqlite` line is awkward — it's a "use the parameter so ty/ruff doesn't flag it as unused" trick. The body has no meaningful work; the entire probe value is in the *signature* (kwarg → resource entry).

Two possible directions:

1. **Accept the awkwardness.** It documents the readiness assertion. `_ = sqlite` reads as "I received this resource and that was the test."
2. **Ship a no-body shorthand**, e.g.:
   ```python
   @app.health_check(probe=SqliteResource)
   ```
   …which would auto-resolve `SqliteResource` and return `HealthResult.ok()` if resolution succeeds. No body needed.

(1) is fine. (2) is a polish wish — not raising it formally, just noting the body now exists purely to satisfy "a function must have a body." A future round might consolidate this.

---

## Carry-overs from round 10

Both still deferred, no fresh signal:

### Friction C — canonical `a2kit.Lazy`, `a2kit.LddEmission`

`a2kit.testing.*` IS now the canonical surface for testing primitives — partial win. But `Lazy` itself still lives at `a2kit.packages.di.Lazy`, the most-touched DI primitive at the tool seam. `LddEmission` (sink-author surface) still at `a2kit.packages.ldd.LddEmission`. Promote to top-level re-exports; document `a2kit.packages.*` as private (stdlib `_thread` / `threading` convention).

### Friction D — `pydantic.Field` description sugar

`routers.py` is still 60-70% `Annotated[T, pydantic.Field(description="...")]` ceremony. `a2kit.desc(...)` or `a2kit.param(description=..., default=...)` would shave each param from 8-12 lines to 2-3, without adding a new primitive (just sugar over pydantic.Field).

Both parked in `A2KIT_WISHES_DEFERRED.md` entries 7 and 8.

---

## Migration status

a2web on a2kit v0.39:

- 414 tests green
- 89.29% coverage (≥85% gate)
- `uv run a2web health` → `{"status": "ok"}`
- `uv run a2web web fetch --url=...` returns structured `FetchResponse`; LDD events stream with ambient ctx bound (no `ctx` declaration in the tool)
- Zero `ctx: ToolContext` / `del ctx` / `_ensure()` / `lazy_of` residue (grep audits clean)
- Archived in `openspec/changes/archive/2026-05-16-a2kit-v039-migration/`

---

## v0.39.3 adoption (2026-05-19) — Note 1 shipped

a2kit v0.39.3 (2026-05-19) shipped `ambient_for_tests_autouse` exactly as proposed in Note 1 option (a) — a pre-decorated autouse peer of `ambient_for_tests`, strictly additive. Documentation moved to `OPERATIONAL_CONTRACTS Q-Ctx` per Note 1 ask (c).

**a2web adoption result: 5-line conftest delta, 490 tests still green, zero behavior change.**

Before (v0.39.0–v0.39.2):
```python
from a2kit.testing import ambient_for_tests as _ambient_inner
_ambient_ldd = pytest.fixture(autouse=True)(_ambient_inner.__wrapped__)
```

After (v0.39.3+):
```python
from a2kit.testing import ambient_for_tests_autouse  # noqa: F401
```

The `__wrapped__` quirk is gone from a2web's conftest. The one-line import reads exactly like what it does. Friction filed → shipped → adopted in three days end-to-end. This is the friction loop working as designed.

The v0.39.3 commit also names the **Shape A3 / Shape E** taxonomy in `CONSUMER_FEEDBACK_DOCTRINE` (under C3), drawn from round-11's own misdiagnoses (A3 mis-filing of `resolve()` use case, E mis-filing of `AppState`-vs-DI-kwarg split as forced verbosity). Self-referential and useful — future filings can lead with "Shape A3 risk:" to flag the priors during proposal review. **No consumer action needed.**

Carry-overs C (canonical surface promotion) and D (`pydantic.Field` description sugar) remain parked. We have no fresh signal on either. v0.39.2's MCP auth boundary work (ADRs + lintable pattern) lands but doesn't intersect a2web — recording for completeness.

### Status update — round 10 adoption table

| Friction | v0.39 status | a2web status |
|---|---|---|
| A1 — `lazy(value)` | Shipped | Adopted ✓ |
| A2 — `ambient_for_tests` (per-test) | Shipped | Adopted ✓ |
| **A2′ — `ambient_for_tests_autouse`** | **Shipped v0.39.3** | **Adopted ✓ (2026-05-19)** |
| A3 — `resolve(app, T)` | Shipped | Not adopted (Shape A3 mis-filing) |
| B — ambient ctx unconditional | Shipped | Adopted ✓ |
| E — `Lazy[T]` in factories | Shipped | Retracted (Shape E mis-filing) |
| F — health-check resource entry | Shipped | Adopted ✓ |
| C — canonical surface promotion | Parked | No fresh signal |
| D — `Field` description sugar | Parked | No fresh signal |

---

## Field report — v0.7 link-discovery (2026-05-18)

Two days after the v0.39 migration landed, a2web v0.7 shipped the `next_links` link-discovery feature: new pydantic response field, new boundary type at the packages seam, five site handlers extended, an `ask=` extractor extension that returns a fenced JSON block, plus an additive `next_links: bool = True` tool param. Roughly **+1,500 LOC across 17 files**, 490 tests, lint + ty clean, coverage 87%.

**Framework friction observed: zero.** Logging this as a positive data point on the v0.33+ tool surface and the v0.36+ DI shape:

- `@a2kit.read(open_world=True, title=...)` with a new `Annotated[bool, pydantic.Field(description=...)]` param defaulting to `True` worked first-try on both `fetch` and `fetch_raw`. MCP schema regenerated cleanly. No `Param(...)` ghosts, no `idempotent=` rejection. Adding a backwards-compatible bool to an existing tool is now genuinely boring — exactly what we wanted from round 7's tool-decorator surface.
- `await fc.llm_extractor()` resolved once in `_phase_extract_answer` and the extracted resource threaded into a helper. No second resolution, no Lazy-handle re-entry. v0.36 lazy first-use is doing its job; nothing to file.
- Ambient ctx never came up — the new feature emits no events of its own; the existing `StageStarted` / `StageEnded` calls in the extract phase kept working through unconditional ambient binding.

We deliberately surfaced the new LLM boundary type `LlmNextLink` inside `packages/llm_extract/` and converted to the domain `NextLink` pydantic at the a2web seam (per `test_packages_independence`). This is an a2web architectural rule, not an a2kit ask — but worth noting that the rule held under a substantive feature without forcing a framework escape hatch.

**Adoption confidence on v0.39 is now two features deep, not just the migration itself.** Treating this as a deferred adoption check for round 10 — the v0.39 surface holds under both a migration AND a green-field feature ship.

---

## What we're NOT asking for

To save you reading: explicitly parked, no fresh signal this round.

- Streaming response API (round 3)
- `@a2kit.read(timeout="60s")` (round 3)
- `app.singleton(..., teardown=fn)` (round 7 — superseded by v0.36 lazy CM)
- Sharper `AmbientContextMissing` message for missing-ctx-param (round 7 — superseded by v0.39 unconditional ambient ctx)

---

## Lesson summary

Two meta-lessons from this round worth bottling for future feedback discipline:

1. **Friction filings can be misdiagnosed.** Friction A3 was a sloppy filing (helper vs. use-case mismatch). Friction E was a correct architectural split mistaken for forced verbosity. Future rounds: include a "did we misdiagnose?" checkbox.

2. **Capability shipping ≠ adoption pressure.** When a2kit ships a capability in response to a friction, the consumer should re-validate the friction. v0.39's `Lazy[T]`-in-factory shipping is correct as a capability; a2web's non-adoption is correct as a design choice. Both can be true.

Thanks for the smoothest migration yet.
