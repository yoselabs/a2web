## MODIFIED Requirements

### Requirement: AskResponse carries router-shape fields by default

`AskResponse` SHALL declare four router-shape fields (narrowed from the prior six — `structural_form` and `shape` are no longer projected onto the wire, see the "Modified" note below):

Required field (always present on the wire when the LLM extractor returned a routing payload):
- `answer: str` — the model's answer to the question.

Conditional fields (omitted from the wire via `_prune_wire` when empty/null):
- `obstacle: Literal["paywalled","blocked","empty","error"] | None` — page-level failure mode; omitted on healthy pages.
- `ask_here: list[str]` — same-URL re-asks; omitted when `[]`.
- `try_url: list[NextUrl]` — different-URL re-asks where each entry has `{url, reason}`; omitted when `[]`.

`AskResponse` SHALL NOT declare a `genre` field (unchanged from the prior change) and SHALL NOT declare `structural_form` or `shape` fields. `RouterPayload` (the internal LLM-parse boundary type) is UNCHANGED — it still requires `structural_form` and `shape` from the extractor, and internal consumers (`content_guidance.kind_guidance()`, the `refinement_axes` gate) continue reading `routing.structural_form` directly; only the wire projection onto `AskResponse` is removed. Audit finding backing this change: `shape` had no downstream consumer anywhere in the pipeline (unlike the earlier `genre` removal's audit, which correctly identified `obstacle` as having a real consumer — that audit's claim that `shape` also had one does not hold up under a direct trace); `structural_form`'s only two internal consumers already surface their own derived output on the wire independently (the `content_guidance` operator hint, and `refinement_axes` itself), making the raw enum redundant for display.

The `ask` tool SHALL accept an `include_routing: bool` parameter defaulting to `True`. When `include_routing=False`, all four fields SHALL be `None` / absent and the wire SHALL carry the lean v0.14 envelope shape. When `include_routing=True` but the extractor returned no routing payload (no LLM, fetch error, parse failure), all four fields SHALL be absent.

#### Scenario: Default ask includes the router-shape fields

- **WHEN** `ask` is called without `include_routing` against a content page that the LLM successfully extracts
- **THEN** the wire carries `answer` always, plus `obstacle` / `ask_here` / `try_url` only when populated, and no `genre`, `structural_form`, or `shape` key under any circumstance

#### Scenario: Opt-out via include_routing=False suppresses all four fields

- **WHEN** `ask` is called with `include_routing=False`
- **THEN** the wire carries no `obstacle`, `ask_here`, or `try_url` keys (and `answer` remains the unstructured extractor answer)

#### Scenario: Extractor unavailable leaves router fields absent

- **WHEN** `ask` is called with `include_routing=True` but the LLM extractor is unavailable
- **THEN** the wire carries none of the four router-shape fields, and an `operator_hint` with `code="llm_unavailable"` records the reason

#### Scenario: structural_form and shape never reach the wire even though RouterPayload requires them

- **WHEN** `ask` is called against a page the LLM classifies as `structural_form: "product"`, `shape: "key-value"`
- **THEN** `RouterPayload.structural_form` and `RouterPayload.shape` are populated internally (consumed by `content_guidance.kind_guidance()` to emit the `content_guidance` operator hint), but neither `structural_form` nor `shape` appears as a key on the `AskResponse` wire

### Requirement: Router-shape envelope omits empty conditional fields via _prune_wire

The `AskResponse._prune_wire` serializer SHALL treat the three conditional router-shape fields as omit-empty:

- `obstacle` is omitted when `None`.
- `ask_here` is omitted when `[]`.
- `try_url` is omitted when `[]`.

The one required field (`answer`) SHALL always appear when present on the model. No `genre`, `structural_form`, or `shape` field exists on `AskResponse` to prune.

#### Scenario: Healthy article with complete answer omits all three conditionals

- **WHEN** `ask` returns a routing payload with `obstacle=None`, `ask_here=[]`, `try_url=[]`
- **THEN** the wire payload contains `answer` plus the rest of the AskResponse envelope; no `genre`, `structural_form`, `shape`, `obstacle`, `ask_here`, or `try_url` keys

#### Scenario: Obstacle page populates obstacle and try_url

- **WHEN** `ask` returns a routing payload with `obstacle="paywalled"` and `try_url=[{...}]`
- **THEN** the wire contains both keys, plus `answer`, with `ask_here` omitted if not populated, and no `genre`, `structural_form`, or `shape` key under any circumstance

#### Scenario: Field shape survives the formatter wire path

- **WHEN** `ask` with the router-shape is invoked through the in-process test client (production formatter wrapper chain)
- **THEN** the marshaled result has omit-empty conditionals absent (not present as `null` or `[]`), and no `genre`, `structural_form`, or `shape` key
