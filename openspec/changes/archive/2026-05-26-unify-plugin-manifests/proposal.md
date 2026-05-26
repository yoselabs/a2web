# unify-plugin-manifests

## Why

The audit found six "extension point" surfaces drifted into three different shapes:

| Surface | Registration | Settings flow | Unavailability |
|---|---|---|---|
| **Tiers** (`tiers/`) | `REGISTRY` dict + `TIER_ORDER` tuple | via `AppState` | `TierResult(no_match=True)` |
| **Handlers** (`handlers/`) | `_HANDLERS` tuple | via `state.settings` reads | `TierResult(no_match=True)` (via `SiteHandlerTier`) |
| **LLM Providers** (`packages/llm_extract/providers/`) | none (manual ctor) | **reads env at `__init__`** | raises `LLMNotAvailable` at construction |
| **LDD Sinks** (`events/sinks.py`, `llm_eval/live_sink.py`) | passed as `tuple` to `app.ldd.add_sink(...)` | stateless | silent drain (no-op when SDK absent) |
| **Wobble Policies** | per-boundary local dicts | none | per-policy `WobbleSkip` exception |
| **Eval Systems** (`llm_eval/systems.py`) | manual ctor in `__main__.py` | constructor args | error-as-data in `SystemResult` |

The drift is low-stakes today (2 providers, 3 eval systems). It becomes high-stakes the moment we add a third LLM provider (Bedrock? Gemini? Ollama?) or fourth eval system — each new entry has to re-discover which pattern to follow.

Per ADR-0001 (Pattern 2), the fix is a single declarative shape that all six surfaces converge on: **typed plugin manifests with capability-aware factories**. Inspired by Dagster Components (Oct 2025 GA), Litestar `Provide`, and VS Code contribution points. Each plugin file exports one `MANIFEST` constant. App boot reflects on manifests, calls factories with sliced `AppSettings`, drops anything returning `Unavailable` *before it reaches the registry*.

## What changes

### New framework: `src/a2web/_plugin.py`

The single source of truth for the manifest shape:

```python
@dataclass(frozen=True, slots=True)
class PluginManifest[T]:
    name: str                                            # "anthropic", "raw", "jina", "reddit", ...
    protocol: type[T]                                    # the SPI (Tier, Handler, Provider, Sink, ...)
    factory: Callable[[AppSettings], T | Unavailable]    # capability-aware constructor
    requires: tuple[str, ...] = ()                       # capability keys, e.g. ("anthropic_key", "browser_pool")
    settings_prefix: str | None = None                   # which AppSettings slice to bind

class Unavailable(NamedTuple):
    reason: str

def load_surface[T](
    surface_path: str,           # "a2web.tiers" or "a2web.packages.llm_extract.providers"
    protocol: type[T],
    settings: AppSettings,
) -> dict[str, T]:
    """Walk every module under surface_path, import its MANIFEST,
    call factory(settings.bind(manifest)). Return {name: instance}
    skipping Unavailable returns."""
```

### Migrate surfaces one per session

Order chosen by drift severity + blast radius:

1. **LLM Providers** (most drifted, smallest surface — 2 providers).
   - Each provider file (`anthropic.py`, `claude_code.py`) exports `MANIFEST = PluginManifest(name=..., protocol=Provider, factory=build_anthropic_provider, requires=("anthropic_key",), settings_prefix="llm")`.
   - `llm_resource.py` calls `load_surface("a2web.packages.llm_extract.providers", Provider, settings)`. Returns `dict[str, Provider]`. Pick by `settings.llm_provider`. The current `_build` method shrinks from ~50 LoC of fallback ladder to ~10 LoC of dict lookup.
   - Retires `llm_resource.py:78-79` reach into provider submodules — domain only knows the `Provider` protocol from the package surface.
   - Retires the bespoke `AnthropicProvider.__init__(api_key_env=...)` env-read; settings get sliced + passed to factory.

2. **Eval Systems** (no registry today; 3 systems).
   - `WebFetchBaseline`, `A2WebDetail`, `A2WebExtract` each become a module under `llm_eval/systems/` with its own `MANIFEST`.
   - `__main__.py`'s `--mode` flag dispatches by manifest name instead of hardcoded `if mode == "default": ...` ladder.
   - New systems require zero edits in `__main__.py`.

