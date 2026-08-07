"""The operator-hint catalogue — the closed code vocabulary and every factory.

**This is what an agent is told when a fetch does not go cleanly.** Every string
here is read by a model deciding what to do next, so the wording is load-bearing
in a way ordinary prose is not: rewording a hint changes downstream behaviour.
Treat an edit here as a contract change, not a copy edit.

Lifted out of `models.py` on 2026-08-01. It had grown to roughly half that
file — a module whose docstring promises "public envelope and diagnostic types"
— and the catalogue is a different thing from the envelope: the envelope is a
SHAPE that MCP clients parse, this is COPY that models read. They change for
different reasons and on different review standards.

Three rules hold this together, each with a guard:

* the code set is CLOSED (`HINT_CODES`) and validated at construction, so a
  typo cannot reach the wire as a hint nothing can match;
* every declared code has exactly one factory HERE, and `OperatorHint` may not
  be constructed anywhere else — otherwise the catalogue a reader sees is the
  incomplete half, which is the state this module was created to end;
* lookups go through `has_hint`, which validates the code it is asked about,
  because a dispatch on a renamed code fails SILENTLY — returning False forever
  while the branch it guards quietly stops running.

All three are enforced by `tests/architecture/test_every_hint_code_has_a_factory.py`.

Severity is stated once, on `HINT_CODES` below, and cited rather than restated:
confidence sets severity, not disappointment. A 404 is never `critical`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Literal

from pydantic import (
    BaseModel,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

#: The CLOSED set of operator-hint codes (change `unify-the-response-contract`).
#:
#: `code` is the field agents branch on, which makes it a wire contract — but it
#: was a bare `str`, so a typo produced a hint nothing could match and nothing
#: would report. Four dispatch sites compared it against string literals; a
#: rename on one side alone would have silently stopped matching.
#:
#: Declared LITERALLY, in one place, for the same reason `wire._TSV_FIELDS` is
#: literal: the set IS the contract. Two of these (`reddit_forbidden_try_archive`,
#: `reddit_deleted_try_archive`) were invisible in any census of `code="..."` —
#: they reach `OperatorHint` through a `code=reason` parameter, which is exactly
#: the shape a closed vocabulary exists to surface.
#:
#: Severity ladder, stated once and cited by the factories (§2.6):
#:   `critical` — a WALL. The URL was not retrieved and the caller must act
#:                (`try_user_browser`, `paid_auth_error`, `fetch_deadline_exceeded`).
#:   `warning`  — UNVERIFIED. Something is probably wrong but a2web cannot
#:                corroborate it (`content_thin`, an unverified 404).
#:   `info`     — VERIFIED and merely worth knowing (a corroborated dead URL,
#:                a partial listing whose totals are known).
#: A 404 is never `critical`: confidence, not disappointment, sets severity.
HINT_CODES: frozenset[str] = frozenset(
    {
        "answer_truncated",
        "archive_snapshot_age",
        "browser_internal_error",
        "browser_unavailable",
        "captcha_redirect",
        "comments_partial",
        "content_empty",
        "content_guidance",
        "content_not_found",
        "content_thin",
        "cookies_stale",
        "extraction_empty",
        "fetch_deadline_exceeded",
        "index_lost",
        "listing_more",
        "listing_partial",
        "llm_error",
        "llm_unavailable",
        "paid_auth_error",
        "reddit_deleted_try_archive",
        "reddit_forbidden_try_archive",
        "retrieval_incomplete",
        "section_unretrieved",
        "served_url_differs",
        "try_user_browser",
    }
)


class OperatorHint(BaseModel):
    """Structured hint about how the fetch could be improved.

    `code` is a stable agent-readable identifier drawn from the closed
    `HINT_CODES` vocabulary above. Agents may branch on `code` to take a next
    action; humans read `message` and `fix` for context and remediation. Both
    audiences are first-class — the field landed under the "operator" name
    historically, not because agents shouldn't read it.

    An unknown code raises at construction rather than reaching the wire. A code
    nothing can match is a hint that cannot be acted on, which for the ADR-0009
    signals is the difference between a loud miss and a silent one.
    """

    code: str

    @field_validator("code")
    @classmethod
    def _code_is_declared(cls, value: str) -> str:
        if value not in HINT_CODES:
            msg = (
                f"operator-hint code {value!r} is not in the closed HINT_CODES "
                "vocabulary. Add it there — the set is the wire contract agents "
                "branch on."
            )
            raise ValueError(msg)
        return value

    message: str
    fix: str | None = None
    severity: Literal["info", "warning", "critical"] = "info"

    @model_serializer(mode="wrap")
    def _omit_default_severity(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        """Drop `severity` from the wire when it is the default `info`, and
        drop `fix` when it carries no actual guidance (`None` or `""`).

        Keeps existing operator-hint snapshots stable — only a `critical`
        hint (e.g. `try_user_browser`) surfaces the new `severity` key, and a
        hint with no remediation step (e.g. `content_guidance`, which is pure
        informational context) omits `fix` rather than emitting a dead `""`.
        """
        data = handler(self)
        if data.get("severity") == "info":
            data.pop("severity", None)
        if not data.get("fix"):
            data.pop("fix", None)
        return data


def has_hint(hints: Iterable[OperatorHint], code: str) -> bool:
    """True when `code` is present, with the code itself checked against the vocabulary.

    The closed `HINT_CODES` set plus the `OperatorHint` validator already make a
    bad code impossible to CONSTRUCT. The dispatch side had no such protection
    and the failure is asymmetric: `any(h.code == "llm_unavailble" ...)` — or a
    correctly-spelled code that was later renamed — does not raise, it silently
    returns `False` forever, and the branch it guards quietly stops running.
    That is the harder bug of the two, because nothing reports it.

    So the lookup validates its own argument. A renamed or mistyped code fails
    loudly at the call site instead of reading as "no such hint present".
    """
    if code not in HINT_CODES:
        msg = (
            f"operator-hint code {code!r} is not in the closed HINT_CODES "
            "vocabulary, so this lookup could only ever return False. If the "
            "code was renamed, update this call site; if it is new, declare it."
        )
        raise ValueError(msg)
    return any(hint.code == code for hint in hints)


def try_user_browser_hint(url: str) -> OperatorHint:
    """The critical never-silently-miss escalation hint for a walled URL.

    Capability-generic (never names a specific browser product). Imperative:
    the caller must either open the URL in a real browser tool or explicitly
    tell the user the source could not be retrieved. Emitted eagerly by the
    Reddit handler and late (after the tier ladder) for other walled hosts.
    """
    return OperatorHint(
        code="try_user_browser",
        message=(
            f"This URL was NOT retrieved — it is behind an anti-bot / paywall wall ({url}). "
            "You do NOT have this content; do not answer as if you do. You MUST either open it "
            "in a real browser tool (a logged-in browser can pass this wall) OR explicitly tell "
            "the user this source could not be retrieved and what is missing."
        ),
        fix="Open the URL in a real-browser tool and read the page, or report the gap to the user.",
        severity="critical",
    )


def content_not_found_hint(url: str, *, verified: bool) -> OperatorHint:
    """The not-found signal for an HTTP 404 — honest, and severity-scaled by confidence.

    `verified=True` (a browser render corroborated the 404, or a handler is
    authoritative): the content is not there, reported as a plain fact at
    `severity: info` — NO soft-404 caveat, NO browser prescription (a dead URL is
    not a wall; commanding the caller to open it would waste a browser session on
    a page that does not exist).

    `verified=False` (the soft-404 check could not complete — browser budget
    spent, pool unavailable, or the browser saw something else): most likely a
    dead URL, at `severity: warning`, disclosing the SMALL residual chance a
    bot-defense served a soft-404 masking real content, with the caller's own
    browser as the residual test. Never `critical` — a 404 is not an anti-bot wall.
    """
    if verified:
        return OperatorHint(
            code="content_not_found",
            message=(
                f"This URL returned HTTP 404 — the content was not found ({url}). "
                "A rendered browser confirmed it; this is most likely a dead or wrong URL."
            ),
            fix="Verify the URL is correct; the page does not appear to exist.",
            severity="info",
        )
    return OperatorHint(
        code="content_not_found",
        message=(
            f"This URL returned HTTP 404 — the content was not found ({url}). Most likely a dead or wrong URL. "
            "Small residual chance a bot-defense served a soft-404 masking real content."
        ),
        fix=(
            "Verify the URL. If you are confident the content exists, open it in your own "
            "real-browser tool — a logged-in browser can pass a soft-404 wall."
        ),
        severity="warning",
    )


def content_thin_hint(url: str) -> OperatorHint:
    """The thin-but-retrieved signal for a corroborated-thin HTTP 200 — honest, WARNING.

    a2web fetched an HTTP 200 that rendered under the extraction length floor even
    after a real headless browser rendered it, and found NO hard-wall evidence.
    That profile is genuinely AMBIGUOUS: it may be an empty result set / a minimal
    page, OR a bespoke wall whose interstitial text a2web could not fingerprint (or
    an IP-reputation wall the same-egress browser could not rule out). a2web does
    NOT assert which — the discriminator is not reliably in the body text. So this
    carries neither the critical `try_user_browser` klaxon (crying wolf on every
    empty storefront search) nor a false "this is empty" verdict. The retrieved
    body is tiny and rides the envelope (`thin_content`); the caller — which can
    read it — decides. `warning`, never `critical`.
    """
    return OperatorHint(
        code="content_thin",
        message=(
            f"This URL was retrieved (HTTP 200) but rendered thin ({url}) — even a headless browser "
            "returned very little content. This is AMBIGUOUS: it could be an empty result set (e.g. a "
            "search with no matches) or a minimal page, OR content behind a wall a2web could not "
            "fingerprint. The retrieved body is attached as `thin_content` — read it to decide which."
        ),
        fix=(
            "Read the attached `thin_content` — it often settles it (e.g. a visible 'no results', "
            "or a visible block/challenge notice). If it reads walled or empty-but-you-need-more, "
            "open the URL in your own real-browser tool."
        ),
        severity="warning",
    )


def content_empty_hint(url: str) -> OperatorHint:
    """The corroborated-empty signal — a search that genuinely returned no results, INFO.

    Distinct from `content_thin` (the ambiguous case): here the empty reading is
    CORROBORATED — an empty-result marker matched, the page was retrieved across
    independent egress paths (incl. a foreign-egress tier), and NO wall evidence
    (hard-wall gate OR a challenged subresource OR a 4xx anywhere) is in the log.
    So "no results" IS the complete, correct answer, not a miss — `info`, and the
    fetch is `ok`, never `retrieval_incomplete`. The thin body still rides
    `thin_content` so the caller can confirm the emptiness itself.
    """
    return OperatorHint(
        code="content_empty",
        message=(
            f"This URL was retrieved and reports NO results ({url}) — corroborated across "
            "independent fetch paths with no wall evidence, so this is a genuine empty result set, "
            "not a block. 'No results' is the complete answer; the retrieved body is attached as "
            "`thin_content` to confirm."
        ),
        fix="Treat this as an authoritative empty result. If you expected matches, re-check the query or the source URL.",
        severity="info",
    )


def comments_partial_hint(*, loaded: int, total: int) -> OperatorHint:
    """Honest partial-comments signal (reddit-via-zyte content-expectations).

    Informational (not critical): the fetch DID retrieve content — a ranked
    sample — but fewer comments than the thread advertises. Names the loaded
    and total counts so an agent knows it is holding a top-N sample, never the
    complete thread. Pairs with the structured `comments_loaded`/`comments_total`
    fields on the response envelope.
    """
    return OperatorHint(
        code="comments_partial",
        message=(
            f"Loaded the top {loaded} of {total} comments (sorted by top). Deeper/nested replies and "
            "comments beyond the fetch limit were NOT retrieved — this is a ranked sample, not the "
            "complete thread. Do not claim to have every comment."
        ),
        fix="Treat this as a top-ranked sample; to read a specific deeper reply, open the thread in a browser tool.",
        severity="info",
    )


def fetch_deadline_hint(url: str, *, seconds: float, about_to: str) -> OperatorHint:
    """The per-fetch budget was spent before the URL was retrieved.

    `critical`, and worded as a2web's own decision. Every hop was individually
    bounded, but until 2026-08-01 nothing bounded their SUM — a ladder walk of
    handler → raw → jina → archive → browser → paid plus extraction can spend
    over six minutes while the caller holds an open tool call. The deadline is a
    backstop against a pathological walk; when it fires, the honest report is
    that a2web ran out of budget, NOT that the site is slow or unreachable
    (a2web has no evidence for either).

    Names the stage that was about to start, because that is the actionable
    part: a deadline spent before `tier:browser` and one spent before
    `tier:zyte` point at very different problems.
    """
    return OperatorHint(
        code="fetch_deadline_exceeded",
        severity="critical",
        message=(
            f"This URL was NOT retrieved ({url}). a2web spent its whole "
            f"{seconds:g}s per-fetch budget and stopped before starting "
            f"`{about_to}`. This is a2web's own limit, not a statement about the "
            "site — the page may well be reachable given more time."
        ),
        fix=(
            "Raise A2WEB_FETCH_DEADLINE_S if this URL legitimately needs a long "
            "ladder walk, or retry: a deadline is often spent on one slow hop "
            "that succeeds on a second attempt."
        ),
    )


def paid_auth_error_hint(url: str, *, tier: str) -> OperatorHint:
    """A keyed paid tier rejected its credential — an OPERATOR fault, loud.

    `critical`, like `try_user_browser`, because it is equally terminal: the URL
    was not retrieved and the caller cannot route around it. Unlike a wall it is
    not the CALLER's problem to solve — the person who can fix it holds the key,
    so the fix names the credential rather than prescribing a browser. Emitting
    `try_user_browser` here would send the caller down the wrong path entirely.

    This hint was claimed by three separate places before it existed:
    `fetcher_response` seeded `retrieval_incomplete` for this verdict *because*
    it "keeps its OWN dedicated hint", `_apply_terminal`'s docstring said the
    same, and the terminal-hint coherence guard allowlisted `operator_error` to
    `{None}` citing a hint "emitted at the paid tier". A bad key therefore
    produced `failed` + `retrieval_incomplete` with nothing naming the remedy,
    which the never-silently-miss floor explicitly requires.
    """
    return OperatorHint(
        code="paid_auth_error",
        message=(
            f"This URL was NOT retrieved ({url}). The paid fallback tier "
            f"`{tier}` rejected its API key (authentication or billing failure), "
            "so the last-resort retrieval path is unavailable. You do NOT have "
            "this content; do not answer as if you do."
        ),
        fix=(
            f"An operator must fix the `{tier}` credential — check the API key is "
            "valid and the account's billing is current. This is a configuration "
            "fault, not an anti-bot wall; retrying or using a browser will not help."
        ),
        severity="critical",
    )


def section_unretrieved_hint(sections: list[str]) -> OperatorHint:
    """A supplementary section of a multi-part page could not be retrieved.

    The primary object WAS retrieved and is useful, so failing the whole fetch
    would be worse than this — but the caller must not read the missing section
    as *absent from the source*. Until 2026-07-31 the GitHub handler swallowed a
    rate-limited sub-fetch and rendered the section empty, making a throttled
    comments call indistinguishable from an issue with zero comments (ADR-0009).

    ONE code carrying the section names, not a code per section: the sections
    are handler-specific and `TierResult.operator_hint` is singular, so a code
    per section would grow the catalogue per handler and still not fit a fetch
    that degraded twice.

    `warning`, not `critical` — nothing here suggests a wall, and the
    `try_user_browser` klaxon must keep meaning exactly one thing.
    """
    named = ", ".join(sections)
    return OperatorHint(
        code="section_unretrieved",
        message=(
            f"These sections were NOT retrieved and are missing from the content below: {named}. "
            "The rest of the page was retrieved normally. Do not read their absence as "
            "meaning the source has none — treat them as unknown."
        ),
        fix=("Usually an API rate limit; retry later, or set a credential (e.g. A2WEB_GITHUB_TOKEN) to raise the quota."),
        severity="warning",
    )


def listing_partial_hint(*, loaded: int, total: int) -> OperatorHint:
    """Honest partial-listing signal (listing-completeness sufficiency axis).

    Informational (not critical): the fetch DID return real records — but fewer
    than the page advertises, because infinite-scroll / lazy-load only
    materialised the first batch. Names the loaded and total counts so an agent
    knows it is holding a truncated sample, never the whole listing. Pairs with
    the structured `items_loaded`/`items_total` fields on the response envelope.
    """
    return OperatorHint(
        code="listing_partial",
        message=(
            f"Parsed {loaded} of {total} listed items — the rest load on scroll / a later page and were "
            "NOT retrieved. This is a partial sample, not the complete listing. For a narrower, complete "
            "set, refine the query (for a search) or open the page in a browser tool."
        ),
        fix="Narrow the search query for fewer, complete results, or open the URL in a browser tool to scroll the full listing.",
        severity="info",
    )


#: Above this, an archive snapshot is old enough that time-sensitive facts
#: (price, availability, rating, "who works here") should be treated as
#: unverified. One year: coarse on purpose — see `archive_snapshot_age_hint`.
_ARCHIVE_STALE_DAYS = 365


def listing_more_hint(*, loaded: int) -> OperatorHint:
    """Honest structural "more exists" signal — a listing with no numeric oracle.

    Informational (not critical): the fetch returned `loaded` real records, and
    the page exposes a pagination / infinite-scroll control, so more items exist
    beyond this batch — but the page advertises no total, so the shortfall
    cannot be quantified (unlike `listing_partial`). The agent must not treat
    the retrieved records as the complete listing. Pairs with the structured
    `items_loaded` field (set) while `items_total` stays absent (unknown).
    """
    return OperatorHint(
        code="listing_more",
        message=(
            f"Parsed {loaded} items, but the page exposes a load-more / next-page control — more items "
            "exist beyond this batch and were NOT retrieved. The total is not advertised, so this is a "
            "partial sample of unknown size, not the complete listing."
        ),
        fix="Narrow the search query for a smaller, complete set, or open the URL in a browser tool to scroll / paginate.",
        severity="info",
    )


def archive_snapshot_age_hint(*, age_days: int, taken_at: date | None = None) -> OperatorHint:
    """The content came from a web-archive SNAPSHOT — dated, and aged.

    `archive.py` has computed the snapshot's age since the tier was written and
    NOTHING read it — the number reached `TierResult` and stopped there, so a
    2019 snapshot and a yesterday snapshot produced identical envelopes.

    Why that is an ADR-0009 failure rather than a missing nicety: the archive
    tier fires precisely when the live site walled us, so the caller asked about
    a page a2web could not reach and got an answer anyway. `tier: archive` is on
    the wire, but a tier name is not a date — and for the questions that drive
    people to a walled page (pricing, reviews, availability, "is this still
    true"), a stale answer is a WRONG answer wearing a confident face. The
    caller cannot audit what it is not told.

    **The DATE leads and the age follows**, because only one of them keeps. "847
    days old" is true at the moment of writing and decays from there — cached,
    logged, or pasted into a report it silently becomes wrong. "Captured
    2023-04-15" is true forever. The age is the readable gloss on the date, not
    the fact.

    Severity rises with age because the risk does. The thresholds are coarse on
    purpose — this is a "how much should you trust this" signal, not a
    measurement, and precision would imply a confidence a snapshot cannot carry.
    """
    when = f"captured {taken_at.isoformat()}, about {age_days} day(s) ago" if taken_at else f"about {age_days} day(s) old"
    if age_days >= _ARCHIVE_STALE_DAYS:
        severity = "warning"
        trust = "Treat time-sensitive details (prices, availability, ratings, staffing) as UNVERIFIED."
    else:
        severity = "info"
        trust = "Recent, but still a snapshot — re-check anything that changes by the day."
    return OperatorHint(
        code="archive_snapshot_age",
        message=(f"This content is a WEB ARCHIVE SNAPSHOT ({when}), not the live page — the live site did not serve us. {trust}"),
        fix="Open the URL in a real browser tool if you need the current page.",
        severity=severity,
    )


def extraction_empty_hint(*, content_chars: int) -> OperatorHint:
    """Dangerous silent-miss guard: content was fetched but extraction produced
    no answer (never-silently-miss / ADR-0009 at extraction granularity).

    Critical: `ask` fetched `content_chars` of real content yet the LLM
    extraction returned an empty answer — an extraction/parse failure or a model
    that did not follow the answer contract. The caller must NOT read an empty
    answer as "no data on the page"; the data is present but unextracted.
    """
    return OperatorHint(
        code="extraction_empty",
        message=(
            f"Fetched {content_chars} characters of content but extraction produced an EMPTY answer. "
            "This is an extraction/parse failure, not an empty page — do not conclude the page has no "
            "relevant data."
        ),
        fix="Retry the fetch, use `fetch_raw` to inspect the raw content, or rephrase the question.",
        severity="critical",
    )


def llm_error_hint(*, message: str, retryable: bool) -> OperatorHint:
    """The extraction LLM backend itself failed (auth, rate limit, overload,
    dead session) — distinct from a genuine empty answer.

    Sibling of `extraction_empty_hint`, and the reason it must exist: both
    produce `answer == ""` over real content, but the honest fix differs
    completely. `extraction_empty`'s advice — retry, or rephrase the question —
    is actively wrong for a broken backend, and sends the operator to inspect
    page content for what is a credentials or availability problem (ADR-0009
    honesty, applied to the diagnosis rather than the retrieval).
    """
    return OperatorHint(
        code="llm_error",
        message=(
            f"Content was fetched, but the extraction LLM backend failed, so no answer could be produced. "
            f"Provider error: {message}. This is NOT a claim about the page — the content is present and unextracted."
        ),
        fix=(
            "Check the LLM backend (API key, base URL, quota, and that the configured provider is reachable); "
            "`fetch_raw` returns the content meanwhile. "
            + (
                "The provider reported this as transient — retrying may succeed."
                if retryable
                else "Retrying will not help until the backend is fixed."
            )
        ),
        severity="critical",
    )


# --------------------------------------------------------------------------- #
# The remaining eleven codes.
#
# Every code in `HINT_CODES` now has exactly one factory, and every factory
# lives here. Before this, eleven codes were constructed inline at their single
# call site — in `fetcher.py`, `fetcher_response.py`, `tiers/browser.py` and
# `handlers/reddit.py` — so the catalogue a reader could see was the incomplete
# half, and the wording of a failure message depended on which module happened
# to build it.
#
# Every string below was MOVED VERBATIM from its call site, not rewritten. This
# is tuned ADR-0009 operator copy: it is what an agent is told when a fetch
# fails, and a reworded hint changes what that agent does next. The mechanical
# move and any wording change are deliberately not the same commit.
# --------------------------------------------------------------------------- #


def answer_truncated_hint() -> OperatorHint:
    """The extractor saw only part of an over-cap page.

    Travels as a hint rather than inside the debug-only `extraction` object
    because it is the ACTIONABLE half: a caller that cannot see `extraction`
    still needs to know the answer was formed over a partial read.
    """
    return OperatorHint(
        code="answer_truncated",
        message="The page was truncated before extraction; the answer may be incomplete.",
        fix="Re-run with a higher max_content_chars, or use fetch_raw to read the full page.",
    )


def content_guidance_hint(guidance: str) -> OperatorHint:
    """One line of "what matters for this page kind", for the caller's model.

    Keyed off the closed `structural_form` enum, never a site — the per-SITE
    version is banned by `tests/architecture/test_content_guidance_no_site.py`.
    Carries no `fix`: it is context, not a remediation, and the serializer drops
    an empty `fix` rather than emitting a dead `""`.
    """
    return OperatorHint(code="content_guidance", message=guidance)


def index_lost_hint() -> OperatorHint:
    """The body was withheld AND the index of it did not survive parsing.

    Deliberately `warning`, never `critical`: nothing here suggests the
    retrieval failed. The page was fetched, the answer is real, and a re-fetch
    would not repair a formatting artifact — status describes retrieval, hints
    describe extraction degradation. This is the ADR-0015 floor failing softly:
    the caller is blind to what was withheld, and is told so.
    """
    return OperatorHint(
        code="index_lost",
        message=(
            "The page body was withheld and the extractor's index of it did not survive "
            "parsing, so this answer may omit content the page carried without saying so. "
            "The answer itself is unaffected."
        ),
        fix="Call fetch_raw on this same URL to read the body — it is served from cache, so it costs no new fetch.",
        severity="warning",
    )


def retrieval_incomplete_hint() -> OperatorHint:
    """The extractor says this page does not carry what was asked for.

    `critical` because this is the ADR-0009 signal proper: the caller is holding
    an answer that may describe a different resource entirely, and the one thing
    they must not do is treat it as the requested content.
    """
    return OperatorHint(
        code="retrieval_incomplete",
        message=(
            "The extractor flagged this page as not carrying the requested content "
            "(likely a single-page-app shell, or a stale/unrelated page); the answer "
            "may not reflect the requested resource. Do not answer as if it does."
        ),
        fix="Verify against the live URL in a browser, or try fetch_raw / an alternate source.",
        severity="critical",
    )


def captcha_redirect_hint() -> OperatorHint:
    """A Google/Bing captcha page slipped past the upfront `rewrite_captcha_host`.

    The second half of a two-part policy whose halves cannot import each other
    (one is in `domain.py`, the marker is in `packages/block_detector`); they are
    held together only by `tests/capabilities/tier_pipeline/test_captcha_policy_halves.py`.
    """
    return OperatorHint(
        code="captcha_redirect",
        message="Search engine returned a captcha page; consider DDG/Brave directly.",
        fix="https://duckduckgo.com/html/?q=<your-query>",
    )


def served_url_differs_hint(*, requested_url: str, served_url: str) -> OperatorHint:
    """The served page landed on a different registrable domain than requested.

    Source: `docs/findings/2026-08-07-a2web-call-trace-audit.md` §4a — a
    hepsiburada product URL served sikayetvar.com content; a trendyol request
    served a hepsiburada title. `warning`, not `critical`: a cross-domain
    landing is sometimes the correct outcome (a shortlink, an intentional
    site-to-site redirect) and a2web cannot tell those apart from a mixup —
    only that the caller's identity assumption ("this is hepsiburada content")
    may not hold. The confidence cap this hint travels with (`build_response`)
    does the enforcement; this hint carries the evidence so the caller can
    judge whether the redirect was expected.
    """
    return OperatorHint(
        code="served_url_differs",
        message=(
            f"Requested {requested_url!r} but the content served came from a different "
            f"site ({served_url!r}). Confidence was capped because this may be a redirect "
            "swap or content mixup rather than the requested page."
        ),
        fix="Verify the served content is actually about the requested subject before answering from it.",
        severity="warning",
    )


def cookies_stale_hint(*, age: str, threshold_hours: int) -> OperatorHint:
    """The local cookie mirror is past its staleness threshold.

    Names both numbers rather than saying "stale": an operator deciding whether
    to spend a Keychain prompt needs the gap, not the verdict.
    """
    return OperatorHint(
        code="cookies_stale",
        message=(
            f"Browser cookies last refreshed {age} ago; threshold is {threshold_hours}h. Some sites may treat this session as logged-out."
        ),
        fix="Run `a2web cookies refresh`",
    )


def llm_unavailable_hint(*, reason: str, key_env: str) -> OperatorHint:
    """No extraction provider could be resolved.

    `critical` and never silent: under ADR-0016 the failure mode this guards
    against is a caller assuming the absent answer means the page was empty. The
    `fix` names the ACTUAL configured key env (`key_env`) rather than a hardcoded
    `ANTHROPIC_API_KEY`, because that name is a settings field and telling an
    operator to set a variable the code does not read is worse than silence.
    """
    return OperatorHint(
        code="llm_unavailable",
        message=reason,
        fix=(
            f"Set {key_env} (Anthropic) or OPENAI_API_KEY "
            "(+ OPENAI_BASE_URL / OPENAI_MODEL) in the environment, or run inside "
            "Claude Code. `fetch_raw` works without an LLM."
        ),
        severity="critical",
    )


#: Re-enable hint for an unavailable engine (missing extra / launch failure).
#: The published image has carried a baked Chromium since 0.46.0, so "build with
#: INSTALL_BROWSER=true" is no longer the container remedy — a container that
#: still reports this is either running a pre-0.46 image or failing to LAUNCH the
#: binary it already has. Name both, since the two need opposite actions.
#:
#: Moved here from `tiers/browser.py` with its two hints. Kept verbatim — it
#: names a concrete version boundary and an env override, and both are the kind
#: of detail that gets lost when a message is "tidied".
BROWSER_UNAVAILABLE_FIX = (
    "local: uv sync --extra browser && patchright install chromium. "
    "container: the published image bakes Chromium in from 0.46.0 — pull a current tag "
    "(pre-0.46 images have none). If already on 0.46+, the binary is present but failed to "
    "launch: check the `detail` for the resolved path and the binary's own output, and "
    "override with ANY_BROWSER_EXECUTABLE_PATH if it lives outside PLAYWRIGHT_BROWSERS_PATH."
)

#: Actionable next step for an internal driver/navigation failure. The driver
#: (Playwright/Firefox) is upstream — a2web cannot patch it — so the operator's
#: levers are retry or disabling the tier.
BROWSER_INTERNAL_FIX = (
    "transient browser-driver error — retry; if it persists the driver "
    "(Playwright/Firefox) is at fault, not the target. Set "
    "A2WEB_BROWSER_ENABLED=false to skip the browser tier."
)


def browser_unavailable_hint(message: str) -> OperatorHint:
    """The browser rung could not start at all (no binary, failed launch)."""
    return OperatorHint(code="browser_unavailable", message=message, fix=BROWSER_UNAVAILABLE_FIX)


def browser_internal_error_hint(detail: str | None) -> OperatorHint:
    """The browser started and the DRIVER failed — not the target site.

    The distinction is the whole point: attributing a driver crash to the page
    would send the caller chasing a wall that is not there.
    """
    return OperatorHint(
        code="browser_internal_error",
        message=detail or "browser internal error",
        fix=BROWSER_INTERNAL_FIX,
    )


def reddit_forbidden_hint(message: str) -> OperatorHint:
    """Reddit answered 403 on a shape that should have been public."""
    return OperatorHint(code="reddit_forbidden_try_archive", message=message)


def reddit_deleted_hint(message: str) -> OperatorHint:
    """The Reddit post is deleted/removed; the archive may still hold it."""
    return OperatorHint(code="reddit_deleted_try_archive", message=message)
