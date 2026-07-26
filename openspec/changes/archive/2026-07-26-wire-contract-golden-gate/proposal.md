## Why

a2web is installed globally and wired into a live Claude Code MCP config. The
`sunset-a2kit-dependency` migration replaces the composition root, the tool
registration path, the response encoder, and the error envelope. **Without a
trustworthy gate, "did we change the wire?" is unanswerable mid-migration** — and
the migration would have to land as one terrifying commit instead of a sequence.

**The existing contract tests cannot serve as that gate. They pass vacuously
across this migration.** Three independent reasons, all verified:

1. **They snapshot the wrong channel.** `tests/contracts/test_contracts.py`'s
   `_ask_wire` uses `client.call_wire` (`:104`), which reads `structured_content`
   and re-formats it via `format_response(value, descriptor.format_hint)`
   (`a2kit/packages/testing/client.py:210-214`) — a path that can only yield
   `tsv`/`page-tsv`/`json`, **never the `envelope` plan production actually
   uses**. Confirmed by the goldens: `ask_failure.json` carries `operator_hints`
   as a JSON array with no `_*_format` sidecars, a shape that never appears on
   the real `content[]` channel. `envelope-wire-hygiene` §2 already identified
   this gap; this change closes it structurally rather than per-defect.
2. **They snapshot the wrong schema.** `test_contract_tool_schemas` (`:190`)
   uses `a2kit.testing.compute_schema`, an a2kit-private reimplementation.
   Its golden has `"title": "fetch_raw_in"`, per-property titles, and **no
   descriptions**. The live wire has descriptions, no titles, and
   `additionalProperties: false`. They are different artifacts.
3. **Nothing covers** tool descriptions, annotations, `_meta`, the error
   envelope, or the log-notification stream.

**Ground truth discovered while scoping this** (all verified live, several
contradicting the documentation):

- The advertised surface is **exactly two tools: `query` and `fetch_raw`**.
  `AppSettings.expose_cookies_tool` defaults false → `build_app()` selects
  `_A2WebServer`, which drops `CookiesRouter`. `refresh` is not on the wire and
  never has been in the installed config; the `canonical_name_override="refresh"`
  pin at `routers.py:293` protects nothing.
- `_meta.health` is registered then killed by `server.disable(tags={"_meta"})`.
  On FastMCP 3.2.4 that removes it from *dispatch*, not just listing — there is
  no `_meta.health` wire surface to preserve.
- The advertised `outputSchema` is `{"type":"object","additionalProperties":true}`,
  not `AskResponse`'s schema — a consequence of a2web's own `@model_serializer`
  and identical under plain FastMCP.

## What Changes

**One layer, one rule: a real `fastmcp.Client` against the real built server.**
Not `call_wire`, not `compute_schema`, not `render_plain`. *If a byte does not
come out of `fastmcp.Client`, it is not a contract byte.*

- **Artifact 1 — `wire_list_tools.json`.** Every advertised tool, sorted, with
  `_meta` **retained** so the a2kit block's eventual disappearance is a reviewed
  delta rather than a silent one. Freezes names, descriptions, `inputSchema`,
  `outputSchema`, annotations, title.
- **Artifact 2 — `wire_call/<scenario>.json`.** Both channels per scenario, with
  `content[].text` stored as an **opaque string, never `json.loads`-ed** — the
  sidecars, the `"\n"` markers and the TSV escaping exist only in raw bytes.
- **Artifact 3 — `wire_errors.json`.** Missing-required-arg (FastMCP-owned, must
  not change), tool-body exception, and `ResourceUnavailable`.
- **Artifact 4 — `wire_notifications.json`.** The `notifications/message` stream
  captured via `Client(..., log_handler=...)`, making the live telemetry surface
  a reviewed decision rather than an accident.

**Four properties that make it non-vacuous:**

1. **Anti-vacuity assertions beside every compare** — e.g. `len(list_tools) == 2`,
   `'\t' in content[0].text` for a links scenario, `"url" not in payload` for the
   same-URL deviation case. A golden with a degenerate payload passes trivially;
   these fail loudly when a fixture stops producing content.
2. **Adversarial TSV fixtures.** Cells containing `"`, `\n`, `\t`, `\`. Under the
   byte-for-byte migration these must be unchanged; under the later `lean-wire`
   swap they are the *only* diffs. That is what separates "we adopted the fix"
   from "we broke something".
3. **Narrow scrubbing.** Keep `_scrub_str`/`_normalize` but apply them **only** to
   `structured_content`. Never regex inside the frozen raw string — that is
   exactly how a real diff hides. Make timings deterministic in the fixture
   instead.
4. **Two-phase bless.** `A2WEB_BLESS_CONTRACTS=1` is too blunt for a migration.
   Add `A2WEB_ACCEPT_WIRE_DELTA=<reason-slug>`, which writes the new golden **and**
   appends the unified diff to `tests/contracts/DELTAS.md` under that slug.
   The migration's gate is "zero deltas"; the `lean-wire` adoption's gate is
   "every delta carries slug `lean-wire-escaping` and touches only cells
   containing `" \ \t \n \r`". Untagged diffs are rejected.

**One invariant test that is not a golden**, because it is the single assertion a
faithful port of a2kit cannot satisfy:

> For every scenario whose model carries a non-empty `other_pages`, the target
> URL substring MUST appear in `content[0].text`.

It fails today (the `encode_envelope` defect tracked in `envelope-wire-hygiene`)
and must pass after the migration deletes the offending middleware. Without it,
an engineer porting the encoder "faithfully" would reproduce the defect and every
gate would stay green.

## Impact

- New: `tests/contracts/wire/` (goldens), the capture harness, `DELTAS.md`.
- Modified: `tests/contracts/test_contracts.py` — the `call_wire` and
  `compute_schema` snapshots are superseded. Decide whether to delete them or
  keep them as a `structured_content`-only view (see open questions).
- **No src changes. No wire changes.** This change only observes.
- **Sequencing: lands AFTER `hotfix-fastmcp-error-envelope`** so Artifact 3
  freezes the repaired error envelope, not the `TypeError` string. Lands BEFORE
  any `sunset-a2kit-dependency` src work.

## Open questions

- **Do the existing `call_wire`/`compute_schema` goldens get deleted or kept?**
  Keeping them costs maintenance and they measure a path that will not exist;
  deleting them loses `structured_content` coverage unless Artifact 2 subsumes it
  (it does). Recommend delete, but it is a judgement call.
- **`wire_notifications.json` presupposes a decision** on whether the live
  MCP log stream (`TierStarted`/`TierEnded` via `notifications/message`) is part
  of the contract at all. Capturing it is cheap and forces the decision; see
  `sunset-a2kit-dependency` open question on the same subject.
- Which scenarios? The six existing contract scenarios plus `fetch_raw` with
  `include_links=True` (the only path exercising `_links_tsv` on real multi-line
  anchors) is the proposed floor.