3. **LDD Sinks** (currently 2: `otel_sink`, `live_sink`).
   - Each sink module exports `MANIFEST`. The OTel sink's `capability` is `"otel_sdk_present"`; the live sink's is empty.
   - `server.py` calls `load_surface("a2web.events.sinks", Sink, settings)` for prod, `llm_eval/__main__.py` adds the live sink at bench boot.
   - Retires the manual `app.ldd.add_sink(otel_sink)` import-line in `server.py`.

4. **Wobble Policies** (5 policies after `wobble-typed-funnel`).
   - The `_policies.py` table style stays; the manifest shape applies at one level up. Each policy "plugin" is the boundary that uses it, not the policy itself.
   - Realistically: keep wobble's `_policies.py` as-is; manifest pattern doesn't extend cleanly here. Mark as "intentionally out of scope" in tasks.md.

5. **Handlers** (10+ handlers).
   - Each handler exports `MANIFEST = PluginManifest(name="reddit", protocol=Handler, factory=build_reddit_handler, requires=(), settings_prefix=None)`.
   - The `handlers/__init__.py` linear-search loop becomes `load_surface(...)` + `handler.matches(url)` over the returned dict's values.
   - This migration is the longest of the five; expect 1 session per 3-4 handlers.

6. **Tiers** (5 tiers).
   - Tiers already have a registry. Migration is mostly cosmetic: replace `REGISTRY` dict + `TIER_ORDER` tuple with `load_surface` + a `priority` field on `PluginManifest`.
   - The migration's value is consistency, not bug fix. Sequenced last for that reason.

### Retire the drift sites

After surfaces 1-5 are done, the following all collapse to the manifest pattern:

- `llm_resource.py`'s `_build` method → 10-line dict lookup
- `_pick_provider` in `llm_eval/__main__.py` → manifest lookup
- `unavailable_lazy(...)` helper → retired (Unavailable result type replaces it)
- `LLMNotAvailable` exception → retired or downgraded (factory returns `Unavailable`, not raise)
- `TierResult(no_match=True)` → keeps; tiers' "no match" is *post-registration* dispatch, not registration unavailability
- `state.py`'s `Resources` frozen dataclass → simplifies (no more `cookie_jar` / `llm_extractor` / `browser_pool` as separate fields; they come from `REGISTRY["resources"]`)

## Impact

**Code-shape changes**
- New `src/a2web/_plugin.py` (~100 LoC)
- Each migrated surface gains a `MANIFEST` per plugin file (~10 LoC per file)
- Removed: `unavailable_lazy(...)`, the bespoke `_pick_provider`, several `_ensure()` shims, the `_HANDLERS` tuple

**Wire / external contracts**
- **No wire changes.** Tool surfaces (`ask`, `fetch_raw`, `cookies_refresh`) keep their signatures and response envelopes.
- **No LDD event changes.** Same payload types, same sink fan-out semantics.

**Tests**
- Each migration step has its own openspec sub-change (this change is the umbrella).
- Tests assert the registry is populated correctly after `load_surface` and that `Unavailable` results don't appear in the registry.
- Existing per-surface tests stay; they now import via the manifest path instead of the bespoke ctor.

**Risk**
- MEDIUM. This is the longest of the three ADR-0001 changes. Migrating handlers (10+ files) is fiddly. Mitigation: one surface per session, each surface lands as its own sub-PR with a clean revert path.
- ONE specific risk: `load_surface` uses module reflection (`pkgutil.iter_modules` or `importlib.import_module`). Side effects at import time would break the model. Mitigation: archon rule (added by `arch-fitness-functions-bootstrap`) bans module-level work in plugin files beyond `MANIFEST = ...` declaration.

**Out of scope (deferred)**
- Migrating wobble policies (kept as `_policies.py` table style; manifest doesn't fit).
- Externalising plugins to PyPI packages (we're not building a plugin ecosystem; in-tree manifests only).
- Adding hot-reload of plugins (no use case).
- Migrating to `pluggy` (not chosen — see ADR-0001).
