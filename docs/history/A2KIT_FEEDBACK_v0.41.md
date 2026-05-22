# a2kit feedback — round 12 (2026-05-22)

Outgoing wishes for the next a2kit minor. Captured from a2web's
`ask-response-diet` change. Not in scope for that change itself — it is an
upstream framework ask.

## Formatter-level empty-field omission (`exclude_none` / `exclude_defaults`)

**Ask.** Let a tool's return type opt into pruning empty fields from the
JSON wire payload — fields whose value is `None`, `[]`, `{}`, or `""`. Either
a per-return-type formatter option, or honoring a model-level marker so
`format_response` calls `model_dump(mode="json", exclude_none=True)` (and
optionally `exclude_defaults=True`) for that type.

**Why.** `a2kit.packages.formatter` serializes every tool return with a
plain `model_dump(mode="json")` — no `exclude_none`, no `exclude_defaults`.
So every optional field reaches the wire even when empty: `byline: null`,
`meta: {}`, `next_links: []`, `original_url: null`. On a token-sensitive
tool like a2web's `ask`, that is pure noise in the calling agent's context
and visual clutter in every response.

**a2web's workaround.** `ask-response-diet` ships a custom
`@model_serializer(mode="wrap")` on `AskResponse` (and `AskExtraction`)
that drops empty optionals while never dropping the required-field set.
It works and routes correctly through `format_response`, but:

- It is per-model boilerplate — every a2kit app that wants lean output
  reinvents the same wrap-serializer.
- It desyncs the model from its generated `outputSchema` (the schema still
  advertises the optional fields; the payload omits them). Harmless when
  the fields are schema-optional, but a framework-level option could keep
  schema and payload consistent.

Once a2kit absorbs this, a2web deletes the custom serializer with no
migration pain.

**Compatibility.** Additive. Default (no opt-in) keeps today's
emit-everything behavior.

## (No other items this round.)

Carrying over from v0.40 / `A2KIT_WISHES_DEFERRED.md`: LDD severity levels,
declarative tool selection, `Lazy[T]` introspection helpers, and the
`app.tools()` name-override mechanism are still wished-for. None is blocking
`ask-response-diet`.
