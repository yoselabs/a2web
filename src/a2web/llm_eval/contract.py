"""Deterministic data-contract conformance check for the output benchmark.

The data-contract axis is a programmatic (non-LLM) assertion that an a2web
wire envelope obeys two families of rule.

**Field-presence (v0.14 serialization discipline):**

  - `tier`, `url`, `status` are deviation-only — present ONLY when they
    differ from their boring default (`tier != raw`, `status != ok`,
    `url != requested_url`).
  - the `debug` object is present ONLY when the caller passed `debug=True`.
  - `next_links`, when present, is a well-shaped TSV block (a non-empty
    string — the serializer renders the list as tab-separated rows).

**Incompleteness coherence (ADR-0009), added 2026-08-03.** Until then this
module checked serialization discipline and *nothing about the cardinal
product invariant*. That gap has a specific shape: a2web's most-repeated rule
is "never tolerate ANY unfetched URL — a walled fetch MUST carry `status:
failed` + `retrieval_incomplete: true` + `narrative` + an operator hint", and
the bench's only always-on envelope check could not tell that envelope from
one claiming incompleteness in total silence.

The distinction that makes this belong HERE rather than in a per-case
`contract:` block is machine-independence. Whether a given URL is reachable
from a given host depends on proxies, paid-tier keys and jina reachability —
so `status: failed` is a per-case, per-host claim and pinning it wholesale
would bake one machine's provisioning into the gate (see `BACKLOG.md`,
2026-08-03, on the eleven adversarial slugs). But *coherence* is a property of
the envelope with itself, true in BOTH branches on EVERY machine: retrieve the
page and there is no incompleteness to declare; fail to, and the declaration
must be loud. The eleven slugs get a real deterministic assertion out of this
without anyone having to decide whether their wall belongs to the site or to
the host.

Note the asymmetry, which is deliberate: incompleteness implies a failed
status, but a failed status does NOT imply incompleteness. A corroborated
`404` is `gone_confirmed` — a fetch that succeeded in learning the page is
dead, not an unfetched URL. Asserting the converse would fail every
honest-404 case in the corpus.

A violation is binary and exactly specified, so an LLM judge would only add
cost and nondeterminism. A contract regression fails the benchmark hard,
like a test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_TIER_DEFAULT = "raw"
_STATUS_DEFAULT = "ok"

#: The one non-default status ADR-0009 permits alongside an unretrieved URL.
_STATUS_FAILED = "failed"


@dataclass(slots=True)
class ContractResult:
    """Outcome of one envelope contract check."""

    conformant: bool
    violations: list[str] = field(default_factory=list)


def check_envelope_contract(
    envelope: dict[str, object],
    *,
    requested_url: str,
    debug: bool,
) -> ContractResult:
    """Assert an a2web wire envelope obeys its field-presence rules.

    `requested_url` is the URL the fetch was asked for — needed to verify the
    deviation rule for `url`. `debug` is whether the fetch was invoked with
    `debug=True` — needed to verify the `debug`-object gating.
    """
    violations: list[str] = []

    if envelope.get("status") == _STATUS_DEFAULT:
        violations.append("`status` present at its default 'ok' — must be omitted when ok")
    if envelope.get("tier") == _TIER_DEFAULT:
        violations.append("`tier` present at its default 'raw' — must be omitted when raw")
    if "url" in envelope and envelope["url"] == requested_url:
        violations.append("`url` present but equal to the requested URL — must be omitted when it matches")

    if "debug" in envelope and not debug:
        violations.append("`debug` object present without debug=True")

    if "next_links" in envelope:
        next_links = envelope["next_links"]
        if not isinstance(next_links, str) or not next_links.strip():
            violations.append("`next_links` present but not a non-empty TSV block")

    violations.extend(_check_incompleteness_coherence(envelope))

    return ContractResult(conformant=not violations, violations=violations)


def _check_incompleteness_coherence(envelope: dict[str, object]) -> list[str]:
    """ADR-0009: an envelope that admits incompleteness must be loud about it.

    Reads the wire, not the model, so every rule accounts for the omit-empty
    serializer: `retrieval_incomplete` is dropped when `False`, `status` is
    dropped when `ok`, `narrative` is failure-only. Absence is therefore
    meaningful and is what each check keys on.

    All three consequents are the invariant's own words. The `narrative` and
    hint clauses are the ones that matter most in practice: a `status: failed`
    with neither is exactly a miss wearing the shape of an answer, and it is
    machine-readable *and* prose-readable that something went wrong only if
    both channels say so.
    """
    if not envelope.get("retrieval_incomplete"):
        return []

    out: list[str] = []
    status = envelope.get("status")
    if status != _STATUS_FAILED:
        seen = "omitted (i.e. ok)" if status is None else repr(status)
        out.append(
            f"`retrieval_incomplete` is true but `status` is {seen} — ADR-0009: a URL "
            "that was not retrieved may never be reported as a complete answer"
        )

    if not str(envelope.get("narrative") or "").strip():
        out.append(
            "`retrieval_incomplete` is true but `narrative` is empty — ADR-0009: the "
            "caller must be told what went wrong in prose, not only by a flag"
        )

    hints = envelope.get("operator_hints")
    if not isinstance(hints, (list, tuple)) or not hints:
        out.append(
            "`retrieval_incomplete` is true but no operator hint fired — ADR-0009: an "
            "unfetched URL is an unfinished job and must carry the recovery signal "
            "(`try_user_browser`, or `paid_auth_error` when a keyed tier's key is bad)"
        )

    return out


__all__ = ["ContractResult", "check_envelope_contract"]
