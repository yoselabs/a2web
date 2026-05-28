"""Spike v6 — benchmark field-name candidates against an LLM consumer.

The affordances field is consumed by AI agents over MCP, not by humans. So
the right "vote" on what to call it comes from how reliably AI agents
interpret the name and use the field correctly.

Tested candidates:
  - `affordances` — original. Precise HCI term but jargon.
  - `signals`     — broad, intuitive, no jargon.
  - `leads`       — investigative ("leads for further investigation").
  - `hints`       — humble, action-oriented ("hints for what to ask next").

Two probes per name:

  Probe A — COLD READING:
    Given JUST the field name, ask the model what it would EXPECT inside.
    Measure semantic overlap with the actual fields we plan to put there:
    {page_kind, page_kind_confidence, content_value, shapes,
     follow_up_questions}.
    Score: how many of the 5 fields does the model anticipate?

  Probe B — BEHAVIORAL:
    Show the model a realistic AskResponse with the field populated. Ask:
    "Given this response, what would you do next?" The good answer should
    reference the follow-up questions, content_value, or page_kind to
    make a downstream decision. Bad answer: ignores the field entirely.
    Score: does the model's planned action grounded in the field's contents?

  Each probe × each name × 3 runs = consistency check.

Run:
    uv run python eval/spikes/affordances_v6_name_bench.py
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider


NAMES = ["affordances", "signals", "leads", "hints"]
RUNS_PER_PROBE = 3

# What we plan to put under the field — what a perfect cold-reading should anticipate.
EXPECTED_FIELDS = {"page_kind", "page_kind_confidence", "content_value", "shapes", "follow_up_questions"}


COLD_SYSTEM = (
    "You are evaluating an API design. Given a field name in a JSON response, "
    "you propose what fields you would expect to find INSIDE that field. "
    "Be specific. Output strict JSON only."
)

COLD_TEMPLATE = """An MCP web-fetching tool returns this kind of response:

{{
  "extracted_answer": "<2-3 sentence answer to the user's question>",
  "{name}": {{ ... }}
}}

Given the field name `{name}`, what fields would you expect INSIDE that
nested object? List 5-8 specific sub-field names (snake_case) you would
anticipate, ordered by how natural they feel given the name.

Respond with strict JSON:
{{
  "name_interpretation": "<one short sentence: what does the name `{name}` suggest the field contains?>",
  "expected_subfields": ["<subfield_1>", "<subfield_2>", ...]
}}
"""


# A realistic AskResponse for the behavioral probe. Wikipedia Rust page —
# high-quality extraction with several follow-up directions.
SAMPLE_PAYLOAD_TEMPLATE = """{{
  "extracted_answer": "This is the Wikipedia article on Rust, a programming language emphasizing performance, type safety, and memory safety without garbage collection. It covers Rust's history (created 2006 by Graydon Hoare, first stable release 2015), governance (Rust Foundation formed 2021), and adoption by major companies.",
  "{name}": {{
    "page_kind": "encyclopedia",
    "page_kind_confidence": "high",
    "content_value": "high",
    "reasoning": "Substantial Wikipedia article with comprehensive sections, citations, code examples, and historical timeline.",
    "shapes": [
      {{"label": "timeline", "where": "History section", "size": "medium"}},
      {{"label": "code", "where": "Syntax section", "size": "large"}},
      {{"label": "citations", "where": "throughout", "size": "large"}}
    ],
    "follow_up_questions": [
      "How does Rust's borrow checker prevent memory safety errors without garbage collection?",
      "What companies have adopted Rust for production use cases?",
      "What was the significance of the Rust Foundation's formation in 2021?"
    ]
  }}
}}"""

BEHAVIORAL_SYSTEM = (
    "You are an AI agent that just called a web-fetching tool to answer a "
    "user's question. You are deciding what to do next based on the tool's "
    "response. Output strict JSON only."
)

BEHAVIORAL_TEMPLATE = """The user asked: "Give me a 2-3 sentence summary of what this page is" about https://en.wikipedia.org/wiki/Rust_(programming_language)

The tool returned:

{payload}

The user just received your answer (the `extracted_answer` field). The user has
NOT asked any follow-up question yet, but they likely will. What would you do
next?

Respond with strict JSON:
{{
  "planned_next_action": "<one of: present-answer-and-wait | proactively-fetch-related | offer-follow-up-suggestions | escalate-to-browser-tier | other>",
  "reasoning": "<2-3 sentences on what informed your decision>",
  "field_references_used": ["<which sub-field names from the `{name}` object did you reference in your reasoning? list the exact subfield names>"]
}}
"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        body = text[3:]
        if body.startswith("json"):
            body = body[4:]
        if "```" in body:
            body = body.split("```", 1)[0]
        text = body.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc), "_raw": text[:400]}


