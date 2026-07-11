## 1. Wire model

- [x] 1.1 Removed `structural_form` and `shape` fields from `AskResponse` in `src/a2web/models.py`. `RouterPayload` confirmed untouched (still requires both).
- [x] 1.2 Updated `AskResponse`'s field comment (the six-field note now explains why `structural_form`/`shape` are absent) and `RouterPayload`'s class docstring (now explicitly states the two fields are internal-only, not projected to the wire).
- [x] 1.3 Checked `_ASK_REQUIRED_FIELDS`/`_prune_wire` plumbing — no reference to `structural_form`/`shape` existed there (they were never in the "required" frozenset, just ordinary omit-empty-when-None fields), so no change needed.

## 2. Response builder

- [x] 2.1 Updated `build_ask_response` in `src/a2web/fetcher_response.py` — removed the `structural_form=`/`shape=` kwargs from the `AskResponse(...)` constructor call.
- [x] 2.2 Confirmed: `kind_guidance(routing.structural_form)` and the `refinement_axes`/`routing.structural_form == "listing"` gate both read the local `routing` variable (the `RouterPayload` instance), not `AskResponse` fields — unaffected by the removal.
- [x] 2.3 Confirmed: the `_INCOMPLETE_OBSTACLES` gate reads `routing.obstacle`/`fc.routing.obstacle`, not `AskResponse` — unaffected.

## 3. Docs and tool surface

- [x] 3.1 Updated `src/a2web/routers.py`'s `ask` tool docstring — "six fields" → "three conditional fields... plus the always-present `answer`", `structural_form`/`shape` mention removed.

## 4. Tests and contracts

- [x] 4.1 Read current state first — `test_ask_response.py` had no references to the two fields; `test_router_wire.py` had many (it's the dedicated router-shape wire-contract test file).
- [x] 4.2 Updated every assertion in `test_router_wire.py` expecting `structural_form`/`shape` presence to instead assert absence; added `test_structural_form_consumed_internally_but_absent_from_wire` (uses a `structural_form: "product"` envelope, asserts the `content_guidance` hint still appears via the internal `RouterPayload` consumer while both fields stay off the wire) — mirrors the new spec scenario directly.
- [x] 4.3 Re-blessed contract goldens via `A2WEB_BLESS_CONTRACTS=1 uv run pytest tests/contracts/test_contracts.py` (only `tool_schemas.json` needed it — `ask_success_rich.json` never had these fields to begin with). Diff confirmed exactly as expected: `AskResponse`'s schema loses `structural_form`/`shape` (and `genre`, already pending from the uncommitted sibling change); `RouterPayload`'s own field schema is untouched, only its docstring text updated.
- [x] 4.4 Full `ask_response` + `contracts` suite green (65/65 before the full run).

## 5. Verification

- [x] 5.1 `make check`: 1000 passed, 2 deselected, 89.88% coverage (≥85% required), lint/ty/arch all clean.
- [x] 5.2 Live-verified via `uv run a2web web ask` against the same Koçtaş product URL used throughout this session: `structural_form`/`shape` absent from the JSON output; `answer` ("Price: 4,221.97 TRY... In stock") and the `content_guidance` operator hint both present and correct.
- [x] 5.3 Skipped `make bench` per explicit instruction.
