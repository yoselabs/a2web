## ADDED Requirements

### Requirement: Answer-bearing structured content exempts a bare length_floor from failure

The quality-gate seam (`fetcher.evaluate(...)`) SHALL promote a **bare** `Verdict.length_floor` to `Verdict.ok` (clearing its subsystem) whenever the collected content menu contains an **answer-bearing structured candidate** — a `ContentCandidate` whose `answer_bearing` flag is set (see the `extraction` and `json-extract` capabilities) — mirroring the existing small-but-complete `is_json` promotion. This lets `_phase_extract_answer` run and answer from the structured data instead of the fetch terminating as `failed` with `answer=null`.

The seam SHALL accept a `structured_answer: bool` input, computed by the
orchestrator as `any(c.answer_bearing for c in fc.content_candidates)`, and SHALL
apply:

```
if structured_answer and verdict is Verdict.length_floor:
    verdict = Verdict.ok
    subsystem = None
```

The promotion is SCOPED to the **bare** `length_floor` case (subsystem unset). It
SHALL NOT fire when the verdict carries a subsystem indicating a wall or an
escalatable shell — specifically `js_required`, `thin_browser_response`,
`jina_stub`, or any anti-bot / block-page verdict. The promotion block SHALL run
after those branches so it only ever rewrites a bare `length_floor`, never a
verdict another branch has already classified. A genuine SPA shell therefore
continues to escalate to the browser tier even when it embeds a stub structured
payload.

The `answer_bearing` signal is authoritative for "small-but-complete": it is set
only for strong structured payloads (≥3 populated fields of an answer-bearing
schema — see `json-extract`), so a stub `LocalBusiness` carrying only `name` and
`url` does NOT trigger promotion.

#### Scenario: Thin contact page with strong LocalBusiness JSON-LD is promoted to ok

- **WHEN** the gate evaluates a raw-tier 200 response whose extracted
  `content_md` is under `LENGTH_FLOOR`, no SPA/anti-bot markers match, and
  `fc.content_candidates` contains a `json_synth` candidate with
  `answer_bearing = True` (a `LocalBusiness` carrying `telephone`, `email`,
  `url`, `name`, `image`)
- **THEN** `verdict == Verdict.ok`, `subsystem is None`, extraction runs, and
  the answer is produced from the structured candidate

#### Scenario: Thin page with only a weak structured payload stays length_floor

- **WHEN** the gate evaluates a thin response whose only structured candidate is
  a `LocalBusiness` with just `name` + `url` (2 fields, `answer_bearing = False`)
- **THEN** `structured_answer == False`, `verdict == Verdict.length_floor`,
  `subsystem is None` — behavior is unchanged from today

#### Scenario: JS-required SPA shell is NOT masked by an embedded strong payload

- **WHEN** the gate evaluates a thin response that matches the `js_required`
  markers (`<script>` + SPA root marker) AND also carries a strong `Product`
  ld_json payload rendered into an `answer_bearing` candidate
- **THEN** `verdict == Verdict.length_floor`, `subsystem == "js_required"`,
  `escalation.next_tier == "browser"` — the structured-answer promotion does not
  fire on a walled/shell verdict; browser escalation proceeds

#### Scenario: Anti-bot verdict is NOT masked by an embedded payload

- **WHEN** the gate evaluates a response fingerprinted as `alibaba_punish` /
  `anubis` / `cf_iuam` that also carries an OG/ld_json stub
- **THEN** the anti-bot / block verdict and its escalation stand unchanged; the
  structured-answer promotion does not fire (it is scoped to bare `length_floor`)

#### Scenario: A page with no structured candidate is unaffected

- **WHEN** the gate evaluates a thin page whose only candidate is trafilatura
  prose (`answer_bearing = False`) and no embedded JSON
- **THEN** `structured_answer == False` and the verdict follows the existing
  classifier path (bare `length_floor` → `failed`)
