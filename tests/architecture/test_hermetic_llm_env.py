"""The suite may not read whether THIS machine has an LLM.

Three releases died on the same defect. 0.47.0 and 0.47.1 failed CI on
provider-selection tests; 0.48.0 failed on the CLI-contract goldens, where the
`Extractor.extract` stub is only reached once `select_provider` returned a
provider — so under `auto` with no credentials every `web query` golden silently
degraded to an `llm_unavailable` payload. Each time the test was green on a
laptop with a Claude Code session and red on a bare runner, with **no code
difference between the two runs**.

Each was fixed one test at a time, and none of the fixes made the next
occurrence impossible. `tests/conftest.py::_hermetic_llm_env` is the mechanism
that does; this file is what stops the mechanism from being quietly removed,
narrowed, or made opt-in.

**What this guard establishes, stated narrowly so it is not over-read:** that
the fixture exists, is autouse, and covers the named variable set. It does NOT
establish that no test reaches the host by an unanticipated route — a new
provider adapter with its own probe, or a library reading a config file outside
the environment, would both pass straight through. The CI runner remains the
exogenous witness. This makes the local run agree with it more often; it does
not make it redundant.

**On this guard's own non-vacuity, honestly.** The behavioural assertion below
("the scrubbed names are absent") is a real witness on a keyed developer
machine, where those variables genuinely are set in the ambient environment and
the fixture genuinely removes them. On a bare CI runner they were absent to
begin with, so there the assertion is satisfied trivially and proves nothing.
That asymmetry is inherent — the defect only exists on machines that have
credentials — and it is why the AST half is here as well: the structural
assertions hold identically in both environments.
"""

from __future__ import annotations

import ast
import os

import pytest

from ._walk import REPO_ROOT

_CONFTEST = REPO_ROOT / "tests" / "conftest.py"

#: The variables the `test-env-hermeticity` capability names. Kept here, in the
#: guard, rather than imported from the fixture's own tuple — importing it would
#: make the guard agree with whatever the fixture currently says, which is the
#: endogenous-oracle failure this repo has been bitten by twice. The two lists
#: are supposed to be written down independently and compared.
_REQUIRED = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "A2WEB_LLM_PROVIDER",
        "CLAUDE_CODE_OAUTH_TOKEN",
    }
)

_FIXTURE = "_hermetic_llm_env"


def _conftest_tree() -> ast.Module:
    return ast.parse(_CONFTEST.read_text(encoding="utf-8"))


def _find_fixture() -> ast.FunctionDef:
    for node in ast.walk(_conftest_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == _FIXTURE:
            return node
    pytest.fail(
        f"tests/conftest.py no longer defines `{_FIXTURE}`. Three releases failed "
        "CI because the suite read the developer's machine; that fixture is what "
        "stops it. If it was renamed, update this guard — do not delete it."
    )


def test_the_walk_found_its_subject() -> None:
    """Non-vacuity floor: a guard that located nothing cannot object to anything.

    Without this, a renamed conftest or a parse failure would make every
    assertion below vacuously true and the file would report green over nothing.
    """
    assert _CONFTEST.exists(), "tests/conftest.py does not exist — this guard is checking nothing"
    functions = [n for n in ast.walk(_conftest_tree()) if isinstance(n, ast.FunctionDef)]
    assert len(functions) >= 5, f"parsed only {len(functions)} function(s) from conftest — the walk is not reading it"
    assert _find_fixture() is not None


def test_the_fixture_is_autouse() -> None:
    """Opt-in would defend only the authors who already know the defect exists.

    Asserted structurally rather than behaviourally because a fixture demoted to
    opt-in still passes every behavioural check in a run where nothing requested
    it — the tests would simply stop being protected, silently.
    """
    fixture = _find_fixture()
    autouse = [
        kw
        for deco in fixture.decorator_list
        if isinstance(deco, ast.Call)
        for kw in deco.keywords
        if kw.arg == "autouse"
    ]
    assert autouse, f"`{_FIXTURE}` is no longer declared `autouse=True`"
    assert all(isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in autouse), (
        f"`{_FIXTURE}` declares autouse with a non-True value — it protects nothing"
    )


def test_every_required_variable_is_covered() -> None:
    """Names the specific variable that stopped being scrubbed, not just 'a gap'."""
    scrubbed = {
        elt.value
        for node in ast.walk(_conftest_tree())
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_SCRUBBED_LLM_ENV" for t in node.targets)
        and isinstance(node.value, ast.Tuple)
        for elt in node.value.elts
        if isinstance(elt, ast.Constant)
    }
    assert scrubbed, "`_SCRUBBED_LLM_ENV` is missing or is no longer a literal tuple of names"

    uncovered = sorted(_REQUIRED - scrubbed)
    assert not uncovered, (
        "the hermetic-env fixture stopped scrubbing:\n"
        + "".join(f"  {name}\n" for name in uncovered)
        + "\nEach of these can make a test's result depend on the machine it ran "
        "on. Restore it, or — if it is genuinely obsolete — remove it from "
        "`_REQUIRED` here in the same commit, with the reason."
    )


def test_the_scrub_is_actually_in_effect() -> None:
    """The behavioural half: inside a test, none of the names are readable.

    Trivially satisfied on a bare runner (see the module docstring); a genuine
    True → False witness on a keyed developer machine, which is the environment
    where the defect lives.
    """
    leaked = sorted(name for name in _REQUIRED if name in os.environ)
    assert not leaked, f"visible to tests despite the scrub: {leaked}"


def test_the_subscription_backends_report_unavailable() -> None:
    """The half no environment variable covers.

    The Claude Code session backends probe the host directly — a running session
    is discoverable without any credential env var set, which is exactly how
    0.48.0's goldens passed locally and failed in CI.
    """
    from anyllm.providers.claude_code_cli import ClaudeCodeCliAdapter
    from anyllm.providers.claude_code_sdk import ClaudeCodeSdkAdapter

    assert ClaudeCodeSdkAdapter().available() is False
    assert ClaudeCodeCliAdapter().available() is False


@pytest.mark.ambient_llm
def test_the_escape_hatch_actually_escapes() -> None:
    """The `ambient_llm` marker, exercised rather than merely registered.

    An escape hatch nobody runs rots into one that no longer works — and this
    one is only correct while the fixture it opts out of still checks the
    marker. Deliberately asserts the WEAK thing (that the patch is not applied),
    not that a provider is available: whether this machine has one is exactly
    the host-dependence the rest of this file forbids, and asserting it here
    would make the suite host-dependent to prove it is not.
    """
    from anyllm.providers.claude_code_sdk import ClaudeCodeSdkAdapter

    assert ClaudeCodeSdkAdapter.available is not None
    assert "lambda" not in getattr(ClaudeCodeSdkAdapter.available, "__qualname__", ""), (
        "the scrub patch is still applied inside an `ambient_llm` test — the "
        "marker no longer opts out, so every test that uses it is silently "
        "asserting against a stubbed host"
    )
