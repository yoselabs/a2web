# Design — tighten-archive-rule-for-reddit

## Context

The planner rule at `src/a2web/actions/playbook.py:92-100` was authored when the only producer of `Verdict.not_found` on a Reddit-comment URL was the Reddit site handler's `_archive_escalation_signal` path — an authoritative, handler-confirmed "this content is gone" signal. The rule short-circuits to `RetryViaArchive(url)` because Wayback frequently holds a pre-deletion capture.

After v0.22 `expand-js-shell-markers`, the raw tier (via `block_detector`) classifies Reddit's anti-bot JS interstitial as `subsystem="js_required"`. That can surface on the gate observation as `Verdict.not_found` (the gate's verdict for "no extractable content + JS marker present") with `subsystem="js_required"` and an `escalation=EscalationSignal(next_tier="browser", ...)`. The existing `gate_outcome + escalation.next_tier == "browser"` rule already handles that case correctly — but only when it is consulted with the gate observation as `log[-1]`. If a follow-up tier observation lands on top, or if the URL-shape rule is checked before the planner sees the gate (in practice the rule order in `decide_next` puts the Reddit-comment rule below the gate-browser rule, so this case is mostly handled), there is still a window where the URL-pattern rule fires on a tier observation that carries `not_found` without a `js_required` discriminator on `log[-1]`.

The bench evidence (`eval/runs/2026-05-25_183411/`) shows a real path where `tier=raw verdict=not_found extras=js_required` reached the planner without a winning browser-escalation. The narrowing below closes that path structurally.

## Decisions

### Decision 1: What is the precise discriminator?

The discriminator is **two signals, OR-combined, that together mean "truly gone"**:

1. The most-recent observation is `authoritative=True` (the Reddit handler vouches the thread is gone — set by `_archive_escalation_signal`).
2. The most-recent observation has `status_code == 404` (a hard HTTP 404 from any tier).

Plus a **veto**: if any observation in the log carries `subsystem == "js_required"`, the rule does NOT fire — regardless of the URL pattern or the `not_found` verdict. The JS-shielded case has a dedicated escalation path (the gate's `escalation.next_tier == "browser"` signal), and short-circuiting to archive would clobber it.

**Why a veto rather than relying on rule order alone**: `decide_next` reads `log[-1]` to drive tier-vs-gate rules. If a tier appended `not_found` after a gate observation, the gate's browser-escalation signal is not on `log[-1]`. The URL-shape rule would fire even though the log holds clear evidence the right answer is browser. A veto that walks the log (not just `log[-1]`) is the correct shape.

**Rejected alternatives**:

- *Match only `authoritative=True`* — leaves the hard-404 case unhandled; a 404 from the raw tier on a deleted thread that the Reddit handler did not claim (e.g. short URL that resolved to a deleted post) would never get to archive.
- *Match only `status_code == 404`* — leaves the handler's `_archive_escalation_signal(status_code=0, authoritative=True)` path unhandled.
- *Require the gate to have run first* — see Decision 2.

### Decision 2: Should the rule require the gate to have run first?

**No.** Arguments for:

- The gate is the canonical place where block_detector runs; if the gate has not run, there is no `js_required` veto signal and the rule could fire on a raw tier's `not_found` that was actually JS-shielded.

Arguments against (which win):

- The gate does not always run. Some failure paths in the tier loop short-circuit before the gate (e.g. a tier that returns empty body + `not_found` verdict skips the gate by design — there is nothing to gate). Requiring the gate would make the rule inapplicable in exactly the case the original rule was designed for (handler-confirmed deletion: no body, no gate, just an authoritative signal).
- The Reddit handler itself sets `authoritative=True` (via the handler-shape projection) on its `_archive_escalation_signal` path. The handler IS the authority on whether the thread is gone — that is the whole point of `authoritative`.
- The block_detector signal that the raw tier surfaces (`subsystem="js_required"`) can be present on a *tier* observation too — the block_detector is consulted both by the gate and (in some paths) by the tier itself. Vetoing on `subsystem == "js_required"` across the log captures both placements.

**Resolution**: gate-not-run is not a precondition; the discriminator is the two-signal "truly gone" check plus the `js_required` veto.

### Decision 3: Generalisation to other handlers (HN, Discourse, etc.)

**Out of scope for this proposal.** The same structural issue (URL-pattern rule + closed-enum verdict that conflates two failure modes) exists for HN deleted submissions, Discourse-style PHP boards that JS-shield, and probably a handful of other handlers. A clean fix is a typed `escalation: EscalationSignal | None` field on tier observations carrying `next_tier="archive"`, set explicitly by the handler when it confirms deletion — then the planner switches on the typed signal instead of regex-matching URLs.

That refactor will land as a separate proposal (`planner-rules-typed-priority`). This proposal patches only the Reddit rule because Reddit is the only rule with confirmed bench-failure evidence today, and the patch is small enough to ship independently.

### Decision 4: Why not remove the URL-based rule and rely solely on the gate signal?

The Reddit handler's `_archive_escalation_signal` path explicitly does **not** run a gate (it returns `body=b""`, `verdict=not_found` directly — there is nothing to gate). If the URL-based rule is removed and the planner relies solely on `last.escalation.next_tier == "archive"` from a gate observation, the handler-confirmed deletion case dead-ends at `Continue` with no archive dispatch.

Two alternatives to a URL-pattern rule would work structurally:

1. Have the Reddit handler emit `escalation=EscalationSignal(next_tier="archive", reason="reddit_deleted_try_archive")` on its tier observation, and have the planner switch on that. This is the `planner-rules-typed-priority` direction.
2. Keep the URL-pattern rule but narrow it as proposed here.

This proposal chooses (2) because (1) is part of the deferred structural change and would expand the diff scope past a single rule edit. The narrowing keeps the URL-based shortcut intact for the handler-confirmed case while structurally vetoing the JS-shielded mis-fire.

## Risks / Trade-offs

- **Risk**: the `subsystem == "js_required"` veto could be too broad — e.g. a Reddit thread where an earlier (failed) raw attempt produced `js_required` but a later handler attempt authoritatively confirmed deletion. Mitigation: the handler's authoritative signal is what populates `authoritative=True` on `log[-1]`; the veto only fires if the *log holds* `js_required`, but the rule still requires `(authoritative or status_code == 404)` regardless — so the handler-confirmed case wins inside its own check. The veto's intent is "do not fire if there is *evidence* this is JS-shielded"; if the handler claims authoritatively that the thread is deleted, that supersedes the earlier raw-tier hint. We will document this precedence explicitly in the scenario and add a test.
- **Trade-off**: this is a targeted patch, not a structural fix. The same shape applies to other handlers and the URL-regex approach is brittle. The follow-up `planner-rules-typed-priority` proposal addresses the structural issue.