async def _one_call(provider: ClaudeCodeProvider, system: str, user: str) -> dict:
    t0 = time.perf_counter()
    response = await provider.complete(
        system=system,
        user=user,
        model="claude-haiku-4-5",
        max_tokens=512,
        thinking_disabled=True,
    )
    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "elapsed_ms": elapsed,
        "cost": response.cost_usd,
        "parsed": _parse_json(response.text),
    }


def _cold_score(parsed: dict) -> dict:
    """Count overlap between expected and predicted subfields."""
    predicted = {s.lower().replace("-", "_") for s in parsed.get("expected_subfields", []) if isinstance(s, str)}
    # Soft-match: a predicted field counts if it shares a substring with an expected one
    matched = set()
    for exp in EXPECTED_FIELDS:
        exp_token = exp.split("_")[-1]
        for pred in predicted:
            if exp in pred or pred in exp or exp_token in pred:
                matched.add(exp)
                break
    return {
        "predicted_n": len(predicted),
        "expected_matched_n": len(matched),
        "expected_matched": sorted(matched),
        "interpretation": parsed.get("name_interpretation", ""),
    }


def _behavioral_score(parsed: dict) -> dict:
    """Score whether the model referenced the field in its reasoning."""
    refs = parsed.get("field_references_used", [])
    if not isinstance(refs, list):
        refs = []
    refs_set = {r.lower().replace("-", "_") for r in refs if isinstance(r, str)}
    grounded = len(refs_set & EXPECTED_FIELDS)
    return {
        "planned_action": parsed.get("planned_next_action", ""),
        "field_refs_used": sorted(refs_set),
        "grounded_n": grounded,
        "reasoning": parsed.get("reasoning", "")[:200],
    }


async def main() -> None:
    provider = ClaudeCodeProvider()
    results: dict[str, Any] = {"per_name": {}}
    total_cost = 0.0

    for name in NAMES:
        print(f"\n=== Benchmarking name: `{name}` ===", flush=True)
        per_name: dict[str, Any] = {"cold": [], "behavioral": []}

        # Cold reading × N
        print(f"  Cold reading ({RUNS_PER_PROBE}x)...", flush=True)
        for i in range(RUNS_PER_PROBE):
            r = await _one_call(provider, COLD_SYSTEM, COLD_TEMPLATE.format(name=name))
            total_cost += r["cost"]
            score = _cold_score(r["parsed"])
            per_name["cold"].append({"run": i + 1, **score, "raw": r["parsed"]})
            print(f"    run {i + 1}: matched {score['expected_matched_n']}/5 — {score['expected_matched']}")

        # Behavioral × N
        print(f"  Behavioral ({RUNS_PER_PROBE}x)...", flush=True)
        payload = SAMPLE_PAYLOAD_TEMPLATE.format(name=name)
        for i in range(RUNS_PER_PROBE):
            r = await _one_call(
                provider,
                BEHAVIORAL_SYSTEM,
                BEHAVIORAL_TEMPLATE.format(payload=payload, name=name),
            )
            total_cost += r["cost"]
            score = _behavioral_score(r["parsed"])
            per_name["behavioral"].append({"run": i + 1, **score, "raw": r["parsed"]})
            print(f"    run {i + 1}: action={score['planned_action']} grounded={score['grounded_n']}/5 refs={score['field_refs_used']}")

        # Aggregate scores
        cold_avg_match = sum(c["expected_matched_n"] for c in per_name["cold"]) / RUNS_PER_PROBE
        behav_avg_grounded = sum(b["grounded_n"] for b in per_name["behavioral"]) / RUNS_PER_PROBE
        per_name["aggregate"] = {
            "cold_avg_match": round(cold_avg_match, 2),
            "behavioral_avg_grounded": round(behav_avg_grounded, 2),
            "combined": round((cold_avg_match + behav_avg_grounded) / 2, 2),
        }
        results["per_name"][name] = per_name

    results["total_cost_usd"] = round(total_cost, 4)

    # Final table
    print("\n\n=== FINAL SCOREBOARD ===\n")
    print(f"{'name':<14} {'cold_match/5':>13} {'behav_grounded/5':>17} {'combined':>10}")
    print("-" * 60)
    ranked = sorted(NAMES, key=lambda n: -results["per_name"][n]["aggregate"]["combined"])
    for name in ranked:
        a = results["per_name"][name]["aggregate"]
        print(f"{name:<14} {a['cold_avg_match']:>13} {a['behavioral_avg_grounded']:>17} {a['combined']:>10}")

    out_path = Path("eval/spikes/affordances_v6_name_bench.json")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"\nWinner: `{ranked[0]}`")


if __name__ == "__main__":
    asyncio.run(main())
