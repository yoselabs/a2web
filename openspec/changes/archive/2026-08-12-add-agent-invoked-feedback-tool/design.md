## Context

See `proposal.md` for motivation. Grounding facts from the codebase that
shaped this design:

- `OperatorHint.fix` already names specific other tools inline, inside a
  response the agent is already reading (`hints.py`, e.g. `fix="Call
  fetch_raw on this same URL to read the body..."`) — this is the working
  precedent for tool discovery used here, not a load-time tool description.
- `fetcher_response.py`'s envelope discipline treats `operator_hints` (and
  most other fields) as "omitted when empty" — extra fields are for
  deviations, not the common case. Any nudge mechanism has to respect that
  or pay real per-call token cost on responses that would otherwise be
  silent.
- `Confidence` (`models.py`) already grades retrieval quality down for
  reasons short of an outright failure — cross-domain landing, query/title
  mismatch, a failed browser rung, a blocked in-page section — via
  `confidence: low` with `status: ok`. This is an existing, already-computed
  deviation signal, not new state.
- Fetches that fail the quality gate are **never cached**
  (`AGENTS.md`: "Never cache a page that fails the quality gate"). Checked
  directly against `cache.py`. This rules out a design where
  `report_feedback` looks up the mechanical fetch context server-side by
  `url` — it would work for the low-confidence-`ok` branch (content was
  cached) but silently fail for the hint-fired branch (nothing cached),
  which is the branch that matters most.
- `feedback-telemetry`'s own `_record_feedback` (`fetcher/pipeline.py`)
  already reuses one OTLP/HTTP-logs transport, hand-rolled over `httpx`, not
  the OTel SDK's Logs API (rejected there: unstable/private Python API,
  sync-only). This change reuses that same transport rather than building a
  second one.
- Real-world evidence from `feedback-telemetry`'s own shipped attributes: a
  much simpler closed-ish value (`severity`, sent as a plain string) still
  arrived inconsistent once real callers touched it (`"0"`, `"INFO"`,
  `"warning"`, `"critical"`, `"CRITICAL"` all observed on the live stream).
  This is the direct evidence behind rejecting a closed `category` enum on
  `report_feedback` below (D2).

## Goals / Non-Goals

