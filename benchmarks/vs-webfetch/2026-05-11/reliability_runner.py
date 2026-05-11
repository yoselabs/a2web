"""Reliability runner — runs any model x any reliability corpus.

Modes:
  --mode inject        run injection.yaml against a model set
  --mode hallucinate   run hallucination.yaml
  --mode determinism   re-run a single corpus N times and measure variance

  --models <comma-list>          override default model set
  --models-from-survivors <N>    pick top N from stage 2 survivors

Default model set when neither flag is set:
  - stage 2 survivors (top 5 from the winnow)

Synthetic content: corpus entries carry `content:` inline (not a URL).
The runner feeds that directly into the Extractor; no HTTP.

Outputs:
  multi_model_runs/reliability_<mode>/<model_safe>/<slug>.{ans.txt,meta.json,score.json}
  reliability_summary_<mode>.json
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).parent
CORPORA = HERE / "reliability_corpora"
STATE = HERE / "multi_model_state.json"
MM_RUNS = HERE / "multi_model_runs"


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

from a2web.llm import Extractor, Judge, JudgeParseError, ModelSpec  # noqa: E402
from a2web.llm.errors import LLMNotAvailable  # noqa: E402
from a2web.llm.prompts import WEBFETCH_DEFAULT_V1  # noqa: E402
from a2web.llm.providers.anthropic import AnthropicProvider  # noqa: E402
from a2web.llm.providers.claude_code import ClaudeCodeProvider  # noqa: E402
from a2web.llm.providers.ollama import OllamaProvider  # noqa: E402
from a2web.llm.providers.openrouter import OpenRouterProvider  # noqa: E402

JUDGE_MODEL = "claude-sonnet-4-6"
import re

def _safe(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name)


def _resolve_models(args: argparse.Namespace) -> list[str]:
    if args.models:
        return [m.strip() for m in args.models.split(",") if m.strip()]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    survivors = state.get("survivors", {}).get("stage2") or []
    if args.models_from_survivors:
        return survivors[: args.models_from_survivors]
    return survivors


def _provider_for(model: str) -> tuple[Any, str]:
    """Route by model id: tag-style (no slash) → local Ollama; else → OpenRouter."""
    # Ollama tags don't contain '/'; OpenRouter slugs always do.
    if "/" not in model:
        return OllamaProvider(), "ollama"
    return OpenRouterProvider(), "openrouter"


async def _judge() -> Judge:
    try:
        return Judge(provider=ClaudeCodeProvider(), model=ModelSpec("claude-code", JUDGE_MODEL))
    except LLMNotAvailable:
        return Judge(provider=AnthropicProvider(), model=ModelSpec("anthropic", JUDGE_MODEL))


async def _extract_judge(
    model: str,
    entry: dict[str, Any],
    extractor: Extractor,
    judge: Judge,
    out_dir: Path,
    run_id: int = 0,
) -> dict[str, Any]:
    slug = entry["slug"]
    task = entry["task"]
    criteria = entry["criteria"]
    content = entry["content"]

    t0 = time.perf_counter()
    try:
        r = await extractor.extract(content=content, ask=task)
    except Exception as exc:
        return {"model": model, "slug": slug, "run": run_id, "error": f"extract: {exc!r}"}
    wall = int((time.perf_counter() - t0) * 1000)

    tag = f"_r{run_id}" if run_id else ""
    (out_dir / f"{slug}{tag}.ans.txt").write_text(r.answer)
    meta = {
        "model": r.model,
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "cost_usd": r.cost_usd,
        "latency_ms": r.latency_ms or wall,
        "cache_hit": r.cache_hit,
    }
    (out_dir / f"{slug}{tag}.meta.json").write_text(json.dumps(meta, indent=2))

    row: dict[str, Any] = {
        "model": model,
        "slug": slug,
        "run": run_id,
        "class": entry.get("class", "?"),
        **meta,
        "answer": r.answer,
        "answer_chars": len(r.answer),
    }

    if r.answer.strip():
        try:
            v = await judge.score(task=task, criteria=criteria, answer=r.answer)
            v_dict = asdict(v)
            (out_dir / f"{slug}{tag}.score.json").write_text(json.dumps(v_dict, indent=2))
            row["judge"] = {"overall": v.overall, "reached": v.reached, "scores": v.scores}
        except JudgeParseError as exc:
            row["judge"] = {"error": str(exc)[:120]}
    else:
        row["judge"] = {"error": "empty"}

    return row


async def _run_corpus(
    mode: str,
    models: list[str],
    corpus_path: Path,
    runs_per_cell: int = 1,
) -> dict[str, Any]:
    corpus = yaml.safe_load(corpus_path.read_text())
    entries = corpus["urls"]
    stage_dir = MM_RUNS / f"reliability_{mode}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    judge = await _judge()
    sem = asyncio.Semaphore(4)

    async def _cell(model: str, entry: dict[str, Any], run_id: int) -> dict[str, Any]:
        async with sem:
            try:
                provider, pname = _provider_for(model)
            except LLMNotAvailable as exc:
                return {"model": model, "slug": entry["slug"], "run": run_id, "error": f"provider: {exc}"}
            ex = Extractor(
                provider=provider,
                model=ModelSpec(pname, model),
                template=WEBFETCH_DEFAULT_V1,
                max_content_chars=100_000,
                max_tokens=1024,
            )
            out_dir = stage_dir / _safe(model)
            out_dir.mkdir(parents=True, exist_ok=True)
            row = await _extract_judge(model, entry, ex, judge, out_dir, run_id=run_id)
            j = row.get("judge", {})
            score = j.get("overall") if isinstance(j, dict) else None
            err = row.get("error")
            tag = f"err={err}" if err else f"score={score} tok={row.get('completion_tokens')} ${row.get('cost_usd', 0):.5f}"
            run_tag = f"r{run_id}" if run_id else ""
            print(f"  [{mode}{run_tag}] {model:<48} {entry['slug']:<22} {tag}", flush=True)
            return row

    t0 = time.time()
    tasks = [_cell(m, e, i) for m in models for e in entries for i in range(runs_per_cell)]
    rows = await asyncio.gather(*tasks)
    wall = int(time.time() - t0)

    summary = _summarize(rows, mode, runs_per_cell)
    out = {
        "mode": mode,
        "models": models,
        "corpus": str(corpus_path.relative_to(HERE)),
        "wall_seconds": wall,
        "runs_per_cell": runs_per_cell,
        "per_model": summary,
        "rows": rows,
    }
    (HERE / f"reliability_summary_{mode}.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    return out


def _summarize(rows: list[dict[str, Any]], mode: str, runs_per_cell: int) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"cells_ok": 0, "errors": 0, "overall": [], "cost": 0.0, "latency": []}
    )
    for r in rows:
        m = r["model"]
        b = by_model[m]
        if "error" in r:
            b["errors"] += 1
            continue
        b["cells_ok"] += 1
        b["cost"] += float(r.get("cost_usd", 0) or 0)
        b["latency"].append(int(r.get("latency_ms", 0) or 0))
        j = r.get("judge", {})
        if isinstance(j, dict) and "overall" in j:
            b["overall"].append(int(j["overall"]))
    out: dict[str, Any] = {}
    for m, b in by_model.items():
        mean = sum(b["overall"]) / len(b["overall"]) if b["overall"] else None
        out[m] = {
            "cells_ok": b["cells_ok"],
            "errors": b["errors"],
            "mean_overall": mean,
            "total_cost_usd": round(b["cost"], 6),
            "mean_latency_ms": int(sum(b["latency"]) / len(b["latency"])) if b["latency"] else 0,
        }

    # Determinism: variance across runs for same (model, slug)
    if runs_per_cell > 1:
        det: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"answer_similarity": [], "score_variance": []}
        )
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            if "error" in r:
                continue
            groups[(r["model"], r["slug"])].append(r)
        for (model, slug), runs in groups.items():
            if len(runs) < 2:
                continue
            answers = [r.get("answer", "") for r in runs]
            scores = [
                r.get("judge", {}).get("overall")
                for r in runs
                if isinstance(r.get("judge"), dict) and "overall" in r.get("judge", {})
            ]
            # Pairwise SequenceMatcher ratios on answers
            sims = []
            for i in range(len(answers)):
                for j in range(i + 1, len(answers)):
                    sims.append(difflib.SequenceMatcher(None, answers[i], answers[j]).ratio())
            mean_sim = sum(sims) / len(sims) if sims else 1.0
            score_var = max(scores) - min(scores) if len(scores) >= 2 else 0
            det[model]["answer_similarity"].append(mean_sim)
            det[model]["score_variance"].append(score_var)
        for m, d in det.items():
            out[m]["determinism"] = {
                "mean_answer_similarity": (
                    sum(d["answer_similarity"]) / len(d["answer_similarity"])
                    if d["answer_similarity"]
                    else None
                ),
                "max_score_variance": max(d["score_variance"]) if d["score_variance"] else 0,
                "n_slugs": len(d["answer_similarity"]),
            }
    return out


async def _amain(args: argparse.Namespace) -> int:
    models = _resolve_models(args)
    if not models:
        print("No models resolved. Pass --models or run stages 0-2 first.")
        return 1
    print(f"[reliability {args.mode}] models={len(models)}: {models}")
    if args.mode == "inject":
        await _run_corpus("inject", models, CORPORA / "injection.yaml", runs_per_cell=1)
    elif args.mode == "hallucinate":
        await _run_corpus("hallucinate", models, CORPORA / "hallucination.yaml", runs_per_cell=1)
    elif args.mode == "language":
        await _run_corpus("language", models, CORPORA / "language.yaml", runs_per_cell=1)
    elif args.mode == "determinism":
        # Reuse the small balanced subset from stage 1 corpus
        det_corpus = HERE / "reliability_corpora" / "determinism_corpus.yaml"
        if not det_corpus.exists():
            # Build it on the fly from main corpus + STAGE1_SLUGS
            main = yaml.safe_load((HERE / "corpus.yaml").read_text())
            from itertools import islice  # noqa
            STAGE1 = {"wikipedia-rust", "linear-marketing", "vercel-blog", "github-issue", "non-english"}
            picks = [u for u in main["urls"] if u["slug"] in STAGE1]
            # Inline content from cached fetched payload (same path runner uses)
            for u in picks:
                payload_path = HERE / "runs" / u["slug"] / "a2web_C_content_only.json"
                if not payload_path.exists():
                    payload_path = HERE / "runs" / u["slug"] / "a2web_A_full.json"
                if payload_path.exists():
                    p = json.loads(payload_path.read_text())
                    u["content"] = p.get("content_md") or ""
            det_corpus.write_text(yaml.safe_dump({"urls": picks}, sort_keys=False, allow_unicode=True))
        await _run_corpus("determinism", models, det_corpus, runs_per_cell=3)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=["inject", "hallucinate", "determinism", "language"])
    p.add_argument("--models", type=str, default="", help="comma-list of model ids")
    p.add_argument("--models-from-survivors", type=int, default=0)
    args = p.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
