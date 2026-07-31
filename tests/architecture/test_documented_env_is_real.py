"""Configuration the README documents must actually work.

Two defects, found 2026-07-31, both of the same shape: prose that names an
environment variable or a value the code does not accept. Ordinary doc drift is
cosmetic; THIS kind is not, because the operator's only feedback is the
deployment behaving wrongly.

- `A2WEB_LLM_PROVIDER` was documented as `openai_compatible` / `anthropic` /
  `claude-code`. All three are pre-rename spellings that raise a pydantic
  `literal_error` at `AppSettings()` construction — a documented boot that
  cannot boot. Under ADR-0016 provider routing is where a wrong belief costs
  money.
- The Google OAuth variables were documented BARE (`GOOGLE_CLIENT_ID`) in a
  copy-pasteable `docker run` block, while `env_prefix="A2WEB_"` applies. An
  operator following it got an UNAUTHENTICATED endpoint with no error. The
  runtime half of that fix is `server._reject_unprefixed_auth_env`; this is the
  half that stops the prose from teaching it again.

Both are read out of README.md rather than restated here — a copy would drift
in exactly the way being guarded against.
"""

from __future__ import annotations

import re
from pathlib import Path

from anyllm import ProviderName

from a2web.server import _AUTH_ENV_FIELDS
from a2web.settings import AppSettings

_README = Path(__file__).resolve().parents[2] / "README.md"


def _readme() -> str:
    return _README.read_text(encoding="utf-8")


def test_documented_provider_ids_are_accepted_by_settings() -> None:
    """Every id offered for `A2WEB_LLM_PROVIDER` must construct.

    The row lists the accepted values inline; each backticked token that is not
    prose must be a real `ProviderName` (or `auto`). The retired spellings are
    named in the row too — as retired — so only the offer list is read.
    """
    row = next((line for line in _readme().splitlines() if line.startswith("| `A2WEB_LLM_PROVIDER`")), None)
    assert row is not None, "the A2WEB_LLM_PROVIDER row vanished — update this guard, do not delete it"

    offered = row.split("Pin the backend instead of auto-selecting:", 1)[1].split(".", 1)[0]
    ids = re.findall(r"`([a-z0-9_-]+)`", offered)
    assert len(ids) >= 3, f"non-vacuous: expected the offer list, parsed {ids}"

    valid = {p.value for p in ProviderName} | {"auto"}
    bad = [i for i in ids if i not in valid]
    assert not bad, f"README offers provider ids that AppSettings rejects: {bad} (valid: {sorted(valid)})"

    # The offer is not merely well-spelled — it boots.
    for provider_id in ids:
        AppSettings(llm_provider=provider_id)


def test_retired_provider_ids_really_are_rejected() -> None:
    """Anti-vacuity: the test above means nothing if everything is accepted."""
    import pytest
    from pydantic import ValidationError

    for retired in ("anthropic", "claude-code", "openai_compatible"):
        with pytest.raises(ValidationError):
            AppSettings(llm_provider=retired)


def test_readme_never_documents_a_bare_auth_env_var() -> None:
    """Auth vars must appear with the `A2WEB_` prefix that actually reads them.

    Checked against `server._AUTH_ENV_FIELDS` — the same tuple the runtime
    guard rejects on — so adding a field extends both at once.
    """
    text = _readme()
    assert len(_AUTH_ENV_FIELDS) >= 3, f"non-vacuous: expected auth fields, got {_AUTH_ENV_FIELDS}"

    bare = [name for name in _AUTH_ENV_FIELDS if re.search(r"(?<!A2WEB_)\b" + re.escape(name) + r"\b", text)]
    assert not bare, (
        f"README names auth env vars without the A2WEB_ prefix: {bare}. "
        "env_prefix='A2WEB_' means these are read by nothing — an operator "
        "following the docs gets an unauthenticated endpoint."
    )


def test_the_prefixed_spelling_is_what_the_readme_actually_carries() -> None:
    """Anti-vacuity for the check above: it passes trivially on a README that
    stopped mentioning auth at all."""
    text = _readme()
    present = [name for name in _AUTH_ENV_FIELDS if f"A2WEB_{name}" in text]
    assert len(present) >= 3, f"README no longer documents the auth vars ({present}) — the bare-var guard is now vacuous"
