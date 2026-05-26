# Tasks — unify-plugin-manifests

Umbrella change. Each surface migration is a sub-PR sequenced below.

---

## Step 0 — Confirm `wobble-typed-funnel` and `arch-fitness-functions-bootstrap` landed

- [ ] 0a. `wobble/` folder exists; `make check` includes `make arch`.
- [ ] 0b. CLAUDE.md "Never" list shortened to test pointers.

## Step 1 — Build the framework (`src/a2web/_plugin.py`)

- [ ] 1a. Define `PluginManifest[T]`, `Unavailable(NamedTuple)`, `load_surface[T]`.
- [ ] 1b. Spike `pkgutil.iter_modules` on `src/a2web/tiers` from a scratch test — confirm discovery works under uv's src-layout install.
- [ ] 1c. Spike `_slice_settings` against the current `AppSettings`. If `AppSettings` doesn't have nested groups, decide between (i) implementing nested groups now, (ii) deferring `settings_prefix` to a follow-up. Record decision in design D3 update.
- [ ] 1d. Unit-test `load_surface` against a fixture surface dir (`tests/fixtures/plugin_surface/`) with 3 plugins, one of which returns `Unavailable`. Confirm registry has 2 entries.
- [ ] 1e. `make check` — green.

## Step 2 — Sub-PR A: Migrate LLM Providers (highest drift, smallest surface)

- [ ] 2a. Add `MANIFEST = PluginManifest(name="anthropic", protocol=Provider, factory=build_anthropic_provider, requires=("anthropic_key",), settings_prefix=None)` to `providers/anthropic.py`. `build_anthropic_provider(settings)` returns `Provider | Unavailable` — replaces the env-read-at-ctor.
- [ ] 2b. Same for `providers/claude_code.py`.
- [ ] 2c. Rewrite `llm_resource.py::_build`: call `load_surface("a2web.packages.llm_extract.providers", Provider, settings)` once, pick by `settings.llm_provider`.
- [ ] 2d. Rewrite `_pick_provider` in `llm_eval/__main__.py` similarly.
- [ ] 2e. Retire `AnthropicProvider.__init__(api_key_env=...)` env-read.
- [ ] 2f. Retire `LLMNotAvailable` raised at construction (factory returns Unavailable instead). Keep the exception for runtime LLM call failures.
- [ ] 2g. Update `packages/llm_extract/providers/__init__.py` `__all__` to expose only the Protocol + Response (no concrete classes). Domain code now goes through the manifest registry.
- [ ] 2h. Grandfather-violations retirement: remove ~5 entries from `tach.toml`'s ignore list (the `llm_resource.py → providers.anthropic` lines).
- [ ] 2i. Tests: existing provider tests adapt to the new factory shape. `make check` — green.

## Step 3 — Sub-PR B: Migrate Eval Systems