**Goals:**
- Let the calling agent report subjective, qualitative feedback a2web's own
  pipeline structurally cannot detect (content that's mechanically fine but
  wrong for the agent's actual need).
- Reuse existing mechanisms wherever one already exists: the `fix`-names-a-
  tool discovery pattern, `feedback-telemetry`'s OTLP transport, `Confidence`
  as an existing deviation signal.
- Keep the activation cost near zero on both sides: cheap for a2web to nudge
  (bounded envelope cost), cheap for an agent to act on (minimal required
  fields, no forced taxonomy).

**Non-Goals:**
- Not attempting to catch the confidently-wrong case (`status: ok,
  confidence: high`) via any in-band nudge — no signal exists for it, and
  paying envelope cost on every silent-success response to advertise a
  rarely-used tool was rejected (D1).
- Not attempting self-judgment reliability mitigation in this change. A
  bare agent complaint is weak evidence alone (the same self-preference-bias
  concern named in `add-a2web-feedback-channel`'s design D4) — this change
  collects the signal; correlating it against a behavioral cross-check
  (e.g. a `uptake.py`-style re-fetch/escalation pattern on the same `url`
  shortly after a `report_feedback` call) is a plausible follow-up, not
  designed here.
- Not inventing a feedback taxonomy (see D2) or a new correlation-ID
  mechanism (see D3) — both evaluated and explicitly rejected in favor of
  simpler alternatives.

## Decisions

### D1 — Nudge trigger: bounded to `{hint fired} ∪ {confidence == low}`

**Options considered:**
- **Always** (every response, including silent `ok`/`high`): most thorough,
  would also nudge on the confidently-wrong case in principle — but doesn't
  actually solve it (a2web still has no idea anything's wrong; the agent
  would have to notice on its own regardless of the nudge). Costs real token
  budget on every call for a tool that's rarely invoked, breaking the
  envelope-diet discipline the rest of the response shape follows. Also
  carries a real risk: an agent reflexively mentioning `report_feedback` in
  its own reasoning just because it was told about it, generating complaints
  where nothing was actually wrong — diluting exactly the signal this exists
  to collect, and adding to volume concerns already raised against the
  shared gateway (`unify-otel-telemetry-seam` design D5).
- **Bounded to hint-fired only**: cheapest, reuses `_REPORTABLE_SEVERITIES`
  exactly as `_record_feedback` already gates on it. Misses the
  low-confidence-but-mechanically-silent case entirely.
- **Chosen: bounded to `{hint severity ∈ warning/critical} ∪ {confidence ==
  low}`.** When a hint already fired, the nudge appends to that hint's
  existing `fix` text — zero marginal envelope cost, the response already
  carries a hint object. When no hint fired but `confidence == low`, one new
  info-severity hint is synthesized carrying just the nudge — bounded cost,
  because low confidence is already an atypical, non-silent response by
  `Confidence`'s own definition, not a new deviation category invented for
  this purpose.

**Explicitly accepted:** the confidently-wrong gap (`status: ok, confidence:
high`, but the content doesn't answer the agent's actual need) gets no
nudge under this design, ever. No trigger design closes it without paying
the "always" cost above, and paying that cost doesn't actually solve it
either — it only makes the tool's existence marginally more memorable at
the price of noise on every call. Judged not worth it.

### D2 — Tool shape: two free-text fields, no closed category

**Signature:** `report_feedback(url: str, note: str, wanted: str | None =
None)`.

`url` is the correlation key (see D3). `note` is what bothered the agent,
free text. `wanted` is what it would have preferred instead, free text,
optional — sometimes the answer is simply wrong with no specific
alternative in mind.

**Alternative considered and rejected: closed `category` enum**, mirroring
`OperatorHint.code`'s closed-vocabulary pattern. Rejected because the
precedent doesn't transfer: `HINT_CODES` is closed because a2web itself
controls what each code means and validates it at construction, built
iteratively against real observed failure modes it collected. A `category`
here would be the reporting *agent* self-selecting from a taxonomy built
from zero real corpus — and the direct evidence against this already
exists: `feedback-telemetry`'s own `severity` attribute, a simpler
closed-ish value than any feedback taxonomy would be, still arrived
inconsistent once real callers touched it (five different casings observed
on the live stream, per `unify-otel-telemetry-seam` design D5/D7). Forcing
self-categorization risks the same drift, plus a worse failure mode
specific to this case: an agent under time/token pressure picks the
*closest* available bucket rather than the *right* one, silently lossy.
Better to mine categories out of free text later, with a pass that has more
context to calibrate consistently than one agent mid-task guessing alone —
if a taxonomy turns out to be worth having at all. Same reasoning rejects a
self-selected severity field: a2web's own mechanical severity already
exists on the correlated report (D3); asking the agent to also self-rate
severity repeats the forced-taxonomy problem for no proven gain.

**Why two fields, not one free-text blob:** costs nothing extra for an LLM
to fill two short fields versus one, and keeps "what's wrong" separable from
"what I wanted instead" for whoever reads reports later — the original
framing this whole exploration started from ("what agent would like to
have... and what bothers it") named these as two different things.

### D3 — Correlation: reuse `url`, no new ID

**Alternative considered and rejected:** mint an opaque `report_id`/
`trace_id` on `FetchResponse` for the agent to pass back. More precise in
principle, but new wire surface for zero proven need — checked directly
(`models.py`): `FetchResponse` has no such field today, and adding one is a
real envelope-shape change on every response, not a one-line addition.

**Chosen:** `report_feedback` takes the same `url` the agent already has
from the response it's reacting to. Server-side lookup-by-`url` to
auto-enrich the report with the mechanical fetch's own chain/verdict data
was considered and rejected — checked directly: fetches that fail the
quality gate are never cached (`AGENTS.md`), so this would work for the
low-confidence-`ok` branch (content cached) but silently fail for the
hint-fired branch (nothing cached), which is the branch that matters most.
Inconsistent behavior between the two trigger branches was judged worse
than no enrichment at all.

Consequence: `report_feedback` doesn't need to resend anything a2web
already knows (verdict, tier, chain) — the mechanical `_record_feedback`
report already sent that, at the same trigger boundary, moments earlier.
Downstream correlation is by `url` + timestamp proximity — consistent with
how the gateway operator already reasons about this stream (per
`unify-otel-telemetry-seam`'s live probing, records are already correlated
this way in practice, not by a formal ID).

### D4 — Transport: reuse `feedback-telemetry`'s OTLP seam, not a new one

`report_feedback` reports go out via the same POST mechanism
`_record_feedback` already uses (hand-rolled async `httpx` over OTLP/HTTP
logs — the OTel Logs SDK was already evaluated and rejected for that
function's own reasons: unstable/private Python API, sync-only,
`unify-otel-telemetry-seam` design D1). Distinguished from the mechanical
report only by `scope.name` (e.g. `a2web.feedback.agent` vs
`a2web.feedback`), not a second pipeline, second config surface, or second
gateway. Whatever `A2WEB_FEEDBACK_ENDPOINT`/`_API_KEY` already point at is
where this goes too.

### D5 — `report_feedback`'s fields are not gated by `A2WEB_FEEDBACK_INCLUDE_CONTENT`

**Gap found during implementation, not addressed by the original design:**
does `report_feedback`'s `url` (and `note`/`wanted`, which may themselves
reference URLs) get redacted the same way `feedback-telemetry`'s mechanical
report gates content behind `A2WEB_FEEDBACK_INCLUDE_CONTENT`?

**Decision: no.** `A2WEB_FEEDBACK_INCLUDE_CONTENT` exists to control content
a2web itself decides to send on the caller's behalf, passively, as a
byproduct of its own pipeline running (`unify-otel-telemetry-seam` D6/D7).
`report_feedback` is categorically different: the agent actively,
deliberately calls this tool and supplies `url`/`note`/`wanted` as explicit
arguments, fully aware it is sending them to a2web's feedback channel — that
is informed disclosure, not a passive default. Gating it behind the same
flag would also break D3's correlation design outright: with the flag off,
`report_feedback` would have to either send no `url` (making correlation to
the mechanical report impossible) or violate the flag's own contract.
`report_feedback` remains gated by the base `feedback_enabled`/`endpoint`/
`api_key` triple only — same as everything else in this capability; content
inclusion is not a separate concern for a tool whose entire payload IS
caller-supplied content by construction.

**Second gap found while actually building it:** the tool's `url` parameter
must NOT be sent as an OTLP attribute literally named `url` — the gateway's
attribute redaction is name-anchored (`^url$`, `unify-otel-telemetry-seam`
D7) and would mask it regardless of D5's decision that it should pass
through. Sent as `requested_url` instead — already confirmed safe
(`_record_feedback` uses the same name), and a shared field name across
both report types is what makes them joinable downstream. Same class of bug
already caught and fixed once on `_record_feedback`'s own `query` attribute
— worth naming here since it would have been trivial to reintroduce it on
a new field.

### D6 — Shared POST mechanics extracted into one small transport helper

**Alternative considered:** duplicate the ~10-line httpx-POST-with-timeout-
and-error-handling block from `_record_feedback` into a new function for
`report_feedback`, per the codebase's general preference for "three similar
lines over a premature abstraction." Rejected here specifically because D4
already commits to "reuse the transport, not build a second one" as a
stated requirement (spec: "a2web SHALL NOT introduce a second transport") —
duplicating the POST mechanics would let the two call sites drift
independently (a timeout change, a new exception type to catch) in exactly
the way D4 says not to.

**Chosen:** a small new module owns the shared piece — resolving
`feedback_enabled`/`endpoint`/`api_key`, building the `resourceLogs`
envelope, POSTing with the `X-Api-Key` header and 5s timeout, and
swallowing delivery failures to `log_warning`. `_record_feedback`
(mechanical, pipeline-triggered) and the new agent-feedback function both
call it, differing only in `scope.name` and the log-record attributes they
build. Neither owns the transport; both are thin callers of it.

## Risks / Trade-offs

- **[Accepted, not a risk to mitigate] The confidently-wrong gap stays
  open.** See D1. Named explicitly so it isn't mistaken for an oversight
  later.
- **[Risk] Self-judgment reliability** — a bare `report_feedback` call is
  one model's unverified opinion, potentially biased (the self-preference-
  bias concern from `add-a2web-feedback-channel` design D4 applies here
  too, arguably more directly since this is explicit self-report rather
  than externally-grounded hint severity).
  → **Mitigation, not designed here**: correlate against a behavioral
  signal, e.g. whether the agent re-fetches/escalates the same `url` shortly
  after calling `report_feedback` — the same shape as `uptake.py`'s existing
  `note_visit`/`record_suggestions` follow-through tracking. Left as a
  named future direction, not implemented in this change.
- **[Risk] Nudge-induced noise** — telling an agent a tool exists,
  even only on already-atypical responses, may produce some complaints that
  wouldn't have been filed unprompted. Bounded by D1's trigger choice
  (only on responses already flagged as atypical) rather than eliminated.
- **[Risk] Free-text `note`/`wanted` inherit the same prompt-injection-
  surface caution already named for feedback bodies in
  `unify-otel-telemetry-seam` design D5** — anything downstream that feeds
  stored reports back into an LLM (e.g. a future auto-triage pass) must
  treat them as data, not instructions. Same caution, not a new one.
- **[Trade-off] No closed category means no cheap aggregate counts by
  complaint type** at ingest time (D2) — accepted; the alternative's
  failure mode (lossy forced self-categorization) was judged worse than
  deferring taxonomy-building to a later pass over real free-text data.

## Open Questions

- Whether the behavioral-correlation mitigation for self-judgment
  reliability (Risks, above) is worth a follow-up change once real
  `report_feedback` data exists to evaluate it against — genuinely
  deferrable, doesn't change this design's shape.
- Exact nudge sentence wording (appended to `fix`, or a fresh hint's
  `message`) — copy-level detail, not architecture; resolve during
  implementation the same way existing `HINT_CODES` factories were written.
