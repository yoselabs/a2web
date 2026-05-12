"""Phase 4: v0.4 server-side extraction (`ask=`) head-to-head with WebFetch.

For each corpus URL:
  1. Call `a2web.fetch(url, ask=task)` via the in-process test client.
     a2web's v0.4 extractor runs Haiku over the fetched content and returns
     a tiny `extracted_answer` — the same trick WebFetch uses internally.
  2. Judge `extracted_answer` against the same criteria used in phase 3.
  3. Re-judge the cached `runs/<slug>/webfetch.txt` answer for an
     apples-to-apples Sonnet verdict in this run.

Outputs:
  - `runs/<slug>/a2web_ask_answer.txt`       — the extracted_answer text
  - `runs/<slug>/a2web_ask_meta.json`        — token / cost / latency
  - `runs/<slug>/score_a2web_ask.json`       — judge verdict
  - `runs/<slug>/score_webfetch_v4.json`     — re-judged WebFetch
  - `phase4_summary.json`                    — aggregated per-row data
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

import a2kit.testing
from a2web.packages.llm_extract import Judge, JudgeParseError, ModelSpec
from a2web.packages.llm_extract import LLMNotAvailable
from a2web.packages.llm_extract.providers.anthropic import AnthropicProvider
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider
from a2web.server import app as a2web_app

HERE = Path(__file__).parent
RUNS = HERE / "runs"
CORPUS = HERE / "corpus.yaml"
JUDGE_MODEL = "claude-sonnet-4-6"


def _pick_provider() -> tuple[Any, str]:
    forced = os.environ.get("A2WEB_BENCH_PROVIDER", "").strip().lower()
    if forced == "anthropic":
        return AnthropicProvider(), "anthropic"
    if forced == "claude-code":
        return ClaudeCodeProvider(), "claude-code"
    try:
        return ClaudeCodeProvider(), "claude-code"
    except LLMNotAvailable as exc:
        print(f"  [info] claude-code unavailable ({exc}); falling back to AnthropicProvider")
        return AnthropicProvider(), "anthropic"


async def _process_one(
    entry: dict[str, Any],
    client: a2kit.testing.TestClient,
    judge: Judge,
) -> dict[str, Any]:
    slug = entry["slug"]
    task = entry["task"]
    criteria = entry["criteria"]
    url = entry["url"]
    run_dir = RUNS / slug
    run_dir.mkdir(parents=True, exist_ok=True)

    row: dict[str, Any] = {
        "slug": slug,
        "class": entry.get("class", "?"),
        "url": url,
        "task": task,
    }

    # 1) a2web fetch with ask=
    t0 = time.perf_counter()
    try:
        resp = await client.invoke("fetch", url=url, ask=task)
    except Exception as exc:
        row["fetch_error"] = repr(exc)
        return row
    wall_ms = int((time.perf_counter() - t0) * 1000)

    ext_answer = getattr(resp, "extracted_answer", None) or ""
    ext_meta = getattr(resp, "extraction", None)

    (run_dir / "a2web_ask_answer.txt").write_text(ext_answer)
    meta_payload = {
        "wall_ms": wall_ms,
        "status": getattr(resp, "status", None),
        "tier": getattr(resp, "tier", None),
        "confidence": str(getattr(resp, "confidence", None)),
        "extraction": ext_meta.model_dump() if ext_meta is not None else None,
    }
    (run_dir / "a2web_ask_meta.json").write_text(json.dumps(meta_payload, indent=2, default=str))
    row.update(meta_payload)
    row["extracted_answer_chars"] = len(ext_answer)

    # 2) Judge a2web_ask
    if ext_answer.strip():
        try:
            verdict = await judge.score(task=task, criteria=criteria, answer=ext_answer)
            v_dict = asdict(verdict)
            (run_dir / "score_a2web_ask.json").write_text(json.dumps(v_dict, indent=2, ensure_ascii=False))
            row["a2web_ask_score"] = v_dict
        except JudgeParseError as exc:
            row["a2web_ask_score"] = {"error": str(exc), "raw": exc.raw_text[:500]}
    else:
        row["a2web_ask_score"] = {"error": "empty extracted_answer"}

    # 3) Re-judge WebFetch (apples to apples in this run)
    wf_path = run_dir / "webfetch.txt"
    if wf_path.exists():
        wf_text = wf_path.read_text()
        try:
            verdict = await judge.score(task=task, criteria=criteria, answer=wf_text)
            v_dict = asdict(verdict)
            (run_dir / "score_webfetch_v4.json").write_text(json.dumps(v_dict, indent=2, ensure_ascii=False))
            row["webfetch_score"] = v_dict
        except JudgeParseError as exc:
            row["webfetch_score"] = {"error": str(exc), "raw": exc.raw_text[:500]}
    else:
        row["webfetch_score"] = {"error": "no webfetch.txt"}

    print(f"  [{slug}] done  a2web_ask={row.get('a2web_ask_score', {}).get('overall')}  webfetch={row.get('webfetch_score', {}).get('overall')}")
    return row


async def _amain() -> int:
    corpus = yaml.safe_load(CORPUS.read_text())
    provider, provider_id = _pick_provider()
    print(f"  [info] provider={provider_id}")
    judge = Judge(provider=provider, model=ModelSpec(provider_id, JUDGE_MODEL))

    sem = asyncio.Semaphore(3)  # a2web fetch hits real URLs — be polite

    async with a2kit.testing.client(a2web_app) as client:
        async def _run(entry: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                try:
                    return await _process_one(entry, client, judge)
                except Exception as exc:
                    return {"slug": entry["slug"], "error": repr(exc)}

        t0 = time.time()
        results = await asyncio.gather(*(_run(e) for e in corpus["urls"]))
        (HERE / "phase4_summary.json").write_text(
            json.dumps(list(results), indent=2, ensure_ascii=False, default=str)
        )
        print(f"done in {int(time.time() - t0)}s; {len(results)} rows")
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    sys.exit(main())
