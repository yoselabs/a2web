#!/usr/bin/env python
"""Methodology-as-code: the a2web extraction-backend model benchmark.

Runs the a2web output bench (`python -m a2web.llm_eval`) once per candidate in
`models.yaml`, all through a single OpenAI-compatible endpoint (OpenRouter),
scored by a fixed strong judge — then aggregates every model's four-axis scores
plus **actual cost** (captured extraction tokens × live OpenRouter prices) into
a committed, provenance-stamped result file under `results/`.

Why committed: this is a reference experiment we re-run every few months and
after prompt/parser ("prescription") changes; the JSON result is the durable
trace so runs stay comparable over time. The raw per-cell run dirs
(`runs/`) are gitignored/regenerable — only the aggregate `results/*.json` +
`*.md` are kept.

Reproduce:

    OPENAI_API_KEY=<openrouter-key> \\
    OPENAI_BASE_URL=https://openrouter.ai/api/v1 \\
    uv run python eval/model_benchmark/run.py

Secrets are env-only; nothing is written to the repo but the aggregate result.
Flags: --skip-run (aggregate an existing runs dir only), --date YYYY-MM-DD.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).parent
CORPUS = HERE / "corpus.yaml"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _load_models() -> dict[str, Any]:
    return yaml.safe_load((HERE / "models.yaml").read_text())


def _provenance(date: str, cfg: dict[str, Any]) -> dict[str, Any]:
    def _git(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=HERE, text=True).strip()
        except Exception:
            return "unknown"

    version = "unknown"
    try:
        pyproject = (HERE.parents[1] / "pyproject.toml").read_text()
        for line in pyproject.splitlines():
            if line.startswith("version"):
                version = line.split("=", 1)[1].strip().strip('"')
                break
    except Exception:
        pass
    return {
        "date": date,
        "a2web_version": version,
        "git_sha": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "judge": cfg["judge"],
        "reference": cfg["reference"],
        "corpus": CORPUS.name,
        "endpoint": os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        # The "prescription" — bump this note when the extraction prompt or the
        # router-shape parser changes, so a future reader knows what produced
        # these numbers.
        "prescription_note": os.environ.get("A2WEB_BENCH_PRESCRIPTION", "see git_sha"),
    }


def _fetch_prices(base_url: str, key: str) -> dict[str, tuple[float, float]]:
    req = urllib.request.Request(f"{base_url}/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - trusted OpenRouter host
        data = json.load(resp)
    out: dict[str, tuple[float, float]] = {}
    for m in data.get("data", []):
        p = m.get("pricing") or {}
        try:
            out[m["id"]] = (float(p["prompt"]), float(p["completion"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _run_one(model: str, judge: str, out_dir: Path, base_url: str) -> None:
    env = {**os.environ, "A2WEB_BENCH_PROVIDER": "openai_compatible", "OPENAI_BASE_URL": base_url, "OPENAI_MODEL": model}
    subprocess.run(
        [
            sys.executable, "-m", "a2web.llm_eval",
            "--corpus", str(CORPUS), "--mode", "detail",
            "--judge-model", judge, "--concurrency", "4",
            "--output-dir", str(out_dir),
        ],
        env=env, check=False,
    )


def _score(run_dir: Path, prices: dict[str, tuple[float, float]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in sorted(run_dir.iterdir()):
        tsv = d / "results.tsv"
        if not tsv.exists():
            continue
        model = d.name.replace("_", "/", 1)
        pin, pout = prices.get(model, (0.0, 0.0))
        overall: list[float] = []
        clarity: list[float] = []
        nlink: list[float] = []
        contract = ptok = ctok = fails = n = 0
        for r in csv.DictReader(tsv.open(), delimiter="\t"):
            if r["system"] != "a2web_extract":
                continue
            n += 1
            fails += 1 if r["fetch_error"] else 0
            overall.append(float(r["judge_overall"] or 0))
            contract += 1 if r["contract_conformant"] == "True" else 0
            if r["clarity_score"]:
                clarity.append(float(r["clarity_score"]))
            if r["next_links_score"]:
                nlink.append(float(r["next_links_score"]))
            ptok += int(r["fetch_prompt_tokens"] or 0)
            ctok += int(r["fetch_completion_tokens"] or 0)
        mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
        rows.append({
            "model": model,
            "n_cells": n,
            "fetch_fails": fails,
            "quality": mean(overall),
            "contract_pass": f"{contract}/{n}",
            "clarity": mean(clarity),
            "next_links": mean(nlink),
            "extraction_prompt_tokens": ptok,
            "extraction_completion_tokens": ctok,
            "extraction_cost_usd": round(ptok * pin + ctok * pout, 6),
            "price_in_per_1m": round(pin * 1e6, 4),
            "price_out_per_1m": round(pout * 1e6, 4),
        })
    rows.sort(key=lambda x: (-(x["quality"] or 0), x["extraction_cost_usd"]))
    return rows


def _write_md(path: Path, prov: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        f"# a2web model benchmark — {prov['date']}",
        "",
        f"a2web `{prov['a2web_version']}` @ `{prov['git_sha']}`"
        f"{' (dirty)' if prov['git_dirty'] else ''} · judge `{prov['judge']}` · "
        f"reference `{prov['reference']}` · corpus `{prov['corpus']}`",
        f"prescription: {prov['prescription_note']}",
        "",
        "| model | quality | contract | clarity | next_links | cost (corpus) | in/out /1M |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['model']}` | {r['quality']} | {r['contract_pass']} | {r['clarity']} | "
            f"{r['next_links']} | ${r['extraction_cost_usd']:.4f} | "
            f"{r['price_in_per_1m']}/{r['price_out_per_1m']} |"
        )
    lines += ["", "Cost is extraction only (candidate model), over the committed corpus; judge cost is a fixed overhead not attributed to candidates.", ""]
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="run date label (default: today via env A2WEB_BENCH_DATE)")
    ap.add_argument("--skip-run", action="store_true", help="aggregate existing runs/<date> only")
    args = ap.parse_args()

    cfg = _load_models()
    date = args.date or os.environ.get("A2WEB_BENCH_DATE")
    if not date:
        print("provide --date YYYY-MM-DD (or A2WEB_BENCH_DATE); Date.now() is intentionally not used", file=sys.stderr)
        return 2
    key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
    if not key:
        print("set OPENAI_API_KEY (OpenRouter key) in the env", file=sys.stderr)
        return 2

    run_dir = HERE / "runs" / date
    if not args.skip_run:
        run_dir.mkdir(parents=True, exist_ok=True)
        for model in cfg["candidates"]:
            print(f"=== {model} ===", flush=True)
            _run_one(model, cfg["judge"], run_dir / model.replace("/", "_"), base_url)

    prices = _fetch_prices(base_url, key)
    rows = _score(run_dir, prices)
    prov = _provenance(date, cfg)
    result = {"provenance": prov, "prices_snapshot_per_1m": {r["model"]: [r["price_in_per_1m"], r["price_out_per_1m"]] for r in rows}, "leaderboard": rows}

    (HERE / "results" / f"{date}.json").write_text(json.dumps(result, indent=2))
    _write_md(HERE / "results" / f"{date}.md", prov, rows)
    print(f"wrote results/{date}.json + results/{date}.md ({len(rows)} models)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
