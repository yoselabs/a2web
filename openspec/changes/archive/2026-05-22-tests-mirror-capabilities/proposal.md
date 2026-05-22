## Why

`tests/` is a flat pile of 60 `test_*.py` files while `src/a2web/` is layered (`packages/`, `tiers/`, `handlers/`, `actions/`, `events/`) and the project is spec-driven — every behavior has an `openspec/specs/<capability>/spec.md`. The flat layout means there is no answer to "a spec changed — which tests verify it?", the `packages/` independence boundary is invisible in the test tree, and integration tests that drive the whole `fetcher.fetch()` orchestrator sit indistinguishably next to one-line pure-function tests. This is a navigability and architecture-enforcement problem, not a speed problem.

## What Changes

- Regroup all 60 test files into a three-zone layout: `tests/architecture/` (codebase-invariant meta-tests), `tests/packages/` (pure `a2web.packages.*` isolation tests, mirroring `src/a2web/packages/`), and `tests/capabilities/<capability>/` (one directory per OpenSpec capability, holding domain-coupled behavior tests).
- `tests/contracts/test_contracts.py` moves next to its golden JSON files; `tests/utils/` mirrors `src/a2web/utils/`.
- Merge fragmented files: `test_proxy_pool.py` + `test_proxy_policy.py` → one `test_proxy_routing.py`; `test_gate.py` + `test_gate_jina_paywall.py` + `test_gate_thin_browser.py` → one `test_gate.py`.
- Add `__init__.py` to every new test directory (consistent with the existing `tests/__init__.py` / `tests/fixtures/__init__.py`).
- Anchor fixture-path resolution: the 15 files using `_FIX = Path(__file__).parent / "fixtures"`, plus `test_contracts.py` and `test_packages_independence.py`, switch to importing a stable anchor (`FIXTURES_DIR` from `tests/fixtures/__init__.py`, and a repo-root anchor) so a deeper directory does not break path math.
- No test logic is rewritten and no behavior changes — every assertion is preserved. Moves are `git mv` (history-preserving); only mechanical path-anchor fixups and the listed merges touch file contents.

## Capabilities

### New Capabilities
- `test-layout`: the canonical structure of the `tests/` tree — the three zones, the rule that decides which zone a test belongs to, the fixture-path anchoring contract, and the merge/`__init__.py` conventions. Codifies "tests mirror specs" so future test files have a spec'd home.

### Modified Capabilities
<!-- None. This is a pure regrouping — no capability's requirements change. -->

## Impact

- Every file under `tests/` moves; 17 files take a one-line path-anchor edit; 5 files merge into 2.
- `Makefile` test targets (`test`, `bless-contracts`) — `pytest tests/` still discovers everything recursively; `bless-contracts` path to `test_contracts.py` updates.
- `tests/conftest.py` stays at `tests/` and cascades to all subdirectories unchanged; `tests/fixtures/__init__.py` gains the `FIXTURES_DIR` anchor constant.
- No `src/` change, no dependency change, no wire/API change. MCP clients and the gate are unaffected.
