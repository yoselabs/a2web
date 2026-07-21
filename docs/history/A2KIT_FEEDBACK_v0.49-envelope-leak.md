# a2kit feedback — round 17 (2026-07-21)

> **Status: OPEN — one-line fix requested; no a2web workaround exists.**
>
> Pinned against a2kit `v0.49.2`. a2web has no formatter seam to
> post-process the MCP wire — the encoding plan is inferred at
> router-registration time from the return type and a2web never touches
> the formatter — so this must be fixed upstream.

## `encode_envelope` re-inserts empty TSV fields the model already pruned

**The bug.** `a2kit/packages/formatter/render.py:94-98`
(`encode_envelope`) iterates the **static** `tsv_fields` tuple (derived
once from the model type at registration) and, for each name, does:

```python
for name in tsv_fields:
    rows = envelope.get(name)                     # None when the model pruned it
    rows = list(rows) if isinstance(rows, (list, tuple)) else []   # None -> []
    envelope[name] = encode_tsv(rows, columns=_derive_columns(rows))  # [] -> "\n"
    envelope[f"_{name}_format"] = "tsv"           # + a sidecar
```

When the response model's own `@model_serializer` already omits an empty
optional field (a2web's `_prune_wire` omit-empty discipline), `envelope`
does **not** contain that key. `envelope.get(name)` returns `None`, which
coerces to `[]`, which `encode_tsv([])` renders as the bare `"\n"` — and
the loop then **re-inserts the key** plus a `_<name>_format = "tsv"`
sidecar. The omit-empty pruning the model performed is silently undone,
one level up, on the wire.

**Reproduction (a2web `AskResponse`, `v0.49.2`):**

```
pruned model keys:  ['answer', 'confidence', 'tier', 'url']          # 4 real keys
encode_envelope out: ['answer', 'confidence', 'tier', 'url',
                      'operator_hints', '_operator_hints_format',
                      'headings', '_headings_format',
                      'other_pages', '_other_pages_format',
                      'refinement_axes', '_refinement_axes_format',
                      'options', '_options_format']                  # 14 keys
LEAKED: operator_hints="\n", headings="\n", other_pages="\n",
        refinement_axes="\n", options="\n"  (+ 5 "_*_format":"tsv")
```

A healthy `query` answer that should carry 4 keys carries 14 — 10 of them
junk. Every empty conditional the AI caller was meant to read as *absent*
("no other pages", "no options") instead arrives present-but-`"\n"`,
defeating the absence signal.

### The sharper face: populated fields are DESTROYED, not just leaked

The empty-field leak above is the benign symptom. The same static-loop /
type-blind coercion has a **data-loss** face when the response model's
serializer pre-encodes a `tsv_field` into a **string** (a2web's
`@model_serializer` renders `other_pages` / `headings` / `options` /
`refinement_axes` as TSV *blocks* — strings — so the CLI/JSON path, which
never reaches `encode_envelope`, still gets TSV):

```
structured['other_pages'] = 'url\treason\tkind\nhttps://…/download\tdl\tdrilldown\n'   # a real, populated page
encode_envelope → envelope.get('other_pages')            # the string
             → isinstance(str, (list, tuple)) is False   # -> []
             → encode_tsv([])                             # -> "\n"
WIRE['other_pages'] = "\n"                                # DESTROYED
```

Verified on `v0.49.2` via `render_plain(structured, plan)` — the exact
call `FormatRoutingMiddleware.on_call_tool` makes at
`format_routing.py:73`. A populated `other_pages` (the ADR-0015 index of
what the answer withheld) is silently replaced with `"\n"` on the
`content[]` channel. `operator_hints` — the ADR-0009 failure klaxon —
takes the same path.

**Blast radius (important, keeps this honest).** This bites only hosts
that read `content[].text` and ignore `structuredContent`. On hosts that
forward `structuredContent` to the model (Anthropic API, Claude
Code/Desktop/.ai — a2web's primary deployment), the model reads the
model's own correct serialization and never sees the damage; there the
bug is **latent**, not felt. But `content[]` is the spec-guaranteed
channel and dual-emit is a2kit's default, so the destruction is a real
correctness/portability defect, not merely cosmetic.

**The fix (str-aware guard).** Presence alone is not enough — a populated
`other_pages` IS present (as a string). `encode_envelope` must skip a
`tsv_field` that is either (a) absent (model pruned it → honor omit-empty)
or (b) already a `str` (model pre-encoded it → don't double-encode):

```python
for name in tsv_fields:
    rows = envelope.get(name)
    if rows is None:              # model pruned it — leave it pruned (empty-leak fix)
        continue
    if isinstance(rows, str):     # model already TSV-encoded it — don't destroy it
        continue
    rows = list(rows) if isinstance(rows, (list, tuple)) else []
    envelope[name] = encode_tsv(rows, columns=_derive_columns(rows))
    envelope[f"_{name}_format"] = "tsv"
```

A *present-but-empty* list (`[]` explicitly on the model) still renders
as today; a list-of-dicts still gets encoded. Only the pruned-away and
already-encoded cases are skipped — backward-compatible for models that
neither prune nor pre-encode.

## The load-bearing finding: the MCP dispatch encoder is untested from a2web

The `"\n"` leak is only the first bug anyone noticed in an **entirely
untested code path**. a2web's wire tests all go through
`a2kit.testing.client.call_wire`, which routes through
`format_response` → `_plan_for_hint` (`hint.py:20`). That planner can
only ever yield `tsv` / `page-tsv` / `json` — **never the `envelope`
plan**. So `encode_envelope` (and the `render_plain(..., plan)` call the
real `FormatRoutingMiddleware` makes for `plan.kind == "envelope"`,
`format_routing.py:73`) is executed by **no a2web test**.

`call_wire` is *not* fidelity-equivalent to the MCP dispatch encoder.
Any a2web author who trusts `call_wire` to mirror what an agent receives
over MCP is wrong for exactly the envelope shape — the shape a2web's
primary `query` tool uses. This is the real report; the leak is its
symptom.

**Requests:**

1. The str-aware guard above (fixes BOTH the empty-field leak and the
   populated-field destruction; blocks the fix a2web adopts).
2. Consider making `call_wire` — or a sibling testing helper — drive the
   real dispatch encoding path for envelope-returning tools, so this
   class of bug is catchable from a consumer's test suite rather than
   only in a live container.

## Optional (bundle if cheap): omittable `_<name>_format` sidecars

For AI-facing tools the `_<name>_format = "tsv"` discriminator alongside
a *present, populated* TSV field is arguably redundant — the caller can
see the value is tab-separated. If there is a cheap way to suppress the
sidecar per-tool (or per-consumer for the `llm` tier), a2web would take
it. Not blocking; the empty-field leak above is the acute problem.
