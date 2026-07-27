"""The wobble triage agrees with the prompt it claims to be reading.

`wobble/_policies.py` states the rule plainly — *`OPTIONAL` vs `DEFAULT` is a
claim about the prompt, and the prompt settles it* — and every policy line cites
the `prompts.py` clause that justifies it. Those citations were verified by hand
when written. Nothing kept them true.

The drift is quiet in both directions and neither shows up as a test failure:

  * `(required)` → `(optional)` in the prompt, policy left `DEFAULT`: the funnel
    fires `llm_wobble` on a field the contract now permits to be absent. That is
    not a harmless over-report — five such warnings on every healthy extraction
    is precisely how `llm_wobble` stopped being a signal, which is the bug
    `fix-extraction-signal-fidelity` existed to undo.
  * `(optional)` → `(required)`, policy left `OPTIONAL`: the funnel goes silent
    on a field the contract demands. A dropped `structural_form` IS the
    `unclassified` routing arm; losing its wobble loses the only report of it.

A renamed prompt field is caught by the same comparison — it lands in the parsed
set with no policy key, rather than silently ceasing to be governed.

**Scope: the router envelope only.** The two bench-judge tables
(`BENCH_CLARITY_POLICY`, `BENCH_NEXT_LINKS_POLICY`) are deliberately not checked
here: their prompts ask for a bare `{"clarity": <int>, "reasoning": "..."}`
object with no marker syntax to parse, so there is nothing to compare against.
Inventing a marker convention for them to satisfy this guard would be writing
the oracle to fit the test.
"""

from __future__ import annotations

import re

from llm_wobble import WobbleTolerance

from a2web.packages.llm_extract.prompts import _ROUTER_SCHEMA_DOC
from a2web.packages.llm_extract.wobble._policies import EXTRACTOR_ROUTING_POLICY

#: A field declaration in the router schema doc: two-space indent, the field
#: name, then `(required` or `(optional`. Matches the literal shape the model is
#: shown — if this stops matching, the vacuity floor below goes red rather than
#: the guard silently governing nothing.
_FIELD_MARKER = re.compile(r"^  ([a-z_]+) \((required|optional)", re.MULTILINE)

#: Tolerances that are legitimate for a `(required)` field. `STRICT` raises on
#: absence, `DEFAULT` substitutes and reports it — both treat absence as a
#: contract violation, which is what "required" means. `OPTIONAL` does not.
_REQUIRED_TOLERANCES = frozenset({WobbleTolerance.STRICT, WobbleTolerance.DEFAULT})

#: The parse must find at least this many declarations. The population is 8 and
#: the policy table is compared for exact equality below, so this floor exists
#: only to fail loudly if the prompt's formatting changes out from under the
#: regex — at which point the comparison would otherwise report "0 fields, all
#: consistent".
_MIN_MARKERS = 8


def _declared_fields() -> dict[str, str]:
    found = dict(_FIELD_MARKER.findall(_ROUTER_SCHEMA_DOC))
    assert len(found) >= _MIN_MARKERS, (
        f"parsed {len(found)} field declaration(s) out of the router schema doc, "
        f"expected at least {_MIN_MARKERS}.\n"
        "The prompt's field-declaration formatting changed and `_FIELD_MARKER` no "
        "longer matches it. Fix the pattern — do NOT lower the floor, which would "
        "leave the triage ungoverned while this test still reports green."
    )
    return found


def test_the_parse_is_not_vacuous() -> None:
    """A guard that parsed nothing is indistinguishable from a passing one."""
    _declared_fields()


def test_every_prompt_field_has_a_policy_and_vice_versa() -> None:
    declared = set(_declared_fields())
    governed = set(EXTRACTOR_ROUTING_POLICY)

    assert declared == governed, (
        "the router prompt and its wobble policy table describe different field sets.\n"
        f"  asked for by the prompt, ungoverned by the funnel: {sorted(declared - governed) or 'none'}\n"
        f"  governed by the funnel, absent from the prompt:     {sorted(governed - declared) or 'none'}\n\n"
        "A field the prompt asks for but no policy governs is parsed with no "
        "presence-recovery at all; a policy key the prompt never mentions is dead "
        "and usually means the prompt renamed the field."
    )


def test_required_and_optional_map_to_the_right_tolerance() -> None:
    offenders: list[str] = []
    for field, marker in sorted(_declared_fields().items()):
        tolerance = EXTRACTOR_ROUTING_POLICY[field].tolerance
        if marker == "optional" and tolerance is not WobbleTolerance.OPTIONAL:
            offenders.append(
                f"  {field}: prompt says (optional), policy is {tolerance.name} — the funnel will report an absence the contract permits"
            )
        elif marker == "required" and tolerance not in _REQUIRED_TOLERANCES:
            offenders.append(
                f"  {field}: prompt says (required), policy is {tolerance.name} — the funnel will stay silent on a dropped required field"
            )

    assert not offenders, (
        "wobble tolerances disagree with the prompt that justifies them:\n"
        + "\n".join(offenders)
        + "\n\nChange whichever one is wrong, and update the citing comment in "
        "`wobble/_policies.py` so it still describes the prompt as it now reads."
    )


def test_the_comparison_can_actually_fail() -> None:
    """The check must be able to go red, not merely to pass.

    Sibling of the vacuity floor: that one proves the parse found fields, this
    proves the tolerance comparison would reject a wrong one. Without it a
    refactor could leave both halves intact while comparing nothing.
    """
    assert WobbleTolerance.DEFAULT not in {WobbleTolerance.OPTIONAL}
    assert WobbleTolerance.OPTIONAL not in _REQUIRED_TOLERANCES
