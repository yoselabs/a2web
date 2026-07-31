"""Operator faults must reach the wire as their typed `a2effect` class.

`guard_tool` has two branches: `except AppError` (render the typed error) and
`except Exception` (quarantine into `UnexpectedDefect`). The first NEVER FIRED.
a2web imported `a2effect` in exactly one file and raised none of its five error
types, so every tool failure — a missing LLM credential, a null deref — rendered
identically as `UnexpectedDefect`. The taxonomy was a direct dependency that
described nothing.

Scope is deliberately narrow: only the errors that are ALREADY operator faults
today get typed. Everything else continues to quarantine, which is correct for
it — a bug should say it is a bug.
"""

from __future__ import annotations

import pytest
from a2effect import AppError, UnexpectedDefect
from a2effect.errors import AuthError, InfrastructureError

from a2web.error_wire import format_error_prose, guard_tool
from a2web.packages.llm_extract import LLMNotAvailable
from a2web.state import ResourceUnavailable


def test_llm_not_available_is_an_auth_error() -> None:
    """Both documented causes are credential problems, so `AuthError` is the fit.

    `LLMNotAvailable` fires when there is no `ANTHROPIC_API_KEY` and no Claude
    Code OAuth session, or when the selected provider's credentials are invalid
    or expired. Not `InfrastructureError` — that class is defined as retryable,
    and retrying a missing credential never helps.
    """
    exc = LLMNotAvailable("no provider available")
    assert isinstance(exc, AppError), "an operator fault must be typed, not bare RuntimeError"
    assert isinstance(exc, AuthError)


def test_resource_unavailable_is_an_infrastructure_error() -> None:
    """A declared resource that could not be entered is an infra failure.

    Distinct from the auth case: nothing is wrong with a credential, a
    dependency the caller declined to provision (or that failed to start) is
    simply not there.
    """
    exc = ResourceUnavailable("browser pool not provisioned")
    assert isinstance(exc, AppError)
    assert isinstance(exc, InfrastructureError)
    assert exc.reason == "browser pool not provisioned", "the operator-hint payload must survive retyping"


def test_both_stay_catchable_as_runtime_error() -> None:
    """Retyping must not break the existing `except` sites.

    Both classes were `RuntimeError` subclasses and are caught as such across
    the pipeline (`_phase_cookies_staleness` catches `ResourceUnavailable`
    directly, but broader handlers exist). Losing that would turn a handled
    degradation into a crash — a silent scope change riding along with a
    cosmetic retype.
    """
    for exc in (LLMNotAvailable("x"), ResourceUnavailable("y")):
        try:
            raise exc
        except RuntimeError:
            pass


@pytest.mark.asyncio
async def test_guard_tool_renders_an_operator_fault_as_itself_not_a_bug() -> None:
    """THE regression this exists to prevent, driven through the real guard.

    Without a typed raise anywhere, `except AppError` is unreachable and this
    prose reads `UnexpectedDefect` — a missing credential and a null deref
    become indistinguishable to whoever is on the other end.
    """

    @guard_tool
    async def _tool() -> None:
        raise LLMNotAvailable("no ANTHROPIC_API_KEY and no Claude Code session")

    with pytest.raises(Exception) as caught:
        await _tool()

    cause = caught.value.__cause__
    assert isinstance(cause, AuthError), f"reached the wire as {type(cause).__name__}"
    assert not isinstance(cause, UnexpectedDefect), "an operator fault must not render as a bug — that is the whole point of the taxonomy"

    prose = format_error_prose(cause)
    assert "LLMNotAvailable" in prose
    assert "UnexpectedDefect" not in prose


@pytest.mark.asyncio
async def test_a_genuine_bug_still_quarantines() -> None:
    """Anti-vacuity: typing the operator faults must not type EVERYTHING.

    If the `except Exception` branch stopped quarantining, the test above would
    still pass while the distinction it asserts had collapsed the other way.
    """

    @guard_tool
    async def _tool() -> None:
        raise AttributeError("'NoneType' object has no attribute 'x'")

    with pytest.raises(Exception) as caught:
        await _tool()

    assert isinstance(caught.value.__cause__, UnexpectedDefect)
