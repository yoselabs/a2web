# Bench findings — post a2kit v0.43 migration

Date: 2026-06-11
Run: `eval/runs/2026-06-11_024938` (gitignored, regenerable)
Provider: `claude-code` (no `ANTHROPIC_API_KEY`; on the Claude Code OAuth session)
Context: sanity bench after the a2kit v0.41 → v0.43 migration (ADR-0028 subclass
App + canonical-name pins; ADR-0027 LDD-on-stdlib-logging). Goal was to confirm
the framework migration moved no output quality/cost, and that the reworked
`LiveSink` (now a `logging.Handler`) still renders the live console.

## Headline: no regression

The migration was framework-surface only and the bench bears that out —
a2web_extract remains the quality + clarity + contract winner, in line with
prior runs.

| System | quality (0-5) | env tokens | clarity (0-5) | contract | reach | per-URL wins |
|---|---|---|---|---|---|---|
| webfetch_baseline | 3.27 | 174 | 3.50 | — | 8/11 | 6 |
| a2web_detail | 3.73 | 3677 | 1.30 | 11/11 | 10/11 | 8 |
| a2web_extract | **4.09** | 442 | **4.70** | 11/11 | 10/11 | **9** |

vs WebFetch baseline: a2web_extract **+0.82 quality / +1.20 clarity** at +268 env
tokens; a2web_detail +0.45 quality but −2.20 clarity (it returns full page
markdown — expected for the "detail" mode, 3677 env tokens).

By URL class, the standout is **spa**: baseline `0.00`, a2web_detail `2.00`,
a2web_extract `5.00`. The React SPA (`spa-react-dev`) 404'd the WebFetch
baseline outright; both a2web modes rendered it via `tier=raw`. Confirms the
adaptive cascade earns its keep where the naive fetch can't.

Cost: total **$1.86** (fetch $0.63 + judge $1.23) over 33 cells, $0.056/row.
a2web_detail has $0 fetch (no LLM extraction step) but the highest judge cost.

## LiveSink — the migration's one behavioral risk: PASS

The reworked `LiveSink(logging.Handler)` rendered the full run live: per-cell
`▶ start` / `[n/33] ✓/✗` lines with the monotonic counter, AND the 30s
heartbeat fired correctly mid-run (`… running: 4, done: 28/33, cost: $1.52`).
The threading.RLock-via-`self.lock` + retained async heartbeat behaves exactly
as designed — no console garbling, no missed events, no deadlock.

## Expected non-issues (not regressions)

- **3 fetch errors**, all pre-existing behavior:
  - `spa-react-dev × webfetch_baseline` — HTTP 404 (baseline can't render the SPA;
    a2web wins this URL).
  - `reddit-listing × a2web_extract` — `tier=raw verdict=length_floor`, `js_required`.
  - `reddit-comments × a2web_detail` — `tier=raw verdict=not_found`, `js_required`.
  - Reddit is JS-gated; raw tier hits the floor. Known corpus behavior.
- **`llm_wobble` warnings** on `obstacle` / `try_url` (router-shape closed-enum)
  — the wobble recovery funnel doing its job (recovered, logged, not dropped).
  Pre-existing; unrelated to the migration.

## Operational note — shutdown hang (KNOWN, pre-existing)

After `write_all(report)` the process hung at 0% CPU with Camoufox/Firefox
subprocesses still alive; killed manually. This is the documented
`bench-shutdown-thread-leak` (`BACKLOG.md:111`,
`eval/findings_2026-05-26-shutdown-thread-leak-spike.md`) — a non-daemon thread /
browser-teardown issue, NOT introduced by the v0.43 migration. The report writes
fully before the hang, so all artifacts are intact.
