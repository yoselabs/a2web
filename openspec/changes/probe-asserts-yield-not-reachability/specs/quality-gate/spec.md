## MODIFIED Requirements

### Requirement: The block catalogue covers bounded bespoke-wall phrases

`_BLOCK_PATTERNS` SHALL include high-precision phrases for the bounded set of common bespoke walls that today fall through to a bare `length_floor` — at minimum a PerimeterX interstitial ("pardon the interruption"), a generic "access denied", "request unsuccessful" (Incapsula/Imperva), and a browser-verification interstitial ("checking your browser"). A sub-floor body matching one SHALL return `BlockVerdict.block_page_detected` (a hard wall), so a genuinely-walled bespoke interstitial is not downgraded to the thin/empty hedge. The catalogue is bounded on purpose: the wall space converges on a small number of mitigation vendors, unlike the open-ended empty-result phrasing space (which is therefore NOT catalogued as a promotion authority).

A pattern added to this catalogue SHALL ship with a captured page as its
witness. A hand-written approximation of an interstitial cannot witness whether
the pattern matches the real one — it encodes the same assumption as the pattern
it tests.

#### Scenario: A PerimeterX interstitial is a hard wall

- **WHEN** the gate evaluates a sub-floor body containing "Pardon the interruption"
- **THEN** `verdict == BlockVerdict.block_page_detected` (a hard wall), NOT a bare `length_floor`

#### Scenario: A browser-verification interstitial is a hard wall

- **WHEN** the gate evaluates a SUB-FLOOR body containing "Checking your browser"
- **THEN** `verdict == BlockVerdict.block_page_detected` (a hard wall), NOT a
  bare `length_floor` that the thin-not-wall terminal would hedge as a possible
  empty result

> Measured 2026-07-28: a nitter instance served a 6822-byte browser-verification
> interstitial with HTTP 200. It rendered to 416 characters — under the 500-char
> floor, so it was reported as thin rather than walled.
>
> **The sub-floor qualifier is load-bearing and is a stated limit, not an
> oversight.** `_BLOCK_PATTERNS` is consulted only when `content_md` is below
> `LENGTH_FLOOR`. An interstitial from the same vendor family that rendered PAST
> the floor would still read as content, and this catalogue entry does not
> change that. Length-independent matching is reserved for the markers that are
> distinctive enough to carry it (turnstile, Akamai, Baxia); a bare English
> phrase is not, and making it length-independent would put every article about
> anti-bot systems at risk of a false wall.
