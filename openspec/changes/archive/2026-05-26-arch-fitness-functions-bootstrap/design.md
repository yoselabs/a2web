# Design — arch-fitness-functions-bootstrap

## Scope

Pattern 3 of ADR-0001. Install Tach (declarative package boundaries) and pytest-archon (AST/call-site rules). Grandfather existing violations via `tach sync`. Land five initial archon rules covering the most-cited CLAUDE.md "Never" lines.

## Architecture

```
              make check
                  │
       ┌──────────┴───────────┬───────────────┬──────────────┐
       ▼                      ▼               ▼              ▼
     lint                     ty            test           arch  ← new
                                                            │
                          ┌─────────────────┬───────────────┘
                          ▼                 ▼
                    tach check        pytest tests/architecture/
                    (≈10ms)           (≈100ms)
                    │                       │
                    ▼                       ▼
              tach.toml                test_*.py
              [[modules]]              archrule(...)
              [[interfaces]]           .match("...").should_not_*
                                       AST walkers
                          │                       │
                          ▼                       ▼
                  package boundaries     call-site / value-shape rules

   Defense in depth:
   - Tach catches "module X may not depend on Y" / "Y is private"
   - Archon catches "this call must only happen inside Z" / "this field
     must not have shape T" / "this decorator implies that constraint"
```

## Decisions

### D1 — Tach for boundaries, pytest-archon for AST. No import-linter.

Per ADR-0001's tooling rationale: Tach's `[[interfaces]]` model fits the dominant rule shape ("`packages/X.__init__.py` is the only public surface"); import-linter would require enumerating every private submodule per package (verbose, drifts as new submodules appear). pytest-archon handles the AST cases Tach can't (call-site bans, value-shape bans, decorator-implied constraints).

### D2 — Run Tach via `uvx` initially; switch to project dev-dep if CI cold-start hurts

```toml
# pyproject.toml — Tach as a real dev-dep, not uvx
[tool.uv]
dev-dependencies = ["tach>=0.20", "pytest-archon>=0.0.6"]
```

Rationale: `uvx tach` worked in the spike but adds a ~5s install on a cold runner. Promoting it to a pinned dev-dep means CI shares the lock with everything else. Slight footprint cost (~10MB Rust binary in the cache) for predictability.

### D3 — Grandfather, don't refactor on this change

`tach sync` generates the violations snapshot. We do NOT fix the ~30 real violations as part of this change — that's the work of subsequent changes (most retire via `unify-plugin-manifests`). Rationale: scope discipline. The bootstrap change is "install tools + ratchet"; mixing it with cleanup turns a 1-day change into a 1-week change.

Each grandfathered violation gets a comment in `tach.toml` pointing at the openspec change that will retire it. If a violation doesn't have an owning change yet, file a backlog entry.

### D4 — Archon rules are AST walkers, not text greps

Every rule lives in `tests/architecture/test_*.py` as a pytest test that walks Python ASTs. Reason: text greps break on variable renames, multi-line statements, and comments. AST walkers see the actual program structure.

Concrete example for the `json.loads`-ban rule:

```python
def test_json_loads_funnel():
    """Only wobble.parse_with_policy may call json.loads inside packages/llm_extract/."""
    forbidden_dir = Path("src/a2web/packages/llm_extract")
    allowed_module = "wobble"
    for path in forbidden_dir.rglob("*.py"):
        if allowed_module in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "json"
                and node.func.attr == "loads"
            ):
                pytest.fail(f"{path}:{node.lineno}: json.loads outside {allowed_module}/")
```

Five rules at bootstrap, each ~30 LoC. The pattern composes: the next "Never" turns into a new test file with the same shape.

### D5 — CLAUDE.md becomes pointers, not rules

Today CLAUDE.md's "Never" list has ~20 entries in English. After this change:

```markdown
## Never

- Never reintroduce `tier_extras: dict[str, Any]` — enforced by `tests/architecture/test_no_dict_str_any_on_dataclasses.py`
- Never return `-> str` from a tool — enforced by `tests/architecture/test_tools_return_pydantic_not_str.py`
- Never use lambdas in `app.provide(...)` — enforced by `tests/architecture/test_no_lambdas_in_app_provide.py`
- Never import from `a2web.<domain>` inside `packages/` — enforced by `tach.toml`
- (rules without enforcement get a TODO link to the change that will add it)
```

Two virtues: each rule is testable, and the prose document gets shorter (CLAUDE.md is currently ~10K tokens — every line trimmed is context budget reclaimed).

### D6 — Rule additions follow a one-test-per-rule convention

To add a new architectural rule:

1. Write a failing test in `tests/architecture/test_<rule_name>.py`.
2. Add a one-line entry to CLAUDE.md "Never" list pointing at the test.
3. Fix existing violations OR grandfather them via xfail markers with a comment pointing at the change that will retire them.

No silent edits to existing rule files. No batch additions. One rule, one test file, one PR.

### D7 — Bootstrap deliberately ships with 38 grandfathered violations

The ratchet metaphor: today's violations are debt. The bootstrap change captures the debt without paying it down. Subsequent changes pay it down. CI fails only on *new* violations.

This is Shopify's Packwerk model, Sorbet's gradual-typing model, and ArchUnit's `archConfiguredRule` model. Proven approach. The alternative — refusing to ship the bootstrap until every violation is fixed — turns a 1-day change into a 1-month change and creates merge-conflict pain across whatever else is in flight.

## Risk register

- **R1 — Tach upgrade churn.** Tach's `strict_mode → [[interfaces]]` migration during the spike was automatic and clean. Future major-version bumps may not be. Mitigation: pin to a major version (`tach>=0.20,<0.21`), upgrade deliberately.
- **R2 — Archon rules over-fitting.** A rule too strict catches legitimate edge cases (e.g. a future module that legitimately uses `dict[str, Any]` for a serialiser shim). Mitigation: each rule's test file includes an explicit allowlist constant at the top; adding to the allowlist is a code-review checkpoint.
- **R3 — CI cold-start time.** Tach's Rust binary needs to be in the runner cache. First CI run after this change adds ~10s. Subsequent runs cached. Acceptable.
- **R4 — False sense of completeness.** Five archon rules don't cover all of CLAUDE.md's "Never" list. Mitigation: each unmigrated "Never" gets an explicit TODO link in CLAUDE.md pointing at a backlog entry. The class of "rules in prose" doesn't disappear immediately, but every prose rule has a known transition path.
