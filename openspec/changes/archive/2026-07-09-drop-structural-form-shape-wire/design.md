## Context

`RouterPayload` (the internal LLM-parse boundary type, `models.py`) has six fields: `answer`, `structural_form`, `shape` (required), `obstacle`, `ask_here`, `try_url` (conditional). Today all six get projected onto `AskResponse`'s wire envelope by `build_ask_response` (`fetcher_response.py`). This change narrows the wire projection to four (`answer`, `obstacle`, `ask_here`, `try_url`) — `RouterPayload` itself, the extraction prompt, and everything that reads `routing.structural_form`/`routing.shape` internally are unchanged.

The trigger was a live audit during this session's Koçtaş follow-up work: grepping `src/a2web` for every `.structural_form`/`.shape` reference found `shape` has zero internal consumers (only the wire-write site), contradicting the same-day `ask-extraction-token-tuning` change's blanket claim that structural_form/shape/obstacle "each has a confirmed consumer." `structural_form` does have two internal consumers, but both already surface their own derived output on the wire independently of the raw enum (see proposal.md). A live payload measurement found the two fields cost ~7.6% of a real 605-byte response — more than half the length of the answer text itself, paid unconditionally on every call.

## Goals / Non-Goals

**Goals:**
- Remove `structural_form`/`shape` from `AskResponse`'s wire envelope with zero change to internal pipeline behavior (content_guidance, refinement_axes gating, incompleteness/obstacle gating all read from `RouterPayload` directly today, not from `AskResponse`'s copies).
- Correct the `ask-response` spec's now-false claims (shape "has a confirmed consumer"; "three required fields" implying structural_form/shape belong on the wire).
- Keep `RouterPayload` and the extraction prompt template completely unchanged — this is a wire-projection change, not an extraction-shape change.

**Non-Goals:**
- Not touching `obstacle`, `ask_here`, `try_url` — confirmed real consumer / confirmed real routing mechanism, out of scope.
- Not touching `RouterPayload`'s six-field shape, the `extract_router_v1` prompt template, or `genre`'s already-completed removal (separate, prior change).
- Not re-litigating `include_routing`'s existence — it stays, just narrows in scope (four fields toggle instead of six).

## Decisions

**D1 — Remove the fields from `AskResponse`, not from `RouterPayload`.** `RouterPayload` is the LLM boundary type; `content_guidance.kind_guidance(routing.structural_form)` and the `refinement_axes`/`structural_form == "listing"` gate both read `routing` (the `RouterPayload` instance held on `FetchResponse.routing`/`FetchContext`), never `AskResponse.structural_form`. Confirmed by grep: no internal call site reads `AskResponse.structural_form` or `AskResponse.shape` — those wire fields exist purely to be serialized, and `build_ask_response` is their only writer. Removing them from `AskResponse` therefore cannot affect `content_guidance`, `refinement_axes`, or the obstacle/incompleteness gate, all of which continue reading from `routing` exactly as before.
  - *Alternative considered*: keep the fields but debug-gate them (only appear under `debug=True`), mirroring how `started_at`/`cache`/etc. are debug-only. Rejected — that still ships them by default under `debug=True` for a case with no confirmed value, and the project's own precedent (`genre`'s removal) was a clean drop, not a debug-gate, when a field's value was unproven.

**D2 — `obstacle` stays exactly as-is.** It has a real, checked internal consumer (`fetcher.py:2161`, `_INCOMPLETE_OBSTACLES` gate) distinguishing it from `shape` (zero consumers) and `structural_form` (consumer exists but is redundant with content_guidance). No ambiguity here — this decision is really "don't let this change's momentum sweep in a field that's actually justified."

## Risks / Trade-offs

- **[Risk] Breaking change for any external caller reading `structural_form`/`shape`.** → Accepted, explicitly, after live investigation this session (no evidence found of the fields providing external value beyond what's now confirmed absent internally). If a caller does depend on them, the failure mode is a missing dict key (not a crash) — parsers checking `.get("structural_form")` degrade gracefully; parsers doing `response["structural_form"]` would raise `KeyError`. This is the same class of breaking change the project's CLAUDE.md already flags as requiring "Ask First" — done, via `AskUserQuestion`, before this proposal was written.
- **[Risk] The uncommitted sibling `ask-extraction-token-tuning` change touches the same files (`models.py`, `fetcher_response.py`, `tests/capabilities/ask_response/*`, contract fixtures) and isn't committed yet.** → Mitigation: read current file state before editing (not the archived proposal's snapshot) at implementation time; this change layers on top of, rather than reverts, that work (it only removes two fields that change also touched).
- **[Trade-off] `RouterPayload` keeps validating and requiring `structural_form`/`shape` from the LLM even though the wire never surfaces them.** → Accepted: the LLM still needs to classify the page to compute `content_guidance`'s hint and the `refinement_axes`/`obstacle` gates correctly — dropping the fields from the *prompt* would break those internal consumers. Only the *wire projection* is removed.

## Migration Plan

No data migration. Pure wire-envelope trim — ship via `make check`. No feature flag. Rollback is a plain revert if a caller turns out to depend on the removed fields (accepted risk above).