- [ ] 3a. Split `llm_eval/systems.py` into `llm_eval/systems/{webfetch.py, a2web_detail.py, a2web_extract.py}`. Each exports `MANIFEST = PluginManifest(name=..., protocol=EvalSystem, factory=..., requires=...)`.
- [ ] 3b. `EvalSystem` becomes a real Protocol (today it's structural; promote to `@runtime_checkable Protocol`).
- [ ] 3c. Rewrite `llm_eval/__main__.py::_amain`: build `systems = load_surface("a2web.llm_eval.systems", EvalSystem, settings)`, filter by `args.mode` against `MANIFEST.name`.
- [ ] 3d. Retire the `if mode == "default": ... elif mode == "baseline": ...` ladder.
- [ ] 3e. Tests at `tests/llm_eval/test_systems.py` adapt. `make check` — green.

## Step 4 — Sub-PR C: Migrate LDD Sinks

- [ ] 4a. Add `MANIFEST` to `events/sinks.py` (`otel_sink`) and `llm_eval/live_sink.py` (`LiveSink`).
- [ ] 4b. `events/sinks.py` factory checks OTel SDK import; returns `Unavailable("opentelemetry sdk not installed")` if absent. Replaces the current `_TRACER is None` check.
- [ ] 4c. `server.py` boots `load_surface("a2web.events.sinks", Sink, settings)` and passes the resulting `tuple(registry.values())` to `app.ldd.add_sink(...)`. Retires the direct `from .events import otel_sink` import.
- [ ] 4d. `llm_eval/__main__.py` similarly loads sinks; bench-only sinks (LiveSink) live under `llm_eval/sinks/` which is a separate surface dir.
- [ ] 4e. Tests: `make check` — green. LiveSink continues to drive stdout in bench mode.

## Step 5 — Sub-PR D: Migrate Handlers (longest)

- [ ] 5a. For each of the 10+ handlers (`reddit`, `hn`, `arxiv`, `wikipedia`, `github`, `habr`, `discourse`, …): add `MANIFEST = PluginManifest(name=..., protocol=Handler, factory=build_X_handler, requires=(), settings_prefix=None)` at module bottom.
- [ ] 5b. Each `build_X_handler(settings)` is a thin wrapper: if the handler needs a token (`github_token`), it returns Unavailable when missing OR returns a handler with degraded rate limits.
- [ ] 5c. Rewrite `handlers/__init__.py`'s linear-search to use `load_surface`. The `matches(url)` dispatch loop stays the same; just iterating over registry values.
- [ ] 5d. Retire `_HANDLERS` tuple.
- [ ] 5e. Tests at `tests/handlers/` adapt. Run full handler test suite. `make check` — green.

## Step 6 — Sub-PR E: Migrate Tiers (last; consistency only)

- [ ] 6a. Add `priority: int = 0` field to `PluginManifest` (was deferred until tiers needed it).
- [ ] 6b. For each tier in `tiers/`: add `MANIFEST = PluginManifest(name=..., protocol=Tier, factory=build_X_tier, requires=..., priority=N)`.
- [ ] 6c. Retire `REGISTRY` dict + `TIER_ORDER` tuple from `tiers/__init__.py`. Replace with `load_surface` + sort by priority.
- [ ] 6d. Archive + browser tiers (out-of-band dispatch) keep their non-in-TIER_ORDER status via `priority=-1` or a `dispatch="out_of_band"` field — decide during impl.
- [ ] 6e. `make check` — green. `make bench` smoke-tested (single URL) for regression.

## Step 7 — Cleanup

- [ ] 7a. Retire `unavailable_lazy(...)` helper from `state.py`.
- [ ] 7b. Simplify `Resources` frozen dataclass — heavy resources now come from `REGISTRY` rather than dedicated fields.
- [ ] 7c. Update CLAUDE.md "Architecture (a2kit v0.39 mediated)" section: replace per-surface descriptions with a single "all extension points use `PluginManifest`" paragraph + pointer to `_plugin.py`.
- [ ] 7d. Add the archon rule from design D7: `test_plugin_modules_only_declare_manifest.py`.

## Step 8 — Verify

- [ ] 8a. `make check` end-to-end green.
- [ ] 8b. `make bench` 5-URL smoke. Confirm registry-driven dispatch produces byte-stable envelopes vs prior runs.
- [ ] 8c. Confirm `tach.toml`'s ignore list shrank substantially (most provider/cookie violations retired).

---

## Done definition

- [ ] `_plugin.py` exists with `PluginManifest`, `Unavailable`, `load_surface`.
- [ ] Five surfaces migrated: providers, eval-systems, sinks, handlers, tiers. (Wobble policies intentionally not migrated — design D6.)
- [ ] `unavailable_lazy(...)`, `_HANDLERS`, `REGISTRY`, `TIER_ORDER`, env-read-at-ctor patterns all retired.
- [ ] `tach.toml` ignore list reduced by at least the ~25 provider/cookie violations.
- [ ] CLAUDE.md updated.
- [ ] Archon rule enforces no module-level side effects in plugin files.
- [ ] `make bench` regression-free.
