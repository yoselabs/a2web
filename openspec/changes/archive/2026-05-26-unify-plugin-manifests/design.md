# Design — unify-plugin-manifests

## Scope

Pattern 2 of ADR-0001. Define `PluginManifest[T]` + `Unavailable` + `load_surface[T](...)` once; migrate five of six extension surfaces. Wobble policies stay as a table style (not a fit for the manifest shape).

## Architecture

```
                  Before                                After
   ┌──────────────────────────┐         ┌──────────────────────────────┐
   │ Provider drift           │         │ Single manifest shape        │
   │ ─ ANTHROPIC env read at  │         │                              │
   │   __init__               │         │   @dataclass(frozen, slots)  │
   │ ─ LLMNotAvailable raised │         │   class PluginManifest[T]:   │
   │   at construction        │         │       name: str              │
   │                          │         │       protocol: type[T]      │
   │ Tier registry            │         │       factory:               │
   │ ─ REGISTRY dict          │   ───►  │           Callable[          │
   │ ─ TIER_ORDER tuple       │         │             [AppSettings],   │
   │                          │         │             T | Unavailable] │
   │ Handler tuple            │         │       requires: tuple[str,…] │
   │ ─ _HANDLERS = (..., ...) │         │       settings_prefix: str   │
   │                          │         │                              │
   │ Sink list                │         │   class Unavailable(         │
   │ ─ app.ldd.add_sink(...)  │         │       NamedTuple             │
   │   in server.py           │         │   ):                         │
   │                          │         │       reason: str            │
   │ Eval system ctor ladder  │         │                              │
   │ ─ if mode == "default":  │         │   def load_surface[T](       │
   │     systems += [...]     │         │       path: str,             │
   │   if mode == "detail":   │         │       protocol: type[T],     │
   │     systems += [...]     │         │       settings: AppSettings, │
   │                          │         │   ) -> dict[str, T]:         │
   │ unavailable_lazy(...)    │         │       …                      │
   │ helper passed to fetcher │         └──────────────────────────────┘
   └──────────────────────────┘                       │
                                                       ▼
                                       ┌──────────────────────────────┐
                                       │ Per-plugin file              │
                                       │                              │
                                       │   # tiers/jina.py            │
                                       │   def build_jina_tier(       │
                                       │       s: AppSettings         │
                                       │   ) -> Tier | Unavailable:   │
                                       │       if not s.jina_key:     │
                                       │           return Unavailable(│
                                       │               "no jina_key") │
                                       │       return JinaTier(s)     │
                                       │                              │
                                       │   MANIFEST = PluginManifest( │
                                       │       name="jina",           │
                                       │       protocol=Tier,         │
                                       │       factory=build_jina_…,  │
                                       │       requires=("jina_key",) │
                                       │   )                          │
                                       └──────────────────────────────┘
                                                       │
                                                       ▼
                                       App boot: load_surface(
                                         "a2web.tiers",
                                         Tier,
                                         settings,
                                       ) → {"raw": ..., "jina": ..., …}
                                       Tiers w/o capabilities skipped silently.
```

## Decisions

### D1 — `load_surface` uses `pkgutil.iter_modules` for discovery

```python
def load_surface[T](path: str, protocol: type[T], settings: AppSettings) -> dict[str, T]:
    pkg = importlib.import_module(path)
    registry: dict[str, T] = {}
    for module_info in pkgutil.iter_modules(pkg.__path__, prefix=f"{path}."):
        module = importlib.import_module(module_info.name)
        manifest = getattr(module, "MANIFEST", None)
        if manifest is None:
            continue  # not a plugin file — utility modules in the surface dir
        if manifest.protocol is not protocol:
            continue  # plugin for a different surface in the same dir (rare; allowed)
        sliced = _slice_settings(settings, manifest)
        instance = manifest.factory(sliced)
        if isinstance(instance, Unavailable):
            _LOG.info("plugin_unavailable", surface=path, name=manifest.name, reason=instance.reason)
            continue
        registry[manifest.name] = instance
    return registry
```

Two alternatives rejected:

- **`importlib.metadata.entry_points`** — targets cross-distribution discovery (PyPI plugins). All a2web surfaces are in-tree; entry_points adds packaging ceremony for zero benefit.
- **Explicit `PLUGINS = (mod1, mod2)` per surface `__init__.py`** — works but every new plugin requires editing the `__init__.py`. Defeats the "drop a file, get a plugin" virtue.

### D2 — `Unavailable` is `NamedTuple`, not Exception

