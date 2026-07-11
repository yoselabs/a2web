## ADDED Requirements

### Requirement: Answer-bearing structured content exempts a length-independent anti-bot marker from forced escalation

The quality-gate seam (`fetcher.evaluate(...)`) SHALL promote a length-independent anti-bot verdict — `akamai_bmp` or `turnstile` only — to `Verdict.ok` (clearing its subsystem and escalation) when BOTH of the following hold:

1. The extracted `content_md` length is **at or above `LENGTH_FLOOR`** (the response is not thin/shell-shaped).
2. `structured_answer` is `True` — the same `structured_answer: bool` input already accepted by `evaluate()` for the existing bare-`length_floor` promotion, computed by the orchestrator as `any(c.answer_bearing for c in fc.content_candidates)`.

This is a distinct exemption from the existing "Answer-bearing structured content exempts a bare length_floor from failure" requirement — that one only ever fires on **thin** content; this one only ever fires on content **above** the floor. The two SHALL NOT overlap and SHALL NOT be merged into one branch, so each remains independently testable and the thin/stub anti-bot scenarios below are unaffected.

This exemption SHALL NOT extend to `anubis`, `alibaba_punish`, `cf_iuam`, `search_captcha`, or generic `block_page_detected` verdicts — only the two markers that are checked length-independently today (`akamai_bmp`, `turnstile`). Existing callers of `evaluate()` that do not pass `structured_answer` SHALL default it to `False`, preserving current behavior for every call site not yet updated.

#### Scenario: Above-floor content with akamai_bmp marker and strong answer-bearing JSON-LD is promoted to ok

- **WHEN** the gate evaluates a raw-tier `200` response whose extracted `content_md` is at or above `LENGTH_FLOOR`, the `akamai_bmp` marker (`_abck`/`bm_sz` cookie names) is present in `raw_html`, and `fc.content_candidates` contains a `json_synth` candidate with `answer_bearing = True` (a `Product` carrying `offers.price`, `availability`, and other populated fields)
- **THEN** `verdict == Verdict.ok`, `subsystem is None`, no browser escalation is triggered, and extraction proceeds from the existing content

#### Scenario: Above-floor content with turnstile marker and strong answer-bearing JSON-LD is promoted to ok

- **WHEN** the gate evaluates a response above `LENGTH_FLOOR` carrying a `cf-turnstile` marker and an `answer_bearing = True` structured candidate
- **THEN** `verdict == Verdict.ok`, `subsystem is None`, no browser escalation is triggered

#### Scenario: Above-floor content with akamai_bmp marker but no answer-bearing candidate escalates as before

- **WHEN** the gate evaluates a response above `LENGTH_FLOOR` carrying the `akamai_bmp` marker, and `fc.content_candidates` has no `answer_bearing = True` entry (`structured_answer = False`)
- **THEN** `verdict == Verdict.anti_bot`, `subsystem == "akamai_bmp"`, and `escalation.next_tier == "browser"` — behavior is unchanged from today

#### Scenario: Thin content with akamai_bmp marker and a strong answer-bearing candidate still escalates

- **WHEN** the gate evaluates a response whose extracted `content_md` is **below** `LENGTH_FLOOR`, the `akamai_bmp` marker is present, and `structured_answer = True`
- **THEN** `verdict == Verdict.anti_bot`, `subsystem == "akamai_bmp"`, and escalation proceeds — the new exemption does not apply below the length floor; this scenario is orthogonal to (and does not reuse) the existing bare-`length_floor` promotion, which never touches an `akamai_bmp`/`turnstile`-classified verdict

#### Scenario: Existing thin/stub anti-bot scenarios are unaffected

- **WHEN** the gate evaluates `anubis`, `alibaba_punish`, `cf_iuam`, or generic `block_page_detected` markers, with or without `structured_answer`
- **THEN** verdict and escalation behavior are identical to before this change — the new exemption applies only to `akamai_bmp` and `turnstile`
