## Why

`query`'s `AskResponse` currently duplicates the full page body on the wire when a caller passes `include_content=True` on a fetch that lands on a thin/empty-confirmed outcome: `content_md` and `thin_content` are both populated from the identical `fr.content_md` string (`src/a2web/fetcher_response.py:1002` and `:1039`). The spec (`ask-response/spec.md`, "thin_content is attached on a thin_unverified failure") currently mandates this by requiring `thin_content`'s presence to be independent of `include_content`. `thin_content` exists to satisfy ADR-0015 (never withhold the body without leaving an index) when `query`'s default (`include_content=False`) would otherwise hide it — once the caller has already opted into `content_md`, that job is already done and the duplicate field only costs wire bytes.

## What Changes

- `thin_content` SHALL be omitted whenever `content_md` is already non-empty on the wire for the same response (i.e. `include_content=True` was passed), for both trigger paths: the `thin_unverified`/`empty_unverified` (`content_thin` hint) outcome and the promoted-`ok` corroborated-empty outcome.
- `thin_content` keeps its current behavior — populated, forcing the body onto the wire — whenever `content_md` is absent (the default `include_content=False` case). No change to that path.
- ADR-0015 gains a short note that the index-forcing rationale for `thin_content` is conditional on the body being withheld, closing the gap its own "if the default flips" caveat didn't cover (a per-call opt-in, not a global default change).
- `ask-response/spec.md`'s "thin_content is attached on a thin_unverified failure" requirement is revised: presence is no longer independent of `include_content` — it's a fallback populated only when `content_md` is absent from the wire.
- New test coverage for `include_content=True` combined with a thin/empty-confirmed outcome (existing `tests/capabilities/retrieval_completeness/test_thin_semantics.py` only covers `include_content=False`).

Not a new field, not a type change — a narrower condition on an already-optional, already-prunable field. Callers who unconditionally read `thin_content` whenever a `content_thin` hint fires must adjust to check `content_md` first; this is called out explicitly since CLAUDE.md requires flagging before response-envelope-shape changes, even though the field itself and its omission mechanism are unchanged.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `ask-response`: the "thin_content is attached on a thin_unverified failure" requirement changes from "presence SHALL NOT depend on `include_content`" to "presence is a fallback, omitted when `content_md` is already populated" — covering both the `thin_unverified`/`empty_unverified` trigger and the promoted-`ok` corroborated-empty trigger.

## Impact

- `src/a2web/fetcher_response.py` (`build_ask_response`, lines ~1002 and ~1039) — add the presence guard.
- `docs/adr/0015-the-withheld-body-index.md` — clarifying note.
- `openspec/specs/ask-response/spec.md` — requirement text + scenarios for "thin_content is attached on a thin_unverified failure" and "Corroborated empty answer is synthetic and honest" (which also asserts `thin_content` presence).
- `tests/capabilities/retrieval_completeness/test_thin_semantics.py` — new scenario(s).
- No tool signature change, no new dependency, no wire type change. Wire byte count decreases for the specific `include_content=True` + thin/empty case; every other case is unaffected.
- Linked to bd issue a2web-y5m.
