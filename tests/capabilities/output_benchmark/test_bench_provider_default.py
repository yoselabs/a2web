"""The Makefile's bench provider default must be a real `anyllm.ProviderName`.

Why this test exists: `ee2452c` (adopt `anyllm.ProviderName` + `resolve_provider`)
renamed the provider ids and updated the *tests* but not the Makefile default, so
`A2WEB_BENCH_PROVIDER ?= claude-code` silently stopped resolving. `make bench`
then failed for everyone with `unknown provider id: claude-code`.

The ADR-0016 cost floor itself held — an unresolvable id fails LOUD rather than
silently falling through to metered billing, so there was never a spend risk. The
damage was that the DEFAULT became inoperative: every bench run needed a
hand-supplied provider, and the natural guess for someone unaware of the rename is
the metered `anthropic-api` — precisely what the default exists to prevent.

Pinning the value here means the next rename fails CI instead of the next bench
run. Parsed out of the Makefile rather than duplicated, so the assertion cannot
drift from the thing it guards.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from anyllm import ProviderName

_MAKEFILE = Path(__file__).resolve().parents[3] / "Makefile"
_ASSIGNMENT = re.compile(r"^A2WEB_BENCH_PROVIDER\s*\?=\s*(?P<value>\S+)\s*$", re.MULTILINE)


def _declared_default() -> str:
    text = _MAKEFILE.read_text()
    match = _ASSIGNMENT.search(text)
    # Non-vacuity: a renamed variable or changed assignment operator would make
    # the regex miss and every assertion below pass over nothing.
    assert match is not None, f"no `A2WEB_BENCH_PROVIDER ?=` assignment found in {_MAKEFILE}"
    return match.group("value")


def test_makefile_bench_provider_default_is_a_real_provider_id() -> None:
    """The default resolves against the live enum — not a stale string."""
    value = _declared_default()
    valid = {p.value for p in ProviderName}
    assert value in valid, (
        f"Makefile default A2WEB_BENCH_PROVIDER={value!r} is not an `anyllm.ProviderName`. "
        f"Valid ids: {sorted(valid)}. A rename that misses this line breaks `make bench` for "
        f"everyone and leaves the ADR-0016 cost-floor default inoperative."
    )


def test_makefile_bench_provider_default_is_not_metered() -> None:
    """ADR-0016: the DEFAULT must be a subscription path, never metered.

    The whole point of the default is that an accidental `make bench` cannot bill
    the metered API. Opting in stays possible via the environment (`?=`), but it
    must be a deliberate act.
    """
    value = _declared_default()
    assert value.startswith("claude-code"), (
        f"Makefile default A2WEB_BENCH_PROVIDER={value!r} is not a subscription provider. "
        "ADR-0016 requires the default to be a flat-rate Claude Code path; metered providers "
        "are explicit-opt-in only."
    )


@pytest.mark.parametrize("stale", ["claude-code", "anthropic", "openai_compatible"])
def test_known_stale_ids_are_rejected(stale: str) -> None:
    """The ids that USED to work must not silently resolve again.

    Guards the regression directly: `claude-code` is the value that shipped
    broken; `anthropic` and `openai_compatible` are the pre-rename spellings that
    still appear in prose and would be plausible hand-typed guesses.
    """
    assert stale not in {p.value for p in ProviderName}, (
        f"{stale!r} resolves again — if the enum re-adds it, revisit the Makefile comment "
        "and this test together."
    )