Exceptions are for *unexpected* failures. Unavailability at construction is *expected* — the provider's API key isn't set, the browser isn't installed, the user is on Windows but the cookie reader needs Keychain. Returning a value rather than raising:

- Forces the call site to handle it explicitly (linter catches missing-branch).
- Keeps the boot path linear — no try/except gauntlet in `load_surface`.
- Aligns with the existing `TierResult(no_match=True)` shape (which is also a sentinel, not an exception).

### D3 — `settings_prefix` slicing is keyed by attribute name

```python
def _slice_settings(settings: AppSettings, manifest: PluginManifest) -> AppSettings:
    if manifest.settings_prefix is None:
        return settings
    # AppSettings has nested groups; if settings_prefix="jina", return settings.jina
    return getattr(settings, manifest.settings_prefix, settings)
```

Two alternatives rejected:

- **Pydantic discriminated unions** — would require refactoring `AppSettings` into a sum type. Too invasive.
- **Pass full `AppSettings` always** — works but defeats the design intent ("each plugin sees only the settings it needs"). Mitigation if the slice idea proves too rigid: fall back to passing the full `AppSettings` and let factory read what it wants.

This decision may revisit during step 1's spike. If `AppSettings` doesn't have nested groups today (it likely doesn't), `settings_prefix` becomes a no-op for the first iteration — implement the full slice in a follow-up.

### D4 — Migration is sub-PR-per-surface

Each surface migration lands as its own openspec sub-change underneath this umbrella:

```
unify-plugin-manifests/                    ← umbrella (this change)
├── proposal.md
├── design.md
├── tasks.md (umbrella)
└── sub-changes/                           ← one per surface
    ├── providers/
    ├── eval-systems/
    ├── sinks/
    ├── handlers/
    └── tiers/
```

Rationale: each surface is ~200-500 LoC of changes, lands cleanly on its own, has its own test surface. The umbrella tracks the cross-cutting framework + the ordering.

### D5 — Tiers migrate last; benefit is consistency only

Tiers already have `REGISTRY` + `TIER_ORDER`. The migration replaces these with manifest discovery, but the existing pattern works. Sequenced last so:

- The manifest pattern is proven on simpler surfaces first.
- Tier-specific concerns (`TIER_ORDER` priority, archive/browser out-of-band dispatch) get the fully-mature framework.
- If we discover during providers/eval/sinks migration that the manifest shape needs to evolve, tiers absorb the final shape.

### D6 — Wobble policies are NOT migrated to manifests

Wobble policies are *data* (per-field tolerance + derive callable), not *plugins* (separate instantiation, capability-aware factory, dispatch). Forcing them into the manifest shape would add ceremony without benefit.

The wobble pattern stays as the `_policies.py` table style established by `wobble-typed-funnel`. CLAUDE.md needs to be explicit that policies are not plugins — a future contributor reading both changes shouldn't try to migrate wobble.

### D7 — `archon` rule: no module-level work beyond `MANIFEST` declaration

Per the proposal's risk note. Added in the `arch-fitness-functions-bootstrap` change OR added here as a follow-up rule:

```python
def test_plugin_modules_only_declare_manifest():
    """In tiers/, handlers/, providers/, sinks/, eval-systems/ — module-level
    statements must be: imports, function defs, class defs, MANIFEST = ...
    Nothing else. No side effects at import time."""
```

Rationale: `load_surface` imports every module in the surface dir. A module-level `print()`, network call, or singleton construction would fire at import time, breaking the model.

## Risk register

- **R1 — `settings_prefix` slicing assumptions don't fit `AppSettings`.** Mitigated by D3's fallback. Re-evaluate during step 1 spike.
- **R2 — Discovery via `pkgutil.iter_modules` fails in editable installs / src layouts.** a2web uses src layout; `tach` and `pytest` both work fine. Confirm during step 1 spike with `pkgutil.iter_modules('src/a2web/tiers')`-shaped test.
- **R3 — Surface migration takes longer than budgeted.** Mitigation: each sub-PR is independently mergeable; partial rollouts are acceptable (e.g. providers + eval done, handlers + tiers pending). The mixed state is documented in CLAUDE.md and a follow-up change tracks the gap.
- **R4 — Tests break when import order changes.** `load_surface` imports plugins lazily. Existing tests that import providers directly (`from ...providers.anthropic import AnthropicProvider`) need to switch to the registry path (`load_surface(...).get("anthropic")`). Catch during step 1 grep audit.
