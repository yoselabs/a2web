"""Token-cost measurement for the output benchmark.

The token-cost axis is the size of the **a2web response envelope** an agent
must read — not the tokens of any internal LLM call. A real BPE tokenizer is
not a project dependency, so token count is estimated from text length. The
estimate is deterministic and applied identically to every system, which is
what a comparative benchmark needs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

# Rough chars-per-token for mixed JSON + prose. cl100k averages ~4 chars per
# token on English prose; JSON punctuation pushes it slightly lower, but 4 is
# the standard cheap estimate and consistency across systems is what matters.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Deterministic token-count estimate for a string.

    Not a real tokenizer — `round(len(text) / 4)`, the standard cheap
    approximation. Used to size response envelopes for the benchmark's
    token-cost axis, where consistency across systems matters more than
    absolute accuracy.
    """
    if not text:
        return 0
    return max(1, round(len(text) / _CHARS_PER_TOKEN))


@dataclass(slots=True)
class EnvelopeTokens:
    """Token cost of one response envelope — total plus per-field breakdown."""

    total: int
    per_field: dict[str, int] = field(default_factory=dict)


def _value_tokens(value: object) -> int:
    if isinstance(value, str):
        return estimate_tokens(value)
    return estimate_tokens(json.dumps(value, default=str, ensure_ascii=False))


def envelope_token_breakdown(envelope: dict[str, object]) -> EnvelopeTokens:
    """Break an a2web wire envelope into per-field token costs.

    Top-level fields are reported individually; the nested `debug` object is
    reported both as a whole (`debug`) and per sub-field (`debug.<name>`).
    `total` is the token cost of the full serialized envelope.
    """
    per_field: dict[str, int] = {}
    for key, value in envelope.items():
        per_field[key] = _value_tokens(value)
        if key == "debug" and isinstance(value, dict):
            for sub_key, sub_value in value.items():
                per_field[f"debug.{sub_key}"] = _value_tokens(sub_value)
    total = estimate_tokens(json.dumps(envelope, default=str, ensure_ascii=False))
    return EnvelopeTokens(total=total, per_field=per_field)


__all__ = ["EnvelopeTokens", "envelope_token_breakdown", "estimate_tokens"]
