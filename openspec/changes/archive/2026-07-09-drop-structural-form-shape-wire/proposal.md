## Why

The same-day `ask-extraction-token-tuning` change (2026-07-09, currently uncommitted) audited the six v0.21 router-shape fields and dropped `genre` for having zero downstream consumers, while keeping `structural_form`/`shape`/`obstacle` on the claim "each has a confirmed consumer." That claim doesn't survive a direct grep: `shape` has **no internal consumer anywhere** in `src/a2web` — the only reference outside its own field declaration is the single write site that copies it onto the wire (`fetcher_response.py:547`). `structural_form` does have two internal consumers (`content_guidance.kind_guidance()` for a one-line hint, and gating whether `refinement_axes` gets attached) — but both of those consumers already surface their *own* derived output on the wire (the `content_guidance` operator hint text, and `refinement_axes` itself), so the raw enum is pure duplication for the 3 of 9 values that have guidance (product/listing/thread) and inert for the other 6 (article/reference/tutorial/changelog/code/media/other).

A live re-probe (this session, real product page) measured the actual cost: `structural_form` + `shape` together are 46 raw JSON chars in a 605-byte total response — ~7.6% of the whole payload, and 62% as long as the actual `answer` text (74 chars) in that example. This is paid on every single `ask` call, unconditionally, forever, for fields nothing internally needs and nothing has demonstrated an external caller reads either.

`obstacle` is unaffected — it has a real internal consumer (`fetcher.py:2161`, the incompleteness gate) and stays on the wire exactly as today.

## What Changes

- **BREAKING**: Remove `structural_form` and `shape` from `AskResponse`'s wire envelope (`src/a2web/models.py`). This is a wire-only removal — `RouterPayload` (the internal LLM-parse boundary type) is unchanged and still requires both fields; internal consumers (`content_guidance.kind_guidance()`, the `refinement_axes` gate, `_INCOMPLETE_OBSTACLES`) already read from `routing: RouterPayload` directly, never from `AskResponse`'s own fields, so removing the wire fields has zero internal behavior risk.
- Update `build_ask_response` (`fetcher_response.py`) to stop projecting `routing.structural_form`/`routing.shape` onto the `AskResponse` instance.
- Update `routers.py`'s `ask` tool docstring: "Router-shape adds six fields" becomes four (`obstacle`, `ask_here`, `try_url`, plus `answer`).
- Correct `openspec/specs/ask-response/spec.md`: the "AskResponse carries router-shape fields by default" requirement currently declares `structural_form`/`shape` as always-present required wire fields and asserts `shape` "has a confirmed consumer" — both statements become false after this change. `RouterPayload`'s own requirement (the internal boundary type, still validating both as required LLM-output fields) is unchanged.
- Update wire-contract tests and fixtures that assert `structural_form`/`shape` presence on `AskResponse`.

No change to `obstacle`, `ask_here`, `try_url`, `RouterPayload`, the extraction prompt template, or `include_routing`'s parameter existence (its scope narrows from six fields to four, documented, not removed).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `ask-response`: `AskResponse` no longer carries `structural_form`/`shape` on the wire; router-shape is now four fields (`obstacle`, `ask_here`, `try_url`, plus `answer`) instead of six. `RouterPayload`'s internal shape (still six fields, still required for `structural_form`/`shape`) is unchanged — only the wire projection changes.

## Impact

- `src/a2web/models.py` — `AskResponse.structural_form`/`AskResponse.shape` fields removed; `RouterPayload` untouched.
- `src/a2web/fetcher_response.py` — `build_ask_response` stops setting the two removed fields.
- `src/a2web/routers.py` — `ask` tool docstring wording update.
- `openspec/specs/ask-response/spec.md` — delta spec (requirement text + scenarios).
- `tests/capabilities/ask_response/test_ask_response.py`, `test_router_wire.py` — remove/update assertions on the two wire fields (note: these files carry uncommitted edits from the sibling `ask-extraction-token-tuning` change already in the working tree — read current state before editing, don't assume a clean baseline).
- `tests/contracts/ask_success_rich.json`, `tests/contracts/tool_schemas.json` — contract fixtures, if they assert the two fields.
- **BREAKING for any external caller currently reading `structural_form`/`shape` off an `ask` response** — explicitly approved this session after live investigation (see design.md for the evidence trail).
