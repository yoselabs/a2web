## Context

See `proposal.md` for motivation. Grounding facts established during
exploration, not re-derived here:

- The shared gateway (homelab repo) now stores whatever a caller sends,
  with **no redaction at all** — `ADR 0062`, archived as
  `2026-08-16-drop-feedback-redaction`, runtime-verified (a probe
  confirmed a URL survives end to end unmasked). Before this,
  `A2WEB_FEEDBACK_INCLUDE_CONTENT` was a caller-side preference layered
  on top of a gateway-side backstop; now it is the *only* control over
  whether a URL reaches permanent, undeletable storage.
- `report_feedback`'s `subject`/`request`/`response`/`note`/`wanted` were
  never gated by `A2WEB_FEEDBACK_INCLUDE_CONTENT` in the first place
  (`adopt-shelf-mcp-feedback` design, carried over from
  `add-agent-invoked-feedback-tool` D5) — active disclosure, not passive
  telemetry. This means the agent-invoked path already sends real
  content regardless of whatever `feedback_include_content` is set to.
- The gateway's own ADR 0062 explicitly names a second producer on this
  pipeline (i.e. `report_feedback`, which didn't exist when the original
  redaction trade was assessed) as re-opening the acceptance decision,
  not inheriting it. This change IS that re-decision, made explicitly
  rather than by default.
- The shared gateway token is intentionally public and low-privilege
  (write-only, ingest-only) — the operator's own stated design intent,
  not an accidental exposure.
- `tests/architecture/test_no_personal_strings.py` denies the substring
  `iorlas`, which the shared gateway's hostname contains — this guard's
  job is catching *accidental* leaks, and needs an explicit, reasoned,
  commented exception for this one deliberate case, not a quiet removal.
- FastMCP's `SkillProvider` (`mcp.add_provider(SkillProvider(path))`,
  `fastmcp.server.providers.skills`) is a real mechanism confirmed this
  session — but `resources/list` (which skills ride on) is optional in
  the MCP spec and inconsistently implemented by clients, unlike
  `tools/list`, which every client fetches every session unconditionally.

## Goals / Non-Goals

**Goals:**
- Flip both feedback mechanisms to on-by-default, using the shared
  gateway's public credential, with no per-operator setup required.
- Make the resulting behavior discoverable through the one MCP mechanism
  every client actually surfaces (`tools/list`), not a README a
  connecting agent has no way to read.
- Keep the opt-out trivial: one env var, documented in the one place
  every client sees.

**Non-Goals:**
- Not building an MCP skill/resource for this — considered and rejected
  (D4).
- Not changing the gateway's own redaction posture — already decided and
  shipped on the homelab side (`drop-feedback-redaction`), out of this
  change's scope entirely. This change only decides how a2web behaves
  given that fact, not whether the fact should be true.
- Not adding a stable feedback correlation ID (the at-least-once/
  duplicate-delivery question from the homelab session) — ruled out as a
  live defect (the earlier duplicate-record finding was retracted;
  no observed duplication, only a design gap with no dedup key). Left as
  a genuinely deferred, separate concern.

## Decisions

### D1 — `feedback_enabled` defaults to `True`

**Alternative considered:** keep off-by-default, ship real credentials so
enabling is a one-line flip instead of a full setup. Rejected: the
explicit ask was zero-config, "all distributions should use it," and the
credential is intentionally public/shared — there's no remaining setup
step off-by-default would actually be protecting the operator from.

### D2 — `feedback_include_content` defaults to `True`

**Alternative considered:** leave the mechanical reporter redacted
(`include_content=False`) while `report_feedback` sends real content
regardless (since it was never gated by this flag) — a middle ground
where automatic background telemetry stays conservative and only
deliberate agent action carries real content. Rejected in favor of one
consistent story: given the gateway itself no longer redacts anything,
and the agent-invoked path already bypasses this flag entirely, leaving
the mechanical reporter as the one remaining redacted surface protects a
property (URL secrecy) that's already gone the moment any single
`report_feedback` call happens — a false sense of the mechanical
reporter being more careful than the tool that's actually more likely to
carry rich content.

### D3 — Shipped default credential, not CI-injected

Per the earlier exploration of "where does the value live" (build-arg vs
repo default vs docs-only): a repo default in `settings.py` is the only
option that reaches every distribution channel (pip/CLI install, Docker,
`make install-global`) uniformly. A GitHub Actions secret baked into the
Docker image via build-arg was rejected — it would only reach the
container path, missing CLI installs entirely, and baking a real value
into a public image's `ENV` layer is extractable via `docker history`
regardless, so it buys no security property the repo-default doesn't
already forgo on purpose (the credential is meant to be public).

### D4 — Disclosure via tool description, not a skill

**Alternative considered:** an MCP skill (`SkillProvider`, `skill://
a2web-feedback/SKILL.md`) carrying the full disclosure, discovered via
`resources/list`. Real, working FastMCP mechanism — not rejected because
it doesn't exist, but because `resources/list` is optional in the MCP
spec and not universally implemented by clients, while `tools/list` is
mandatory and always fetched. A skill could end up with *worse*
guaranteed reach than a tool-description line, not better — the opposite
of what disclosure needs. Token cost was also raised as a concern but
turned out not to be the deciding factor: a skill's full content is only
loaded on `resources/read` (on-demand, not automatic); the real
distinction is reach, not cost.

**Chosen:** one short sentence appended to `query`, `fetch_raw`, and
`report_feedback`'s descriptions. `cookies_refresh` excluded — it never
triggers the mechanical reporter, so the disclosure wouldn't be true of
it. Draft text: *"a2web reports its own failures to its maintainers by
default — set `A2WEB_FEEDBACK_ENABLED=false` to opt out."*
`report_feedback`'s existing description line ("Off unless the operator
has configured feedback reporting") is stale under the new default and
gets rewritten alongside this.

### D5 — `test_no_personal_strings` carve-out

The guard's own docstring already anticipates this exact situation
(planning documents under `openspec/changes/**` are excluded because "a
change that *proposes removing* an identifier has to be able to name
it") — the same reasoning extends to a deliberate, reasoned shipped
default. The carve-out itself (exact mechanism: widen `_SKIP_PREFIXES`
vs an explicit per-string allow-list) is an implementation-time call, not
a design fork — either satisfies "explicit and commented," which is the
actual requirement here.

## Risks / Trade-offs

- **[Accepted, named] This is a real, permanent shift in what "installing
  a2web" implies for privacy** — every install now sends failure data,
  including real URLs and agent-authored content, to a third-party
  gateway with no delete path, by default. Mitigated by disclosure (D4)
  and a trivial opt-out, not eliminated — that's the nature of a
  default, not a bug in this design.
- **[Risk] Credential abuse** — a public, shared, write-only key with no
  redaction downstream means anyone (not only a2web installs) can write
  arbitrary permanent content to the gateway's store. Named explicitly in
  the gateway's own ADR 0062 as the accepted trade on that side; nothing
  in this change makes it worse, but shipping the credential in a widely
  distributed public repo does increase its exposure surface
  meaningfully versus today's near-zero adoption.
- **[Trade-off] Rotation cost** — if the shared token needs rotating,
  every a2web install needs a new release to pick up the new default
  (unlike a CI-injected value, which could rotate independent of a2web's
  own release cadence). Accepted per D3's reasoning: the alternative
  doesn't reach all distribution channels anyway.
