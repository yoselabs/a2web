# Tasks

## 1. a2kit feedback (the leak is upstream — a2web has no formatter hook)

- [x] 1.1 Write the `encode_envelope` defect into
      `docs/history/A2KIT_FEEDBACK_v0.49-envelope-leak.md` (round 17): BOTH faces —
      the empty-field leak AND the populated-field DESTRUCTION (a2web's pre-encoded
      TSV string → `[]` → `"\n"`, verified via `render_plain`), the str-aware fix
      (skip a `tsv_field` absent OR already a `str`), the blast-radius nuance
      (only `content[]`-reading hosts; latent for structuredContent-forwarding
      hosts), and — the load-bearing finding — that `call_wire` never exercises
      `encode_envelope`, so the entire MCP dispatch encoder is untested from a2web.
- [ ] 1.2 (optional, same feedback) request the `_<name>_format` sidecars be
      omittable for AI-facing tools, pending the open-question answer.

## 2. Close the test gap on a2web's side

- [x] 2.1 Added `tests/capabilities/ask_response/test_envelope_dispatch_encoder.py`
      driving the REAL MCP dispatch encoder (`render_plain(structured, plan)` with
      the envelope plan, not `call_wire`). Two scenarios, both `xfail(strict=True)`
      so they document the defect without breaking `make check` and self-heal
      (XPASS → hard fail forces the marker off) once the a2kit fix is adopted:
      (a) a healthy answer omits every empty conditional + its `_*_format` sidecar;
      (b) a populated `other_pages` survives as TSV (currently destroyed → `"\n"`).

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
