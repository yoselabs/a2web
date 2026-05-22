"""Deterministic data-contract conformance check for the output benchmark.

The data-contract axis is a programmatic (non-LLM) assertion that an a2web
wire envelope obeys its v0.14 field-presence rules:

  - `tier`, `url`, `status` are deviation-only — present ONLY when they
    differ from their boring default (`tier != raw`, `status != ok`,
    `url != requested_url`).
  - the `debug` object is present ONLY when the caller passed `debug=True`.
  - `next_links`, when present, is a well-shaped TSV block (a non-empty
    string — the serializer renders the list as tab-separated rows).

A violation is binary and exactly specified, so an LLM judge would only add
cost and nondeterminism. A contract regression fails the benchmark hard,
like a test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_TIER_DEFAULT = "raw"
_STATUS_DEFAULT = "ok"


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

    return ContractResult(conformant=not violations, violations=violations)


__all__ = ["ContractResult", "check_envelope_contract"]
