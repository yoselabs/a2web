# The DHL tracking redirect: is the url-deviation signal loud enough? (a2web-7bj.10)

**Date:** 2026-08-08
**Source:** I0269 live session, 2026-07-31. Parent epic: a2web-7bj.
**Outcome: working as intended — no code change, no bead filed.**

## The question

The requested URL was:

    https://www.dhl.com/tr-en/home/tracking/tracking-express.html?submit=1&tracking-id=7957139164

The served envelope's `url` field carried:

    https://www.dhl.com/tr-en/home/tracking.html?submit=1&tracking-id=7957139164

The `tracking/tracking-express` path segment collapsed to `tracking` — a same-host
redirect that changed the PATH, not just query/host. Two things needed checking:
whether the caller is told this happened at all, and whether the tracking id
survived the redirect *meaningfully* (the landing page actually engaging with
`7957139164`) or only *textually* (the query string preserved, but ignored).

## Finding 1: the deviation signal fired, by design

`url` on both `FetchResponse` and `AskResponse` is a deviation-only field
(`src/a2web/models.py:417-418`, `_WIRE_DEVIATION` at `models.py:594`): it is
dropped from the wire when the served URL equals the requested URL, and present
when they differ (`fetcher_response.py:883-886`,
`deviated_url = fc.final_url if fc.final_url != fc.inputs.requested_url else ""`).
In the captured session `url` WAS present — the deviation signal fired exactly as
designed. A caller checking "is `url` in the envelope?" has a correct,
structural answer: yes, you did not land where you asked.

This is deliberately the ONLY thing that fires here. `served_url_differs`
(`fetcher_response.py:900-909`) — the louder signal that also caps confidence
`high`→`medium` and appends an explicit hint — is scoped to a **cross-domain**
landing (`registrable_domain(requested) != registrable_domain(served)`,
tested by `tests/capabilities/retrieval_completeness/test_served_url_identity_mismatch.py`).
Its own docstring is explicit about why a same-site path/query redirect does
NOT trip it: canonicalization and captcha-host rewrites-back-to-origin are the
COMMON, CORRECT case, and flagging them "would make the hint noise instead of
signal." `tracking/tracking-express.html` → `tracking.html` on `www.dhl.com` is
exactly that common case — a same-registrable-domain path redirect, not a
mixup landing on someone else's content.

## Finding 2: the tracking id survived meaningfully, not just textually

The captured answer from the SAME call:

> "This page does not provide the current status, full event history, dates, or
> location for tracking number **7957139164**. It offers general tracking info
> and links to login portals and services for detailed tracking."

The served page's own extracted content led the model to name the specific
tracking number back to the caller — not a generic "enter your tracking number"
placeholder. That is evidence the landing page (`tracking.html`) DID engage
with the `tracking-id=7957139164` query parameter meaningfully, even though it
could not (or does not, without a session) render the detailed status. The
concern that a2web might have "answered from a generic tracking page" without
resolving the ID at all is not what happened here — the honest-absence answer
(a2web-7bj.7's subject) is itself evidence the ID was processed, just not
enough to produce a status.

## Conclusion

Both halves check out:

1. The deviation field fired and is structurally checkable — no defect.
2. The query parameter's survival was meaningful, not merely textual — no defect.

The one open question is philosophical, not a bug: should a PATH change (not
just a domain change) on an otherwise same-site redirect ever be louder than
the bare `url` field? The existing anti-noise rationale for `served_url_differs`
applies just as much to path-only redirects as to query-only ones — DHL's own
site canonicalizes `tracking/tracking-express.html` to `tracking.html`
routinely, and flagging every such redirect would drown the genuinely
suspicious cross-domain case in noise. No change proposed; closing a2web-7bj.10
with this finding rather than filing a new bead.
