"""Phase 3: reader + judge pipeline.

For each URL in the corpus:
  1. Build 4 "answers":
     - webfetch:    contents of runs/<slug>/webfetch.txt (already an answer)
     - a2web_A:     reader(claude haiku) over runs/<slug>/a2web_A_full.json + task
     - a2web_B:     reader over a2web_B_meta.json
     - a2web_C:     reader over a2web_C_content_only.json
  2. For each answer, run blind judge (claude sonnet) against criteria.
     Judge returns JSON: {scores: [0-5 per criterion], overall: 0-5, reasoning: ""}

Outputs per slug: answer_<system>.txt, score_<system>.json.
Aggregates into phase3_summary.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).parent
RUNS = HERE / "runs"
CORPUS = HERE / "corpus.yaml"

READER_MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-sonnet-4-6"


def claude_p(prompt: str, model: str, timeout: int = 180) -> str:
    """Call `claude -p` as a subprocess and return stdout text."""
    proc = subprocess.run(
        ["claude", "-p", "--model", model],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        return f"[CLI ERROR rc={proc.returncode}] {proc.stderr[:500]}"
    return proc.stdout.strip()


def read_answer(payload_json: str, task: str) -> str:
    """Have a reader model produce an answer to `task` from `payload_json`."""
    prompt = (
        "You are a downstream agent that received a web-fetch response from a tool. "
        "Read the response and answer the user's question concisely. "
        "If the response does not contain the information needed (e.g. it is a block page, "
        "404, login wall, or otherwise lacks the substantive content), say so explicitly and "
        "describe what kind of response you received. Do not invent content.\n\n"
        f"=== FETCH RESPONSE (JSON) ===\n{payload_json}\n=== END ===\n\n"
        f"QUESTION: {task}\n\n"
        "Your answer:"
    )
    return claude_p(prompt, READER_MODEL)


JSON_RE = re.compile(r"\{[\s\S]*\}")


def judge_answer(criteria: list[str], task: str, answer: str) -> dict[str, Any]:
    """Score an answer against criteria. Returns parsed JSON or {error: ...}."""
    crit_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(criteria))
    prompt = (
        "You are a strict, blind judge evaluating an answer to a question about a web page. "
        "You do NOT know which system produced this answer. Score it against the criteria below. "
        "Be terse and honest. Penalize fabrication. Reward concise correctness. "
        "Reward acknowledging 'fetch failed / no content' when that is honest, but a failed fetch "
        "still scores low on substantive criteria since it didn't deliver the information.\n\n"
        f"QUESTION ASKED: {task}\n\n"
        f"CRITERIA (each scored 0-5, where 0=absent, 3=partial, 5=fully satisfied):\n{crit_text}\n\n"
        f"ANSWER TO JUDGE:\n{answer}\n\n"
        'Respond with STRICT JSON ONLY, no prose, no markdown fence, in this exact shape:\n'
        '{"scores":[<int per criterion>], "overall":<int 0-5>, '
        '"reached":<bool: did the answer convey real page content, not a failure notice>, '
        '"reasoning":"<one sentence>"}'
    )
    raw = claude_p(prompt, JUDGE_MODEL)
    m = JSON_RE.search(raw)
    if not m:
        return {"error": "no_json", "raw": raw[:500]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"error": f"json_decode: {e}", "raw": raw[:500]}


def process_one(entry: dict[str, Any]) -> dict[str, Any]:
    slug = entry["slug"]
    task = entry["task"]
    criteria = entry["criteria"]
    run_dir = RUNS / slug
    if not run_dir.exists():
        return {"slug": slug, "error": "missing run dir"}

    result: dict[str, Any] = {"slug": slug, "class": entry["class"], "task": task, "scores": {}}

    # System 1: WebFetch (already an answer)
    wf_text = (run_dir / "webfetch.txt").read_text()
    (run_dir / "answer_webfetch.txt").write_text(wf_text)

    # Systems 2-4: a2web variants → reader
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
        if len(payload) > 200_000:  # safety cap
            payload = payload[:200_000] + "\n[TRUNCATED]"
        ans = read_answer(payload, task)
        (run_dir / f"answer_{sys_name}.txt").write_text(ans)

    # Judge all 4 answers
    for sys_name in ["webfetch", "a2web_A", "a2web_B", "a2web_C"]:
        ans_path = run_dir / f"answer_{sys_name}.txt"
        if not ans_path.exists():
            result["scores"][sys_name] = {"error": "no answer"}
            continue
        ans = ans_path.read_text()
        verdict = judge_answer(criteria, task, ans)
        (run_dir / f"score_{sys_name}.json").write_text(json.dumps(verdict, indent=2))
        result["scores"][sys_name] = verdict

    print(f"  [{slug}] done")
    return result


def main() -> int:
    corpus = yaml.safe_load(CORPUS.read_text())
    t0 = time.time()
    results = []
    # Parallelize across URLs but keep concurrency modest to avoid CLI thrash.
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(process_one, e): e["slug"] for e in corpus["urls"]}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001
                results.append({"slug": futures[fut], "error": str(e)})
    (HERE / "phase3_summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )
    print(f"done in {int(time.time() - t0)}s; {len(results)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
