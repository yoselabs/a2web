"""Phase 3: reader + judge pipeline (a2web.llm edition).

Migrated from `claude -p` subprocess calls to `a2web.llm` primitives:
  - reader step  → `Extractor` over the WebFetch byte-identical template
  - judge step   → `Judge` (returns parsed `JudgeVerdict`, no ad-hoc regex)
  - provider     → `AnthropicProvider` (single SDK client, in-process)

Behavior preserved:
  - WebFetch answers passed through as-is (already extracted server-side).
  - a2web variants A/B/C run through the reader to produce an answer.
  - Each of the 4 answers blind-judged against per-question criteria.
  - Output filenames unchanged so existing analysis scripts still work.

Requires `ANTHROPIC_API_KEY` in env and `a2web[llm]` installed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from a2web.packages.llm_extract import (
    Extractor,
    Judge,
    JudgeParseError,
    ModelSpec,
    PromptTemplate,
)
from a2web.packages.llm_extract import LLMNotAvailable
from a2web.packages.llm_extract.providers.anthropic import AnthropicProvider
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider

HERE = Path(__file__).parent
RUNS = HERE / "runs"
CORPUS = HERE / "corpus.yaml"

READER_MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-sonnet-4-6"

# Reader prompt: same shape as the original CLI version, but driven through
# the Extractor's 2-slot template (content / ask).
READER_TEMPLATE = PromptTemplate(
    name="benchmark_reader_v1",
    version=1,
    system=(
        "You are a downstream agent that received a web-fetch response from a tool. "
        "Read the response and answer the user's question concisely. "
        "If the response does not contain the information needed (e.g. block page, "
        "404, login wall, or otherwise lacks substantive content), say so explicitly "
        "and describe what kind of response you received. Do not invent content.",
    ),
    user_template=(
        "=== FETCH RESPONSE (JSON) ===\n{content}\n=== END ===\n\n"
        "QUESTION: {ask}\n\n"
        "Your answer:"
    ),
)


async def _read_answer(extractor: Extractor, payload_json: str, task: str) -> str:
    result = await extractor.extract(content=payload_json, ask=task)
    return result.answer


async def _process_one(
    entry: dict[str, Any],
    reader: Extractor,
    judge: Judge,
) -> dict[str, Any]:
    slug = entry["slug"]
    task = entry["task"]
    criteria = entry["criteria"]
    run_dir = RUNS / slug
    if not run_dir.exists():
        return {"slug": slug, "error": "missing run dir"}

    result: dict[str, Any] = {
        "slug": slug,
        "class": entry["class"],
        "task": task,
        "scores": {},
    }

    # System 1: WebFetch — already an answer; pass-through.
    wf_text = (run_dir / "webfetch.txt").read_text()
    (run_dir / "answer_webfetch.txt").write_text(wf_text)

    # Systems 2-4: a2web payloads → reader produces an answer.
    a2web_variants = {
        "a2web_A": "a2web_A_full.json",
        "a2web_B": "a2web_B_meta.json",
        "a2web_C": "a2web_C_content_only.json",
    }
    for sys_name, fname in a2web_variants.items():
        payload_path = run_dir / fname
        if not payload_path.exists():
            (run_dir / f"answer_{sys_name}.txt").write_text("[a2web fetch failed; no payload]")
            continue
        payload = payload_path.read_text()
        if len(payload) > 200_000:
            payload = payload[:200_000] + "\n[TRUNCATED]"
        ans = await _read_answer(reader, payload, task)
        (run_dir / f"answer_{sys_name}.txt").write_text(ans)

    # Judge all 4 answers.
    for sys_name in ("webfetch", "a2web_A", "a2web_B", "a2web_C"):
        ans_path = run_dir / f"answer_{sys_name}.txt"
        if not ans_path.exists():
            result["scores"][sys_name] = {"error": "no answer"}
            continue
        ans = ans_path.read_text()
        try:
            verdict = await judge.score(task=task, criteria=criteria, answer=ans)
            verdict_dict = asdict(verdict)
            (run_dir / f"score_{sys_name}.json").write_text(
                json.dumps(verdict_dict, indent=2, ensure_ascii=False)
            )
            result["scores"][sys_name] = verdict_dict
        except JudgeParseError as exc:
            err = {"error": str(exc), "raw": exc.raw_text[:500]}
            (run_dir / f"score_{sys_name}.json").write_text(json.dumps(err, indent=2))
            result["scores"][sys_name] = err

    print(f"  [{slug}] done")
    return result


def _pick_provider() -> tuple[Any, str]:
    """Prefer Claude Code's OS session (OAuth subscription) over API key.

    Falls back to AnthropicProvider only if claude-agent-sdk / CLI is
    unavailable. Caller controls via `A2WEB_BENCH_PROVIDER=anthropic`.
    """
    import os

    forced_name = os.environ.get("A2WEB_BENCH_PROVIDER", "").strip().lower()
    if forced_name == "anthropic":
        return AnthropicProvider(), "anthropic"
    if forced_name == "claude-code":
        return ClaudeCodeProvider(), "claude-code"
    try:
        return ClaudeCodeProvider(), "claude-code"
    except LLMNotAvailable as exc:
        print(f"  [info] claude-code provider unavailable ({exc}); falling back to AnthropicProvider")
        return AnthropicProvider(), "anthropic"


async def _amain() -> int:
    corpus = yaml.safe_load(CORPUS.read_text())
    provider, provider_id = _pick_provider()
    print(f"  [info] provider={provider_id}")
    reader = Extractor(
        provider=provider,
        model=ModelSpec(provider_id, READER_MODEL),
        template=READER_TEMPLATE,
        max_content_chars=200_000,
        max_tokens=1024,
    )
    judge = Judge(
        provider=provider,
        model=ModelSpec(provider_id, JUDGE_MODEL),
    )

    sem = asyncio.Semaphore(4)

    async def _run(entry: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            try:
                return await _process_one(entry, reader, judge)
            except Exception as exc:  # capture per-row, keep going
                return {"slug": entry["slug"], "error": str(exc)}

    t0 = time.time()
    results = await asyncio.gather(*(_run(e) for e in corpus["urls"]))
    (HERE / "phase3_summary.json").write_text(
        json.dumps(list(results), indent=2, ensure_ascii=False)
    )
    print(f"done in {int(time.time() - t0)}s; {len(results)} rows")
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    sys.exit(main())
