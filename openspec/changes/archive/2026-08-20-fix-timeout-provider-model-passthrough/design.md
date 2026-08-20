## Context

`TimeoutProvider` (`src/a2web/llm_resource.py:248-282`) is a `@dataclass(slots=True)` with an `inner: Any` field, wrapping whatever `resolve_provider()` returns. It exposes `name` and `available()` as explicit forwarding members. `_build()` (`llm_resource.py:327-362`) reads `provider.default_model` via `getattr(..., "")` after `select_provider()` has already applied the wrap — see proposal.md for why that always misses.

`anyllm`'s own `_GuardedProvider` (`.venv/lib/python3.12/site-packages/anyllm/cost.py:104-153`), used by `with_cost_guard`, wraps the same provider duck-type and solves this with `__getattr__`, explicitly commented as forwarding `default_model`. It guards against recursion during `__init__` by reading `self.__dict__.get("_inner")` before `_inner` is set. `select_provider()` does not currently call `with_cost_guard` anywhere in the chain — only `with_timeout` — so today there is exactly one wrapper to fix, not two.

## Goals / Non-Goals

**Goals:**
- Make `TimeoutProvider` transparently forward every attribute the wrapped provider defines, not just `name`/`available()`, so the current `default_model` gap and any future one of the same shape are both closed.
- Prove the fix with a test that exercises `select_provider()`'s actual return value (the real wrap), not a bare adapter or a hand-constructed `TimeoutProvider`.

**Non-Goals:**
- Changing `_build()`'s `getattr(provider, "default_model", "") or s.llm_model` fallback logic itself — it is correct once the getattr can actually see through the wrapper; only the wrapper's opacity is the bug.
- Wiring `with_cost_guard` into `select_provider()` — out of scope; this change only confirms `_GuardedProvider` doesn't share the gap, it doesn't adopt cost guarding.
- Touching `_config_for()`, `_resolve_openai_model()`, or the provider-order policy (`auto_order`) — none of that is implicated.

## Decisions

**`__getattr__` passthrough over a single `default_model` property.** A `default_model` property (mirroring the existing `name` property) is the smaller diff and would fix today's symptom, but leaves the same failure mode open for the next attribute a provider adds that a caller reads through the wrapper (e.g. anything `anyllm` adds to the `LLMProvider` duck-type later). `__getattr__` closes the class of bug, matches the precedent already established by `_GuardedProvider` one dependency over, and needs no maintenance when `anyllm`'s provider protocol grows. Cost: `__getattr__` is only consulted for attributes not already found through normal lookup, which is exactly right here — `name`, `available()`, and `complete()` stay explicit dataclass members and take priority, so nothing about the timeout-wrapping behavior changes.

**Guard against recursion via `self.__dict__`, not `self.inner`.** `TimeoutProvider`'s field is named `inner` (not `_inner` as in `_GuardedProvider`), and it's a `@dataclass(slots=True)` — `__getattr__` fires whenever normal attribute lookup fails, including during `__init__` before `inner` is assigned, and unguarded recursion (`self.inner` inside `__getattr__` triggering `__getattr__` again) would stack-overflow. The guard reads `object.__getattribute__(self, "inner")` (slotted classes have no `__dict__`, so `_GuardedProvider`'s `self.__dict__.get(...)` pattern doesn't transfer directly) inside a `try/except AttributeError`, then forwards.

**No change to `_build()`.** Its `getattr(provider, "default_model", "") or s.llm_model` already expresses the right policy (provider's resolved model wins; the Anthropic-shaped setting is the fallback for backends that never carry one, e.g. `claude-code-sdk`/`anthropic-api`). Once `TimeoutProvider` forwards `default_model`, that line does what it always looked like it should do.

## Risks / Trade-offs

- **`__getattr__` forwarding could mask a genuinely missing attribute as a silent `AttributeError` from `inner` instead of from `TimeoutProvider`.** → Acceptable: that's the same behavior `_GuardedProvider` already ships, and the alternative (explicit property per attribute) doesn't scale as `anyllm`'s provider surface grows — it would just reproduce this bug for the next field.
- **A future `complete`-shaped attribute added to some provider could shadow-collide with a dataclass field name added to `TimeoutProvider` later.** → Low probability; `__getattr__` is only consulted after normal lookup fails, so an explicit `TimeoutProvider` field always wins over the forwarded one — no silent override risk today, and any future field addition is a visible diff reviewers will see.

## Migration Plan

Single-file behavioral fix, no data migration, no config/env change. Deploy is the normal release path (`release.yml` reruns `make check` on tag). Rollback is a plain revert — no state is created or altered by this change that would need unwinding.
