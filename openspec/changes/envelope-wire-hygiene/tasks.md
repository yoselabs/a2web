# Tasks

## 1. a2kit feedback (the leak is upstream — a2web has no formatter hook)

- [ ] 1.1 Write the `encode_envelope` empty-field defect into
      `docs/history/A2KIT_FEEDBACK_v0.*.md`: the bug (`render.py:94-98`, static
      `tsv_fields` → `envelope.get(name)` None → `[]` → `"\n"` + `_*_format`
      sidecar), the one-line fix (skip a `tsv_field` absent from the pruned
      envelope), and — the load-bearing finding — that `call_wire` never exercises
      `encode_envelope`, so the entire MCP dispatch encoder is untested from a2web.
- [ ] 1.2 (optional, same feedback) request the `_<name>_format` sidecars be
      omittable for AI-facing tools, pending the open-question answer.

## 2. Close the test gap on a2web's side

- [ ] 2.1 Add a wire-contract test that drives the REAL MCP dispatch encoder (the
      `format_routing` path, not `call_wire`) and asserts a healthy `query`
      response omits every empty conditional (`other_pages`, `headings`,
      `refinement_axes`, `options`) and emits no `_*_format` sidecar for them.
      This fails today (documents the leak) and passes once the a2kit fix is
      adopted.

## 3. Adopt the a2kit fix

- [ ] 3.1 When a2kit ships the `encode_envelope` guard, bump the pin, `uv lock`,
      and confirm the wire-contract test (2.1) goes green.

## 4. Schema trim (DEFERRED — revisit after 1-3 lands)

- [ ] 4.1 After the leak fix is live, re-assess the envelope and confirm whether
      any trim set (`confidence`, `meta`, `tier`, failure-story fields) is still
      worth a breaking change. Breaking for parsers — human decides.
- [ ] 4.2 Apply the confirmed trim in `models.py` (`AskResponse` field tiers +
      `_prune_wire`), keeping `also_here`/`other_pages` (ADR-0015 index) intact.
- [ ] 4.3 Update the four-axis output-benchmark envelope-shape assertions.
- [ ] 4.4 `make check` green; `make bench` to confirm the clarity axis improved
      (or held) and nothing else regressed.
